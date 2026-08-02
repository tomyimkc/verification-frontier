# Research position: ill-posedness recognition as the missing third state

> **Scope.** This note states the open problem this submission engages, our
> contribution relative to the 2025–2026 literature, the handbook criteria it
> maps to, and — most importantly — what we do **not** claim. Every empirical
> number below is bound to a committed, hash-checked artifact in
> [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md). Unsupported
> claims are removed, not softened.
>
> 🌐 简体中文：[`zh/研究定位.md`](zh/研究定位.md)
>
> **Companion documents:**
> [`EXECUTIVE-SUMMARY.md`](EXECUTIVE-SUMMARY.md) (one-page entry),
> [`FAILURE-SHOWCASE.md`](FAILURE-SHOWCASE.md) §"Ill-posedness recognition",
> [`RELATED-WORK.md`](RELATED-WORK.md) (claim-safe prior-work comparison).

---

## 1. The open problem (with citations)

A growing 2025–2026 literature converges on one finding: **LLMs do not
recognize ill-posed / unsolvable problems.** Confronted with a problem that has
no well-defined answer, today's models attempt to solve it and emit a confident
answer rather than flag it. The state space they operate in has only two
states — *answer* or *refuse* — and neither is "this problem is ill-posed."

1. **"LLMs Fail to Recognize Mathematical Unsolvability"** (Bai et al.,
   OpenReview / ICLR 2026 submission `Urs8lNvMXB`, 2025). Introduces the
   **MathTrap300** benchmark of unsolvable math problems and shows most LLMs
   exhibit an accuracy drop *and still attempt* the problems instead of
   flagging them as unsolvable. The failure mode is hallucinating a solution,
   not abstaining.

2. **"Aligning LLMs to Detect Unsolvable Problems"** (Peng et al.,
   arXiv:2512.01661, Dec 2025; the *Learning the Boundary of Solvability* line).
   Argues that **current alignment focuses on refusing hard-but-solvable
   problems, not on detecting truly unsolvable ones**, and that LLMs conflate
   the solvability dimension with the reasoning dimension. Their alignment
   method raises unsolvability detection to >85%, establishing both that the
   gap is real and that it is an *open* target.

3. **"The Illusion of Thinking"** (Shojaee, Mirzadeh et al., Apple Machine
   Learning Research, 2025). Shows reasoning models hit a complexity ceiling
   and — germane to us — **do not recognize unsolvability**: their reasoning
   effort does not gate into "this cannot be solved," it just degrades.

4. **"Open Problems Solved by LLMs?"** (Tzachristas, *Big Picture v2* workshop,
   ACL Anthology `2026.bigpicture-main.2`, 2026). Proposes an **evidence
   ladder** for interpreting "LLM solved an open problem" claims, precisely
   because such claims are routinely made on ill-posed or unverifiable tasks.

The shared diagnosis: LLMs lack a *recognition* mechanism for ill-posedness.
They can be told to refuse; they cannot, on their own authority, certify "this
problem is contradictory / underspecified / out of domain."

## 2. Our contribution: the `abstain` verdict *is* the missing third state

This submission's verification-frontier methodology exposes **three** verdicts
at every step, not two:

1. **accepted** — an executable check *establishes* the candidate;
2. **rejected** — an executable check *refutes* it (a logic error is caught); and
3. **abstain** — *no applicable executable check can decide*, which is reported
   as an explicit, typed abstention rather than a silent pass.

The `abstain` verdict is the missing third state the literature calls for. But
we go one step further: the recognition of ill-posedness is **not** delegated to
the LLM's judgment. A **deterministic ill-posedness detector** — SI
dimension+value, SymPy equivalence, Lean proof-placeholder — catches what LLMs
miss, mechanically and fail-closed, *before* any coverage abstention is recorded.
A dimension mismatch (`9.8 m/s²` offered where `9.8 m/s` was meant), a
non-equivalent expression (`(x−1)²` for `(x+1)²`), or a smuggled `sorry`/`admit`
Lean placeholder are each *recognized as ill-posed* by a deterministic check,
not by the model.

> The contribution is **not** a new model capability for recognizing
> unsolvability. It is a deterministic detector for specific ill-posedness
> categories, exposed as an explicit third verdict behind a fail-closed,
> content-addressed, human-gated receipt protocol.

## 3. Mapping to the handbook criteria

