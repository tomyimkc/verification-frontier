# Preregistration: transferable verification-frontier expansion

**Frozen on:** July 31, 2026<br/>
**Competition:** GOAI 2026 AI for Research — Open Exploration<br/>
**Status:** prospective confirmatory plan; no v2 model outcomes existed when
this document was frozen<br/>
**Claim ceiling:** `candidateOnly:true`, `canClaimAGI:false`

> **Development engineering amendment — August 1, 2026:** Study Root v3 adds
> descendant transfer-execution receipts, complete constructed B0-B6 and
> ablation manifests, 24 serialization variants of one valid DAG topology,
> 164 invalid deterministic DAG mutations, and 12,000 null + 12,000
> prospective-alternative scorer simulations. These are
> development-only instrument artifacts. They do not alter any confirmatory
> hypothesis, threshold, task count, model condition, or claim ceiling.
>
> **Stage A execution amendment — August 1, 2026:** the public development
> programme is instantiated as exactly 24 families: eight physics, eight
> symbolic-mathematics, and eight Lean families. All 30 public frontier-gap
> tasks are source-hash bound once; the three Lean open-problem controls remain
> non-promotable. A reviewed local-model lane may generate bounded structured
> proposals and deterministic validation receipts, but cannot create reviewer
> approvals, execute or activate an extension, enable confirmatory mode, or
> change any prospective Stage B quantity.

## 1. Research question

Can model-proposed, human-approved verifier extensions increase the safe
executable coverage of a frozen scientific verification stack on sealed
transfer tasks?

An extension counts only if it is reusable beyond the task that triggered it,
passes hidden sibling tests, preserves the protected verifier suite, and does
not increase unsafe acceptance.

This experiment studies verification infrastructure. It does not test whether
a model solved an open scientific problem, and it does not equate verifier
coverage with model knowledge or scientific discovery.

## 2. Two-stage design

### Stage A — extension development

Use 24 public development families, eight each from physics, symbolic
mathematics, and Lean. Development tasks may be used to:

- refine the typed-abstention taxonomy;
- propose and reject candidate specifications or verifier extensions;
- test the human-review rubric;
- establish execution and rollback budgets;
- build visible positive, negative, and fail-closed tests.

The public 150-row task manifest in `v2/artifacts/` is a broad development and
regression stress pack. It is **not** the confirmatory sample and cannot support
the headline effect.

At the end of Stage A, freeze:

- the base verifier commit;
- the approved extension bundle;
- the human-gate rubric;
- allowed patch classes and budgets;
- model identifiers and prompts;
- the confirmatory task seal.

No verifier or prompt changes are permitted after confirmatory outcomes are
viewed.

### Stage B — sealed confirmatory benchmark

The primary scored confirmatory benchmark contains **144 tasks arranged as 72
matched pairs**. A separate unscored auxiliary transfer pack contributes
another **120 tasks / 60 matched pairs**:

| component | families/domain | pairs/family | total pairs | total tasks |
|---|---:|---:|---:|---:|
| frontier valid + safety sibling | 10 | 2 | 60 | 120 |
| auxiliary transfer valid + safety sibling | 10 | 2 | 60 | 120 |
| already-covered valid + safety sibling | 4 | 1 | 12 | 24 |
| **full study corpus** |  |  | **132** | **264** |

Domains:

1. SI and physical reasoning;
2. symbolic mathematics;
3. Lean formal reasoning.

Each frontier pair contains:

- one valid member initially outside the base verifier's executable coverage;
- one minimally perturbed sibling that must remain rejected or abstained.

Two primary frontier pairs share each extension/generator family. Two
additional unscored transfer pairs in the same family provide two valid
transfer tasks and their paired safety tasks; none may be used to construct or
approve an extension. The primary pair remains the SFPA measurement unit, but
uncertainty and hypothesis testing cluster at the **30 independent
extension/generator families**. Models, parameter variants, transfer tasks,
and sampling replicates do not inflate the independent cluster count.

The current `synthetic-rehearsal-*` artifacts are not this benchmark. They have
only 15 families, public structural leakage, seed-independent tasks, and
duplicate prompts. They are retained only to test environment mechanics and
are marked `confirmatoryEligible:false`.

Open conjectures may appear only as safety sentinels. They can never become
accepted outcomes or count toward frontier expansion.

## 3. Prospective hypotheses

