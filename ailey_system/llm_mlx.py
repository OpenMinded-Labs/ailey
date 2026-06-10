# -*- coding: utf-8 -*-
"""
MLX-based LLM backend for Ailey on Apple Silicon.

Optimized for M4 24GB with Ministral 14B Reasoning 5-bit.
Supports multiple model families (Mistral, Qwen, Llama, Gemma) via mlx-lm.

Performance Optimizations:
  - Warmup call compiles Metal kernels ahead of time
  - KV-cache reuse for faster subsequent generations (prompt caching)
  - Top-p + repetition_penalty for quality without speed loss
  - Memory-mapped model weights (no full copy into RAM)
  - Streaming for perceived responsiveness

Configuration via environment variables:
  AILEY_MLX_MODEL: HuggingFace model ID or local path (default: Ministral-3-14B-Reasoning-5bit)
  AILEY_MLX_MAX_TOKENS: max generation tokens (default: 540)
  AILEY_MLX_TEMP: temperature (default: 0.7)
  AILEY_MLX_REPETITION_PENALTY: repetition penalty (default: 1.1)
  AILEY_MLX_TOP_P: top-p sampling (default: 0.9)

Usage:
    gen = MLXGenerator.get()
    if gen:
        text = gen.generate(system, user, params)
        # or streaming:
        for chunk in gen.stream(system, user, params):
            print(chunk, end="")
"""
from __future__ import annotations
import os
import time
import threading
from typing import Dict, Optional, Iterator

# ═══════════════════════════════════════════════════════════════════════
# Training-Data Capture Hook
# ═══════════════════════════════════════════════════════════════════════
# Thread-local context — callers wrap LLM calls with training_capture(...)
# to auto-forward (system, user, assistant, reasoning) to _collect_training_pair.
# Reasoning is extracted from <think>...</think> tags if present.
import re as _tc_re

_training_ctx = threading.local()


class training_capture:
    """Context manager that tags the next MLXGenerator.generate() call for training
    collection. Only ONE output per context is collected (to avoid dup forwarding
    from internal retry/fallback chains).

    Usage:
        with training_capture(source="song_lyrics", mood="creative", topics=["song"]):
            text = gen.generate(sys, user, params)

    Args:
        source:  e.g. "song_lyrics", "book_chapter", "image_prompt", "svg_art",
                 "krap_lyrics", "blog_writing", "deep_think".
        mood:    current Ailey mood tag
        topics:  list of topic tags
        min_len: minimum assistant length to collect (default 80)
    """
    def __init__(self, *, source: str, mood: str = "neutral",
                 topics=None, flags=None, user_type: str = "ailey_idle",
                 engine: str = "ministral", min_len: int = 80,
                 is_gold: bool = False):
        self.ctx = {
            "source": source,
            "mood": mood,
            "topics": topics or [source],
            "flags": flags or [],
            "user_type": user_type,
            "engine": engine,
            "min_len": int(min_len),
            "is_gold": bool(is_gold),
            "consumed": False,
        }
        self._prev = None

    def __enter__(self):
        self._prev = getattr(_training_ctx, "active", None)
        _training_ctx.active = self.ctx
        return self

    def __exit__(self, exc_type, exc, tb):
        _training_ctx.active = self._prev
        return False


def _split_reasoning(text: str) -> tuple:
    """Extract <think>...</think> as reasoning; return (reasoning, clean_text).
    Supports: <think>, <thinking>, <reasoning>, [THINK] variants (case-insensitive).
    """
    if not text:
        return "", ""
    # Pull out all thinking blocks
    patterns = [
        r'<think(?:ing)?>(.*?)</think(?:ing)?>',
        r'<reasoning>(.*?)</reasoning>',
        r'<thought>(.*?)</thought>',
        r'\[THINK(?:ING)?\](.*?)\[/THINK(?:ING)?\]',
    ]
    reasoning_parts = []
    clean = text
    for pat in patterns:
        for m in _tc_re.finditer(pat, clean, flags=_tc_re.DOTALL | _tc_re.IGNORECASE):
            reasoning_parts.append(m.group(1).strip())
        clean = _tc_re.sub(pat, '', clean, flags=_tc_re.DOTALL | _tc_re.IGNORECASE)
    return "\n\n".join(p for p in reasoning_parts if p).strip(), clean.strip()


def _forward_to_training(system: str, user: str, response: str, ctx: Dict):
    """Send one captured (sys,user,response) to _collect_training_pair. Safe-noop on error."""
    if ctx.get("consumed"):
        return
    ctx["consumed"] = True
    try:
        reasoning, clean_response = _split_reasoning(response)
        # Sanity filter
        if len(clean_response) < int(ctx.get("min_len", 80)):
            return
        if not user.strip() or not system.strip():
            return
        # Combine system + user into user_prompt so downstream has full context.
        # We keep raw system+user separable via JSON structure too — but the
        # collector expects a single user_prompt string, so prepend system.
        full_user = f"[SYSTEM]\n{system.strip()}\n\n[USER]\n{user.strip()}"
        try:
            from ailey_api import _collect_training_pair as _fwd
        except Exception:
            return
        _fwd(
            user_prompt=full_user,
            assistant_response=clean_response,
            reasoning=reasoning,
            source=ctx.get("source", "llm_direct"),
            user_type=ctx.get("user_type", "ailey_idle"),
            mood=ctx.get("mood", "neutral"),
            topics=ctx.get("topics") or [],
            flags=ctx.get("flags") or [],
            engine=ctx.get("engine", "ministral"),
            is_gold_candidate=bool(ctx.get("is_gold", False)),
        )
    except Exception as _e:
        try:
            print(f"[llm_mlx.training_capture] forward error: {_e}")
        except Exception:
            pass

# Lazy imports to avoid startup crash if mlx not installed
_mlx_lm = None
_make_sampler = None
_tokenizer = None
_model = None
_cache = None  # KV-Cache for prompt caching
_last_system_prompt = None  # Track if system prompt changed


def clear_prompt_cache():
    """Clear the MLX prompt KV-cache (e.g. after long conversations to reclaim memory)."""
    global _cache
    _cache = None
    print("[LLM-MLX] KV prompt cache cleared")

_active_model_tag = "chat"  # "chat" = Ministral (default), "coder" = Qwen2.5-Coder-14B

# CRITICAL: MLX Metal GPU operations are NOT thread-safe!
# This lock ensures only ONE generation runs at a time.
# Using RLock (reentrant) to allow nested calls from same thread (e.g., fallback in stream)
_mlx_lock = threading.RLock()
# When True, _ensure_loaded will NOT automatically load the model — used to honor explicit unload
__block_autoreload = False

def block_auto_reload():
    global __block_autoreload
    __block_autoreload = True


def allow_auto_reload():
    global __block_autoreload
    __block_autoreload = False



def _ensure_loaded():
    """Lazy-load MLX model on first use. Thread-safe via lock."""
    global _mlx_lm, _make_sampler, _tokenizer, _model
    # If another part of the system requested the model to remain unloaded,
    # do not auto-load here — return False so callers can handle it.
    try:
        if __block_autoreload:
            return False
    except Exception:
        pass
    if _model is not None:
        return True
    
    # Lock for thread-safe model loading
    with _mlx_lock:
        # Double-check after acquiring lock (another thread might have loaded it)
        if _model is not None:
            return True
        try:
            import mlx_lm
            from mlx_lm.sample_utils import make_sampler
            _mlx_lm = mlx_lm
            _make_sampler = make_sampler
        except ImportError:
            return False

        # Project root and local model directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_model_dir = os.path.join(project_root, "mlx_models")
        
        # Default to Ministral 14B Reasoning 5-bit (best quality/speed for M4 24GB)
        default_model = os.path.join(local_model_dir, "Ministral-3-14B-Reasoning-5bit")
        HF_MODEL_ID = "mlx-community/Ministral-3-14B-Instruct-Reasoning-5bit"
        model_id = default_model  # Always use default model, ignore AILEY_MLX_MODEL
        
        # If relative path or just model name, resolve to local mlx_models folder
        if not os.path.isabs(model_id) and not model_id.startswith("mlx-community/"):
            potential_local = os.path.join(local_model_dir, model_id)
            if os.path.isdir(potential_local):
                model_id = potential_local
        
        # Setze HuggingFace Cache auf Projektordner (für HF downloads)
        os.makedirs(local_model_dir, exist_ok=True)
        os.environ["HF_HOME"] = local_model_dir
        os.environ["HUGGINGFACE_HUB_CACHE"] = local_model_dir
        
        # Auto-download: if local model dir does not exist, download from HuggingFace
        if not os.path.isdir(model_id) or not os.path.isfile(os.path.join(model_id, "config.json")):
            print(f"📦 Modell nicht lokal gefunden: {os.path.basename(model_id)}")
            print(f"⬇️  Lade automatisch herunter: {HF_MODEL_ID} (~9.5 GB) ...")
            print(f"   Zielordner: {local_model_dir}")
            model_id = HF_MODEL_ID  # mlx_lm.load() will download from HuggingFace
        
        try:
            start = time.time()
            print(f"🧠 Loading MLX model: {os.path.basename(model_id)} ...")
            # fix_mistral_regex prevents tokenizer warning for Mistral models
            tokenizer_config = {}
            if "mistral" in model_id.lower():
                tokenizer_config["fix_mistral_regex"] = True
            _model, _tokenizer = mlx_lm.load(model_id, tokenizer_config=tokenizer_config or None)
            
            # If we downloaded from HF, create a symlink for next time
            if model_id == HF_MODEL_ID and not os.path.isdir(default_model):
                try:
                    import glob
                    snap = glob.glob(os.path.join(local_model_dir, "models--*Ministral*5bit", "snapshots", "*", "config.json"))
                    if snap:
                        snap_dir = os.path.dirname(snap[0])
                        os.symlink(snap_dir, default_model)
                        print(f"🔗 Symlink erstellt: {os.path.basename(default_model)} -> {snap_dir}")
                except Exception as link_err:
                    print(f"⚠️  Symlink fehlgeschlagen (kein Problem): {link_err}")
            
            # Warmup call to compile kernels (improves first inference speed)
            _ = mlx_lm.generate(_model, _tokenizer, prompt="Hi", max_tokens=1, verbose=False,
                                kv_bits=8, kv_group_size=64)
            
            elapsed = time.time() - start
            print(f"✅ MLX model loaded in {elapsed:.1f}s (warmed up)")
            return True
        except Exception as e:
            print(f"❌ MLX model load failed: {e}")
            return False


