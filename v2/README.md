# GOAI verification-frontier expansion v2

This directory holds the preregistered winner-oriented extension of the compact
GOAI Open Exploration package.

The v1 package remains a working fallback. V2 changes the research question
from merely detecting a verifier-coverage boundary to measuring whether that
boundary can be expanded safely:

```text
proposal
  -> accepted / rejected / typed abstain
  -> bounded next action
  -> candidate specification or verifier extension
  -> human gate
  -> re-verification
  -> measured coverage delta
```

V2 does not allow a model to approve its own specification or verifier. Every
new executable check remains `candidateOnly:true` until a human accepts it and
the deterministic test contract passes.

Read:

- `PREREGISTRATION.md` — frozen hypotheses, benchmark composition, metrics,
  thresholds, exclusions, and claim ceiling;
- `FRONTIER-EXPANSION-SPEC.md` — environment states, typed abstention causes,
  human-gated transitions, and receipt schemas;
- `HUMAN-GATE-RUBRIC.md` — frozen reviewer separation, rejection rules,
  domain checks, test obligations, and decision schema;
- `DEVELOPMENT-FAILURES.md` — preserved instrument failures and corrections;
- `EXPERT-VALIDATION.md` — independent methodology review and conditional-GO
  requirements.
- `EXPERT-POSTBUILD-AUDIT.md` — independent NO-GO on the first rehearsal and
  the corrections/blockers that now govern confirmatory readiness.
- `EXPERT-READINESS-AUDIT.md` — adversarial scorer review, the two fail-open
  defects corrected by the receipt milestone, and the remaining protocol-twin
  blockers.
- `EXPERT-CORRECTNESS-AUDIT.md` — hosted-demo and receipt-integrity findings,
  their development-branch dispositions, and the unchanged confirmatory
  NO-GO.
- `EXPERT-STAGE-A-AUDIT.md` — independent direct Z.AI review of the 24-family
  programme, structured proposal runner, guarded Pro6000 preflight, and claim
  ceilings.
- `PROTOCOL-TWIN-SPEC.md` — deterministic B0-B6 shadow execution, all eight
  ablation groups, byte-identical replay, and equal-budget validation.
- `STUDY-ROOT-V3-SPEC.md` — descendant transfer execution receipts, complete
  B0-B6/ablation result manifests, the immutable development Study Root, DAG
  adversarial benchmark, and scorer operating-characteristic simulation.

The current public 150-row manifest is a development/regression stress pack.
The confirmatory headline will require a future privately generated 144-task
matched-pair benchmark with 30 independent extension/generator families.

The current `synthetic-rehearsal-*` artifacts are retained only as an
instrument-design rehearsal. They are marked `confirmatoryEligible:false`
because independent audit found pseudoreplication, seed-independent rows,
duplicate prompts, and public structural leakage. Confirmatory execution is
hard-blocked in code for this milestone. Re-enabling it requires a reviewed code
change after the complete hash-linked readiness-receipt lifecycle in
`FRONTIER-EXPANSION-SPEC.md` exists; a self-declared seal is insufficient.

Planned evidence artifacts:

```text
v2/artifacts/task-manifest.jsonl
v2/artifacts/task-manifest-summary.json
v2/artifacts/task-validation.json
v2/artifacts/synthetic-rehearsal-seal.manifest.json
v2/artifacts/synthetic-rehearsal-validation.json
v2/artifacts/receipt-rehearsal-index.json
v2/artifacts/receipt-rehearsal-validation.json
v2/artifacts/receipt-protocol-benchmark.json
v2/artifacts/receipt-rehearsal/<sha256>.json
v2/artifacts/protocol-twin.json
v2/artifacts/protocol-twin-validation.json
v2/artifacts/study-arm-results.json
v2/artifacts/study-ablation-results.json
v2/artifacts/study-root-v3.json
v2/artifacts/study-root-v3-validation.json
v2/artifacts/study-root-dag-benchmark.json
v2/artifacts/scorer-operating-characteristics.json
v2/artifacts/raw-model-attempts.jsonl
v2/artifacts/environment-episodes.jsonl
v2/artifacts/frontier-proposals.jsonl
v2/artifacts/human-decisions.jsonl
v2/artifacts/benchmark-summary.json
v2/artifacts/risk-coverage.csv
v2/artifacts/ablation-summary.json
v2/artifacts/run-manifest.json
```

Claim ceiling:

```json
{"candidateOnly": true, "canClaimAGI": false}
```

## Current pre-confirmatory engineering milestone

`receipt_protocol.py` implements a content-addressed, fail-closed development
receipt chain. It verifies canonical JSON bytes and actual file hashes across:

- proposal;
- owner and independent expert-AI decisions;
- typed positive, negative, malformed, timeout, and rollback tests;
- activation;
- two transfer tasks;
- protected-suite execution;
- rollback;
- Lean execution metadata when applicable;
- final extension-chain receipt.

`build_receipt_rehearsal.py` generates three deterministic public
development-only chains (physics, symbolic, and Lean) comprising 34 JSON
receipts and 60 evidence blobs. The development scorer requires a receipt store
and checks these artifacts instead of trusting SHA-shaped strings. Each
transfer parent now links two content-addressed descendant execution receipts
that bind the valid task, paired safety task, decisions, and output blobs.

These are protocol fixtures, not scientific outcomes. Every chain is marked
`confirmatoryEligible:false`; confirmatory execution remains disabled.

The deterministic adversarial benchmark currently checks seven cases: intact
chains, post-hash tampering, a missing evidence blob, a missing independent
review, a result/chain cross-link mismatch, attempted reuse of development
receipts as confirmatory evidence, and a self-declared confirmatory chain.

## CPU-only Protocol Twin milestone

