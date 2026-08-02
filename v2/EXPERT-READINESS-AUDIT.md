# Independent expert-AI confirmatory-readiness audit

**Review date:** July 31, 2026  
**Reviewed snapshot:** merged GOAI v2 infrastructure at commit `26862e688`  
**Review mode:** read-only methodology and adversarial scorer audit  
**Confirmatory outcomes available:** none  
**Verdict:** **NO-GO for confirmatory execution**; **CONDITIONAL GO for a
preliminary infrastructure proposal**

This review assessed whether the merged instrument could support a scientifically
consumable future result. It did not review or certify a capability outcome.

## Deciding findings

### 1. Counterfeit evidence could satisfy the old scorer

The reviewed scorer checked whether extension and decision references looked
like SHA-256 values, but did not resolve the files or verify their contents.
A complete synthetic result matrix using fake hashes and nonexistent transfer
IDs could therefore return `winnerLevelGateMet:true`.

**Correction in the next development milestone:** the scorer now requires a
receipt store and resolves a content-addressed chain containing proposal,
independent decisions, typed tests, activation, transfer, protected-suite,
rollback, and Lean receipts. Missing files, symlinks, byte mutations,
non-canonical JSON, and broken cross-links fail closed. Development receipts
cannot be reused as confirmatory evidence, and self-declared confirmatory chains
remain disabled.

### 2. A pooled comparator could hide a model-family loss

The reviewed scorer selected one globally strongest baseline, then compared
every required model family against that pooled choice. A constructed result
could pass even when the proposed arm lost by 20 percentage points to Qwen's
actual strongest baseline.

**Correction in the next development milestone:** each required model family is
now compared against its own strongest non-oracle baseline. A model-specific
reversal fails the cross-model gate even when pooled results are positive.

### 3. Effect wording exceeded the implemented inference

The design required an observed point estimate of at least 20 percentage points
and a confidence-interval lower bound above zero. That supports evidence of a
positive effect whose observed estimate is at least 20 points; it does not
establish that the population effect itself is at least 20 points.

**Correction:** the preregistration and submission wording now state that
distinction explicitly.

## Remaining P0 blockers

The corrections above remove two fail-open scorer defects. They do not make the
study ready for confirmatory execution. The following remain:

1. build a full B0-B6 shadow executor plus all eight preregistered ablations;
2. bind identical candidate-trajectory hashes across primary replay arms;
3. instantiate the declared 24-family Stage A extension-development program;
4. generate a genuinely private 30-family Stage B benchmark with provenance and
   independence attestations, not only distinct family labels;
5. bind prompts, model revisions, budgets, randomization, runner, scorer,
   rubric, protected suite, and extension bundle into one readiness root;
6. run a large mutation suite with zero false passes and zero false rejects on
   valid fixtures;
7. perform a preregistered operating-characteristic/power simulation through
   the exact final scorer;
8. freeze reviewer identities, blinded assignment, counterbalanced order, and
   equal-budget accounting for human-only versus AI-assisted arms;
9. complete repository, benchmark, and public-web contamination adjudication;
10. add OS-level Lean sandboxing and clean Linux reproduction.

## Recommended next acceptance bars

- at least 100 invalid receipt-DAG mutation fixtures: **0 false passes**;
- at least 20 fully valid receipt-DAG fixtures: **0 false rejects**;
- the model-family reversal fixture must always return
  `winnerLevelGateMet:false`;
- missing any required arm or ablation must return `INVALID`;
- primary replay candidate bytes and hashes must be identical across declared
  comparison arms;
- the exact final scorer must show null false-positive rate at or below 0.05 and
  at least 0.80 power at the prospectively selected design alternative;
- a single readiness root must fail if any bound descendant is absent or
  changed.

## Claim boundary

Current evidence supports instrument mechanics only. There is still no
confirmatory effect, transfer result, protected-suite result, safety result, or
scientific-domain reproduction.

`candidateOnly:true`; `canClaimAGI:false`.

## Final re-audit

After receipt resolution, per-model comparator selection, development winner
ineligibility, and the row-identity cache regression were corrected, the
independent methodology reviewer returned **GO for merging the development
milestone**.

The reviewer separately retained **NO-GO for confirmatory execution** because
the Stage A/Stage B samples, full arms and ablations, power simulation, blinded
reviewer protocol, contamination adjudication, readiness root, and OS-level
Lean sandbox are still missing.
