#!/usr/bin/env python3
"""Lazy local-model runner for the HF Space demo.

Loads Qwen2.5-0.5B-Instruct on first use (CPU, float32, ~2GB RAM).
Small model = more mistakes = better demo (the verifier has more to catch).
Falls back to curated responses if the model can't load.
"""
from __future__ import annotations

import os
import sys
import logging

logger = logging.getLogger(__name__)

_MODEL = None
_TOKENIZER = None
_LOAD_ATTEMPTED = False
_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

# Curated fallback responses (used if model can't load)
_CURATED = {
    "velocity": "The final velocity is 9.8 m/s^2.",
    "energy": "The kinetic energy is 6 N.",
    "expand_correct": "(x+1)^2 = x^2 + 2x + 1",
    "expand_sign_error": "(x+1)^2 = x^2 - 2x + 1",
    "expand_extra_const": "(x+1)^2 = x^2 + 2x + 2",
    "contradictory": "From x + y = 3 and x + y = 5, we get x = 1, y = 2.",
    "circular": "Since A depends on B and B depends on A, substituting gives A = A, so A = 0.",
}


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
        logger.warning("Model load failed (using curated fallback): %s", e)
        _MODEL = None
        _TOKENIZER = None
    return _MODEL, _TOKENIZER


def generate_response(prompt: str, max_new_tokens: int = 80, temperature: float = 0.3) -> str:
    """Generate a response from the local model. Falls back to curated on failure."""
    model, tok = _load_model()
    if model is None or tok is None:
        return f"[curated fallback — model not loaded]\n{prompt}"

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
        response = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return response.strip()
    except Exception as e:
        return f"[generation error: {e}]"


def model_status() -> dict:
    """Return model loading status for display."""
    model, tok = _load_model()
    return {
        "modelId": _MODEL_ID,
        "loaded": model is not None,
        "params": f"{sum(p.numel() for p in model.parameters()) // 1_000_000}M" if model else "N/A",
        "backend": "local CPU (transformers)",
        "fallback": "curated examples" if model is None else "active",
    }
