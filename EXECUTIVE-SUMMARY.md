> 🌐 简体中文 / Simplified Chinese: [`zh/执行摘要.md`](执行摘要.md)

# Executive summary / 执行摘要

> **One page for judges.** This is the fastest entry point. Everything claimed
> here is traceable to a committed, hash-bound artifact in
> [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md).
>
> **Track:** GOAI 2026 前沿探索 / AI for Research — Open Exploration
> **Title (EN):** Safely Expanding the Verification Frontier of Scientific Agents
> **Title (中文):** 安全扩展科学 Agent 的验证边界
> **Team:** Yim Kin Cheong (Tom), Independent Researcher, Hong Kong · Apache-2.0
> **Preliminary deadline:** 2026-08-16 (still open as of 2026-08-02)

---

## The problem (under one minute)

A scientific agent that uses a verifier (a unit check, a symbolic equivalence
test, or a Lean kernel proof) must distinguish three states at every step:

1. **accepted** — an executable check *establishes* the candidate;
2. **rejected** — an executable check *refutes* it; and
3. **abstain** — *no applicable executable check can decide*.

The dangerous failure mode is treating case 3 as "no error found" — a **silent
pass**. Merely abstaining, however, leaves science stuck: coverage never grows.
So the research question is:

> **Can model-proposed, human-approved verifier extensions increase the safe
> executable coverage of a frozen scientific verification stack on sealed
> transfer tasks? — Safe Frontier-Pair Accuracy (SFPA).**

The contribution is **not** dimensional analysis, SymPy, Lean, RLVR, abstention,
or the frontier concept. It is their **operational integration** behind a
fail-closed, content-addressed, human-gated receipt protocol.

## Why it matters

Static verifiers have a fixed coverage boundary. If an agent cannot grow that
boundary *safely* — without accepting a wrong answer, smuggling a gold label,
or self-approving its own extension — then every uncovered case is either a
silent pass or a dead end. This project makes the boundary an **explicit
environment state** and measures, with preregistered matched pairs, whether it
can move without regressions.

## Strongest honest evidence (all development-only)

| Evidence | Result | What it proves | What it does *not* prove |
|---|---|---|---|
| Real Stage A run (Pro6000, Qwen2.5-7B) | **24 families, 8/8/8; 23/24 structured-output valid; 1 retained malformed Lean response; 2/2 open controls preserved; all 7 policy-violation totals zero** | structured-output + strict-schema + policy-boundary compliance on frozen public families | verifier extension, capability, discovery, frontier expansion, contest score |
| Public task manifest | **150 rows, 150/150 strict validation** (incl. 48 Lean) | the development instrument and gold contracts are executable | model capability |
| Receipt protocol | **3 chains / 34 receipts / 60 blobs; 7/7 adversarial cases** | content-addressed, fail-closed evidence integrity | a scientific outcome |
| CPU-only Protocol Twin | **B0–B6, 8 ablations, 13 variants, 2,160 deterministic cells; 0 model/network calls** | the confirmatory protocol shape runs and fails-closed correctly | an efficacy experiment |
| Development Study Root v3 | **756 arm + 108 B6 + 1,404 ablation rows; 24 valid DAG variants; 164 invalid mutations rejected; 24,000 scorer simulations** | protocol mechanics bind end-to-end | confirmatory power / MDE |
| Synthetic rehearsal | 144/144 (48 Lean) | construction is internally consistent | confirmatory result — explicitly `confirmatoryEligible:false` (15 families, known leakage) |

## The exact claim ceiling (frozen — do not relax)

```json
{
  "candidateOnly": true,
  "canClaimAGI": false,
  "winnerLevelEligible": false,
  "winnerLevelGateMet": false,
  "scientificOutcome": false,
  "capabilityClaim": false,
  "confirmatoryEligible": false,
  "activationAuthorized": false
}
```

**Recommendation:** NO-GO for confirmatory execution; CONDITIONAL GO for a
preliminary infrastructure proposal. A polished honest development result is
preferable to an unsupported winner claim.

## What remains unproven (the real blocker list)

- owner review of the 23 valid Stage A proposals;
- qualifying blinded independent expert-AI review (the author has seen aggregate outcomes — cannot self-count);
- execution of visible tests; any approved verifier extension;
- private provenance-bound Stage B packs; real B0–B6 and ablation outcomes;
- full-resample power/MDE near the decision boundary; protected-suite + rollback;
- OS-level Lean isolation; clean-Linux reproduction; scientific-domain expert review;
- external submission.

## Reproduce in under two minutes (no GPU)

```bash
./run_all.sh                                   # 188+ deterministic tests + build + validate
python3 v2/stage_a.py --check                  # 24-family programme
python3 v2/build_stage_a_result.py --check     # the real 23/24 result binding
python3 verify_bundle.py                       # deterministic ZIP integrity
```

---

## 中文摘要

**研究问题：** 科学 Agent 在每一步都必须区分三种状态——可执行检查**确立**候选
（accepted）、**反驳**候选（rejected）、或**无适用可执行检查**（abstain）。把第三种
状态当作"未发现错误"会造成**静默放行**。本项目的核心问题是：

> **在密封迁移任务上，由模型提出、人类批准的验证器扩展，能否安全地扩大一个冻结科学
> 验证栈的可执行覆盖范围？**（安全前沿配对准确率 SFPA）

**最强证据（均为开发阶段，非确认性结果）：** 在 Pro6000 Blackwell 上用
Qwen2.5-7B 对 24 个公开开发族（物理 8 / 符号 8 / Lean 8）进行唯一一次授权开发运行：
23/24 结构化输出有效，**1 条格式错误的 Lean 响应被原样保留**，2/2 开放控制保持为
不可晋升的弃权，七类策略违规计数全部为零。此外有 150/150 任务校验、3 链 34 凭证 60
证据块的收据协议（7/7 对抗用例通过）、以及 2,160 个确定性单元的 CPU 协议孪生。

**这仅是结构化输出与策略合规证据，不是验证器扩展、科学发现、能力提升、竞赛成绩、
获奖资格、AGI 或 ASI 证据。**

**声明边界（冻结，不可放宽）：** `candidateOnly:true`、`canClaimAGI:false`、
`winnerLevelEligible:false`、`winnerLevelGateMet:false`；同时 `scientificOutcome:false`、
`capabilityClaim:false`、`confirmatoryEligible:false`、`activationAuthorized:false`。

**结论：** 确认性执行 NO-GO；作为初步基础设施提案 CONDITIONAL GO。诚实的开发结果优于
无法支撑的获奖声明。每条声明均可在 [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md)
中追溯到带哈希绑定的提交工件。