| Weight | Official criterion | How this position engages it |
|---:|---|---|
| **45 %** | problem definition + environment-design quality | "LLMs cannot recognize unsolvability" is **genuinely unsolved** (four 2025–2026 citations) and **real** (MathTrap300 documents the failure mode at scale). Our environment makes recognition an explicit three-state verdict rather than a hidden assumption. |
| **35 %** | exploration process and research signal | The **catch-rate + baseline comparison IS the signal**. The deterministic detector catches planted ill-posedness at a measured rate, and the proposed-system policy dominates every baseline on the unsafe-acceptance axis. See §5. |
| **20 %** | verifiability and extensibility | The detector is **deterministic, CPU-only, and reproducible** — `./run_all.sh`, no GPU. Two consecutive bundle builds are byte-identical; every claim is hash-bound. |

## 4. What we do **not** claim (read this carefully)

This is the boundary between our claim and the literature's open problem. We do
**not** claim:

- to have **solved** unsolvability recognition in general. We have built a
  deterministic detector for **specific ill-posedness categories** (SI
  dimension/value/sign, symbolic non-equivalence, Lean proof-placeholder). Many
  categories of ill-posedness remain outside deterministic reach and are
  honestly reported as `abstain`.
- a **model-capability result.** The catch-rate is a property of the
  *deterministic verifiers*, not of any model. It is **instrument evidence**
  that the detectors are real and fail-closed — not evidence that Qwen2.5-7B (or
  any model) has learned to recognize unsolvability.
- that the `abstain` verdict is **calibrated model uncertainty.** It is an
  *environment-designed* coverage boundary. The model never certifies its own
  abstention; the deterministic verifier decides.
- **capability uplift, contest performance, winner eligibility, scientific
  outcome, AGI/ASI, or confirmatory power.** Each is false/absent and the gates
  enforce it (see [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md) §E).

Per Tzachristas (2026), we place ourselves on a **low rung of the evidence
ladder by design**: deterministic-instrument evidence for a focused detector,
not an "LLM solved unsolvability" claim.

## 5. The evidence (all development-only)

Every row is reproducible from the package root with no GPU and no network.

| Evidence | Result | Artifact / verify | What it proves |
|---|---|---|---|
| **Logic-error catch-rate** (strongest) | **67 planted logic errors, 67/67 caught = 100 % catch-rate**, 0 misses. By tier: SI 30/30, SymPy 26/26, Lean-placeholder 11/11. | `v2/artifacts/logic-error-catch-rate.json` (`eaa5d302…`); `python3 v2/build_logic_error_audit.py --check` | the deterministic detectors are real and fail-closed across every tier |
| **Baseline comparison** (the signal) | proposed-system: errorCatchRate **1.0**, unsafeAcceptances **0**, coverage 0.1566. `raw-model` & `always-accept`: errorCatchRate **0.0**, **67 unsafe acceptances** each. `always-abstain`: coverage **0.0**. proposed-system **dominates** all three baselines on the unsafe-acceptance axis. | `v2/artifacts/baseline-comparison.json`; `python3 v2/build_baseline_comparison.py --check` | the verifier policy is not a sampling artifact — every degenerate baseline fails a distinct axis (zero coverage, or 67 unsafe acceptances) |
| **Self-correction ratchet** | errorReductionRate **0.8358**, rejectionClearedRate **1.0**, `canSelfAccept: false`, final acceptance authority = **deterministic-verifier**. | `v2/artifacts/self-correction-audit.json`; `python3 -c "from v2.self_correct import write_audit; write_audit()"` | the model may *revise* a caught error, but can **never confirm** a step on its own authority — the verifier re-runs and decides |
| **RAG novel-error proposal** | 5 novel errors surfaced; 4 `would_catch_if_implemented`; all proposals `approvalStatus: pending` (candidate-only, advisory). Retrieval is stdlib keyword Jaccard — **no embeddings**. | `v2/artifacts/error-rag-audit.json`; `python3 -c "from v2.error_rag import run_error_rag_audit; run_error_rag_audit()"` | the frontier can be *proposed* to grow, but every new rule is pending human approval and issues **no verdict** |

These four artifacts are the through-line: detect (catch-rate), compare against
degenerate alternatives (baseline), let the model revise but not self-approve
(ratchet), and propose-but-don't-apply new coverage (RAG). Together they
operationalize "recognize ill-posedness and abstain" as a deterministic,
human-gated loop.

## 6. Position in one sentence

Where the 2025–2026 literature shows LLMs hallucinate answers to ill-posed
problems, this submission supplies the **missing third state** — a deterministic,
fail-closed `abstain` — as instrument evidence, not a capability claim, scoped to
specific ill-posedness categories and grown only through human-gated proposals.

```json
{
  "candidateOnly": true,
  "canClaimAGI": false,
  "winnerLevelEligible": false,
  "scientificOutcome": false,
  "capabilityClaim": false
}
```

`candidateOnly:true`; `canClaimAGI:false`.