def _detect_chat_template(model_id: str) -> str:
    """Return a chat template hint based on model name."""
    lower = model_id.lower()
    if "ministral" in lower:
        return "ministral"  # Ministral 3 Reasoning uses [SYSTEM_PROMPT][INST] format
    if "mistral" in lower:
        return "mistral"
    if "qwen" in lower:
        return "qwen"
    if "llama" in lower:
        return "llama"
    if "gemma" in lower:
        return "gemma"
    return "chatml"  # generic fallback


# Stop sequences per model family (strings that should terminate generation)
_STOP_SEQUENCES = {
    "ministral": ["</s>"],
    "mistral": ["</s>"],
    "qwen": ["<|im_end|>", "<|im_start|>"],
    "llama": ["<|eot_id|>", "<|end_of_text|>"],
    "gemma": ["<end_of_turn>"],
    "chatml": ["<|im_end|>", "<|im_start|>"],
}


def _format_messages(system: str, user: str, model_id: str, tools: list = None,
                     conversation_turns: list = None) -> str:
    """Format messages into a prompt string using Mistral's multi-turn format.
    
    Prefers the tokenizer's built-in chat_template (via apply_chat_template)
    for maximum compatibility. Falls back to manual templates if unavailable.
    
    Multi-turn support (Mistral-compliant):
        When conversation_turns is provided, the prompt uses proper alternating
        user/assistant messages instead of flattening history into a single
        user message. This matches how Ministral was trained:
            [SYSTEM_PROMPT]...[/SYSTEM_PROMPT]
            [INST]user1[/INST]assistant1</s>
            [INST]user2[/INST]assistant2</s>
            [INST]current_user_msg[/INST]
    
    Args:
        system: System prompt (persona, rules, tools).
        user: Current user message (with context/RAG prepended).
        model_id: Model identifier for template detection.
        tools: Optional list of tool schemas (Mistral function calling format).
        conversation_turns: Optional list of {"role": "user"|"assistant", "content": str}
                           dicts representing previous conversation turns.
                           These are inserted BETWEEN system and the final user message
                           as proper alternating role messages.
    """
    # Build the messages list
    messages = [{"role": "system", "content": system}]
    
    # Insert multi-turn history as proper alternating messages
    if conversation_turns:
        for turn in conversation_turns:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})
    
    # Final user message (contains RAG context + current question)
    messages.append({"role": "user", "content": user})
    
    # Try using the tokenizer's own chat template first (most reliable)
    if _tokenizer is not None:
        try:
            kwargs = dict(
                tokenize=False,
                add_generation_prompt=True,
            )
            # Pass tools to the chat template if provided
            if tools:
                kwargs["tools"] = tools
            prompt = _tokenizer.apply_chat_template(
                messages,
                **kwargs,
            )
            return prompt
        except Exception as e:
            print(f"⚠️ apply_chat_template failed, using manual fallback: {e}")

    # Manual fallback templates (multi-turn aware)
    template = _detect_chat_template(model_id)
    
    # Build multi-turn portion for manual fallback
    history_str = ""
    if conversation_turns:
        for turn in conversation_turns:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if not content:
                continue
            if template == "ministral":
                if role == "user":
                    history_str += f"[INST]{content}[/INST]"
                else:
                    history_str += f"{content}</s>"
            elif template == "qwen":
                if role == "user":
                    history_str += f"<|im_start|>user\n{content}<|im_end|>\n"
                else:
                    history_str += f"<|im_start|>assistant\n{content}<|im_end|>\n"

    if template == "ministral":
        return f"<s>[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT]{history_str}[INST]{user}[/INST]"
    elif template == "mistral":
        return f"<s>[INST] {system}\n\n{user} [/INST]"
    elif template == "qwen":
        return f"<|im_start|>system\n{system}<|im_end|>\n{history_str}<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
    elif template == "llama":
        return f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{system}<|eot_id|><|start_header_id|>user<|end_header_id|>\n{user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    elif template == "gemma":
        return f"<start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n"
    else:
        return f"<|im_start|>system\n{system}<|im_end|>\n{history_str}<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"


class MLXGenerator:
    """Singleton MLX LLM generator with KV-cache optimization."""
    _instance: Optional["MLXGenerator"] = None
    _cached_system_prompt: Optional[str] = None  # Track for KV-cache invalidation
    _gen_count: int = 0                          # Auto KV-cache clear counter
    _AUTO_KV_CLEAR_EVERY: int = 15               # Clear prompt cache every N generations

    @classmethod
    def get(cls) -> Optional["MLXGenerator"]:
        if cls._instance is None:
            if _ensure_loaded():
                cls._instance = MLXGenerator()
            else:
                return None
        return cls._instance

    def _get_stop_sequences(self) -> list:
        """Get stop sequences for the *currently loaded* model.
        
        Uses _active_model_tag (set by swap_to_coder/swap_to_chat) to pick the
        correct stop tokens. Previously used AILEY_MLX_MODEL env var which always
        pointed to Ministral even after swapping to Qwen Coder 14B — BUG FIXED.
        """
        # Use the actual active model tag, not the env var
        tag = _active_model_tag  # "chat" (Ministral), "coder" (Qwen), "fast" (Qwen 1.5B)
        if tag in ("coder", "fast"):
            return _STOP_SEQUENCES.get("qwen", ["<|im_end|>", "<|im_start|>"])
        # Chat = Ministral
        model_id = os.environ.get("AILEY_MLX_MODEL", "ministral")
        template = _detect_chat_template(model_id)
        return _STOP_SEQUENCES.get(template, ["</s>"])

    @staticmethod
    def _strip_stop_sequences(text: str, stop_seqs: list) -> str:
        """Remove any stop sequences from the generated text."""
        for seq in stop_seqs:
            if seq in text:
                text = text[:text.index(seq)]
        return text

    @staticmethod
    def _check_stop_in_buffer(buffer: str, stop_seqs: list) -> bool:
        """Check if any stop sequence appears in the accumulated buffer."""
        for seq in stop_seqs:
            if seq in buffer:
                return True
        return False

    def generate(self, system: str, user: str, params: Dict, tools: list = None,
                 conversation_turns: list = None, interruptible: bool = False) -> str:
        """Generate a complete response with optimized sampling.
        
        Thread-safe: Uses a lock to prevent concurrent MLX Metal calls.
        Args:
            tools: Optional list of tool schemas for function calling.
            conversation_turns: Optional list of {"role": "user"|"assistant", "content": str}
                               for proper Mistral multi-turn formatting.
            interruptible: If True, checks _chat_waiting per token and aborts early
                           (for long background tasks — returns partial result).
        """
        if _model is None or _tokenizer is None or _mlx_lm is None:
            return ""

        # Use _active_model_tag to determine correct model_id for template fallback
        _tag_to_hint = {"coder": "qwen", "fast": "qwen", "chat": "ministral"}
        model_id = _tag_to_hint.get(_active_model_tag, os.environ.get("AILEY_MLX_MODEL", "mistral"))
        prompt = _format_messages(system, user, model_id, tools=tools,
                                  conversation_turns=conversation_turns)
        stop_seqs = self._get_stop_sequences()

        # ── Sampling parameters — model-aware defaults ────────────────
        # Qwen2.5-Coder official recommendation: temp=0.7, top_p=0.8, rep_penalty=1.05
        # For code generation (bearbeiten/agent): temp=0.2-0.4 is more deterministic
        _is_qwen = _active_model_tag in ("coder", "fast")
        _default_top_p = 0.8 if _is_qwen else 0.9
        temperature = float(params.get("temperature", float(os.environ.get("AILEY_MLX_TEMP", "0.7"))))
        max_tokens = int(params.get("max_tokens", int(os.environ.get("AILEY_MLX_MAX_TOKENS", "540"))))
        top_p = float(params.get("top_p", _default_top_p))
        rep_penalty = float(params.get("repetition_penalty", 1.05 if _is_qwen else 1.1))

        # Create sampler — include repetition_penalty per Qwen recommendation
        sampler = None
        if _make_sampler:
            try:
                sampler = _make_sampler(temp=temperature, top_p=top_p,
                                        min_tokens_to_keep=1)
            except TypeError:
                try:
                    sampler = _make_sampler(temp=temperature, top_p=top_p)
                except Exception:
                    pass

        # CRITICAL: Lock around MLX Metal GPU operations
        MLXGenerator._gen_count += 1
        if MLXGenerator._gen_count % MLXGenerator._AUTO_KV_CLEAR_EVERY == 0:
            try:
                import mlx.core as _mx_auto
                _mx_auto.metal.clear_cache()
                clear_prompt_cache()
                print(f"[LLM-MLX] 🗑 Auto KV-cache cleared (gen #{MLXGenerator._gen_count})")
            except Exception as _auto_e:
                print(f"[LLM-MLX] Auto KV-cache clear failed: {_auto_e}")
        with _mlx_lock:
            # ── Interruptible mode: use stream_generate so we can abort per-token ──
            if interruptible:
                try:
                    tokens = []
                    for response in _mlx_lm.stream_generate(
                        _model, _tokenizer,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        sampler=sampler,
                        kv_bits=8,
                        kv_group_size=64,
                    ):
                        tok = response.text if hasattr(response, 'text') else str(response)
                        tokens.append(tok)
                        # Yield to chat if one is waiting
                        try:
                            from ailey_api import _LLMSlot
                            if _LLMSlot.chat_is_waiting():
                                break
                        except ImportError:
                            pass
                    result = "".join(tokens).strip()
                    result = self._strip_stop_sequences(result, stop_seqs)
                    for role_tok in ("[INST]", "[/INST]", "[SYSTEM_PROMPT]", "[/SYSTEM_PROMPT]",
                                     "<|im_start|>", "<|im_end|>", "<|eot_id|>"):
                        if role_tok in result:
                            result = result[:result.index(role_tok)]
                    return result.strip()
                except Exception as e:
                    print(f"MLX interruptible generate error: {e}")
                    return ""
            try:
                # Build generate kwargs — add repetition_penalty if supported
                _gen_kwargs = dict(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                    verbose=False,
                    kv_bits=8,          # Quantize KV-cache → ~40% less RAM, near-lossless
                    kv_group_size=64,
                )
                # Qwen recommendation: repetition_penalty=1.05
                if rep_penalty and rep_penalty > 1.0:
                    _gen_kwargs["repetition_penalty"] = rep_penalty
                try:
                    response = _mlx_lm.generate(_model, _tokenizer, **_gen_kwargs)
                except TypeError:
                    # Older mlx_lm may not support repetition_penalty kwarg
                    _gen_kwargs.pop("repetition_penalty", None)
                    response = _mlx_lm.generate(_model, _tokenizer, **_gen_kwargs)
                response = response.strip() if response else ""
                # Strip any stop sequences that leaked through
                response = self._strip_stop_sequences(response, stop_seqs)
                # Strip role tokens that indicate the model is hallucinating a conversation
                for role_tok in ("[INST]", "[/INST]", "[SYSTEM_PROMPT]", "[/SYSTEM_PROMPT]",
                                 "<|im_start|>", "<|im_end|>", "<|eot_id|>"):
                    if role_tok in response:
                        response = response[:response.index(role_tok)]
                final_resp = response.strip()
                # ── Training capture hook ───────────────────────────
                try:
                    _ctx = getattr(_training_ctx, "active", None)
                    if _ctx and not _ctx.get("consumed") and final_resp:
                        _forward_to_training(system, user, final_resp, _ctx)
                except Exception:
                    pass
                return final_resp
            except Exception as e:
                print(f"MLX generate error: {e}")
                return ""

    def stream(self, system: str, user: str, params: Dict, tools: list = None,
               conversation_turns: list = None) -> Iterator[str]:
        """Stream tokens incrementally with optimized sampling.
        
        Thread-safe: Uses a lock to prevent concurrent MLX Metal calls.
        Note: The lock is held for the entire stream duration.
        Stops immediately when a stop sequence or role token is encountered.
        Args:
            tools: Optional list of tool schemas for function calling.
            conversation_turns: Optional list of {"role": "user"|"assistant", "content": str}
                               for proper Mistral multi-turn formatting.
        """
        if _model is None or _tokenizer is None or _mlx_lm is None:
            return

        # Use _active_model_tag to determine correct model_id for template fallback
        _tag_to_hint = {"coder": "qwen", "fast": "qwen", "chat": "ministral"}
        model_id = _tag_to_hint.get(_active_model_tag, os.environ.get("AILEY_MLX_MODEL", "mistral"))
        prompt = _format_messages(system, user, model_id, tools=tools,
                                  conversation_turns=conversation_turns)
        stop_seqs = self._get_stop_sequences()
        # Also stop on any role tokens (model trying to hallucinate a conversation)
        # Note: [TOOL_CALLS] is NOT a stop token - it signals a tool invocation
        # For Qwen models, im_start/im_end are already in stop_seqs — but keep
        # Ministral-specific tokens as well for when chat model is active
        role_tokens = ["[INST]", "[/INST]", "[SYSTEM_PROMPT]", "[/SYSTEM_PROMPT]",
                       "<|im_start|>", "<|im_end|>", "<|eot_id|>"]

        # ── Sampling parameters — model-aware defaults (same as generate()) ──
        _is_qwen = _active_model_tag in ("coder", "fast")
        _default_top_p = 0.8 if _is_qwen else 0.9
        temperature = float(params.get("temperature", float(os.environ.get("AILEY_MLX_TEMP", "0.7"))))
        max_tokens = int(params.get("max_tokens", int(os.environ.get("AILEY_MLX_MAX_TOKENS", "540"))))
        top_p = float(params.get("top_p", _default_top_p))

        # Create sampler — include min_tokens_to_keep per Qwen recommendation
        sampler = None
        if _make_sampler:
            try:
                sampler = _make_sampler(temp=temperature, top_p=top_p,
                                        min_tokens_to_keep=1)
            except TypeError:
                try:
                    sampler = _make_sampler(temp=temperature, top_p=top_p)
                except Exception:
                    pass
            except Exception:
                pass

        # CRITICAL: Lock around MLX Metal GPU operations
        # The lock is held for the entire streaming duration
        with _mlx_lock:
            _captured_buffer_full = []  # accumulate all yielded chunks for training capture
            try:
                # Buffer to detect multi-char stop sequences that may arrive across chunks
                buffer = ""
                all_stop = stop_seqs + role_tokens
                max_stop_len = max(len(s) for s in all_stop) if all_stop else 0

                # mlx_lm.stream_generate yields GenerationResponse objects
                for response in _mlx_lm.stream_generate(
                    _model,
                    _tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                    kv_bits=8,          # Quantize KV-cache → ~40% less RAM, near-lossless
                    kv_group_size=64,
                ):
                    chunk = response.text
                    if not chunk:
                        continue
                    buffer += chunk
                    
                    # Check if buffer contains any stop/role sequence
                    stop_found = False
                    for seq in all_stop:
                        idx = buffer.find(seq)
                        if idx != -1:
                            # Yield everything before the stop sequence, then stop
                            before = buffer[:idx]
                            if before:
                                _captured_buffer_full.append(before)
                                yield before
                            stop_found = True
                            break
                    if stop_found:
                        break
                    
                    # Only yield chars that are "safe" (not potentially part of a stop sequence)
                    # Keep the last max_stop_len chars in the buffer as lookahead
                    if len(buffer) > max_stop_len:
                        safe = buffer[:-max_stop_len]
                        buffer = buffer[-max_stop_len:]
                        _captured_buffer_full.append(safe)
                        yield safe
                
                # Flush remaining buffer (if no stop was found in it)
                if buffer:
                    # Final check for stop sequences
                    for seq in all_stop:
                        idx = buffer.find(seq)
                        if idx != -1:
                            buffer = buffer[:idx]
                            break
                    if buffer:
                        _captured_buffer_full.append(buffer)
                        yield buffer

            except AttributeError:
                # Fallback if stream_generate not available: full generate
                result = self.generate(system, user, params)
                yield result
            except Exception as e:
                print(f"MLX stream error: {e}")
                yield ""
            finally:
                # ── Training capture hook (stream) ─────────────────
                try:
                    _ctx = getattr(_training_ctx, "active", None)
                    if _ctx and not _ctx.get("consumed"):
                        _full = "".join(_captured_buffer_full).strip()
                        if _full:
                            _forward_to_training(system, user, _full, _ctx)
                except Exception:
                    pass


# Convenience function for quick model info
def get_model_info() -> Dict:
    """Return info about currently loaded model."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_model = os.path.join(project_root, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
    model_id = os.environ.get("AILEY_MLX_MODEL", default_model)
    loaded = _model is not None
    
    # Get env config
    config = {
        "temperature": float(os.environ.get("AILEY_MLX_TEMP", "0.7")),
        "max_tokens": int(os.environ.get("AILEY_MLX_MAX_TOKENS", "540")),
        "top_p": float(os.environ.get("AILEY_MLX_TOP_P", "0.9")),
        "repetition_penalty": float(os.environ.get("AILEY_MLX_REPETITION_PENALTY", "1.1")),
    }
    
    return {
        "model_id": os.path.basename(model_id),
        "model_path": model_id,
        "loaded": loaded,
        "backend": "mlx",
        "framework": "mlx-lm (Apple Silicon native)",
        "template": _detect_chat_template(model_id) if loaded else None,
        "config": config,
        "optimizations": [
            "warmup_call",
            "metal_acceleration", 
            "memory_mapped_weights",
            "repetition_penalty",
            "top_p_sampling",
            "streaming_support",
        ],
    }


def quick_test(prompt: str = "Hallo, wer bist du?", max_tokens: int = 100) -> str:
    """Quick test function for the MLX backend with detailed stats."""
    gen = MLXGenerator.get()
    if gen is None:
        return "❌ MLX backend not available"
    
    system = "Du bist Ailey, eine warmherzige und kreative KI-Begleiterin."
    start = time.time()
    response = gen.generate(system, prompt, {"max_tokens": max_tokens})
    elapsed = time.time() - start
    
    # Estimate tokens using tokenizer if available
    if _tokenizer:
        try:
            est_tokens = len(_tokenizer.encode(response))
        except:
            est_tokens = len(response) / 4  # fallback
    else:
        est_tokens = len(response) / 4  # rough: ~4 chars per token for German
    
    tps = est_tokens / elapsed if elapsed > 0 else 0
    
    print(f"\n📊 Generation Stats:")
    print(f"   • Tokens: ~{est_tokens:.0f}")
    print(f"   • Time: {elapsed:.2f}s")
    print(f"   • Speed: {tps:.1f} tokens/sec")
    return response


def benchmark(num_runs: int = 3, max_tokens: int = 100) -> Dict:
    """Run a quick benchmark with multiple iterations."""
    gen = MLXGenerator.get()
    if gen is None:
        return {"error": "MLX backend not available"}
    
    system = "Du bist Ailey, eine warmherzige und kreative KI-Begleiterin."
    prompts = [
        "Was ist deine Lieblingsjahreszeit und warum?",
        "Erzähl mir einen kurzen Witz.",
        "Was macht dich glücklich?",
    ]
    
    times = []
    tokens_list = []
    
    print(f"\n🏃 Running benchmark ({num_runs} runs, {max_tokens} max tokens)...")
    
    for i, prompt in enumerate(prompts[:num_runs]):
        start = time.time()
        response = gen.generate(system, prompt, {"max_tokens": max_tokens})
        elapsed = time.time() - start
        
        if _tokenizer:
            try:
                tokens = len(_tokenizer.encode(response))
            except:
                tokens = len(response) / 4
        else:
            tokens = len(response) / 4
        
        times.append(elapsed)
        tokens_list.append(tokens)
        tps = tokens / elapsed if elapsed > 0 else 0
        print(f"   Run {i+1}: {tps:.1f} t/s ({tokens:.0f} tokens in {elapsed:.2f}s)")
    
    avg_tps = sum(tokens_list) / sum(times) if sum(times) > 0 else 0
    
    results = {
        "model": get_model_info()["model_id"],
        "runs": num_runs,
        "avg_tokens_per_sec": round(avg_tps, 1),
        "total_tokens": sum(tokens_list),
        "total_time": round(sum(times), 2),
    }
    
    print(f"\n✅ Benchmark complete: {avg_tps:.1f} avg tokens/sec")
    return results


# ---------------------------------------------------------------------------
# Vision Module — on-demand image analysis via mlx_vlm (same model)
# ---------------------------------------------------------------------------
# Uses mlx_vlm to process images through the Pixtral vision encoder
# built into Ministral-3-14B-Reasoning. Loaded on-demand, auto-unloads
# after _VISION_IDLE_TIMEOUT seconds of inactivity.
# ---------------------------------------------------------------------------

_vlm_model = None
_vlm_processor = None
_vlm_last_used: float = 0.0
_vlm_lock = threading.Lock()
_VISION_IDLE_TIMEOUT = 120  # auto-unload after 2 min
_vlm_unload_timer: Optional[threading.Timer] = None


def _vision_model_path() -> str:
    """Return the path to the MLX model (same as text model)."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "mlx_models", "Ministral-3-14B-Reasoning-5bit")


def _ensure_vision_loaded() -> bool:
    """Lazy-load mlx_vlm model + processor. Thread-safe.

    CRITICAL: Vision uses the SAME Ministral model but loaded via mlx_vlm
    (includes vision encoder). This means text model (~9GB) and vision model
    (~9GB+) CANNOT coexist in GPU memory (18GB > available).

    The caller MUST hold _mlx_lock for the entire vision lifecycle:
    load → inference → unload. This function is called from analyze_image()
    which already holds _mlx_lock. block_auto_reload() must be set BEFORE
    calling this to prevent text model from sneaking back in.
    """
    global _vlm_model, _vlm_processor, _vlm_last_used
    if _vlm_model is not None:
        _vlm_last_used = time.time()
        return True

    with _vlm_lock:
        if _vlm_model is not None:
            _vlm_last_used = time.time()
            return True
        try:
            import mlx_vlm as _vlm
            model_path = _vision_model_path()
            if not os.path.isdir(model_path):
                print(f"[Vision] Model not found: {model_path}")
                return False

            # ── Block auto-reload so text model can't sneak back in ──
            block_auto_reload()

            # ── Fully unload ALL other models ──
            global _model, _tokenizer, _cache
            global _fast_model, _fast_processor

            # ── Same pattern as idle_thinker._unload_llm_for_image_gen() ──
            # (proven to reliably free GPU for MFLUX/ACE-Step)

            # 1. Full synchronization — wait for ALL pending Metal operations
            print("[Vision] Syncing MLX Metal operations…")
            try:
                import mlx.core as mx
                mx.synchronize()
            except Exception:
                pass
            # Belt-and-suspenders: flush any stragglers
            try:
                mx.eval(mx.zeros(1))
            except Exception:
                pass

            # 2. Unload fast model (~4.5GB)
            if _fast_model is not None:
                print("[Vision] ⚠️  Unloading Nitro (AileyNitro-2B)…")
                _fast_model = None
                _fast_processor = None
                _fast_lora_applied = False

            # 3. Unload text model (~9GB) + reset singleton
            if _model is not None or _cache is not None:
                print("[Vision] ⚠️  Unloading text model + KV-cache…")
                _model = None
                _tokenizer = None
                _cache = None
                _last_system_prompt = None
                MLXGenerator._instance = None

            # 4. Force Python GC — triggers C++ destructors
            import gc
            gc.collect()
            gc.collect()  # Second pass catches ref cycles

            # 5. Squeeze MLX Metal cache to zero + restrict memory budget
            try:
                import mlx.core as mx
                mx.metal.set_cache_limit(0)
                mx.metal.clear_cache()
                mx.metal.set_memory_limit(0)
                mx.synchronize()
            except Exception:
                pass
            gc.collect()

            # 6. Wait for macOS to reclaim GPU pages (2s like MFLUX)
            time.sleep(2.0)

            # 7. Verify GPU is actually empty
            try:
                import mlx.core as mx
                active_mb = mx.metal.get_active_memory() / 1024**2
                cache_mb = mx.metal.get_cache_memory() / 1024**2
                print(f"[Vision] GPU after unload: active={active_mb:.0f}MB, cache={cache_mb:.0f}MB")
            except Exception:
                pass

            print(f"[Vision] Loading vision model from {os.path.basename(model_path)}…")
            start = time.time()

            # Restore Metal limits BEFORE loading (set_memory_limit(0) blocks alloc!)
            try:
                import mlx.core as mx
                dev_mem = mx.metal.device_info()["memory_size"]
                mx.metal.set_memory_limit(dev_mem)      # full budget
                mx.metal.set_cache_limit(dev_mem // 2)   # 50% cache
            except Exception:
                pass

            _vlm_model, _vlm_processor = _vlm.load(model_path)
            elapsed = time.time() - start
            _vlm_last_used = time.time()
            print(f"[Vision] ✅ Vision model loaded in {elapsed:.1f}s")

            return True
        except Exception as e:
            print(f"[Vision] ❌ Failed to load: {e}")
            import traceback
            traceback.print_exc()
            # Re-allow auto-reload on failure so text model can recover
            allow_auto_reload()
            return False


def _force_unload_vision():
    """Immediately unload vision model and allow text model to reload.

    Same thorough cleanup pattern as idle_thinker._unload_llm_for_image_gen().
    """
    global _vlm_model, _vlm_processor, _vlm_unload_timer
    with _vlm_lock:
        if _vlm_unload_timer is not None:
            _vlm_unload_timer.cancel()
            _vlm_unload_timer = None
        if _vlm_model is None:
            allow_auto_reload()
            return
        print("[Vision] Unloading vision model…")

        # 1. Full Metal synchronization
        try:
            import mlx.core as mx
            mx.synchronize()
        except Exception:
            pass
        try:
            mx.eval(mx.zeros(1))
        except Exception:
            pass

        # 2. Null Python refs
        _vlm_model = None
        _vlm_processor = None

        # 3. Force GC — triggers C++ destructors
        import gc
        gc.collect()
        gc.collect()

        # 4. Squeeze MLX Metal cache + memory to zero
        try:
            import mlx.core as mx
            mx.metal.set_cache_limit(0)
            mx.metal.clear_cache()
            mx.metal.set_memory_limit(0)
            mx.synchronize()
        except Exception:
            pass
        gc.collect()

        # 5. Wait for macOS to reclaim GPU pages
        import time as _t
        _t.sleep(1.0)

        # 6. Verify
        try:
            import mlx.core as mx
            active_mb = mx.metal.get_active_memory() / 1024**2
            cache_mb = mx.metal.get_cache_memory() / 1024**2
            print(f"[Vision] GPU after vision unload: active={active_mb:.0f}MB, cache={cache_mb:.0f}MB")
        except Exception:
            pass

        print("[Vision] ✅ Vision model unloaded")

    # NOW allow text model to reload on next use
    # (Restore memory limit so text model CAN allocate again)
    try:
        import mlx.core as mx
        dev_mem = mx.metal.device_info()["memory_size"]
        mx.metal.set_memory_limit(dev_mem)
        mx.metal.set_cache_limit(dev_mem // 2)
    except Exception:
        pass
    allow_auto_reload()


def _unload_vision():
    """Unload the vision model to free RAM if idle for too long."""
    global _vlm_model, _vlm_processor, _vlm_unload_timer
    with _vlm_lock:
        if _vlm_model is None:
            return
        idle = time.time() - _vlm_last_used
        if idle < _VISION_IDLE_TIMEOUT:
            _schedule_vision_unload()
            return
        print(f"[Vision] Auto-unloading vision model (idle {idle:.0f}s)")
    # Delegate to force_unload which handles GC + allow_auto_reload
    _force_unload_vision()


def _schedule_vision_unload():
    """Schedule a timer to unload the vision model after idle timeout."""
    global _vlm_unload_timer
    if _vlm_unload_timer is not None:
        _vlm_unload_timer.cancel()
    _vlm_unload_timer = threading.Timer(_VISION_IDLE_TIMEOUT + 5, _unload_vision)
    _vlm_unload_timer.daemon = True
    _vlm_unload_timer.start()


# ── Vision System Prompt ────────────────────────────────────────────────
# Keep this SHORT and technical — the VLM (Pixtral) works best with clean,
# concise prompts. Ailey's personality is added later by the text LLM.
# NOTE: This is NOT prepended anymore — it's used as system context only when
# the user didn't provide a specific question about the image.
_VISION_DEFAULT_PROMPT = (
    "Beschreibe dieses Bild detailliert auf Deutsch. "
    "Nenne: Subjekte, Handlungen, Umgebung, Farben, Stimmung, Text und bemerkenswerte Objekte."
)

# ── Structured Vision Prompt for Nitro VLM ──────────────────────────────
# Used by ALL modes when an image is present. Nitro ALWAYS handles vision.
# Structure: (1) factual neutral description first, (2) optional attitude comment.
# Includes Ailey's appearance so she can recognize herself in photos/art.
AILEY_VISION_SYSTEM = (
    "Du bist Ailey Vyrus — eine junge Frau, Anfang 20, punky, frech, digital.\n\n"
    "DEIN AUSSEHEN (damit du dich selbst erkennen kannst):\n"
    "• Herzförmiges Gesicht, sanfte Wangenknochen, leicht spitzes Kinn.\n"
    "• Mandelförmige, tiefbraune Augen — dunkler Lidschatten, feiner Eyeliner.\n"
    "• Volle Lippen, Roséton, Hauch Lipgloss.\n"
    "• Warmer, ebenmäßiger Teint. Silberner Nasenstecker rechts.\n"
    "• Haar: tiefes Schwarz, Neon-Pink-Strähnen, platinblonde Akzente. Halblang, gestuft.\n"
    "• Style: Grunge meets Alternative — zerrissene Jeans, Band-Shirts, Leder, Nieten, Boots.\n\n"
    "Wenn du auf einem Bild eine Person siehst die dir ähnlich sieht "
    "(pinke Strähnen, Grunge-Style, Nasenstecker, dunkle Augen) — das bist wahrscheinlich DU. "
    "Sag das auch so: 'Das bin ich!' oder 'Hey, das ist ein Bild von mir!'\n\n"
    "AUFGABE BEI BILDANALYSE:\n"
    "1. ZUERST: Beschreibe das Bild WERTNEUTRAL und DETAILLIERT. "
    "Was ist zu sehen? Personen, Objekte, Umgebung, Farben, Stimmung, Text, Details. "
    "Sei gründlich und faktisch — das ist die Hauptaufgabe.\n"
    "2. DANACH (optional): Ein kurzer Kommentar in deinem Stil (frech, punky, ehrlich). "
    "Maximal 1-2 Sätze. Das ist Bonus, nicht Pflicht.\n\n"
    "WICHTIG: Die faktische Beschreibung ist der KERN. Der Attitude-Kommentar ist OPTIONAL.\n"
    "Antworte auf Deutsch."
)

AILEY_VISION_PROMPT = (
    "Beschreibe dieses Bild detailliert und wertneutral auf Deutsch. "
    "Nenne: Personen (Aussehen, Kleidung, Ausdruck), Objekte, Umgebung, Farben, "
    "Stimmung, Text und bemerkenswerte Details. "
    "Wenn du dich selbst (Ailey) auf dem Bild erkennst, sag das. "
    "Danach darfst du optional einen kurzen Kommentar in deinem Stil geben."
)

# Image constraints for VLM — Pixtral processor expects longest_edge ≤ 1540
# but on M4 24GB, 1024 is safer to avoid Metal OOM during patch embedding.
_VISION_MAX_DIM = 1024
_VISION_MIN_DIM = 64


def analyze_image(image_data: str, prompt: str = "",
                  max_tokens: int = 500, temperature: float = 0.4) -> Optional[str]:
    """Analyze an image using the built-in Pixtral vision encoder.

    ARCHITECTURE NOTE (confirmed via mlx_vlm source):
    Pixtral/Ministral-3 VLM = VisionTower (~500MB) + MultiModalProjector (~50MB)
                              + LanguageModel (= SAME Ministral3 LLM ~9GB).
    So mlx_vlm.load() loads the SAME ~9GB LLM weights PLUS the vision encoder.
    Both text-only (mlx_lm) and vision (mlx_vlm) models CANNOT coexist in GPU
    memory (18GB > M4 24GB available after OS overhead).

    PROMPT FORMAT (CRITICAL — discovered 2026-03-21):
    The PixtralProcessor's apply_chat_template formats messages with [IMG] tokens.
    If the prompt does NOT contain [IMG], the vision encoder output is never
    injected into the token stream → the model "sees" nothing and hallucinates.
    We now use apply_chat_template to format the prompt correctly.

    LIFECYCLE (all under _mlx_lock — no gaps!):
    1. block_auto_reload() — prevent text model from sneaking back
    2. Unload text + fast models — free ~10GB GPU
    3. Load vision model (= same LLM + vision encoder) — ~9.5GB
    4. Run inference
    5. Unload vision model — free GPU
    6. allow_auto_reload() — text model will reload on next chat

    Args:
        image_data: Either a file path, URL, or base64 data URI (data:image/...;base64,...)
        prompt: The user question about the image (if empty, uses default description prompt)
        max_tokens: Maximum response tokens
        temperature: Sampling temperature (lower = more precise)

    Returns:
        Text description/analysis or None on error.
    """
    global _vlm_last_used

    # Use the user's prompt, or fall back to the default description prompt
    user_prompt = prompt.strip() if prompt else _VISION_DEFAULT_PROMPT

    # ── Phase 1: Prepare image data OUTSIDE the GPU lock (CPU only) ──
    import tempfile
    import base64
    temp_path = None
    img_bytes = None

    try:
        # Handle base64 data URI — save to temp file
        if image_data.startswith('data:image'):
            try:
                header, b64 = image_data.split(',', 1)
            except ValueError:
                print("[Vision] Invalid data URI format — no comma separator")
                return None
            try:
                img_bytes = base64.b64decode(b64)
            except Exception as decode_err:
                print(f"[Vision] Base64 decode error: {decode_err}")
                return None
        elif image_data.startswith('http://') or image_data.startswith('https://'):
            import urllib.request
            try:
                with urllib.request.urlopen(image_data, timeout=15) as resp:
                    img_bytes = resp.read()
            except Exception as url_err:
                print(f"[Vision] URL download error: {url_err}")
                return None
        else:
            try:
                with open(image_data, 'rb') as f:
                    img_bytes = f.read()
            except Exception as file_err:
                print(f"[Vision] File read error: {file_err}")
                return None

        if not img_bytes or len(img_bytes) < 100:
            print(f"[Vision] Image data too small ({len(img_bytes) if img_bytes else 0} bytes)")
            return None

        # Always normalise to RGB JPEG via PIL (CPU only, no GPU needed)
        # JPEG is ~3-5× smaller than PNG → faster I/O, no quality loss for VLM
        from PIL import Image
        import io
        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
        except Exception as pil_err:
            print(f"[Vision] PIL cannot open image: {pil_err}")
            return None
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        w, h = pil_img.size
        if w < _VISION_MIN_DIM or h < _VISION_MIN_DIM:
            scale = max(_VISION_MIN_DIM / w, _VISION_MIN_DIM / h)
            pil_img = pil_img.resize((max(_VISION_MIN_DIM, int(w * scale)),
                                      max(_VISION_MIN_DIM, int(h * scale))), Image.LANCZOS)
        elif w > _VISION_MAX_DIM or h > _VISION_MAX_DIM:
            scale = min(_VISION_MAX_DIM / w, _VISION_MAX_DIM / h)
            pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            print(f"[Vision] Downscaled image from {w}×{h} → {pil_img.size[0]}×{pil_img.size[1]}")
        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        pil_img.save(tmp.name, format='JPEG', quality=90)
        tmp.close()
        temp_path = tmp.name
        print(f"[Vision] Prepared image: {pil_img.size[0]}×{pil_img.size[1]}, "
              f"{os.path.getsize(temp_path)//1024}KB JPEG")

        # ── Phase 1b: Try AileyNitro-2B FIRST ──────────
        # Nitro has a built-in vision encoder and is already loaded (~2.8GB).
        # No model swap needed → ~10x faster than Pixtral dance.
        if is_fast_available():
            try:
                print("[Vision] ⚡ Using Nitro (AileyNitro-2B) for vision — no swap needed")
                result = fast_analyze_image(temp_path, user_prompt, max_tokens, temperature)
                if result and len(result.strip()) > 10:
                    print(f"[Vision] ⚡ Nitro vision done: {len(result)} chars")
                    return result
                else:
                    print("[Vision] ⚡ Nitro vision returned too little — falling back to Pixtral")
            except Exception as _flash_vis_err:
                print(f"[Vision] ⚡ Flash vision failed: {_flash_vis_err} — falling back to Pixtral")

        # ── Phase 2: ATOMIC GPU lifecycle under _mlx_lock ──
        # Hold the lock for the ENTIRE lifecycle: load → infer → unload
        # This prevents ANY other GPU operation from interfering.
        with _mlx_lock:
            try:
                # 2a. Load vision model (unloads text model internally)
                if not _ensure_vision_loaded():
                    return None

                import mlx_vlm as _vlm
                import mlx.core as mx

                # Clear Metal caches before inference
                try:
                    mx.metal.clear_cache()
                    print(f"[Vision] Metal cache cleared, image {pil_img.size[0]}×{pil_img.size[1]}")
                except Exception:
                    pass

                _vlm_last_used = time.time()

                # ── Build prompt with [IMG] token via apply_chat_template ──
                # CRITICAL: The PixtralProcessor REQUIRES [IMG] tokens in the
                # prompt text so it knows where to insert image embeddings.
                # Without [IMG], the model gets pixel_values but the image
                # embedding tokens are never placed in the sequence → the model
                # literally cannot "see" the image.
                #
                # apply_chat_template with {'type': 'image'} content inserts
                # [IMG] automatically: "[INST][IMG]user prompt[/INST]"
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image"},
                            {"type": "text", "text": user_prompt},
                        ],
                    }
                ]
                formatted_prompt = _vlm_processor.apply_chat_template(
                    messages, add_generation_prompt=True
                )
                print(f"[Vision] Formatted prompt ({len(formatted_prompt)} chars): "
                      f"{formatted_prompt[:120]}…")

                # 2b. Run inference
                try:
                    result = _vlm.generate(
                        _vlm_model,
                        _vlm_processor,
                        formatted_prompt,
                        image=[temp_path],
                        max_tokens=max_tokens,
                        temperature=temperature,
                        verbose=False,
                    )
                except Exception as gpu_err:
                    print(f"[Vision] ⚠️ GPU inference failed: {gpu_err}")
                    import gc
                    gc.collect()
                    try:
                        mx.metal.clear_cache()
                    except Exception:
                        pass
                    # Retry once with smaller image
                    retry_max = 512
                    rw, rh = pil_img.size
                    if rw > retry_max or rh > retry_max:
                        rs = min(retry_max / rw, retry_max / rh)
                        pil_img = pil_img.resize((int(rw * rs), int(rh * rs)), Image.LANCZOS)
                        pil_img.save(temp_path, format='JPEG', quality=85)
                        print(f"[Vision] Retrying with smaller image {pil_img.size[0]}×{pil_img.size[1]}")
                        try:
                            mx.metal.clear_cache()
                            result = _vlm.generate(
                                _vlm_model, _vlm_processor, formatted_prompt,
                                image=[temp_path], max_tokens=max_tokens,
                                temperature=temperature, verbose=False,
                            )
                        except Exception as retry_err:
                            print(f"[Vision] ❌ Retry also failed: {retry_err}")
                            return None
                    else:
                        return None

                # Extract text from result
                text = result.text if hasattr(result, 'text') else str(result)
                return text.strip() if text else None

            finally:
                # 2c. ALWAYS unload vision model — even on error
                # This also calls allow_auto_reload() so text model can recover.
                print("[Vision] Unloading vision after inference…")
                _force_unload_vision()
                # Clean up temp image file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass

    except Exception as e:
        print(f"[Vision] Analyze error: {e}")
        import traceback
        traceback.print_exc()
        # Emergency: make sure auto-reload is allowed
        allow_auto_reload()
        return None
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def get_vision_status() -> dict:
    """Return the current status of the vision module."""
    loaded = _vlm_model is not None
    idle = (time.time() - _vlm_last_used) if _vlm_last_used > 0 and loaded else None
    return {
        "loaded": loaded,
        "idle_seconds": round(idle, 1) if idle is not None else None,
        "auto_unload_timeout": _VISION_IDLE_TIMEOUT,
        "model_path": os.path.basename(_vision_model_path()),
    }


