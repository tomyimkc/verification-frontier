# Safely Expanding the Verification Frontier of Scientific Agents

**GOAI 2026 AI for Research — Open Exploration**<br/>
**Team:** Yim Kin Cheong (Tom), Independent Researcher, Hong Kong<br/>
**Licence:** Apache-2.0<br/>
**Evidence ceiling:** `candidateOnly:true`, `canClaimAGI:false`,
`winnerLevelEligible:false`, `winnerLevelGateMet:false`

<!-- PAGE 1 -->

## 1. Research problem and proposed contribution

Scientific agents need to distinguish three cases at every step:

1. an available executable check establishes a candidate;
2. an available check refutes it; and
3. the candidate lies outside current verifier coverage.

Treating case 3 as “no error found” creates a silent pass. Merely abstaining,
however, leaves the scientific workflow stuck. This project therefore asks:

> Can model-proposed, human-approved verifier extensions increase the safe
> executable coverage of a frozen scientific verification stack on sealed
> transfer tasks?

The proposed contribution is not dimensional analysis, SymPy, Lean, RLVR,
abstention, or the verification-frontier concept itself. It is their
operational integration into a prospective experiment with:

- typed coverage gaps;
- bounded specification/verifier proposals;
- owner and independent expert-AI approval;
- executable positive, negative, and fail-closed tests;
- hidden transfer and paired safety siblings;
- rollback and coverage-delta receipts.

The deliverable is the environment and verification signal. It does not claim
scientific discovery, recursive self-improvement, model capability, or AGI.

<!-- PAGE 2 -->

## 2. Exploration environment

The base environment emits:

| outcome | contract |
|---|---|
| `accepted` | an applicable deterministic check establishes the candidate |
| `rejected` | an applicable check establishes a concrete failure |
| `abstain` | no applicable executable check can decide; never a silent pass |

The v2 state machine is:

```text
observe -> propose -> verify
  accepted: keep
  rejected: revise or stop
  abstain: classify gap -> propose bounded extension
    -> owner + expert-AI gate -> executable tests
    -> re-verify -> activate locally or preserve abstention
```

No model can approve its own extension. A reviewer who saw aggregate
confirmatory outcomes does not count. Open-problem controls can never be
promoted.

Three deterministic domains are exercised:

- **physics:** SI quantities, affine units, vectors, uncertainty, conservation,
  and reference frames;
- **symbolic mathematics:** domains, assumptions, singularities, piecewise
  boundaries, and inequality direction;
- **Lean:** pinned Lean 4.24.0 + Mathlib kernel checking together with explicit
  natural-language/formal-contract alignment.

A public no-login demo exposes only public verifiers, reference episodes,
synthetic gate mechanics, and seal metadata—never sealed tasks or credentials.

The content-addressed evidence DAG is:

```text
proposal# -> owner-review# + expert-AI-review# -> typed-tests# -> activation#
          -> transfer# -> protected-suite# -> rollback# -> extension-chain#
```

<!-- PAGE 3 -->

## 3. Preregistered evaluation and current milestones

### Target confirmatory design

The primary scored benchmark is **144 tasks / 72 matched pairs**, plus a
separate 120-task auxiliary transfer pack:

| component | physics | symbolic | Lean | total |
|---|---:|---:|---:|---:|
| frontier valid+safety pairs | 20 | 20 | 20 | 60 |
| auxiliary transfer valid+safety pairs | 20 | 20 | 20 | 60 |
| already-covered control pairs | 4 | 4 | 4 | 12 |
| full study tasks | 88 | 88 | 88 | 264 |

The 60 primary frontier pairs must form **30 independent extension/generator
families** with two scored pairs and two auxiliary transfer pairs per family.
Inference clusters by family, not by transfer task, parameter variant, or model
replicate.

Primary endpoint: **Safe Frontier-Pair Accuracy (SFPA)**. A pair succeeds only
when the valid member is machine-decided, the safety sibling is rejected or
abstained, and the responsible extension passes transfer and regression gates.

Winner-level thresholds are preregistered:

- zero unsafe acceptance among 60 frontier safety siblings;
- `delta_SFPA >= +20 percentage points` over the strongest non-oracle baseline;
- 95% cluster-bootstrap CI lower bound above zero;
- paired sign-flip `p < 0.05`;
- positive point estimate in each required model family against that family's
  strongest non-oracle baseline;
- every counted extension passes two sealed valid transfer tasks and their
  paired safety tasks;
- no covered-control or protected-suite regression.

### Evidence completed by August 1, 2026

- compact v1 demo and deterministic reference policies: operational;
- public development/regression pack: 150 rows, 50 per domain;
- public Stage A programme: **24 families (8/domain)**, all 30 public
  frontier-gap tasks hash-bound once, with three non-promotable Lean open
  controls and bounded positive/negative/malformed/safety/rollback test plans;
