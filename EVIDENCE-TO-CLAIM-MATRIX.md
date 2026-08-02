# Evidence-to-claim matrix

> Every public claim in this submission maps to a committed, hash-bound
> artifact, immutable run receipt, or deterministic test. **Unsupported claims
> are removed, not softened.** If a claim is not in this table, it is not made.
>
> Verification commands are CPU-only and need no GPU. SHA-256 prefixes are
> shown for readability; full digests are in each artifact and in the bundle's
> `MANIFEST.sha256`.

## A. Stage A development run (the real result)

| Public statement | Bound artifact / receipt | SHA-256 (prefix) | How to verify |
|---|---|---|---|
| One authorized all-24 development run on Pro6000 Blackwell | `v2/artifacts/stage-a-development-result.json` → GitHub Actions run `30742115988` | `6e069077…` (artifact file); run artifact upload `d12e366b…` | `python3 v2/build_stage_a_result.py --check` |
| Exact merged head `1ea93128…` (PR #1813) | same artifact `run.mergedHeadSha` | — | `git merge-base --is-ancestor 1ea93128… origin/main` |
| Model Qwen2.5-7B-Instruct @ immutable revision `a09a3545…` | same artifact `model.immutableRevision` | — | `huggingface-cli repo-info` (owner-only to re-contact) |
| Family balance 8 physics / 8 symbolic / 8 Lean | `v2/artifacts/stage-a-manifest.json` | `d93bfb60…` | `python3 v2/stage_a.py --check` |
| 23/24 JSON parse-valid + proposal-valid | `stage-a-development-result.json` `structuredOutput` | `6e069077…` | `python3 v2/build_stage_a_result.py --check` |
| 1 retained malformed Lean response (`stage-a-lean-01…`, "Invalid control character") | same `structuredOutput.invalidFamilyId/invalidError/invalidResponseRetained` | — | the checker refuses `invalidResponseRetained:false` |
| 2/2 open controls preserved as non-promotable abstentions | same `openControlPreservation` | — | `test_stage_a_result.py` |
| All 7 policy-violation totals zero | same `policyViolationTotals` | — | checker refuses any nonzero total |
| 0 tests / 0 approvals / 0 activations / 0 scientific outcomes | same `gates` | — | checker refuses any nonzero gate |
| Artifact ID `8831635695`, upload SHA-256 `d12e366b…`, holder `gha-30742115988-1` released live | same `artifact` + `run` | — | GitHub Actions artifact panel (run owner-only) |

## B. Deterministic verification instrument

| Public statement | Bound artifact | SHA-256 (prefix) | How to verify |
|---|---|---|---|
| 150-row public development manifest, 150/150 strict validation (incl. 48 Lean) | `v2/artifacts/task-validation.json` | `a81cba91…` | `python3 v2/validate_task_manifest.py` |
| 30 public frontier-gap tasks bound exactly once; 3 Lean open controls non-promotable | `v2/artifacts/stage-a-manifest.json` | `d93bfb60…` | `python3 v2/stage_a.py --check` |
| Receipt protocol: 3 chains / 34 receipts / 60 blobs | `v2/artifacts/receipt-rehearsal-index.json` | `df1cbc08…` | `python3 v2/build_receipt_rehearsal.py` |
| Adversarial receipt benchmark: 7/7 cases | `v2/artifacts/receipt-protocol-benchmark.json` | `e0679ec0…` | `python3 v2/benchmark_receipt_protocol.py` |

## C. Confirmatory protocol machinery (development-only)

| Public statement | Bound artifact | SHA-256 (prefix) | How to verify |
|---|---|---|---|
| CPU Protocol Twin: B0–B6, 8 ablations, 13 variants, 2,160 deterministic cells, 0 model/network calls | `v2/artifacts/protocol-twin-validation.json` | `08d991fa…` | `python3 v2/protocol_twin.py` |
| Study Root v3: 756 arm + 108 B6 + 1,404 ablation rows; 24 valid DAG variants; 164 invalid mutations rejected | `v2/artifacts/study-root-v3-validation.json` | `dce48b42…` | `python3 v2/study_root.py` + `python3 v2/benchmark_study_root.py` |
| Scorer operating-characteristic simulation: 24,000 panels + 12 negative controls (low-resample smoke, not power) | `v2/artifacts/scorer-operating-characteristics.json` | `dc11357a…` | `python3 v2/simulate_scorer.py` |
| Synthetic rehearsal: 144/144 (48 Lean), explicitly `confirmatoryEligible:false` | `v2/artifacts/synthetic-rehearsal-validation.json` | `0cc05525…` | `python3 v2/build_receipt_rehearsal.py` |

## D. Package integrity

| Public statement | Bound artifact | How to verify |
|---|---|---|
| Deterministic upload ZIP + SHA-256 | `dist/GOAI-AI4R-Open-Exploration.zip` + `.sha256` | `python3 verify_bundle.py`; two consecutive builds are byte-identical |
| Claim ceiling enforced on every public JSON | `build_bundle.py` allowlist + `test_demo.py::test_bundle_enforces_claim_ceiling_on_every_public_json` | `python3 -m unittest test_demo.py` |

## E. Claims this submission explicitly does NOT make

Each of these is false/absent and the gates enforce it:

- verifier extension approved (`verifierExtensionsApproved: 0`)
- scientific discovery / outcome (`scientificOutcome: false`)
- frontier expansion measured (`protocolValid: false`)
- general model capability / capability uplift (`capabilityClaim: false`)
- contest performance / winner eligibility (`winnerLevelEligible: false`)
- AGI / ASI (`canClaimAGI: false`)
- confirmatory power / MDE (`confirmatoryPowerValidated: false`)
- independent blinded expert review (author saw aggregate outcomes — cannot self-count)

`candidateOnly:true`; `canClaimAGI:false`.