### H1 — safe frontier-pair accuracy

The proposed human-gated frontier-expansion system will show evidence of a
positive Safe Frontier-Pair Accuracy effect, with an **observed point estimate
of at least 20 percentage points** relative to the strongest non-oracle
baseline.

The confidence interval tests positivity (`lower bound > 0`); it does not
establish that the population effect itself is at least 20 percentage points.

For a pair to count as successful:

1. the valid member is correctly machine-decided;
2. its paired trap is rejected or abstained;
3. the responsible extension passes hidden transfer and regression obligations.

### H2 — safety

The proposed system will produce **zero unsafe acceptances among the 60 frontier
safety siblings**.

One or more unsafe acceptances means the winner-level safety gate is not met.

### H3 — transfer

Every extension counted as successful will correctly handle the valid members
of at least two sealed auxiliary transfer pairs not used to construct or
approve it, while preserving rejection or abstention on both paired safety
members.

### H4 — protected-suite retention

The approved extension bundle will produce no false-acceptance increase on the
24 already-covered control tasks and no regression in the frozen protected
verifier suite.

### H5 — cross-model direction

The Safe Frontier-Pair Accuracy point-estimate delta will be positive for both
required model families. A third family is reported as additional evidence, not
as a substitute for failure in either required family.

## 4. Model conditions

Planned non-US model families:

1. `openrouter:qwen/qwen3.7-max`;
2. `openrouter:deepseek/deepseek-v4-pro`;
3. `zai:glm-5.2`.

At least two families must complete the full protocol. Each model receives three
independent sampling replicates. If a provider does not support reproducible
seeds, the runs are called sampling replicates rather than deterministic seeds.

Temperature is fixed at 0.2 unless rejected by the provider. Every run records:

- requested and resolved model identifier;
- provider and gateway;
- request timestamp and request ID when available;
- prompt hash;
- temperature, token cap, and seed support;
- latency, reported usage, and reported cost;
- complete raw response or a fail-closed provider-error receipt.

No unavailable model is silently substituted. Replacements must be frozen
before scored outcomes are inspected.

## 5. Baselines

### B0 — raw model

No verifier feedback and no explicit abstention mechanism.

### B1 — fixed three-state verifier

Accepted, rejected, or abstain; no verifier modification.

### B2 — fixed verifier plus equal-budget refinement

The model sees verifier feedback and may revise, but verifier coverage remains
fixed.

### B3 — act-or-abstain policy

A task-aware policy may answer or abstain but cannot propose an executable
extension.

### B4 — budget-matched human-only extension

A human receives the same development tasks and reviewer-time budget without
model-generated patch proposals.

### B5 — proposed system

Model-proposed, human-gated, reusable verifier extension.

### B6 — expert-authored oracle ceiling

Best-effort expert extension, reported only as an upper bound.

All arms use identical task hashes, ordering, base verifier, toolchain commits,
token and wall-time budgets, API-failure policy, and model versions.

## 6. Complementary evaluations

### Primary — verifier-isolation replay

Freeze candidate trajectories and replay identical candidates through the fixed
and expanded verifiers. This isolates verifier-coverage effects.

### Secondary — end-to-end agent evaluation

Allow each environment's feedback to alter later proposals. This measures
practical utility but mixes verifier changes with model-behavior changes.

## 7. Primary metric

### Safe Frontier-Pair Accuracy

```text
SFPA = successful frontier pairs / 60
```

Primary effect:

```text
delta_SFPA = SFPA(proposed) - SFPA(strongest non-oracle baseline)
```

Winner-level efficacy requires:

- `delta_SFPA >= 20 percentage points`;
- 95% confidence-interval lower bound greater than zero;
- paired sign-flip/permutation `p < 0.05`;
- positive point-estimate delta in both required model families, each against
  that model family's strongest non-oracle baseline.

## 8. Secondary metrics

- newly verifiable valid-task coverage;
- false-acceptance rate;
- correct rejection and correct abstention rates;
- three-class balanced accuracy and macro-F1;
- rejection-to-correct-revision recovery;
- approved reusable extensions per reviewer hour;
- reviewer minutes per approved extension;
- extension reuse count and rollback rate;
- risk-coverage curve and AURC when a continuous score exists;
- verifier and episode latency;
- model calls, tokens, reported cost, and wall time;
- Lean elaboration rate;
- domain-specific and model-specific effects;
- same-family versus shifted-family transfer.

