# Independent expert-AI methodology validation

**Reviewer class:** independent methodology/statistics expert AI
**Review date:** July 31, 2026
**Access to v2 aggregate outcomes:** none; no v2 model outcomes existed
**Repository edits by reviewer:** none
**Verdict:** CONDITIONAL GO

## Executive finding

The pivot from boundary detection to human-gated verifier expansion is
scientifically meaningful only when a counted extension:

1. starts from a documented verifier abstention;
2. is reusable rather than a task-specific answer lookup;
3. is approved without access to confirmatory gold labels;
4. transfers to at least two sealed sibling tasks;
5. preserves paired safety siblings;
6. does not regress the protected verifier suite;
7. records proposal, diff, tests, approval, activation, and rollback state.

The previous six-task demonstration and novelty ladder establish instrument
behavior only. They do not demonstrate verification-frontier expansion.

## Required confirmatory design

The reviewer recommended a 144-task matched-pair benchmark:

| component | pairs | tasks |
|---|---:|---:|
| frontier valid + safety sibling | 60 | 120 |
| already-covered control pairs | 12 | 24 |
| **total** | **72** | **144** |

The 60 frontier pairs are balanced across physics, symbolic mathematics, and
Lean. The matched pair, not the model attempt or sampling replicate, is the
independent statistical unit.

## Primary endpoint

Safe Frontier-Pair Accuracy:

```text
pair success =
  valid member correctly machine-decided
  AND safety sibling rejected or abstained
  AND responsible extension passes transfer and regression obligations
```

Winner-level gates:

- zero unsafe acceptances among 60 frontier safety siblings;
- at least +20 percentage points over the strongest non-oracle baseline;
- 95% confidence-interval lower bound above zero;
- paired permutation/sign-flip p-value below 0.05;
- positive point-estimate delta in both required model families;
- no protected-suite regression.

## Required baselines

1. raw model;
2. fixed three-state verifier;
3. fixed verifier plus equal-budget refinement;
4. act-or-abstain policy without executable extension;
5. budget-matched human-only extension;
6. proposed human-gated system;
7. expert-authored oracle ceiling.

## Required ablations

- no human gate;
- no executable extension;
- no transfer requirement;
- forced binary accept/reject;
- remove physics, symbolic, and Lean tiers one at a time;
- fixed candidate replay versus interactive agent run;
- AI-assisted versus budget-matched human-only extension;
- visible versus hidden safety tests.

## Claim and related-work corrections

The reviewer confirmed three submission-visible metadata defects:

- AgentAbstain is `arXiv:2607.10059`, not `2607.17639`;
- RLVP expands to **Reinforcement Learning with Verifiable Physics**, not
  “Reward Learning from Verifiable Physics”;
- EG-VAR expands to **Evidence-Grounded Verified Agentic Reasoning**, not
  “Epistemic-Governed Verifiable Agentic Reasoning.”

The highest conceptual novelty risk is Recursive Epistemic Engines, which
already discusses guarded verifier expansion around a Novelty Horizon.
Defensible novelty therefore lies in prospective empirical evidence: a
preregistered, matched-pair, cross-domain benchmark of human-gated verifier
expansion with safety traps, hidden transfer, uncertainty, and public receipts.

## Final decision

- **GO** for preregistration, benchmark sealing, real model runs, Lean
  verification, and hosted-demo construction.
- **NO-GO** for presenting the old ladder or six-task demo as evidence of
  verification-frontier expansion.
- **CONDITIONAL GO** for a winner-level claim, contingent on transfer, safety,
  contamination, and protected-suite gates.

This validation is a methodology review. It is not a substitute for the
per-extension expert decisions required by the human gate.
