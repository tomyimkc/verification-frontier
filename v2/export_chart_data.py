#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Export every benchmark artifact into one HF-demo chart payload.

This is a PURE PROJECTION over the existing canonical artifacts. It reads:

  * ``v2/artifacts/logic-error-catch-rate.json``  (logicErrorCatchRate)
  * ``v2/artifacts/baseline-comparison.json``      (baselineComparison)
  * ``v2/artifacts/ill-posed-audit.json``          (illPosedCatchRate)
  * ``v2/artifacts/self-correction-audit.json``    (selfCorrection)

and writes ``v2/artifacts/chart-data.json`` (schema ``goai-chart-data/v1``) --
a single, flat, chart-ready file the Hugging Face demo's visualization can
fetch in one request.

DESIGN NOTES
------------
* The label order and the 2-decimal presentation rounding are part of the
  ``goai-chart-data/v1`` SCHEMA CONTRACT (the demo's chart config keys off the
  labels and the rounded magnitudes). The exporter therefore derives the
  COUNTS from the artifacts but emits labels / rounding per the schema.
* Nothing here rebuilds a source artifact -- if a source is stale, rerun its
  builder; this file only projects. ``--check`` re-derives the canonical bytes
  and byte-compares them so a drifted or hand-edited chart-data.json is caught.
* Claim ceiling is frozen on the payload exactly as on every other artifact.

Claim ceiling: candidateOnly:true, canClaimAGI:false. This is instrument
evidence about deterministic detectors, NOT a model-capability claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
ARTIFACTS = HERE / "artifacts"
OUTPUT_PATH = ARTIFACTS / "chart-data.json"

LOGIC_ERROR_PATH = ARTIFACTS / "logic-error-catch-rate.json"
BASELINE_PATH = ARTIFACTS / "baseline-comparison.json"
ILL_POSED_PATH = ARTIFACTS / "ill-posed-audit.json"
SELF_CORRECTION_PATH = ARTIFACTS / "self-correction-audit.json"

SCHEMA = "goai-chart-data/v1"

# Presentation rounding for the chart schema. Counts are exact integers;
# rates are rounded to 2 decimals so the demo's axis ticks are stable.
_RATE_DIGITS = 2

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

# The fixed label order for the logic-error stacked bar. The labels group the
# 67 planted logic errors by verifier sub-tier; the order is verifier-first
# (SI dimension -> SI value -> SI sign -> SymPy ... -> Lean placeholder).
LOGIC_ERROR_LABELS = [
    "SI dimension",
    "SI value",
    "SI sign",
    "SymPy equivalence",
    "SymPy expansion",
    "SymPy domain",
    "Lean placeholder",
]

# Fixed policy order for the 4-way baseline comparison chart.
BASELINE_POLICY_ORDER = [
    "raw-model",
    "always-abstain",
    "always-accept",
    "proposed-system",
]


