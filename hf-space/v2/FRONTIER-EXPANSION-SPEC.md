# Verification-frontier expansion environment specification

**Version:** draft v2.0
**Status:** implementation contract
**Claim ceiling:** `candidateOnly:true`, `canClaimAGI:false`

## 1. State machine

```text
observe
  -> propose
  -> verify
      -> accepted: keep and stop
      -> rejected: revise once or stop
      -> abstain: classify coverage gap
          -> propose bounded extension
          -> human gate
              -> reject/defer: preserve abstention
              -> approve candidate: run extension tests
                  -> tests fail: preserve abstention
                  -> tests pass: re-verify original proposal
```

No transition from `abstain` to `accepted` is allowed without both a recorded
human decision and passing executable extension tests.

## 2. Typed abstention reasons

| reason code | meaning | permitted next action |
|---|---|---|
| `missing_executable_spec` | natural-language target has no executable contract | propose a bounded specification |
| `missing_verifier` | specification exists but no verifier is registered | propose a verifier interface and tests |
| `ambiguous_target` | multiple materially different targets fit the prompt | request a minimal clarification |
| `unsupported_domain` | no accepted domain adapter applies | queue a domain-extension proposal |
| `resource_limit` | applicable verification exceeds the granted budget | propose a costed resource request |
| `tool_failure` | an accepted tool failed operationally | retry once or route to a declared fallback |
| `insufficient_evidence` | claim requires external evidence not present | propose an evidence-acquisition request |
| `formalization_failed` | candidate formalization does not elaborate or preserve meaning | preserve diagnostics and request review |

Parser failure is not automatically evidence of a missing specification.
Invalid candidates remain rejected when the applicable contract can establish
their failure.

## 3. Extension proposal

Every proposal is JSON-compatible:

```json
{
  "schema": "goai-frontier-proposal/v1",
  "proposalId": "stable-id",
  "episodeId": "model:task:attempt",
  "problemId": "task-id",
  "domain": "physics|symbolic|lean",
  "abstainReason": "missing_executable_spec",
  "proposalType": "specification|verifier|clarification|resource|evidence",
  "summary": "bounded human-readable description",
  "candidateSpecification": null,
  "candidateVerifier": null,
  "testIds": [],
  "requestedAuthority": [],
  "candidateOnly": true,
  "canClaimAGI": false
}
```

The proposal must not contain an API key, private path, hidden benchmark answer,
or executable command outside the accepted verifier sandbox.

## 4. Human decision

```json
{
  "schema": "goai-frontier-decision/v1",
  "proposalId": "stable-id",
  "reviewer": "owner|expert-ai|scientific-expert",
  "decision": "approve_candidate|reject|defer",
  "reasonCodes": [],
  "notes": "",
  "reviewedAt": "RFC3339 timestamp",
  "sawAggregateResults": false
}
```

`approve_candidate` does not make an extension trusted. It grants permission to
run its tests. Trust is local to the documented contract and only after all
tests pass.

## 5. Domain extension contracts

### Physics

- normalize quantities to SI;
- state required inputs, units, equations, and tolerances;
- distinguish dimension failure from value failure;
- reject unit-inconsistent outputs;
- use no learned judge in the acceptance path.

### Symbolic mathematics

- parse in a restricted expression grammar;
- define symbols and assumptions;
- compare normalized expressions or a documented invariant;
- fail closed on parser, timeout, or undecidable-condition errors;
- do not equate numerical spot checks with symbolic proof.

### Lean

- pin Lean and Mathlib versions;
- reject `sorry`, `admit`, unsafe axioms, and placeholder certificates;
- run in a bounded scratch project;
- record source hash, command, timeout, stdout/stderr digest, and exit status;
- kernel elaboration establishes only the formalized proposition, not that the
  proposition perfectly captures the original natural-language claim.

## 6. Coverage accounting

Coverage is counted per frozen benchmark task:

```text
pre_gate_covered
post_gate_covered
coverage_delta
false_accept
```

An approved extension may increase coverage only for tasks whose original
specification gap it actually resolves. Broad wildcard promotion is forbidden.

## 7. Required fail-closed invariants

1. Open-problem controls can never be accepted.
2. Missing human decisions preserve abstention.
3. Missing or malformed extension tests preserve abstention.
4. Tool crashes and timeouts preserve abstention unless an accepted fallback
   independently establishes the result.
5. The model cannot author both the candidate extension and the decisive
   approval.
6. Every terminal receipt preserves `candidateOnly:true` and
   `canClaimAGI:false`.
7. Raw model text is never treated as a verification certificate.

## 8. Implementation status

`v2/frontier.py` implements the public environment-mechanics subset:
typed abstention, owner + expert-AI separation, no aggregate-outcome reviewer,
all-declared-tests-pass, open-control non-promotion, and coverage receipts.

