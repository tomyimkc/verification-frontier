#!/usr/bin/env python3
"""Deterministic adversarial benchmark for the public receipt protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from v2.build_receipt_rehearsal import build
from v2.receipt_protocol import (
    canonical_json_bytes,
    load_receipt,
    validate_extension_chain,
    validate_result_receipts,
)

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "artifacts" / "receipt-protocol-benchmark.json"


def _fresh() -> tuple[tempfile.TemporaryDirectory, Path, dict]:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    store = root / "receipts"
    index_path = root / "index.json"
    errors, _ = build(store, index_path, root / "validation.json")
    if errors:
        temp.cleanup()
        raise RuntimeError(f"receipt rehearsal setup failed: {errors}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    return temp, store, index


def _physics_chain(store: Path, index: dict) -> tuple[str, dict, dict]:
    for digest in index["chainSha256s"]:
        errors, report = validate_extension_chain(store, digest)
        if errors:
            raise RuntimeError(f"invalid baseline chain {digest}: {errors}")
        if report["domain"] == "physics":
            chain, load_errors = load_receipt(store, digest)
            if load_errors or chain is None:
                raise RuntimeError(f"cannot load physics chain: {load_errors}")
            return digest, chain, report
    raise RuntimeError("physics chain not found")


def run_benchmark() -> dict:
    cases: list[dict] = []

    temp, store, index = _fresh()
    try:
        passed = 0
        for digest in index["chainSha256s"]:
            errors, report = validate_extension_chain(store, digest)
            passed += int(not errors and report["status"] == "PASS")
        cases.append(
            {
                "case": "intact-development-chains",
                "expected": "3/3 PASS",
                "observed": f"{passed}/3 PASS",
                "passed": passed == 3,
            }
        )
    finally:
        temp.cleanup()

    temp, store, index = _fresh()
    try:
        digest, chain, _ = _physics_chain(store, index)
        proposal, load_errors = load_receipt(store, chain["proposalSha256"])
        if load_errors or proposal is None:
            raise RuntimeError(f"cannot load proposal: {load_errors}")
        candidate = proposal["candidateSha256"]
        (store / "blobs" / f"{candidate}.blob").unlink()
        errors, _ = validate_extension_chain(store, digest)
        detected = any("missing evidence blob" in error for error in errors)
        cases.append(
            {
                "case": "missing-evidence-blob",
                "expected": "INVALID",
                "observed": "INVALID" if detected else "NOT DETECTED",
                "passed": detected,
            }
        )
    finally:
        temp.cleanup()

    temp, store, index = _fresh()
    try:
        digest, chain, _ = _physics_chain(store, index)
        proposal_path = store / f"{chain['proposalSha256']}.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal["taskId"] = "tampered-after-hash"
        proposal_path.write_bytes(canonical_json_bytes(proposal))
        errors, _ = validate_extension_chain(store, digest)
        detected = any("content hash mismatch" in error for error in errors)
        cases.append(
            {
                "case": "content-tamper",
                "expected": "INVALID",
                "observed": "INVALID" if detected else "NOT DETECTED",
                "passed": detected,
            }
        )
    finally:
        temp.cleanup()

    temp, store, index = _fresh()
    try:
        digest, chain, _ = _physics_chain(store, index)
        missing = chain["reviewDecisionSha256s"][0]
        (store / f"{missing}.json").unlink()
        errors, _ = validate_extension_chain(store, digest)
        detected = (
            any("missing receipt file" in error for error in errors)
            and any("owner and expert-ai" in error for error in errors)
        )
        cases.append(
            {
                "case": "missing-independent-review",
                "expected": "INVALID",
                "observed": "INVALID" if detected else "NOT DETECTED",
                "passed": detected,
            }
        )
    finally:
        temp.cleanup()

    temp, store, index = _fresh()
    try:
        _, chain, report = _physics_chain(store, index)
        result = {
            "extensionReceiptSha256": report["chainSha256"],
            "reviewDecisionSha256s": report["reviewDecisionSha256s"],
            "transferTaskIds": ["unlinked-a", "unlinked-b"],
            "transferPassed": True,
            "protectedSuiteReceiptSha256": report[
                "protectedSuiteReceiptSha256"
            ],
            "protectedSuitePassed": True,
        }
        errors = validate_result_receipts(store, result)
        detected = any(
            "transfer task IDs do not match" in error for error in errors
        )
        cases.append(
            {
                "case": "result-cross-link-mismatch",
                "expected": "INVALID",
                "observed": "INVALID" if detected else "NOT DETECTED",
                "passed": detected,
            }
        )
    finally:
        temp.cleanup()

    temp, store, index = _fresh()
    try:
        _, _, report = _physics_chain(store, index)
        result = {
            "extensionReceiptSha256": report["chainSha256"],
            "reviewDecisionSha256s": report["reviewDecisionSha256s"],
            "transferTaskIds": report["transferTaskIds"],
            "transferPassed": True,
            "protectedSuiteReceiptSha256": report[
                "protectedSuiteReceiptSha256"
            ],
            "protectedSuitePassed": True,
        }
        errors = validate_result_receipts(
            store,
            result,
            required_evidence_class="confirmatory",
        )
        detected = any("evidenceClass must be 'confirmatory'" in error for error in errors)
        cases.append(
            {
                "case": "development-receipt-used-as-confirmatory",
                "expected": "INVALID",
                "observed": "INVALID" if detected else "NOT DETECTED",
                "passed": detected,
            }
        )
    finally:
        temp.cleanup()

    temp, store, index = _fresh()
    try:
        _, chain, _ = _physics_chain(store, index)
        chain["evidenceClass"] = "confirmatory"
        chain["confirmatoryEligible"] = True
        data = canonical_json_bytes(chain)
        forged_digest = hashlib.sha256(data).hexdigest()
        (store / f"{forged_digest}.json").write_bytes(data)
        errors, _ = validate_extension_chain(store, forged_digest)
        detected = any(
            "confirmatory receipt validation is disabled" in error
            for error in errors
        )
        cases.append(
            {
                "case": "self-declared-confirmatory-chain",
                "expected": "INVALID",
                "observed": "INVALID" if detected else "NOT DETECTED",
                "passed": detected,
            }
        )
    finally:
        temp.cleanup()

    passed_count = sum(case["passed"] for case in cases)
    return {
        "schema": "goai-frontier-receipt-protocol-benchmark/v1",
        "status": "PASS" if passed_count == len(cases) else "FAIL",
        "caseCount": len(cases),
        "passedCount": passed_count,
        "failedCount": len(cases) - passed_count,
        "cases": cases,
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"RECEIPT PROTOCOL BENCHMARK: {report['status']} "
        f"({report['passedCount']}/{report['caseCount']})"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
