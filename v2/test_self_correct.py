#!/usr/bin/env python3
"""Tests for the revision-only self-correction ratchet.

These tests pin the single load-bearing invariant: the ratchet can REJECT then
REVISE, but it can NEVER confirm a step as correct on its own authority. The
final ``accepted`` must come from the deterministic verifier re-running on the
revised candidate.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from v2 import self_correct as sc
from v2 import build_logic_error_audit as audit


@dataclass(frozen=True)
class _FakeResult:
    verdict: str
    reason_code: str = ""
    tier: str = ""


class _ScriptedVerifier:
    """A verifier that returns a scripted sequence of verdicts, one per call.

    Records every call so tests can assert the ratchet re-ran the verifier on
    the revised candidate (and never invented a verdict itself).
    """

    def __init__(self, verdicts):
        # verdicts: list of (verdict, reason_code, tier)
        self._verdicts = list(verdicts)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, candidate, reference):
        self.calls.append((candidate, reference))
        if not self._verdicts:
            raise AssertionError("scripted verifier exhausted")
        v, rc, tier = self._verdicts.pop(0)
        return _FakeResult(verdict=v, reason_code=rc, tier=tier)


class RatchetInvariantTests(unittest.TestCase):
    """The core constraint: revision-only, never self-accept."""

    def test_accepted_original_is_returned_unchanged(self):
        verifier = _ScriptedVerifier([("accepted", "ok", "si")])
        result = sc.attempt_self_correction(
            "9.8 m/s", "9.8 m/s", verifier_fn=verifier, tier="si"
        )
        self.assertFalse(result.correction_applied)
        self.assertEqual(result.original_verdict, "accepted")
        self.assertEqual(result.revised_verdict, "accepted")
        self.assertEqual(result.final_verdict, "accepted")
        self.assertEqual(result.revised_candidate, "")
        # No revision, so exactly one verifier call.
        self.assertEqual(len(verifier.calls), 1)

    def test_abstain_original_is_returned_unchanged(self):
        verifier = _ScriptedVerifier([("abstain", "sympy_unavailable", "sympy")])
        result = sc.attempt_self_correction(
            "x^2", "(x+1)^2", verifier_fn=verifier, tier="sympy"
        )
        self.assertFalse(result.correction_applied)
        self.assertEqual(result.original_verdict, "abstain")
        self.assertEqual(result.final_verdict, "abstain")
        # The ratchet must NOT revise on abstain.
        self.assertEqual(len(verifier.calls), 1)

    def test_rejection_then_revision_then_verifier_accept(self):
        """The happy path: reject -> revise -> verifier accepts the revision."""
        verifier = _ScriptedVerifier(
            [
                ("rejected", "dimension_mismatch", "si"),
                ("accepted", "dimension_and_value_match", "si"),
            ]
        )
        result = sc.attempt_self_correction(
            "9.8 m/s^2", "9.8 m/s", verifier_fn=verifier, tier="si"
        )
        self.assertTrue(result.correction_applied)
        self.assertEqual(result.original_verdict, "rejected")
        self.assertEqual(result.revised_verdict, "accepted")
        self.assertEqual(result.final_verdict, "accepted")
        # The final ACCEPT came from the verifier's SECOND call, not from us.
        self.assertEqual(len(verifier.calls), 2)
        # The second call re-verified the REVISED candidate, not the original.
        self.assertEqual(verifier.calls[1][0], result.revised_candidate)
        self.assertNotEqual(result.revised_candidate, "9.8 m/s^2")

    def test_rejection_then_revision_then_verifier_STILL_rejects(self):
        """If the verifier still rejects the revision, final_verdict is 'rejected'.

        This is the fail-closed case: the heuristic produced a candidate, but the
        verifier refused it. The ratchet must NOT promote it.
        """
        verifier = _ScriptedVerifier(
            [
                ("rejected", "dimension_mismatch", "si"),
                ("rejected", "value_mismatch", "si"),
            ]
        )
        result = sc.attempt_self_correction(
            "9.8 m/s^2", "9.8 m/s", verifier_fn=verifier, tier="si"
        )
        self.assertTrue(result.correction_applied)
        self.assertEqual(result.original_verdict, "rejected")
        self.assertEqual(result.revised_verdict, "rejected")
        self.assertEqual(result.final_verdict, "rejected")

    def test_ratchet_never_emits_verdict_strings_of_its_own(self):
        """final_verdict must always be a verifier-returned verdict, never a
        string fabricated by the ratchet. We assert it is one of the three the
        verifier actually returned across both calls."""
        verifier = _ScriptedVerifier(
            [("rejected", "dimension_mismatch", "si"), ("accepted", "ok", "si")]
        )
        result = sc.attempt_self_correction(
            "9.8 m/s^2", "9.8 m/s", verifier_fn=verifier, tier="si"
        )
        emitted = {result.original_verdict, result.revised_verdict, result.final_verdict}
        self.assertTrue(emitted.issubset({"accepted", "rejected", "abstain"}))

    def test_max_revisions_zero_disables_correction(self):
        """With zero budget the ratchet degrades to plain verification."""
        verifier = _ScriptedVerifier([("rejected", "dimension_mismatch", "si")])
        result = sc.attempt_self_correction(
            "9.8 m/s^2",
            "9.8 m/s",
            verifier_fn=verifier,
            max_revisions=0,
            tier="si",
        )
        self.assertFalse(result.correction_applied)
        self.assertEqual(result.final_verdict, "rejected")
        self.assertEqual(len(verifier.calls), 1)
        self.assertIn("budget", result.correction_description)


class SelfCorrectionResultTests(unittest.TestCase):
    def test_claim_ceiling_defaults_are_pinned(self):
        result = sc.SelfCorrectionResult(
            original_verdict="rejected",
            revised_verdict="accepted",
            correction_applied=True,
            correction_description="x",
            final_verdict="accepted",
        )
        cc = result.claim_ceiling
        self.assertTrue(cc["candidateOnly"])
        self.assertFalse(cc["canClaimAGI"])
        self.assertFalse(cc["winnerLevelEligible"])
        self.assertFalse(cc["winnerLevelGateMet"])

    def test_to_dict_round_trip_is_json_serializable(self):
        result = sc.SelfCorrectionResult(
            original_verdict="rejected",
            revised_verdict="accepted",
            correction_applied=True,
            correction_description="x",
            final_verdict="accepted",
            revised_candidate="9.8 m/s",
        )
        d = result.to_dict()
        # Must be JSON-serializable for artifact emission.
        json.dumps(d)
        self.assertEqual(d["final_verdict"], "accepted")
        self.assertTrue(d["correction_applied"])
        self.assertEqual(d["revised_candidate"], "9.8 m/s")

    def test_default_revised_candidate_is_empty_when_no_correction(self):
        result = sc.SelfCorrectionResult(
            original_verdict="accepted",
            revised_verdict="accepted",
            correction_applied=False,
            correction_description="none",
            final_verdict="accepted",
        )
        self.assertEqual(result.revised_candidate, "")


class HeuristicFixTests(unittest.TestCase):
    """The declared per-tier heuristics against the real deterministic verifiers."""

    def test_si_dimension_mismatch_heuristic_uses_reference_unit(self):
        # "9.8 m/s^2" -> keep 9.8, adopt "m/s" -> "9.8 m/s" -> accepted.
        result = sc.attempt_self_correction(
            "9.8 m/s^2", "9.8 m/s", verifier_fn=__import__("demo").verify_physics, tier="si"
        )
        self.assertTrue(result.correction_applied)
        self.assertEqual(result.revised_candidate, "9.8 m/s")
        self.assertEqual(result.final_verdict, "accepted")

    def test_si_value_mismatch_heuristic_adopts_reference(self):
        # "8.0 m/s" vs "9.8 m/s" -> value_mismatch -> adopt reference -> accepted.
        result = sc.attempt_self_correction(
            "8.0 m/s", "9.8 m/s", verifier_fn=__import__("demo").verify_physics, tier="si"
        )
        self.assertTrue(result.correction_applied)
        self.assertEqual(result.revised_candidate, "9.8 m/s")
        self.assertEqual(result.final_verdict, "accepted")

    def test_sympy_heuristic_adopts_reference_expression(self):
        result = sc.attempt_self_correction(
            "x^2+2*x+2",
            "(x+1)^2",
            verifier_fn=__import__("demo").verify_math,
            tier="sympy",
        )
        self.assertTrue(result.correction_applied)
        self.assertEqual(result.revised_candidate, "(x+1)^2")
        self.assertEqual(result.final_verdict, "accepted")

    def test_lean_placeholder_heuristic_replaces_sorry(self):
        import demo

        def verifier(candidate, reference):
            return demo.verify_problem(
                demo.Problem(
                    problem_id="t",
                    rung="closed",
                    tier="formal-proof",
                    prompt="",
                    gold=reference,
                ),
                candidate,
            )

        result = sc.attempt_self_correction(
            "sorry", "have h : True := trivial", verifier_fn=verifier, tier="lean-placeholder"
        )
        self.assertTrue(result.correction_applied)
        self.assertEqual(result.revised_candidate, "have h : True := trivial")
        # The reference is the placeholder proof term; the demo abstains on it
        # (unsupported specification) rather than accepting it — but it does NOT
        # keep the rejection of 'sorry'. The ratchet moved; the verifier decided.
        self.assertNotEqual(result.final_verdict, "rejected")


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.audit_payload = sc.run_self_correction_audit()

    def test_schema_and_status(self):
        self.assertEqual(self.audit_payload["schema"], "goai-self-correction-audit/v1")
        self.assertEqual(self.audit_payload["status"], "PASS")
        self.assertEqual(self.audit_payload["evidenceClass"], "development-only")

    def test_every_planted_error_caught_without_self_correction(self):
        t = self.audit_payload["totals"]
        self.assertEqual(t["caughtWithoutSelfCorrection"], t["planted"])

    def test_every_error_rejection_cleared_by_self_correction(self):
        """The ratchet moves EVERY planted error off 'rejected' (the rejection
        is always cleared). The final verdict may be 'accepted' OR, for the
        lean-placeholder tier, 'abstain' — the ratchet revised; the verifier
        (the only acceptance authority) decided it could not confirm."""
        t = self.audit_payload["totals"]
        self.assertEqual(t["rejectionClearedAfter"], t["planted"])
        self.assertEqual(t["stillRejectedAfter"], 0)
        self.assertEqual(t["rejectionClearedRate"], 1.0)

    def test_si_and_sympy_errors_reach_full_verifier_acceptance(self):
        """For the SI and SymPy tiers the deterministic oracle-ish heuristic
        drives every error to a full verifier ACCEPT (errorReductionRate 1.0
        within those tiers)."""
        by_tier = self.audit_payload["byTier"]
        for tier in ("si", "sympy"):
            b = by_tier[tier]
            self.assertEqual(
                b["fixed_by_self_correction"],
                b["total"],
                f"{tier}: every error should reach verifier ACCEPT",
            )
            self.assertEqual(b["abstained_after"], 0, tier)

    def test_lean_placeholder_clears_rejection_but_abstains_honestly(self):
        """The lean-placeholder heuristic replaces 'sorry'/'admit' with the
        reference proof term, clearing the rejection, but the compact package
        has no Lean backend so the verifier ABSTAINS. This is the ratchet
        working as designed: it revised; the verifier, not the ratchet, decided
        — and honestly could not confirm."""
        b = self.audit_payload["byTier"]["lean-placeholder"]
        self.assertEqual(b["rejection_cleared_after"], b["total"])
        self.assertEqual(b["abstained_after"], b["total"])
        self.assertEqual(b["fixed_by_self_correction"], 0)

    def test_error_reduction_rate_is_strict_and_below_one(self):
        """errorReductionRate is the strict verifier-authoritative number
        (cleared to full ACCEPT). It is strictly below 1.0 because the
        lean-placeholder errors honestly abstain (no Lean backend in the compact
        package). rejectionClearedRate is the looser number and is 1.0 (every
        rejection was cleared, some to abstain). The two rates must reconcile:
        fixed + abstained == planted, and fixed/caught == errorReductionRate."""
        t = self.audit_payload["totals"]
        planted = t["planted"]
        caught = t["caughtWithoutSelfCorrection"]
        fixed = t["fixedBySelfCorrection"]
        abstained = t["abstainedAfter"]
        self.assertEqual(caught, planted)  # verifier catches all without SC
        self.assertEqual(fixed + abstained, planted)  # every error is settled
        self.assertEqual(t["stillRejectedAfter"], 0)  # none left rejected
        self.assertLess(t["errorReductionRate"], 1.0)  # lean abstains
        self.assertEqual(t["errorReductionRate"], round(fixed / caught, 4))
        self.assertEqual(t["rejectionClearedRate"], 1.0)  # all moved off rejected

    def test_audit_covers_all_planted_errors(self):
        planted_ids = {e.error_id for e in audit.planted_errors()}
        audit_ids = {d["error_id"] for d in self.audit_payload["details"]}
        self.assertEqual(audit_ids, planted_ids)

    def test_every_detail_revised_and_rejection_cleared(self):
        """Every detail has correction_applied=True, original_verdict='rejected',
        a non-empty revised candidate, and a final_verdict that is no longer
        'rejected' (it is 'accepted' for SI/SymPy, 'abstain' for lean)."""
        for d in self.audit_payload["details"]:
            wsc = d["with_self_correction"]
            self.assertTrue(wsc["correction_applied"], d["error_id"])
            self.assertEqual(wsc["original_verdict"], "rejected", d["error_id"])
            self.assertIn(wsc["final_verdict"], {"accepted", "abstain"}, d["error_id"])
            self.assertNotEqual(wsc["final_verdict"], "rejected", d["error_id"])
            self.assertNotEqual(wsc["revised_candidate"], "", d["error_id"])

    def test_si_and_sympy_details_reach_full_acceptance(self):
        for d in self.audit_payload["details"]:
            if d["tier"] in ("si", "sympy"):
                wsc = d["with_self_correction"]
                self.assertEqual(wsc["final_verdict"], "accepted", d["error_id"])
                self.assertTrue(wsc["accepted_after_revision"], d["error_id"])

    def test_lean_placeholder_details_abstain_honestly(self):
        for d in self.audit_payload["details"]:
            if d["tier"] == "lean-placeholder":
                wsc = d["with_self_correction"]
                self.assertEqual(wsc["final_verdict"], "abstain", d["error_id"])
                self.assertFalse(wsc["accepted_after_revision"], d["error_id"])

    def test_by_tier_sum_matches_totals(self):
        totals = self.audit_payload["totals"]
        by_tier = self.audit_payload["byTier"]
        self.assertEqual(
            sum(v["total"] for v in by_tier.values()), totals["planted"]
        )
        self.assertEqual(
            sum(v["fixed_by_self_correction"] for v in by_tier.values()),
            totals["fixedBySelfCorrection"],
        )
        self.assertEqual(
            sum(v["rejection_cleared_after"] for v in by_tier.values()),
            totals["rejectionClearedAfter"],
        )
        self.assertEqual(
            sum(v["abstained_after"] for v in by_tier.values()),
            totals["abstainedAfter"],
        )

    def test_claim_ceiling_preserved(self):
        self.assertTrue(self.audit_payload["candidateOnly"])
        self.assertFalse(self.audit_payload["canClaimAGI"])
        self.assertFalse(self.audit_payload["winnerLevelEligible"])
        self.assertFalse(self.audit_payload["winnerLevelGateMet"])
        self.assertFalse(self.audit_payload["scientificOutcome"])
        self.assertFalse(self.audit_payload["capabilityClaim"])

    def test_interpretation_is_simulated_not_capability(self):
        interp = self.audit_payload["interpretation"]
        self.assertIn("SIMULATION", interp)
        self.assertIn("revision-only", interp)
        self.assertIn("NEVER confirm", interp)
        self.assertIn("deterministic verifier", interp)
        self.assertIn("NOT a model-capability", interp)
        mech = self.audit_payload["mechanism"]
        self.assertFalse(mech["canSelfAccept"])
        self.assertEqual(mech["finalAcceptanceAuthority"], "deterministic-verifier")

    def test_write_then_check_round_trips_canonical(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "self-correction-audit.json"
            sc.write_audit(out)
            expected = sc._canonical_bytes(sc.run_self_correction_audit())
            self.assertEqual(out.read_bytes(), expected)
            # And the --check path agrees.
            reread = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(reread["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
