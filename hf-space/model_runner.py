#!/usr/bin/env python3
"""Lazy local-model runner for the HF Space demo.

Loads Qwen2.5-0.5B-Instruct on first use (CPU, float32, ~2GB RAM).
Small model = more mistakes = better demo.
Per-session call logging via Gradio session state.
"""
from __future__ import annotations

import os
import sys
import time
import json
import uuid
import logging

logger = logging.getLogger(__name__)

_MODEL = None
_TOKENIZER = None
_LOAD_ATTEMPTED = False
_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

# Global call log (all sessions) — capped
_GLOBAL_LOG: list[dict] = []
_MAX_LOG = 100


def _load_model():
    global _MODEL, _TOKENIZER, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _MODEL, _TOKENIZER
    _LOAD_ATTEMPTED = True
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        logger.info("Loading %s...", _MODEL_ID)
        _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_ID)
        _MODEL = AutoModelForCausalLM.from_pretrained(_MODEL_ID)
        logger.info("Loaded: %dM params", sum(p.numel() for p in _MODEL.parameters()) // 1_000_000)
    except Exception as e:
        logger.warning("Load failed: %s", e)
    return _MODEL, _TOKENIZER


def generate_response(prompt: str, session_id: str = "unknown", max_new_tokens: int = 200, temperature: float = 0.8) -> str:
    """Generate response from local model. Logs with session_id."""
    model, tok = _load_model()
    t0 = time.time()
    call_id = len(_GLOBAL_LOG) + 1

    if model is None or tok is None:
        _log(call_id, session_id, prompt, "[model not loaded]", 0, False)
        return "[模型未加载 / model not loaded]"

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
                do_sample=True,
                top_p=0.9,
                pad_token_id=tok.eos_token_id,
            )
        resp = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        elapsed = round(time.time() - t0, 2)
        _log(call_id, session_id, prompt, resp, elapsed, True)
        return resp
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        _log(call_id, session_id, prompt, f"[error: {e}]", elapsed, False)
        return f"[error: {e}]"


def _log(call_id, session_id, prompt, response, elapsed, success):
    _GLOBAL_LOG.append({
        "callId": call_id,
        "sessionId": session_id[:8],
        "time": time.strftime("%H:%M:%S"),
        "model": _MODEL_ID,
        "prompt": prompt[:120].replace("\n", " ") + ("..." if len(prompt) > 120 else ""),
        "response": response[:300] + ("..." if len(response) > 300 else ""),
        "respLen": len(response),
        "sec": elapsed,
        "ok": success,
    })
    if len(_GLOBAL_LOG) > _MAX_LOG:
        _GLOBAL_LOG.pop(0)


def get_session_log(session_id: str) -> list[dict]:
    """Return calls from this session only."""
    sid = session_id[:8] if session_id else "unknown"
    return [e for e in _GLOBAL_LOG if e.get("sessionId") == sid]


def get_global_log(limit: int = 20) -> list[dict]:
    return list(_GLOBAL_LOG[-limit:])


def model_status() -> dict:
    model, _ = _load_model()
    return {
        "modelId": _MODEL_ID,
        "loaded": model is not None,
        "params": f"{sum(p.numel() for p in model.parameters()) // 1_000_000}M" if model else "N/A",
        "backend": "local CPU (transformers)",
        "totalCalls": len(_GLOBAL_LOG),
    }