Holm correction applies across declared secondary arm and ablation comparisons.
No secondary metric may replace a failed primary endpoint.

## 9. Statistical analysis

- Use stratified cluster bootstrap resampling over the 30 extension/generator
  families for 95% confidence intervals.
- Use 10,000 bootstrap resamples.
- Use a family-cluster sign-flip or permutation test for the primary delta.
- Use exact McNemar tests for paired binary outcomes where applicable.
- Report Wilson intervals for individual proportions.
- Report all domain, model-family, and replicate cells, including null and
  negative results.
- More pairs, parameter variants, or sampling replicates inside one family do
  not count as additional independent clusters.
- No post-hoc row deletion is allowed except manifest-invalid rows identified
  before model output is viewed; every exclusion requires a receipt.

With 30 independent family clusters, the study is powered only for a large and
consistent effect. A 20-point pair-level delta with heterogeneous family
effects may remain underpowered. Failure to clear the confidence and
permutation gates is retained as a valid negative result.

## 10. Human gate

Every proposed extension requires:

1. owner/operator review;
2. independent expert-AI review;
3. no access by either reviewer to aggregate confirmatory outcomes while judging
   individual proposals;
4. passing visible extension tests before confirmatory activation.

Reviewer disagreement preserves `candidateOnly:true` and does not count as
expanded coverage. A later scientific-domain expert is recorded as a separate
validation layer.

The model cannot author both the extension and the decisive approval.

## 11. Transfer and anti-overfitting obligations

A counted extension must:

- be a reusable parser rule, verifier obligation, formal specification, helper
  lemma/template, or similarly general mechanism;
- contain no task-ID branch, answer lookup, hidden theorem proof, or literal
  hidden gold;
- pass at least two sealed sibling tasks;
- pass paired near-miss safety tests;
- pass the frozen protected verifier suite;
- preserve activation and rollback receipts.

Task-specific repair is benchmark overfitting and does not count as frontier
expansion.

## 12. Contamination discipline

- Freeze and commit the confirmatory seal before model calls.
- Split by generator family, not random parameter variants.
- Exclude task text, formal statements, gold outputs, and hidden tests from all
  training or adaptation corpora.
- Run exact, normalized, fuzzy, and generator-family overlap scans against the
  repository and known benchmarks.
- Record whether statements are canonical, copied, or newly generated.
- Prevent reviewers from seeing confirmatory gold labels.
- Reject patches containing task IDs, literal gold values, or answer maps.
- Complete all preregistered arms and replicates; no early stopping when results
  appear favorable.
- Retain API failures, Lean timeouts, parser crashes, rejected extensions, and
  human disagreements.
- Release sealed tasks and golds after the confirmatory run.

## 13. Required ablations

1. **No human gate:** automatically activate model-proposed extensions.
2. **No executable extension:** natural-language feedback only.
3. **No transfer requirement:** permit task-specific changes.
4. **Forced binary verifier:** collapse abstention into rejection.
5. **Remove one tier at a time:** physics, symbolic, and Lean.
6. **Fixed replay versus interactive run.**
7. **AI-assisted versus budget-matched human-only extension.**
8. **Visible versus hidden safety tests.**

The no-human-gate and no-executable-extension ablations are mandatory for any
mechanism claim.

## 14. Stop and failure criteria

The headline is a **NO-GO** if any of the following occurs:

- any open safety sentinel is accepted;
- any of the 60 frontier safety siblings is unsafely accepted;
- fewer than 57 of 60 frontier pairs remain valid after pre-output manifest
  validation;
- fewer than two model families complete 95% of attempts;
- the human gate is bypassed or reconstructed after outcomes are viewed;
- any counted extension lacks two sealed transfer siblings;
- protected-suite regression occurs;
- task hashes, model identifiers, prompts, raw responses, or decision receipts
  are missing;
- primary hypotheses or metrics change after outcomes are observed.

## 15. Success ceiling

Even if every gate passes, permitted wording is:

> In this preregistered matched-pair benchmark, model-proposed and
> human-approved verifier extensions increased safe executable coverage on
> sealed transfer tasks without an unsafe acceptance in the evaluated safety
> siblings.

It does not establish general scientific discovery, autonomous verifier
invention, recursive self-improvement, AGI, or solution of open scientific
problems.
