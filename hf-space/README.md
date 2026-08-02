---
title: Verification Frontier
emoji: 🛡️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "5.49.0"
app_file: app.py
pinned: true
license: apache-2.0
short_description: Human-gated scientific verification frontier (GOAI 2026 AI for Research)
---

# Verification Frontier · 验证边界

Public, no-login instrument demo for **GOAI 2026 AI for Research / Open Exploration**:
**Safely Expanding the Verification Frontier of Scientific Agents (安全扩展科学 Agent 的验证边界).**

This Space runs the deterministic, provider-free verification environment from the
[verification-frontier](https://github.com/tomyimkc/verification-frontier) repository.
It exposes public SI verification, symbolic verification, deterministic reference
episodes, a synthetic owner+expert-AI+test gate preview, and the public seal/claim-ceiling
metadata. **It makes zero network calls and zero model calls.**

### Claim ceiling

```json
{"candidateOnly": true, "canClaimAGI": false, "winnerLevelEligible": false, "winnerLevelGateMet": false}
```

This is an **instrument/environment demo**, not a confirmatory result, capability claim,
verifier extension, or contest score.

### Reproduce locally

```bash
pip install gradio sympy
python app.py
```
