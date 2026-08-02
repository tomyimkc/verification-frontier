# Reproducibility quickstart

> **No GPU, no network, no login, no model credentials required** to verify
> this package. Everything below is deterministic and CPU-only. Model contact
> is a separate, explicitly-selected, owner-authorized path.
>
> Tested Python: **3.12** (the v2 deterministic builders also run on 3.11+).
> The optional symbolic tier needs `sympy`; the no-deps path needs only the
> standard library.

## 1. Fastest verification (≈2 min, standard library only)

```bash
python3 demo.py --selfcheck                  # verifier, coverage, episode contracts
python3 v2/stage_a.py --check                # 24-family programme (8/8/8)
python3 v2/build_stage_a_result.py --check   # the real 23/24 Stage A result binding
python3 verify_bundle.py                     # deterministic ZIP integrity + claim ceiling
```

If all four print `PASS`/`SELF-CHECK PASSED`, the core evidence is intact.

### Logic-error catch-rate audit (strongest instrument evidence; needs `sympy`)

The 16/16 planted-logic-error catch-rate requires the optional symbolic tier.
Run it with the venv interpreter (which has `sympy`):

```bash
.venv/bin/python v2/build_logic_error_audit.py --check
# expect: LOGIC ERROR AUDIT: PASS (planted=16; caught=16; missed=0; catchRate=1.0)
```

(With bare `python3` and no `sympy`, the SymPy tier abstains and the audit
correctly reports a non-canonical result — the 16/16 figure is conditional on
the optional tier being installed, as designed.)

## 2. Full deterministic suite (≈2 min with the venv)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # sympy (optional symbolic tier)
.venv/bin/pip install -r requirements-docs.txt   # pypdf + reportlab (PDF build/verify)
./run_all.sh
```

`run_all.sh` runs, in order:
1. `demo.py --selfcheck` + 48 deterministic environment tests;
2. **140 v2 tests** (frontier, lean, protocol-twin, study-root, scorer, stage-a,
   stage-a-model, stage-a-pro6000, **stage-a-result**, receipt-protocol,
   run-model-attempts, score-confirmatory, task-manifest, validate-task-manifest);
3. hosted-demo logic + healthcheck (0 network / 0 model calls);
4. the bilingual four-page PDF build;
5. the deterministic ZIP build + `verify_bundle.py`.

Expected: every line reports PASS / OK; the final ZIP SHA-256 matches
`dist/GOAI-AI4R-Open-Exploration.zip.sha256`.

## 3. Verify the deterministic ZIP is byte-reproducible

The bundle is built from a frozen allowlist with fixed timestamps and a sorted
manifest, so two consecutive builds must be byte-identical:

```bash
.venv/bin/python build_bundle.py              # build #1
cp dist/GOAI-AI4R-Open-Exploration.zip /tmp/goai-build-1.zip
.venv/bin/python build_bundle.py              # build #2
cmp /tmp/goai-build-1.zip dist/GOAI-AI4R-Open-Exploration.zip && echo "BYTE-IDENTICAL"
shasum -a 256 dist/GOAI-AI4R-Open-Exploration.zip
# must match dist/GOAI-AI4R-Open-Exploration.zip.sha256
```

## 4. Trace any claim to its artifact

Every public claim is bound to a hash in [`EVIDENCE-TO-CLAIM-MATRIX.md`](EVIDENCE-TO-CLAIM-MATRIX.md).
To re-derive any artifact's SHA-256:

```bash
shasum -a 256 v2/artifacts/stage-a-development-result.json
# compare to the prefix in the evidence matrix and to MANIFEST.sha256 in the ZIP
```

## 5. Strict Lean development validation (optional, needs the pinned project)

The 48 Lean rows are validated against a pinned Lean 4.24.0 + Mathlib project
that is **not bundled** (Lean is external-receipt-only in the compact package).
If you have the project locally:

```bash
python3 v2/build_task_manifest.py
python3 v2/validate_task_manifest.py \
  --lean-project /path/to/pinned/miniF2F-lean4 \
  --require-lean \
  --timeout 90
```

## 6. Paths that are explicitly NOT in this CPU package

These require separate owner authorization and are **not** triggered by anything
above:

| Path | Why it's separate |
|---|---|
| Stage A model contact (Pro6000) | GPU + immutable model revision; one authorized run already recorded (`30742115988`) |
| Confirmatory B0–B6 execution | needs a frozen private 30-family benchmark, blinded review, protected suite, rollback |
| Hosted demo deployment | external owner-controlled action (`hosted-demo/` ships a no-login Gradio app + Dockerfile) |
| External contest upload | owner-only |

`candidateOnly:true`; `canClaimAGI:false`.
