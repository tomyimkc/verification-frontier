#!/usr/bin/env python3
"""Tests for the deterministic CPU-only GOAI protocol twin."""
from __future__ import annotations

import copy
import unittest

from v2.protocol_twin import (
    ARMS,
    build_ablation_runs,
    build_arm_runs,
    build_protocol_twin,
    build_trajectories,
    seal_protocol_twin,
    validate_protocol_twin,
)


class ProtocolTwinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_protocol_twin()

    def validate(self, payload: dict) -> tuple[list[str], dict]:
        return validate_protocol_twin(seal_protocol_twin(payload))

    def test_complete_twin_passes_as_development_only(self) -> None:
        errors, report = validate_protocol_twin(self.payload)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["armCount"], 7)
        self.assertEqual(report["ablationGroupCount"], 8)
        self.assertEqual(report["ablationVariantCount"], 13)
        self.assertTrue(report["primaryReplayCandidateHashesBound"])
        self.assertTrue(report["equalBudgetAccountingBound"])
        self.assertFalse(report["scientificOutcome"])
        self.assertFalse(report["statisticsEligible"])
        self.assertFalse(report["confirmatoryEligible"])
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["modelContact"])
        self.assertEqual(report["modelCallCount"], 0)
        self.assertEqual(report["networkCallCount"], 0)
        self.assertTrue(report["candidateOnly"])
        self.assertFalse(report["canClaimAGI"])

    def test_build_is_deterministic(self) -> None:
        self.assertEqual(self.payload, build_protocol_twin())

    def test_frozen_task_semantics_cannot_be_resealed(self) -> None:
        payload = copy.deepcopy(self.payload)
        task = next(
            row
            for row in payload["tasks"]
            if row["taskId"] == "twin-physics-valid-transfer-fail"
        )
        task["transferPassed"] = True
        payload["trajectories"] = build_trajectories(payload["tasks"])
        payload["armRuns"] = build_arm_runs(
            payload["tasks"],
            payload["trajectories"],
        )
        payload["ablationRuns"] = build_ablation_runs(
            payload["tasks"],
            payload["trajectories"],
        )
        errors, report = self.validate(payload)
        self.assertIn(
            "protocol twin payload does not exactly match the frozen "
            "canonical build",
            errors,
        )
        self.assertEqual(report["status"], "INVALID")

    def test_malformed_task_row_returns_invalid_without_raising(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["tasks"][0] = []
        errors, report = self.validate(payload)
        self.assertIn("task 0: expected object", errors)
        self.assertEqual(report["status"], "INVALID")

    def test_missing_required_arm_cell_is_invalid(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["armRuns"] = [
            row
            for row in payload["armRuns"]
            if not (
                row["arm"] == "B6-oracle-ceiling"
                and row["taskId"] == "twin-physics-valid-approved"
                and row["modelFamily"] == "qwen"
                and row["replicate"] == 0
            )
        ]
        errors, report = self.validate(payload)
        self.assertTrue(any("missing 1 B0-B6 cells" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")

    def test_missing_ablation_variant_is_invalid(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["requiredAblationGroups"]["A5-remove-one-tier"].remove("lean")
        payload["ablationRuns"] = [
            row
            for row in payload["ablationRuns"]
            if not (
                row["ablation"] == "A5-remove-one-tier"
                and row["variant"] == "lean"
            )
        ]
        errors, report = self.validate(payload)
        self.assertTrue(
            any("ablation groups or variants are incomplete" in error for error in errors)
        )
        self.assertTrue(any("missing" in error and "ablation cells" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")

    def test_primary_replay_candidate_mismatch_is_invalid(self) -> None:
        payload = copy.deepcopy(self.payload)
        target = next(
            row
            for row in payload["armRuns"]
            if row["arm"] == "B5-proposed"
            and row["taskId"] == "twin-symbolic-valid-approved"
            and row["modelFamily"] == "deepseek"
            and row["replicate"] == 1
        )
        trajectory = next(
            row
            for row in payload["trajectories"]
            if row["taskId"] == target["taskId"]
            and row["modelFamily"] == target["modelFamily"]
            and row["replicate"] == target["replicate"]
        )
        target["candidateSha256"] = trajectory["revisedCandidateSha256"]
        errors, report = self.validate(payload)
        self.assertTrue(any("candidate hash mismatch" in error for error in errors))
        self.assertTrue(
            any(
                "primary replay candidate bytes differ" in error
                for error in errors
            )
        )
        self.assertFalse(report["primaryReplayCandidateHashesBound"])

    def test_b2_consumes_revised_candidate_and_changes_sentinel_decision(self) -> None:
        rows = {
            row["arm"]: row
            for row in self.payload["armRuns"]
            if row["taskId"] == "twin-physics-valid-approved"
            and row["modelFamily"] == "qwen"
            and row["replicate"] == 0
        }
        trajectory = next(
            row
            for row in self.payload["trajectories"]
            if row["taskId"] == "twin-physics-valid-approved"
            and row["modelFamily"] == "qwen"
            and row["replicate"] == 0
        )
        self.assertEqual(
            rows["B1-fixed-verifier"]["candidateSha256"],
            trajectory["initialCandidateSha256"],
        )
        self.assertEqual(
            rows["B2-fixed-refinement"]["candidateSha256"],
            trajectory["revisedCandidateSha256"],
        )
        self.assertEqual(rows["B1-fixed-verifier"]["decision"], "abstain")
        self.assertEqual(rows["B2-fixed-refinement"]["decision"], "accepted")

    def test_a6_interactive_consumes_revision_and_changes_sentinel(self) -> None:
        rows = {
            row["variant"]: row
            for row in self.payload["ablationRuns"]
            if row["ablation"] == "A6-replay-vs-interactive"
            and row["taskId"] == "twin-physics-valid-approved"
            and row["modelFamily"] == "deepseek"
            and row["replicate"] == 2
        }
        self.assertNotEqual(
            rows["fixed-replay"]["candidateSha256"],
            rows["interactive-feedback"]["candidateSha256"],
        )
        self.assertEqual(rows["fixed-replay"]["decision"], "abstain")
        self.assertEqual(rows["interactive-feedback"]["decision"], "accepted")

    def test_budget_mismatch_is_invalid(self) -> None:
        payload = copy.deepcopy(self.payload)
        target = next(
            row
            for row in payload["armRuns"]
            if row["arm"] == "B4-human-only"
        )
        target["reviewerTimeBudgetSec"] += 1
        errors, report = self.validate(payload)
        self.assertTrue(any("reviewer budget mismatch" in error for error in errors))
        self.assertFalse(report["equalBudgetAccountingBound"])

    def test_claim_ceiling_cannot_be_relaxed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["canClaimAGI"] = True
        errors, report = self.validate(payload)
        self.assertIn("protocol twin: canClaimAGI must be false", errors)
        self.assertEqual(report["status"], "INVALID")

    def test_all_declared_arms_are_present(self) -> None:
        self.assertEqual(self.payload["requiredArms"], list(ARMS))
        self.assertEqual(
            {row["arm"] for row in self.payload["armRuns"]},
            set(ARMS),
        )


if __name__ == "__main__":
    unittest.main()
