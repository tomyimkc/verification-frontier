#!/usr/bin/env python3
"""Offline checks for the hosted demo's provider-free logic."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from demo_logic import (
    frontier_gate_preview,
    public_status,
    reference_episode,
    verify_si,
    verify_symbolic,
)


class HostedDemoLogicTests(unittest.TestCase):
    def test_si_verifier(self) -> None:
        result = verify_si("9.8 m/s", "9.8 m/s")
        self.assertEqual(result["verdict"], "accepted")
        self.assertTrue(result["candidateOnly"])
        self.assertFalse(result["canClaimAGI"])

    def test_reference_episode_is_json_compatible(self) -> None:
        rows = reference_episode("free-fall", "scripted-refine")
        self.assertEqual(rows[-1]["verdict"], "accepted")
        self.assertTrue(rows[-1]["candidateOnly"])

    def test_symbolic_verifier_rejects_python_syntax(self) -> None:
        for attack in (
            'eval("0")',
            '__import__("os")',
            "(1).__class__",
            "x[0]",
            "((((((2**16)**16)**16)**16)**16)**16)",
        ):
            with self.subTest(attack=attack):
                result = verify_symbolic(attack, "0")
                self.assertEqual(result["verdict"], "abstain")
                self.assertEqual(
                    result["reasonCode"],
                    "expression_unparseable",
                )

    def test_gate_fails_closed_without_both_approvals(self) -> None:
        result = frontier_gate_preview(True, False, True)
        self.assertEqual(result["result"]["verdict"], "abstain")
        self.assertEqual(
            result["result"]["reasonCode"],
            "human_gate_incomplete",
        )

    def test_gate_can_activate_only_after_approvals_and_tests(self) -> None:
        result = frontier_gate_preview(True, True, True)
        self.assertEqual(result["result"]["verdict"], "accepted")
        self.assertEqual(result["receipt"]["coverageDelta"], 1)

    def test_status_never_claims_confirmatory_outcome(self) -> None:
        status = public_status()
        self.assertEqual(
            status["syntheticRehearsalSealValidation"]["status"],
            "PASS",
        )
        self.assertFalse(status["confirmatorySealAvailable"])
        self.assertFalse(status["confirmatoryExecutionAuthorized"])
        self.assertFalse(status["confirmatoryOutcomesAvailable"])
        self.assertTrue(status["claimCeiling"]["candidateOnly"])
        self.assertFalse(status["claimCeiling"]["canClaimAGI"])

    def test_status_rejects_forged_or_malformed_seal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seal.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "forged",
                        "status": "FORGED-PASS",
                        "taskCount": 999,
                        "outcomesViewedAtSeal": True,
                    }
                ),
                encoding="utf-8",
            )
            forged = public_status(path)
            self.assertEqual(
                forged["syntheticRehearsalSealValidation"]["status"],
                "INVALID",
            )
            path.write_text("{not-json", encoding="utf-8")
            malformed = public_status(path)
            self.assertEqual(
                malformed["syntheticRehearsalSealValidation"]["status"],
                "INVALID",
            )


if __name__ == "__main__":
    unittest.main()
