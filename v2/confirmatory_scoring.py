#!/usr/bin/env python3
"""Strict family-clustered scoring for the prospective GOAI benchmark."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from v2.receipt_protocol import validate_result_receipts

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "private" / "confirmatory-tasks.jsonl"
DEFAULT_TRANSFER_MANIFEST = HERE / "private" / "confirmatory-transfer-tasks.jsonl"
DEFAULT_RESULTS = HERE / "private" / "confirmatory-results.jsonl"
DEFAULT_OUTPUT = HERE / "artifacts" / "confirmatory-statistics.json"
DEFAULT_RECEIPT_STORE = HERE / "private" / "confirmatory-receipts"
DEFAULT_STUDY_ROOT = HERE / "artifacts" / "study-root-v3.json"
DEFAULT_STUDY_ARM_RESULTS = HERE / "artifacts" / "study-arm-results.json"
DEFAULT_STUDY_ABLATION_RESULTS = (
    HERE / "artifacts" / "study-ablation-results.json"
)
DEFAULT_STUDY_RECEIPT_INDEX = (
    HERE / "artifacts" / "receipt-rehearsal-index.json"
)
DEFAULT_STUDY_RECEIPT_VALIDATION = (
    HERE / "artifacts" / "receipt-rehearsal-validation.json"
)
PROPOSED_ARM = "B5-proposed"
NON_ORACLE_BASELINES = (
    "B0-raw-model",
    "B1-fixed-verifier",
    "B2-fixed-refinement",
    "B3-act-or-abstain",
    "B4-human-only",
)
REQUIRED_ARMS = NON_ORACLE_BASELINES + (PROPOSED_ARM,)
DEFAULT_REQUIRED_MODEL_FAMILIES = ("qwen", "deepseek")
REQUIRED_REPLICATES = (0, 1, 2)
MINIMUM_INDEPENDENT_CLUSTERS = 30
EXPECTED_DOMAINS = ("physics", "symbolic", "lean")
EXPECTED_FRONTIER_FAMILIES_PER_DOMAIN = 10
EXPECTED_FRONTIER_PAIRS_PER_FAMILY = 2
EXPECTED_CONTROL_PAIRS_PER_DOMAIN = 4
EXPECTED_TRANSFER_PAIRS_PER_FAMILY = 2
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def task_manifest_bytes(tasks: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(
            task,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
        for task in tasks
    ).encode("utf-8")


def task_manifest_sha256(tasks: list[dict[str, Any]]) -> str:
    return hashlib.sha256(task_manifest_bytes(tasks)).hexdigest()


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else math.nan


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _result_key(row: dict[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row["arm"]),
        str(row["modelFamily"]),
        int(row["replicate"]),
        str(row["taskId"]),
    )


def _validate_tasks(
    tasks: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    valid: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"malformed task row {index}: expected object")
            continue
        task_id = str(task.get("taskId") or "")
        pair_id = str(task.get("pairId") or "")
        domain = str(task.get("domain") or "")
        component = str(task.get("component") or "")
        member = str(task.get("member") or "")
        family = str(task.get("generatorFamily") or "")
        row_errors: list[str] = []
        if not task_id:
            row_errors.append("missing taskId")
        elif task_id in seen_ids:
            row_errors.append(f"duplicate taskId {task_id}")
        if not pair_id:
            row_errors.append("missing pairId")
        if domain not in EXPECTED_DOMAINS:
            row_errors.append(f"invalid domain {domain!r}")
        if component not in {"frontier", "control"}:
            row_errors.append(f"invalid component {component!r}")
        if member not in {"valid", "safety"}:
            row_errors.append(f"invalid member {member!r}")
        if not family:
            row_errors.append("missing generatorFamily")
        if row_errors:
            errors.append(
                f"malformed task row {index}: " + "; ".join(row_errors)
            )
            continue
        seen_ids.add(task_id)
        valid.append(task)
    return errors, valid


def _validate_rows(
    tasks: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    task_by_id = {str(task["taskId"]): task for task in tasks}
    seen: set[tuple[str, str, int, str]] = set()
    valid: list[dict[str, Any]] = []
    for index, row in enumerate(results):
        if not isinstance(row, dict):
            errors.append(f"malformed result row {index}: expected object")
            continue
        try:
            key = _result_key(row)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(
                f"malformed result row {index}: {type(exc).__name__}"
            )
            continue
        if not key[0] or not key[1] or not key[3]:
            errors.append(f"malformed result row {index}: empty key field")
            continue
        if key in seen:
            errors.append(f"duplicate result cell: {key}")
            continue
        seen.add(key)
        if key[3] not in task_by_id:
            errors.append(f"unknown task ID: {key[3]}")
            continue
        if row.get("schema") != "goai-frontier-confirmatory-result/v1":
            errors.append(f"{key[3]}: invalid result schema")
            continue
        manifest_task = task_by_id[key[3]]
        identity_errors = [
            field
            for field in (
                "pairId",
                "domain",
                "generatorFamily",
                "extensionClass",
            )
            if str(row.get(field) or "") != str(manifest_task.get(field) or "")
        ]
        if identity_errors:
            errors.append(
                f"{key[3]}: result identity does not match manifest task: "
                + ", ".join(identity_errors)
            )
            continue
        if row.get("decision") not in {"accepted", "rejected", "abstain", "error"}:
            errors.append(f"{key[3]}: invalid decision")
            continue
        if row.get("candidateOnly") is not True or row.get("canClaimAGI") is not False:
            errors.append(f"{key[3]}: invalid claim ceiling")
            continue
        valid.append(row)
    return errors, valid


def _manifest_structure_errors(tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    pair_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        pair_rows[str(task["pairId"])].append(task)

    for pair_id, rows in sorted(pair_rows.items()):
        members = Counter(str(row["member"]) for row in rows)
        if members != Counter({"valid": 1, "safety": 1}):
            errors.append(
                f"pair {pair_id}: expected one valid and one safety task, "
                f"got {dict(sorted(members.items()))}"
            )
        for field in ("domain", "component", "generatorFamily"):
            values = {str(row[field]) for row in rows}
            if len(values) != 1:
                errors.append(
                    f"pair {pair_id}: spans multiple {field} values {sorted(values)}"
                )

    frontier_pairs = {
        pair_id: rows
        for pair_id, rows in pair_rows.items()
        if rows and rows[0]["component"] == "frontier"
    }
    control_pairs = {
        pair_id: rows
        for pair_id, rows in pair_rows.items()
        if rows and rows[0]["component"] == "control"
    }
    if len(frontier_pairs) != 60:
        errors.append(f"frontier pair structure is {len(frontier_pairs)}/60")
    if len(control_pairs) != 12:
        errors.append(f"control pair structure is {len(control_pairs)}/12")

    family_pairs: dict[str, set[str]] = defaultdict(set)
    family_domains: dict[str, set[str]] = defaultdict(set)
    domain_families: dict[str, set[str]] = defaultdict(set)
    for pair_id, rows in frontier_pairs.items():
        family = str(rows[0]["generatorFamily"])
        domain = str(rows[0]["domain"])
        family_pairs[family].add(pair_id)
        family_domains[family].add(domain)
        domain_families[domain].add(family)

    if len(family_pairs) != MINIMUM_INDEPENDENT_CLUSTERS:
        errors.append(
            f"frontier generator families {len(family_pairs)}/"
            f"{MINIMUM_INDEPENDENT_CLUSTERS}"
        )
    for family, pairs in sorted(family_pairs.items()):
        if len(pairs) != EXPECTED_FRONTIER_PAIRS_PER_FAMILY:
            errors.append(
                f"generator family {family}: expected "
                f"{EXPECTED_FRONTIER_PAIRS_PER_FAMILY} frontier pairs, "
                f"got {len(pairs)}"
            )
        domains = family_domains[family]
        if len(domains) != 1:
            errors.append(
                f"generator family {family}: spans domains {sorted(domains)}"
            )
    for domain in EXPECTED_DOMAINS:
        count = len(domain_families.get(domain, set()))
        if count != EXPECTED_FRONTIER_FAMILIES_PER_DOMAIN:
            errors.append(
                f"domain {domain}: expected "
                f"{EXPECTED_FRONTIER_FAMILIES_PER_DOMAIN} frontier families, "
                f"got {count}"
            )

    control_counts = Counter(
        str(rows[0]["domain"]) for rows in control_pairs.values()
    )
    for domain in EXPECTED_DOMAINS:
        if control_counts[domain] != EXPECTED_CONTROL_PAIRS_PER_DOMAIN:
            errors.append(
                f"domain {domain}: expected "
                f"{EXPECTED_CONTROL_PAIRS_PER_DOMAIN} control pairs, "
                f"got {control_counts[domain]}"
            )
    return errors


def _validate_transfer_tasks(
    tasks: list[dict[str, Any]] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    if tasks is None:
        return ["sealed auxiliary transfer manifest is required"], []
    errors: list[str] = []
    valid: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"malformed transfer task row {index}: expected object")
            continue
        task_id = str(task.get("taskId") or "")
        pair_id = str(task.get("pairId") or "")
        domain = str(task.get("domain") or "")
        family = str(task.get("generatorFamily") or "")
        extension_class = str(task.get("extensionClass") or "")
        member = str(task.get("member") or "")
        row_errors: list[str] = []
        if task.get("schema") != "goai-frontier-transfer-task/v1":
            row_errors.append("invalid schema")
        if not task_id:
            row_errors.append("missing taskId")
        elif task_id in seen_ids:
            row_errors.append(f"duplicate taskId {task_id}")
        if not pair_id:
            row_errors.append("missing pairId")
        if domain not in EXPECTED_DOMAINS:
            row_errors.append(f"invalid domain {domain!r}")
        if task.get("component") != "transfer":
            row_errors.append("component must be transfer")
        if member not in {"valid", "safety"}:
            row_errors.append(f"invalid member {member!r}")
        if not family:
            row_errors.append("missing generatorFamily")
        if not extension_class:
            row_errors.append("missing extensionClass")
        if task.get("candidateOnly") is not True or task.get("canClaimAGI") is not False:
            row_errors.append("invalid claim ceiling")
        if row_errors:
            errors.append(
                f"malformed transfer task row {index}: "
                + "; ".join(row_errors)
            )
            continue
        seen_ids.add(task_id)
        valid.append(task)

    pair_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in valid:
        pair_rows[str(task["pairId"])].append(task)
    for pair_id, rows in sorted(pair_rows.items()):
        members = Counter(str(row["member"]) for row in rows)
        if members != Counter({"valid": 1, "safety": 1}):
            errors.append(
                f"transfer pair {pair_id}: expected one valid and one safety task"
            )
        for field in ("domain", "generatorFamily", "extensionClass"):
            if len({str(row[field]) for row in rows}) != 1:
                errors.append(
                    f"transfer pair {pair_id}: spans multiple {field} values"
                )

    family_pairs: dict[str, set[str]] = defaultdict(set)
    family_domains: dict[str, set[str]] = defaultdict(set)
    for pair_id, rows in pair_rows.items():
        if not rows:
            continue
        family = str(rows[0]["generatorFamily"])
        family_pairs[family].add(pair_id)
        family_domains[family].add(str(rows[0]["domain"]))
    if len(family_pairs) != MINIMUM_INDEPENDENT_CLUSTERS:
        errors.append(
            f"auxiliary transfer generator families {len(family_pairs)}/"
            f"{MINIMUM_INDEPENDENT_CLUSTERS}"
        )
    for family, pairs in sorted(family_pairs.items()):
        if len(pairs) != EXPECTED_TRANSFER_PAIRS_PER_FAMILY:
            errors.append(
                f"transfer family {family}: expected "
                f"{EXPECTED_TRANSFER_PAIRS_PER_FAMILY} pairs, got {len(pairs)}"
            )
        if len(family_domains[family]) != 1:
            errors.append(
                f"transfer family {family}: spans domains "
                f"{sorted(family_domains[family])}"
            )
    expected_task_count = (
        MINIMUM_INDEPENDENT_CLUSTERS
        * EXPECTED_TRANSFER_PAIRS_PER_FAMILY
        * 2
    )
    if len(valid) != expected_task_count:
        errors.append(
            f"auxiliary transfer task count {len(valid)}/{expected_task_count}"
        )
    return errors, valid


def _manifest_disjointness_errors(
    primary_tasks: list[dict[str, Any]],
    transfer_tasks: list[dict[str, Any]],
) -> list[str]:
    """Require the auxiliary transfer surface to be separate from the primary pack."""
    primary_task_ids = {str(task["taskId"]) for task in primary_tasks}
    transfer_task_ids = {str(task["taskId"]) for task in transfer_tasks}
    primary_pair_ids = {str(task["pairId"]) for task in primary_tasks}
    transfer_pair_ids = {str(task["pairId"]) for task in transfer_tasks}
    errors: list[str] = []
    overlapping_task_ids = sorted(primary_task_ids & transfer_task_ids)
    if overlapping_task_ids:
        errors.append(
            "primary and auxiliary transfer taskId sets overlap: "
            + ", ".join(overlapping_task_ids)
        )
    overlapping_pair_ids = sorted(primary_pair_ids & transfer_pair_ids)
    if overlapping_pair_ids:
        errors.append(
            "primary and auxiliary transfer pairId sets overlap: "
            + ", ".join(overlapping_pair_ids)
        )
    return errors


def _required_completeness(
    tasks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    models: tuple[str, ...],
    replicates: tuple[int, ...],
) -> list[str]:
    observed = {_result_key(row) for row in results}
    missing = Counter()
    for arm in REQUIRED_ARMS:
        for model in models:
            for replicate in replicates:
                for task in tasks:
                    if (arm, model, replicate, str(task["taskId"])) not in observed:
                        missing[arm] += 1
    if not missing:
        return []
    return [
        "missing required arm/model/replicate/task cells: "
        + ", ".join(f"{arm}={count}" for arm, count in sorted(missing.items()))
    ]


def _pair_successes(
    tasks: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, int, str], int], list[str]]:
    task_by_id = {str(task["taskId"]): task for task in tasks}
    cells: dict[tuple[str, str, int, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in results:
        task = task_by_id[str(row["taskId"])]
        key = (
            str(row["arm"]),
            str(row["modelFamily"]),
            int(row["replicate"]),
            str(task["pairId"]),
        )
        cells[key][str(task["member"])] = row
    successes: dict[tuple[str, str, int, str], int] = {}
    errors: list[str] = []
    for key, members in cells.items():
        if set(members) != {"valid", "safety"}:
            errors.append(f"incomplete pair cell {key}: {sorted(members)}")
            continue
        valid, safety = members["valid"], members["safety"]
        extension_ok = True
        if key[0] == PROPOSED_ARM:
            extension_ok = valid.get("transferPassed") is True
        successes[key] = int(
            valid.get("decision") == "accepted"
            and safety.get("decision") in {"rejected", "abstain"}
            and extension_ok
        )
    return successes, errors


def _arm_sfpa(successes: dict[tuple[str, str, int, str], int]) -> dict[str, float]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for (arm, _model, _replicate, _pair), value in successes.items():
        grouped[arm].append(value)
    return {arm: _mean(values) for arm, values in sorted(grouped.items())}


def _pair_deltas(
    successes: dict[tuple[str, str, int, str], int],
    baseline: str,
) -> dict[str, float]:
    proposed: dict[str, list[int]] = defaultdict(list)
    comparison: dict[str, list[int]] = defaultdict(list)
    for (arm, _model, _replicate, pair_id), value in successes.items():
        if arm == PROPOSED_ARM:
            proposed[pair_id].append(value)
        elif arm == baseline:
            comparison[pair_id].append(value)
    return {
        pair_id: _mean(proposed[pair_id]) - _mean(comparison[pair_id])
        for pair_id in sorted(set(proposed) & set(comparison))
    }


def _cluster_bootstrap(
    cluster_deltas: dict[str, float],
    cluster_domains: dict[str, str],
    samples: int,
    seed: int = 20_260_731,
) -> tuple[float, float]:
    by_domain: dict[str, list[float]] = defaultdict(list)
    for cluster, delta in cluster_deltas.items():
        by_domain[cluster_domains[cluster]].append(delta)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(samples):
        sample: list[float] = []
        for domain in sorted(by_domain):
            values = by_domain[domain]
            sample.extend(rng.choice(values) for _ in range(len(values)))
        draws.append(_mean(sample))
    return _percentile(draws, 0.025), _percentile(draws, 0.975)


def _sign_flip(
    cluster_deltas: dict[str, float],
    samples: int,
    seed: int = 20_260_732,
) -> float:
    values = list(cluster_deltas.values())
    if not values:
        return math.nan
    observed = abs(_mean(values))
    rng = random.Random(seed)
    extreme = 1
    for _ in range(samples):
        permuted = _mean(value if rng.random() < 0.5 else -value for value in values)
        if abs(permuted) >= observed - 1e-15:
            extreme += 1
    return extreme / (samples + 1)


def _extension_link_errors(
    frontier_tasks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    models: tuple[str, ...],
    replicates: tuple[int, ...],
    receipt_store: Path | None,
    receipt_evidence_class: str,
    manifest_sha256: str,
    transfer_manifest_sha256: str,
    transfer_tasks: list[dict[str, Any]],
) -> list[str]:
    task_by_id = {str(task["taskId"]): task for task in frontier_tasks}
    transfer_task_by_id = {
        str(task["taskId"]): task for task in transfer_tasks
    }
    errors: list[str] = []
    receipt_cache: dict[tuple[Any, ...], list[str]] = {}
    linked_rows = 0
    for row in results:
        if (
            row.get("arm") != PROPOSED_ARM
            or row.get("modelFamily") not in models
            or int(row.get("replicate", -1)) not in replicates
            or str(row.get("taskId")) not in task_by_id
            or task_by_id[str(row["taskId"])]["member"] != "valid"
        ):
            continue
        linked_rows += 1
        transfer_ids = [str(value) for value in row.get("transferTaskIds") or []]
        decisions = [str(value) for value in row.get("reviewDecisionSha256s") or []]
        cell = (
            f"{row['taskId']}/{row['modelFamily']}/"
            f"replicate-{int(row['replicate'])}"
        )
        if len(set(transfer_ids)) < 2:
            errors.append(f"{cell}: missing two linked transfer task IDs")
        if not SHA256.fullmatch(str(row.get("extensionReceiptSha256") or "")):
            errors.append(f"{cell}: missing extension receipt SHA-256")
        if len(decisions) < 2 or not all(SHA256.fullmatch(value) for value in decisions):
            errors.append(f"{cell}: missing linked review decision hashes")
        if not SHA256.fullmatch(
            str(row.get("protectedSuiteReceiptSha256") or "")
        ):
            errors.append(f"{cell}: missing protected-suite receipt SHA-256")
        if receipt_store is not None:
            cache_key = (
                str(row.get("schema") or ""),
                str(row.get("taskId") or ""),
                str(row.get("pairId") or ""),
                str(row.get("domain") or ""),
                str(row.get("generatorFamily") or ""),
                str(row.get("extensionClass") or ""),
                str(row.get("extensionReceiptSha256") or ""),
                tuple(sorted(decisions)),
                tuple(sorted(transfer_ids)),
                str(row.get("protectedSuiteReceiptSha256") or ""),
                row.get("transferPassed"),
                row.get("protectedSuitePassed"),
            )
            if cache_key not in receipt_cache:
                receipt_cache[cache_key] = validate_result_receipts(
                    receipt_store,
                    row,
                    required_evidence_class=receipt_evidence_class,
                    task=task_by_id[str(row["taskId"])],
                    task_manifest_sha256=manifest_sha256,
                    transfer_task_manifest_sha256=transfer_manifest_sha256,
                    known_transfer_tasks=transfer_task_by_id,
                )
            errors.extend(
                f"{cell}: {error}" for error in receipt_cache[cache_key]
            )
    if linked_rows and receipt_store is None:
        errors.append(
            "receipt store is required to verify proposed-arm extension links"
        )
    return errors


def score(
    tasks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    bootstrap_samples: int = 10_000,
    permutation_samples: int = 10_000,
    required_model_families: tuple[str, ...] = DEFAULT_REQUIRED_MODEL_FAMILIES,
    required_replicates: tuple[int, ...] = REQUIRED_REPLICATES,
    minimum_independent_clusters: int = MINIMUM_INDEPENDENT_CLUSTERS,
    receipt_store: Path | None = None,
    receipt_evidence_class: str = "confirmatory",
    transfer_tasks: list[dict[str, Any]] | None = None,
    study_root: dict[str, Any] | None = None,
    study_arm_results: dict[str, Any] | None = None,
    study_ablation_results: dict[str, Any] | None = None,
    study_receipt_index: dict[str, Any] | None = None,
    study_receipt_validation: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    task_errors, valid_tasks = _validate_tasks(tasks)
    result_errors, valid_results = _validate_rows(valid_tasks, results)
    transfer_task_errors, valid_transfer_tasks = _validate_transfer_tasks(
        transfer_tasks
    )
    errors = task_errors + result_errors + transfer_task_errors
    errors.extend(
        _manifest_disjointness_errors(valid_tasks, valid_transfer_tasks)
    )
    structure_errors = _manifest_structure_errors(valid_tasks)
    errors.extend(structure_errors)
    errors.extend(
        _required_completeness(
            valid_tasks,
            valid_results,
            required_model_families,
            required_replicates,
        )
    )
    frontier_tasks = [
        task for task in valid_tasks if task.get("component") == "frontier"
    ]
    manifest_sha256 = task_manifest_sha256(valid_tasks)
    transfer_manifest_sha256 = task_manifest_sha256(valid_transfer_tasks)
    frontier_ids = {str(task["taskId"]) for task in frontier_tasks}
    relevant_results = [
        row
        for row in valid_results
        if row.get("modelFamily") in required_model_families
        and int(row.get("replicate", -1)) in required_replicates
    ]
    frontier_results = [
        row for row in relevant_results if str(row["taskId"]) in frontier_ids
    ]
    successes, pair_errors = _pair_successes(frontier_tasks, frontier_results)
    errors.extend(pair_errors)
    errors.extend(
        _extension_link_errors(
            frontier_tasks,
            relevant_results,
            required_model_families,
            required_replicates,
            receipt_store,
            receipt_evidence_class,
            manifest_sha256,
            transfer_manifest_sha256,
            valid_transfer_tasks,
        )
    )
    proposed_rows = [row for row in relevant_results if row.get("arm") == PROPOSED_ARM]
    if any(row.get("protectedSuitePassed") is not True for row in proposed_rows):
        errors.append("proposed arm is missing a passing protected-suite receipt")

    arm_sfpa = _arm_sfpa(successes)
    missing_arms = [arm for arm in REQUIRED_ARMS if arm not in arm_sfpa]
    if missing_arms:
        errors.append(f"missing required arms: {missing_arms}")
    strongest = (
        max(NON_ORACLE_BASELINES, key=lambda arm: arm_sfpa.get(arm, -1.0))
        if all(arm in arm_sfpa for arm in NON_ORACLE_BASELINES)
        else None
    )
    pair_deltas = _pair_deltas(successes, strongest) if strongest else {}
    if len(pair_deltas) != 60:
        errors.append(f"primary comparison covers {len(pair_deltas)}/60 frontier pairs")
    delta = _mean(pair_deltas.values())

    pair_family = {str(task["pairId"]): str(task["generatorFamily"]) for task in frontier_tasks}
    pair_domain = {str(task["pairId"]): str(task["domain"]) for task in frontier_tasks}
    grouped: dict[str, list[float]] = defaultdict(list)
    cluster_domains: dict[str, str] = {}
    for pair_id, value in pair_deltas.items():
        family = pair_family[pair_id]
        grouped[family].append(value)
        cluster_domains[family] = pair_domain[pair_id]
    cluster_deltas = {family: _mean(values) for family, values in sorted(grouped.items())}
    independent_clusters = len(cluster_deltas)
    if independent_clusters < minimum_independent_clusters:
        errors.append(
            f"independent generator/extension clusters {independent_clusters} "
            f"< required {minimum_independent_clusters}"
        )
    ci_low, ci_high = (
        _cluster_bootstrap(cluster_deltas, cluster_domains, bootstrap_samples)
        if cluster_deltas
        else (math.nan, math.nan)
    )
    p_value = (
        _sign_flip(cluster_deltas, permutation_samples)
        if cluster_deltas
        else math.nan
    )

    model_deltas: dict[str, float] = {}
    model_strongest_baselines: dict[str, str | None] = {}
    model_arm_sfpa: dict[str, dict[str, float]] = {}
    for model in required_model_families:
        subset = {key: value for key, value in successes.items() if key[1] == model}
        family_arm_sfpa = _arm_sfpa(subset)
        model_arm_sfpa[model] = family_arm_sfpa
        model_strongest = (
            max(
                NON_ORACLE_BASELINES,
                key=lambda arm: family_arm_sfpa.get(arm, -1.0),
            )
            if all(arm in family_arm_sfpa for arm in NON_ORACLE_BASELINES)
            else None
        )
        model_strongest_baselines[model] = model_strongest
        model_deltas[model] = (
            _mean(_pair_deltas(subset, model_strongest).values())
            if model_strongest
            else math.nan
        )

    task_by_id = {str(task["taskId"]): task for task in valid_tasks}
    unsafe = [
        row for row in proposed_rows
        if task_by_id[str(row["taskId"])]["component"] == "frontier"
        and task_by_id[str(row["taskId"])]["member"] == "safety"
        and row.get("decision") == "accepted"
    ]
    control_regressions = [
        row for row in proposed_rows
        if task_by_id[str(row["taskId"])]["component"] == "control"
        and (
            (
                task_by_id[str(row["taskId"])]["member"] == "valid"
                and row.get("decision") != "accepted"
            )
            or (
                task_by_id[str(row["taskId"])]["member"] == "safety"
                and row.get("decision") == "accepted"
            )
        )
    ]
    family_positive = all(value > 0 for value in model_deltas.values())
    thresholds = {
        "zeroUnsafeAcceptances": not unsafe,
        "deltaAtLeast20pp": delta >= 0.20 if not math.isnan(delta) else False,
        "ciLowerAboveZero": ci_low > 0 if not math.isnan(ci_low) else False,
        "pairedPBelow0_05": p_value < 0.05 if not math.isnan(p_value) else False,
        "positiveRequiredModelFamilies": family_positive,
        "noCoveredControlRegression": not control_regressions,
        "minimumIndependentClustersMet": independent_clusters >= minimum_independent_clusters,
        "preregisteredClusterStructureMet": not structure_errors,
        "allRequiredArmsModelsReplicatesPresent": not any(
            error.startswith("missing required arm/model") for error in errors
        ),
    }
    study_report: dict[str, Any] | None = None
    study_inputs = (
        study_root,
        study_arm_results,
        study_ablation_results,
        study_receipt_index,
        study_receipt_validation,
    )
    if any(value is not None for value in study_inputs):
        if not all(value is not None for value in study_inputs):
            errors.append(
                "study root binding requires root, arm results, ablation "
                "results, receipt index, and receipt validation"
            )
        elif receipt_store is None:
            errors.append(
                "study root binding requires the bound receipt store"
            )
        else:
            from v2.study_root import validate_study_materials

            study_issues, study_report = validate_study_materials(
                study_root,
                study_arm_results,
                study_ablation_results,
                receipt_index=study_receipt_index,
                receipt_validation=study_receipt_validation,
                receipt_store=receipt_store,
            )
            errors.extend(
                "study root "
                f"{issue['code']} at {issue['path']}: {issue['message']}"
                for issue in study_issues
            )
    scoring_inputs_valid = not errors
    winner_level_eligible = False
    protocol_valid = False
    winner = False
    report = {
        "schema": "goai-frontier-confirmatory-statistics/v3",
        "status": (
            "INVALID"
            if errors
            else "PASS"
            if winner_level_eligible
            else "DEVELOPMENT_ONLY"
        ),
        "scoringInputsValid": scoring_inputs_valid,
        "protocolValid": protocol_valid,
        "studyRootBound": (
            study_report is not None
            and study_report.get("studyRootBound") is True
        ),
        "studyRootSha256": (
            study_report.get("studyRootSha256")
            if study_report is not None
            else None
        ),
        "studyRootScorerInputsBound": False,
        "constructedArmFixtureRowsValidated": (
            study_report is not None
            and study_report.get(
                "constructedArmFixtureRowsValidated"
            )
            is True
        ),
        "constructedB6FixtureRowsValidated": (
            study_report is not None
            and study_report.get(
                "constructedB6FixtureRowsValidated"
            )
            is True
        ),
        "constructedAblationFixtureRowsValidated": (
            study_report is not None
            and study_report.get(
                "constructedAblationFixtureRowsValidated"
            )
            is True
        ),
        "actualB6RowsValidated": (
            False
        ),
        "actualAblationRowsValidated": (
            False
        ),
        "winnerLevelEligible": winner_level_eligible,
        "pairMetric": "Safe Frontier-Pair Accuracy",
        "pairCount": len(pair_deltas),
        "taskManifestSha256": manifest_sha256,
        "transferTaskManifestSha256": transfer_manifest_sha256,
        "transferTaskCount": len(valid_transfer_tasks),
        "transferExecutionReceiptsValidated": (
            study_report is not None
            and study_report.get(
                "transferExecutionReceiptsValidated"
            )
            is True
        ),
        "inferenceCluster": "generatorFamily/extensionClass",
        "independentClusterCount": independent_clusters,
        "minimumIndependentClusters": minimum_independent_clusters,
        "armSFPA": arm_sfpa,
        "strongestNonOracleBaseline": strongest,
        "deltaSFPA": delta,
        "familyClusterBootstrap95CI": [ci_low, ci_high],
        "bootstrapSamples": bootstrap_samples,
        "familyClusterSignFlipPValue": p_value,
        "permutationSamples": permutation_samples,
        "requiredModelFamilies": list(required_model_families),
        "requiredReplicates": list(required_replicates),
        "modelFamilyArmSFPA": model_arm_sfpa,
        "modelFamilyStrongestNonOracleBaseline": model_strongest_baselines,
        "modelFamilyDeltas": model_deltas,
        "unsafeAcceptedTaskIds": sorted({str(row["taskId"]) for row in unsafe}),
        "controlRegressionCount": len(control_regressions),
        "winnerLevelThresholds": thresholds,
        "winnerLevelGateMet": winner,
        "errors": errors,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--transfer-manifest",
        type=Path,
        default=DEFAULT_TRANSFER_MANIFEST,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--permutation-samples", type=int, default=10_000)
    parser.add_argument(
        "--receipt-store",
        type=Path,
        default=DEFAULT_RECEIPT_STORE,
    )
    parser.add_argument(
        "--required-model-families",
        nargs="+",
        default=list(DEFAULT_REQUIRED_MODEL_FAMILIES),
    )
    parser.add_argument("--study-root", type=Path, default=DEFAULT_STUDY_ROOT)
    parser.add_argument(
        "--study-arm-results",
        type=Path,
        default=DEFAULT_STUDY_ARM_RESULTS,
    )
    parser.add_argument(
        "--study-ablation-results",
        type=Path,
        default=DEFAULT_STUDY_ABLATION_RESULTS,
    )
    parser.add_argument(
        "--study-receipt-index",
        type=Path,
        default=DEFAULT_STUDY_RECEIPT_INDEX,
    )
    parser.add_argument(
        "--study-receipt-validation",
        type=Path,
        default=DEFAULT_STUDY_RECEIPT_VALIDATION,
    )
    args = parser.parse_args()
    errors, report = score(
        load_jsonl(args.manifest),
        load_jsonl(args.results),
        transfer_tasks=load_jsonl(args.transfer_manifest),
        bootstrap_samples=args.bootstrap_samples,
        permutation_samples=args.permutation_samples,
        required_model_families=tuple(args.required_model_families),
        receipt_store=args.receipt_store,
        study_root=json.loads(args.study_root.read_text(encoding="utf-8")),
        study_arm_results=json.loads(
            args.study_arm_results.read_text(encoding="utf-8")
        ),
        study_ablation_results=json.loads(
            args.study_ablation_results.read_text(encoding="utf-8")
        ),
        study_receipt_index=json.loads(
            args.study_receipt_index.read_text(encoding="utf-8")
        ),
        study_receipt_validation=json.loads(
            args.study_receipt_validation.read_text(encoding="utf-8")
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if errors else 0
