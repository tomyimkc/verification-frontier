#!/usr/bin/env python3
"""Lazy local-model runner for the HF Space demo.

Loads Qwen2.5-0.5B-Instruct on first use (CPU, float32, ~2GB RAM).
Small model = more mistakes = better demo (the verifier has more to catch).
Includes call logging so judges can track every LLM call.
"""
from __future__ import annotations

import os
import sys
import time
import json
import logging

logger = logging.getLogger(__name__)

_MODEL = None
_TOKENIZER = None
_LOAD_ATTEMPTED = False
_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

# Call log — accumulates every generate_response() call
_CALL_LOG: list[dict] = []
_MAX_LOG_ENTRIES = 50


def _load_model():
    """Lazy-load the model. Returns (model, tokenizer) or (None, None) on failure."""
    global _MODEL, _TOKENIZER, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _MODEL, _TOKENIZER
    _LOAD_ATTEMPTED = True
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        logger.info("Loading %s on CPU...", _MODEL_ID)
        _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_ID)
        _MODEL = AutoModelForCausalLM.from_pretrained(_MODEL_ID)
        logger.info("Model loaded: %dM params", sum(p.numel() for p in _MODEL.parameters()) // 1_000_000)
    except Exception as e:
        logger.warning("Model load failed: %s", e)
        _MODEL = None
        _TOKENIZER = None
    return _MODEL, _TOKENIZER


def generate_response(prompt: str, max_new_tokens: int = 150, temperature: float = 0.7) -> str:
    """Generate a response from the local model. Logs every call."""
    model, tok = _load_model()
    t0 = time.time()

    if model is None or tok is None:
        _log_call(prompt, "[model not loaded]", 0, False)
        return "[模型未加载 / model not loaded — 请检查 Space 日志 / check Space logs]"

    try:
        import torch
        messages = [{"role": "user", "content": prompt}]
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(text, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=tok.eos_token_id,
            )
        response = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        elapsed = round(time.time() - t0, 2)
        _log_call(prompt, response, elapsed, True)
        return response
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        _log_call(prompt, f"[error: {e}]", elapsed, False)
        return f"[生成错误 / generation error: {e}]"


def _log_call(prompt: str, response: str, elapsed: float, success: bool):
    """Append to the call log."""
    entry = {
        "callId": len(_CALL_LOG) + 1,
        "timestamp": time.strftime("%H:%M:%S"),
        "model": _MODEL_ID,
        "prompt": prompt[:100] + ("..." if len(prompt) > 100 else ""),
        "responseLength": len(response),
        "elapsedSec": elapsed,
        "success": success,
    }
    _CALL_LOG.append(entry)
    if len(_CALL_LOG) > _MAX_LOG_ENTRIES:
        _CALL_LOG.pop(0)


def get_call_log() -> list[dict]:
    """Return the full call log."""
    return list(_CALL_LOG)


def model_status() -> dict:
    """Return model loading status for display."""
    model, tok = _load_model()
    return {
        "modelId": _MODEL_ID,
        "loaded": model is not None,
        "params": f"{sum(p.numel() for p in model.parameters()) // 1_000_000}M" if model else "N/A",
        "backend": "local CPU (transformers)",
        "fallback": "curated examples" if model is None else "active",
        "totalCalls": len(_CALL_LOG),
    }
