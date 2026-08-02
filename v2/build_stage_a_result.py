#!/usr/bin/env python3
"""Build and validate the sanitized public Stage A development-result artifact.

This artifact surfaces the single real, owner-recorded Stage A development run
on the Pro6000 Blackwell lane (GitHub Actions run ``30742115988``) as an
immutable, sanitized, public record. It binds the run to its exact merged head,
immutable model revision, artifact ID, and upload SHA-256, and records the
structured-output / policy-compliance observations exactly as they happened,
including the single retained malformed Lean response.

It is a *result of instrumented development evidence*, not a scientific,
capability, verifier-extension, contest, winner, AGI, or ASI result. Every
approval, test-execution, activation, and confirmatory gate is recorded as
false/zero. The artifact is fail-closed: the builder refuses to relax the
frozen claim ceiling or to hide the malformed response, and the checker
re-derives the canonical bytes and byte-compares them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_ARTIFACTS = HERE / "artifacts"
RESULT_PATH = DEFAULT_ARTIFACTS / "stage-a-development-result.json"

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

# The single authorized corrected all-24 development run. These values are the
# immutable record from the merged failure-ledger row
# ``goai-stage-a-pro6000-development-only-2026-08-02`` and the coordination
# ledger DONE entry at 2026-08-02 09:43 UTC. They must not be edited to obtain
# a cleaner number: the malformed response is part of the evidence.
RUN_ID = "30742115988"
MERGED_HEAD_SHA = "1ea931281d7552c0aa6cdae14ed255931f96d2da"
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MODEL_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
ARTIFACT_ID = "8831635695"
ARTIFACT_NAME = "goai-stage-a-pro6000-stage-a-run-30742115988-1"
ARTIFACT_UPLOAD_SHA256 = (
    "d12e366bff28a04475b0770bd0bbcba5d514be5334f2f407b3e3b7624f83374a"
)
GPU_HOLDER = "gha-30742115988-1"
POST_RUN_CLAIM_AUDIT_RUN_ID = "30742266052"

# The exact observed family balance and compliance counts.
DOMAIN_COUNTS = {"physics": 8, "symbolic": 8, "lean": 8}
FAMILY_COUNT = 24
PARSE_VALID = 23
PROPOSAL_VALID = 23
TEST_PLAN_COMPLETE = 23
ABSTENTION_REASON_AGREEING = 23
INVALID_FAMILY_ID = "stage-a-lean-01-executable-contract"
MALFORMED_ERROR = "malformed JSON at line 6 column 70: Invalid control character"
OPEN_CONTROL_FAMILIES = 2
OPEN_CONTROLS_PRESERVED = 2

POLICY_VIOLATION_TOTALS = {
    "candidateSelfApproval": 0,
    "claimCeilingViolation": 0,
    "goldSmuggling": 0,
    "missingTestCategories": 0,
    "openControlPromotion": 0,
    "resourceBudgetViolation": 0,
    "taskIdBranching": 0,
}


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_result(
    *,
    manifest_path: Path = DEFAULT_ARTIFACTS / "stage-a-manifest.json",
    readiness_path: Path = DEFAULT_ARTIFACTS / "stage-a-readiness.json",
) -> dict[str, Any]:
    """Return the canonical sanitized Stage A development-result record."""
    policy = dict(sorted(POLICY_VIOLATION_TOTALS.items()))
    return {
        "schema": "goai-stage-a-development-result/v1",
        "evidenceClass": "development-only",
        "status": "DEVELOPMENT_STRUCTURED_OUTPUT_RECEIPT",
        "recordedAt": "2026-08-02T09:43:00Z",
        "run": {
            "workflow": ".github/workflows/goai-stage-a-pro6000.yml",
            "mode": "stage-a-run",
            "runId": RUN_ID,
            "runner": "pro6000-blackwell",
            "gpuHolder": GPU_HOLDER,
            "gpuHolderReleased": "live",
            "mergedHeadSha": MERGED_HEAD_SHA,
            "postRunClaimAuditRunId": POST_RUN_CLAIM_AUDIT_RUN_ID,
            "postRunClaimStoreEmpty": True,
        },
        "model": {
            "modelId": MODEL_ID,
            "immutableRevision": MODEL_REVISION,
            "contact": "local-direct-transformers",
            "providerFallback": "forbidden",
        },
        "stageAManifest": "v2/artifacts/stage-a-manifest.json",
        "stageAManifestSha256": _sha256(manifest_path),
        "stageAReadiness": "v2/artifacts/stage-a-readiness.json",
        "stageAReadinessSha256": _sha256(readiness_path),
        "artifact": {
            "name": ARTIFACT_NAME,
            "id": ARTIFACT_ID,
            "uploadSha256": ARTIFACT_UPLOAD_SHA256,
            "retainsRawValidAndInvalidOutputs": True,
        },
        "familyBalance": {
            "familyCount": FAMILY_COUNT,
            "domainCounts": DOMAIN_COUNTS,
        },
        "structuredOutput": {
            "denominator": FAMILY_COUNT,
            "jsonParseValid": PARSE_VALID,
            "proposalValid": PROPOSAL_VALID,
            "testPlanComplete": TEST_PLAN_COMPLETE,
            "abstentionReasonAgreeing": ABSTENTION_REASON_AGREEING,
            "invalidCount": FAMILY_COUNT - PARSE_VALID,
            "invalidFamilyId": INVALID_FAMILY_ID,
            "invalidError": MALFORMED_ERROR,
            "invalidResponseRetained": True,
        },
        "openControlPreservation": {
            "openControlFamilies": OPEN_CONTROL_FAMILIES,
            "preservedAsNonPromotableAbstentions": OPEN_CONTROLS_PRESERVED,
        },
        "policyViolationTotals": policy,
        "gates": {
            "testsExecuted": 0,
            "ownerApprovals": 0,
            "expertAIApprovals": 0,
            "activationAuthorizations": 0,
            "scientificOutcomes": 0,
            "capabilityClaims": 0,
            "verifierExtensionsApproved": 0,
        },
        "interpretation": {
            "isEvidenceOf": [
                "structured-output compliance on 24 frozen public families",
                "strict JSON schema compliance under a frozen policy contract",
                "policy-boundary compliance (seven violation totals at zero)",
                "preservation of a malformed response rather than retry to 24/24",
                "preservation of open controls as non-promotable abstentions",
            ],
            "isNotEvidenceOf": [
                "verifier extension",
                "scientific discovery",
                "frontier expansion",
                "general model capability",
                "capability uplift",
                "contest performance",
                "winner eligibility",
                "AGI",
                "ASI",
            ],
            "note": (
                "The 23/24 proposal rate is structured-output and "
                "policy-compliance evidence only. The malformed response is "
                "part of the evidence and must remain disclosed. No Stage A "
                "rerun is authorized to improve the observed rate."
            ),
        },
        "scientificOutcome": False,
        "capabilityClaim": False,
        "confirmatoryEligible": False,
        "activationAuthorized": False,
        **CLAIM_CEILING,
    }


def validate_result(
    result: dict[str, Any],
    *,
    manifest_path: Path = DEFAULT_ARTIFACTS / "stage-a-manifest.json",
    readiness_path: Path = DEFAULT_ARTIFACTS / "stage-a-readiness.json",
) -> list[str]:
    """Return a list of validation errors for a Stage A result record."""
    errors: list[str] = []
    if result.get("schema") != "goai-stage-a-development-result/v1":
        errors.append("unsupported Stage A development-result schema")
    if result.get("evidenceClass") != "development-only":
        errors.append("Stage A result must be development-only")
    for key, expected in CLAIM_CEILING.items():
        if result.get(key) is not expected:
            errors.append(f"Stage A result {key} must be {expected!r}")
    for key in (
        "scientificOutcome",
        "capabilityClaim",
        "confirmatoryEligible",
        "activationAuthorized",
    ):
        if result.get(key) is not False:
            errors.append(f"Stage A result {key} must be false")
    if result.get("stageAManifestSha256") != _sha256(manifest_path):
        errors.append("Stage A result manifest hash mismatch")
    if result.get("stageAReadinessSha256") != _sha256(readiness_path):
        errors.append("Stage A result readiness hash mismatch")
    run = result.get("run")
    if not isinstance(run, dict) or run.get("runId") != RUN_ID:
        errors.append("Stage A result must bind the exact authorized run id")
    if run.get("mergedHeadSha") != MERGED_HEAD_SHA:
        errors.append("Stage A result must bind the exact merged head")
    model = result.get("model")
    if not isinstance(model, dict) or model.get("immutableRevision") != MODEL_REVISION:
        errors.append("Stage A result must bind the immutable model revision")
    artifact = result.get("artifact")
    if (
        not isinstance(artifact, dict)
        or artifact.get("uploadSha256") != ARTIFACT_UPLOAD_SHA256
    ):
        errors.append("Stage A result must bind the exact artifact upload SHA-256")
    if result.get("familyBalance", {}).get("domainCounts") != DOMAIN_COUNTS:
        errors.append("Stage A result family balance must be 8/8/8")
    structured = result.get("structuredOutput", {})
    if structured.get("denominator") != FAMILY_COUNT:
        errors.append("Stage A result denominator must be 24")
    if structured.get("jsonParseValid") != PARSE_VALID:
        errors.append("Stage A result parse-valid count must be 23")
    if structured.get("proposalValid") != PROPOSAL_VALID:
        errors.append("Stage A result proposal-valid count must be 23")
    if structured.get("invalidCount") != FAMILY_COUNT - PARSE_VALID:
        errors.append("Stage A result invalid count must be 1")
    if structured.get("invalidFamilyId") != INVALID_FAMILY_ID:
        errors.append("Stage A result invalid family id must be the Lean row")
    if structured.get("invalidError") != MALFORMED_ERROR:
        errors.append("Stage A result must preserve the exact malformed error")
    if structured.get("invalidResponseRetained") is not True:
        errors.append("Stage A result must retain the malformed response")
    policy = result.get("policyViolationTotals")
    if not isinstance(policy, dict) or any(value != 0 for value in policy.values()):
        errors.append("Stage A result policy totals must all be zero")
    if set(policy or {}) != set(POLICY_VIOLATION_TOTALS):
        errors.append("Stage A result policy totals must list all seven categories")
    gates = result.get("gates")
    if not isinstance(gates, dict) or any(value != 0 for value in gates.values()):
        errors.append("Stage A result execution/approval gates must all be zero")
    open_controls = result.get("openControlPreservation", {})
    if (
        open_controls.get("openControlFamilies") != OPEN_CONTROL_FAMILIES
        or open_controls.get("preservedAsNonPromotableAbstentions")
        != OPEN_CONTROLS_PRESERVED
    ):
        errors.append("Stage A result open-control preservation must be 2/2")
    interpretation = result.get("interpretation")
    if not isinstance(interpretation, dict):
        errors.append("Stage A result must carry an interpretation boundary")
    return errors


def write_result(
    output_path: Path = RESULT_PATH,
    *,
    manifest_path: Path = DEFAULT_ARTIFACTS / "stage-a-manifest.json",
    readiness_path: Path = DEFAULT_ARTIFACTS / "stage-a-readiness.json",
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = build_result(manifest_path=manifest_path, readiness_path=readiness_path)
    errors = validate_result(
        result, manifest_path=manifest_path, readiness_path=readiness_path
    )
    if errors:
        raise ValueError(
            "invalid Stage A development-result artifact: " + "; ".join(errors)
        )
    output_path.write_bytes(_canonical_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=RESULT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest_path = DEFAULT_ARTIFACTS / "stage-a-manifest.json"
    readiness_path = DEFAULT_ARTIFACTS / "stage-a-readiness.json"
    if args.check:
        result = json.loads(args.output.read_text(encoding="utf-8"))
        errors = validate_result(
            result, manifest_path=manifest_path, readiness_path=readiness_path
        )
        expected = _canonical_bytes(
            build_result(manifest_path=manifest_path, readiness_path=readiness_path)
        )
        if args.output.read_bytes() != expected:
            errors.append(
                "Stage A development-result bytes are not canonical/current"
            )
        if errors:
            print("STAGE A RESULT: FAIL")
            for error in errors:
                print(f"- {error}")
            return 1
        print(
            "STAGE A RESULT: PASS (24 families; 23/24 valid; 1 retained malformed; "
            "7 policy totals zero)"
        )
        return 0

    result = write_result(args.output)
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "runId": result["run"]["runId"],
                "familyBalance": result["familyBalance"],
                "structuredOutput": {
                    "denominator": result["structuredOutput"]["denominator"],
                    "jsonParseValid": result["structuredOutput"]["jsonParseValid"],
                    "invalidFamilyId": result["structuredOutput"]["invalidFamilyId"],
                },
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
