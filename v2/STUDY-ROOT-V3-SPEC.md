# Development Study Root v3

- **Frozen implementation date:** August 1, 2026
- **Evidence class:** development-only
- **Model/provider contact:** none
- **Claim ceiling:** `candidateOnly:true`, `canClaimAGI:false`

## Purpose

Study Root v3 closes four engineering gaps left by the standalone Protocol
Twin:

1. transfer success is derived from content-addressed descendant execution
   receipts rather than trusted parent booleans;
2. every B0–B6 fixture cell is materialized in one complete arm-result
   manifest;
3. every preregistered ablation cell is materialized in one complete
   ablation-result manifest;
4. one immutable root binds the manifests, receipt graph, Protocol Twin,
   scorer, verifier, preregistration, rubric, and protocol specifications.

It remains a constructed CPU-only development study. It does not turn fixture
rows into model outcomes, scientific evidence, or contest-winning evidence.

## Bound artifacts

```text
study-arm-results.json
study-ablation-results.json
study-root-v3.json
study-root-v3-validation.json
study-root-dag-benchmark.json
scorer-operating-characteristics.json
```

The root binds:

- the Protocol Twin root and validation report;
- 756 complete B0–B6 result rows, including 108 B6 oracle-only rows;
- 1,404 complete ablation rows across 8 groups and 13 variants;
- 3 extension chains and 6 descendant transfer-execution receipts;
- the receipt rehearsal index and validation report;
- the frozen scorer, receipt validator, Protocol Twin, Study Root builder,
  DAG benchmark, scorer simulation, preregistration, human-gate rubric, and
  protocol specifications, including this specification.

All root and manifest JSON uses deterministic canonical hashing.
Bundle verification compares every `sourceFileSha256s` entry with the
corresponding source bytes inside the ZIP before allowing cached or local
report recomputation.

## Descendant transfer execution

Each transfer parent now links a distinct
`goai-frontier-transfer-execution-receipt/v1` for each valid transfer task.
The descendant binds:

- the activation receipt;
- the original trigger task;
- the valid transfer task, pair, and paired safety task;
- valid and safety terminal decisions;
- separate valid/safety output blobs;
- zero exit status and the CPU-development runner mode;
- `passed:true` and `safetyPreserved:true`.

Deleting, tampering, cross-linking, or reusing a descendant invalidates the
extension chain.

## Adversarial benchmark

`benchmark_study_root.py` validates:

- 24 valid row-order serialization variants of one development DAG topology,
  bound by `serializationVariant`;
- 164 deterministic invalid DAG mutations;
- stable typed issue codes for every invalid case.

The mutation inventory covers root links, all seven arms, all thirteen
ablation variants, receipt-chain links, source hashes, claim ceilings, budget
fields, decisions, schemas, and contact counters.

## Scorer operating characteristics

`simulate_scorer.py` runs:

- 12,000 null simulations;
- 12,000 prospective-alternative simulations;
- 12 negative controls.

It calls the scorer's frozen family-cluster bootstrap and sign-flip functions.
The per-simulation resample counts are deliberately small development settings
and are disclosed in the artifact. Wilson 95% intervals are reported and the
operating gates use the conservative interval bounds. The simulation checks
implementation behavior at one easy alternative point; it is not a power or
MDE guarantee for the future private study. Confirmatory power analysis near
the +20 percentage-point boundary remains open.

## Scorer binding

When the development scorer is supplied all Study Root materials, it may
report:

```json
{
  "studyRootBound": true,
  "studyRootScorerInputsBound": false,
  "constructedB6FixtureRowsValidated": true,
  "constructedAblationFixtureRowsValidated": true,
  "actualB6RowsValidated": false,
  "actualAblationRowsValidated": false,
  "transferExecutionReceiptsValidated": true,
  "protocolValid": false,
  "winnerLevelEligible": false,
  "winnerLevelGateMet": false
}
```

`protocolValid` remains false because no confirmatory study, real model rows,
real blinded reviewers, private Stage B pack, or measured resource receipts
exist. The constructed fixture manifests are independently validated but are
not represented as the scorer's actual B6 or ablation inputs.

## Reproduction

```bash
python3 v2/build_receipt_rehearsal.py
python3 v2/protocol_twin.py
python3 v2/study_root.py
python3 v2/benchmark_study_root.py
python3 v2/simulate_scorer.py
python3 -m unittest -v \
  v2.test_study_root \
  v2.test_benchmark_study_root \
  v2.test_simulate_scorer
```

## Remaining blockers

- execute the declared 24-family Stage A development program;
- create and seal a genuinely private provenance-bound 30-family Stage B
  primary pack and separate 120-task auxiliary transfer pack;
- record real complete B0–B6 and ablation outcomes from frozen model calls;
- assign real blinded reviewers and record measured equal-budget receipts;
- complete contamination adjudication and one immutable private readiness
  root;
- add OS-level Lean isolation, clean Linux reproduction, and scientific-domain
  expert review.

The only permitted conclusion is that the development protocol is more fully
bound and adversarially exercised. No capability, frontier-expansion,
scientific-discovery, safety-efficacy, winner-level, AGI, or ASI claim follows.