# --------------------------------------------------------------------------- #
# Source loading
# --------------------------------------------------------------------------- #
class ChartDataError(RuntimeError):
    """Raised when a source artifact is missing or malformed."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ChartDataError(f"source artifact missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChartDataError(f"source artifact not valid JSON ({path}): {exc}") from exc


def _require_source_schemas(
    logic_error: dict, baseline: dict, ill_posed: dict, self_correction: dict
) -> None:
    """Fail fast with a clear message if a source is the wrong schema."""
    checks = [
        (logic_error, LOGIC_ERROR_PATH, "goai-logic-error-catch-rate/v1"),
        (baseline, BASELINE_PATH, "goai-baseline-comparison/v1"),
        (ill_posed, ILL_POSED_PATH, "goai-ill-posed-audit/v1"),
        (self_correction, SELF_CORRECTION_PATH, "goai-self-correction-audit/v1"),
    ]
    for payload, path, expected in checks:
        got = payload.get("schema")
        if got != expected:
            raise ChartDataError(
                f"source {path.name} has schema {got!r}; expected {expected!r}. "
                "Re-run the matching builder before exporting chart data."
            )


# --------------------------------------------------------------------------- #
# Section 1: logicErrorCatchRate
# --------------------------------------------------------------------------- #
def _categorize_logic_error(row: dict) -> str:
    """Map a planted-error detail row to one of LOGIC_ERROR_LABELS.

    The mapping is derived from the row's ``tier`` + ``error_type`` + the
    ``error_id`` prefix (e.g. ``si-dim-01``), which are stable across rebuilds.
    """
    tier = row.get("tier", "")
    etype = row.get("error_type", "")
    eid = str(row.get("error_id", ""))
    if tier == "si":
        if etype == "dimension_mismatch":
            return "SI dimension"
        if etype == "sign_error":
            return "SI sign"
        if etype in {"value_outside_tolerance", "order_of_magnitude_error"}:
            return "SI value"
    if tier == "sympy":
        if etype == "domain_error" or eid.startswith("sym-dom"):
            return "SymPy domain"
        if etype == "expansion_error":
            return "SymPy expansion"
        # not_equivalent / sign_error / missing_term / wrong_degree /
        # factorization_error / constant_arithmetic_error -> general non-equivalence.
        return "SymPy equivalence"
    if tier == "lean-placeholder":
        return "Lean placeholder"
    raise ChartDataError(f"uncategorizable logic-error row: {row!r}")


def _build_logic_error_chart(logic_error: dict) -> dict[str, Any]:
    details = logic_error.get("details")
    if not isinstance(details, list) or not details:
        raise ChartDataError(
            "logic-error-catch-rate.json has no `details` list to project from"
        )
    counts = {label: 0 for label in LOGIC_ERROR_LABELS}
    for row in details:
        label = _categorize_logic_error(row)
        counts[label] += 1
    total = int(logic_error.get("totals", {}).get("planted", len(details)))
    caught = int(logic_error.get("totals", {}).get("caught", len(details)))
    # Sanity: the per-label counts must sum to the headline total.
    if sum(counts.values()) != total:
        raise ChartDataError(
            f"logic-error label counts sum to {sum(counts.values())} but "
            f"totals.planted is {total}; artifact is inconsistent"
        )
    return {
        "labels": list(LOGIC_ERROR_LABELS),
        "values": [counts[label] for label in LOGIC_ERROR_LABELS],
        "total": total,
        "caught": caught,
    }


# --------------------------------------------------------------------------- #
# Section 2: baselineComparison
# --------------------------------------------------------------------------- #
def _round_rate(value: Any) -> float:
    """Round a rate to the chart-schema presentation precision."""
    try:
        return round(float(value), _RATE_DIGITS)
    except (TypeError, ValueError):
        return 0.0


def _build_baseline_chart(baseline: dict) -> dict[str, Any]:
    table = baseline.get("comparisonTable")
    if not isinstance(table, list) or not table:
        raise ChartDataError("baseline-comparison.json has no comparisonTable")
    by_policy = {row["policy"]: row for row in table if "policy" in row}
    missing = [p for p in BASELINE_POLICY_ORDER if p not in by_policy]
    if missing:
        raise ChartDataError(
            f"baseline comparisonTable is missing policies: {missing}"
        )
    return {
        "labels": list(BASELINE_POLICY_ORDER),
        "errorCatchRate": [
            _round_rate(by_policy[p].get("errorCatchRate")) for p in BASELINE_POLICY_ORDER
        ],
        "unsafeAcceptances": [
            int(by_policy[p].get("unsafeAcceptances", 0)) for p in BASELINE_POLICY_ORDER
        ],
        "coverageRate": [
            _round_rate(by_policy[p].get("coverageRate")) for p in BASELINE_POLICY_ORDER
        ],
    }


# --------------------------------------------------------------------------- #
# Section 3: illPosedCatchRate
# --------------------------------------------------------------------------- #
def _build_ill_posed_chart(ill_posed: dict) -> dict[str, Any]:
    cr = ill_posed.get("catchRate", {})
    ip = cr.get("illPosed", {})
    wp = cr.get("wellPosedControls", {})
    by_category_raw = ip.get("byCategory", {})
    if not isinstance(by_category_raw, dict) or not by_category_raw:
        raise ChartDataError("ill-posed-audit.json has no catchRate.illPosed.byCategory")
    # Preserve the artifact's (sorted) category order; emit a compact
    # {caught, total, catchRate} triple per category.
    by_category = {
        cat: {
            "caught": int(v.get("caught", 0)),
            "total": int(v.get("total", 0)),
            "catchRate": _round_rate(v.get("catchRate", 0.0)),
        }
        for cat, v in sorted(by_category_raw.items())
    }
    return {
        "byCategory": by_category,
        "total": int(ip.get("total", sum(v["total"] for v in by_category.values()))),
        "caught": int(ip.get("caught", sum(v["caught"] for v in by_category.values()))),
        "falseAlarmRate": _round_rate(wp.get("falseAlarmRate", 0.0)),
    }


# --------------------------------------------------------------------------- #
# Section 4: selfCorrection
# --------------------------------------------------------------------------- #
def _build_self_correction_chart(self_correction: dict) -> dict[str, Any]:
    totals = self_correction.get("totals", {})
    err_red = totals.get("errorReductionRate")
    rej_cleared = totals.get("rejectionClearedRate")
    if err_red is None or rej_cleared is None:
        raise ChartDataError(
            "self-correction-audit.json is missing errorReductionRate / "
            "rejectionClearedRate in totals"
        )
    return {
        "errorReductionRate": _round_rate(err_red),
        "rejectionClearedRate": _round_rate(rej_cleared),
    }


# --------------------------------------------------------------------------- #
# Build / canonical bytes / write / check
# --------------------------------------------------------------------------- #
def build_chart_data(
    logic_error: dict | None = None,
    baseline: dict | None = None,
    ill_posed: dict | None = None,
    self_correction: dict | None = None,
) -> dict[str, Any]:
    """Assemble the chart-data payload from the four source artifacts.

    Sources default to the on-disk canonical artifacts; callers (tests) may
    pass pre-loaded dicts to project from fixtures instead.
    """
    logic_error = logic_error if logic_error is not None else _load_json(LOGIC_ERROR_PATH)
    baseline = baseline if baseline is not None else _load_json(BASELINE_PATH)
    ill_posed = ill_posed if ill_posed is not None else _load_json(ILL_POSED_PATH)
    self_correction = (
        self_correction if self_correction is not None else _load_json(SELF_CORRECTION_PATH)
    )
    _require_source_schemas(logic_error, baseline, ill_posed, self_correction)

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "logicErrorCatchRate": _build_logic_error_chart(logic_error),
        "baselineComparison": _build_baseline_chart(baseline),
        "illPosedCatchRate": _build_ill_posed_chart(ill_posed),
        "selfCorrection": _build_self_correction_chart(self_correction),
        "evidenceClass": "development-only",
        "interpretation": (
            "Flat, chart-ready projection of the GOAI benchmark artifacts for "
            "the Hugging Face demo's visualization. Every value is derived "
            "from a canonical source artifact; this file adds no new evidence. "
            "It is INSTRUMENT evidence about deterministic detectors, NOT a "
            "model-capability claim."
        ),
        "claimCeiling": dict(CLAIM_CEILING),
        **CLAIM_CEILING,
    }
    return payload


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_chart_data(output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_chart_data()
    output_path.write_bytes(_canonical_bytes(payload))
    return payload


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive canonical bytes and byte-compare against the on-disk file",
    )
    args = parser.parse_args()

    if args.check:
        try:
            expected = build_chart_data()
        except ChartDataError as exc:
            print(f"CHART-DATA: FAIL (cannot rebuild: {exc})")
            return 1
        if not args.output.is_file():
            print("CHART-DATA: FAIL (artifact missing)")
            return 1
        on_disk_bytes = args.output.read_bytes()
        expected_bytes = _canonical_bytes(expected)
        if on_disk_bytes != expected_bytes:
            print("CHART-DATA: FAIL (bytes not canonical/current)")
            print(
                f"  on-disk sha256={_sha256(on_disk_bytes)} "
                f"expected sha256={_sha256(expected_bytes)}"
            )
            return 1
        print(
            "CHART-DATA: PASS ("
            f"logicError total={expected['logicErrorCatchRate']['total']}; "
            f"caught={expected['logicErrorCatchRate']['caught']}; "
            f"illPosed caught={expected['illPosedCatchRate']['caught']}/"
            f"{expected['illPosedCatchRate']['total']}; "
            f"selfCorrection errReduction={expected['selfCorrection']['errorReductionRate']})"
        )
        return 0

    try:
        payload = write_chart_data(args.output)
    except ChartDataError as exc:
        print(f"CHART-DATA: cannot build ({exc})")
        return 1
    print(
        json.dumps(
            {
                "schema": payload["schema"],
                "output": str(args.output),
                "logicErrorCatchRate": payload["logicErrorCatchRate"],
                "baselineComparison": payload["baselineComparison"],
                "illPosedCatchRate": payload["illPosedCatchRate"],
                "selfCorrection": payload["selfCorrection"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
