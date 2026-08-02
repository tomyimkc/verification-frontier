# Architecture

> A judge-facing map of the system. The dotted line is the trust boundary —
> **where the LLM's probabilistic reasoning ends and deterministic logic-error
> detection begins.** Everything to its right is deterministic,
> content-addressed, or human-gated. No model output is ever an approval, and no
> model can cross the line alone. The verifiers (SI dimension+value, SymPy
> equivalence, Lean kernel) **are** the logic-error detectors: a dimension
> mismatch *is* a logic error, caught mechanically. A planted-logic-error audit
> catches **16/16 = 100%** of known errors across all three tiers
> (`v2/artifacts/logic-error-catch-rate.json`).

## End-to-end flow

```
                        ┌─────────────────────────────────────────────┐
                        │            FROZEN BEFORE SCORING             │
                        │  task hashes · pair hashes · base verifier   │
                        │  protected suite · typed abstain taxonomy    │
                        │  allowed patch classes · review rubric       │
                        │  model ids · prompts · budgets · thresholds  │
                        └────────────────────┬────────────────────────┘
                                             │
   ┌─────────────────────────────────────────┘
   │
   ▼
┌──────────────────┐    model proposes one    ┌─────────────────────────┐
│  frozen public   │  strict-JSON proposal    │  local public model     │
│  task family     │ ───────────────────────► │  (Qwen2.5-7B-Instruct,  │
│  (physics /      │    no task/family id     │   immutable revision,   │
│   symbolic /     │    in prompt             │   direct Transformers)  │
│   Lean)          │                          └───────────┬─────────────┘
└──────────────────┘                                      │
                                                          │  raw model text
═══════════════════════════════════════════════════════════╪═══════════════════
 ▲ TRUST BOUNDARY — model generation ends here; below is   │
 │ deterministic LOGIC-ERROR DETECTION. No model text       ▼
 │ is a cert. Verifiers catch 16/16 planted logic errors.   │
 │                  ┌──────────────────────────────────────────────────┐
 │                  │  strict parser + schema gate                      │
 │                  │  (malformed JSON retained, never retried to hide) │
 │                  └────────────┬─────────────────────────────────────┘
 │                               │  parsed proposal
 │                  ┌────────────▼─────────────────────────────────────┐
 │                  │  POLICY GATE  (seven fail-closed checks)          │
 │                  │  task-id branching · gold/answer smuggling        │
 │                  │  open-control promotion · missing test categories │
 │                  │  unbounded resource/authority · self-approval     │
 │                  │  missing claim ceiling                           │
 │                  └────────────┬─────────────────────────────────────┘
 │                               │  clean typed proposal / typed abstain
 │                  ┌────────────▼─────────────────────────────────────┐
 │   accept/reject  │  deterministic verifier tier = LOGIC-ERROR       │
 │   /abstain  ◄────┤  DETECTOR: SI dimension+value · SymPy equiv ·    │
 │                  │  Lean kernel (sorry/admit rejected before abstain)│
 │                  └────────────┬─────────────────────────────────────┘
 │            accepted │          │ abstain (coverage gap)
 │                keep │          ▼
 │                      │  propose BOUNDED extension (spec/verifier)    │
 │                      └────────────┬─────────────────────────────────┘
 │                                   │
 │              ┌────────────────────┴────────────────────┐
 │              ▼                                         ▼
 │   ┌─────────────────────┐                ┌──────────────────────────┐
 │   │  OWNER review       │                │  INDEPENDENT expert-AI   │
 │   │  (human, separate)  │                │  review (blinded, did    │
 │   │                     │                │  NOT see aggregate        │
 │   │  approve / defer    │                │  outcomes)                │
 │   └──────────┬──────────┘                └────────────┬─────────────┘
 │              │  both must approve                      │
 │              └──────────────────┬──────────────────────┘
 │                                 ▼
 │                  ┌──────────────────────────────────────────────────┐
 │                  │  VISIBLE TESTS (bounded executionBudget)         │
 │                  │  positive · negative · malformed · safety ·      │
 │                  │  rollback — ephemeral scratch, no network        │
 │                  └────────────┬─────────────────────────────────────┘
 │                               │ all pass
 │                  ┌────────────▼─────────────────────────────────────┐
 │                  │  ACTIVATION GATE  (local only, receipted)        │
 │                  │  activate extension OR preserve abstention       │
 │                  └────────────┬─────────────────────────────────────┘
 │                               │
 │                  ┌────────────▼─────────────────────────────────────┐
 │                  │  CONFIRMATORY STAGE  (B0–B6 + 8 ablations)       │
 │                  │  matched valid/safety pairs · hidden transfer ·  │
 │                  │  protected suite · rollback · full-resample      │
 │                  │  power/MDE · blinded review · clean reproduction │
 │                  └────────────┬─────────────────────────────────────┘
 │                               │
 └───────────────────────────────┴──►  content-addressed receipt DAG
            proposal# → owner# + expert# → tests# → activation#
                     → transfer# → protected-suite# → rollback# → chain#
```

## Where each gate currently sits

| Gate | State in this package | Why |
|---|---|---|
| Frozen task/verifier/policy | ✅ done | 24-family manifest, 150-row task manifest, pinned Lean |
| Model proposal collection | ✅ **done (development)** | real Stage A run 23/24 — but 0 approvals |
| Strict parser/schema/policy | ✅ done | seven policy totals at zero; malformed retained |
| Deterministic verifier tiers | ✅ done | SI + SymPy available; Lean external-receipt-only; **16/16 planted logic errors caught (100% catch-rate audit)** |
| Owner review | ⬜ not done | owner-only action |
| Independent expert-AI review | ⬜ not done | needs a fresh blinded reviewer (author saw aggregates) |
| Visible tests | ⬜ not done | 0 tests executed |
| Activation | ⬜ not done | 0 activations |
| Confirmatory B0–B6 + ablations | ⬜ not done | machinery built (Protocol Twin/Study Root), no real run |

## Content-addressed evidence DAG

Every transition above writes a content-addressed receipt (SHA-256 of canonical
JSON). A result is invalid if any link is missing, tampered, cross-linked,
self-declared-confirmatory, or lacks an independent review. The adversarial
benchmark exercises 7 such mutations; all 7 are rejected.

`candidateOnly:true`; `canClaimAGI:false`.