`protocol_twin.py` now executes a development-only B0-B6 fixture matrix and all
eight preregistered ablation groups on constructed, provider-free data:

- 18 tasks arranged as six frontier valid+safety pairs and three covered
  control pairs;
- 108 frozen synthetic candidate trajectories across two model-family labels
  and three replicate labels;
- 756 fixed-replay arm cells;
- 1,404 ablation cells across 13 explicit variants;
- 2,160 deterministic CPU execution cells in total;
- zero model calls and zero network calls.

The validator binds identical primary-replay candidate bytes across B1/B5,
requires B2 to consume a revised candidate, checks an A6 sentinel whose
interactive outcome differs from fixed replay, and binds task ordering,
base-verifier identity, toolchain identity, a common resource budget, B4/B5
review-budget fixture symmetry, all ablation variants, and one final
protocol-twin root.

The scorer intentionally does not consume this standalone root. It cannot
return `protocolValid:true` until a future immutable study root binds actual
B0-B6 rows, all ablations, execution receipts, prompts, models, budgets,
runner, and scorer.

This remains development-only machinery. The committed twin explicitly records
`scientificOutcome:false`, `statisticsEligible:false`,
`confirmatoryEligible:false`, and `winnerLevelEligible:false`.

## Development Study Root v3 milestone

`study_root.py` now materializes all 756 B0-B6 cells and all 1,404 ablation
cells as complete result manifests, then binds them with the Protocol Twin,
three extension chains, six descendant transfer-execution receipts, receipt
validation, scorer, verifier, preregistration, rubric, and protocol
specifications under one deterministic root.

The Study Root DAG benchmark rejects 164/164 deterministic invalid mutations
and accepts 24/24 row-order serialization variants of one valid development
DAG topology with stable typed issue codes. The scorer simulation runs 12,000
null and 12,000
prospective-alternative synthetic family panels plus 12 negative controls.

When these development artifacts are supplied to the scorer,
`studyRootBound`, `constructedB6FixtureRowsValidated`,
`constructedAblationFixtureRowsValidated`, and
`transferExecutionReceiptsValidated` can be true. `protocolValid`,
`studyRootScorerInputsBound`, `actualB6RowsValidated`,
`actualAblationRowsValidated`, `winnerLevelEligible`, and
`winnerLevelGateMet` remain false because no real confirmatory study or model
outcome exists. The low-resample operating-characteristic simulation is an
implementation smoke, not a confirmatory power or MDE result.

## Public Stage A development programme

`stage_a.py` freezes and validates exactly 24 public development families:

- 8 physics;
- 8 symbolic mathematics;
- 8 Lean;
- all 30 public frontier-gap tasks bound exactly once;
- all three Lean open-problem controls non-promotable.

The committed `stage-a-manifest.json` binds every public task row and prompt by
SHA-256 and fixes patch classes, permissions, resource ceilings, test-plan
categories, reviewer separation, and the base verifier commit. The companion
`stage-a-readiness.json` is ready only for development proposal generation.
Model run, owner review, independent expert-AI review, visible tests, approved
bundle freeze, and confirmatory seal all remain false.

`stage_a_model.py` asks a local model for one strict JSON proposal per family
without exposing task or family identifiers. It measures structured-output and
policy compliance while retaining every failure:

- malformed JSON;
- task-ID branching;
- answer/gold smuggling;
- open-control promotion;
- missing test categories;
- unbounded resources or authority;
- candidate self-approval;
- missing claim ceilings.

No model output is an approval. Every receipt remains
`awaiting-owner-and-independent-expert-ai`, `testsExecuted:false`,
`activationAuthorized:false`, `confirmatoryEligible:false`,
`winnerLevelEligible:false`, and `winnerLevelGateMet:false`.

## Public Stage A development result

`build_stage_a_result.py` records the single authorized all-24 development run
as a sanitized, immutable, public artifact
(`v2/artifacts/stage-a-development-result.json`):

- run `30742115988` on merged head `1ea93128…` with Qwen2.5-7B-Instruct at
  immutable revision `a09a3545…`;
- 8 physics / 8 symbolic / 8 Lean families;
- **23/24** JSON parse-valid and proposal-valid, with the single malformed Lean
  response retained;
- 2/2 open controls preserved as non-promotable abstentions;
- all seven policy-violation totals at zero;
- 0 tests, 0 owner/expert approvals, 0 activations, 0 scientific outcomes.

This is structured-output and policy-compliance evidence only. The builder is
fail-closed: it refuses to relax the claim ceiling, to hide the malformed
response, or to fabricate a cleaner 24/24 rate. It is bound to the manifest and
readiness artifacts by SHA-256, and its checker re-derives the canonical bytes.

## Pro6000 development lane

The Pro6000 lane has three dispatch-only modes:

```text
preflight          storage + exact-holder claim + CUDA/model-cache feasibility
development-smoke balanced 3-family structured-proposal run
stage-a-run        all 24 public Stage A families
```

It selects plain writable storage before CUDA/model contact, uses a reviewed
7B public model through direct Transformers, and releases only its exact GPU
holder under `if: always()`. This lane is development infrastructure, not a
Stage B run or capability result.

The storage gate distinguishes a cold-cache preflight from a development run
that may reuse the persistent reviewed cache. `preflight` keeps the 32 GiB
cold-cache admission floor. `development-smoke` and `stage-a-run` require a
20 GiB operational reserve so the 15.24 GB model snapshot downloaded by a
successful smoke does not make the next run reject its own cache. This does
not bypass cache feasibility: after the exact GPU holder is acquired and
before any model-weight load, the host preflight queries the immutable model
revision, measures the exact cached and missing bytes, and requires
`1.20 * missingBytes + 4 GiB` free. A cold or damaged cache with insufficient
space therefore still stops before proposal generation.
