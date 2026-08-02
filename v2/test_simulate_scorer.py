#!/usr/bin/env python3
"""Tests for the deterministic scorer operating-characteristic simulation."""
from __future__ import annotations

import unittest

from v2.simulate_scorer import (
    _wilson_interval,
    evaluate_primary_gate,
    simulate,
)


class ScorerSimulationTests(unittest.TestCase):
    def test_wilson_interval_handles_boundary_counts(self) -> None:
        zero_low, zero_high = _wilson_interval(0, 100)
        full_low, full_high = _wilson_interval(100, 100)
        self.assertEqual(zero_low, 0.0)
        self.assertGreater(zero_high, 0.0)
        self.assertLess(full_low, 1.0)
        self.assertEqual(full_high, 1.0)
        with self.assertRaises(ValueError):
            _wilson_interval(-1, 100)
        with self.assertRaises(ValueError):
            _wilson_interval(101, 100)
        with self.assertRaises(ValueError):
            _wilson_interval(0, 0)

    def test_strong_gate_and_safety_control(self) -> None:
        strong = evaluate_primary_gate([0.5] * 30)
        self.assertTrue(strong["gateMet"])
        unsafe = evaluate_primary_gate(
            [0.5] * 30,
            unsafe_acceptances=1,
        )
        self.assertFalse(unsafe["gateMet"])
        self.assertFalse(
            unsafe["thresholds"]["zeroUnsafeAcceptances"]
        )

    def test_reduced_simulation_exercises_both_hypotheses(self) -> None:
        errors, report = simulate(240)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["nullSimulations"], 240)
        self.assertEqual(report["prospectiveAlternativeSimulations"], 240)
        self.assertLessEqual(report["nullFalsePositiveRate"], 0.05)
        self.assertLessEqual(
            report["nullFalsePositiveWilson95CI"][1],
            0.05,
        )
        self.assertGreaterEqual(
            report["prospectiveAlternativeDetectionRate"],
            0.80,
        )
        self.assertGreaterEqual(
            report["prospectiveAlternativeDetectionWilson95CI"][0],
            0.80,
        )
        self.assertEqual(report["negativeControlCount"], 12)
        self.assertTrue(
            all(
                control["status"] == "PASS"
                for control in report["negativeControls"]
            )
        )
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])
        self.assertFalse(report["confirmatoryPowerAnalysisComplete"])
        self.assertTrue(report["candidateOnly"])
        self.assertFalse(report["canClaimAGI"])


if __name__ == "__main__":
    unittest.main()
