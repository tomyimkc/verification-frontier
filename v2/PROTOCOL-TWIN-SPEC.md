# CPU-only Development Protocol Twin

- **Frozen implementation date:** July 31, 2026
- **Evidence class:** development-only
- **Confirmatory eligibility:** false
**Claim ceiling:** `candidateOnly:true`, `canClaimAGI:false`

## Purpose

The Protocol Twin is a deterministic shadow executor for the declared GOAI
study. It answers a pre-confirmatory engineering question:

> Can the declared fixture cells, content hashes, sentinel transitions, and
> budget fields be represented and validated without contacting a model
> provider?

It does **not** estimate Safe Frontier-Pair Accuracy, model quality, transfer
efficacy, safety, scientific discovery, or contest-winning performance.

## Constructed fixture geometry

The committed twin contains:

| unit | count |
|---|---:|
| domains | 3 |
| constructed pairs | 9 |
| frontier valid+safety pairs | 6 |
| already-covered control pairs | 3 |
| tasks | 18 |
| required model-family labels | 2 |
| replicates per label | 3 |
| frozen candidate trajectories | 108 |
| B0-B6 fixed-replay cells | 756 |
| ablation cells | 1,404 |
| total deterministic execution cells | 2,160 |
| model calls | 0 |
| network calls | 0 |

The model-family and replicate labels reproduce the future matrix shape. They
are fixture coordinates, not sampled model outcomes and not independent
statistical observations.

## B0-B6 shadow arms

| arm | twin semantics |
|---|---|
| B0 raw model | frozen synthetic answer action; no verifier authority |
| B1 fixed verifier | one pass through the unchanged three-state verifier |
| B2 fixed refinement | consumes a precomputed revised candidate after fixed-verifier feedback |
| B3 act-or-abstain | deterministic answer/abstain policy with no executable extension |
| B4 human-only | human-fixture extension path with the same review budget as B5 |
| B5 proposed | model-fixture proposal plus human-gate, tests, transfer, protected-suite, and rollback conditions |
| B6 oracle ceiling | expert-fixture integrity ceiling; `oracleOnly:true`, never a non-oracle baseline |

The primary replay comparison, B1 versus B5, binds the same:

- candidate SHA-256;
- trajectory SHA-256;
- task-order SHA-256;
- base-verifier SHA-256;
- toolchain SHA-256;
- common resource-budget SHA-256.

B4 and B5 additionally have identical fixture reviewer-time budgets. The
review-time field is explicitly labelled as a fixture, not measured human
labor.

## Eight preregistered ablation groups

1. no human gate;
2. no executable extension;
3. no transfer requirement;
4. forced binary verifier;
5. remove one tier, with physics, symbolic, and Lean variants;
6. fixed replay versus interactive feedback;
7. AI-assisted versus human-only extension;
8. visible versus hidden safety tests.

The eight groups expand to 13 explicit variants. Missing any group, required
variant, task cell, model-family label, or replicate makes the twin invalid.

## Resource envelope

All non-oracle arms bind the same content-addressed resource envelope:

```json
{
  "candidateStepCap": 2,
  "extensionProposalCap": 1,
  "extensionTestCap": 7,
  "fixtureTickCap": 100,
  "modelCallCap": 0,
  "networkCallCap": 0,
  "reviewDecisionCap": 2,
  "revisionStepCap": 1,
  "verifierCallCap": 2
}
```

Unused budget is not reallocated. Any model or network contact would violate
the twin contract.

## Fail-closed validator

`protocol_twin.py` rejects:

- missing, duplicate, extra, or unknown arm/ablation cells;
- absent tier-removal or safety-visibility variants;
- candidate or trajectory hash drift;
- primary replay candidate differences across B1/B5;
- task-order, base-verifier, toolchain, or resource-budget drift;
- B4/B5 reviewer-budget asymmetry;
- wrong proposal-author or oracle-only labels;
- executor decisions inconsistent with the frozen fixture semantics or the
  independent B2/A6 sentinel expectations;
- altered descendant hashes or the final protocol-twin root;
- missing `candidateOnly:true`, `canClaimAGI:false`, or development-only
  status;
- any model contact, network contact, statistical eligibility, confirmatory
  eligibility, or winner-level eligibility.

`confirmatory_scoring.py` does **not** treat the standalone twin root as
sufficient. `study_root.py` now separately binds the twin to complete
development-only result manifests, descendant transfer receipts, and frozen
source files. With those materials, the scorer can report:

```json
{
  "scoringInputsValid": true,
  "protocolValid": false,
  "studyRootBound": true,
  "studyRootScorerInputsBound": false,
  "constructedB6FixtureRowsValidated": true,
  "constructedAblationFixtureRowsValidated": true,
  "actualB6RowsValidated": false,
  "actualAblationRowsValidated": false,
  "transferExecutionReceiptsValidated": true,
  "winnerLevelEligible": false,
  "winnerLevelGateMet": false
}
```

## Reproduction

```bash
python3 v2/protocol_twin.py
python3 v2/protocol_twin.py --check
python3 -m unittest -v v2.test_protocol_twin
```

## Remaining blockers

Study Root v3 has completed the development-only descendant-receipt,
complete-manifest, DAG-mutation, and scorer-simulation items. The project still
needs:

- the declared 24-family Stage A development program;
- a genuinely private, provenance-bound 30-family Stage B primary benchmark
  plus the separate 120-task auxiliary transfer pack;
- real complete B0-B6 and 13-variant ablation outcomes from frozen model calls;
- blinded reviewer assignment and real equal-budget accounting;
- one immutable readiness root over every prompt, runner, scorer, verifier,
  rubric, protected suite, and extension bundle;
- complete contamination adjudication;
- OS-level Lean sandboxing, clean Linux reproduction, and scientific-domain
  expert review.

The only permitted conclusion is:

> The development-only CPU Protocol Twin deterministically checks declared
> fixture construction, B1/B5 replay hashes, B2/A6 sentinel transitions,
> cell completeness, and budget fields on constructed data. Study Root v3
> additionally binds its complete fixture manifests and descendant transfer
> receipts under one deterministic development root.

It is not a confirmatory result or a capability claim.
