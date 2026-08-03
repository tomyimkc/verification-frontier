#!/usr/bin/env python3
"""HF Inference API runner — multi-model support.

Calls multiple LLMs in parallel via HF router. No local model loading.
"""
from __future__ import annotations
import os, time, logging, requests
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
_TOKEN = os.environ.get("HF_TOKEN", "")
_MAX_LOG = 100
_GLOBAL_LOG: list[dict] = []

AVAILABLE_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "deepseek-ai/DeepSeek-V3",
    "meta-llama/Llama-3.1-8B-Instruct",
]

DEFAULT_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
]


def _api_call(model: str, messages: list[dict], max_tokens: int = 400, temperature: float = 0.7) -> str:
    try:
        resp = requests.post(_ROUTER_URL, headers={"Authorization": f"Bearer {_TOKEN}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        return f"[API {resp.status_code}: {resp.text[:80]}]"
    except Exception as e:
        return f"[error: {e}]"


def generate_multi(prompt: str, models: list[str] = None, session_id: str = "unknown",
                   temperature: float = 0.7) -> dict:
    """Call multiple models in parallel. Returns {model_id: response}."""
    models = models or DEFAULT_MODELS
    results = {}

    def _call_one(model):
        t0 = time.time()
        resp = _api_call(model, [{"role": "user", "content": prompt}], temperature=temperature)
        elapsed = round(time.time() - t0, 2)
        call_id = len(_GLOBAL_LOG) + 1
        _GLOBAL_LOG.append({
            "callId": call_id, "sessionId": session_id[:8], "type": "generate",
            "model": model, "time": time.strftime("%H:%M:%S"),
            "prompt": prompt[:100].replace("\n", " "),
            "response": resp[:500], "respLen": len(resp), "sec": elapsed,
            "ok": not resp.startswith("["),
        })
        if len(_GLOBAL_LOG) > _MAX_LOG:
            _GLOBAL_LOG.pop(0)
        return model, resp, elapsed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_call_one, m) for m in models]
        for f in futures:
            model, resp, elapsed = f.result()
            results[model] = {"response": resp, "elapsed": elapsed, "model": model}
    return results


def self_judge_single(model: str, prompt: str, response: str, session_id: str = "unknown") -> str:
    judge_prompt = (
        f"You are checking work for errors.\n\nQuestion:\n{prompt}\n\nAnswer:\n{response}\n\n"
        f"Check for: 1) unit errors 2) sign errors 3) arithmetic errors 4) is the problem solvable?\n"
        f"Answer: CORRECT / ERROR (explain) / UNSOLVABLE (explain)"
    )
    t0 = time.time()
    resp = _api_call(model, [{"role": "user", "content": judge_prompt}], max_tokens=300, temperature=0.2)
    elapsed = round(time.time() - t0, 2)
    _GLOBAL_LOG.append({
        "callId": len(_GLOBAL_LOG) + 1, "sessionId": session_id[:8], "type": "self_judge",
        "model": model, "time": time.strftime("%H:%M:%S"),
        "prompt": judge_prompt[:100], "response": resp[:300], "respLen": len(resp),
        "sec": elapsed, "ok": not resp.startswith("["),
    })
    if len(_GLOBAL_LOG) > _MAX_LOG:
        _GLOBAL_LOG.pop(0)
    return resp


def get_session_log(session_id: str) -> list:
    sid = session_id[:8] if session_id else "unknown"
    return [e for e in _GLOBAL_LOG if e.get("sessionId") == sid]


def get_global_log(limit: int = 20) -> list:
    return list(_GLOBAL_LOG[-limit:])


def model_status() -> dict:
    return {
        "models": DEFAULT_MODELS,
        "backend": "HF Inference API (parallel)",
        "tokenPresent": bool(_TOKEN),
        "totalCalls": len(_GLOBAL_LOG),
    }