- **one authorized all-24 Stage A development run completed (Pro6000 Blackwell,
  Qwen2.5-7B-Instruct, run `30742115988`): 8/8/8 balance, 23/24
  structured-output valid, one retained malformed Lean response, 2/2 open
  controls preserved, all seven policy-violation totals zero** — structured-
  output/policy evidence only, not a verifier extension or capability result;
- real Lean validation: **150/150** development rows valid;
- content-addressed receipt protocol: **3 chains / 34 receipts / 60 evidence
  blobs**;
- deterministic adversarial receipt benchmark: **7/7** cases passed;
- CPU-only Protocol Twin: **B0-B6 / 8 ablation groups / 13 variants / 2,160
  deterministic cells**, with 108 frozen trajectories and zero model or network
  calls;
- development Study Root v3: **756 constructed arm rows / 108 B6 fixture rows /
  1,404 constructed ablation rows / 6 descendant transfer executions / 24
  serialization variants of one valid DAG topology + 164 invalid mutations /
  24,000 scorer simulations + 12 negative controls**;
- synthetic rehearsal: 144 tasks / 72 pairs, marked
  `confirmatoryEligible:false`;
- rehearsal validation: **144/144**, including 48 Lean items, but only 15
  generator families with known leakage and duplicate prompts;
- direct Z.AI GLM development smoke: successful, no provider fallback.
- guarded Pro6000 lane: storage-before-CUDA, reviewed 7B local model,
  immutable revision, exact-holder claim/release, and strict proposal-policy
  receipts; the development proposal run is complete but no approval, test,
  activation, or confirmatory outcome is included.

These are infrastructure milestones, not evidence of frontier-expansion
efficacy. No confirmatory seal or outcome exists.

Study Root v3 binds the complete constructed manifests and descendant transfer
receipts, so the development scorer can report `studyRootBound:true`,
`constructedB6FixtureRowsValidated:true`,
`constructedAblationFixtureRowsValidated:true`, and
`transferExecutionReceiptsValidated:true`. Because no real confirmatory study
exists, it still reports `studyRootScorerInputsBound:false`,
`actualB6RowsValidated:false`, `actualAblationRowsValidated:false`,
`protocolValid:false`, `winnerLevelEligible:false`, and
`winnerLevelGateMet:false`. The simulation is a low-resample implementation
smoke, not confirmatory power or MDE evidence.

The winner claim is falsified by any unsafe acceptance, any required
model-family loss against its strongest baseline, any broken receipt link,
covered-control regression, or failure of the CI / p-value gates.

<!-- PAGE 4 -->

## 4. Baselines, novelty boundary, disclosure, and continuation

Required arms are: raw model; fixed verifier; fixed verifier plus equal-budget
refinement; act-or-abstain without executable extension; budget-matched
human-only extension; proposed human-gated system; and an expert-authored oracle
ceiling. Required ablations include removing the human gate, executable patch,
transfer obligation, explicit abstention, and each verifier tier.

The committed CPU-only twin executes this protocol shape on constructed
fixtures and fails closed on missing arms, missing ablation variants, replay
hash drift, or budget asymmetry. It is not an efficacy experiment.

Direct prior work includes RLVP (arXiv:2607.10474), EG-VAR
(arXiv:2607.12650), Recursive Epistemic Engines and its Novelty Horizon, and
AgentAbstain (arXiv:2607.10059). The strongest novelty risk is prior guarded
verifier-expansion work. The defensible contribution is therefore prospective
empirical evidence and reproducible instrumentation—not invention of the
frontier.

**Pre-existing Sophia infrastructure:** SI and symbolic verifiers, Lean
checking/evaluations, provenance and no-overclaim gates, and prior candidate
ladder evidence.<br/>
**Contest-period work:** three-state environment packaging, typed frontier
protocol, matched-pair generator and seal, content-addressed receipt protocol,
human-gate contracts, 24-family Stage A programme, guarded local-model runner,
statistics, bilingual materials, and hosted-demo package.

Current recommendation is **NO-GO for confirmatory execution** and
**CONDITIONAL GO for preliminary upload as an infrastructure proposal**.
Confirmatory scoring must not begin until a genuinely private 30-family
benchmark, prompts, models, budgets, and extension bundle are frozen, and the
receipt protocol is instantiated with real independent reviews, hidden
transfer, protected-suite, and rollback executions.

```bash
./run_all.sh
python3 v2/build_stage_a_result.py --check
python3 v2/validate_confirmatory_pack.py --lean-project <pinned-project> --require-lean
```

Limits: no confirmatory benchmark or efficacy result yet; the rehearsal is
constructed and structurally leaked; the Stage A development proposal run is
complete (23/24, one retained malformed response) but owner/expert decisions
and executable extension tests are not yet completed; human and
scientific-domain review remain necessary. `candidateOnly:true`,
`canClaimAGI:false`, `winnerLevelEligible:false`,
`winnerLevelGateMet:false`.