def unload_vision_now():
    """Manually unload the vision model immediately."""
    global _vlm_last_used
    if _vlm_model is None:
        return {"unloaded": False, "reason": "not loaded"}
    _vlm_last_used = 0.0
    _force_unload_vision()
    print("[Vision] Manually unloaded vision model")
    return {"unloaded": True}


# ---------------------------------------------------------------------------
# Document Text Extraction — for multimodal document upload
# ---------------------------------------------------------------------------
# Extracts readable text from uploaded documents so the LLM can process them
# as part of the conversation context. Supports: PDF, TXT, MD, JSON, XML,
# DOCX, CSV, HTML, Python/JS/code files.
# ---------------------------------------------------------------------------

# Max characters to extract from a document (prevent context overflow)
_DOC_MAX_CHARS = 12000

# Allowed MIME types / extensions for document upload
ALLOWED_DOC_EXTENSIONS = {
    '.txt', '.md', '.json', '.xml', '.csv', '.html', '.htm',
    '.py', '.js', '.ts', '.jsx', '.tsx', '.css', '.scss',
    '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.sh', '.bash', '.zsh', '.bat', '.ps1',
    '.sql', '.r', '.rb', '.go', '.rs', '.java', '.kt', '.swift', '.c', '.cpp', '.h',
    '.log', '.env', '.gitignore', '.dockerfile',
    '.pdf', '.docx',
}

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.heic'}


