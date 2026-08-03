#!/usr/bin/env python3
"""HF Inference API model runner — calls Qwen2.5-7B-Instruct via HF router.

No local model loading — instant responses, smarter model, zero CPU overhead.
Uses HF_TOKEN from the Space environment (auto-injected for Space owner).
"""
from __future__ import annotations

import os
import sys
import time
import logging
import requests

logger = logging.getLogger(__name__)

_MODEL_ID = os.environ.get("VF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
_FALLBACK_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "deepseek-ai/DeepSeek-V3",
]
_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
_TOKEN = os.environ.get("HF_TOKEN", "")

_GLOBAL_LOG: list[dict] = []
_MAX_LOG = 100


def _api_call(messages: list[dict], max_tokens: int = 1000, temperature: float = 0.7) -> str:
    """Call the HF router API with automatic fallback to alternative models."""
    global _MODEL_ID
    models_to_try = [_MODEL_ID] + [m for m in _FALLBACK_MODELS if m != _MODEL_ID]
    for model in models_to_try:
        try:
            resp = requests.post(
                _ROUTER_URL,
                headers={"Authorization": f"Bearer {_TOKEN}"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                if model != _MODEL_ID:
                    logger.info("Switched to fallback model: %s", model)
                    _MODEL_ID = model
                return resp.json()["choices"][0]["message"]["content"].strip()
            elif resp.status_code == 400:
                logger.info("Model %s unavailable, trying fallback...", model)
                continue
            else:
                return f"[API error {resp.status_code}: {resp.text[:100]}]"
        except Exception as e:
            logger.warning("API call to %s failed: %s", model, e)
            continue
    return "[All models unavailable — please retry later]"


def generate_response(prompt: str, session_id: str = "unknown",
                      max_new_tokens: int = 1000, temperature: float = 0.7) -> str:
    t0 = time.time()
    call_id = len(_GLOBAL_LOG) + 1
    resp = _api_call([{"role": "user", "content": prompt}], max_new_tokens, temperature)
    elapsed = round(time.time() - t0, 2)
    ok = not resp.startswith("[")
    _log(call_id, session_id, "generate", prompt, resp, elapsed, ok)
    return resp


def self_judge(original_prompt: str, llm_response: str, session_id: str = "unknown") -> str:
    judge_prompt = (
        f"You are checking your own work for errors.\n\n"
        f"Original question:\n{original_prompt}\n\n"
        f"Your answer was:\n{llm_response}\n\n"
        f"Now carefully check your answer for these specific errors:\n"
        f"1. Unit errors (e.g. using m/s^2 instead of m/s, or N instead of J)\n"
        f"2. Sign errors (e.g. forgetting to flip inequality when dividing by negative)\n"
        f"3. Arithmetic errors\n"
        f"4. Whether the problem is actually solvable\n\n"
        f"Is your answer correct? If you find an error, state what the error is. "
        f"If the problem is unsolvable, say so.\n"
        f"Answer: CORRECT / ERROR (explain) / UNSOLVABLE (explain)"
    )
    t0 = time.time()
    call_id = len(_GLOBAL_LOG) + 1
    resp = _api_call([{"role": "user", "content": judge_prompt}], max_tokens=1000, temperature=0.2)
    elapsed = round(time.time() - t0, 2)
    ok = not resp.startswith("[")
    _log(call_id, session_id, "self_judge", judge_prompt, resp, elapsed, ok)
    return resp


def generate_with_steps(prompt, session_id, max_new_tokens=1000, temperature=0.7):
    resp = generate_response(prompt, session_id, max_new_tokens, temperature)
    steps = _parse_cot_steps(resp)
    return {"response": resp, "steps": steps}


def _parse_cot_steps(response: str) -> list[dict]:
    if not response or not response.strip():
        return []
    import re
    lines = response.strip().splitlines()
    steps = []
    current = []
    step_num = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                step_num += 1
                steps.append({"step_number": step_num, "raw_text": " ".join(current).strip()})
                current = []
            continue
        m = re.match(r"^(?:Step\s+)?(\d+)[\.\)\:]\s*(.*)", stripped, re.I)
        if m and current:
            step_num += 1
            steps.append({"step_number": step_num, "raw_text": " ".join(current).strip()})
            current = [m.group(2)]
        elif m:
            current = [m.group(2)]
        else:
            current.append(stripped)
    if current:
        step_num += 1
        steps.append({"step_number": step_num, "raw_text": " ".join(current).strip()})
    return steps if steps else [{"step_number": 1, "raw_text": response.strip()[:200]}]


def _log(call_id, session_id, call_type, prompt, response, elapsed, success):
    _GLOBAL_LOG.append({
        "callId": call_id,
        "sessionId": session_id[:8],
        "type": call_type,
        "time": time.strftime("%H:%M:%S"),
        "model": _MODEL_ID,
        "prompt": prompt[:120].replace("\n", " ") + ("..." if len(prompt) > 120 else ""),
        "response": response[:500] + ("..." if len(response) > 500 else ""),
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
    return {
        "modelId": _MODEL_ID,
        "backend": "HF Inference API (router.huggingface.co)",
        "tokenPresent": bool(_TOKEN),
        "totalCalls": len(_GLOBAL_LOG),
        "generateCalls": sum(1 for e in _GLOBAL_LOG if e.get("type") == "generate"),
        "selfJudgeCalls": sum(1 for e in _GLOBAL_LOG if e.get("type") == "self_judge"),
    }
