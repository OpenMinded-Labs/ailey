# -*- coding: utf-8 -*-
"""
Generic GGUF Model Backend via llama.cpp with Metal acceleration.

Supports: Qwen3, Ministral, Mistral, Llama, and other GGUF models.

Configuration (Environment Variables):
- AILEY_MODEL_PATH: Path to GGUF model file
- AILEY_MODEL_CTX: Context window size (default: 4096)
- AILEY_MODEL_CHAT_FORMAT: Chat format hint (auto-detected if not set)

Usage:
    from ailey_system.llm_gguf import LLMBackend
    
    llm = LLMBackend.get()
    response = llm.generate(system_prompt, user_message, params)
    
    # Streaming
    for token in llm.stream(system_prompt, user_message, params):
        print(token, end='', flush=True)
"""
from __future__ import annotations
import os
import re
from typing import Dict, Optional, Generator

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore


# Default model paths (order of preference)
DEFAULT_MODEL_PATHS = [
    "/Users/simonvandeloo/models/ministral-14b/ministral-3-14b-instruct-q5_k_m.gguf",
    "/Users/simonvandeloo/models/qwen3-8b/qwen3-8b-instruct-q8_0.gguf",
]


class LLMBackend:
    """Unified LLM backend for GGUF models via llama.cpp."""
    
    _instance: Optional["LLMBackend"] = None
    
    @classmethod
    def get(cls, force_reload: bool = False) -> Optional["LLMBackend"]:
        """Get or create singleton instance."""
        if cls._instance is None or force_reload:
            try:
                cls._instance = LLMBackend()
            except Exception as e:
                print(f"[LLMBackend] Failed to initialize: {e}")
                cls._instance = None
        return cls._instance
    
    def __init__(self):
        if Llama is None:
            raise RuntimeError("llama-cpp-python not installed. Run: pip install llama-cpp-python")
        
        # Find model path
        model_path = os.environ.get("AILEY_MODEL_PATH")
        if not model_path:
            for path in DEFAULT_MODEL_PATHS:
                if os.path.exists(path):
                    model_path = path
                    break
        
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"No GGUF model found. Set AILEY_MODEL_PATH or place model in: {DEFAULT_MODEL_PATHS}")
        
        self.model_path = model_path
        self.model_name = os.path.basename(model_path)
        
        # Configuration
        n_ctx = int(os.environ.get("AILEY_MODEL_CTX", "4096"))
        chat_format = os.environ.get("AILEY_MODEL_CHAT_FORMAT", "").strip() or None
        
        print(f"[LLMBackend] Loading: {self.model_name}")
        print(f"[LLMBackend] Context: {n_ctx} tokens")
        
        # Detect model type for optimal settings
        self._is_qwen3 = "qwen3" in self.model_name.lower()
        self._is_ministral = "ministral" in self.model_name.lower()
        
        # Load model with Metal acceleration
        try:
            self._llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=max(1, os.cpu_count() or 4),
                n_gpu_layers=-1,  # Full GPU offload
                chat_format=chat_format,
                verbose=False,
            )
        except Exception:
            # Fallback without chat_format
            self._llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=max(1, os.cpu_count() or 4),
                n_gpu_layers=-1,
                verbose=False,
            )
        
        print(f"[LLMBackend] ✅ Model loaded successfully")
    
    def generate(self, system: str, user: str, params: Dict) -> str:
        """Generate a complete response."""
        temperature = float(params.get("temperature", 0.7))
        top_p = float(params.get("top_p", 0.9))
        max_tokens = int(params.get("max_tokens", 512))
        stop = params.get("stop") or []
        
        try:
            out = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stop=stop,
            )
            text = out["choices"][0]["message"]["content"] or ""
            return self._postprocess(text)
        except Exception as e:
            # Fallback to completion API
            prompt = f"System: {system}\n\nUser: {user}\n\nAssistant:"
            out = self._llm(
                prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stop=stop,
            )
            text = (out or {}).get("choices", [{}])[0].get("text", "")
            return self._postprocess(text)
    
    def stream(self, system: str, user: str, params: Dict) -> Generator[str, None, None]:
        """Stream response tokens with real-time think-block filtering."""
        temperature = float(params.get("temperature", 0.7))
        top_p = float(params.get("top_p", 0.9))
        max_tokens = int(params.get("max_tokens", 512))
        stop = params.get("stop") or []
        
        buffer = ""
        in_think_block = False
        past_think = False
        
        try:
            for chunk in self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=True,
                stop=stop,
            ):
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if not delta:
                    continue
                
                # For Qwen3: filter <think>...</think> blocks
                if self._is_qwen3:
                    buffer += delta
                    
                    # Detect think block start
                    if "<think>" in buffer and not in_think_block:
                        in_think_block = True
                        before = buffer.split("<think>")[0]
                        if before.strip():
                            yield before
                        buffer = buffer.split("<think>", 1)[1] if "<think>" in buffer else ""
                        continue
                    
                    # Detect think block end
                    if "</think>" in buffer and in_think_block:
                        in_think_block = False
                        past_think = True
                        buffer = buffer.split("</think>", 1)[1] if "</think>" in buffer else ""
                        if buffer.strip():
                            yield buffer
                        buffer = ""
                        continue
                    
                    # Output tokens after think block
                    if past_think and not in_think_block:
                        yield delta
                        buffer = ""
                    elif not in_think_block and "<" not in buffer:
                        yield buffer
                        buffer = ""
                else:
                    # Non-Qwen models: stream directly
                    yield delta
                    
        except Exception:
            # Fallback to non-streaming
            full = self.generate(system, user, params)
            if full:
                yield full
    
    def _postprocess(self, text: str) -> str:
        """Clean up model output."""
        # Remove Qwen3 think blocks
        if self._is_qwen3:
            if "</think>" in text:
                text = text.split("</think>")[-1]
            text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
        
        # Remove <thinking>/<thought> blocks (Ministral DoRA model)
        for _close in ("</thinking>", "</thought>"):
            if _close in text:
                text = text.split(_close)[-1]
        for _open in ("<thinking>", "<thought>"):
            text = re.sub(re.escape(_open) + r".*", "", text, flags=re.DOTALL)
        
        # Remove common artifacts
        text = re.sub(r"^[A-Z]:\s*", "", text.strip())  # "A:" prefix
        
        return text.strip()
    
    @property
    def info(self) -> Dict:
        """Get model information."""
        return {
            "model_name": self.model_name,
            "model_path": self.model_path,
            "is_qwen3": self._is_qwen3,
            "is_ministral": self._is_ministral,
        }


# Backwards compatibility alias
QwenLlamaCpp = LLMBackend
