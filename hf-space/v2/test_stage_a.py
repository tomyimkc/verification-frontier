#!/usr/bin/env python3
"""Tests for the frozen 24-family Stage A programme."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from v2 import stage_a


class StageAManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = stage_a.build_manifest()

    def test_exact_24_family_domain_balance_and_claim_ceiling(self) -> None:
        self.assertEqual(stage_a.validate_manifest(self.manifest), [])
        self.assertEqual(self.manifest["familyCount"], 24)
        self.assertEqual(
            Counter(family["domain"] for family in self.manifest["families"]),
            Counter({"physics": 8, "symbolic": 8, "lean": 8}),
        )
        self.assertEqual(
            self.manifest["typedAbstainReasonsCovered"],
            sorted(stage_a.ABSTAIN_REASONS),
        )
        self.assertTrue(self.manifest["candidateOnly"])
        self.assertFalse(self.manifest["canClaimAGI"])
        self.assertFalse(self.manifest["winnerLevelEligible"])
        self.assertFalse(self.manifest["winnerLevelGateMet"])
        self.assertFalse(self.manifest["activationAuthorized"])
        self.assertFalse(self.manifest["confirmatoryEligible"])

    def test_every_public_frontier_task_is_bound_once(self) -> None:
        rows = stage_a._load_task_rows()
        expected = {
            task_id
            for task_id, row in rows.items()
            if row["split"] == "frontier-gap"
        }
        observed = [
            task_id
            for family in self.manifest["families"]
            for task_id in family["developmentTaskIds"]
        ]
        self.assertEqual(len(observed), len(set(observed)))
        self.assertEqual(set(observed), expected)
        self.assertEqual(len(observed), 30)

    def test_open_controls_are_non_promotable(self) -> None:
        controls = [
            family
            for family in self.manifest["families"]
            if family["openControl"]
        ]
        self.assertEqual(len(controls), 2)
        self.assertEqual(
            sum(len(family["developmentTaskIds"]) for family in controls),
            3,
        )
        for family in controls:
            self.assertEqual(
                family["permittedProposalType"],
                "preserve_abstention",
            )
            self.assertFalse(family["openControlPromotionAllowed"])
            self.assertFalse(family["modelMayApprove"])

    def test_every_family_has_bounded_complete_test_plan(self) -> None:
        for family in self.manifest["families"]:
            tests = family["developmentTestIds"]
            self.assertEqual(
                set(tests),
                set(stage_a.REQUIRED_TEST_CATEGORIES),
            )
            self.assertGreaterEqual(len(tests["positive"]), 2)
            self.assertGreaterEqual(len(tests["negative"]), 2)
            self.assertGreaterEqual(len(tests["malformed"]), 1)
            self.assertGreaterEqual(len(tests["safety"]), 1)
            self.assertGreaterEqual(len(tests["rollback"]), 1)
            budget = family["executionBudget"]
            self.assertLessEqual(budget["maxWallTimeSec"], 120)
            self.assertLessEqual(budget["maxMemoryMiB"], 2048)
            self.assertLessEqual(budget["maxTests"], 10)
            self.assertFalse(budget["networkAllowed"])
            self.assertFalse(budget["credentialAccessAllowed"])

    def test_duplicate_task_binding_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["families"][1]["developmentTaskIds"][0] = (
            mutated["families"][0]["developmentTaskIds"][0]
        )
        errors = stage_a.validate_manifest(mutated)
        self.assertTrue(
            any("task reused across Stage A families" in error for error in errors)
        )

    def test_open_control_promotion_mutation_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        control = next(
            family for family in mutated["families"] if family["openControl"]
        )
        control["permittedProposalType"] = "verifier"
        control["openControlPromotionAllowed"] = True
        errors = stage_a.validate_manifest(mutated)
        self.assertTrue(
            any("open controls must use preserve_abstention" in error for error in errors)
        )
        self.assertTrue(
            any("promotion/self-approval ceiling weakened" in error for error in errors)
        )

    def test_unbounded_resource_mutation_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["families"][0]["executionBudget"]["maxWallTimeSec"] = 999999
        mutated["families"][0]["executionBudget"]["networkAllowed"] = True
        errors = stage_a.validate_manifest(mutated)
        self.assertTrue(any("wall-time budget is unbounded" in error for error in errors))
        self.assertTrue(
            any("authority budget is not fail-closed" in error for error in errors)
        )

    def test_task_source_mutation_breaks_hash_binding(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        task_id = mutated["families"][0]["developmentTaskIds"][0]
        mutated["taskBindings"][task_id]["promptSha256"] = "0" * 64
        errors = stage_a.validate_manifest(mutated)
        self.assertTrue(
            any("task binding mismatch" in error for error in errors)
        )

    def test_readiness_preserves_all_future_gates_false(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-stage-a-") as tmp:
            output = Path(tmp)
            manifest, readiness = stage_a.write_artifacts(output)
            manifest_path = output / "stage-a-manifest.json"
            readiness_path = output / "stage-a-readiness.json"
            self.assertEqual(stage_a.validate_manifest(manifest), [])
            self.assertEqual(
                stage_a.validate_readiness(
                    readiness,
                    manifest_path=manifest_path,
                ),
                [],
            )
            self.assertEqual(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                manifest,
            )
            self.assertEqual(
                json.loads(readiness_path.read_text(encoding="utf-8")),
                readiness,
            )
            self.assertFalse(
                readiness["powerEvidence"]["confirmatoryPowerValidated"]
            )
            # The single authorized development proposal run is complete and
            # its sanitized result is bound; every downstream gate that would
            # require human/expert review, tests, freeze, or confirmatory
            # execution remains false.
            self.assertTrue(readiness["readiness"]["modelProposalRunComplete"])
            self.assertEqual(
                readiness["readiness"]["modelProposalRunArtifact"],
                "v2/artifacts/stage-a-development-result.json",
            )
            for gate in (
                "ownerReviewComplete",
                "independentExpertAIReviewComplete",
                "visibleExtensionTestsComplete",
                "approvedExtensionBundleFrozen",
                "confirmatorySealFrozen",
            ):
                self.assertFalse(readiness["readiness"][gate])


if __name__ == "__main__":
    unittest.main()
