> 🌐 简体中文 / Simplified Chinese: [`zh/评审对照.md`](评审对照.md)

# Judging-criteria crosswalk

> Maps each official Open Exploration judging criterion to exactly where this
> submission addresses it. Official wording and weights are quoted from the
> *GOAI Track 3 AI for Research — Participant Handbook (EN)* (80 pp., retrieved
> 2026-08-01; re-verified live 2026-08-02). See [`OFFICIAL-RULES-CHECK.md`](OFFICIAL-RULES-CHECK.md)
> for the full rules check.

## Official Open Exploration judging weights

| Weight | Official criterion | Where addressed in this package |
|---:|---|---|
| **45 %** | problem definition and environment-design quality | `EXECUTIVE-SUMMARY.md` §"The problem"; `PROJECT.md` §1–4 (research question, fixed/explorable, environment contract, three domains); `submission/submission-en.md` §1–2; `ARCHITECTURE.md`; `v2/FRONTIER-EXPANSION-SPEC.md` |
| **35 %** | exploration process and scientific/research signal | `PROJECT.md` §5–8 (development pack, rehearsal vs target, primary endpoint SFPA, baselines/ablations); `v2/PREREGISTRATION.md`; the **real Stage A development result** (`v2/artifacts/stage-a-development-result.json`, 23/24 + retained malformed); `FAILURE-SHOWCASE.md` (negative/anomaly signals); `v2/DEVELOPMENT-FAILURES.md` |
| **20 %** | verifiability and extensibility | `REPRODUCIBILITY-QUICKSTART.md`; `EVIDENCE-TO-CLAIM-MATRIX.md`; `verify_bundle.py` + deterministic ZIP; `v2/receipt_protocol.py` + 7/7 adversarial benchmark; `v2/study_root.py` (DAG benchmark 24 valid / 164 invalid); per-family `executionBudget` and test-plan categories in `v2/stage_a.py` |

## The three core Open Exploration constraints (handbook)

| Handbook constraint | How this submission satisfies it |
|---|---|
| **Real problem** — must genuinely exist and lack a generally accepted answer, supported by literature/data/expert evidence | Verification-coverage gaps in scientific agents are a documented failure mode (silent pass). See `RELATED-WORK.md` and `PROJECT.md` §11 for prior-work positioning (RLVP, EG-VAR, Recursive Epistemic Engines, AgentAbstain). |
| **Exploration environment** — specify what the agent observes, may change, and receives as feedback | The three-state verifier (accepted/rejected/abstain) + typed-abstention taxonomy + bounded patch classes + content-addressed receipt DAG. See `ARCHITECTURE.md` and `v2/FRONTIER-EXPANSION-SPEC.md`. |
| **Discovery signal** — state before exploration what counts as a signal (positive, anomaly, counterexample, stable negative, failure mode, justified revision) | Preregistered in `v2/PREREGISTRATION.md`: SFPA success, unsafe-acceptance anomaly, control/protected-suite regression counterexample, abstention-as-signal, and the falsification conditions for the winner claim. |

## Required deliverables by round

| Round | Official requirement | Delivered |
|---|---|---|
| **Preliminary** | problem-definition document ≤ 4 pages | `submission/GOAI-AI4R-Open-Exploration-{EN,ZH}.pdf` (4 pp. each, bilingual) + `submission/submission-{en,zh}.md` sources |
| **Second round** | minimal runnable exploration environment, ≥1 complete execution log, baseline designs, README, reproduction instructions | `demo.py` + `run_all.sh` (one-command); `artifacts/episodes.jsonl` (complete log); four deterministic reference policies (baselines); `README.md` + `REPRODUCIBILITY-QUICKSTART.md`; the real Stage A run log bound in `stage-a-development-result.json` |
| **Final** | exploration report, defense materials, final code repo, live demo, signal explanation | `PROJECT.md` (report); `hosted-demo/` (no-login Gradio demo); `FAILURE-SHOWCASE.md` + `EXECUTIVE-SUMMARY.md` (signal explanation). Final defense is owner-only. |

## Open-source / IP / data disclosure (handbook)

| Handbook term | This submission |
|---|---|
| open-source plan and release boundaries stated | Apache-2.0; `LICENSE`; `PROJECT.md` §12 separates pre-existing Sophia infrastructure from contest-period work |
| commercial APIs / closed-source models permitted only with disclosure | Only a **local** public model (Qwen2.5-7B-Instruct, immutable revision) via direct Transformers was used for Stage A. No commercial API call is in the package. The optional `run_model_attempts.py` discloses gateway/endpoint/cost/fallback policy. |
| building on an existing project — original source, entrant contribution, innovations, license compatibility clear | `PROJECT.md` §11–12; `RELATED-WORK.md` |
| all data sources, licenses, dependencies, versions disclosed | `requirements*.txt`; `OFFICIAL-RULES-CHECK.md`; `submission/submission-metadata.json` |

## Negative results are explicitly permitted

The handbook permits negative results provided the process and insight are
explainable. This submission **leads with its failures as integrity evidence**:
the retained malformed Lean response (23/24, not retried to 24/24), the
warm-cache admission failure, the dependency-resolution failures, and the
explicit `confirmatoryEligible:false` on the structurally-leaked rehearsal. See
`FAILURE-SHOWCASE.md`.

`candidateOnly:true`; `canClaimAGI:false`.
