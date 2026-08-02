#!/usr/bin/env python3
"""Tests for the development-only GOAI Study Root v3."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from v2.build_receipt_rehearsal import build as build_receipts
from v2.protocol_twin import build_protocol_twin, validate_protocol_twin
from v2.study_root import (
    build_study_materials,
    validate_study_materials,
)


class StudyRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = root / "receipts"
        self.index_path = root / "index.json"
        self.receipt_validation_path = root / "receipt-validation.json"
        errors, report = build_receipts(
            self.store,
            self.index_path,
            self.receipt_validation_path,
        )
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.receipt_index = json.loads(
            self.index_path.read_text(encoding="utf-8")
        )
        self.receipt_validation = json.loads(
            self.receipt_validation_path.read_text(encoding="utf-8")
        )
        self.twin = build_protocol_twin()
        twin_errors, self.twin_validation = validate_protocol_twin(
            self.twin
        )
        self.assertEqual(twin_errors, [])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def materials(self, study_id: str = "goai-development-study-root-v3"):
        return build_study_materials(
            study_id=study_id,
            twin=self.twin,
            twin_validation=self.twin_validation,
            receipt_index=self.receipt_index,
            receipt_validation=self.receipt_validation,
            receipt_store=self.store,
        )

    def validate(self, root, arms, ablations):
        return validate_study_materials(
            root,
            arms,
            ablations,
            twin=self.twin,
            twin_validation=self.twin_validation,
            receipt_index=self.receipt_index,
            receipt_validation=self.receipt_validation,
            receipt_store=self.store,
        )

    def test_complete_study_root_passes_as_development_only(self) -> None:
        root, arms, ablations = self.materials()
        issues, report = self.validate(root, arms, ablations)
        self.assertEqual(issues, [])
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["studyRootBound"])
        self.assertFalse(report["studyRootScorerInputsBound"])
        self.assertTrue(
            report["constructedArmFixtureRowsValidated"]
        )
        self.assertTrue(
            report["constructedB6FixtureRowsValidated"]
        )
        self.assertTrue(
            report["constructedAblationFixtureRowsValidated"]
        )
        self.assertFalse(report["actualB6RowsValidated"])
        self.assertFalse(report["actualAblationRowsValidated"])
        self.assertTrue(report["transferExecutionReceiptsValidated"])
        self.assertEqual(report["armRowCount"], 756)
        self.assertEqual(report["b6RowCount"], 108)
        self.assertEqual(report["ablationRowCount"], 1404)
        self.assertEqual(report["transferExecutionReceiptCount"], 6)
        self.assertFalse(report["protocolValid"])
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])
        self.assertTrue(report["candidateOnly"])
        self.assertFalse(report["canClaimAGI"])

    def test_missing_b6_row_is_invalid(self) -> None:
        root, arms, ablations = self.materials()
        arms = copy.deepcopy(arms)
        index = next(
            i
            for i, row in enumerate(arms["rows"])
            if row["arm"] == "B6-oracle-ceiling"
        )
        del arms["rows"][index]
        issues, report = self.validate(root, arms, ablations)
        self.assertIn(
            "ARM_RESULT_MANIFEST_MISMATCH",
            {issue["code"] for issue in issues},
        )
        self.assertFalse(
            report["constructedB6FixtureRowsValidated"]
        )
        self.assertFalse(report["actualB6RowsValidated"])

    def test_missing_ablation_variant_row_is_invalid(self) -> None:
        root, arms, ablations = self.materials()
        ablations = copy.deepcopy(ablations)
        del ablations["rows"][0]
        issues, report = self.validate(root, arms, ablations)
        self.assertIn(
            "ABLATION_RESULT_MANIFEST_MISMATCH",
            {issue["code"] for issue in issues},
        )
        self.assertFalse(
            report["constructedAblationFixtureRowsValidated"]
        )
        self.assertFalse(report["actualAblationRowsValidated"])

    def test_claim_ceiling_cannot_be_relaxed(self) -> None:
        root, arms, ablations = self.materials()
        root = copy.deepcopy(root)
        root["winnerLevelEligible"] = True
        root["winnerLevelGateMet"] = True
        root["canClaimAGI"] = True
        issues, report = self.validate(root, arms, ablations)
        codes = {issue["code"] for issue in issues}
        self.assertIn("CLAIM_CEILING_AGI", codes)
        self.assertIn("CLAIM_CEILING_RELAXED", codes)
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])
        self.assertFalse(report["canClaimAGI"])

    def test_protocol_twin_validation_drift_is_invalid(self) -> None:
        fabricated_validation = copy.deepcopy(self.twin_validation)
        fabricated_validation["status"] = "FABRICATED_PASS"
        fabricated_validation["errors"] = ["fabricated"]
        root, arms, ablations = build_study_materials(
            twin=self.twin,
            twin_validation=fabricated_validation,
            receipt_index=self.receipt_index,
            receipt_validation=self.receipt_validation,
            receipt_store=self.store,
        )
        issues, report = validate_study_materials(
            root,
            arms,
            ablations,
            twin=self.twin,
            twin_validation=fabricated_validation,
            receipt_index=self.receipt_index,
            receipt_validation=self.receipt_validation,
            receipt_store=self.store,
        )
        self.assertIn(
            "PROTOCOL_TWIN_VALIDATION_MISMATCH",
            {issue["code"] for issue in issues},
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["studyRootBound"])

    def test_twenty_four_distinct_development_roots_validate(self) -> None:
        roots = set()
        for index in range(24):
            study_id = f"goai-development-study-root-v3-{index:02d}"
            root, arms, ablations = self.materials(study_id)
            issues, report = self.validate(root, arms, ablations)
            self.assertEqual(issues, [])
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(root["serializationVariant"], index)
            self.assertEqual(arms["serializationVariant"], index)
            self.assertEqual(ablations["serializationVariant"], index)
            roots.add(root["studyRootSha256"])
        self.assertEqual(len(roots), 24)


if __name__ == "__main__":
    unittest.main()
