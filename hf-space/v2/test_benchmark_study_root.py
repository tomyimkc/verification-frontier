#!/usr/bin/env python3
"""Tests for the Study Root DAG adversarial benchmark."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.benchmark_study_root import mutation_catalog, run_benchmark
from v2.build_receipt_rehearsal import build as build_receipts
from v2.protocol_twin import build_protocol_twin, validate_protocol_twin


class StudyRootBenchmarkTests(unittest.TestCase):
    def test_catalog_and_benchmark_counts_are_frozen(self) -> None:
        self.assertEqual(len(mutation_catalog()), 164)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "receipts"
            index_path = root / "index.json"
            validation_path = root / "validation.json"
            receipt_errors, receipt_report = build_receipts(
                store,
                index_path,
                validation_path,
            )
            self.assertEqual(receipt_errors, [])
            self.assertEqual(receipt_report["status"], "PASS")
            twin = build_protocol_twin()
            twin_errors, twin_validation = validate_protocol_twin(twin)
            self.assertEqual(twin_errors, [])
            errors, report = run_benchmark(
                twin=twin,
                twin_validation=twin_validation,
                receipt_index=json.loads(
                    index_path.read_text(encoding="utf-8")
                ),
                receipt_validation=json.loads(
                    validation_path.read_text(encoding="utf-8")
                ),
                receipt_store=store,
            )
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validDagCount"], 24)
        self.assertEqual(report["validDagPassed"], 24)
        self.assertEqual(report["validDagTopologyCount"], 1)
        self.assertEqual(
            report["validSerializationVariantCount"],
            24,
        )
        self.assertEqual(report["invalidDagCount"], 164)
        self.assertEqual(report["invalidDagRejected"], 164)
        self.assertTrue(report["stableTypedIssueCodes"])
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])
        self.assertTrue(report["candidateOnly"])
        self.assertFalse(report["canClaimAGI"])


if __name__ == "__main__":
    unittest.main()
