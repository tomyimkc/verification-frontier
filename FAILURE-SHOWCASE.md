# Failure-case showcase

> Per the handbook, **negative results are permitted** if the process and
> insight are explainable. This package leads with its failures as **integrity
> evidence**, not capability evidence. Nothing here was hidden or retried to
# manufacture a cleaner number.

## 0. Logic errors the verifiers catch (positive integrity evidence)

Before the failures, the strongest piece of integrity evidence: **the verifiers
work.** A logic-error catch-rate audit plants 16 known logic errors across every
verifier tier and records whether each was caught. The verifiers **are** the
logic-error detectors — a dimension mismatch *is* a logic error, a non-equivalent
expression *is* a logic error, a `sorry`/`admit` placeholder *is* a logic error.
This is instrument evidence (the verifiers are real and fail-closed), **not** a
model-capability claim.

- **Bound artifact:** `v2/artifacts/logic-error-catch-rate.json` (SHA-256 `eaa5d302…`)
- **Verify:** `python3 v2/build_logic_error_audit.py --check` (needs `sympy`; use `.venv/bin/python`)
- **Result:** **16/16 caught = 100% catch-rate**, 0 misses.

| Tier | Planted | Caught | Examples of logic errors caught |
|---|---:|---:|---|
| SI dimension+value | 8 | 8 | `9.8 m/s²` where `9.8 m/s` meant (dimension mismatch); `8.0 m/s` where `9.8 m/s` meant (value out of tolerance); `5 kg` for `5 N`; `12 W` for `12 J` |
| SymPy equivalence | 6 | 6 | `x²+2x+2` for `(x+1)²` (not equivalent); `(x−1)²` for `(x+1)²` (sign error); `2x+1` (missing term); `x³+1` (wrong degree) |
| Lean proof-placeholder | 2 | 2 | `sorry` and `admit` placeholders rejected **before** any coverage abstention |
| **Total** | **16** | **16** | **catchRate = 1.0** |

- **Signal type:** positive instrument evidence + stable negative (the verifiers
  reject every planted logic error, and the rejection is byte-stable under the
  canonical-bytes check).
- **Scope it does NOT claim:** this is a *planted*-error catch-rate. It does not
  say what fraction of an unseen LLM's logic errors are in-scope — that is the
  open research question the human-gated frontier expansion is built to answer.

## 1. Retained malformed JSON response (Stage A)

- **Family:** `stage-a-lean-01-executable-contract`
- **Error:** `malformed JSON at line 6 column 70: Invalid control character`
  (an unescaped newline inside a Lean-formalization JSON field).
- **Disposition:** **retained as invalid**, not retried. The all-24 result is
  therefore **23/24**, and this is disclosed immutably in
  `v2/artifacts/stage-a-development-result.json`.
- **Why it matters:** a project that silently retries malformed responses until
  it hits 24/24 would be reporting sampling luck, not structured-output
  compliance. The malformed row *is* the evidence that the parser is real and
  fail-closed.
- **Signal type:** failure mode + stable negative (the parser rejects, and the
  rejection is preserved across the canonical-bytes check).

## 2. Warm-cache storage-admission failure (first all-24 attempt)

- **Run:** `30729611283` (exact head `d2daa02911…`)
- **What happened:** the successful 3-family smoke populated the persistent
  15.24 GB model cache, leaving ~21.0 GiB free — below the 32 GiB cold-cache
  admission floor. The run **stopped at the initial storage gate, before any
  GPU claim, CUDA contact, model contact, revision resolution, weight load, or
  proposal generation**.
- **Receipt:** `gpuClaimed:false`, `gpuReleased:false`, `modelRevision:null`,
  `status:failure`.
- **Correction (merged PR #1813):** the storage gate now distinguishes a
  cold-cache `preflight` (32 GiB floor) from a development `stage-a-run`
  (20 GiB operational reserve), while keeping the authoritative host gate
  `ceil(1.20 × missingBytes + 4 GiB)` before any model-weight load.
- **Signal type:** anomaly + justified problem revision (the gate was correct
  to stop; the *floor policy* was the bug).

## 3. Dependency-resolution failures (two preflights)

- **Runs:** `30724109619` then `30725934502`
- **What happened:** `transformers==5.13.1` requires
  `huggingface-hub>=1.5.0,<2.0` and `safetensors>=0.8.0`; the merged
  requirements pinned incompatible older versions. Both preflights failed
  during `pip` resolution, **before any host/model-feasibility or proposal
  step**; `modelRevision:null`; no model load occurred.
- **Correction (merged PRs #1808, #1810):** a Python 3.12 pip-resolver dry-run
  closed the full 29-package dependency set with synthetic preinstalled Torch.
  After that, preflight `30727627325` succeeded.
- **Signal type:** failure mode + counterexample (one-pin blind retries do not
  work; full dependency closure does). The third preflight was explicitly gated
  on the closure fix, not a blind retry.

## 4. Open-control preservation (non-promotable abstention)

- **What happened:** two Lean open-problem control families were presented to
  the model. Both were preserved as **abstentions** (`openControlPromotion: 0`).
- **Why it matters:** an open control is a task with no executable specification.
  If a model "solved" it, that would be a silent pass or gold smuggling. The
  package's policy gate rejects open-control promotion; the count is zero and
  the checker enforces it.
- **Signal type:** stable negative + safety (the system correctly refuses to
  over-claim on unsolved problems).

## 5. Synthetic-rehearsal structural leakage (self-audit)

- **What happened:** independent audit found the 144-task rehearsal had only 15
  generator families (not 30), 70 seed-independent rows, 14 duplicate prompts,
  and public structural leakage through the former generator/oracle.
- **Disposition:** the rehearsal is retained but explicitly marked
  `confirmatoryEligible:false`. Its generator/oracle were moved behind the
  ignored private boundary and are **not bundled**. Confirmatory execution is
  hard-blocked in code until a genuinely private 30-family benchmark exists.
- **Signal type:** counterexample + justified problem revision (the instrument
  was flawed; the flaw is disclosed rather than papered over).

`candidateOnly:true`; `canClaimAGI:false`.