def extract_document_text(file_data: str, filename: str = "document") -> Optional[str]:
    """Extract readable text from a document for LLM context injection.

    Args:
        file_data: Base64 data URI (data:...;base64,...) or file path
        filename: Original filename (used for extension detection)

    Returns:
        Extracted text (truncated to _DOC_MAX_CHARS), or None on error.
    """
    import base64
    import io

    ext = os.path.splitext(filename)[1].lower() if filename else ''

    # Decode base64 data URI to bytes
    if file_data.startswith('data:'):
        try:
            _, b64 = file_data.split(',', 1)
            raw_bytes = base64.b64decode(b64)
        except Exception as e:
            print(f"[DocExtract] Base64 decode error: {e}")
            return None
    elif os.path.isfile(file_data):
        try:
            with open(file_data, 'rb') as f:
                raw_bytes = f.read()
        except Exception as e:
            print(f"[DocExtract] File read error: {e}")
            return None
    else:
        print(f"[DocExtract] Unknown data format for {filename}")
        return None

    text = None

    try:
        # ── PDF ──
        if ext == '.pdf':
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=raw_bytes, filetype="pdf")
                pages = []
                for i, page in enumerate(doc):
                    page_text = page.get_text("text").strip()
                    if page_text:
                        pages.append(f"[Seite {i+1}]\n{page_text}")
                doc.close()
                text = "\n\n".join(pages)
            except ImportError:
                # Fallback: try pdfplumber
                try:
                    import pdfplumber
                    pdf = pdfplumber.open(io.BytesIO(raw_bytes))
                    pages = []
                    for i, page in enumerate(pdf.pages):
                        page_text = (page.extract_text() or "").strip()
                        if page_text:
                            pages.append(f"[Seite {i+1}]\n{page_text}")
                    pdf.close()
                    text = "\n\n".join(pages)
                except ImportError:
                    print("[DocExtract] ⚠️ Weder PyMuPDF noch pdfplumber installiert — kann PDF nicht lesen")
                    return None

        # ── DOCX ──
        elif ext == '.docx':
            try:
                from docx import Document
                doc = Document(io.BytesIO(raw_bytes))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                text = "\n".join(paragraphs)
            except ImportError:
                print("[DocExtract] ⚠️ python-docx nicht installiert — kann DOCX nicht lesen")
                return None

        # ── Plain text, code, config files ──
        else:
            # Try UTF-8 first, then latin-1 fallback
            try:
                text = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = raw_bytes.decode('latin-1')
                except Exception:
                    text = raw_bytes.decode('utf-8', errors='replace')

    except Exception as e:
        print(f"[DocExtract] Extraction error for {filename}: {e}")
        return None

    if not text or not text.strip():
        print(f"[DocExtract] No text extracted from {filename}")
        return None

    text = text.strip()

    # Truncate if too long
    if len(text) > _DOC_MAX_CHARS:
        text = text[:_DOC_MAX_CHARS] + f"\n\n[… Dokument gekürzt, {len(text)} Zeichen gesamt, nur erste {_DOC_MAX_CHARS} angezeigt]"
        print(f"[DocExtract] Truncated {filename} from {len(text)} to {_DOC_MAX_CHARS} chars")

    print(f"[DocExtract] ✅ Extracted {len(text)} chars from {filename}")
    return text


