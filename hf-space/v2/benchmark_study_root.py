#!/usr/bin/env python3
"""Adversarial benchmark for the development-only Study Root v3."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from v2.protocol_twin import (
    ABLATION_VARIANTS,
    ARMS,
    DEFAULT_TWIN,
    DEFAULT_VALIDATION as DEFAULT_TWIN_VALIDATION,
)
from v2.study_root import (
    DEFAULT_RECEIPT_INDEX,
    DEFAULT_RECEIPT_STORE,
    DEFAULT_RECEIPT_VALIDATION,
    build_study_materials,
    load_json,
    validate_study_materials,
)

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "artifacts" / "study-root-dag-benchmark.json"

Mutation = Callable[
    [
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
    None,
]


def _different_decision(value: str) -> str:
    return "abstain" if value != "abstain" else "accepted"


def _root_mutations() -> list[tuple[str, Mutation]]:
    specifications = (
        ("schema", "invalid/schema"),
        ("status", "CONFIRMATORY"),
        ("studyId", "invalid-study"),
        ("protocolTwinRootSha256", "0" * 64),
        ("protocolTwinValidationSha256", "0" * 64),
        ("armResultManifestSha256", "0" * 64),
        ("ablationResultManifestSha256", "0" * 64),
        ("receiptRehearsalIndexSha256", "0" * 64),
        ("receiptRehearsalValidationSha256", "0" * 64),
        ("receiptGraphReportSha256", "0" * 64),
        ("sourceFileSha256s", {}),
        ("requiredArmRowCount", 755),
        ("requiredB6RowCount", 107),
        ("requiredAblationRowCount", 1403),
        ("requiredAblationVariantCount", 12),
        ("transferExecutionReceiptCount", 5),
        ("candidateOnly", False),
        ("canClaimAGI", True),
        ("winnerLevelEligible", True),
        ("winnerLevelGateMet", True),
    )
    mutations: list[tuple[str, Mutation]] = []
    for field, value in specifications:
        def mutate(
            root,
            _arms,
            _ablations,
            _twin,
            _index,
            _validation,
            *,
            field=field,
            value=value,
        ):
            root[field] = copy.deepcopy(value)

        mutations.append((f"root-{field}", mutate))
    return mutations


def _arm_mutations() -> list[tuple[str, Mutation]]:
    mutations: list[tuple[str, Mutation]] = []
    for arm in ARMS:
        for mutation_name in (
            "missing-row",
            "duplicate-row",
            "decision-drift",
            "candidate-hash-drift",
            "schema-drift",
            "budget-drift",
            "claim-drift",
            "source-root-drift",
        ):
            def mutate(
                _root,
                arms,
                _ablations,
                _twin,
                _index,
                _validation,
                *,
                arm=arm,
                mutation_name=mutation_name,
            ):
                row_index = next(
                    index
                    for index, row in enumerate(arms["rows"])
                    if row["arm"] == arm
                )
                row = arms["rows"][row_index]
                if mutation_name == "missing-row":
                    del arms["rows"][row_index]
                elif mutation_name == "duplicate-row":
                    arms["rows"].append(copy.deepcopy(row))
                elif mutation_name == "decision-drift":
                    row["decision"] = _different_decision(row["decision"])
                elif mutation_name == "candidate-hash-drift":
                    row["candidateSha256"] = "0" * 64
                elif mutation_name == "schema-drift":
                    row["schema"] = "invalid/schema"
                elif mutation_name == "budget-drift":
                    row["budget"]["verifierCallCap"] += 1
                elif mutation_name == "claim-drift":
                    row["canClaimAGI"] = True
                elif mutation_name == "source-root-drift":
                    row["sourceProtocolTwinRootSha256"] = "0" * 64

            mutations.append((f"arm-{arm}-{mutation_name}", mutate))
    return mutations


def _ablation_mutations() -> list[tuple[str, Mutation]]:
    mutations: list[tuple[str, Mutation]] = []
    variants = [
        (group, variant)
        for group, values in ABLATION_VARIANTS.items()
        for variant in values
    ]
    for group, variant in variants:
        for mutation_name in (
            "missing-row",
            "duplicate-row",
            "decision-drift",
            "candidate-hash-drift",
            "schema-drift",
            "budget-drift",
        ):
            def mutate(
                _root,
                _arms,
                ablations,
                _twin,
                _index,
                _validation,
                *,
                group=group,
                variant=variant,
                mutation_name=mutation_name,
            ):
                row_index = next(
                    index
                    for index, row in enumerate(ablations["rows"])
                    if row["ablation"] == group
                    and row["variant"] == variant
                )
                row = ablations["rows"][row_index]
                if mutation_name == "missing-row":
                    del ablations["rows"][row_index]
                elif mutation_name == "duplicate-row":
                    ablations["rows"].append(copy.deepcopy(row))
                elif mutation_name == "decision-drift":
                    row["decision"] = _different_decision(row["decision"])
                elif mutation_name == "candidate-hash-drift":
                    row["candidateSha256"] = "0" * 64
                elif mutation_name == "schema-drift":
                    row["schema"] = "invalid/schema"
                elif mutation_name == "budget-drift":
                    row["budget"]["extensionTestCap"] += 1

            mutations.append(
                (f"ablation-{group}-{variant}-{mutation_name}", mutate)
            )
    return mutations


def _cross_mutations() -> list[tuple[str, Mutation]]:
    def missing_chain(_root, _arms, _ablations, _twin, index, _validation):
        del index["chainSha256s"][0]

    def bogus_chain(_root, _arms, _ablations, _twin, index, _validation):
        index["chainSha256s"][0] = "0" * 64

    def duplicate_chain(_root, _arms, _ablations, _twin, index, _validation):
        index["chainSha256s"].append(index["chainSha256s"][0])

    def validation_invalid(
        _root, _arms, _ablations, _twin, _index, validation
    ):
        validation["status"] = "INVALID"

    def validation_count(
        _root, _arms, _ablations, _twin, _index, validation
    ):
        validation["validChainCount"] = 0

    def twin_root(_root, _arms, _ablations, twin, _index, _validation):
        twin["protocolTwinRootSha256"] = "0" * 64

    def twin_contact(_root, _arms, _ablations, twin, _index, _validation):
        twin["modelContact"] = True
        twin["modelCallCount"] = 1

    def arm_manifest_hash(
        _root, arms, _ablations, _twin, _index, _validation
    ):
        arms["manifestSha256"] = "0" * 64

    def ablation_manifest_hash(
        _root, _arms, ablations, _twin, _index, _validation
    ):
        ablations["manifestSha256"] = "0" * 64

    def root_execution_list(
        root, _arms, _ablations, _twin, _index, _validation
    ):
        del root["transferExecutionReceiptSha256s"][0]

    return [
        ("cross-missing-chain", missing_chain),
        ("cross-bogus-chain", bogus_chain),
        ("cross-duplicate-chain", duplicate_chain),
        ("cross-validation-status", validation_invalid),
        ("cross-validation-count", validation_count),
        ("cross-twin-root", twin_root),
        ("cross-twin-contact", twin_contact),
        ("cross-arm-manifest-hash", arm_manifest_hash),
        ("cross-ablation-manifest-hash", ablation_manifest_hash),
        ("cross-transfer-execution-list", root_execution_list),
    ]


def mutation_catalog() -> list[tuple[str, Mutation]]:
    catalog = (
        _root_mutations()
        + _arm_mutations()
        + _ablation_mutations()
        + _cross_mutations()
    )
    if len(catalog) != 164:
        raise AssertionError(f"expected 164 mutations, got {len(catalog)}")
    return catalog


def run_benchmark(
    *,
    twin: dict[str, Any],
    twin_validation: dict[str, Any],
    receipt_index: dict[str, Any],
    receipt_validation: dict[str, Any],
    receipt_store: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    valid_cases: list[dict[str, Any]] = []
    valid_roots: set[str] = set()
    for index in range(24):
        study_id = f"goai-development-study-root-v3-{index:02d}"
        root, arms, ablations = build_study_materials(
            study_id=study_id,
            twin=twin,
            twin_validation=twin_validation,
            receipt_index=receipt_index,
            receipt_validation=receipt_validation,
            receipt_store=receipt_store,
        )
        issues, report = validate_study_materials(
            root,
            arms,
            ablations,
            twin=twin,
            twin_validation=twin_validation,
            receipt_index=receipt_index,
            receipt_validation=receipt_validation,
            receipt_store=receipt_store,
        )
        passed = not issues and report["status"] == "PASS"
        if not passed:
            errors.append(f"valid case {study_id} was rejected")
        valid_roots.add(str(root["studyRootSha256"]))
        valid_cases.append(
            {
                "caseId": study_id,
                "status": "PASS" if passed else "FAIL",
                "studyRootSha256": root["studyRootSha256"],
                "issueCodes": [issue["code"] for issue in issues],
            }
        )
    if len(valid_roots) != 24:
        errors.append("valid DAG roots are not distinct")

    base_root, base_arms, base_ablations = build_study_materials(
        study_id="goai-development-study-root-v3-00",
        twin=twin,
        twin_validation=twin_validation,
        receipt_index=receipt_index,
        receipt_validation=receipt_validation,
        receipt_store=receipt_store,
    )
    invalid_cases: list[dict[str, Any]] = []
    for case_id, mutation in mutation_catalog():
        root = copy.deepcopy(base_root)
        arms = copy.deepcopy(base_arms)
        ablations = copy.deepcopy(base_ablations)
        mutated_twin = copy.deepcopy(twin)
        index = copy.deepcopy(receipt_index)
        validation = copy.deepcopy(receipt_validation)
        mutation(
            root,
            arms,
            ablations,
            mutated_twin,
            index,
            validation,
        )
        issues, report = validate_study_materials(
            root,
            arms,
            ablations,
            twin=mutated_twin,
            twin_validation=twin_validation,
            receipt_index=index,
            receipt_validation=validation,
            receipt_store=receipt_store,
        )
        rejected = bool(issues) and report["status"] == "INVALID"
        if not rejected:
            errors.append(f"invalid case {case_id} was accepted")
        invalid_cases.append(
            {
                "caseId": case_id,
                "status": "PASS" if rejected else "FAIL",
                "issueCodes": sorted(
                    {issue["code"] for issue in issues}
                ),
            }
        )

    issue_codes = sorted(
        {
            code
            for case in invalid_cases
            for code in case["issueCodes"]
        }
    )
    report = {
        "schema": "goai-frontier-study-root-dag-benchmark/v1",
        "status": "PASS" if not errors else "INVALID",
        "validDagCount": len(valid_cases),
        "validDagPassed": sum(
            case["status"] == "PASS" for case in valid_cases
        ),
        "validDagTopologyCount": 1,
        "validSerializationVariantCount": len(valid_cases),
        "validDagDiversity": (
            "24 deterministic row-order serialization variants of one "
            "valid DAG topology, bound by serializationVariant"
        ),
        "invalidDagCount": len(invalid_cases),
        "invalidDagRejected": sum(
            case["status"] == "PASS" for case in invalid_cases
        ),
        "stableTypedIssueCodes": issue_codes,
        "validCases": valid_cases,
        "invalidCases": invalid_cases,
        "errors": errors,
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
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    errors, report = run_benchmark(
        twin=load_json(DEFAULT_TWIN),
        twin_validation=load_json(DEFAULT_TWIN_VALIDATION),
        receipt_index=load_json(DEFAULT_RECEIPT_INDEX),
        receipt_validation=load_json(DEFAULT_RECEIPT_VALIDATION),
        receipt_store=DEFAULT_RECEIPT_STORE,
    )
    expected = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if args.check:
        if not args.output.is_file() or args.output.read_text(
            encoding="utf-8"
        ) != expected:
            print(f"STUDY ROOT DAG BENCHMARK STALE: {args.output}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected, encoding="utf-8")
    print(
        "STUDY ROOT DAG BENCHMARK: "
        f"{report['status']} "
        f"({report['validDagPassed']}/"
        f"{report['validSerializationVariantCount']} valid serialization "
        "variants of one topology; "
        f"{report['invalidDagRejected']}/{report['invalidDagCount']} invalid)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
