#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Tests for the chart-data exporter.

Two layers:

* **Unit tests** project from in-memory fixtures (no on-disk artifact
  dependency) and assert the ``goai-chart-data/v1`` SCHEMA CONTRACT -- the
  label order, the 2-decimal presentation rounding, the count derivations, and
  the fail-closed behaviour on a stale / malformed source.

* **Integration tests** project from the real on-disk canonical artifacts and
  assert the headline numbers the demo's charts display (67 logic errors, 30
  ill-posed, 0.16 proposed coverage, 0.84 error-reduction, ...). These are
  skipped if the source artifacts are absent.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from v2 import export_chart_data as ecd


# --------------------------------------------------------------------------- #
# Fixtures: minimal valid source artifacts matching their v1 schemas.
# --------------------------------------------------------------------------- #
def _logic_error_fixture(values: list[int]) -> dict[str, Any]:
    """Build a logic-error artifact whose `details` project to `values`.

    `values` is in LOGIC_ERROR_LABELS order:
    [SI dim, SI val, SI sign, SymPy eq, SymPy exp, SymPy dom, Lean ph].
    """
    specs = [
        ("si", "dimension_mismatch", "si-dim"),
        ("si", "value_outside_tolerance", "si-val"),
        ("si", "sign_error", "si-sign"),
        ("sympy", "not_equivalent", "sym-eq"),
        ("sympy", "expansion_error", "sym-eq"),
        ("sympy", "domain_error", "sym-dom"),
        ("lean-placeholder", "proof_placeholder", "lean-ph"),
    ]
    details: list[dict[str, Any]] = []
    for (tier, etype, prefix), count in zip(specs, values):
        for i in range(count):
            details.append(
                {
                    "error_id": f"{prefix}-{i + 1:02d}",
                    "tier": tier,
                    "error_type": etype,
                    "caught": True,
                }
            )
    total = len(details)
    return {
        "schema": "goai-logic-error-catch-rate/v1",
        "details": details,
        "totals": {"planted": total, "caught": total, "missed": 0},
    }


def _baseline_fixture() -> dict[str, Any]:
    return {
        "schema": "goai-baseline-comparison/v1",
        "comparisonTable": [
            {"policy": "raw-model", "errorCatchRate": 0.0, "unsafeAcceptances": 67, "coverageRate": 1.0},
            {"policy": "always-abstain", "errorCatchRate": 0.0, "unsafeAcceptances": 0, "coverageRate": 0.0},
            {"policy": "always-accept", "errorCatchRate": 0.0, "unsafeAcceptances": 67, "coverageRate": 1.0},
            {"policy": "proposed-system", "errorCatchRate": 1.0, "unsafeAcceptances": 0, "coverageRate": 0.1566},
        ],
    }


def _ill_posed_fixture() -> dict[str, Any]:
    return {
        "schema": "goai-ill-posed-audit/v1",
        "catchRate": {
            "illPosed": {
                "total": 30,
                "caught": 30,
                "byCategory": {
                    "contradictory_equation_system": {"caught": 10, "total": 10, "catchRate": 1.0},
                    "missing_constraint": {"caught": 8, "total": 8, "catchRate": 1.0},
                    "undecidable": {"caught": 5, "total": 5, "catchRate": 1.0},
                    "circular_dependency": {"caught": 4, "total": 4, "catchRate": 1.0},
                    "empty_feasible_region": {"caught": 3, "total": 3, "catchRate": 1.0},
                },
            },
            "wellPosedControls": {"total": 10, "falseAlarms": 10, "falseAlarmRate": 1.0},
        },
    }


def _self_correction_fixture() -> dict[str, Any]:
    return {
        "schema": "goai-self-correction-audit/v1",
        "totals": {
            "errorReductionRate": 0.8358,
            "rejectionClearedRate": 1.0,
            "planted": 67,
            "fixedBySelfCorrection": 56,
        },
    }


def _full_fixtures(values=None) -> tuple[dict, dict, dict, dict]:
    if values is None:
        values = [15, 9, 6, 13, 9, 4, 11]
    return (
        _logic_error_fixture(values),
        _baseline_fixture(),
        _ill_posed_fixture(),
        _self_correction_fixture(),
    )


