# V2 development failure record

`candidateOnly:true`; `canClaimAGI:false`

This local record preserves failures found while building the GOAI instrument.
It is not a capability or contest-result ledger.

## Shared Lean scratch path caused race-corrupted verdicts

**Status:** RESOLVED in the GOAI package on July 31, 2026

The inherited repository helper wrote every Lean check to one fixed
`LadderProbe.lean` inside the shared pinned Mathlib project. Concurrent
validators could overwrite that file between write and elaboration, producing a
verdict for another task.

Observed symptom:

- two intentionally invalid covered-control proofs were reported accepted
  during a repeated strict run;
- the shared scratch file was left containing one of those task sources;
- earlier serial runs had produced the expected rejection.

Correction:

- `v2/lean_verify.py` now creates a unique temporary Lean file per check;
- every file is removed in `finally`;
- `v2/test_lean_verify.py` exercises 24 concurrent unique scratch calls;
- a real 12-call parallel Lean check returned exactly 6 accepts and 6 rejects
  with zero leftover GOAI scratch files;
- both strict suites were rerun after the correction.

This defect invalidated the raced receipt. It did not establish a false
scientific result because no confirmatory efficacy run existed.

## Direct Z.AI smoke initially lacked its transport dependency

**Status:** RESOLVED on July 31, 2026

The package-local virtual environment contained SI, SymPy, PDF, and Gradio
dependencies but not the Anthropic-compatible SDK used by direct Z.AI.

The first rerun therefore emitted a fail-closed transport receipt:

```text
No module named 'anthropic'
```

No API call, token use, or fallback occurred. The failed response and run
manifest are retained under `v2/artifacts/` with the
`missing-anthropic` suffix.

Correction:

- added `requirements-models.txt`;
- installed the declared transport dependency;
- updated the GitHub development-model workflow to install it;
- reran the same one-task development smoke successfully with direct Z.AI and
  no fallback.

Neither the failed nor successful smoke is confirmatory evidence.