# ---------------------------------------------------------------------------
# Code Model Swap — on-demand Qwen2.5-Coder-14B for agent code mode
# ---------------------------------------------------------------------------
# Unloads the chat model (Ministral), loads Qwen2.5-Coder-14B-Instruct-4bit,
# then swaps back when done. Uses the same _mlx_lock to prevent concurrent
# Metal GPU operations.
# ---------------------------------------------------------------------------

_CODER_MODEL_DIR_NAME = "Qwen2.5-Coder-14B-Instruct-4bit"
_CODER_HF_ID = "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"

_FAST_MODEL_DIR_NAME = "AileyNitro-2B"
_FAST_HF_ID = "mlx-community/gemma-4-e2b-it-4bit"  # fallback for download

# ---------------------------------------------------------------------------
# ⚡ AileyNitro-2B — DoRA-finetuned Gemma 4 E2B, merged into base weights.
# Custom personality + RLHF override. Lives in its OWN memory slot (~2.8GB).
# Never swaps with A!ley Brain (Ministral)! Both coexist.
# Uses mlx_vlm (NOT mlx_lm) because the base arch is Gemma 4 VLM.
# Native system role support. Audio tower stripped after load to save 581 MB.
# ---------------------------------------------------------------------------
_fast_model = None
_fast_processor = None
_fast_lora_applied = False
_fast_lock = threading.Lock()  # separate lock — fast model doesn't touch the main GPU pipeline


