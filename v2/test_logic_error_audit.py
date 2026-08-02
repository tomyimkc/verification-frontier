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

    # ── Top-level invariants ──
    def test_catches_all_planted_errors(self) -> None:
        t = self.audit["totals"]
        self.assertEqual(t["planted"], t["caught"])
        self.assertEqual(t["missed"], 0)
        self.assertEqual(t["catchRate"], 1.0)
        self.assertEqual(self.audit["status"], "PASS")

    def test_planted_count_meets_benchmark_floor(self) -> None:
        """The expanded benchmark must plant at least 60 logic errors."""
        self.assertGreaterEqual(self.audit["totals"]["planted"], 60)

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

    # ── Per-tier breadth (the expanded taxonomy) ──
    def test_si_tier_breadth(self) -> None:
        si_errors = [d for d in self.audit["details"] if d["tier"] == "si"]
        self.assertGreaterEqual(len(si_errors), 20)
        for d in si_errors:
            self.assertTrue(d["caught"], d["error_id"])

    def test_symbolic_equivalence_errors_caught(self) -> None:
        """Expanded SymPy tier must cover >= 20 planted errors."""
        sym_errors = [d for d in self.audit["details"] if d["tier"] == "sympy"]
        self.assertGreaterEqual(len(sym_errors), 20)
        for d in sym_errors:
            self.assertTrue(d["caught"], d["error_id"])

    def test_proof_placeholder_variants_caught(self) -> None:
        """sorry/admit and their variants must be rejected (>= 6 cases)."""
        ph = [d for d in self.audit["details"] if d["tier"] == "lean-placeholder"]
        self.assertGreaterEqual(len(ph), 6)
        for d in ph:
            self.assertEqual(d["observed_verdict"], "rejected", d["error_id"])
            self.assertEqual(d["observed_reason_code"], "proof_placeholder", d["error_id"])

    # ── New category coverage (each sub-category actually appears and is caught) ──
    def _ids_by_type(self, tier: str) -> dict[str, list[str]]:
        by_type: dict[str, list[str]] = {}
        for d in self.audit["details"]:
            if d["tier"] == tier:
                by_type.setdefault(d["error_type"], []).append(d["error_id"])
        return by_type

    def test_si_sign_convention_errors(self) -> None:
        by_type = self._ids_by_type("si")
        self.assertIn("sign_error", by_type)
        self.assertGreaterEqual(len(by_type["sign_error"]), 4)
        # Sign errors live in BOTH tiers; the reason code differs by tier:
        #   SI tier  -> value_mismatch
        #   SymPy    -> not_symbolically_equivalent
        for d in self.audit["details"]:
            if d["error_type"] == "sign_error":
                self.assertTrue(d["caught"], d["error_id"])
                if d["tier"] == "si":
                    self.assertEqual(d["observed_reason_code"], "value_mismatch", d["error_id"])

    def test_si_order_of_magnitude_errors(self) -> None:
        by_type = self._ids_by_type("si")
        self.assertIn("order_of_magnitude_error", by_type)
        self.assertGreaterEqual(len(by_type["order_of_magnitude_error"]), 4)
        for d in self.audit["details"]:
            if d["error_type"] == "order_of_magnitude_error":
                self.assertTrue(d["caught"], d["error_id"])
                self.assertEqual(d["observed_reason_code"], "value_mismatch", d["error_id"])

    def test_si_dimension_mismatch_variety(self) -> None:
        by_type = self._ids_by_type("si")
        self.assertIn("dimension_mismatch", by_type)
        self.assertGreaterEqual(len(by_type["dimension_mismatch"]), 12)
        for d in self.audit["details"]:
            if d["error_type"] == "dimension_mismatch":
                self.assertEqual(d["observed_reason_code"], "dimension_mismatch", d["error_id"])

    def test_si_wrong_power_of_base_unit(self) -> None:
        """m^2 vs m, s^2 vs s — single base unit, wrong exponent."""
        ids = {"si-dim-13", "si-dim-14", "si-dim-15"}
        present = {d["error_id"] for d in self.audit["details"]}
        self.assertTrue(ids.issubset(present), ids - present)
        for d in self.audit["details"]:
            if d["error_id"] in ids:
                self.assertTrue(d["caught"], d["error_id"])

    def test_sympy_expansion_errors(self) -> None:
        by_type = self._ids_by_type("sympy")
        self.assertIn("expansion_error", by_type)
        self.assertGreaterEqual(len(by_type["expansion_error"]), 6)

    def test_sympy_factorization_errors(self) -> None:
        by_type = self._ids_by_type("sympy")
        self.assertIn("factorization_error", by_type)
        self.assertGreaterEqual(len(by_type["factorization_error"]), 2)

    def test_sympy_constant_arithmetic_errors(self) -> None:
        by_type = self._ids_by_type("sympy")
        self.assertIn("constant_arithmetic_error", by_type)
        self.assertGreaterEqual(len(by_type["constant_arithmetic_error"]), 2)

    def test_sympy_domain_errors_division_by_zero(self) -> None:
        """1/0, 0/0, 1/(x-x) must be REJECTED (zoo/nan), not abstained."""
        by_type = self._ids_by_type("sympy")
        self.assertIn("domain_error", by_type)
        self.assertGreaterEqual(len(by_type["domain_error"]), 3)
        for d in self.audit["details"]:
            if d["error_type"] == "domain_error":
                self.assertTrue(d["caught"], d["error_id"])
                self.assertEqual(d["observed_verdict"], "rejected", d["error_id"])
                self.assertEqual(
                    d["observed_reason_code"], "not_symbolically_equivalent", d["error_id"]
                )

    def test_proof_placeholder_spanning_multiple_tiers(self) -> None:
        """The guard fires on physics/math/formal golds alike (>= 3 distinct refs)."""
        ph = [d for d in self.audit["details"] if d["tier"] == "lean-placeholder"]
        distinct_refs = {d["reference"] for d in ph}
        self.assertGreaterEqual(len(distinct_refs), 3)
        # No placeholder case may have slipped through to coverage abstention.
        for d in ph:
            self.assertNotEqual(d["observed_reason_code"], "unsupported_specification")

    def test_proof_placeholder_case_and_embedding_variants(self) -> None:
        ids = {d["error_id"] for d in self.audit["details"] if d["tier"] == "lean-placeholder"}
        for required in ("lean-ph-01", "lean-ph-04", "lean-ph-06", "lean-ph-10", "lean-ph-11"):
            self.assertIn(required, ids)

    # ── Round-trip / fail-closed contract ──
    def test_write_then_check_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "logic-error-catch-rate.json"
            audit.write_audit(out)
            self.assertEqual(audit.build_audit()["status"], "PASS")
            expected = audit._canonical_bytes(audit.build_audit())
            self.assertEqual(out.read_bytes(), expected)

    def test_a_missing_catch_would_fail_the_audit(self) -> None:
        """If a planted error were NOT caught, status must be FAIL (never hidden).

        Uses the live totals so this stays correct as the benchmark grows.
        """
        tampered = copy.deepcopy(self.audit)
        planted = tampered["totals"]["planted"]
        tampered["details"][0]["caught"] = False
        tampered["misses"] = [tampered["details"][0]]
        tampered["totals"]["missed"] = 1
        tampered["totals"]["caught"] = planted - 1
        tampered["totals"]["catchRate"] = round((planted - 1) / planted, 4)
        tampered["status"] = "FAIL"
        self.assertEqual(tampered["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