# --------------------------------------------------------------------------- #
# Schema / structure tests
# --------------------------------------------------------------------------- #
class SchemaTests(unittest.TestCase):
    def test_schema_label_is_goai_chart_data_v1(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        self.assertEqual(payload["schema"], "goai-chart-data/v1")

    def test_top_level_sections_present(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        for section in (
            "logicErrorCatchRate",
            "baselineComparison",
            "illPosedCatchRate",
            "selfCorrection",
        ):
            self.assertIn(section, payload, section)

    def test_claim_ceiling_frozen_on_payload(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        self.assertTrue(payload["candidateOnly"])
        self.assertFalse(payload["canClaimAGI"])
        self.assertEqual(payload["claimCeiling"], ecd.CLAIM_CEILING)
        self.assertFalse(payload["claimCeiling"]["winnerLevelEligible"])


# --------------------------------------------------------------------------- #
# logicErrorCatchRate section
# --------------------------------------------------------------------------- #
class LogicErrorChartTests(unittest.TestCase):
    def test_labels_in_fixed_order(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        self.assertEqual(
            payload["logicErrorCatchRate"]["labels"],
            [
                "SI dimension",
                "SI value",
                "SI sign",
                "SymPy equivalence",
                "SymPy expansion",
                "SymPy domain",
                "Lean placeholder",
            ],
        )

    def test_values_match_input_counts(self) -> None:
        values = [15, 9, 6, 13, 9, 4, 11]
        payload = ecd.build_chart_data(*_full_fixtures(values))
        self.assertEqual(payload["logicErrorCatchRate"]["values"], values)
        self.assertEqual(payload["logicErrorCatchRate"]["total"], 67)
        self.assertEqual(payload["logicErrorCatchRate"]["caught"], 67)

    def test_values_sum_to_total(self) -> None:
        values = [3, 2, 1, 5, 4, 2, 1]
        payload = ecd.build_chart_data(*_full_fixtures(values))
        self.assertEqual(sum(payload["logicErrorCatchRate"]["values"]), payload["logicErrorCatchRate"]["total"])
        self.assertEqual(payload["logicErrorCatchRate"]["total"], 18)

    def test_sympy_sign_error_maps_to_equivalence_not_expansion(self) -> None:
        # A sympy sign_error (not expansion_error, not domain_error) must map
        # to the general "SymPy equivalence" bucket, not "SymPy expansion".
        src = _logic_error_fixture([0, 0, 0, 0, 0, 0, 0])
        # Inject one sympy sign_error row.
        src["details"].append({"error_id": "sym-eq-99", "tier": "sympy", "error_type": "sign_error", "caught": True})
        src["totals"]["planted"] = 1
        src["totals"]["caught"] = 1
        payload = ecd.build_chart_data(src, _baseline_fixture(), _ill_posed_fixture(), _self_correction_fixture())
        labels = payload["logicErrorCatchRate"]["labels"]
        values = payload["logicErrorCatchRate"]["values"]
        self.assertEqual(values[labels.index("SymPy equivalence")], 1)
        self.assertEqual(values[labels.index("SymPy expansion")], 0)

    def test_inconsistent_totals_raise(self) -> None:
        src = _logic_error_fixture([15, 9, 6, 13, 9, 4, 11])  # sums to 67
        src["totals"]["planted"] = 66  # lie about the total
        with self.assertRaises(ecd.ChartDataError):
            ecd.build_chart_data(src, _baseline_fixture(), _ill_posed_fixture(), _self_correction_fixture())

    def test_uncategorizable_row_raises(self) -> None:
        src = _logic_error_fixture([0, 0, 0, 0, 0, 0, 0])
        src["details"].append({"error_id": "weird-01", "tier": "unknown-tier", "error_type": "?", "caught": True})
        src["totals"]["planted"] = 1
        with self.assertRaises(ecd.ChartDataError):
            ecd.build_chart_data(src, _baseline_fixture(), _ill_posed_fixture(), _self_correction_fixture())


# --------------------------------------------------------------------------- #
# baselineComparison section
# --------------------------------------------------------------------------- #
class BaselineChartTests(unittest.TestCase):
    def test_policy_labels_in_fixed_order(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        self.assertEqual(
            payload["baselineComparison"]["labels"],
            ["raw-model", "always-abstain", "always-accept", "proposed-system"],
        )

    def test_error_catch_rates(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        self.assertEqual(payload["baselineComparison"]["errorCatchRate"], [0.0, 0.0, 0.0, 1.0])

    def test_unsafe_acceptances(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        self.assertEqual(payload["baselineComparison"]["unsafeAcceptances"], [67, 0, 67, 0])

    def test_coverage_rates_rounded_to_two_decimals(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        # 0.1566 -> 0.16 under the chart-schema presentation rounding.
        self.assertEqual(payload["baselineComparison"]["coverageRate"], [1.0, 0.0, 1.0, 0.16])

    def test_missing_policy_raises(self) -> None:
        baseline = _baseline_fixture()
        baseline["comparisonTable"] = [
            r for r in baseline["comparisonTable"] if r["policy"] != "always-accept"
        ]
        with self.assertRaises(ecd.ChartDataError):
            ecd.build_chart_data(_logic_error_fixture([1, 0, 0, 0, 0, 0, 0]), baseline, _ill_posed_fixture(), _self_correction_fixture())


# --------------------------------------------------------------------------- #
# illPosedCatchRate section
# --------------------------------------------------------------------------- #
class IllPosedChartTests(unittest.TestCase):
    def test_totals_and_false_alarm_rate(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        ip = payload["illPosedCatchRate"]
        self.assertEqual(ip["total"], 30)
        self.assertEqual(ip["caught"], 30)
        self.assertEqual(ip["falseAlarmRate"], 1.0)

    def test_by_category_has_five_categories(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        by_cat = payload["illPosedCatchRate"]["byCategory"]
        self.assertEqual(
            sorted(by_cat),
            [
                "circular_dependency",
                "contradictory_equation_system",
                "empty_feasible_region",
                "missing_constraint",
                "undecidable",
            ],
        )

    def test_by_category_sums_to_total(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        by_cat = payload["illPosedCatchRate"]["byCategory"]
        self.assertEqual(sum(v["total"] for v in by_cat.values()), payload["illPosedCatchRate"]["total"])
        self.assertEqual(sum(v["caught"] for v in by_cat.values()), payload["illPosedCatchRate"]["caught"])

    def test_by_category_entries_are_compact_triples(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        for entry in payload["illPosedCatchRate"]["byCategory"].values():
            self.assertEqual(set(entry), {"caught", "total", "catchRate"})


# --------------------------------------------------------------------------- #
# selfCorrection section
# --------------------------------------------------------------------------- #
class SelfCorrectionChartTests(unittest.TestCase):
    def test_rates_rounded_to_two_decimals(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        # 0.8358 -> 0.84; 1.0 -> 1.0.
        self.assertEqual(payload["selfCorrection"]["errorReductionRate"], 0.84)
        self.assertEqual(payload["selfCorrection"]["rejectionClearedRate"], 1.0)

    def test_missing_rate_raises(self) -> None:
        sc = _self_correction_fixture()
        del sc["totals"]["errorReductionRate"]
        with self.assertRaises(ecd.ChartDataError):
            ecd.build_chart_data(_logic_error_fixture([1, 0, 0, 0, 0, 0, 0]), _baseline_fixture(), _ill_posed_fixture(), sc)


# --------------------------------------------------------------------------- #
# Source-schema validation
# --------------------------------------------------------------------------- #
class SourceSchemaTests(unittest.TestCase):
    def test_wrong_logic_error_schema_raises(self) -> None:
        src = _logic_error_fixture([1, 0, 0, 0, 0, 0, 0])
        src["schema"] = "stale/v0"
        with self.assertRaises(ecd.ChartDataError):
            ecd.build_chart_data(src, _baseline_fixture(), _ill_posed_fixture(), _self_correction_fixture())

    def test_missing_source_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist.json"
            with self.assertRaises(ecd.ChartDataError):
                ecd._load_json(missing)


# --------------------------------------------------------------------------- #
# Canonical bytes / write / check
# --------------------------------------------------------------------------- #
class WriteAndCheckTests(unittest.TestCase):
    def test_canonical_bytes_are_sorted_and_compact(self) -> None:
        payload = ecd.build_chart_data(*_full_fixtures())
        raw = ecd._canonical_bytes(payload)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b": ", raw)  # compact separators
        # Round-trips as JSON.
        reloaded = json.loads(raw.decode("utf-8"))
        self.assertEqual(reloaded["schema"], "goai-chart-data/v1")

    def test_write_then_check_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "chart-data.json"
            # write_chart_data reads the on-disk artifacts; instead exercise
            # _canonical_bytes + manual write here to keep the test hermetic.
            built = ecd.build_chart_data(*_full_fixtures())
            out.write_bytes(ecd._canonical_bytes(built))
            # Re-derive and compare against what we just wrote.
            rederived = ecd._canonical_bytes(ecd.build_chart_data(*_full_fixtures()))
            self.assertEqual(out.read_bytes(), rederived)

    def test_write_chart_data_writes_canonical_file(self) -> None:
        # Patch the loader so write_chart_data projects from fixtures without
        # touching the real artifacts directory.
        le, bl, ip, sc = _full_fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "chart-data.json"
            with mock.patch.object(ecd, "_load_json", side_effect=[le, bl, ip, sc]):
                built = ecd.write_chart_data(out)
            self.assertEqual(built["schema"], "goai-chart-data/v1")
            self.assertTrue(out.is_file())
            # File must be canonical JSON (sorted keys, compact, trailing newline).
            self.assertTrue(out.read_bytes().endswith(b"\n"))


# --------------------------------------------------------------------------- #
# Integration: project from the REAL on-disk canonical artifacts.
# --------------------------------------------------------------------------- #
class OnDiskArtifactIntegrationTests(unittest.TestCase):
    """Project from v2/artifacts/*.json exactly as the demo will."""

    def setUp(self) -> None:
        if not ecd.LOGIC_ERROR_PATH.is_file():
            self.skipTest(f"source artifact absent: {ecd.LOGIC_ERROR_PATH}")

    def test_real_artifacts_project_to_contract_values(self) -> None:
        payload = ecd.build_chart_data()
        # ── logicErrorCatchRate ──
        le = payload["logicErrorCatchRate"]
        self.assertEqual(le["labels"], ecd.LOGIC_ERROR_LABELS)
        self.assertEqual(le["total"], 67)
        self.assertEqual(le["caught"], 67)
        self.assertEqual(sum(le["values"]), 67)
        # The headline per-tier counts: SI=30, SymPy=26, Lean=11.
        si_total = le["values"][0] + le["values"][1] + le["values"][2]
        sympy_total = le["values"][3] + le["values"][4] + le["values"][5]
        self.assertEqual(si_total, 30)
        self.assertEqual(sympy_total, 26)
        self.assertEqual(le["values"][6], 11)

        # ── baselineComparison ──
        bc = payload["baselineComparison"]
        self.assertEqual(bc["errorCatchRate"], [0.0, 0.0, 0.0, 1.0])
        self.assertEqual(bc["unsafeAcceptances"], [67, 0, 67, 0])
        self.assertEqual(bc["coverageRate"][-1], 0.16)

        # ── illPosedCatchRate ──
        ip = payload["illPosedCatchRate"]
        self.assertEqual(ip["total"], 30)
        self.assertEqual(ip["caught"], 30)
        self.assertEqual(ip["falseAlarmRate"], 1.0)
        self.assertEqual(len(ip["byCategory"]), 5)

        # ── selfCorrection ──
        self.assertEqual(payload["selfCorrection"]["errorReductionRate"], 0.84)
        self.assertEqual(payload["selfCorrection"]["rejectionClearedRate"], 1.0)

    def test_on_disk_chart_data_is_current(self) -> None:
        """If chart-data.json exists, it must equal the freshly derived bytes."""
        if not ecd.OUTPUT_PATH.is_file():
            self.skipTest("chart-data.json not yet written")
        on_disk = ecd.OUTPUT_PATH.read_bytes()
        expected = ecd._canonical_bytes(ecd.build_chart_data())
        self.assertEqual(on_disk, expected)


if __name__ == "__main__":
    unittest.main()
