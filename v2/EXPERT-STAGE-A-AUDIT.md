# Independent expert-AI Stage A implementation audit

**Review date:** August 1, 2026
**Reviewer transport:** direct Z.AI `glm-5.2` through the Anthropic-compatible
repository transport
**Fallback:** none
**Review mode:** read-only, adversarial source review
**Verdict:** **SAFE-TO-COMMIT**

The independent reviewer inspected:

- `stage_a.py`;
- `stage_a_model.py`;
- `stage_a_pro6000.py`;
- `.github/workflows/goai-stage-a-pro6000.yml`.

The review was explicitly asked to check:

1. exactly 24 public Stage A families, eight per domain, with all 30 public
   frontier tasks bound once and the three Lean open controls non-promotable;
2. strict structured model output, no task/family identifiers in prompts,
   task-ID/gold/self-approval/resource/claim-ceiling rejection, and no
   activation authority;
3. storage selection before CUDA/model contact, exact-holder GPU claim/release,
   immutable model revision, preflight without model-weight loading, and no
   confirmatory or winner path;
4. preservation of `candidateOnly:true`, `canClaimAGI:false`,
   `winnerLevelEligible:false`, and `winnerLevelGateMet:false`.

## Findings

- **P0:** none.
- **P1:** none.
- **P2:** none.

## Reviewer boundary

The reviewer validated the four supplied source files for structural
correctness, claim-ceiling enforcement, and fail-closed workflow logic. It did
not independently validate the task-manifest bytes, the external
`tools/gpu_guard.py` implementation, or live model-generation behavior.

Those unreviewed surfaces remain covered only by the package's deterministic
task/source bindings, repository GPU-guard tests and receipts, local adversarial
tests, workflow preflight, and any future live run. This audit is not approval
of a model-generated extension, not a scientific-domain review, and not a
confirmatory or capability result.

`candidateOnly:true`; `canClaimAGI:false`;
`winnerLevelEligible:false`; `winnerLevelGateMet:false`.
