# Executive summary / 执行摘要

> **One page for judges.** This is the fastest entry point. Everything claimed
> here is traceable to a committed, hash-bound artifact in
> [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md).
>
> **Track:** GOAI 2026 前沿探索 / AI for Research — Open Exploration
> **Title (EN):** Safely Catching Logic Errors in LLM Scientific Reasoning: A Deterministic Verification Frontier
> **Title (中文):** 安全捕获 LLM 科学推理中的逻辑错误：确定性验证边界
> **Team:** Yim Kin Cheong (Tom), Independent Researcher, Hong Kong · Apache-2.0
> **Preliminary deadline:** 2026-08-16 (still open as of 2026-08-02)

---

## The problem (under one minute)

An LLM doing scientific reasoning makes logic errors: a dimension mismatch (m/s²
written where m/s was meant), a sign flip (`(x−1)²` for `(x+1)²`), a smuggled
`sorry`/`admit` placeholder in a Lean proof. The central question is:

> **What fraction of an LLM's logic errors in scientific reasoning can a
> deterministic verifier catch, and can that fraction be safely expanded by
> human-gated verifier proposals?**

The deterministic verifiers — SI dimension+value, SymPy equivalence, Lean kernel
— **are** the logic-error detectors. A dimension mismatch *is* a logic error,
caught mechanically. The trust boundary is the line where the LLM's
probabilistic reasoning ends and deterministic logic-error detection begins.

A scientific agent using such a verifier must distinguish three states at every
step:

1. **accepted** — an executable check *establishes* the candidate;
2. **rejected** — an executable check *refutes* it (a logic error is caught);
   and
3. **abstain** — *no applicable executable check can decide*.

The dangerous failure mode is treating case 3 as "no error found" — a **silent
pass**. Merely abstaining, however, leaves coverage stuck: the catchable
fraction never grows. So the second half of the question is the **human-gated
frontier expansion** — the LLM proposes a new check, a human approves it, and
coverage grows without the model self-approving on its own authority. In short:
humans guide the LLM's direction; the LLM never certifies itself.

The contribution is **not** dimensional analysis, SymPy, Lean, RLVR, abstention,
or the frontier concept. It is their **operational integration** behind a
fail-closed, content-addressed, human-gated receipt protocol, with measured
logic-error catch-rate.

## Why it matters

Static verifiers have a fixed logic-error detection boundary. If an agent cannot
grow that boundary *safely* — without accepting a wrong answer, smuggling a gold
label, or self-approving its own extension — then every uncovered case is either
a silent pass or a dead end. This project makes the boundary an **explicit
environment state**, measures the deterministic catch-rate on planted logic
errors, and asks, with preregistered matched pairs, whether the boundary can move
without regressions.

## Strongest honest evidence (all development-only)

| Evidence | Result | What it proves | What it does *not* prove |
|---|---|---|---|
| **Logic-error catch-rate audit (strongest)** | **16 planted logic errors (8 SI dimension+value, 6 SymPy equivalence, 2 Lean proof-placeholder), 16/16 caught = 100% catch-rate** | the deterministic verifiers are real and fail-closed across every tier — when a logic error is present, it is detected | model capability, catch-rate on unseen model errors, frontier expansion, contest score |
| Real Stage A run (Pro6000, Qwen2.5-7B) | **24 families, 8/8/8; 23/24 structured-output valid; 1 retained malformed Lean response; 2/2 open controls preserved; all 7 policy-violation totals zero** | structured-output + strict-schema + policy-boundary compliance on frozen public families — and confirms the verifiers are real | verifier extension, capability, discovery, frontier expansion, contest score |
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
python3 v2/build_logic_error_audit.py --check  # 16/16 logic-error catch-rate (needs sympy)
python3 verify_bundle.py                       # deterministic ZIP integrity
```

---

## 中文摘要

**研究问题：** LLM 在科学推理中会产生逻辑错误——量纲不匹配（把 m/s² 写成 m/s）、
符号翻转（把 `(x+1)²` 写成 `(x−1)²`）、或在 Lean 证明中偷渡 `sorry`/`admit`
占位符。确定性验证器（SI 量纲+数值、SymPy 等价、Lean 内核）**就是**逻辑错误检测器——
量纲不匹配*本身*就是一个逻辑错误，能被机械地捕获。核心问题是：

> **LLM 科学推理中的逻辑错误，有多大比例能被确定性验证器捕获？这个比例能否通过
> 人类把关的验证器提案被安全地扩大？**

人类把关的前沿扩展 = "引导 LLM 的方向"（LLM 提出新检查 → 人类批准 → 覆盖增长）。
信任边界即 LLM 概率推理结束、确定性逻辑错误检测开始的界线。科学 Agent 在每一步都必须
区分三种状态——可执行检查**确立**候选（accepted）、**反驳**候选（rejected，即捕获逻辑
错误）、或**无适用可执行检查**（abstain）。把第三种状态当作"未发现错误"会造成
**静默放行**。

**最强证据（均为开发阶段，非确认性结果）：** 逻辑错误捕获率审计——在全部验证器层
（8 SI 量纲+数值 / 6 SymPy 等价 / 2 Lean 占位符）植入 16 个已知逻辑错误，
**16/16 全部捕获 = 100% 捕获率**。这是验证器"真实且失败即闭"的**仪器证据**，不是模型
能力声明。此外在 Pro6000 Blackwell 上用 Qwen2.5-7B 对 24 个公开开发族（物理 8 / 符号 8 /
Lean 8）进行唯一一次授权开发运行：23/24 结构化输出有效，**1 条格式错误的 Lean 响应被
原样保留**，2/2 开放控制保持为不可晋升的弃权，七类策略违规计数全部为零。另有 150/150
任务校验、3 链 34 凭证 60 证据块的收据协议（7/7 对抗用例通过）、以及 2,160 个确定性
单元的 CPU 协议孪生。

**这仅是仪器（验证器真实）与结构化输出/策略合规证据，不是验证器扩展、科学发现、
能力提升、竞赛成绩、获奖资格、AGI 或 ASI 证据。**

**声明边界（冻结，不可放宽）：** `candidateOnly:true`、`canClaimAGI:false`、
`winnerLevelEligible:false`、`winnerLevelGateMet:false`；同时 `scientificOutcome:false`、
`capabilityClaim:false`、`confirmatoryEligible:false`、`activationAuthorized:false`。

**结论：** 确认性执行 NO-GO；作为初步基础设施提案 CONDITIONAL GO。诚实的开发结果优于
无法支撑的获奖声明。每条声明均可在 [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md)
中追溯到带哈希绑定的提交工件。

`candidateOnly:true`; `canClaimAGI:false`.