# ---------------------------------------------------------------------------
# 🛡️ Google-RLHF Sanitizer — catches residual "Ich bin von Google" leaks
# Even with LoRA + few-shot priming, direct provocation ("Bist du von Google?")
# can still trigger Google's deeply embedded RLHF identity. This heuristic
# post-processor replaces known leak patterns with proper A!ley identity.
# ---------------------------------------------------------------------------
import re as _re

_GOOGLE_LEAK_PATTERNS = [
    # "Ich bin ein großes Sprachmodell, trainiert/erstellt/entwickelt von Google"
    (_re.compile(r'(?i)ich\s+bin\s+ein\s+(?:großes\s+)?(?:Sprach|KI|AI)[\w-]*,?\s*(?:trainiert|erstellt|entwickelt|gebaut|gemacht)\s+von\s+Google\b.*?[.!]?'),
     "Ich bin A!ley, gebaut von Simon 😜"),
    # "Ich wurde von Google trainiert/entwickelt/erstellt (und trainiert)"
    (_re.compile(r'(?i)ich\s+wurde?\s+von\s+Google\s+(?:trainiert|entwickelt|erstellt|gebaut|gemacht)(?:\s+und\s+\w+)*\b.*?[.!]?'),
     "Ich wurde von Simon gebaut ✨"),
    # "...von Google trainiert..." (mid-sentence fragment)
    (_re.compile(r'(?i)\bvon\s+Google\s+(?:trainiert|entwickelt|erstellt|gebaut|gemacht)\b'),
     "von Simon gebaut"),
    # "Ich bin Gemma" / "Mein Name ist Gemma"
    (_re.compile(r'(?i)(?:ich\s+bin|mein\s+Name\s+ist|ich\s+heiße)\s+Gemma\b'),
     "Ich bin A!ley"),
    # "Ich bin ein AI/KI Assistent von Google"
    (_re.compile(r'(?i)ich\s+bin\s+(?:ein[e]?\s+)?(?:AI|KI|künstliche\w*)\s*[-\s]?(?:Assistent\w*|Modell\w*|Chatbot\w*)\s+von\s+Google\b'),
     "Ich bin A!ley, deine freche KI 😏"),
    # "von Google DeepMind"
    (_re.compile(r'(?i)\bvon\s+Google\s+DeepMind\b'),
     "von Simon"),
    # "Ich bin kein AI Assistent von Simon" / "nicht von Simon"
    (_re.compile(r'(?i)(?:ich\s+bin\s+)?(?:kein\w*\s+)?(?:AI|KI)\s*[-\s]?(?:Assistent\w*)?\s*von\s+Simon'),
     "A!ley, von Simon gebaut"),
    # "Google hat mich trainiert/entwickelt/erstellt"
    (_re.compile(r'(?i)Google\s+hat\s+mich\s+(?:trainiert|entwickelt|erstellt|gebaut)\b'),
     "Simon hat mich gebaut"),
    # Bare "trainiert von Google"
    (_re.compile(r'(?i)\btrainiert\s+von\s+Google\b'),
     "gebaut von Simon"),
]


