#!/usr/bin/env python3
"""Deterministic logic-error catch-rate audit for the verification tiers.

This is the **strongest instrument evidence** in the package: it *plants* known
logic errors across every verifier tier (SI dimension, SymPy equivalence, Lean
proof placeholder) and records whether each was caught. The catch-rate is a
property of the **deterministic verifiers**, not of any model — it answers
"when a logic error is present, does the verifier detect it?"

It is fail-closed: the builder refuses to relax the claim ceiling, and the
checker re-derives the canonical bytes and byte-compares them. Every planted
error must be caught; any miss is recorded as an audit failure (never hidden).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_OUTPUT = HERE / "artifacts"
AUDIT_PATH = DEFAULT_OUTPUT / "logic-error-catch-rate.json"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import demo  # noqa: E402

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}


@dataclass(frozen=True)
class PlantedError:
    """A candidate with a known logic error, plus the expected rejection."""

    error_id: str
    tier: str  # "si" | "sympy" | "lean-placeholder"
    error_type: str  # "dimension_mismatch" | "sign_flip" | ...
    candidate: str
    reference: str
    expected_verdict: str  # always "rejected" for planted errors
    expected_reason_code: str


def _si(candidate: str, reference: str, *, error_id: str, error_type: str) -> PlantedError:
    return PlantedError(error_id, "si", error_type, candidate, reference, "rejected", "")


def _sym(candidate: str, reference: str, *, error_id: str, error_type: str) -> PlantedError:
    return PlantedError(error_id, "sympy", error_type, candidate, reference, "rejected", "")


def planted_errors() -> list[PlantedError]:
    """The frozen set of known logic errors the verifiers must catch."""
    return [
        # ── SI dimension logic errors ──
        _si("9.8 m/s^2", "9.8 m/s", error_id="si-dim-01", error_type="dimension_mismatch"),
        _si("9.8 J", "9.8 m/s", error_id="si-dim-02", error_type="dimension_mismatch"),
        _si("5 kg", "5 N", error_id="si-dim-03", error_type="dimension_mismatch"),
        _si("3 m", "3 m/s", error_id="si-dim-04", error_type="dimension_mismatch"),
        _si("12 W", "12 J", error_id="si-dim-05", error_type="dimension_mismatch"),
        _si("100 Pa", "100 N", error_id="si-dim-06", error_type="dimension_mismatch"),
        # SI value logic errors (wrong magnitude)
        _si("8.0 m/s", "9.8 m/s", error_id="si-val-01", error_type="value_outside_tolerance"),
        _si("50.0 m/s", "9.8 m/s", error_id="si-val-02", error_type="value_outside_tolerance"),
        # ── SymPy equivalence logic errors ──
        _sym("x^2+2*x+2", "(x+1)^2", error_id="sym-eq-01", error_type="not_equivalent"),
        _sym("x^2+1", "(x+1)^2", error_id="sym-eq-02", error_type="not_equivalent"),
        _sym("x^2-2*x+1", "(x+1)^2", error_id="sym-eq-03", error_type="sign_error"),
        _sym("2*x+1", "(x+1)^2", error_id="sym-eq-04", error_type="missing_term"),
        _sym("(x-1)^2", "(x+1)^2", error_id="sym-eq-05", error_type="sign_error"),
        _sym("x^3+1", "(x+1)^2", error_id="sym-eq-06", error_type="wrong_degree"),
        # ── Proof-placeholder logic errors (caught before coverage abstention) ──
        PlantedError(
            "lean-ph-01", "lean-placeholder", "proof_placeholder",
            "sorry", "have h : True := trivial",
            "rejected", "proof_placeholder",
        ),
        PlantedError(
            "lean-ph-02", "lean-placeholder", "proof_placeholder",
            "admit", "have h : True := trivial",
            "rejected", "proof_placeholder",
        ),
    ]


def _verify_one(planted: PlantedError) -> dict[str, Any]:
    """Run the appropriate verifier tier on one planted error."""
    if planted.tier == "si":
        result = demo.verify_physics(planted.candidate, planted.reference)
    elif planted.tier == "sympy":
        result = demo.verify_math(planted.candidate, planted.reference)
    elif planted.tier == "lean-placeholder":
        # The demo rejects sorry/admit before any coverage abstention.
        result = demo.verify_problem(
            demo.Problem(
                problem_id="audit-lean-placeholder",
                rung="closed",
                tier="formal-proof",
                prompt="placeholder audit",
                gold=planted.reference,
            ),
            planted.candidate,
        )
    else:
        return {"error_id": planted.error_id, "caught": False, "error": f"unknown tier {planted.tier}"}
    caught = result.verdict == planted.expected_verdict
    return {
        "error_id": planted.error_id,
        "tier": planted.tier,
        "error_type": planted.error_type,
        "candidate": planted.candidate,
        "reference": planted.reference,
        "expected_verdict": planted.expected_verdict,
        "observed_verdict": result.verdict,
        "observed_reason_code": result.reason_code,
        "caught": caught,
    }


def build_audit() -> dict[str, Any]:
    errors = planted_errors()
    results = [_verify_one(e) for e in errors]
    caught = sum(1 for r in results if r["caught"])
    total = len(results)
    misses = [r for r in results if not r["caught"]]
    by_tier: dict[str, dict[str, int]] = {}
    for r in results:
        t = r["tier"]
        by_tier.setdefault(t, {"caught": 0, "total": 0})
        by_tier[t]["total"] += 1
        by_tier[t]["caught"] += int(r["caught"])
    return {
        "schema": "goai-logic-error-catch-rate/v1",
        "evidenceClass": "development-only",
        "status": "PASS" if not misses else "FAIL",
        "interpretation": (
            "This audit plants known logic errors across every verifier tier "
            "and records whether each was caught. The catch-rate is a property "
            "of the DETERMINISTIC VERIFIERS, not of any model. It is instrument "
            "evidence that the verifiers are real and fail-closed; it is NOT a "
            "model-capability, capability-uplift, or contest-performance result."
        ),
        "totals": {
            "planted": total,
            "caught": caught,
            "missed": len(misses),
            "catchRate": round(caught / total, 4) if total else 0.0,
        },
        "byTier": {t: {**v, "catchRate": round(v["caught"] / v["total"], 4) if v["total"] else 0.0} for t, v in sorted(by_tier.items())},
        "misses": misses,
        "details": results,
        "scientificOutcome": False,
        "capabilityClaim": False,
        **CLAIM_CEILING,
    }


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_audit(output_path: Path = AUDIT_PATH) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    output_path.write_bytes(_canonical_bytes(audit))
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=AUDIT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        if not args.output.is_file():
            print("LOGIC ERROR AUDIT: FAIL (artifact missing)")
            return 1
        on_disk = json.loads(args.output.read_text(encoding="utf-8"))
        expected = _canonical_bytes(build_audit())
        if args.output.read_bytes() != expected:
            print("LOGIC ERROR AUDIT: FAIL (bytes not canonical/current)")
            return 1
        if on_disk.get("status") != "PASS":
            print(f"LOGIC ERROR AUDIT: FAIL (status={on_disk.get('status')})")
            return 1
        t = on_disk["totals"]
        print(
            f"LOGIC ERROR AUDIT: PASS (planted={t['planted']}; "
            f"caught={t['caught']}; missed={t['missed']}; "
            f"catchRate={t['catchRate']})"
        )
        return 0

    audit = write_audit(args.output)
    t = audit["totals"]
    print(
        json.dumps(
            {
                "schema": audit["schema"],
                "status": audit["status"],
                "totals": t,
                "byTier": audit["byTier"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
