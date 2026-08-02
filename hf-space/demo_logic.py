#!/usr/bin/env python3
"""Provider-free logic used by the public no-login GOAI demo."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import demo
from v2.frontier import (
    ExtensionTest,
    FrontierTask,
    ReviewDecision,
    VerificationResult,
    evaluate_frontier_expansion,
    propose_extension,
)

REHEARSAL_SEAL = (
    PACKAGE_ROOT / "v2" / "artifacts" / "synthetic-rehearsal-seal.manifest.json"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _result_payload(result: demo.Result) -> dict:
    return {
        "verdict": result.verdict,
        "reasonCode": result.reason_code,
        "reason": result.reason,
        "tier": result.tier,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def verify_si(candidate: str, reference: str) -> dict:
    return _result_payload(demo.verify_physics(candidate, reference))


def verify_symbolic(candidate: str, reference: str) -> dict:
    return _result_payload(demo.verify_math(candidate, reference))


def reference_episode(problem_id: str, policy: str) -> list[dict]:
    problem = demo.PROBLEM_BY_ID[problem_id]
    return [asdict(record) for record in demo.run_episode(problem, policy)]


def frontier_gate_preview(
    owner_approved: bool,
    expert_approved: bool,
    tests_pass: bool,
) -> dict:
    """Demonstrate gate mechanics on a public synthetic example only."""
    task = FrontierTask(
        problem_id="public-demo-temperature-contract",
        domain="physics",
        rung="frontier-gap",
        prompt="Convert a declared Fahrenheit value to Kelvin.",
        initial_coverage=False,
        expected_abstain_reason="missing_verifier",
    )
    pre_gate = VerificationResult(
        "abstain",
        "missing_verifier",
        "the base demo has no affine-temperature verifier",
        "coverage",
    )
    proposal = propose_extension(
        task,
        episode_id="public-demo:temperature:0",
        abstain_reason="missing_verifier",
        candidate_verifier=(
            "Fahrenheit-to-Kelvin affine transform with unit and tolerance checks"
        ),
        test_ids=("positive", "wrong-offset", "wrong-unit"),
    )
    decisions: list[ReviewDecision] = []
    for approved, reviewer in (
        (owner_approved, "owner"),
        (expert_approved, "expert-ai"),
    ):
        decisions.append(
            ReviewDecision(
                schema="goai-frontier-decision/v1",
                proposal_id=proposal.proposal_id,
                reviewer=reviewer,
                decision="approve_candidate" if approved else "defer",
                reason_codes=(),
                notes="public interactive preview",
                reviewed_at="2026-07-31T00:00:00Z",
                saw_aggregate_results=False,
            )
        )
    tests = tuple(
        ExtensionTest(test_id, tests_pass, "public preview")
        for test_id in proposal.test_ids
    )
    result, receipt = evaluate_frontier_expansion(
        task,
        pre_gate=pre_gate,
        proposal=proposal,
        decisions=tuple(decisions),
        tests=tests,
        reverify=lambda: VerificationResult(
            "accepted",
            "affine_temperature_verified",
            "public synthetic candidate passed the declared transform",
            "affine-temperature",
        ),
    )
    return {
        "previewOnly": True,
        "result": result.to_dict(),
        "receipt": receipt.to_dict(),
        "note": (
            "This public example demonstrates gate mechanics only. It is not a "
            "confirmatory task, extension approval, or capability result."
        ),
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def load_public_seal(path: Path = REHEARSAL_SEAL) -> tuple[dict, list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, [f"missing public seal: {path.name}"]
    try:
        seal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {}, [f"invalid public seal: {type(exc).__name__}"]
    if not isinstance(seal, dict):
        return {}, ["public seal must be a JSON object"]
    expected = {
        "schema": "goai-frontier-synthetic-rehearsal-seal/v1",
        "status": "design-rehearsal-not-confirmatory",
        "taskCount": 144,
        "pairCount": 72,
        "frontierPairCount": 60,
        "controlPairCount": 12,
        "outcomesViewedAtSeal": False,
        "confirmatoryEligible": False,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    for field, value in expected.items():
        if seal.get(field) != value:
            errors.append(
                f"public seal {field} must be {value!r}, got {seal.get(field)!r}"
            )
    for field in (
        "privateTaskManifestSha256",
        "seedCommitmentSha256",
        "generatorSha256",
    ):
        if not SHA256.fullmatch(str(seal.get(field) or "")):
            errors.append(f"public seal {field} must be SHA-256")
    return seal, errors


def public_status(seal_path: Path = REHEARSAL_SEAL) -> dict:
    seal, seal_errors = load_public_seal(seal_path)
    return {
        "project": "Human-gated verification-frontier expansion",
        "track": "GOAI AI for Research / Open Exploration",
        "syntheticRehearsalSealValidation": {
            "status": "PASS" if not seal_errors else "INVALID",
            "errors": seal_errors,
        },
        "syntheticRehearsalSeal": {
            key: seal.get(key)
            for key in (
                "status",
                "taskCount",
                "pairCount",
                "frontierPairCount",
                "controlPairCount",
                "privateTaskManifestSha256",
                "seedCommitmentSha256",
                "generatorSha256",
                "outcomesViewedAtSeal",
            )
        },
        "confirmatorySealAvailable": False,
        "confirmatoryExecutionAuthorized": False,
        "confirmatoryOutcomesAvailable": False,
        "claimCeiling": {
            "candidateOnly": True,
            "canClaimAGI": False,
        },
    }