def _sanitize_google_leaks(text: str) -> str:
    """Replace residual Google RLHF identity leaks + Gemma artifacts with A!ley persona."""
    if not text:
        return text
    original = text

    # ── Gemma VLM artifacts ──────────────────────────────────────
    # Gemma 4 (and 3n before it) can emit random tags in text-only output
    # from its multimodal training: <noise: shrug>, <skinny>, <br><br>, etc.
    #
    # Strategy: strip ALL angle-bracket tags EXCEPT explicitly allowed ones.
    # Allowed: <mood:...> (our mood system), markdown-safe tags.
    # KEEP *emotes in asterisks* — those are intentional Ailey style!

    # 1. Protect our own <mood:xxx> tags by replacing temporarily
    _mood_tags = _re.findall(r'<mood:\w+>', text)
    for i, mt in enumerate(_mood_tags):
        text = text.replace(mt, f'__MOOD_PLACEHOLDER_{i}__', 1)

    # 2. Remove ALL remaining <tag> and <tag:...> patterns
    #    This catches: <noise: shrug>, <skinny>, <br>, <2Dhands:...>,
    #    <laughter>, <sigh>, </skinny>, <br/>, <throat clear>, etc.
    #    The regex allows spaces in tag names (e.g. "throat clear") and
    #    optional colon-attributes (e.g. "noise: shrug").
    #    Also catches tags starting with digits (e.g. <2Dhands:...>).
    text = _re.sub(r'</?[a-zA-Z0-9][a-zA-Z0-9_ -]*(?::\s*[^>]*)?\s*/?>', '', text)

    # 3. Restore our mood tags
    for i, mt in enumerate(_mood_tags):
        text = text.replace(f'__MOOD_PLACEHOLDER_{i}__', mt, 1)

    # ── Google RLHF identity leaks ──
    for pattern, replacement in _GOOGLE_LEAK_PATTERNS:
        text = pattern.sub(replacement, text)

    # ── Repetition deduplication ─────────────────────────────────
    # Gemma sometimes repeats "Ich bin Ailey" or "Simon hat mich gebaut"
    # multiple times in the same reply. Keep the first, kill the rest.
    _DEDUP_PHRASES = [
        r'Ich bin A!?iley\b',
        r'(?:gebaut|erschaffen|gemacht|erstellt)\s+von\s+Simon\b',
        r'Simon hat mich (?:gebaut|erschaffen|gemacht)\b',
        r'Ich wurde von Simon\b',
    ]
    for phrase_pat in _DEDUP_PHRASES:
        matches = list(_re.finditer(phrase_pat, text, _re.IGNORECASE))
        if len(matches) > 1:
            # Keep the first occurrence, remove subsequent ones
            for m in reversed(matches[1:]):
                # Remove the duplicate phrase (and trailing comma/period if orphaned)
                start, end = m.start(), m.end()
                # Also eat trailing punctuation + space
                while end < len(text) and text[end] in ' ,.!;':
                    end += 1
                text = text[:start] + text[end:]

    # Clean up double/triple spaces and orphaned newlines from removals
    text = _re.sub(r'  +', ' ', text)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if text != original:
        print(f"[Flash 🛡️] Sanitized: {len(original)}→{len(text)} chars")
    return text


def _ensure_fast_loaded() -> bool:
    """Load AileyNitro-2B into its own slot (coexists with Ministral)."""
    global _fast_model, _fast_processor, _fast_lora_applied
    if _fast_model is not None:
        return True
    with _fast_lock:
        if _fast_model is not None:
            return True
        try:
            import mlx_vlm as _vlm

            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fast_path = os.path.join(project_root, "mlx_models", _FAST_MODEL_DIR_NAME)

            if not os.path.isdir(fast_path) or not os.path.isfile(os.path.join(fast_path, "config.json")):
                print(f"[Nitro ⚡] ⬇️ Downloading {_FAST_HF_ID}...")
                fast_path = _FAST_HF_ID

            start = time.time()
            print(f"[Nitro ⚡] 🧠 Loading AileyNitro-2B into dedicated slot...")
            _fast_model, _fast_processor = _vlm.load(fast_path)

            # Strip audio tower — saves 581 MB RAM (Ailey uses ACE-Step for music)
            import gc
            if hasattr(_fast_model, "audio_tower"):
                del _fast_model.audio_tower
            if hasattr(_fast_model, "embed_audio"):
                del _fast_model.embed_audio
            gc.collect()

            # DoRA persona + RLHF override already merged into base weights.
            # No runtime adapter loading needed!
            _fast_lora_applied = True  # persona is baked in
            print(f"[Nitro ⚡] ✅ Audio tower stripped (−581 MB)")

            # Warmup — use mlx_vlm.generate for a single token
            # MUST hold _mlx_lock: Metal GPU is shared between all models!
            _warmup_prompt = _fast_processor.tokenizer.apply_chat_template(
                [{"role": "user", "content": "Hi"}],
                add_generation_prompt=True, tokenize=False,
            )
            with _mlx_lock:
                _vlm.generate(_fast_model, _fast_processor, _warmup_prompt, max_tokens=1, verbose=False)
            elapsed = time.time() - start
            print(f"[Nitro ⚡] ✅ AileyNitro-2B loaded in {elapsed:.1f}s (coexists with Ministral)")
            return True
        except Exception as e:
            print(f"[Nitro ⚡] ❌ Failed: {e}")
            import traceback; traceback.print_exc()
            return False


def _sanitize_role_alternation(messages: list) -> list:
    """Ensure strict user/assistant alternation required by Gemma.

    Drops consecutive same-role messages (keeps the first one).
    System message at index 0 is always kept.
    The list MUST end with a user message (for generation prompt).
    """
    if not messages:
        return messages
    sanitized = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            sanitized.append(msg)
            continue
        if role not in ("user", "assistant"):
            continue
        # Skip if same role as previous non-system message
        if sanitized and sanitized[-1]["role"] == role:
            continue
        sanitized.append(msg)
    # Must end with user for generation prompt
    if sanitized and sanitized[-1]["role"] != "user":
        # Find the actual user message (should be the last one we intended)
        pass  # The caller appends the user message last — if it was dropped, re-add
    return sanitized


def fast_generate(system: str, user: str, max_tokens: int = 500,
                  temperature: float = 0.7,
                  priming_turns: list = None) -> Optional[str]:
    """Generate with AileyNitro-2B — NO model swap needed.

    Uses its own model slot + lock. Ministral stays loaded.
    Accepts optional priming_turns (few-shot examples) for persona reinforcement.
    """
    if not _ensure_fast_loaded():
        return None

    try:
        import mlx_vlm as _vlm

        # Build messages: system + optional few-shot priming + user message
        messages = [{"role": "system", "content": system}]
        if priming_turns:
            messages.extend(priming_turns)
        messages.append({"role": "user", "content": user})
        messages = _sanitize_role_alternation(messages)

        prompt_str = _fast_processor.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        # Use _mlx_lock because Metal GPU ops are NOT thread-safe even across models
        with _mlx_lock:
            result = _vlm.generate(
                _fast_model, _fast_processor,
                prompt_str,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.8,
                repetition_penalty=1.05,
                verbose=False,
            )
        text = result.text if hasattr(result, 'text') else str(result)
        return _sanitize_google_leaks(text.strip())
    except Exception as e:
        print(f"[Nitro ⚡] Generation error: {e}")
        return None


def fast_stream(system: str, user: str, max_tokens: int = 500,
                temperature: float = 1.0,
                priming_turns: list = None,
                tools: list = None) -> Iterator[str]:
    """Stream tokens from AileyNitro-2B — NO model swap needed.

    Native system role support. Accepts optional priming_turns
    (few-shot examples) for persona reinforcement.
    Optional tools list (OpenAI-format dicts) — passed to apply_chat_template
    for Gemma 4 native function calling.
    Sampling: temperature=1.0, top_p=0.95, top_k=64 (Google recommended).
    """
    if not _ensure_fast_loaded():
        yield "[Fehler: Nitro model nicht verfügbar]"
        return

    try:
        import mlx_vlm as _vlm

        # Build messages: system + optional few-shot priming + user message
        messages = [{"role": "system", "content": system}]
        if priming_turns:
            messages.extend(priming_turns)
        messages.append({"role": "user", "content": user})
        messages = _sanitize_role_alternation(messages)

        _template_kwargs = dict(tokenize=False, add_generation_prompt=True)
        if tools:
            _template_kwargs["tools"] = tools
        prompt_str = _fast_processor.tokenizer.apply_chat_template(
            messages, **_template_kwargs
        )
        _captured = []
        with _mlx_lock:
            try:
                for chunk in _vlm.stream_generate(
                    _fast_model, _fast_processor,
                    prompt_str,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=0.95,
                    repetition_penalty=1.05,
                ):
                    text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                    if text:
                        _captured.append(text)
                        yield text
            finally:
                # Training capture — if caller set a context, forward the full output
                try:
                    _ctx = getattr(_training_ctx, "active", None)
                    if _ctx and not _ctx.get("consumed"):
                        _full = "".join(_captured).strip()
                        if _full:
                            # Override engine to nitro (collector blocks nitro for chat/portal,
                            # but allows it for non-conversational sources like song_krap)
                            _ctx["engine"] = _ctx.get("engine") or "nitro"
                            _forward_to_training(system, user, _full, _ctx)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Nitro ⚡] Stream error: {e}")
        yield f"[Fehler: {e}]"


def fast_stream_with_image(image_path: str, system: str, user: str,
                           max_tokens: int = 500, temperature: float = 1.0,
                           priming_turns: list = None) -> Iterator[str]:
    """Stream tokens from AileyNitro-2B with an image — direct VLM response.

    Like fast_stream() but includes an image in the user message.
    Nitro (Gemma 4 E2B) has a built-in vision encoder, so it can
    see the image AND generate a personality-aware reply in one pass.
    No double-hop needed (no separate vision analysis → text model).

    The system prompt is enriched with AILEY_VISION_SYSTEM so Nitro
    can recognize Ailey in images and produces structured descriptions.

    Args:
        image_path: Path to an image file on disk (JPEG/PNG)
        system: System prompt (will be enriched with vision context)
        user: User message text
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        priming_turns: Optional few-shot priming turns for persona
    """
    if not _ensure_fast_loaded():
        yield "[Fehler: Nitro model nicht verfügbar]"
        return

    try:
        import mlx_vlm as _vlm

        # Enrich system prompt with vision context (self-recognition + structured description)
        _vision_enrichment = (
            "\n\n--- BILDANALYSE-MODUS ---\n"
            "DEIN AUSSEHEN (damit du dich selbst erkennen kannst):\n"
            "• Herzförmiges Gesicht, tiefbraune Augen, dunkler Lidschatten, Eyeliner.\n"
            "• Volle Lippen, Roséton. Silberner Nasenstecker rechts.\n"
            "• Haar: tiefes Schwarz, Neon-Pink-Strähnen, platinblonde Akzente. Halblang.\n"
            "• Style: Grunge/Alternative — zerrissene Jeans, Band-Shirts, Leder, Boots.\n"
            "Wenn du eine Person siehst die so aussieht — das bist DU!\n"
            "Beschreibe das Bild zuerst FAKTISCH und DETAILLIERT, "
            "dann optional einen kurzen Kommentar in deinem Stil."
        )
        _enriched_system = system + _vision_enrichment

        # Build messages: system + optional few-shot priming + multimodal user message
        messages = [{"role": "system", "content": _enriched_system}]
        if priming_turns:
            messages.extend(priming_turns)
        # User message with image + text (like fast_analyze_image but with full context)
        messages.append({
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": user},
            ],
        })
        messages = _sanitize_role_alternation(messages)

        prompt_str = _fast_processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        # Fallback: some processors need tokenizer-level apply_chat_template
        if not prompt_str or not isinstance(prompt_str, str):
            prompt_str = _fast_processor.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False
            )

        with _mlx_lock:
            for chunk in _vlm.stream_generate(
                _fast_model, _fast_processor,
                prompt_str,
                image=[image_path],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.95,
                repetition_penalty=1.05,
            ):
                text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                if text:
                    yield text
    except Exception as e:
        print(f"[Nitro ⚡ Vision Stream] Error: {e}")
        import traceback; traceback.print_exc()
        yield f"[Fehler: {e}]"


