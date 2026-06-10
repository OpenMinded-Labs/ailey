# -*- coding: utf-8 -*-
"""
Qwen 3 8B Instruct via llama.cpp (GGUF) using Metal on macOS.

Configuration:
- Env AILEY_QWEN_GGUF: path to GGUF model (defaults to Simon's known path)
- Env AILEY_QWEN_CTX: context window (default 4096)

Usage:
    gen = QwenLlamaCpp.get()
    text = gen.generate(system, user, params)
"""
from __future__ import annotations
import os
from typing import Dict, Optional

try:
    from llama_cpp import Llama
except Exception:  # pragma: no cover
    Llama = None  # type: ignore


class QwenLlamaCpp:
    _instance: Optional["QwenLlamaCpp"] = None

    @classmethod
    def get(cls) -> Optional["QwenLlamaCpp"]:
        if cls._instance is None:
            try:
                cls._instance = QwenLlamaCpp()
            except Exception:
                cls._instance = None
        return cls._instance

    def __init__(self):
        if Llama is None:
            raise RuntimeError("llama_cpp not available in environment")

        model_path = os.environ.get(
            "AILEY_QWEN_GGUF",
            "/Users/simonvandeloo/models/qwen3-8b/qwen3-8b-instruct-q8_0.gguf",
        )
        n_ctx = int(os.environ.get("AILEY_QWEN_CTX", "4096"))

        # Prefer chat_format for Qwen (qwen2/qwen) if available; llama.cpp handles templates.
        # If the model does not embed chat template, llama.cpp will still accept plain prompts.
        chat_format = os.environ.get("AILEY_QWEN_CHAT_FORMAT", "qwen2").strip()
        try:
            self._llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=max(1, os.cpu_count() or 4),
                n_gpu_layers=-1,  # offload as much as possible to Metal
                chat_format=chat_format or None,  # type: ignore[arg-type]
                verbose=False,
            )
        except Exception:
            # Fallback without chat_format if the template name is not supported
            try:
                self._llm = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_threads=max(1, os.cpu_count() or 4),
                    n_gpu_layers=-1,
                    verbose=False,
                )
            except Exception:
                # Final fallback: CPU only
                self._llm = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_threads=max(1, os.cpu_count() or 4),
                    n_gpu_layers=0,
                    verbose=False,
                )

    def generate(self, system: str, user: str, params: Dict) -> str:
        temperature = float(params.get("temperature", 0.7))
        top_p = float(params.get("top_p", 0.9))
        max_tokens = int(params.get("max_tokens", 512))
        stop = params.get("stop") or []

        # Prefer chat API to leverage the chat template
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
            text = out["choices"][0]["message"]["content"]
            # Strip Qwen3 thinking tags if present
            text = self._strip_thinking(text or "")
            return text
        except Exception:
            # Fallback: plain completion with a simple instruction-style prompt
            prompt = f"System:\n{system}\n\nUser:\n{user}\n\nAssistant:\n"
            out = self._llm(
                prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stop=stop,
            )
            text = (out or {}).get("choices", [{}])[0].get("text", "")
            return self._strip_thinking(text)

    def _strip_thinking(self, text: str) -> str:
        """Remove <think>...</think> blocks from Qwen3 output and return only the response."""
        import re
        
        # If there's a </think> tag, return everything after it
        if '</think>' in text:
            text = text.split('</think>')[-1]
        
        # Remove any remaining <think> tags (incomplete blocks)
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
        
        # Remove "A:" or "B:" prefixes that Qwen sometimes adds
        text = re.sub(r'^[A-Z]:\s*', '', text.strip())
        
        # Remove reasoning artifacts that leaked through
        lines = text.split('\n')
        cleaned = []
        skip_reasoning = False
        for line in lines:
            stripped = line.strip()
            # Skip empty lines at start
            if not cleaned and not stripped:
                continue
            # Skip obvious reasoning lines
            if re.match(r'^(Okay,|Let me|First,|I need to|I should|The user|That sounds|Alright,|Yeah,)', stripped):
                skip_reasoning = True
                continue
            if skip_reasoning and stripped.startswith(('B:', 'A:')):
                skip_reasoning = False
                line = re.sub(r'^[A-Z]:\s*', '', stripped)
            if not skip_reasoning:
                cleaned.append(line)
        
        result = '\n'.join(cleaned).strip()
        # Final cleanup of any A:/B: prefix
        result = re.sub(r'^[A-Z]:\s*', '', result)
        return result

    def stream(self, system: str, user: str, params: Dict):  # generator
        """Yield tokens incrementally using llama.cpp's streaming support.
        
        Filters out <think>...</think> blocks in real-time.
        Falls back to non-streaming full generation if streaming errors occur.
        """
        temperature = float(params.get("temperature", 0.7))
        top_p = float(params.get("top_p", 0.9))
        max_tokens = int(params.get("max_tokens", 512))
        stop = params.get("stop") or []
        
        # Buffer for detecting and filtering think blocks
        buffer = ""
        in_think_block = False
        think_ended = False
        
        try:
            for out in self._llm.create_chat_completion(
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
                try:
                    delta = out["choices"][0]["delta"].get("content")
                except Exception:
                    delta = None
                    
                if not delta:
                    continue
                
                buffer += delta
                
                # Check for think block start
                if "<think>" in buffer and not in_think_block:
                    in_think_block = True
                    # Yield anything before <think>
                    before_think = buffer.split("<think>")[0]
                    if before_think.strip():
                        yield before_think
                    buffer = buffer.split("<think>", 1)[1] if "<think>" in buffer else ""
                
                # Check for think block end
                if "</think>" in buffer and in_think_block:
                    in_think_block = False
                    think_ended = True
                    # Keep everything after </think>
                    buffer = buffer.split("</think>", 1)[1] if "</think>" in buffer else ""
                    # Yield the rest if any
                    if buffer.strip():
                        yield buffer
                        buffer = ""
                    continue
                
                # If we're past the think block, yield tokens
                if think_ended and not in_think_block:
                    yield delta
                    buffer = ""
                elif not in_think_block and not "<" in buffer:
                    # No think block detected yet, yield immediately
                    yield buffer
                    buffer = ""
                    
        except Exception:
            # Fallback: single full reply
            full = self.generate(system, user, params)
            if full:
                yield full
