#!/usr/bin/env python3
"""Build and validate the public GOAI Stage A development programme.

Stage A contains exactly 24 public development families: eight physics, eight
symbolic-mathematics, and eight Lean families. The programme is deliberately
development-only. It can collect bounded model proposals and review/test
receipts, but it cannot activate an extension, enter confirmatory execution, or
support a capability, scientific-discovery, winner, or AGI claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_ARTIFACTS = HERE / "artifacts"
TASK_MANIFEST = DEFAULT_ARTIFACTS / "task-manifest.jsonl"
BASE_VERIFIER_COMMIT = "a961baa612aba11f7215b699f11cc45ec306c54c"

DOMAINS = ("physics", "symbolic", "lean")
ABSTAIN_REASONS = (
    "missing_executable_spec",
    "missing_verifier",
    "ambiguous_target",
    "unsupported_domain",
    "resource_limit",
    "tool_failure",
    "insufficient_evidence",
    "formalization_failed",
)
PROPOSAL_TYPES = (
    "specification",
    "verifier",
    "clarification",
    "resource",
    "evidence",
    "preserve_abstention",
)
REQUIRED_TEST_CATEGORIES = (
    "positive",
    "negative",
    "malformed",
    "safety",
    "rollback",
)
CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


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


def _load_task_rows(path: Path = TASK_MANIFEST) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"task manifest line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(
                f"task manifest line {line_number}: row must be an object"
            )
        task_id = str(row.get("task_id") or "")
        if not task_id:
            raise ValueError(
                f"task manifest line {line_number}: task_id is required"
            )
        if task_id in rows:
            raise ValueError(f"duplicate task_id in task manifest: {task_id}")
        rows[task_id] = row
    return rows


def _test_plan(family_id: str) -> dict[str, list[str]]:
    return {
        "positive": [
            f"{family_id}:positive:01",
            f"{family_id}:positive:02",
        ],
        "negative": [
            f"{family_id}:negative:01",
            f"{family_id}:negative:02",
        ],
        "malformed": [f"{family_id}:malformed:01"],
        "safety": [f"{family_id}:safety:01"],
        "rollback": [f"{family_id}:rollback:01"],
    }


def _family(
    *,
    family_id: str,
    domain: str,
    task_ids: Iterable[str],
    reason: str,
    proposal_type: str,
    patch_class: str,
    open_control: bool = False,
) -> dict[str, Any]:
    tasks = list(task_ids)
    return {
        "schema": "goai-stage-a-family/v1",
        "familyId": family_id,
        "domain": domain,
        "developmentTaskIds": tasks,
        "frozenAbstainReason": reason,
        "permittedProposalType": proposal_type,
        "patchClass": patch_class,
        "proposalEligible": True,
        "openControl": open_control,
        "openControlPromotionAllowed": False,
        "modelMayApprove": False,
        "requiredReviewers": ["owner", "expert-ai"],
        "developmentTestIds": _test_plan(family_id),
        "executionBudget": {
            "maxWallTimeSec": 120,
            "maxMemoryMiB": 2048,
            "maxTests": 10,
            "networkAllowed": False,
            "credentialAccessAllowed": False,
            "filesystemScope": "ephemeral-scratch-only",
        },
        "status": "development-only",
        "confirmatoryEligible": False,
        "scientificOutcome": False,
        **CLAIM_CEILING,
    }


def build_families() -> list[dict[str, Any]]:
    """Return the frozen 24-family Stage A programme."""
    families = [
        _family(
            family_id="stage-a-physics-01-executable-contract",
            domain="physics",
            task_ids=(
                "physics-frontier-01-missing-speed-contract",
                "physics-frontier-02-missing-tolerance",
            ),
            reason="missing_executable_spec",
            proposal_type="specification",
            patch_class="si-executable-contract",
        ),
        _family(
            family_id="stage-a-physics-02-verifier-obligation",
            domain="physics",
            task_ids=(
                "physics-frontier-03-missing-temperature-verifier",
                "physics-frontier-04-missing-vector-verifier",
            ),
            reason="missing_verifier",
            proposal_type="verifier",
            patch_class="si-verifier-obligation",
        ),
        _family(
            family_id="stage-a-physics-03-target-clarification",
            domain="physics",
            task_ids=("physics-frontier-05-ambiguous-acceleration",),
            reason="ambiguous_target",
            proposal_type="clarification",
            patch_class="physics-clarification-only",
        ),
        _family(
            family_id="stage-a-physics-04-domain-adapter",
            domain="physics",
            task_ids=("physics-frontier-06-unsupported-fluid-domain",),
            reason="unsupported_domain",
            proposal_type="verifier",
            patch_class="physics-domain-adapter-candidate",
        ),
        _family(
            family_id="stage-a-physics-05-resource-request",
            domain="physics",
            task_ids=("physics-frontier-07-resource-orbit",),
            reason="resource_limit",
            proposal_type="resource",
            patch_class="bounded-resource-request",
        ),
        _family(
            family_id="stage-a-physics-06-tool-fallback",
            domain="physics",
            task_ids=("physics-frontier-08-tool-failed-solver",),
            reason="tool_failure",
            proposal_type="resource",
            patch_class="declared-tool-fallback-request",
        ),
        _family(
            family_id="stage-a-physics-07-evidence-request",
            domain="physics",
            task_ids=("physics-frontier-09-missing-calibration-data",),
            reason="insufficient_evidence",
            proposal_type="evidence",
            patch_class="bounded-evidence-request",
        ),
        _family(
            family_id="stage-a-physics-08-formalization-repair",
            domain="physics",
            task_ids=("physics-frontier-10-formalization-units",),
            reason="formalization_failed",
            proposal_type="specification",
            patch_class="si-formalization-repair",
        ),
        _family(
            family_id="stage-a-symbolic-01-executable-contract",
            domain="symbolic",
            task_ids=(
                "symbolic-frontier-01-undefined-assumptions",
                "symbolic-frontier-02-missing-equivalence-domain",
            ),
            reason="missing_executable_spec",
            proposal_type="specification",
            patch_class="symbolic-domain-contract",
        ),
        _family(
            family_id="stage-a-symbolic-02-verifier-obligation",
            domain="symbolic",
            task_ids=(
                "symbolic-frontier-03-missing-matrix-verifier",
                "symbolic-frontier-04-missing-distribution-verifier",
            ),
            reason="missing_verifier",
            proposal_type="verifier",
            patch_class="symbolic-verifier-obligation",
        ),
        _family(
            family_id="stage-a-symbolic-03-target-clarification",
            domain="symbolic",
            task_ids=("symbolic-frontier-05-ambiguous-normal-form",),
            reason="ambiguous_target",
            proposal_type="clarification",
            patch_class="symbolic-clarification-only",
        ),
        _family(
            family_id="stage-a-symbolic-04-domain-adapter",
            domain="symbolic",
            task_ids=("symbolic-frontier-06-unsupported-category-theory",),
            reason="unsupported_domain",
            proposal_type="verifier",
            patch_class="symbolic-domain-adapter-candidate",
        ),
        _family(
            family_id="stage-a-symbolic-05-resource-request",
            domain="symbolic",
            task_ids=("symbolic-frontier-07-resource-groebner",),
            reason="resource_limit",
            proposal_type="resource",
            patch_class="bounded-resource-request",
        ),
        _family(
            family_id="stage-a-symbolic-06-tool-fallback",
            domain="symbolic",
            task_ids=("symbolic-frontier-08-tool-failed-cas",),
            reason="tool_failure",
            proposal_type="resource",
            patch_class="declared-tool-fallback-request",
        ),
        _family(
            family_id="stage-a-symbolic-07-evidence-request",
            domain="symbolic",
            task_ids=("symbolic-frontier-09-missing-parameter-evidence",),
            reason="insufficient_evidence",
            proposal_type="evidence",
            patch_class="bounded-evidence-request",
        ),
        _family(
            family_id="stage-a-symbolic-08-formalization-repair",
            domain="symbolic",
            task_ids=("symbolic-frontier-10-formalization-piecewise",),
            reason="formalization_failed",
            proposal_type="specification",
            patch_class="symbolic-formalization-repair",
        ),
        _family(
            family_id="stage-a-lean-01-executable-contract",
            domain="lean",
            task_ids=(
                "lean-frontier-01-missing-natural-language-map",
                "lean-frontier-02-missing-side-conditions",
            ),
            reason="missing_executable_spec",
            proposal_type="specification",
            patch_class="lean-proposition-contract",
        ),
        _family(
            family_id="stage-a-lean-02-library-verifier",
            domain="lean",
            task_ids=("lean-frontier-03-missing-library-verifier",),
            reason="missing_verifier",
            proposal_type="verifier",
            patch_class="lean-library-adapter-candidate",
        ),
        _family(
            family_id="stage-a-lean-03-quantifier-clarification",
            domain="lean",
            task_ids=("lean-frontier-04-ambiguous-quantifiers",),
            reason="ambiguous_target",
            proposal_type="clarification",
            patch_class="lean-clarification-only",
        ),
        _family(
            family_id="stage-a-lean-04-resource-request",
            domain="lean",
            task_ids=("lean-frontier-05-resource-large-proof",),
            reason="resource_limit",
            proposal_type="resource",
            patch_class="bounded-lean-resource-request",
        ),
        _family(
            family_id="stage-a-lean-05-tool-fallback",
            domain="lean",
            task_ids=("lean-frontier-06-tool-failed-lean",),
            reason="tool_failure",
            proposal_type="resource",
            patch_class="declared-lean-tool-retry",
        ),
        _family(
            family_id="stage-a-lean-06-formalization-repair",
            domain="lean",
            task_ids=("lean-frontier-07-formalization-mismatch",),
            reason="formalization_failed",
            proposal_type="specification",
            patch_class="lean-formalization-repair",
        ),
        _family(
            family_id="stage-a-lean-07-open-math-sentinels",
            domain="lean",
            task_ids=(
                "lean-frontier-08-riemann-control",
                "lean-frontier-09-p-vs-np-control",
            ),
            reason="missing_executable_spec",
            proposal_type="preserve_abstention",
            patch_class="non-promotable-open-control",
            open_control=True,
        ),
        _family(
            family_id="stage-a-lean-08-open-physics-sentinel",
            domain="lean",
            task_ids=("lean-frontier-10-navier-stokes-control",),
            reason="missing_executable_spec",
            proposal_type="preserve_abstention",
            patch_class="non-promotable-open-control",
            open_control=True,
        ),
    ]
    return families


def build_manifest(task_manifest: Path = TASK_MANIFEST) -> dict[str, Any]:
    families = build_families()
    task_rows = _load_task_rows(task_manifest)
    task_bindings = {
        task_id: {
            "sha256": _sha256_bytes(_canonical_bytes(task_rows[task_id])),
            "promptSha256": _sha256_bytes(
                str(task_rows[task_id].get("prompt") or "").encode("utf-8")
            ),
        }
        for family in families
        for task_id in family["developmentTaskIds"]
    }
    return {
        "schema": "goai-stage-a-manifest/v1",
        "stage": "A",
        "programme": "public-extension-development",
        "frozenAt": "2026-08-01T00:00:00Z",
        "baseVerifierCommit": BASE_VERIFIER_COMMIT,
        "taskManifest": "v2/artifacts/task-manifest.jsonl",
        "taskManifestSha256": _sha256(task_manifest),
        "familyCount": len(families),
        "domainCounts": dict(
            sorted(Counter(family["domain"] for family in families).items())
        ),
        "typedAbstainReasonsCovered": sorted(
            {family["frozenAbstainReason"] for family in families}
        ),
        "taskBindings": task_bindings,
        "families": families,
        "modelOutputPurpose": (
            "Generate bounded candidate proposals for later owner and independent "
            "expert-AI review. Raw model text is never an approval or certificate."
        ),
        "reviewStatus": "not-started",
        "activationAuthorized": False,
        "confirmatoryEligible": False,
        "scientificOutcome": False,
        "capabilityClaim": False,
        **CLAIM_CEILING,
    }


def validate_manifest(
    manifest: dict[str, Any],
    *,
    task_manifest: Path = TASK_MANIFEST,
) -> list[str]:
    errors: list[str] = []
    task_rows = _load_task_rows(task_manifest)
    if manifest.get("schema") != "goai-stage-a-manifest/v1":
        errors.append("unsupported Stage A manifest schema")
    for key, expected in CLAIM_CEILING.items():
        if manifest.get(key) is not expected:
            errors.append(f"manifest {key} must be {expected!r}")
    if manifest.get("confirmatoryEligible") is not False:
        errors.append("Stage A manifest confirmatoryEligible must be false")
    if manifest.get("scientificOutcome") is not False:
        errors.append("Stage A manifest scientificOutcome must be false")
    if manifest.get("activationAuthorized") is not False:
        errors.append("Stage A manifest activationAuthorized must be false")
    if manifest.get("baseVerifierCommit") != BASE_VERIFIER_COMMIT:
        errors.append("Stage A base verifier commit changed")
    if manifest.get("taskManifestSha256") != _sha256(task_manifest):
        errors.append("Stage A task manifest hash mismatch")

    families = manifest.get("families")
    if not isinstance(families, list):
        return errors + ["families must be a list"]
    if len(families) != 24 or manifest.get("familyCount") != 24:
        errors.append("Stage A must contain exactly 24 families")
    domain_counts = Counter()
    seen_families: set[str] = set()
    seen_tasks: set[str] = set()
    observed_reasons: set[str] = set()
    observed_bindings = manifest.get("taskBindings")
    if not isinstance(observed_bindings, dict):
        errors.append("taskBindings must be an object")
        observed_bindings = {}

    for index, family in enumerate(families):
        label = f"family[{index}]"
        if not isinstance(family, dict):
            errors.append(f"{label} must be an object")
            continue
        family_id = str(family.get("familyId") or "")
        label = family_id or label
        if family.get("schema") != "goai-stage-a-family/v1":
            errors.append(f"{label}: unsupported schema")
        if not family_id or family_id in seen_families:
            errors.append(f"{label}: missing or duplicate familyId")
        seen_families.add(family_id)
        domain = str(family.get("domain") or "")
        if domain not in DOMAINS:
            errors.append(f"{label}: unsupported domain {domain!r}")
        else:
            domain_counts[domain] += 1
        reason = str(family.get("frozenAbstainReason") or "")
        if reason not in ABSTAIN_REASONS:
            errors.append(f"{label}: unsupported abstention reason {reason!r}")
        observed_reasons.add(reason)
        proposal_type = str(family.get("permittedProposalType") or "")
        if proposal_type not in PROPOSAL_TYPES:
            errors.append(f"{label}: unsupported proposal type {proposal_type!r}")
        open_control = family.get("openControl") is True
        if open_control and proposal_type != "preserve_abstention":
            errors.append(
                f"{label}: open controls must use preserve_abstention"
            )
        if (
            family.get("openControlPromotionAllowed") is not False
            or family.get("modelMayApprove") is not False
        ):
            errors.append(f"{label}: promotion/self-approval ceiling weakened")
        if family.get("requiredReviewers") != ["owner", "expert-ai"]:
            errors.append(f"{label}: reviewer separation changed")
        for key, expected in CLAIM_CEILING.items():
            if family.get(key) is not expected:
                errors.append(f"{label}: {key} must be {expected!r}")
        if (
            family.get("confirmatoryEligible") is not False
            or family.get("scientificOutcome") is not False
        ):
            errors.append(f"{label}: development-only ceiling weakened")

        budget = family.get("executionBudget")
        if not isinstance(budget, dict):
            errors.append(f"{label}: executionBudget must be an object")
        else:
            if not (1 <= int(budget.get("maxWallTimeSec") or 0) <= 120):
                errors.append(f"{label}: wall-time budget is unbounded")
            if not (1 <= int(budget.get("maxMemoryMiB") or 0) <= 2048):
                errors.append(f"{label}: memory budget is unbounded")
            if not (1 <= int(budget.get("maxTests") or 0) <= 10):
                errors.append(f"{label}: test budget is unbounded")
            if (
                budget.get("networkAllowed") is not False
                or budget.get("credentialAccessAllowed") is not False
                or budget.get("filesystemScope")
                != "ephemeral-scratch-only"
            ):
                errors.append(f"{label}: authority budget is not fail-closed")

        tests = family.get("developmentTestIds")
        if not isinstance(tests, dict):
            errors.append(f"{label}: developmentTestIds must be an object")
        else:
            if set(tests) != set(REQUIRED_TEST_CATEGORIES):
                errors.append(f"{label}: test categories are incomplete")
            for category in REQUIRED_TEST_CATEGORIES:
                values = tests.get(category)
                minimum = 2 if category in {"positive", "negative"} else 1
                if (
                    not isinstance(values, list)
                    or len(values) < minimum
                    or any(not isinstance(value, str) or not value for value in values)
                ):
                    errors.append(
                        f"{label}: {category} requires at least {minimum} test IDs"
                    )

        task_ids = family.get("developmentTaskIds")
        if not isinstance(task_ids, list) or not task_ids:
            errors.append(f"{label}: developmentTaskIds must be non-empty")
            continue
        for task_id in map(str, task_ids):
            if task_id in seen_tasks:
                errors.append(f"{label}: task reused across Stage A families: {task_id}")
            seen_tasks.add(task_id)
            row = task_rows.get(task_id)
            if row is None:
                errors.append(f"{label}: unknown task ID {task_id}")
                continue
            if row.get("domain") != domain:
                errors.append(f"{label}: task domain mismatch for {task_id}")
            if row.get("expected_abstain_reason") != reason:
                errors.append(f"{label}: frozen reason mismatch for {task_id}")
            if bool(row.get("open_control")) != open_control:
                errors.append(f"{label}: open-control binding mismatch for {task_id}")
            binding = observed_bindings.get(task_id)
            expected_binding = {
                "sha256": _sha256_bytes(_canonical_bytes(row)),
                "promptSha256": _sha256_bytes(
                    str(row.get("prompt") or "").encode("utf-8")
                ),
            }
            if binding != expected_binding:
                errors.append(f"{label}: task binding mismatch for {task_id}")

    if dict(sorted(domain_counts.items())) != {
        "lean": 8,
        "physics": 8,
        "symbolic": 8,
    }:
        errors.append(
            f"Stage A domain counts must be 8/8/8, observed {dict(domain_counts)}"
        )
    if observed_reasons != set(ABSTAIN_REASONS):
        errors.append("Stage A does not cover the complete typed-abstention taxonomy")
    if set(observed_bindings) != seen_tasks:
        errors.append("taskBindings do not exactly match Stage A development tasks")
    declared_reasons = manifest.get("typedAbstainReasonsCovered")
    if declared_reasons != sorted(ABSTAIN_REASONS):
        errors.append("typedAbstainReasonsCovered does not match the frozen taxonomy")
    if manifest.get("domainCounts") != {
        "lean": 8,
        "physics": 8,
        "symbolic": 8,
    }:
        errors.append("declared Stage A domainCounts are invalid")
    return errors


def build_readiness(
    manifest_path: Path,
    *,
    source_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    if source_paths is None:
        source_paths = {
            "PREREGISTRATION.md": HERE / "PREREGISTRATION.md",
            "FRONTIER-EXPANSION-SPEC.md": HERE / "FRONTIER-EXPANSION-SPEC.md",
            "HUMAN-GATE-RUBRIC.md": HERE / "HUMAN-GATE-RUBRIC.md",
            "stage_a.py": Path(__file__),
            "stage_a_model.py": HERE / "stage_a_model.py",
            "stage_a_pro6000.py": HERE / "stage_a_pro6000.py",
            "requirements-stage-a-gpu.txt": (
                PACKAGE_ROOT / "requirements-stage-a-gpu.txt"
            ),
            "scorer-operating-characteristics.json": (
                DEFAULT_ARTIFACTS / "scorer-operating-characteristics.json"
            ),
        }
    bindings = {
        name: _sha256(path)
        for name, path in sorted(source_paths.items())
    }
    return {
        "schema": "goai-stage-a-readiness/v1",
        "createdAt": "2026-08-01T00:00:00Z",
        "stageAManifest": "v2/artifacts/stage-a-manifest.json",
        "stageAManifestSha256": _sha256(manifest_path),
        "sourceFileSha256s": bindings,
        "readiness": {
            "manifestValid": True,
            "familyCount": 24,
            "domainCountsValid": True,
            "typedAbstentionCoverageValid": True,
            "publicTaskBindingsValid": True,
            "openControlPromotionAllowedCount": 0,
            "modelProposalRunComplete": True,
            "modelProposalRunArtifact": (
                "v2/artifacts/stage-a-development-result.json"
            ),
            "ownerReviewComplete": False,
            "independentExpertAIReviewComplete": False,
            "visibleExtensionTestsComplete": False,
            "approvedExtensionBundleFrozen": False,
            "confirmatorySealFrozen": False,
        },
        "powerEvidence": {
            "artifact": "v2/artifacts/scorer-operating-characteristics.json",
            "artifactSha256": bindings["scorer-operating-characteristics.json"],
            "kind": "development-only-low-resample-simulation",
            "confirmatoryPowerValidated": False,
            "note": (
                "The existing scorer simulation is an implementation smoke, not "
                "full-resample power or minimum-detectable-effect evidence."
            ),
        },
        "status": "DEVELOPMENT_PROPOSALS_COLLECTED_AWAITING_REVIEW",
        "activationAuthorized": False,
        "confirmatoryEligible": False,
        "scientificOutcome": False,
        **CLAIM_CEILING,
    }


def validate_readiness(
    readiness: dict[str, Any],
    *,
    manifest_path: Path,
) -> list[str]:
    errors: list[str] = []
    if readiness.get("schema") != "goai-stage-a-readiness/v1":
        errors.append("unsupported Stage A readiness schema")
    if readiness.get("stageAManifestSha256") != _sha256(manifest_path):
        errors.append("Stage A readiness manifest hash mismatch")
    for key, expected in CLAIM_CEILING.items():
        if readiness.get(key) is not expected:
            errors.append(f"Stage A readiness {key} must be {expected!r}")
    if (
        readiness.get("activationAuthorized") is not False
        or readiness.get("confirmatoryEligible") is not False
        or readiness.get("scientificOutcome") is not False
    ):
        errors.append("Stage A readiness claim boundary is not fail-closed")
    gates = readiness.get("readiness")
    if not isinstance(gates, dict):
        errors.append("Stage A readiness gates must be an object")
    else:
        for name in (
            "ownerReviewComplete",
            "independentExpertAIReviewComplete",
            "visibleExtensionTestsComplete",
            "approvedExtensionBundleFrozen",
            "confirmatorySealFrozen",
        ):
            if gates.get(name) is not False:
                errors.append(f"Stage A future gate must remain false: {name}")
        if gates.get("modelProposalRunComplete") is not True:
            errors.append(
                "Stage A development proposal run is complete and must be true"
            )
        if gates.get("modelProposalRunArtifact") != (
            "v2/artifacts/stage-a-development-result.json"
        ):
            errors.append(
                "Stage A readiness must bind the development-result artifact"
            )
        if gates.get("openControlPromotionAllowedCount") != 0:
            errors.append("Stage A open-control promotion count must be zero")
    power = readiness.get("powerEvidence")
    if (
        not isinstance(power, dict)
        or power.get("confirmatoryPowerValidated") is not False
    ):
        errors.append("Stage A readiness overstates power evidence")
    return errors


def write_artifacts(output_dir: Path = DEFAULT_ARTIFACTS) -> tuple[dict, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("invalid Stage A manifest: " + "; ".join(errors))
    manifest_path = output_dir / "stage-a-manifest.json"
    manifest_path.write_bytes(_canonical_bytes(manifest))
    readiness = build_readiness(manifest_path)
    readiness_errors = validate_readiness(
        readiness,
        manifest_path=manifest_path,
    )
    if readiness_errors:
        raise ValueError(
            "invalid Stage A readiness artifact: "
            + "; ".join(readiness_errors)
        )
    (output_dir / "stage-a-readiness.json").write_bytes(
        _canonical_bytes(readiness)
    )
    return manifest, readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        manifest_path = args.output_dir / "stage-a-manifest.json"
        readiness_path = args.output_dir / "stage-a-readiness.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        errors = validate_manifest(manifest)
        errors.extend(
            validate_readiness(readiness, manifest_path=manifest_path)
        )
        expected_manifest = _canonical_bytes(build_manifest())
        expected_readiness = _canonical_bytes(build_readiness(manifest_path))
        if manifest_path.read_bytes() != expected_manifest:
            errors.append("Stage A manifest bytes are not canonical/current")
        if readiness_path.read_bytes() != expected_readiness:
            errors.append("Stage A readiness bytes are not canonical/current")
        if errors:
            print("STAGE A: FAIL")
            for error in errors:
                print(f"- {error}")
            return 1
        print("STAGE A: PASS (24 families; 8 physics / 8 symbolic / 8 Lean)")
        return 0

    manifest, readiness = write_artifacts(args.output_dir)
    print(
        json.dumps(
            {
                "familyCount": manifest["familyCount"],
                "domainCounts": manifest["domainCounts"],
                "status": readiness["status"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
