#!/usr/bin/env python3
"""Build and validate the CPU-only GOAI Study Root v3.

The Study Root binds the already-frozen Protocol Twin to complete B0-B6 and
ablation result manifests, the descendant transfer-execution receipt graph,
and the code/specification files that define the development protocol.

This remains development-only machinery.  It does not contact a model
provider, does not make a scientific claim, and cannot make the confirmatory
or winner-level gates eligible.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from v2.protocol_twin import (
    ABLATION_VARIANTS,
    ARMS,
    DEFAULT_TWIN,
    DEFAULT_VALIDATION as DEFAULT_TWIN_VALIDATION,
    build_protocol_twin,
    validate_protocol_twin,
)
from v2.receipt_protocol import (
    load_blob,
    load_receipt,
    validate_extension_chain,
)

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
DEFAULT_RECEIPT_STORE = ARTIFACTS / "receipt-rehearsal"
DEFAULT_RECEIPT_INDEX = ARTIFACTS / "receipt-rehearsal-index.json"
DEFAULT_RECEIPT_VALIDATION = ARTIFACTS / "receipt-rehearsal-validation.json"
DEFAULT_ARM_RESULTS = ARTIFACTS / "study-arm-results.json"
DEFAULT_ABLATION_RESULTS = ARTIFACTS / "study-ablation-results.json"
DEFAULT_STUDY_ROOT = ARTIFACTS / "study-root-v3.json"
DEFAULT_STUDY_VALIDATION = ARTIFACTS / "study-root-v3-validation.json"

STUDY_ID = "goai-development-study-root-v3"
STUDY_ID_PATTERN = re.compile(r"^goai-development-study-root-v3(?:-[0-9]{2})?$")
SOURCE_FILES = (
    "PREREGISTRATION.md",
    "FRONTIER-EXPANSION-SPEC.md",
    "HUMAN-GATE-RUBRIC.md",
    "PROTOCOL-TWIN-SPEC.md",
    "STUDY-ROOT-V3-SPEC.md",
    "receipt_protocol.py",
    "confirmatory_scoring.py",
    "protocol_twin.py",
    "study_root.py",
    "benchmark_study_root.py",
    "simulate_scorer.py",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _claim_ceiling() -> dict[str, Any]:
    return {
        "evidenceClass": "development-only",
        "scientificOutcome": False,
        "statisticsEligible": False,
        "confirmatoryEligible": False,
        "winnerLevelEligible": False,
        "winnerLevelGateMet": False,
        "modelContact": False,
        "modelCallCount": 0,
        "networkCallCount": 0,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def _serialization_variant(study_id: str) -> int:
    match = re.search(r"-([0-9]{2})$", study_id)
    return int(match.group(1)) if match else 0


def _rotate(values: list[dict[str, Any]], amount: int) -> list[dict[str, Any]]:
    if not values:
        return values
    offset = amount % len(values)
    return values[offset:] + values[:offset]


def build_arm_result_manifest(
    twin: dict[str, Any],
    *,
    study_id: str = STUDY_ID,
) -> dict[str, Any]:
    rows = []
    for source in twin["armRuns"]:
        row = copy.deepcopy(source)
        row["schema"] = "goai-frontier-study-arm-result/v1"
        row["studyId"] = study_id
        row["sourceProtocolTwinRootSha256"] = twin[
            "protocolTwinRootSha256"
        ]
        rows.append(row)
    variant = _serialization_variant(study_id)
    rows = _rotate(rows, variant)
    payload = {
        "schema": "goai-frontier-study-arm-result-manifest/v1",
        "studyId": study_id,
        "serializationVariant": variant,
        "sourceProtocolTwinRootSha256": twin[
            "protocolTwinRootSha256"
        ],
        "requiredArms": list(ARMS),
        "requiredModelFamilies": twin["requiredModelFamilies"],
        "requiredReplicates": twin["requiredReplicates"],
        "rowCount": len(rows),
        "rows": rows,
        **_claim_ceiling(),
    }
    payload["rowsSha256"] = sha256_value(rows)
    payload["manifestSha256"] = sha256_value(payload)
    return payload


def build_ablation_result_manifest(
    twin: dict[str, Any],
    *,
    study_id: str = STUDY_ID,
) -> dict[str, Any]:
    rows = []
    for source in twin["ablationRuns"]:
        row = copy.deepcopy(source)
        row["schema"] = "goai-frontier-study-ablation-result/v1"
        row["studyId"] = study_id
        row["sourceProtocolTwinRootSha256"] = twin[
            "protocolTwinRootSha256"
        ]
        rows.append(row)
    variant = _serialization_variant(study_id)
    rows = _rotate(rows, variant * 3)
    payload = {
        "schema": "goai-frontier-study-ablation-result-manifest/v1",
        "studyId": study_id,
        "serializationVariant": variant,
        "sourceProtocolTwinRootSha256": twin[
            "protocolTwinRootSha256"
        ],
        "requiredAblationGroups": {
            key: list(values)
            for key, values in ABLATION_VARIANTS.items()
        },
        "requiredModelFamilies": twin["requiredModelFamilies"],
        "requiredReplicates": twin["requiredReplicates"],
        "rowCount": len(rows),
        "rows": rows,
        **_claim_ceiling(),
    }
    payload["rowsSha256"] = sha256_value(rows)
    payload["manifestSha256"] = sha256_value(payload)
    return payload


def _receipt_graph(
    receipt_store: Path,
    receipt_index: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    execution_digests: list[str] = []
    for digest in receipt_index.get("chainSha256s", []):
        chain_errors, report = validate_extension_chain(
            receipt_store,
            str(digest),
        )
        errors.extend(
            f"{digest}: {error}" for error in chain_errors
        )
        reports.append(report)
        execution_digests.extend(
            str(value)
            for value in report.get(
                "transferExecutionReceiptSha256s",
                [],
            )
        )
    return reports, errors, sorted(set(execution_digests))


def _receipt_material_errors(
    receipt_store: Path,
    receipt_index: dict[str, Any],
    receipt_validation: dict[str, Any],
    reports: list[dict[str, Any]],
    graph_errors: list[str],
) -> list[str]:
    errors: list[str] = []
    expected_index_fields = {
        "schema": "goai-frontier-receipt-rehearsal-index/v1",
        "status": "PASS",
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    for field, expected in expected_index_fields.items():
        if receipt_index.get(field) != expected:
            errors.append(
                f"receipt index {field} must be {expected!r}"
            )
    receipt_digests = receipt_index.get("receiptSha256s")
    blob_digests = receipt_index.get("blobSha256s")
    chain_digests = receipt_index.get("chainSha256s")
    if not isinstance(receipt_digests, list):
        errors.append("receipt index receiptSha256s must be a list")
        receipt_digests = []
    if not isinstance(blob_digests, list):
        errors.append("receipt index blobSha256s must be a list")
        blob_digests = []
    if not isinstance(chain_digests, list):
        errors.append("receipt index chainSha256s must be a list")
        chain_digests = []
    if len(receipt_digests) != len(set(map(str, receipt_digests))):
        errors.append("receipt index contains duplicate receipt hashes")
    if len(blob_digests) != len(set(map(str, blob_digests))):
        errors.append("receipt index contains duplicate blob hashes")
    if len(chain_digests) != 3 or len(set(map(str, chain_digests))) != 3:
        errors.append("receipt index must contain three distinct chains")
    if not set(map(str, chain_digests)).issubset(
        set(map(str, receipt_digests))
    ):
        errors.append("receipt index chain hashes are absent from receipt set")
    if receipt_index.get("receiptCount") != len(receipt_digests):
        errors.append("receipt index receiptCount mismatch")
    if receipt_index.get("blobCount") != len(blob_digests):
        errors.append("receipt index blobCount mismatch")
    for digest in map(str, receipt_digests):
        _, load_errors = load_receipt(receipt_store, digest)
        errors.extend(
            f"indexed receipt {digest}: {error}" for error in load_errors
        )
    for digest in map(str, blob_digests):
        _, load_errors = load_blob(receipt_store, digest)
        errors.extend(
            f"indexed blob {digest}: {error}" for error in load_errors
        )
    expected_validation = {
        "schema": "goai-frontier-receipt-rehearsal-validation/v1",
        "status": "PASS" if not graph_errors else "INVALID",
        "chainCount": len(chain_digests),
        "validChainCount": sum(
            report.get("status") == "PASS" for report in reports
        ),
        "receiptCount": len(receipt_digests),
        "blobCount": len(blob_digests),
        "reports": reports,
        "errors": graph_errors,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    if receipt_validation != expected_validation:
        errors.append(
            "receipt validation does not exactly match graph recomputation"
        )
    return errors


def _source_hashes() -> dict[str, str]:
    return {
        name: sha256_bytes((HERE / name).read_bytes())
        for name in SOURCE_FILES
    }


def build_study_materials(
    *,
    study_id: str = STUDY_ID,
    twin: dict[str, Any] | None = None,
    twin_validation: dict[str, Any] | None = None,
    receipt_index: dict[str, Any] | None = None,
    receipt_validation: dict[str, Any] | None = None,
    receipt_store: Path = DEFAULT_RECEIPT_STORE,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not STUDY_ID_PATTERN.fullmatch(study_id):
        raise ValueError(f"invalid development studyId: {study_id!r}")
    twin = copy.deepcopy(twin or build_protocol_twin())
    if twin_validation is None:
        _, twin_validation = validate_protocol_twin(twin)
    if receipt_index is None:
        receipt_index = load_json(DEFAULT_RECEIPT_INDEX)
    if receipt_validation is None:
        receipt_validation = load_json(DEFAULT_RECEIPT_VALIDATION)
    arm_manifest = build_arm_result_manifest(twin, study_id=study_id)
    ablation_manifest = build_ablation_result_manifest(
        twin,
        study_id=study_id,
    )
    reports, receipt_errors, execution_digests = _receipt_graph(
        receipt_store,
        receipt_index,
    )
    receipt_errors = receipt_errors + _receipt_material_errors(
        receipt_store,
        receipt_index,
        receipt_validation,
        reports,
        receipt_errors,
    )
    payload = {
        "schema": "goai-frontier-study-root/v3",
        "studyId": study_id,
        "serializationVariant": _serialization_variant(study_id),
        "status": "DEVELOPMENT_ONLY",
        "protocolTwinRootSha256": twin[
            "protocolTwinRootSha256"
        ],
        "protocolTwinValidationSha256": sha256_value(
            twin_validation
        ),
        "armResultManifestSha256": sha256_value(arm_manifest),
        "ablationResultManifestSha256": sha256_value(
            ablation_manifest
        ),
        "receiptRehearsalIndexSha256": sha256_value(
            receipt_index
        ),
        "receiptRehearsalValidationSha256": sha256_value(
            receipt_validation
        ),
        "extensionChainSha256s": sorted(
            str(value)
            for value in receipt_index.get("chainSha256s", [])
        ),
        "transferExecutionReceiptSha256s": execution_digests,
        "receiptGraphReportSha256": sha256_value(reports),
        "receiptGraphErrorCount": len(receipt_errors),
        "sourceFileSha256s": _source_hashes(),
        "requiredArmRowCount": len(twin["armRuns"]),
        "requiredB6RowCount": sum(
            row.get("arm") == "B6-oracle-ceiling"
            for row in twin["armRuns"]
        ),
        "requiredAblationRowCount": len(twin["ablationRuns"]),
        "requiredAblationVariantCount": sum(
            len(values) for values in ABLATION_VARIANTS.values()
        ),
        "transferExecutionReceiptCount": len(execution_digests),
        **_claim_ceiling(),
    }
    payload["studyRootSha256"] = sha256_value(payload)
    return payload, arm_manifest, ablation_manifest


def _issue(
    issues: list[dict[str, str]],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append({"code": code, "path": path, "message": message})


def validate_study_materials(
    study_root: dict[str, Any],
    arm_manifest: dict[str, Any],
    ablation_manifest: dict[str, Any],
    *,
    twin: dict[str, Any] | None = None,
    twin_validation: dict[str, Any] | None = None,
    receipt_index: dict[str, Any] | None = None,
    receipt_validation: dict[str, Any] | None = None,
    receipt_store: Path = DEFAULT_RECEIPT_STORE,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    issues: list[dict[str, str]] = []
    if not isinstance(study_root, dict):
        study_root = {}
        _issue(
            issues,
            "STUDY_ROOT_NOT_OBJECT",
            "$",
            "study root must be a JSON object",
        )
    study_id = str(study_root.get("studyId") or "")
    if not STUDY_ID_PATTERN.fullmatch(study_id):
        _issue(
            issues,
            "STUDY_ID_INVALID",
            "$.studyId",
            "studyId is not an allowed development identifier",
        )
        study_id = STUDY_ID
    twin = copy.deepcopy(twin or build_protocol_twin())
    twin_errors, computed_twin_validation = validate_protocol_twin(twin)
    if twin_validation is None:
        twin_validation = computed_twin_validation
    elif twin_validation != computed_twin_validation:
        _issue(
            issues,
            "PROTOCOL_TWIN_VALIDATION_MISMATCH",
            "$.protocolTwinValidationSha256",
            "supplied Protocol Twin validation does not exactly match "
            "recomputation",
        )
    if twin_errors:
        _issue(
            issues,
            "PROTOCOL_TWIN_INVALID",
            "$.protocolTwinRootSha256",
            f"protocol twin has {len(twin_errors)} validation error(s)",
        )
    if receipt_index is None:
        receipt_index = load_json(DEFAULT_RECEIPT_INDEX)
    if receipt_validation is None:
        receipt_validation = load_json(DEFAULT_RECEIPT_VALIDATION)
    reports, receipt_errors, execution_digests = _receipt_graph(
        receipt_store,
        receipt_index,
    )
    receipt_errors = receipt_errors + _receipt_material_errors(
        receipt_store,
        receipt_index,
        receipt_validation,
        reports,
        receipt_errors,
    )
    if receipt_errors:
        _issue(
            issues,
            "RECEIPT_GRAPH_INVALID",
            "$.extensionChainSha256s",
            f"receipt graph has {len(receipt_errors)} validation error(s)",
        )
    if not all(
        report.get("transferExecutionReceiptsValidated") is True
        for report in reports
    ):
        _issue(
            issues,
            "TRANSFER_EXECUTION_DESCENDANTS_INVALID",
            "$.transferExecutionReceiptSha256s",
            "not every extension chain has validated transfer descendants",
        )

    expected_root, expected_arm, expected_ablation = build_study_materials(
        study_id=study_id,
        twin=twin,
        twin_validation=twin_validation,
        receipt_index=receipt_index,
        receipt_validation=receipt_validation,
        receipt_store=receipt_store,
    )
    if arm_manifest != expected_arm:
        _issue(
            issues,
            "ARM_RESULT_MANIFEST_MISMATCH",
            "$armResultManifest",
            "B0-B6 result manifest does not match the frozen twin",
        )
    if ablation_manifest != expected_ablation:
        _issue(
            issues,
            "ABLATION_RESULT_MANIFEST_MISMATCH",
            "$ablationResultManifest",
            "ablation result manifest does not match the frozen twin",
        )
    if study_root != expected_root:
        _issue(
            issues,
            "STUDY_ROOT_MISMATCH",
            "$",
            "study root does not match the canonical bound materials",
        )
    for label, payload in (
        ("study root", study_root),
        ("arm result manifest", arm_manifest),
        ("ablation result manifest", ablation_manifest),
    ):
        if payload.get("candidateOnly") is not True:
            _issue(
                issues,
                "CLAIM_CEILING_CANDIDATE_ONLY",
                label,
                "candidateOnly must be true",
            )
        if payload.get("canClaimAGI") is not False:
            _issue(
                issues,
                "CLAIM_CEILING_AGI",
                label,
                "canClaimAGI must be false",
            )
        for field in (
            "scientificOutcome",
            "statisticsEligible",
            "confirmatoryEligible",
            "winnerLevelEligible",
            "winnerLevelGateMet",
            "modelContact",
        ):
            if payload.get(field) is not False:
                _issue(
                    issues,
                    "CLAIM_CEILING_RELAXED",
                    f"{label}.{field}",
                    f"{field} must be false",
                )
        for field in ("modelCallCount", "networkCallCount"):
            if payload.get(field) != 0:
                _issue(
                    issues,
                    "CONTACT_COUNT_NONZERO",
                    f"{label}.{field}",
                    f"{field} must be zero",
                )

    b6_rows = [
        row
        for row in arm_manifest.get("rows", [])
        if isinstance(row, dict)
        and row.get("arm") == "B6-oracle-ceiling"
    ]
    constructed_b6_fixture_validated = (
        arm_manifest == expected_arm
        and len(b6_rows) == expected_root["requiredB6RowCount"]
    )
    constructed_ablation_fixture_validated = (
        ablation_manifest == expected_ablation
        and ablation_manifest.get("rowCount")
        == expected_root["requiredAblationRowCount"]
    )
    transfer_execution_validated = (
        not receipt_errors
        and len(execution_digests)
        == expected_root["transferExecutionReceiptCount"]
        and all(
            report.get("transferExecutionReceiptsValidated") is True
            for report in reports
        )
    )
    report = {
        "schema": "goai-frontier-study-root-validation/v3",
        "status": "PASS" if not issues else "INVALID",
        "studyId": study_root.get("studyId"),
        "studyRootSha256": study_root.get("studyRootSha256"),
        "studyRootBound": not issues,
        "studyRootScorerInputsBound": False,
        "constructedArmFixtureRowsValidated": (
            arm_manifest == expected_arm
        ),
        "constructedB6FixtureRowsValidated": (
            constructed_b6_fixture_validated
        ),
        "constructedAblationFixtureRowsValidated": (
            constructed_ablation_fixture_validated
        ),
        "actualB6RowsValidated": False,
        "actualAblationRowsValidated": False,
        "transferExecutionReceiptsValidated": (
            transfer_execution_validated
        ),
        "armRowCount": len(arm_manifest.get("rows", [])),
        "b6RowCount": len(b6_rows),
        "ablationRowCount": len(
            ablation_manifest.get("rows", [])
        ),
        "ablationVariantCount": expected_root[
            "requiredAblationVariantCount"
        ],
        "extensionChainCount": len(reports),
        "transferExecutionReceiptCount": len(execution_digests),
        "protocolValid": False,
        "scientificOutcome": False,
        "statisticsEligible": False,
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "winnerLevelEligible": False,
        "winnerLevelGateMet": False,
        "modelContact": False,
        "modelCallCount": 0,
        "networkCallCount": 0,
        "issues": issues,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return issues, report


def _pretty(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-id", default=STUDY_ID)
    parser.add_argument("--arm-results", type=Path, default=DEFAULT_ARM_RESULTS)
    parser.add_argument(
        "--ablation-results",
        type=Path,
        default=DEFAULT_ABLATION_RESULTS,
    )
    parser.add_argument("--study-root", type=Path, default=DEFAULT_STUDY_ROOT)
    parser.add_argument(
        "--validation",
        type=Path,
        default=DEFAULT_STUDY_VALIDATION,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    twin = load_json(DEFAULT_TWIN)
    twin_validation = load_json(DEFAULT_TWIN_VALIDATION)
    receipt_index = load_json(DEFAULT_RECEIPT_INDEX)
    receipt_validation = load_json(DEFAULT_RECEIPT_VALIDATION)
    root, arm_manifest, ablation_manifest = build_study_materials(
        study_id=args.study_id,
        twin=twin,
        twin_validation=twin_validation,
        receipt_index=receipt_index,
        receipt_validation=receipt_validation,
    )
    issues, report = validate_study_materials(
        root,
        arm_manifest,
        ablation_manifest,
        twin=twin,
        twin_validation=twin_validation,
        receipt_index=receipt_index,
        receipt_validation=receipt_validation,
    )
    outputs = {
        args.arm_results: _pretty(arm_manifest),
        args.ablation_results: _pretty(ablation_manifest),
        args.study_root: _pretty(root),
        args.validation: _pretty(report),
    }
    if args.check:
        stale = [
            str(path)
            for path, expected in outputs.items()
            if not path.is_file()
            or path.read_text(encoding="utf-8") != expected
        ]
        if stale:
            print("STUDY ROOT STALE: " + ", ".join(stale))
            return 1
    else:
        for path, expected in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    print(
        f"STUDY ROOT: {report['status']} "
        f"(arms={report['armRowCount']}, "
        f"B6={report['b6RowCount']}, "
        f"ablations={report['ablationRowCount']}, "
        f"transferExecutions={report['transferExecutionReceiptCount']})"
    )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
