#!/usr/bin/env python3
"""Lazy local-model runner for the HF Space demo.

Loads Qwen2.5-0.5B-Instruct on first use (CPU, float32, ~2GB RAM).
Supports: generate_response() for answering, and self_judge() for the
same model to critique its own output.
Per-session call logging with full response capture.
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


def _raw_generate(prompt: str, max_new_tokens: int = 200, temperature: float = 0.8) -> str:
    """Internal: generate raw text from the model."""
    model, tok = _load_model()
    if model is None or tok is None:
        return "[model not loaded]"
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
        return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    except Exception as e:
        return f"[error: {e}]"


def generate_response(prompt: str, session_id: str = "unknown",
                      max_new_tokens: int = 200, temperature: float = 0.8) -> str:
    """Generate a response from the local model. Logs the call."""
    t0 = time.time()
    call_id = len(_GLOBAL_LOG) + 1
    resp = _raw_generate(prompt, max_new_tokens, temperature)
    elapsed = round(time.time() - t0, 2)
    ok = not resp.startswith("[")
    _log(call_id, session_id, "generate", prompt, resp, elapsed, ok)
    return resp


def self_judge(original_prompt: str, llm_response: str,
               session_id: str = "unknown") -> str:
    """The SAME model critiques its own output.

    Asks the model: 'You previously answered X to question Y. Is your
    answer correct? Check for unit errors, sign errors, or logical issues.'
    Returns the model's self-assessment.
    """
    judge_prompt = (
        f"You are checking your own work for errors.\n\n"
        f"Original question:\n{original_prompt}\n\n"
        f"Your answer was:\n{llm_response}\n\n"
        f"Now carefully check your answer for these specific errors:\n"
        f"1. Unit errors (e.g. using m/s^2 instead of m/s, or N instead of J)\n"
        f"2. Sign errors (e.g. +2x instead of -2x)\n"
        f"3. Whether the problem is actually solvable\n\n"
        f"Is your answer correct? If you find an error, state what the error is. "
        f"If the problem is unsolvable, say so.\n"
        f"Answer: CORRECT / ERROR (explain) / UNSOLVABLE (explain)"
    )
    t0 = time.time()
    call_id = len(_GLOBAL_LOG) + 1
    resp = _raw_generate(judge_prompt, max_new_tokens=150, temperature=0.3)
    elapsed = round(time.time() - t0, 2)
    ok = not resp.startswith("[")
    _log(call_id, session_id, "self_judge", judge_prompt, resp, elapsed, ok)
    return resp


def _log(call_id, session_id, call_type, prompt, response, elapsed, success):
    _GLOBAL_LOG.append({
        "callId": call_id,
        "sessionId": session_id[:8],
        "type": call_type,
        "time": time.strftime("%H:%M:%S"),
        "model": _MODEL_ID,
        "prompt": prompt[:120].replace("\n", " ") + ("..." if len(prompt) > 120 else ""),
        "response": response[:400] + ("..." if len(response) > 400 else ""),
        "respLen": len(response),
        "sec": elapsed,
        "ok": success,
    })
    if len(_GLOBAL_LOG) > _MAX_LOG:
        _GLOBAL_LOG.pop(0)


def get_session_log(session_id: str) -> list[dict]:
    sid = session_id[:8] if session_id else "unknown"
    return [e for e in _GLOBAL_LOG if e.get("sessionId") == sid]


def get_global_log(limit: int = 20) -> list[dict]:
    return list(_GLOBAL_LOG[-limit:])


def model_status() -> dict:
    model, _ = _load_model()
    gen_calls = sum(1 for e in _GLOBAL_LOG if e.get("type") == "generate")
    judge_calls = sum(1 for e in _GLOBAL_LOG if e.get("type") == "self_judge")
    return {
        "modelId": _MODEL_ID,
        "loaded": model is not None,
        "params": f"{sum(p.numel() for p in model.parameters()) // 1_000_000}M" if model else "N/A",
        "backend": "local CPU (transformers)",
        "totalCalls": len(_GLOBAL_LOG),
        "generateCalls": gen_calls,
        "selfJudgeCalls": judge_calls,
    }
