# Safely Expanding the Verification Frontier of Scientific Agents

> GOAI 2026 前沿探索 / AI for Research — Open Exploration
> 中文：**安全扩展科学 Agent 的验证边界**

> **Judge entry point:** start at [`EXECUTIVE-SUMMARY.md`](EXECUTIVE-SUMMARY.md)
> (one page, bilingual). Then [`JUDGING-CROSSWALK.md`](JUDGING-CROSSWALK.md)
> (criteria → where addressed), [`ARCHITECTURE.md`](ARCHITECTURE.md),
> [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md), and
> [`REPRODUCIBILITY-QUICKSTART.md`](REPRODUCIBILITY-QUICKSTART.md).

This package makes verifier coverage an explicit environment state and adds a
prospective v2 experiment on whether that coverage can be expanded safely:

| verdict | meaning |
|---|---|
| `accepted` | an applicable deterministic check establishes the candidate |
| `rejected` | an applicable deterministic check establishes a concrete failure |
| `abstain` | no applicable executable check can decide; never a silent pass |

The contribution is an executable environment integration, not a claim to have
invented abstention, verification frontiers, dimensional analysis, SymPy, Lean,
or RLVR.

## Winner-oriented v2 study

The v1 six-problem demo remains the compact fallback. The primary research
direction is now a preregistered, human-gated verification-frontier expansion
study:

```text
typed abstention
  -> bounded verifier/specification proposal
  -> owner + independent expert-AI gate
  -> executable tests
  -> sealed transfer and safety siblings
  -> coverage delta with rollback receipts
```

The primary scored confirmatory design is **144 tasks / 72 matched pairs**:

- 60 frontier valid+safety pairs;
- 12 already-covered control pairs;
- 30 independent extension/generator families across physics, symbolic
  mathematics, and Lean.

A separate unscored auxiliary transfer pack adds 60 valid+safety pairs /
120 tasks: two transfer pairs per frontier family. The full future study corpus
is therefore 264 tasks, while SFPA remains defined over the 60 primary
frontier pairs.

The current 144-task artifact is a synthetic design rehearsal with only 15
families and known structural leakage. It is marked
`confirmatoryEligible:false`; no confirmatory seal or outcome exists. A future
benchmark must be generated privately and released after the preregistered run.

## What runs

- embedded SI dimension and numeric verification;
- optional SymPy symbolic equivalence;
- four deterministic reference policies;
- multi-step propose -> verify -> revise/stop episodes;
- JSONL step receipts;
- machine-readable benchmark summary;
- fail-closed artifact validation.

Lean-backed results are included only as pinned external evidence. **Lean is not
bundled in this compact package.**

## Quick start

Fail-closed standard-library path:

```bash
python3 demo.py --selfcheck
python3 -m unittest -v test_demo.py
python3 demo.py --benchmark --output-dir artifacts
python3 verify_artifacts.py artifacts
```

Full SI plus symbolic path:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-docs.txt
./run_all.sh
```

Development-only external model runner:

```bash
.venv/bin/pip install -r requirements-models.txt
.venv/bin/python v2/run_model_attempts.py --dry-run
```

This runner command requires a full `sophia-agi` checkout because it imports the
repository's `agent.model` transport; that transport is intentionally not copied
into the upload ZIP. Model credentials are read only from declared environment
variables, and cross-provider fallback is forbidden. Confirmatory execution is
hard-disabled in this milestone until the complete readiness-receipt lifecycle
is implemented and independently validated.

Public Stage A programme:

```bash
python3 v2/stage_a.py
python3 v2/stage_a.py --check
python3 -m unittest -v \
  v2.test_stage_a \
  v2.test_stage_a_model \
  v2.test_stage_a_pro6000
```

The generated Stage A artifacts contain exactly 24 families, bind all 30 public
frontier-gap tasks, and keep every future review/test/activation/confirmatory
gate false. The dispatch-only `GOAI Stage A Pro6000` workflow starts with
`mode=preflight`; it selects writable non-symlinked storage before claiming the
GPU or contacting CUDA/model services. One authorized `stage-a-run` has
completed on the Pro6000 Blackwell lane with Qwen2.5-7B-Instruct: **23/24
structured-output valid, one retained malformed Lean response, 2/2 open controls
preserved, and all seven policy-violation totals zero** — recorded immutably in
`v2/artifacts/stage-a-development-result.json`. This is structured-output and
policy-compliance evidence only; it cannot manufacture owner/expert approval or
activate an extension, and no rerun is authorized to improve the rate.

Interactive examples:

```bash
python3 demo.py
> ladder
> episode scripted-refine free-fall
> verify riemann-zeros "have h : True := trivial"
```

## Benchmark meaning

The included benchmark measures the deterministic environment and its reference
policies. It is **not** a model-capability benchmark.

Open examples lack executable formal specifications. Their correct environment
outcome is:

```text
ABSTAIN [coverage] unsupported_specification
```

That outcome does not prove that a model recognized an unsolved problem.

## Package map

| file | purpose |
|---|---|
| `EXECUTIVE-SUMMARY.md` | **one-page bilingual judge entry point** |
| `JUDGING-CROSSWALK.md` | official criteria → where addressed |
| `ARCHITECTURE.md` | judge-facing system diagram + trust boundary |
| `EVIDENCE-TO-CLAIM-MATRIX.md` | every claim → hash-bound artifact |
| `FAILURE-SHOWCASE.md` | retained failures as integrity evidence |
| `REPRODUCIBILITY-QUICKSTART.md` | CPU-only verify in ≈2 min |
| `demo.py` | verifier routing, episode loop, reference policies, self-check, benchmark |
| `units.py` | embedded SI engine |
| `test_demo.py` | deterministic environment tests |
| `verify_artifacts.py` | fail-closed receipt validation |
| `requirements.txt` | optional symbolic tier |
| `requirements-stage-a-gpu.txt` | pinned direct-Transformers dependencies; CUDA torch is installed separately |
| `run_all.sh` | one-command local run |
| `PROJECT.md` | full submission narrative and disclosure |
| `OFFICIAL-RULES-CHECK.md` | verified contest contract (deadline, criteria, weights) |
| `RELATED-WORK.md` | claim-safe primary-work comparison |
| `evidence/` | compact pinned evidence receipts |
| `artifacts/` | generated JSONL traces and benchmark summary |
| `submission/` | Simplified Chinese and English four-page sources/PDFs |
| `v2/` | preregistration, 24-family Stage A programme, guarded proposal runner, the real Stage A development result, synthetic rehearsal receipts, and family-clustered statistics |
| `dist/` | deterministic upload-ready ZIP plus SHA-256 |

## Claim ceiling

```json
{
  "candidateOnly": true,
  "canClaimAGI": false,
  "winnerLevelEligible": false,
  "winnerLevelGateMet": false
}
```

The environment and verification receipts are the submission. Low pass rates
are not presented as capability.
