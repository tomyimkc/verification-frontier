#!/usr/bin/env python3
"""Write a deterministic offline health receipt for the hosted demo logic."""
from __future__ import annotations

import json
from pathlib import Path

from demo_logic import frontier_gate_preview, public_status, verify_si, verify_symbolic

HERE = Path(__file__).resolve().parent


def main() -> int:
    symbolic = verify_symbolic("x^2+2*x+1", "(x+1)^2")
    status = public_status()
    checks = {
        "siAccepted": verify_si("9.8 m/s", "9.8 m/s")["verdict"] == "accepted",
        "siWrongDimensionRejected": (
            verify_si("9.8 m/s^2", "9.8 m/s")["verdict"] == "rejected"
        ),
        "symbolicAcceptedOrUnavailableFailClosed": (
            symbolic["verdict"] == "accepted"
            or (
                symbolic["verdict"] == "abstain"
                and symbolic["reasonCode"] == "sympy_unavailable"
            )
        ),
        "incompleteGateAbstains": (
            frontier_gate_preview(True, False, True)["result"]["verdict"] == "abstain"
        ),
        "completeGateActivatesPreview": (
            frontier_gate_preview(True, True, True)["result"]["verdict"] == "accepted"
        ),
        "confirmatoryOutcomeWithheld": (
            status["confirmatoryOutcomesAvailable"] is False
        ),
        "publicSealValid": (
            status["syntheticRehearsalSealValidation"]["status"] == "PASS"
        ),
    }
    report = {
        "schema": "goai-hosted-demo-healthcheck/v1",
        "checkedOn": "2026-08-01",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "networkCalls": 0,
        "modelCalls": 0,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    (HERE / "healthcheck.public-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
