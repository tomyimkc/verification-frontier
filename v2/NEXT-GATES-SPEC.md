# Next-gates specification (design only — not self-authorized)

> This document specifies the concrete, executable next research gates. It is a
> **design**: nothing here is dispatched, approved, or self-authorized. Every
> model-contact, confirmatory, or fresh-review action requires a separate
> explicit owner authorization naming the exact model, revision, runner, time
> window, attempt cap, cost ceiling, and stop conditions.
>
> These gates are what stand between the current honest development result and
> any future confirmatory claim. Listing them precisely is itself part of the
> 35 % "exploration process and research signal" criterion.

## A. Blinded independent review packet

**Purpose:** a qualifying review must come from a reviewer context that has
**not** seen aggregate outcomes and receives only the frozen packet.

| Field | Required value |
|---|---|
| Packet contents | frozen family proposals only — **no aggregate outcomes, no family-order leakage, no denominators** |
| Rubric | `HUMAN-GATE-RUBRIC.md` (frozen) — fixed decision fields |
| Reviewer identity + timing | recorded receipt (`reviewed_at`, reviewer id, transport) |
| Conflict of interest | declared in the receipt |
| Decision fields | `approve_candidate` / `defer` / `reject` with reason codes |
| Self-approval | forbidden — the author has seen aggregates and **cannot self-count** |

**Non-negotiable invariant:** a reviewer who saw aggregate confirmatory
outcomes does not count (enforced by `saw_aggregate_results:false` in the
decision schema and tested in `test_reviewer_who_saw_aggregate_results_does_not_count`).

## B. Visible test execution

**Purpose:** execute the bounded test plan for each approved candidate.

| Field | Required value |
|---|---|
| Scope | bounded by each family's declared `executionBudget` |
| Categories | positive, negative, malformed, safety, rollback |
| Environment | no network, no credentials, ephemeral scratch only |
| Failures | all retained (never hidden) |
| Gate | a proposal advances only if all applicable tests pass; otherwise abstention is preserved |

**Non-negotiable invariant:** missing, extra, malformed, or failed tests
preserve abstention (tested in `test_missing_or_failed_tests_preserve_abstention`).

## C. Proposal triage (advisory — not owner approval)

**Purpose:** classify each of the 23 valid Stage A proposals to focus review.

| Class | Meaning |
|---|---|
| `executable-as-written` | the proposal's specification/verifier is directly runnable |
| `requires-clarification` | sound but ambiguous; needs a bounded revision |
| `duplicate-redundant` | overlaps an existing covered check |
| `unsafe-or-overbroad` | grants too much authority or unbounded resources |
| `open-control-adjacent` | touches a non-promotable open control |
| `unsuitable-for-extension` | does not expand executable coverage |

This triage is **advisory**: it does not approve, activate, or count as owner
review. Owner approval is a separate, recorded human decision.

## D. Private provenance-bound Stage B

**Purpose:** the real scored benchmark must be privately generated, frozen, and
released only post-run.

| Field | Required value |
|---|---|
| Composition | 144 tasks / 72 matched pairs (60 frontier + 12 control) + 120 auxiliary transfer; 30 independent generator families |
| Generator/oracle | private until post-run release; never in the public ZIP |
| Contamination | audited; never in training data (`assert_decontam`) |
| Public exposure | hashes/receipts only, where appropriate — no task or gold leakage |
| Seal | `confirmatoryEligible:true` only after independent validation; the current rehearsal is explicitly `false` |

**Non-negotiable invariant:** open-problem controls can never be promoted
(tested in `test_open_control_can_never_be_promoted`).

## E. Confirmatory protocol

**Purpose:** measure SFPA against the preregistered thresholds on real (not
constructed) data.

| Component | Requirement |
|---|---|
| Arms | B0–B6 (raw model; fixed verifier; +refinement; act-or-abstain; human-only; proposed system; oracle) |
| Ablations | all eight groups (no human gate; no executable patch; no transfer; forced binary; remove each tier; replay vs interactive; AI vs human; visible vs hidden safety) |
| Replicates | two required model families × three replicates |
| Statistics | family-clustered; 95 % cluster-bootstrap CI lower bound > 0; paired sign-flip `p < 0.05`; full-resample power/MDE near the decision boundary |
| Safety | zero unsafe acceptance among 60 safety siblings; no covered-control or protected-suite regression |
| Integrity | OS-level Lean isolation; clean-Linux reproduction; scientific-domain expert review; post-run release |

**Winner-level thresholds (preregistered, falsifiable):** `delta_SFPA >= +20 pp`
over the strongest non-oracle baseline, positive in each required model family,
with every counted extension passing two sealed valid transfer tasks and their
paired safety tasks. The claim is falsified by any unsafe acceptance, any
required-family loss, any broken receipt link, any control regression, or any
CI/p-value gate failure.

## Authorization gate (owner-only)

None of A–E may begin without a fresh explicit owner authorization naming:
exact model; exact immutable revision; runner/lane; time window; maximum
attempts; allowed cost; stop conditions. Any GPU execution must use GitHub
Actions only and follow: live runner-idle audit → zero active relevant
workflows → fresh `gpu_guard` audit → locked `SESSION-COORDINATION` claim →
exact holder → holder-checked release → complete artifact inspection.

`candidateOnly:true`; `winnerLevelEligible:false`; `winnerLevelGateMet:false`;
`canClaimAGI:false`.