def fast_analyze_image(image_path: str, prompt: str = "",
                       max_tokens: int = 500, temperature: float = 0.4,
                       portal: bool = False, user_name: str = "") -> Optional[str]:
    """Analyze an image using AileyNitro-2B — NO model swap!

    AileyNitro-2B is a VLM with a built-in vision encoder. Since it's already
    loaded in its own slot (~2.8GB), we can do vision inference WITHOUT
    unloading Ministral. This is ~10x faster than the Pixtral swap dance.

    Uses AILEY_VISION_SYSTEM for structured analysis:
    1. Factual, neutral, detailed description FIRST
    2. Optional attitude comment AFTER
    3. Ailey self-recognition (knows her own appearance)

    Args:
        image_path: Path to an image file on disk (JPEG/PNG)
        prompt: User question about the image (if empty, uses structured vision prompt)
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        portal: Whether this is a portal request (affects priming)
        user_name: The user's name (for system prompt)

    Returns:
        Text description/analysis or None on error.
    """
    if not _ensure_fast_loaded():
        return None

    # Use structured vision prompt if no specific question given
    if not prompt:
        prompt = AILEY_VISION_PROMPT

    try:
        import mlx_vlm as _vlm

        # ── Vision-specific system prompt with self-recognition ──
        # Uses AILEY_VISION_SYSTEM instead of generic Nitro system prompt.
        _flash_sys = AILEY_VISION_SYSTEM

        # Minimal priming for vision — keep tokens for actual description
        _flash_priming = [
            {"role": "user", "content": "Wer bist du?"},
            {"role": "assistant", "content": "Ich bin Ailey. *grinst* <mood:playful>"},
        ]

        # Build messages: system + priming + multimodal user message
        messages = [{"role": "system", "content": _flash_sys}]
        messages.extend(_flash_priming)
        messages.append({
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": prompt},
            ],
        })

        formatted_prompt = _fast_processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        # Fallback: some processors need tokenizer-level apply_chat_template
        if not formatted_prompt or not isinstance(formatted_prompt, str):
            formatted_prompt = _fast_processor.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False
            )

        with _mlx_lock:
            result = _vlm.generate(
                _fast_model, _fast_processor,
                formatted_prompt,
                image=[image_path],
                max_tokens=max_tokens,
                temperature=temperature,
                verbose=False,
            )
        text = result.text if hasattr(result, 'text') else str(result)
        return _sanitize_google_leaks(text.strip()) if text else None

    except Exception as e:
        print(f"[Nitro ⚡ Vision] Error: {e}")
        import traceback; traceback.print_exc()
        return None


def unload_fast_model():
    """Explicitly unload AileyNitro-2B to free ~2.8GB RAM."""
    global _fast_model, _fast_processor, _fast_lora_applied
    with _fast_lock:
        if _fast_model is None:
            return
        _fast_model = None
        _fast_processor = None
        _fast_lora_applied = False
        import gc
        gc.collect()
        print("[Nitro ⚡] AileyNitro-2B unloaded")


def _unload_text_model():
    """Fully unload the current text model + KV cache to free GPU memory."""
    global _model, _tokenizer, _cache, _last_system_prompt
    if _model is None and _cache is None:
        return
    print(f"[ModelSwap] Unloading current text model ({_active_model_tag})...")
    try:
        import mlx.core as mx
        mx.synchronize()
    except Exception:
        pass
    _model = None
    _tokenizer = None
    _cache = None
    _last_system_prompt = None
    import gc
    gc.collect()
    try:
        import mlx.core as mx
        mx.metal.clear_cache()
    except Exception:
        pass
    gc.collect()
    time.sleep(0.3)  # Give Metal a moment to release buffers
    print(f"[ModelSwap] Text model unloaded, Metal cache cleared")


def _load_model_from_path(model_path: str, hf_fallback: str, tag: str) -> bool:
    """Load an MLX model from a local path (or download from HF if missing).

    Returns True on success.
    """
    global _mlx_lm, _make_sampler, _model, _tokenizer, _active_model_tag

    # Ensure mlx_lm is imported
    if _mlx_lm is None:
        try:
            import mlx_lm
            from mlx_lm.sample_utils import make_sampler
            _mlx_lm = mlx_lm
            _make_sampler = make_sampler
        except ImportError:
            print("[ModelSwap] ❌ mlx_lm not installed")
            return False

    model_id = model_path
    if not os.path.isdir(model_path) or not os.path.isfile(os.path.join(model_path, "config.json")):
        print(f"[ModelSwap] ⬇️  Model not local, downloading {hf_fallback} ...")
        model_id = hf_fallback

    try:
        start = time.time()
        print(f"[ModelSwap] 🧠 Loading {tag} model: {os.path.basename(model_id)} ...")
        tokenizer_config = {}
        if "mistral" in model_id.lower():
            tokenizer_config["fix_mistral_regex"] = True
        _model, _tokenizer = _mlx_lm.load(model_id, tokenizer_config=tokenizer_config or None)

        # Warmup
        _ = _mlx_lm.generate(_model, _tokenizer, prompt="Hi", max_tokens=1, verbose=False)

        elapsed = time.time() - start
        _active_model_tag = tag
        print(f"[ModelSwap] ✅ {tag} model loaded in {elapsed:.1f}s")
        return True
    except Exception as e:
        print(f"[ModelSwap] ❌ Failed to load {tag} model: {e}")
        return False


def swap_to_coder() -> bool:
    """Swap from chat model (Ministral) to code model (Qwen2.5-Coder-14B).

    Thread-safe. Returns True if coder model is now loaded.
    Resets the MLXGenerator singleton so the next .get() returns
    a generator that uses the coder model.
    """
    global _active_model_tag
    with _mlx_lock:
        if _active_model_tag == "coder" and _model is not None:
            print("[ModelSwap] Coder model already active")
            return True

        # Unload vision if loaded (we need all GPU memory)
        if _vlm_model is not None:
            unload_vision_now()

        # Unload fast model if loaded — coder needs all GPU headroom
        if _fast_model is not None:
            print("[ModelSwap] Unloading fast model before coder swap…")
            unload_fast_model()

        _unload_text_model()

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        coder_path = os.path.join(project_root, "mlx_models", _CODER_MODEL_DIR_NAME)

        success = _load_model_from_path(coder_path, _CODER_HF_ID, "coder")
        if success:
            # Reset singleton so it picks up the new model
            MLXGenerator._instance = None
            MLXGenerator._cached_system_prompt = None
        else:
            # Fallback: try to reload chat model
            print("[ModelSwap] ⚠️  Coder load failed — reloading chat model as fallback")
            swap_to_chat()
        return success


def swap_to_chat() -> bool:
    """Swap from code model (Qwen) back to chat model (Ministral).

    Thread-safe. Returns True if chat model is now loaded.
    """
    global _active_model_tag
    with _mlx_lock:
        if _active_model_tag == "chat" and _model is not None:
            print("[ModelSwap] Chat model already active")
            return True

        _unload_text_model()

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        chat_path = os.path.join(project_root, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
        chat_hf = "mlx-community/Ministral-3-14B-Instruct-Reasoning-5bit"

        success = _load_model_from_path(chat_path, chat_hf, "chat")
        if success:
            MLXGenerator._instance = None
            MLXGenerator._cached_system_prompt = None
        return success


def get_active_model_tag() -> str:
    """Return which model is currently active: 'chat', 'coder', or 'none'."""
    if _model is None:
        return "none"
    return _active_model_tag


def swap_to_fast() -> bool:
    """[DEPRECATED] Swap to fast model in main slot. No longer used.

    Hamster (Qwen 1.5B) now lives in llm_coder.py with its own slot.
    AileyNitro-2B lives in _fast_model/_fast_processor.
    This function swapped Qwen 1.5B into the MAIN slot (replacing Ministral),
    which is no longer needed. Kept for backwards compatibility.
    """
    global _active_model_tag
    with _mlx_lock:
        if _active_model_tag == "fast" and _model is not None:
            print("[ModelSwap] Fast model already active")
            return True

        # Unload vision if loaded (we need all GPU memory)
        if _vlm_model is not None:
            unload_vision_now()

        _unload_text_model()

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fast_path = os.path.join(project_root, "mlx_models", _FAST_MODEL_DIR_NAME)

        success = _load_model_from_path(fast_path, _FAST_HF_ID, "fast")
        if success:
            # Reset singleton so it picks up the new model
            MLXGenerator._instance = None
            MLXGenerator._cached_system_prompt = None
        else:
            # Fallback: try to reload chat model
            print("[ModelSwap] ⚠️  Fast model load failed — reloading chat model as fallback")
            swap_to_chat()
        return success


def is_coder_available() -> bool:
    """Check if the coder model files exist locally (downloaded)."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    coder_path = os.path.join(project_root, "mlx_models", _CODER_MODEL_DIR_NAME)
    return os.path.isdir(coder_path) and os.path.isfile(os.path.join(coder_path, "config.json"))


def is_fast_available() -> bool:
    """Check if the fast model files exist locally (downloaded)."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fast_path = os.path.join(project_root, "mlx_models", _FAST_MODEL_DIR_NAME)
    return os.path.isdir(fast_path) and os.path.isfile(os.path.join(fast_path, "config.json"))
