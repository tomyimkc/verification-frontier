---
title: 验证边界 Verification Frontier
emoji: 🛡️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "5.49.0"
app_file: app.py
pinned: true
license: apache-2.0
short_description: "安全扩展科学 Agent 的验证边界 (GOAI 2026 AI for Research)"
---

# 验证边界 · Verification Frontier

**安全扩展科学 Agent 的验证边界 / Safely Expanding the Verification Frontier of Scientific Agents**

GOAI 2026 AI for Research · Open Exploration — 公开免登录演示 / public no-login demo.

本 Space 运行确定性的验证环境（来自
[verification-frontier](https://github.com/tomyimkc/verification-frontier) 仓库）。
This Space runs the deterministic verification environment from the
[verification-frontier](https://github.com/tomyimkc/verification-frontier) repository.

### 网络与模型调用 / Network and model calls

| 部分 / Part | 网络 / Network |
|---|---|
| 确定性验证器（SI、SymPy、病态检测、步骤验证）<br>Deterministic verifiers (SI, SymPy, ill-posedness, step-check) | **无 / none** — 纯本地计算 / pure local computation |
| 多模型 / 自定义 / 自检标签页<br>Multi-Model / Custom / Self-Judge tabs | **有 / yes** — 通过 HF Inference API 实时调用所选 LLM<br>live calls to the selected LLMs via the HF Inference API |
| 手动标签页 / Manual tab | **无 / none** — 完全离线 / fully offline |

> 早期版本的本页声称"零网络调用，零模型调用"。自加入多模型对比后这一说法已不成立，现已更正。
> An earlier version of this page claimed "zero network calls, zero model calls".
> That stopped being true when multi-model comparison was added; it is corrected here.
> **裁决始终由确定性验证器作出，模型从不参与判定。**
> **Verdicts are always produced by the deterministic verifiers; no model is in the adjudication path.**

## 声明边界 / Claim ceiling

```json
{"candidateOnly": true, "canClaimAGI": false, "winnerLevelEligible": false, "winnerLevelGateMet": false}
```

这是一个**环境/工具演示**，不是确认性结果、能力声明、验证器扩展或竞赛成绩。
This is an **environment/instrument demo**, not a confirmatory result, capability
claim, verifier extension, or contest score.
