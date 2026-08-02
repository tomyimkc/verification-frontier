<div align="center">

# 验证边界 · Verification Frontier

**安全扩展科学 Agent 的验证边界**<br/>
**Safely Expanding the Verification Frontier of Scientific Agents**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![GOAI 2026](https://img.shields.io/badge/GOAI%2026-AI%20for%20Research-green.svg)](OFFICIAL-RULES-CHECK.md)
[![Tests](https://img.shields.io/badge/tests-200%20deterministic-success-brightgreen.svg)](REPRODUCIBILITY-QUICKSTART.md)
[![candidateOnly](https://img.shields.io/badge/claim-candidateOnly%3Atrue-lightgrey.svg)](EVIDENCE-TO-CLAIM-MATRIX.md)

**GOAI 2026 全球开源 AI 挑战赛 · 前沿探索 / AI for Research — Open Exploration**

**作品 / Project:** 验证边界 / Verification Frontier
**团队 / Team:** 严建正 (Yim Kin Cheong, Tom) · 独立研究者 · 香港 / Independent Researcher · Hong Kong
**许可 / License:** Apache-2.0

**🌐 Demo:** https://tomyimkc-sophia-agi.hf.space · **📦 附件 ZIP:** `dist/GOAI-AI4R-Open-Exploration.zip`

</div>

---

## 中文（简体）

### 一句话问题

> 科学 Agent 在每一步都必须区分三种状态：可执行检查**确立**候选（accepted）、**反驳**候选（rejected）、或**无适用可执行检查**（abstain）。把第三种状态当作"未发现错误"会造成**静默放行**。
>
> **核心研究问题：** 在密封迁移任务上，由模型提出、人类批准的验证器扩展，能否**安全**地扩大一个冻结科学验证栈的可执行覆盖范围？（安全前沿配对准确率 SFPA）

### 一分钟看懂

- **问题：** 静态验证器有固定的覆盖边界。当 Agent 遇到边界外的命题时，"没有错误"≠"已通过验证"——否则就是静默放行。
- **机制：** 三态验证器（accepted/rejected/abstain）+ 类型化弃权分类 + 有界补丁类 + 内容寻址证据 DAG + 人类与独立专家 AI 双重审批门。
- **最强诚实证据（开发阶段）：** 在 Pro6000 Blackwell 上用 Qwen2.5-7B 对 24 个公开开发族（物理 8 / 符号 8 / Lean 8）执行唯一一次授权开发运行——**23/24 结构化输出有效，1 条格式错误的 Lean 响应被原样保留，2/2 开放控制保持为不可晋升的弃权，七类策略违规计数全部为零。**
- **这不是：** 验证器扩展、科学发现、能力提升、竞赛成绩、获奖资格、AGI 或 ASI 证据。

### 声明边界（冻结，不可放宽）

```json
{"candidateOnly": true, "canClaimAGI": false, "winnerLevelEligible": false, "winnerLevelGateMet": false}
```

同时固定 `scientificOutcome:false`、`capabilityClaim:false`、`confirmatoryEligible:false`、`activationAuthorized:false`。

### 评委快速入口（两步内可找到）

| 想看什么 | 去哪里看 |
|---|---|
| 一页摘要（双语） | [`执行摘要 / EXECUTIVE-SUMMARY.md`](EXECUTIVE-SUMMARY.md) |
| 评审标准对照（45/35/20） | [`评审对照 / JUDGING-CROSSWALK.md`](JUDGING-CROSSWALK.md) |
| 架构与信任边界图 | [`架构 / ARCHITECTURE.md`](ARCHITECTURE.md) |
| 每条声明 → 哈希绑定工件 | [`证据矩阵 / EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md) |
| 失败如何作为完整性证据 | [`失败展示 / FAILURE-SHOWCASE.md`](FAILURE-SHOWCASE.md) |
| 两分钟 CPU 复现 | [`复现指南 / REPRODUCIBILITY-QUICKSTART.md`](REPRODUCIBILITY-QUICKSTART.md) |
| 完整提交叙述与披露 | [`PROJECT.md`](PROJECT.md)（[中文摘要见执行摘要](EXECUTIVE-SUMMARY.md#中文摘要)） |
| 真实 Stage A 23/24 结果工件 | [`v2/artifacts/stage-a-development-result.json`](v2/artifacts/stage-a-development-result.json) |

### 两分钟复现（无需 GPU / 无网络 / 无登录）

```bash
python3 demo.py --selfcheck                  # 验证器、覆盖、回合契约
python3 v2/stage_a.py --check                # 24 家族计划（8/8/8）
python3 v2/build_stage_a_result.py --check   # 真实 23/24 结果绑定
python3 verify_bundle.py                     # 确定性 ZIP 完整性 + 声明边界
```

或一键全量：`./run_all.sh`（200 个确定性测试 + 构建 + 校验）。

---

## English

### The problem in one sentence

> A scientific agent must distinguish three states at every step: an executable check **establishes** a candidate (accepted), **refutes** it (rejected), or **no applicable executable check can decide** (abstain). Treating case three as "no error found" is a **silent pass**.
>
> **Research question:** Can model-proposed, human-approved verifier extensions **safely** increase the executable coverage of a frozen scientific verification stack on sealed transfer tasks? (Safe Frontier-Pair Accuracy, SFPA)

### What it is — and is not

The contribution is **not** dimensional analysis, SymPy, Lean, RLVR, abstention, or the frontier concept. It is their **operational integration** behind a fail-closed, content-addressed, human-gated receipt protocol. The strongest honest evidence (a real 23/24 development run) is disclosed immutably; every unmet gate is listed.

### Claim ceiling (frozen)

```json
{"candidateOnly": true, "canClaimAGI": false, "winnerLevelEligible": false, "winnerLevelGateMet": false}
```

### Reproduce in two minutes (no GPU, no network, no login)

```bash
./run_all.sh    # 200 deterministic tests + deterministic ZIP build + validation
```

---

<div align="center">

**结论 / Recommendation:** 确认性执行 NO-GO；作为初步基础设施提案 CONDITIONAL GO。
诚实的开发结果优于无法支撑的获奖声明。 A polished honest development result is preferable to an unsupported winner claim.

</div>

---

## 目录结构 / Repository map

| 路径 / Path | 内容 / Contents |
|---|---|
| `EXECUTIVE-SUMMARY.md` | 一页双语评委入口 / one-page bilingual judge entry |
| `JUDGING-CROSSWALK.md` | 评审标准对照 / criteria → where addressed |
| `ARCHITECTURE.md` | 架构图 + 信任边界 / architecture + trust boundary |
| `EVIDENCE-TO-CLAIM-MATRIX.md` | 声明→工件证据矩阵 / claim → hash-bound artifact |
| `FAILURE-SHOWCASE.md` | 失败展示 / retained failures as integrity evidence |
| `REPRODUCIBILITY-QUICKSTART.md` | 复现指南 / CPU-only verify in ≈2 min |
| `OFFICIAL-RULES-CHECK.md` | 赛事规则核验 / verified contest contract |
| `PROJECT.md` | 完整叙述与披露 / full narrative + disclosure |
| `README-TECHNICAL.md` | 技术说明 / technical README (runnable details) |
| `submission/` | 双语四页 PDF + 源文件 / bilingual 4-page PDFs + sources |
| `hosted-demo/` | 免登录 Gradio 演示 / no-login Gradio demo |
| `v2/` | 预注册、Stage A 计划、真实结果、协议孪生、统计 / preregistration, Stage A, real result, protocol twin, stats |
| `dist/` | 确定性上传 ZIP + SHA-256 / deterministic upload ZIP |

---

<div align="center">

<sub>本仓库不包含任何密钥、私有任务、确认性测评题或 Stage B 私有材料。
This repository contains no secrets, private tasks, confirmatory eval items, or private Stage B material.</sub>

</div>