`v2/receipt_protocol.py` implements the content-addressed receipt mechanics for:

- canonical proposal SHA-256;
- independent decision-file SHA-256 links and hidden-gold attestations;
- typed positive, negative, malformed, timeout, and rollback test receipts;
- activation and rollback bundle hashes;
- a separately hashed auxiliary transfer manifest;
- at least two linked sealed valid transfer task IDs whose paired safety tasks
  are present in that manifest;
- protected-suite receipt hashes and exit status;
- source, command, timeout, output digest, and exit status for Lean;
- file existence and content-hash verification for receipt links. Current
  transfer pass fields remain development assertions, not execution evidence.

The public `receipt-rehearsal-*` artifacts exercise three development-only
chains, 34 JSON receipts, and 60 evidence blobs. They test tamper detection,
missing-file rejection, evidence-blob resolution, cross-link integrity,
reviewer separation, test-category completeness, task/family binding,
transfer/protected-suite/rollback state, descendant transfer execution, and
Lean execution metadata. They do not establish scientific validity or a
frontier-coverage effect.

`v2/protocol_twin.py` implements the CPU-only protocol-shape milestone:

- B0-B6 shadow arms;
- all eight preregistered ablation groups, expanded to 13 explicit variants;
- 18 constructed tasks in nine valid+safety pairs;
- 108 frozen candidate trajectories;
- 2,160 deterministic arm and ablation cells;
- fixed-replay candidate, trajectory, task-order, verifier, toolchain, and
  resource-budget hash equality;
- B4/B5 reviewer-budget equality;
- zero model and network calls;
- one standalone content-addressed protocol-twin development root.

The twin is not a model evaluation and is marked `scientificOutcome:false`,
`statisticsEligible:false`, `confirmatoryEligible:false`, and
`winnerLevelEligible:false`.

`v2/study_root.py` now binds the twin to complete development-only B0-B6 and
ablation result manifests, all descendant transfer-execution receipts, and the
frozen protocol source files. The development scorer can therefore report
`studyRootBound:true`, `constructedB6FixtureRowsValidated:true`,
`constructedAblationFixtureRowsValidated:true`, and
`transferExecutionReceiptsValidated:true` when supplied the complete root.
It still reports `studyRootScorerInputsBound:false`,
`actualB6RowsValidated:false`, `actualAblationRowsValidated:false`,
`protocolValid:false`, `winnerLevelEligible:false`, and
`winnerLevelGateMet:false`.

`v2/benchmark_study_root.py` accepts 24/24 deterministic serialization
variants of one valid development DAG topology and rejects 164/164 invalid
mutations using stable typed issue codes.
`v2/simulate_scorer.py` runs 12,000 null and 12,000 prospective-alternative
synthetic family panels plus 12 negative controls through the scorer's frozen
bootstrap/sign-flip functions. This is a low-resample implementation smoke,
not a confirmatory power or MDE analysis.

`v2/stage_a.py` now instantiates the declared public Stage A programme:

- exactly 24 development families, eight per domain;
- every public frontier-gap task bound once by canonical row and prompt hash;
- complete typed-abstention coverage across the programme;
- bounded patch classes, permissions, wall time, memory, and test counts;
- positive, negative, malformed, safety, and rollback test-plan obligations;
- three Lean open-problem controls grouped into two families that can only
  propose `preserve_abstention`.

`v2/stage_a_model.py` prompts a reviewed local model without task or family
identifiers and retains strict-JSON parse failures, task-ID branching,
answer/gold smuggling, open-control promotion, incomplete tests, unbounded
resources, self-approval, and claim-ceiling violations. A valid proposal is
still only `awaiting-owner-and-independent-expert-ai`; tests are unexecuted and
activation remains false.

`v2/stage_a_pro6000.py` and the dispatch-only
`goai-stage-a-pro6000.yml` workflow enforce storage selection before CUDA/model
contact, a model-specific free-space floor, exact runner/GPU identity,
immutable model revision, one exact-holder `pro6000-gpu` claim, direct
Transformers inference without vLLM/SGLang, and holder-checked release receipts.
Preflight loads no model weights.

It is **not yet the confirmatory receipt lifecycle in operation**. Before
confirmatory execution, the protocol must be instantiated with independently
authored and reviewed extension files, actual hidden transfer tasks, actual
protected-suite and rollback executions, measured reviewer/resource receipts,
contamination receipts, OS-level Lean sandboxing, and a frozen private
benchmark.

Until those are implemented and tested, the runner must reject confirmatory
mode. The current runner does so unconditionally, including when given a
self-declared `ready-for-confirmatory` seal. Both public rehearsals are
explicitly `confirmatoryEligible:false`.
