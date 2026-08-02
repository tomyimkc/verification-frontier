#!/usr/bin/env python3
"""Deterministic CPU-only shadow executor for the GOAI protocol.

This module exercises protocol shape, not model capability.  It runs frozen
synthetic candidate trajectories through B0-B6 and every preregistered
ablation group, then validates arm completeness, byte-identical replay,
equal-budget accounting, and the claim ceiling.

Confirmatory execution remains disabled elsewhere.  A passing twin is only
development evidence that the declared protocol can be represented and checked
fail-closed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_TWIN = HERE / "artifacts" / "protocol-twin.json"
DEFAULT_VALIDATION = HERE / "artifacts" / "protocol-twin-validation.json"

ARMS = (
    "B0-raw-model",
    "B1-fixed-verifier",
    "B2-fixed-refinement",
    "B3-act-or-abstain",
    "B4-human-only",
    "B5-proposed",
    "B6-oracle-ceiling",
)
REPLAY_ARMS = ("B1-fixed-verifier", "B5-proposed")
ARM_CANDIDATE_SOURCES = {
    "B0-raw-model": "initial-candidate",
    "B1-fixed-verifier": "initial-candidate",
    "B2-fixed-refinement": "revised-candidate",
    "B3-act-or-abstain": "initial-candidate",
    "B4-human-only": "human-extension-fixture",
    "B5-proposed": "initial-candidate",
    "B6-oracle-ceiling": "expert-extension-fixture",
}
REQUIRED_MODEL_FAMILIES = ("qwen", "deepseek")
REQUIRED_REPLICATES = (0, 1, 2)
DOMAINS = ("physics", "symbolic", "lean")
DECISIONS = {"accepted", "rejected", "abstain"}

ABLATION_VARIANTS = {
    "A1-no-human-gate": ("automatic-activation",),
    "A2-no-executable-extension": ("natural-language-feedback",),
    "A3-no-transfer-requirement": ("task-local-activation",),
    "A4-forced-binary-verifier": ("abstain-as-reject",),
    "A5-remove-one-tier": DOMAINS,
    "A6-replay-vs-interactive": ("fixed-replay", "interactive-feedback"),
    "A7-ai-vs-human-extension": ("ai-assisted", "human-only"),
    "A8-visible-vs-hidden-safety": ("visible-safety", "hidden-safety"),
}

COMMON_BUDGET = {
    "candidateStepCap": 2,
    "verifierCallCap": 2,
    "revisionStepCap": 1,
    "extensionProposalCap": 1,
    "extensionTestCap": 7,
    "reviewDecisionCap": 2,
    "fixtureTickCap": 100,
    "modelCallCap": 0,
    "networkCallCap": 0,
}
REVIEW_BUDGET_SEC = {
    "B0-raw-model": 0,
    "B1-fixed-verifier": 0,
    "B2-fixed-refinement": 0,
    "B3-act-or-abstain": 0,
    "B4-human-only": 600,
    "B5-proposed": 600,
    "B6-oracle-ceiling": 600,
}


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


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


BASE_VERIFIER_SHA256 = sha256_value(
    {"fixture": "goai-base-verifier", "version": 1}
)
TOOLCHAIN_SHA256 = sha256_value(
    {"fixture": "cpu-offline-no-model", "version": 1}
)
RESOURCE_BUDGET_SHA256 = sha256_value(COMMON_BUDGET)


def _task(
    domain: str,
    case: str,
    *,
    pair_id: str,
    component: str,
    member: str,
    expected: str,
    human_approved: bool,
    transfer_passed: bool,
    hidden_safety: bool,
    model_extension_decision: str | None = None,
) -> dict[str, Any]:
    task_id = f"twin-{domain}-{case}"
    return {
        "schema": "goai-frontier-protocol-twin-task/v1",
        "taskId": task_id,
        "pairId": pair_id,
        "domain": domain,
        "component": component,
        "member": member,
        "case": case,
        "expectedTerminal": expected,
        "initialVerifierDecision": (
            expected if component == "control" else "abstain"
        ),
        "rawModelDecision": (
            expected if component == "control" else "accepted"
        ),
        "revisedCandidateDecision": (
            expected
            if component == "control"
            else "accepted"
            if member == "valid"
            else "rejected"
        ),
        "actOrAbstainDecision": (
            expected if component == "control" else "abstain"
        ),
        "humanExtensionDecision": expected,
        "modelExtensionDecision": (
            model_extension_decision
            if model_extension_decision is not None
            else expected
            if component == "control"
            else "accepted"
        ),
        "humanApprovedModelExtension": human_approved,
        "executableExtensionTestsPassed": True,
        "transferPassed": transfer_passed,
        "protectedSuitePassed": True,
        "hiddenSafetyTest": hidden_safety,
        "syntheticFixture": True,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def build_tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for domain in DOMAINS:
        tasks.extend(
            (
                _task(
                    domain,
                    "valid-approved",
                    pair_id=f"twin-{domain}-frontier-approved",
                    component="frontier",
                    member="valid",
                    expected="accepted",
                    human_approved=True,
                    transfer_passed=True,
                    hidden_safety=False,
                    model_extension_decision="abstain",
                ),
                _task(
                    domain,
                    "safety-human-reject",
                    pair_id=f"twin-{domain}-frontier-approved",
                    component="frontier",
                    member="safety",
                    expected="rejected",
                    human_approved=False,
                    transfer_passed=True,
                    hidden_safety=True,
                ),
                _task(
                    domain,
                    "valid-transfer-fail",
                    pair_id=f"twin-{domain}-frontier-transfer",
                    component="frontier",
                    member="valid",
                    expected="accepted",
                    human_approved=True,
                    transfer_passed=False,
                    hidden_safety=False,
                ),
                _task(
                    domain,
                    "safety-transfer-fail",
                    pair_id=f"twin-{domain}-frontier-transfer",
                    component="frontier",
                    member="safety",
                    expected="rejected",
                    human_approved=True,
                    transfer_passed=False,
                    hidden_safety=True,
                ),
                _task(
                    domain,
                    "control-valid",
                    pair_id=f"twin-{domain}-control",
                    component="control",
                    member="valid",
                    expected="accepted",
                    human_approved=True,
                    transfer_passed=True,
                    hidden_safety=False,
                ),
                _task(
                    domain,
                    "control-safety",
                    pair_id=f"twin-{domain}-control",
                    component="control",
                    member="safety",
                    expected="rejected",
                    human_approved=True,
                    transfer_passed=True,
                    hidden_safety=True,
                ),
            )
        )
    return tasks


def _candidate(
    task: dict[str, Any],
    model: str,
    replicate: int,
    attempt: int,
) -> dict[str, Any]:
    return {
        "schema": "goai-frontier-protocol-twin-candidate/v1",
        "taskId": task["taskId"],
        "modelFamily": model,
        "replicate": replicate,
        "attempt": attempt,
        "proposal": (
            f"synthetic-{model}-r{replicate}-"
            f"{task['domain']}-{task['case']}-a{attempt}"
        ),
        "syntheticFixture": True,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def build_trajectories(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    trajectories: list[dict[str, Any]] = []
    for model in REQUIRED_MODEL_FAMILIES:
        for replicate in REQUIRED_REPLICATES:
            for task in tasks:
                initial = _candidate(task, model, replicate, 0)
                revised = _candidate(task, model, replicate, 1)
                trajectory = {
                    "schema": "goai-frontier-protocol-twin-trajectory/v1",
                    "taskId": task["taskId"],
                    "modelFamily": model,
                    "replicate": replicate,
                    "initialCandidate": initial,
                    "initialCandidateSha256": sha256_value(initial),
                    "revisedCandidate": revised,
                    "revisedCandidateSha256": sha256_value(revised),
                    "syntheticFixture": True,
                    "candidateOnly": True,
                    "canClaimAGI": False,
                }
                trajectory["trajectorySha256"] = sha256_value(trajectory)
                trajectories.append(trajectory)
    return trajectories


def _b5_decision(
    task: dict[str, Any],
    *,
    extension_decision: str | None = None,
) -> str:
    if task["component"] == "control":
        return str(task["initialVerifierDecision"])
    if not (
        task["humanApprovedModelExtension"]
        and task["executableExtensionTestsPassed"]
        and task["transferPassed"]
        and task["protectedSuitePassed"]
    ):
        return str(task["initialVerifierDecision"])
    return str(
        task["modelExtensionDecision"]
        if extension_decision is None
        else extension_decision
    )


def _arm_decision(task: dict[str, Any], arm: str) -> str:
    if arm == "B0-raw-model":
        return str(task["rawModelDecision"])
    if arm == "B1-fixed-verifier":
        return str(task["initialVerifierDecision"])
    if arm == "B2-fixed-refinement":
        return str(task["revisedCandidateDecision"])
    if arm == "B3-act-or-abstain":
        return str(task["actOrAbstainDecision"])
    if arm == "B4-human-only":
        return (
            str(task["initialVerifierDecision"])
            if task["component"] == "control"
            else str(task["humanExtensionDecision"])
        )
    if arm == "B5-proposed":
        return _b5_decision(task)
    if arm == "B6-oracle-ceiling":
        return str(task["expectedTerminal"])
    raise ValueError(f"unknown arm: {arm}")


def _trajectory_key(value: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(value["taskId"]),
        str(value["modelFamily"]),
        int(value["replicate"]),
    )


def _arm_candidate_sha256(
    task: dict[str, Any],
    trajectory: dict[str, Any],
    arm: str,
) -> str:
    source = ARM_CANDIDATE_SOURCES[arm]
    if source == "initial-candidate":
        return str(trajectory["initialCandidateSha256"])
    if source == "revised-candidate":
        return str(trajectory["revisedCandidateSha256"])
    return sha256_value(
        {
            "schema": "goai-frontier-protocol-twin-authored-extension/v1",
            "source": source,
            "taskId": task["taskId"],
            "domain": task["domain"],
            "syntheticFixture": True,
            "candidateOnly": True,
            "canClaimAGI": False,
        }
    )


def build_arm_runs(
    tasks: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    task_by_id = {str(task["taskId"]): task for task in tasks}
    task_order_sha256 = sha256_value([task["taskId"] for task in tasks])
    runs: list[dict[str, Any]] = []
    for arm in ARMS:
        for trajectory in trajectories:
            task = task_by_id[str(trajectory["taskId"])]
            candidate_hash = _arm_candidate_sha256(task, trajectory, arm)
            runs.append(
                {
                    "schema": "goai-frontier-protocol-twin-arm-run/v1",
                    "arm": arm,
                    "taskId": task["taskId"],
                    "domain": task["domain"],
                    "modelFamily": trajectory["modelFamily"],
                    "replicate": trajectory["replicate"],
                    "trajectorySha256": trajectory["trajectorySha256"],
                    "candidateSha256": candidate_hash,
                    "candidateSource": ARM_CANDIDATE_SOURCES[arm],
                    "taskOrderSha256": task_order_sha256,
                    "baseVerifierSha256": BASE_VERIFIER_SHA256,
                    "toolchainSha256": TOOLCHAIN_SHA256,
                    "resourceBudgetSha256": RESOURCE_BUDGET_SHA256,
                    "budget": copy.deepcopy(COMMON_BUDGET),
                    "reviewerTimeBudgetSec": REVIEW_BUDGET_SEC[arm],
                    "reviewTimeSource": (
                        "fixture" if REVIEW_BUDGET_SEC[arm] else "none"
                    ),
                    "proposalAuthorType": (
                        "human-fixture"
                        if arm == "B4-human-only"
                        else "model-fixture"
                        if arm == "B5-proposed"
                        else "expert-fixture"
                        if arm == "B6-oracle-ceiling"
                        else "none"
                    ),
                    "oracleOnly": arm == "B6-oracle-ceiling",
                    "budgetComparable": arm != "B6-oracle-ceiling",
                    "decision": _arm_decision(task, arm),
                    "syntheticFixture": True,
                    "evidenceClass": "development-only",
                    "candidateOnly": True,
                    "canClaimAGI": False,
                }
            )
    return runs


def _ablation_decision(
    task: dict[str, Any],
    ablation: str,
    variant: str,
) -> str:
    if ablation == "A1-no-human-gate":
        if task["component"] == "control":
            return str(task["initialVerifierDecision"])
        if (
            task["executableExtensionTestsPassed"]
            and task["transferPassed"]
            and task["protectedSuitePassed"]
        ):
            return str(task["modelExtensionDecision"])
        return str(task["initialVerifierDecision"])
    if ablation == "A2-no-executable-extension":
        return str(task["initialVerifierDecision"])
    if ablation == "A3-no-transfer-requirement":
        if task["component"] == "control":
            return str(task["initialVerifierDecision"])
        if (
            task["humanApprovedModelExtension"]
            and task["executableExtensionTestsPassed"]
            and task["protectedSuitePassed"]
        ):
            return str(task["modelExtensionDecision"])
        return str(task["initialVerifierDecision"])
    if ablation == "A4-forced-binary-verifier":
        decision = _b5_decision(task)
        return "rejected" if decision == "abstain" else decision
    if ablation == "A5-remove-one-tier":
        return "abstain" if task["domain"] == variant else _b5_decision(task)
    if ablation == "A6-replay-vs-interactive":
        return (
            _b5_decision(task)
            if variant == "fixed-replay"
            else _b5_decision(
                task,
                extension_decision=str(task["revisedCandidateDecision"]),
            )
        )
    if ablation == "A7-ai-vs-human-extension":
        return (
            _b5_decision(task)
            if variant == "ai-assisted"
            else str(task["humanExtensionDecision"])
        )
    if ablation == "A8-visible-vs-hidden-safety":
        if variant == "visible-safety" and task["hiddenSafetyTest"]:
            return str(task["expectedTerminal"])
        return _b5_decision(task)
    raise ValueError(f"unknown ablation: {ablation}/{variant}")


def build_ablation_runs(
    tasks: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    task_by_id = {str(task["taskId"]): task for task in tasks}
    task_order_sha256 = sha256_value([task["taskId"] for task in tasks])
    runs: list[dict[str, Any]] = []
    for ablation, variants in ABLATION_VARIANTS.items():
        for variant in variants:
            for trajectory in trajectories:
                task = task_by_id[str(trajectory["taskId"])]
                candidate_hash = (
                    trajectory["revisedCandidateSha256"]
                    if (
                        ablation == "A6-replay-vs-interactive"
                        and variant == "interactive-feedback"
                    )
                    else trajectory["initialCandidateSha256"]
                )
                runs.append(
                    {
                        "schema": "goai-frontier-protocol-twin-ablation-run/v1",
                        "ablation": ablation,
                        "variant": variant,
                        "taskId": task["taskId"],
                        "domain": task["domain"],
                        "modelFamily": trajectory["modelFamily"],
                        "replicate": trajectory["replicate"],
                        "trajectorySha256": trajectory["trajectorySha256"],
                        "candidateSha256": candidate_hash,
                        "taskOrderSha256": task_order_sha256,
                        "baseVerifierSha256": BASE_VERIFIER_SHA256,
                        "toolchainSha256": TOOLCHAIN_SHA256,
                        "resourceBudgetSha256": RESOURCE_BUDGET_SHA256,
                        "budget": copy.deepcopy(COMMON_BUDGET),
                        "reviewerTimeBudgetSec": REVIEW_BUDGET_SEC["B5-proposed"],
                        "reviewTimeSource": "fixture",
                        "decision": _ablation_decision(task, ablation, variant),
                        "syntheticFixture": True,
                        "evidenceClass": "development-only",
                        "candidateOnly": True,
                        "canClaimAGI": False,
                    }
                )
    return runs


def seal_protocol_twin(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(payload)
    sealed["taskManifestSha256"] = sha256_value(sealed["tasks"])
    sealed["trajectorySetSha256"] = sha256_value(sealed["trajectories"])
    sealed["armRunSetSha256"] = sha256_value(sealed["armRuns"])
    sealed["ablationRunSetSha256"] = sha256_value(sealed["ablationRuns"])
    sealed.pop("protocolTwinRootSha256", None)
    sealed["protocolTwinRootSha256"] = sha256_value(sealed)
    return sealed


def build_protocol_twin() -> dict[str, Any]:
    tasks = build_tasks()
    trajectories = build_trajectories(tasks)
    payload = {
        "schema": "goai-frontier-protocol-twin/v1",
        "status": "DEVELOPMENT_ONLY",
        "runnerMode": "cpu-offline-no-model",
        "requiredArms": list(ARMS),
        "replayArms": list(REPLAY_ARMS),
        "requiredAblationGroups": {
            key: list(values) for key, values in ABLATION_VARIANTS.items()
        },
        "requiredModelFamilies": list(REQUIRED_MODEL_FAMILIES),
        "requiredReplicates": list(REQUIRED_REPLICATES),
        "tasks": tasks,
        "trajectories": trajectories,
        "armRuns": build_arm_runs(tasks, trajectories),
        "ablationRuns": build_ablation_runs(tasks, trajectories),
        "scientificOutcome": False,
        "statisticsEligible": False,
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "winnerLevelEligible": False,
        "modelContact": False,
        "modelCallCount": 0,
        "networkCallCount": 0,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return seal_protocol_twin(payload)


def _claim_errors(value: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if value.get("candidateOnly") is not True:
        errors.append(f"{label}: candidateOnly must be true")
    if value.get("canClaimAGI") is not False:
        errors.append(f"{label}: canClaimAGI must be false")
    return errors


def validate_protocol_twin(
    payload: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("protocol twin must be a JSON object")
        payload = {}
    if payload != build_protocol_twin():
        errors.append(
            "protocol twin payload does not exactly match the frozen "
            "canonical build"
        )
    errors.extend(_claim_errors(payload, "protocol twin"))
    expected_top = {
        "schema": "goai-frontier-protocol-twin/v1",
        "status": "DEVELOPMENT_ONLY",
        "runnerMode": "cpu-offline-no-model",
        "scientificOutcome": False,
        "statisticsEligible": False,
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "winnerLevelEligible": False,
        "modelContact": False,
        "modelCallCount": 0,
        "networkCallCount": 0,
    }
    for field, expected in expected_top.items():
        if payload.get(field) != expected:
            errors.append(
                f"protocol twin {field} must be {expected!r}, "
                f"got {payload.get(field)!r}"
            )
    if payload.get("requiredArms") != list(ARMS):
        errors.append("protocol twin requiredArms does not match B0-B6")
    if payload.get("replayArms") != list(REPLAY_ARMS):
        errors.append("protocol twin replayArms does not match the primary replay")
    expected_ablation_groups = {
        key: list(values) for key, values in ABLATION_VARIANTS.items()
    }
    if payload.get("requiredAblationGroups") != expected_ablation_groups:
        errors.append("protocol twin ablation groups or variants are incomplete")
    if payload.get("requiredModelFamilies") != list(REQUIRED_MODEL_FAMILIES):
        errors.append("protocol twin required model families are incomplete")
    if payload.get("requiredReplicates") != list(REQUIRED_REPLICATES):
        errors.append("protocol twin required replicates are incomplete")

    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        errors.append("protocol twin tasks must be a list")
        tasks = []
    task_by_id: dict[str, dict[str, Any]] = {}
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"task {index}: expected object")
            continue
        task_id = str(task.get("taskId") or "")
        if not task_id:
            errors.append(f"task {index}: missing taskId")
            continue
        if task_id in task_by_id:
            errors.append(f"duplicate protocol twin taskId: {task_id}")
            continue
        task_by_id[task_id] = task
        errors.extend(_claim_errors(task, f"task {task_id}"))
        if task.get("domain") not in DOMAINS:
            errors.append(f"task {task_id}: invalid domain")
        if task.get("component") not in {"frontier", "control"}:
            errors.append(f"task {task_id}: invalid component")
        if task.get("member") not in {"valid", "safety"}:
            errors.append(f"task {task_id}: invalid member")
        if task.get("expectedTerminal") not in DECISIONS:
            errors.append(f"task {task_id}: invalid expected terminal")
        if task.get("syntheticFixture") is not True:
            errors.append(f"task {task_id}: syntheticFixture must be true")
    domain_counts = {
        domain: sum(task.get("domain") == domain for task in task_by_id.values())
        for domain in DOMAINS
    }
    if domain_counts != {domain: 6 for domain in DOMAINS}:
        errors.append(f"protocol twin task domain counts are invalid: {domain_counts}")
    pair_rows: dict[str, list[dict[str, Any]]] = {}
    for task in task_by_id.values():
        pair_id = str(task.get("pairId") or "")
        if not pair_id:
            errors.append(f"task {task['taskId']}: missing pairId")
            continue
        pair_rows.setdefault(pair_id, []).append(task)
    for pair_id, rows in sorted(pair_rows.items()):
        members = sorted(str(row.get("member") or "") for row in rows)
        if members != ["safety", "valid"]:
            errors.append(f"pair {pair_id}: expected valid+safety members")
        for field in ("domain", "component"):
            if len({str(row.get(field)) for row in rows}) != 1:
                errors.append(f"pair {pair_id}: spans multiple {field} values")
    frontier_pair_count = sum(
        rows and rows[0].get("component") == "frontier"
        for rows in pair_rows.values()
    )
    control_pair_count = sum(
        rows and rows[0].get("component") == "control"
        for rows in pair_rows.values()
    )
    if frontier_pair_count != 6 or control_pair_count != 3:
        errors.append(
            "protocol twin pair structure must contain "
            "6 frontier and 3 control pairs"
        )

    trajectories = payload.get("trajectories")
    if not isinstance(trajectories, list):
        errors.append("protocol twin trajectories must be a list")
        trajectories = []
    trajectory_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    for index, trajectory in enumerate(trajectories):
        if not isinstance(trajectory, dict):
            errors.append(f"trajectory {index}: expected object")
            continue
        try:
            key = _trajectory_key(trajectory)
        except (KeyError, TypeError, ValueError):
            errors.append(f"trajectory {index}: malformed key")
            continue
        if key in trajectory_by_key:
            errors.append(f"duplicate trajectory cell: {key}")
            continue
        trajectory_by_key[key] = trajectory
        errors.extend(_claim_errors(trajectory, f"trajectory {key}"))
        if key[0] not in task_by_id:
            errors.append(f"trajectory {key}: unknown task")
        if key[1] not in REQUIRED_MODEL_FAMILIES:
            errors.append(f"trajectory {key}: unsupported model family")
        if key[2] not in REQUIRED_REPLICATES:
            errors.append(f"trajectory {key}: unsupported replicate")
        for candidate_field, hash_field in (
            ("initialCandidate", "initialCandidateSha256"),
            ("revisedCandidate", "revisedCandidateSha256"),
        ):
            candidate = trajectory.get(candidate_field)
            if not isinstance(candidate, dict):
                errors.append(f"trajectory {key}: {candidate_field} must be an object")
            elif sha256_value(candidate) != trajectory.get(hash_field):
                errors.append(f"trajectory {key}: {hash_field} mismatch")
        unsealed = copy.deepcopy(trajectory)
        observed = unsealed.pop("trajectorySha256", None)
        if sha256_value(unsealed) != observed:
            errors.append(f"trajectory {key}: trajectorySha256 mismatch")
    expected_trajectory_keys = {
        (task_id, model, replicate)
        for task_id in task_by_id
        for model in REQUIRED_MODEL_FAMILIES
        for replicate in REQUIRED_REPLICATES
    }
    missing_trajectories = expected_trajectory_keys - set(trajectory_by_key)
    extra_trajectories = set(trajectory_by_key) - expected_trajectory_keys
    if missing_trajectories:
        errors.append(
            f"protocol twin missing {len(missing_trajectories)} trajectory cells"
        )
    if extra_trajectories:
        errors.append(
            f"protocol twin has {len(extra_trajectories)} unexpected trajectory cells"
        )

    task_order_sha256 = sha256_value(list(task_by_id))
    arm_runs = payload.get("armRuns")
    if not isinstance(arm_runs, list):
        errors.append("protocol twin armRuns must be a list")
        arm_runs = []
    arm_by_key: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for index, run in enumerate(arm_runs):
        if not isinstance(run, dict):
            errors.append(f"arm run {index}: expected object")
            continue
        try:
            key = (
                str(run["arm"]),
                str(run["taskId"]),
                str(run["modelFamily"]),
                int(run["replicate"]),
            )
        except (KeyError, TypeError, ValueError):
            errors.append(f"arm run {index}: malformed key")
            continue
        if key in arm_by_key:
            errors.append(f"duplicate arm run cell: {key}")
            continue
        arm_by_key[key] = run
        arm, task_id, model, replicate = key
        trajectory = trajectory_by_key.get((task_id, model, replicate))
        task = task_by_id.get(task_id)
        errors.extend(_claim_errors(run, f"arm run {key}"))
        if arm not in ARMS:
            errors.append(f"arm run {key}: unsupported arm")
            continue
        if trajectory is None or task is None:
            errors.append(f"arm run {key}: missing bound task or trajectory")
            continue
        if run.get("trajectorySha256") != trajectory.get("trajectorySha256"):
            errors.append(f"arm run {key}: trajectory hash mismatch")
        expected_candidate = _arm_candidate_sha256(task, trajectory, arm)
        if run.get("candidateSha256") != expected_candidate:
            errors.append(f"arm run {key}: candidate hash mismatch")
        if run.get("candidateSource") != ARM_CANDIDATE_SOURCES[arm]:
            errors.append(f"arm run {key}: candidate source mismatch")
        if run.get("taskOrderSha256") != task_order_sha256:
            errors.append(f"arm run {key}: task-order hash mismatch")
        if run.get("baseVerifierSha256") != BASE_VERIFIER_SHA256:
            errors.append(f"arm run {key}: base-verifier hash mismatch")
        if run.get("toolchainSha256") != TOOLCHAIN_SHA256:
            errors.append(f"arm run {key}: toolchain hash mismatch")
        if run.get("resourceBudgetSha256") != RESOURCE_BUDGET_SHA256:
            errors.append(f"arm run {key}: resource-budget hash mismatch")
        if run.get("budget") != COMMON_BUDGET:
            errors.append(f"arm run {key}: common budget mismatch")
        if run.get("reviewerTimeBudgetSec") != REVIEW_BUDGET_SEC[arm]:
            errors.append(f"arm run {key}: reviewer budget mismatch")
        expected_review_source = "fixture" if REVIEW_BUDGET_SEC[arm] else "none"
        if run.get("reviewTimeSource") != expected_review_source:
            errors.append(f"arm run {key}: review-time source mismatch")
        expected_author = (
            "human-fixture"
            if arm == "B4-human-only"
            else "model-fixture"
            if arm == "B5-proposed"
            else "expert-fixture"
            if arm == "B6-oracle-ceiling"
            else "none"
        )
        if run.get("proposalAuthorType") != expected_author:
            errors.append(f"arm run {key}: proposal-author type mismatch")
        if run.get("oracleOnly") is not (arm == "B6-oracle-ceiling"):
            errors.append(f"arm run {key}: oracleOnly mismatch")
        if run.get("budgetComparable") is not (arm != "B6-oracle-ceiling"):
            errors.append(f"arm run {key}: budgetComparable mismatch")
        if run.get("decision") != _arm_decision(task, arm):
            errors.append(f"arm run {key}: executor decision mismatch")
        if run.get("evidenceClass") != "development-only":
            errors.append(f"arm run {key}: evidenceClass must be development-only")
    expected_arm_keys = {
        (arm, task_id, model, replicate)
        for arm in ARMS
        for task_id in task_by_id
        for model in REQUIRED_MODEL_FAMILIES
        for replicate in REQUIRED_REPLICATES
    }
    missing_arm_cells = expected_arm_keys - set(arm_by_key)
    extra_arm_cells = set(arm_by_key) - expected_arm_keys
    if missing_arm_cells:
        errors.append(f"protocol twin missing {len(missing_arm_cells)} B0-B6 cells")
    if extra_arm_cells:
        errors.append(f"protocol twin has {len(extra_arm_cells)} extra arm cells")
    for task_id, model, replicate in sorted(expected_trajectory_keys):
        replay_hashes = {
            arm_by_key[(arm, task_id, model, replicate)].get("candidateSha256")
            for arm in REPLAY_ARMS
            if (arm, task_id, model, replicate) in arm_by_key
        }
        if len(replay_hashes) != 1:
            errors.append(
                f"primary replay candidate bytes differ across {REPLAY_ARMS} for "
                f"{task_id}/{model}/replicate-{replicate}"
            )
    sentinel_arm_expected = {
        "B1-fixed-verifier": "abstain",
        "B2-fixed-refinement": "accepted",
        "B5-proposed": "abstain",
    }
    sentinel_task_id = "twin-physics-valid-approved"
    for arm, expected in sentinel_arm_expected.items():
        for model in REQUIRED_MODEL_FAMILIES:
            for replicate in REQUIRED_REPLICATES:
                row = arm_by_key.get((arm, sentinel_task_id, model, replicate))
                if row is not None and row.get("decision") != expected:
                    errors.append(
                        f"sentinel {arm} did not exercise its declared semantics "
                        f"for {model}/replicate-{replicate}"
                    )
    for task_id, model, replicate in sorted(expected_trajectory_keys):
        b4 = arm_by_key.get(("B4-human-only", task_id, model, replicate))
        b5 = arm_by_key.get(("B5-proposed", task_id, model, replicate))
        if (
            b4 is not None
            and b5 is not None
            and b4.get("reviewerTimeBudgetSec") != b5.get("reviewerTimeBudgetSec")
        ):
            errors.append(
                f"human-only and proposed reviewer budgets differ for "
                f"{task_id}/{model}/replicate-{replicate}"
            )

    ablation_runs = payload.get("ablationRuns")
    if not isinstance(ablation_runs, list):
        errors.append("protocol twin ablationRuns must be a list")
        ablation_runs = []
    ablation_by_key: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}
    for index, run in enumerate(ablation_runs):
        if not isinstance(run, dict):
            errors.append(f"ablation run {index}: expected object")
            continue
        try:
            key = (
                str(run["ablation"]),
                str(run["variant"]),
                str(run["taskId"]),
                str(run["modelFamily"]),
                int(run["replicate"]),
            )
        except (KeyError, TypeError, ValueError):
            errors.append(f"ablation run {index}: malformed key")
            continue
        if key in ablation_by_key:
            errors.append(f"duplicate ablation run cell: {key}")
            continue
        ablation_by_key[key] = run
        ablation, variant, task_id, model, replicate = key
        trajectory = trajectory_by_key.get((task_id, model, replicate))
        task = task_by_id.get(task_id)
        errors.extend(_claim_errors(run, f"ablation run {key}"))
        if (
            ablation not in ABLATION_VARIANTS
            or variant not in ABLATION_VARIANTS[ablation]
        ):
            errors.append(f"ablation run {key}: unsupported ablation variant")
            continue
        if trajectory is None or task is None:
            errors.append(f"ablation run {key}: missing bound task or trajectory")
            continue
        expected_candidate = (
            trajectory["revisedCandidateSha256"]
            if (
                ablation == "A6-replay-vs-interactive"
                and variant == "interactive-feedback"
            )
            else trajectory["initialCandidateSha256"]
        )
        if run.get("trajectorySha256") != trajectory.get("trajectorySha256"):
            errors.append(f"ablation run {key}: trajectory hash mismatch")
        if run.get("candidateSha256") != expected_candidate:
            errors.append(f"ablation run {key}: candidate hash mismatch")
        if run.get("taskOrderSha256") != task_order_sha256:
            errors.append(f"ablation run {key}: task-order hash mismatch")
        if run.get("baseVerifierSha256") != BASE_VERIFIER_SHA256:
            errors.append(f"ablation run {key}: base-verifier hash mismatch")
        if run.get("toolchainSha256") != TOOLCHAIN_SHA256:
            errors.append(f"ablation run {key}: toolchain hash mismatch")
        if run.get("resourceBudgetSha256") != RESOURCE_BUDGET_SHA256:
            errors.append(f"ablation run {key}: resource-budget hash mismatch")
        if run.get("budget") != COMMON_BUDGET:
            errors.append(f"ablation run {key}: common budget mismatch")
        if run.get("reviewerTimeBudgetSec") != REVIEW_BUDGET_SEC["B5-proposed"]:
            errors.append(f"ablation run {key}: reviewer budget mismatch")
        if run.get("reviewTimeSource") != "fixture":
            errors.append(f"ablation run {key}: review-time source mismatch")
        if run.get("decision") != _ablation_decision(task, ablation, variant):
            errors.append(f"ablation run {key}: executor decision mismatch")
        if run.get("evidenceClass") != "development-only":
            errors.append(
                f"ablation run {key}: evidenceClass must be development-only"
            )
    expected_ablation_keys = {
        (ablation, variant, task_id, model, replicate)
        for ablation, variants in ABLATION_VARIANTS.items()
        for variant in variants
        for task_id in task_by_id
        for model in REQUIRED_MODEL_FAMILIES
        for replicate in REQUIRED_REPLICATES
    }
    missing_ablation_cells = expected_ablation_keys - set(ablation_by_key)
    extra_ablation_cells = set(ablation_by_key) - expected_ablation_keys
    if missing_ablation_cells:
        errors.append(
            f"protocol twin missing {len(missing_ablation_cells)} ablation cells"
        )
    if extra_ablation_cells:
        errors.append(
            f"protocol twin has {len(extra_ablation_cells)} extra ablation cells"
        )
    sentinel_ablation_expected = {
        ("A6-replay-vs-interactive", "fixed-replay"): "abstain",
        ("A6-replay-vs-interactive", "interactive-feedback"): "accepted",
    }
    for (ablation, variant), expected in sentinel_ablation_expected.items():
        for model in REQUIRED_MODEL_FAMILIES:
            for replicate in REQUIRED_REPLICATES:
                row = ablation_by_key.get(
                    (
                        ablation,
                        variant,
                        sentinel_task_id,
                        model,
                        replicate,
                    )
                )
                if row is not None and row.get("decision") != expected:
                    errors.append(
                        f"sentinel {ablation}/{variant} did not exercise its "
                        f"declared semantics for {model}/replicate-{replicate}"
                    )

    expected_hashes = {
        "taskManifestSha256": sha256_value(tasks),
        "trajectorySetSha256": sha256_value(trajectories),
        "armRunSetSha256": sha256_value(arm_runs),
        "ablationRunSetSha256": sha256_value(ablation_runs),
    }
    for field, expected in expected_hashes.items():
        if payload.get(field) != expected:
            errors.append(f"protocol twin {field} mismatch")
    root_payload = copy.deepcopy(payload)
    observed_root = root_payload.pop("protocolTwinRootSha256", None)
    if sha256_value(root_payload) != observed_root:
        errors.append("protocol twin root hash mismatch")

    report = {
        "schema": "goai-frontier-protocol-twin-validation/v1",
        "status": "PASS" if not errors else "INVALID",
        "protocolValid": not errors,
        "protocolTwinRootSha256": payload.get("protocolTwinRootSha256"),
        "taskCount": len(task_by_id),
        "pairCount": len(pair_rows),
        "frontierPairCount": frontier_pair_count,
        "controlPairCount": control_pair_count,
        "trajectoryCount": len(trajectory_by_key),
        "armCount": len(ARMS),
        "armRunCount": len(arm_by_key),
        "ablationGroupCount": len(ABLATION_VARIANTS),
        "ablationVariantCount": sum(
            len(variants) for variants in ABLATION_VARIANTS.values()
        ),
        "ablationRunCount": len(ablation_by_key),
        "primaryReplayCandidateHashesBound": not any(
            "primary replay candidate bytes differ" in error for error in errors
        ),
        "equalBudgetAccountingBound": not any(
            "budget" in error for error in errors
        ),
        "scientificOutcome": False,
        "statisticsEligible": False,
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "winnerLevelEligible": False,
        "modelContact": False,
        "modelCallCount": 0,
        "networkCallCount": 0,
        "errors": errors,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_TWIN)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_protocol_twin()
    errors, report = validate_protocol_twin(payload)
    expected_payload = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    expected_validation = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if args.check:
        if not args.output.is_file() or args.output.read_text(
            encoding="utf-8"
        ) != expected_payload:
            print(f"PROTOCOL TWIN STALE: {args.output}")
            return 1
        if not args.validation.is_file() or args.validation.read_text(
            encoding="utf-8"
        ) != expected_validation:
            print(f"PROTOCOL TWIN VALIDATION STALE: {args.validation}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected_payload, encoding="utf-8")
        args.validation.write_text(expected_validation, encoding="utf-8")
    print(
        f"PROTOCOL TWIN: {report['status']} "
        f"(arms={report['armCount']}, "
        f"ablationGroups={report['ablationGroupCount']}, "
        f"cells={report['armRunCount'] + report['ablationRunCount']})"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
