#!/usr/bin/env python3
"""Revision-only self-correction ratchet (development-only simulation).

This module demonstrates a *revision-only* self-correction mechanism. A model
may detect and fix its OWN logic error, but it can **never** confirm a step as
correct on its own authority. Confirmation still requires the deterministic
verifier to re-run on the revised candidate and return ``accepted``.

The ratchet has exactly one direction: ``rejected`` -> ``revised`` -> (verifier
re-runs). It can never move ``rejected`` -> ``accepted`` by itself. This is the
single-load-bearing constraint, and it is enforced structurally:

* the original verdict and the revised verdict are BOTH produced by the
  deterministic ``verifier_fn`` passed in by the caller;
* this module never emits a verdict string of its own, never short-circuits a
  rejection into an acceptance, and never trusts a "looks right" signal from the
  critique stage;
* the ``final_verdict`` is whatever the verifier returned on the final candidate
  the ratchet actually produced — accepted only if the verifier said so.

SIMULATION HONESTY
------------------
In the TUI integration, the model's own critique would replace the
error-fixing heuristic. For this deterministic demo, the "fix" is a simple,
declared, per-tier heuristic:

* ``si`` dimension error: keep the candidate's numeric value, replace its unit
  with the reference's unit (this is the canonical "I had the right number, wrong
  unit" repair);
* ``si`` value error: substitute the reference value (the candidate was simply
  wrong by more than tolerance);
* ``sympy`` non-equivalence: substitute the reference expression itself;
* ``lean-placeholder`` (sorry/admit): substitute the reference proof term.

None of this is a model capability. The ``claim_ceiling`` is pinned:
``candidateOnly=True``, ``canClaimAGI=False``, ``winnerLevelEligible=False``.
This is instrument evidence that the ratchet plumbing is correct and fail-closed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_OUTPUT = HERE / "artifacts"
AUDIT_PATH = DEFAULT_OUTPUT / "self-correction-audit.json"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import demo  # noqa: E402
from v2 import build_logic_error_audit as audit  # noqa: E402

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

# The cap on how many revise passes the ratchet will allow. The preregistered
# secondary metric is "rejection-to-correct-revision recovery" — a single
# revision is the minimal, honest demonstration of the seam.
DEFAULT_MAX_REVISIONS = 1

# A bare leading number with optional sign / decimals / scientific notation, so
# we can lift "9.8" out of "9.8 m/s^2" without re-implementing the SI parser.
_LEADING_NUM = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


class VerifierLike(Protocol):
    """Minimal structural contract for a verifier callable.

    A verifier takes ``(candidate, reference)`` and returns an object exposing a
    ``verdict`` attribute that is one of ``"accepted"`` / ``"rejected"`` /
    ``"abstain"`` and a ``reason_code`` attribute. ``demo.verify_physics`` and
    ``demo.verify_math`` satisfy this directly.
    """

    def __call__(self, candidate: str, reference: str) -> Any: ...


@dataclass(frozen=True)
class SelfCorrectionResult:
    """Outcome of one revision-only self-correction attempt.

    Fields:
        original_verdict: the verifier's verdict on the original candidate.
        revised_verdict: the verifier's verdict on the revised candidate
            (identical to ``original_verdict`` when no revision was applied).
        correction_applied: True iff the ratchet produced and re-verified a
            revised candidate. This is the "did the model revise?" flag, NOT a
            "is the answer correct?" flag.
        correction_description: human-readable description of the heuristic
            applied (or why none was applied).
        final_verdict: the verdict that downstream code should treat as
            authoritative. It is always the verifier's verdict on the final
            candidate — never invented by this module.
        revised_candidate: the candidate produced by the heuristic (empty string
            when ``correction_applied`` is False). Exposed so callers and audits
            can see exactly what was re-verified.
        claim_ceiling: the frozen claim ceiling for this result. Self-correction
            never lifts it.
    """

    original_verdict: str
    revised_verdict: str
    correction_applied: bool
    correction_description: str
    final_verdict: str
    revised_candidate: str = ""
    claim_ceiling: dict[str, bool] = field(
        default_factory=lambda: dict(CLAIM_CEILING)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_verdict": self.original_verdict,
            "revised_verdict": self.revised_verdict,
            "correction_applied": self.correction_applied,
            "correction_description": self.correction_description,
            "final_verdict": self.final_verdict,
            "revised_candidate": self.revised_candidate,
            "claim_ceiling": dict(self.claim_ceiling),
        }


def _extract_leading_number(text: str) -> str | None:
    """Return the leading numeric token of an SI quantity, or ``None``."""
    m = _LEADING_NUM.match((text or "").strip())
    return m.group(0) if m else None


def _extract_reference_unit(reference: str) -> str | None:
    """Return the unit substring of a reference like ``"9.8 m/s"`` -> ``"m/s"``.

    Returns ``None`` if there is no numeric prefix to strip.
    """
    m = _LEADING_NUM.match((reference or "").strip())
    if not m:
        return None
    return reference.strip()[m.end():].strip() or None


def _heuristic_fix(
    candidate: str,
    reference: str,
    *,
    original_verdict: str,
    reason_code: str,
    tier: str,
) -> tuple[str, str]:
    """Return ``(revised_candidate, description)`` for one declared heuristic.

    This is the deterministic stand-in for the model's own critique. In the TUI
    integration the model's critique would go here; for this demo we use one
    simple, declared repair per tier so the ratchet can be exercised end-to-end
    with no model in the loop.
    """
    # SI tier: repair the candidate against the reference unit / value.
    if tier == "si":
        if reason_code == "dimension_mismatch":
            # "right number, wrong unit": keep the candidate's numeric value,
            # adopt the reference's unit.
            num = _extract_leading_number(candidate)
            unit = _extract_reference_unit(reference)
            if num is not None and unit:
                revised = f"{num} {unit}"
                return (
                    revised,
                    (
                        "heuristic: dimension_mismatch -> kept candidate's "
                        "numeric value and adopted the reference's SI unit"
                    ),
                )
            return (
                "",
                "heuristic skipped: could not isolate a numeric value and unit",
            )
        if reason_code == "value_mismatch":
            # wrong magnitude: substitute the reference quantity outright.
            return (
                reference,
                "heuristic: value_mismatch -> adopted the reference SI quantity",
            )
        # Any other SI rejection reason (e.g. unparseable reference) has no
        # declared deterministic repair — the ratchet declines to invent one.
        return (
            "",
            f"heuristic skipped: no declared SI repair for reason_code={reason_code!r}",
        )
    # SymPy tier: substitute the reference expression. (In a real model loop
    # this would be the model re-deriving the expression; here the verifier
    # itself is the ground truth, so adopting the reference is the honest
    # deterministic stand-in for "the model arrived at the canonical form".)
    if tier == "sympy":
        return (
            reference,
            "heuristic: not_symbolically_equivalent -> adopted the reference expression",
        )
    # Lean-placeholder tier: replace sorry/admit with the reference proof term.
    if tier == "lean-placeholder":
        return (
            reference,
            "heuristic: proof_placeholder -> replaced sorry/admit with the reference proof term",
        )
    return (
        "",
        f"heuristic skipped: no declared repair for tier={tier!r}",
    )


def attempt_self_correction(
    candidate: str,
    reference: str,
    *,
    verifier_fn: VerifierLike,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    tier: str | None = None,
) -> SelfCorrectionResult:
    """Run the revision-only ratchet once.

    Steps:
        1. Run the verifier on the original candidate -> ``original_verdict``.
        2. If the verdict is ``rejected`` and a revision budget remains, apply
           the declared per-tier heuristic to produce a revised candidate, then
           RE-RUN THE VERIFIER on it -> ``revised_verdict``.
        3. If the verdict is ``accepted`` or ``abstain``, no correction is
           applied: the ratchet never revises a non-rejection.

    The ``final_verdict`` is always the verifier's verdict on the final
    candidate. This module never emits "accepted" on its own authority.
    """
    original = verifier_fn(candidate, reference)
    original_verdict = getattr(original, "verdict", str(original))
    original_reason_code = getattr(original, "reason_code", "")
    original_tier = tier or getattr(original, "tier", "")

    if original_verdict != "rejected":
        return SelfCorrectionResult(
            original_verdict=original_verdict,
            revised_verdict=original_verdict,
            correction_applied=False,
            correction_description=(
                f"no correction applied: original verdict is {original_verdict!r}; "
                "the ratchet only revises on 'rejected'"
            ),
            final_verdict=original_verdict,
            revised_candidate="",
        )

    if max_revisions <= 0:
        return SelfCorrectionResult(
            original_verdict=original_verdict,
            revised_verdict=original_verdict,
            correction_applied=False,
            correction_description=(
                "no correction applied: revision budget is exhausted (max_revisions=0)"
            ),
            final_verdict=original_verdict,
            revised_candidate="",
        )

    revised_candidate, description = _heuristic_fix(
        candidate,
        reference,
        original_verdict=original_verdict,
        reason_code=original_reason_code,
        tier=original_tier,
    )

    if not revised_candidate:
        # The heuristic declined to produce a candidate (no declared repair).
        # The ratchet stays at the original rejection — it never invents a fix.
        return SelfCorrectionResult(
            original_verdict=original_verdict,
            revised_verdict=original_verdict,
            correction_applied=False,
            correction_description=description,
            final_verdict=original_verdict,
            revised_candidate="",
        )

    revised = verifier_fn(revised_candidate, reference)
    revised_verdict = getattr(revised, "verdict", str(revised))

    return SelfCorrectionResult(
        original_verdict=original_verdict,
        revised_verdict=revised_verdict,
        correction_applied=True,
        correction_description=description,
        final_verdict=revised_verdict,
        revised_candidate=revised_candidate,
    )


# ---------------------------------------------------------------------------
# Tier-specific verifier adapters for the audit.
# ---------------------------------------------------------------------------


def _make_verifier(tier: str) -> Callable[[str, str], Any]:
    """Return the deterministic verifier callable for one audit tier."""
    if tier == "si":
        return demo.verify_physics
    if tier == "sympy":
        return demo.verify_math
    if tier == "lean-placeholder":
        def _verify_lean(candidate: str, reference: str) -> Any:
            # Reuse the same routing the logic-error audit uses: the demo
            # rejects sorry/admit before any coverage abstention fires.
            return demo.verify_problem(
                demo.Problem(
                    problem_id="self-correct-lean-placeholder",
                    rung="closed",
                    tier="formal-proof",
                    prompt="self-correction placeholder audit",
                    gold=reference,
                ),
                candidate,
            )
        return _verify_lean
    raise ValueError(f"unknown audit tier: {tier!r}")


def _audit_one(planted: audit.PlantedError) -> dict[str, Any]:
    """Run one planted error through both arms of the audit."""
    verifier_fn = _make_verifier(planted.tier)

    # Arm A: WITHOUT self-correction — the verifier alone.
    without = attempt_self_correction(
        planted.candidate,
        planted.reference,
        verifier_fn=verifier_fn,
        max_revisions=0,
        tier=planted.tier,
    )
    # Arm B: WITH self-correction — the ratchet gets one revision.
    with_sc = attempt_self_correction(
        planted.candidate,
        planted.reference,
        verifier_fn=verifier_fn,
        max_revisions=DEFAULT_MAX_REVISIONS,
        tier=planted.tier,
    )

    return {
        "error_id": planted.error_id,
        "tier": planted.tier,
        "error_type": planted.error_type,
        "candidate": planted.candidate,
        "reference": planted.reference,
        "without_self_correction": {
            "final_verdict": without.final_verdict,
            "rejected": without.final_verdict == "rejected",
        },
        "with_self_correction": {
            "original_verdict": with_sc.original_verdict,
            "correction_applied": with_sc.correction_applied,
            "correction_description": with_sc.correction_description,
            "revised_candidate": with_sc.revised_candidate,
            "revised_verdict": with_sc.revised_verdict,
            "final_verdict": with_sc.final_verdict,
            "rejected": with_sc.final_verdict == "rejected",
            "accepted_after_revision": (
                with_sc.correction_applied
                and with_sc.original_verdict == "rejected"
                and with_sc.final_verdict == "accepted"
            ),
        },
    }


def run_self_correction_audit() -> dict[str, Any]:
    """Build the self-correction audit artifact over the planted logic errors.

    For each planted error this reports two arms:

    * WITHOUT self-correction: the deterministic verifier alone (which already
      catches every planted error — this is the logic-error-catch-rate result).
    * WITH self-correction: the ratchet applies its declared heuristic and the
      verifier re-runs on the revised candidate.

    The artifact is honest about being a SIMULATION: the "fix" is a deterministic
    per-tier heuristic, not a model's own critique. Two rates are reported so the
    ratchet's contribution is never confounded with the verifier's authority:

    * ``errorReductionRate`` — strict: the fraction of caught errors cleared to a
      full verifier ACCEPT. SI/SymPy reach 1.0 under the oracle-ish heuristic;
      the lean-placeholder tier honestly falls short because the compact package
      has no Lean backend, so the verifier ABSTAINS on the revised proof term.
    * ``rejectionClearedRate`` — looser: the fraction moved off 'rejected'
      (including to 'abstain'). This is 1.0 — every planted rejection is cleared
      by a revision, even when the verifier then cannot confirm.

    Neither rate is a model-capability or contest-performance number.
    """
    planted = audit.planted_errors()
    details = [_audit_one(p) for p in planted]
    total = len(details)

    caught_without = sum(1 for d in details if d["without_self_correction"]["rejected"])
    # "Fixed" = the verifier re-ran on the revised candidate and ACCEPTED it.
    # This is the strict, verifier-authoritative count: the ratchet only counts
    # a fix when the deterministic verifier confirms it.
    fixed_by_self_correction = sum(
        1 for d in details if d["with_self_correction"]["accepted_after_revision"]
    )
    # "Rejection cleared" = the final verdict is no longer 'rejected' (it may be
    # 'accepted' OR 'abstain'). The lean-placeholder tier demonstrates this
    # distinction cleanly: the heuristic replaces 'sorry' with the reference
    # proof term, the placeholder rejection is cleared, but the compact package
    # has no Lean backend so the verifier ABSTAINS rather than accepts. The
    # ratchet did its job (revised the candidate); the verifier is the authority
    # and honestly could not confirm. This is the ratchet working as designed.
    rejection_cleared_after = sum(
        1 for d in details if not d["with_self_correction"]["rejected"]
    )
    still_rejected_after = sum(
        1 for d in details if d["with_self_correction"]["rejected"]
    )
    abstained_after = sum(
        1
        for d in details
        if d["with_self_correction"]["final_verdict"] == "abstain"
    )

    # Headline error-reduction rate: of the errors the verifier caught WITHOUT
    # self-correction, the fraction the ratchet subsequently cleared to a full
    # verifier ACCEPT. This is the conservative, verifier-authoritative number.
    denom = caught_without if caught_without else 0
    error_reduction_rate = (
        round(fixed_by_self_correction / denom, 4) if denom else 0.0
    )
    rejection_cleared_rate = (
        round(rejection_cleared_after / denom, 4) if denom else 0.0
    )

    by_tier: dict[str, dict[str, int]] = {}
    for d in details:
        t = d["tier"]
        bucket = by_tier.setdefault(
            t,
            {
                "total": 0,
                "caught_without_self_correction": 0,
                "fixed_by_self_correction": 0,
                "rejection_cleared_after": 0,
                "abstained_after": 0,
                "still_rejected_after": 0,
            },
        )
        bucket["total"] += 1
        bucket["caught_without_self_correction"] += int(
            d["without_self_correction"]["rejected"]
        )
        bucket["fixed_by_self_correction"] += int(
            d["with_self_correction"]["accepted_after_revision"]
        )
        bucket["rejection_cleared_after"] += int(
            not d["with_self_correction"]["rejected"]
        )
        bucket["abstained_after"] += int(
            d["with_self_correction"]["final_verdict"] == "abstain"
        )
        bucket["still_rejected_after"] += int(
            d["with_self_correction"]["rejected"]
        )

    return {
        "schema": "goai-self-correction-audit/v1",
        "evidenceClass": "development-only",
        "status": "PASS",
        "interpretation": (
            "SIMULATION (not a model result). This audit demonstrates the "
            "revision-only self-correction ratchet: a model may detect and fix "
            "its OWN logic error, but it can NEVER confirm a step as correct on "
            "its own authority — the final ACCEPT must come from the "
            "deterministic verifier re-running on the revised candidate. The "
            "self-correction mechanism is demonstrated with deterministic "
            "error-fixing heuristics; in the TUI integration, the model's own "
            "critique would replace the heuristic. Two rates are reported: "
            "errorReductionRate is the strict verifier-authoritative number "
            "(fraction of caught errors cleared to a full verifier ACCEPT), and "
            "rejectionClearedRate is the looser number (fraction moved off "
            "'rejected', including to 'abstain'). The lean-placeholder tier "
            "illustrates the difference: the heuristic replaces 'sorry' with the "
            "reference proof term, the rejection is cleared, but the compact "
            "package has no Lean backend so the verifier ABSTAINS rather than "
            "accepts — the ratchet revised; the verifier, not the ratchet, "
            "decided. This is NOT a model-capability, capability-uplift, or "
            "contest-performance result."
        ),
        "mechanism": {
            "direction": "revision-only",
            "canSelfAccept": False,
            "finalAcceptanceAuthority": "deterministic-verifier",
            "maxRevisions": DEFAULT_MAX_REVISIONS,
            "simulationNote": (
                "the error-fixing step uses declared deterministic heuristics "
                "(SI: repair unit/value; SymPy: adopt reference expression; "
                "Lean-placeholder: replace sorry/admit). In the TUI integration "
                "the model's own critique replaces the heuristic."
            ),
        },
        "totals": {
            "planted": total,
            "caughtWithoutSelfCorrection": caught_without,
            "fixedBySelfCorrection": fixed_by_self_correction,
            # Moved off 'rejected' (to 'accepted' OR 'abstain') after revision.
            "rejectionClearedAfter": rejection_cleared_after,
            "abstainedAfter": abstained_after,
            "stillRejectedAfter": still_rejected_after,
            # errorReductionRate: strict, verifier-authoritative (cleared to a
            # full verifier ACCEPT). rejectionClearedRate: looser (moved off
            # 'rejected', including to 'abstain'). Under the deterministic
            # oracle-ish heuristic both are 1.0 for the SI/SymPy tiers; the
            # lean-placeholder tier abstains honestly. A real model's critique
            # would be strictly lower and would be reported as such.
            "errorReductionRate": error_reduction_rate,
            "rejectionClearedRate": rejection_cleared_rate,
        },
        "byTier": {
            t: {**v} for t, v in sorted(by_tier.items())
        },
        "details": details,
        "scientificOutcome": False,
        "capabilityClaim": False,
        **CLAIM_CEILING,
    }


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_audit(output_path: Path = AUDIT_PATH) -> dict[str, Any]:
    """Write the audit artifact in canonical (deterministic) byte form."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_payload = run_self_correction_audit()
    output_path.write_bytes(_canonical_bytes(audit_payload))
    return audit_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=AUDIT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive the canonical bytes and byte-compare against the on-disk artifact",
    )
    args = parser.parse_args()

    if args.check:
        if not args.output.is_file():
            print("SELF-CORRECTION AUDIT: FAIL (artifact missing)")
            return 1
        on_disk_bytes = args.output.read_bytes()
        expected = _canonical_bytes(run_self_correction_audit())
        if on_disk_bytes != expected:
            print("SELF-CORRECTION AUDIT: FAIL (bytes not canonical/current)")
            return 1
        on_disk = json.loads(args.output.read_text(encoding="utf-8"))
        if on_disk.get("status") != "PASS":
            print(f"SELF-CORRECTION AUDIT: FAIL (status={on_disk.get('status')})")
            return 1
        t = on_disk["totals"]
        print(
            "SELF-CORRECTION AUDIT: PASS "
            f"(planted={t['planted']}; "
            f"caughtWithoutSelfCorrection={t['caughtWithoutSelfCorrection']}; "
            f"fixedBySelfCorrection={t['fixedBySelfCorrection']}; "
            f"errorReductionRate={t['errorReductionRate']})"
        )
        return 0

    payload = write_audit(args.output)
    t = payload["totals"]
    print(
        json.dumps(
            {
                "schema": payload["schema"],
                "status": payload["status"],
                "totals": t,
                "byTier": payload["byTier"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
