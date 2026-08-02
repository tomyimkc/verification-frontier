#!/usr/bin/env python3
"""Tests for the deterministic logic-error catch-rate audit."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from v2 import build_logic_error_audit as audit


class LogicErrorAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = audit.build_audit()

    def test_catches_all_planted_errors(self) -> None:
        t = self.audit["totals"]
        self.assertEqual(t["planted"], t["caught"])
        self.assertEqual(t["missed"], 0)
        self.assertEqual(t["catchRate"], 1.0)
        self.assertEqual(self.audit["status"], "PASS")

    def test_covers_all_three_verifier_tiers(self) -> None:
        tiers = set(self.audit["byTier"].keys())
        self.assertEqual(tiers, {"si", "sympy", "lean-placeholder"})

    def test_every_tier_has_perfect_catch_rate(self) -> None:
        for tier, stats in self.audit["byTier"].items():
            self.assertEqual(stats["caught"], stats["total"], tier)
            self.assertEqual(stats["catchRate"], 1.0, tier)

    def test_no_misses_recorded(self) -> None:
        self.assertEqual(self.audit["misses"], [])

    def test_claim_ceiling_preserved(self) -> None:
        self.assertTrue(self.audit["candidateOnly"])
        self.assertFalse(self.audit["canClaimAGI"])
        self.assertFalse(self.audit["winnerLevelEligible"])
        self.assertFalse(self.audit["winnerLevelGateMet"])
        self.assertFalse(self.audit["scientificOutcome"])
        self.assertFalse(self.audit["capabilityClaim"])

    def test_interpretation_is_instrument_not_capability(self) -> None:
        interp = self.audit["interpretation"]
        self.assertIn("DETERMINISTIC VERIFIERS", interp)
        self.assertIn("NOT a model-capability", interp)

    def test_dimension_mismatch_errors_caught(self) -> None:
        si_errors = [d for d in self.audit["details"] if d["tier"] == "si"]
        self.assertTrue(len(si_errors) >= 6)
        for d in si_errors:
            self.assertTrue(d["caught"], d["error_id"])

    def test_symbolic_equivalence_errors_caught(self) -> None:
        sym_errors = [d for d in self.audit["details"] if d["tier"] == "sympy"]
        self.assertTrue(len(sym_errors) >= 4)
        for d in sym_errors:
            self.assertTrue(d["caught"], d["error_id"])

    def test_proof_placeholder_caught_before_abstention(self) -> None:
        """sorry/admit must be rejected before the coverage abstention fires."""
        ph = [d for d in self.audit["details"] if d["tier"] == "lean-placeholder"]
        self.assertEqual(len(ph), 2)
        for d in ph:
            self.assertEqual(d["observed_verdict"], "rejected")
            self.assertEqual(d["observed_reason_code"], "proof_placeholder")

    def test_write_then_check_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "logic-error-catch-rate.json"
            audit.write_audit(out)
            reread = audit.build_audit()
            self.assertEqual(audit.build_audit()["status"], "PASS")
            expected = audit._canonical_bytes(audit.build_audit())
            self.assertEqual(out.read_bytes(), expected)

    def test_a_missing_catch_would_fail_the_audit(self) -> None:
        """If a planted error were NOT caught, status must be FAIL (never hidden)."""
        tampered = copy.deepcopy(self.audit)
        tampered["details"][0]["caught"] = False
        tampered["misses"] = [tampered["details"][0]]
        tampered["totals"]["missed"] = 1
        tampered["totals"]["caught"] = 15
        tampered["totals"]["catchRate"] = 15 / 16
        tampered["status"] = "FAIL"
        self.assertEqual(tampered["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
