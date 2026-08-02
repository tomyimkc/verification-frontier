#!/usr/bin/env python3
"""Verify the upload-ready GOAI bundle and its embedded evidence contract."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import tempfile
import zipfile
from collections import Counter
from functools import lru_cache
from pathlib import Path, PurePosixPath

from pypdf import PdfReader

from build_bundle import REQUIRED as BUNDLE_REQUIRED
from build_bundle import canonical_bundle_bytes
from build_bundle import receipt_rehearsal_files
from submission.pdf_contract import INVARIANT_PDF_DATE
from v2.benchmark_study_root import run_benchmark
from v2.protocol_twin import validate_protocol_twin
from v2.receipt_protocol import validate_extension_chain
from v2.simulate_scorer import (
    DEFAULT_SIMULATIONS_PER_HYPOTHESIS,
    simulate,
)
from v2.study_root import SOURCE_FILES, validate_study_materials
from v2 import stage_a

MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 512
_STUDY_BENCHMARK_CACHE: dict[
    tuple[str, str, str, str, str],
    tuple[tuple[str, ...], dict],
] = {}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unsafe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or path.as_posix() != name
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _json_loads(data: bytes):
    return json.loads(data, parse_constant=_reject_json_constant)


@lru_cache(maxsize=1)
def _recomputed_scorer_simulation() -> tuple[tuple[str, ...], dict]:
    errors, report = simulate(DEFAULT_SIMULATIONS_PER_HYPOTHESIS)
    return tuple(errors), report


def _materialize_receipt_store(
    store: Path,
    payloads: dict[str, bytes],
    receipt_prefix: str,
    receipt_hashes: list,
    blob_hashes: list,
) -> None:
    (store / "blobs").mkdir()
    for digest in map(str, receipt_hashes):
        name = receipt_prefix + f"{digest}.json"
        if name in payloads:
            (store / f"{digest}.json").write_bytes(payloads[name])
    for digest in map(str, blob_hashes):
        name = receipt_prefix + f"blobs/{digest}.blob"
        if name in payloads:
            (store / "blobs" / f"{digest}.blob").write_bytes(
                payloads[name]
            )


def _study_source_binding_errors(
    study_root: dict,
    payloads: dict[str, bytes],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    bindings = study_root.get("sourceFileSha256s")
    if not isinstance(bindings, dict):
        return ["Study Root sourceFileSha256s must be an object"]
    expected_names = set(SOURCE_FILES)
    actual_names = set(map(str, bindings))
    if actual_names != expected_names:
        errors.append(
            "Study Root source binding names do not exactly match the "
            "frozen source allowlist"
        )
    for name in SOURCE_FILES:
        bundle_name = prefix + "v2/" + name
        if bundle_name not in payloads:
            errors.append(
                f"missing Study Root bound source: {bundle_name}"
            )
            continue
        expected_digest = str(bindings.get(name) or "")
        actual_digest = sha256(payloads[bundle_name])
        if expected_digest != actual_digest:
            errors.append(
                f"Study Root source binding hash mismatch: {name}"
            )
    return errors


def _study_source_material_sha256(
    payloads: dict[str, bytes],
    prefix: str,
) -> str:
    digest = hashlib.sha256()
    for name in SOURCE_FILES:
        data = payloads[prefix + "v2/" + name]
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def validate(bundle: Path) -> list[str]:
    errors: list[str] = []
    prefix = "goai-ai4r-open-exploration/"
    if not bundle.is_file():
        return [f"missing bundle: {bundle}"]
    try:
        archive_size = bundle.stat().st_size
    except OSError as exc:
        return [f"cannot stat bundle {bundle}: {type(exc).__name__}: {exc}"]
    if archive_size > MAX_ARCHIVE_BYTES:
        return [
            f"bundle exceeds compressed size limit: {archive_size}/"
            f"{MAX_ARCHIVE_BYTES}"
        ]
    try:
        archive_context = zipfile.ZipFile(bundle)
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"invalid bundle {bundle}: {type(exc).__name__}: {exc}"]

    with archive_context as archive:
        archive_entries = archive.infolist()
        name_list = [entry.filename for entry in archive_entries]
        names = set(name_list)
        duplicate_names = sorted(
            name for name, count in Counter(name_list).items() if count > 1
        )
        if len(archive_entries) > MAX_ARCHIVE_ENTRIES:
            return errors + [
                f"archive entry count exceeds limit: "
                f"{len(archive_entries)}/{MAX_ARCHIVE_ENTRIES}"
            ]
        total_uncompressed = sum(
            entry.file_size for entry in archive_entries
        )
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
            return errors + [
                "archive total uncompressed size exceeds validation limit: "
                f"{total_uncompressed}/{MAX_TOTAL_UNCOMPRESSED_BYTES}"
            ]
        resource_errors: list[str] = []
        for entry in archive_entries:
            if entry.file_size > MAX_MEMBER_BYTES:
                resource_errors.append(
                    f"archive entry exceeds size limit: {entry.filename}"
                )
            if (
                (entry.file_size > 0 and entry.compress_size == 0)
                or (
                    entry.compress_size > 0
                    and entry.file_size / entry.compress_size
                    > MAX_COMPRESSION_RATIO
                )
            ):
                resource_errors.append(
                    f"archive entry exceeds compression-ratio limit: "
                    f"{entry.filename}"
                )
        if resource_errors:
            return errors + resource_errors
        payloads: dict[str, bytes] = {}
        for entry in archive_entries:
            try:
                data = archive.read(entry)
            except Exception as exc:
                errors.append(
                    f"cannot read archive entry {entry.filename}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            if entry.filename not in payloads:
                payloads[entry.filename] = data
        manifest_name = prefix + "MANIFEST.sha256"
        try:
            expected_relative_names = set(BUNDLE_REQUIRED)
            expected_relative_names.update(receipt_rehearsal_files())
        except SystemExit as exc:
            return [
                "cannot derive exact bundle allowlist from receipt index: "
                f"{exc}"
            ]
        expected_names = {
            prefix + relative for relative in expected_relative_names
        }
        expected_names.add(manifest_name)
        unexpected_names = sorted(names - expected_names)
        missing_allowlisted_names = sorted(expected_names - names)
        if unexpected_names or missing_allowlisted_names:
            errors.append(
                "archive entry set does not exactly match builder allowlist; "
                f"unexpected={unexpected_names}, "
                f"missing={missing_allowlisted_names}"
            )
        for name in sorted(expected_names & payloads.keys()):
            if name.endswith(".json"):
                try:
                    value = _json_loads(payloads[name])
                except Exception as exc:
                    errors.append(
                        f"invalid public JSON claim artifact {name}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue
                if not isinstance(value, dict):
                    errors.append(
                        f"public JSON claim artifact must be an object: {name}"
                    )
                    continue
                if value.get("candidateOnly") is not True:
                    errors.append(
                        f"public JSON claim artifact candidateOnly must be "
                        f"true: {name}"
                    )
                if value.get("canClaimAGI") is not False:
                    errors.append(
                        f"public JSON claim artifact canClaimAGI must be "
                        f"false: {name}"
                    )
            elif name.endswith(".jsonl"):
                for line_number, line in enumerate(
                    payloads[name].splitlines(),
                    start=1,
                ):
                    if not line:
                        continue
                    try:
                        value = _json_loads(line)
                    except Exception as exc:
                        errors.append(
                            f"invalid public JSONL claim artifact {name}:"
                            f"{line_number}: {type(exc).__name__}: {exc}"
                        )
                        continue
                    if (
                        not isinstance(value, dict)
                        or value.get("candidateOnly") is not True
                        or value.get("canClaimAGI") is not False
                    ):
                        errors.append(
                            f"public JSONL claim ceiling is invalid: "
                            f"{name}:{line_number}"
                        )
        if (
            not duplicate_names
            and names == expected_names
            and expected_names.issubset(payloads)
        ):
            relative_payloads = {
                name.removeprefix(prefix): payloads[name]
                for name in expected_names
            }
            try:
                canonical = canonical_bundle_bytes(relative_payloads)
                observed_bundle = bundle.read_bytes()
            except Exception as exc:
                errors.append(
                    "cannot compare canonical bundle bytes: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if observed_bundle != canonical:
                    errors.append(
                        "bundle bytes do not match the deterministic canonical "
                        "archive representation"
                    )
        for entry in archive_entries:
            unix_mode = (entry.external_attr >> 16) & 0xFFFF
            if entry.create_system != 3 or not stat.S_ISREG(unix_mode):
                errors.append(
                    f"archive entry is not a regular file: {entry.filename}"
                )
        if duplicate_names:
            errors.append(f"duplicate archive entry names: {duplicate_names}")
        unexpected_roots = sorted(name for name in names if not name.startswith(prefix))
        if unexpected_roots:
            errors.append(f"entries outside required prefix {prefix!r}: {unexpected_roots}")
        unsafe_names = sorted(name for name in names if _unsafe_archive_name(name))
        if unsafe_names:
            errors.append(f"unsafe archive entry names: {unsafe_names}")
        forbidden = [
            name
            for name in names
            if (
                PurePosixPath(name).as_posix() == prefix + "v2/private"
                or PurePosixPath(name)
                .as_posix()
                .startswith(prefix + "v2/private/")
            )
            or any(
                    token in name
                    for token in (
                        "__pycache__",
                        ".pyc",
                        ".DS_Store",
                        ".venv",
                        "OWNER-CHECKLIST",
                        "/.git/",
                    )
                )
        ]
        if forbidden:
            errors.append(f"forbidden archive entries: {forbidden}")

        if manifest_name not in names:
            return errors + ["missing embedded MANIFEST.sha256"]
        try:
            manifest_rows = payloads[manifest_name].decode("utf-8").splitlines()
        except (KeyError, UnicodeDecodeError) as exc:
            return errors + [f"invalid MANIFEST.sha256: {type(exc).__name__}: {exc}"]

        manifest_names: set[str] = set()
        for line_number, row in enumerate(manifest_rows, start=1):
            if not row or "  " not in row:
                errors.append(f"manifest line {line_number}: expected '<sha256>  <path>'")
                continue
            expected, relative = row.split("  ", 1)
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                errors.append(f"manifest line {line_number}: invalid SHA-256")
                continue
            if not relative or _unsafe_archive_name(relative):
                errors.append(f"manifest line {line_number}: unsafe or empty path {relative!r}")
                continue
            name = prefix + relative
            if name in manifest_names:
                errors.append(f"manifest line {line_number}: duplicate path {relative}")
                continue
            manifest_names.add(name)
            if name not in names:
                errors.append(f"manifest entry missing from archive: {relative}")
                continue
            if name not in payloads:
                errors.append(f"manifest entry could not be read: {relative}")
                continue
            observed = sha256(payloads[name])
            if observed != expected:
                errors.append(f"checksum mismatch: {relative}")

        unmanifested = sorted(names - manifest_names - {manifest_name})
        if unmanifested:
            errors.append(f"archive entries missing from manifest: {unmanifested}")
        for name in sorted(names):
            if not name.endswith((".json", ".jsonl")):
                continue
            try:
                text = payloads[name].decode("utf-8")
            except (KeyError, UnicodeDecodeError):
                continue
            for marker in ("/Users/", "/private/", "/home/runner/", "C:\\Users\\"):
                if marker in text:
                    errors.append(
                        f"public JSON artifact exposes a host-local path: {name}"
                    )
                    break

        summary_name = prefix + "artifacts/benchmark-summary.json"
        if summary_name not in names:
            errors.append(f"missing required bundle entry: {summary_name}")
        else:
            try:
                summary = _json_loads(payloads[summary_name])
            except Exception as exc:
                errors.append(f"invalid bundle summary: {type(exc).__name__}: {exc}")
            else:
                if not isinstance(summary, dict):
                    errors.append("bundle summary must be a JSON object")
                else:
                    if summary.get("candidateOnly") is not True:
                        errors.append("bundle summary candidateOnly must be true")
                    if summary.get("canClaimAGI") is not False:
                        errors.append("bundle summary canClaimAGI must be false")
                    policies = summary.get("policies")
                    if not isinstance(policies, dict):
                        errors.append("bundle summary policies must be an object")
                    elif any(
                        not isinstance(details, dict)
                        or details.get("openUnformalizedAccepted") != 0
                        for details in policies.values()
                    ):
                        errors.append(
                            "a bundled policy is malformed or accepted an "
                            "open-unformalized item"
                        )

        seal_name = prefix + "v2/artifacts/synthetic-rehearsal-seal.manifest.json"
        if seal_name not in names:
            errors.append(f"missing required bundle entry: {seal_name}")
        else:
            try:
                seal = _json_loads(payloads[seal_name])
            except Exception as exc:
                errors.append(
                    f"invalid synthetic rehearsal seal: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(seal, dict):
                    errors.append("synthetic rehearsal seal must be a JSON object")
                else:
                    expected_fields = {
                        "taskCount": 144,
                        "pairCount": 72,
                        "frontierPairCount": 60,
                        "controlPairCount": 12,
                        "outcomesViewedAtSeal": False,
                        "confirmatoryEligible": False,
                        "status": "design-rehearsal-not-confirmatory",
                        "candidateOnly": True,
                        "canClaimAGI": False,
                    }
                    for field, expected in expected_fields.items():
                        if seal.get(field) != expected:
                            errors.append(
                                f"synthetic rehearsal seal {field} must be "
                                f"{expected!r}, got {seal.get(field)!r}"
                            )
                    for field in (
                        "privateTaskManifestSha256",
                        "seedCommitmentSha256",
                        "generatorSha256",
                    ):
                        if not re.fullmatch(
                            r"[0-9a-f]{64}",
                            str(seal.get(field) or ""),
                        ):
                            errors.append(
                                f"synthetic rehearsal seal {field} is not SHA-256"
                            )

        task_manifest_name = prefix + "v2/artifacts/task-manifest.jsonl"
        validation_name = prefix + "v2/artifacts/task-validation.json"
        if task_manifest_name not in names:
            errors.append(f"missing required bundle entry: {task_manifest_name}")
        if validation_name not in names:
            errors.append(f"missing required bundle entry: {validation_name}")
        if task_manifest_name in names and validation_name in names:
            try:
                validation = _json_loads(payloads[validation_name])
            except Exception as exc:
                errors.append(
                    f"invalid strict task validation: {type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(validation, dict):
                    errors.append("strict task validation must be a JSON object")
                else:
                    expected_validation = {
                        "taskCount": 150,
                        "validCount": 150,
                        "invalidCount": 0,
                        "leanRequired": True,
                        "candidateOnly": True,
                        "canClaimAGI": False,
                    }
                    for field, expected in expected_validation.items():
                        if validation.get(field) != expected:
                            errors.append(
                                f"strict task validation {field} must be "
                                f"{expected!r}, got {validation.get(field)!r}"
                            )
                    expected_manifest_hash = sha256(
                        payloads[task_manifest_name]
                    )
                    if validation.get("manifestSha256") != expected_manifest_hash:
                        errors.append(
                            "strict task validation manifestSha256 does not match "
                            "the bundled task manifest"
                        )
                    if "leanProject" in validation:
                        errors.append(
                            "strict task validation must not expose a local Lean path"
                        )
                    if validation.get("leanVersion") != "4.24.0":
                        errors.append(
                            "strict task validation Lean version must be 4.24.0"
                        )
                    if validation.get("leanProjectLabel") != "pinned-miniF2F-lean4":
                        errors.append(
                            "strict task validation must identify the pinned Lean project"
                        )
                    if (
                        validation.get("leanProjectRepository")
                        != "yangky11/miniF2F-lean4"
                    ):
                        errors.append(
                            "strict task validation Lean repository is unexpected"
                        )
                    if not re.fullmatch(
                        r"[0-9a-f]{40}",
                        str(validation.get("leanProjectCommit") or ""),
                    ):
                        errors.append(
                            "strict task validation must record the Lean project commit"
                        )
                    counts = validation.get("counts")
                    if not isinstance(counts, dict):
                        errors.append(
                            "strict task validation counts must be an object"
                        )
                    else:
                        if counts.get("lean:accepted") != 40:
                            errors.append(
                                "strict task validation must contain 40 accepted "
                                "Lean executable tasks"
                            )
                        if counts.get("lean:abstain") != 10:
                            errors.append(
                                "strict task validation must contain 10 Lean "
                                "frontier abstentions"
                            )

        stage_a_manifest_name = prefix + "v2/artifacts/stage-a-manifest.json"
        stage_a_readiness_name = prefix + "v2/artifacts/stage-a-readiness.json"
        if stage_a_manifest_name not in names:
            errors.append(f"missing required bundle entry: {stage_a_manifest_name}")
        if stage_a_readiness_name not in names:
            errors.append(f"missing required bundle entry: {stage_a_readiness_name}")
        if (
            stage_a_manifest_name in payloads
            and stage_a_readiness_name in payloads
        ):
            try:
                stage_manifest = _json_loads(payloads[stage_a_manifest_name])
                stage_readiness = _json_loads(payloads[stage_a_readiness_name])
            except Exception as exc:
                errors.append(
                    f"invalid Stage A artifacts: {type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(stage_manifest, dict):
                    errors.append("Stage A manifest must be an object")
                else:
                    errors.extend(
                        f"Stage A manifest: {error}"
                        for error in stage_a.validate_manifest(stage_manifest)
                    )
                    expected_stage_manifest = stage_a._canonical_bytes(
                        stage_a.build_manifest()
                    )
                    if payloads[stage_a_manifest_name] != expected_stage_manifest:
                        errors.append(
                            "Stage A manifest bytes do not match the current "
                            "frozen source/task bindings"
                        )
                if not isinstance(stage_readiness, dict):
                    errors.append("Stage A readiness must be an object")
                else:
                    current_manifest_path = (
                        stage_a.DEFAULT_ARTIFACTS / "stage-a-manifest.json"
                    )
                    errors.extend(
                        f"Stage A readiness: {error}"
                        for error in stage_a.validate_readiness(
                            stage_readiness,
                            manifest_path=current_manifest_path,
                        )
                    )
                    expected_stage_readiness = stage_a._canonical_bytes(
                        stage_a.build_readiness(current_manifest_path)
                    )
                    if (
                        payloads[stage_a_readiness_name]
                        != expected_stage_readiness
                    ):
                        errors.append(
                            "Stage A readiness bytes do not match the current "
                            "source bindings"
                        )

        receipt_index_name = (
            prefix + "v2/artifacts/receipt-rehearsal-index.json"
        )
        receipt_validation_name = (
            prefix + "v2/artifacts/receipt-rehearsal-validation.json"
        )
        receipt_prefix = prefix + "v2/artifacts/receipt-rehearsal/"
        receipt_error_start = len(errors)
        receipt_material_valid = False
        recomputed_receipt_reports: list[dict] = []
        receipt_index: dict = {}
        receipt_validation: dict = {}
        receipt_hashes: list = []
        blob_hashes: list = []
        if receipt_index_name not in names:
            errors.append(f"missing required bundle entry: {receipt_index_name}")
        if receipt_validation_name not in names:
            errors.append(
                f"missing required bundle entry: {receipt_validation_name}"
            )
        if receipt_index_name in names:
            try:
                receipt_index = _json_loads(payloads[receipt_index_name])
            except Exception as exc:
                errors.append(
                    f"invalid receipt rehearsal index: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                expected_receipt_index = {
                    "status": "PASS",
                    "evidenceClass": "development-only",
                    "confirmatoryEligible": False,
                    "receiptCount": 34,
                    "blobCount": 60,
                    "candidateOnly": True,
                    "canClaimAGI": False,
                }
                if not isinstance(receipt_index, dict):
                    errors.append("receipt rehearsal index must be an object")
                    receipt_index = {}
                for field, expected in expected_receipt_index.items():
                    if receipt_index.get(field) != expected:
                        errors.append(
                            f"receipt rehearsal index {field} must be "
                            f"{expected!r}, got {receipt_index.get(field)!r}"
                        )
                receipt_hashes = receipt_index.get("receiptSha256s")
                chain_hashes = receipt_index.get("chainSha256s")
                valid_receipt_list = (
                    isinstance(receipt_hashes, list)
                    and len(receipt_hashes) == 34
                    and len(set(map(str, receipt_hashes))) == 34
                    and all(
                        re.fullmatch(r"[0-9a-f]{64}", str(value))
                        for value in receipt_hashes
                    )
                )
                if not valid_receipt_list:
                    errors.append(
                        "receipt rehearsal index must list 34 distinct "
                        "SHA-256 receipts"
                    )
                    receipt_hashes = []
                valid_chain_list = (
                    isinstance(chain_hashes, list)
                    and len(chain_hashes) == 3
                    and len(set(map(str, chain_hashes))) == 3
                    and set(map(str, chain_hashes)).issubset(
                        set(map(str, receipt_hashes))
                    )
                )
                if not valid_chain_list:
                    errors.append(
                        "receipt rehearsal index must list three valid chain hashes"
                    )
                blob_hashes = receipt_index.get("blobSha256s")
                valid_blob_list = (
                    isinstance(blob_hashes, list)
                    and len(blob_hashes) == 60
                    and len(set(map(str, blob_hashes))) == 60
                    and all(
                        re.fullmatch(r"[0-9a-f]{64}", str(value))
                        for value in blob_hashes
                    )
                )
                if not valid_blob_list:
                    errors.append(
                        "receipt rehearsal index must list 60 distinct "
                        "evidence blobs"
                    )
                    blob_hashes = []
                expected_receipt_names = {
                    receipt_prefix + f"{digest}.json"
                    for digest in map(str, receipt_hashes)
                }
                expected_receipt_names.update(
                    receipt_prefix + f"blobs/{digest}.blob"
                    for digest in map(str, blob_hashes)
                )
                expected_receipt_names.add(
                    receipt_prefix + ".goai-receipt-rehearsal-store"
                )
                actual_receipt_names = {
                    name for name in names if name.startswith(receipt_prefix)
                }
                if actual_receipt_names != expected_receipt_names:
                    errors.append(
                        "bundled receipt files do not exactly match the "
                        "content-addressed receipt index"
                    )
                marker_name = (
                    receipt_prefix + ".goai-receipt-rehearsal-store"
                )
                if marker_name in payloads and payloads[marker_name] != (
                    b"GOAI public development-only receipt rehearsal store\n"
                ):
                    errors.append(
                        "receipt rehearsal store marker content is invalid"
                    )
                if valid_receipt_list and valid_chain_list and valid_blob_list:
                    with tempfile.TemporaryDirectory() as tmp:
                        store = Path(tmp)
                        (store / "blobs").mkdir()
                        for digest in map(str, receipt_hashes):
                            name = receipt_prefix + f"{digest}.json"
                            if name not in payloads:
                                continue
                            data = payloads[name]
                            if sha256(data) != digest:
                                errors.append(
                                    f"receipt rehearsal hash mismatch: {digest}"
                                )
                            (store / f"{digest}.json").write_bytes(data)
                        for digest in map(str, blob_hashes):
                            name = receipt_prefix + f"blobs/{digest}.blob"
                            if name not in payloads:
                                continue
                            data = payloads[name]
                            if sha256(data) != digest:
                                errors.append(
                                    f"receipt evidence blob hash mismatch: {digest}"
                                )
                            (store / "blobs" / f"{digest}.blob").write_bytes(data)
                        for digest in map(str, chain_hashes):
                            chain_errors, report = validate_extension_chain(
                                store,
                                digest,
                            )
                            errors.extend(
                                f"receipt rehearsal {digest}: {error}"
                                for error in chain_errors
                            )
                            recomputed_receipt_reports.append(report)
                            if report.get("status") != "PASS":
                                errors.append(
                                    f"receipt rehearsal chain {digest} is not PASS"
                                )
        if receipt_validation_name in names:
            try:
                receipt_validation = _json_loads(
                    payloads[receipt_validation_name]
                )
            except Exception as exc:
                errors.append(
                    f"invalid receipt rehearsal validation: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                expected_receipt_validation = {
                    "schema": "goai-frontier-receipt-rehearsal-validation/v1",
                    "status": "PASS",
                    "chainCount": 3,
                    "validChainCount": 3,
                    "receiptCount": 34,
                    "blobCount": 60,
                    "reports": recomputed_receipt_reports,
                    "errors": [],
                    "candidateOnly": True,
                    "canClaimAGI": False,
                }
                if receipt_validation != expected_receipt_validation:
                    errors.append(
                        "receipt rehearsal validation report does not exactly "
                        "match recomputed chain validation"
                    )
        receipt_material_valid = len(errors) == receipt_error_start

        receipt_benchmark_name = (
            prefix + "v2/artifacts/receipt-protocol-benchmark.json"
        )
        if receipt_benchmark_name not in names:
            errors.append(
                f"missing required bundle entry: {receipt_benchmark_name}"
            )
        else:
            try:
                receipt_benchmark = _json_loads(
                    payloads[receipt_benchmark_name]
                )
            except Exception as exc:
                errors.append(
                    f"invalid receipt protocol benchmark: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(receipt_benchmark, dict):
                    errors.append(
                        "receipt protocol benchmark must be a JSON object"
                    )
                else:
                    expected_receipt_benchmark = {
                        "status": "PASS",
                        "caseCount": 7,
                        "passedCount": 7,
                        "failedCount": 0,
                        "evidenceClass": "development-only",
                        "confirmatoryEligible": False,
                        "candidateOnly": True,
                        "canClaimAGI": False,
                    }
                    for field, expected in expected_receipt_benchmark.items():
                        if receipt_benchmark.get(field) != expected:
                            errors.append(
                                f"receipt protocol benchmark {field} must be "
                                f"{expected!r}, got "
                                f"{receipt_benchmark.get(field)!r}"
                            )

        protocol_twin_name = prefix + "v2/artifacts/protocol-twin.json"
        protocol_twin_validation_name = (
            prefix + "v2/artifacts/protocol-twin-validation.json"
        )
        protocol_twin_error_start = len(errors)
        protocol_twin_material_valid = False
        protocol_twin: dict = {}
        recomputed_twin_validation: dict = {}
        if protocol_twin_name not in names:
            errors.append(f"missing required bundle entry: {protocol_twin_name}")
        else:
            try:
                protocol_twin = _json_loads(payloads[protocol_twin_name])
            except Exception as exc:
                errors.append(
                    f"invalid protocol twin: {type(exc).__name__}: {exc}"
                )
                protocol_twin = {}
            if isinstance(protocol_twin, dict):
                try:
                    twin_errors, recomputed_twin_validation = (
                        validate_protocol_twin(protocol_twin)
                    )
                except Exception as exc:
                    errors.append(
                        "bundled protocol twin validation raised instead of "
                        f"returning errors: {type(exc).__name__}: {exc}"
                    )
                else:
                    errors.extend(
                        f"bundled protocol twin: {error}"
                        for error in twin_errors
                    )
            else:
                errors.append("bundled protocol twin must be a JSON object")

        if protocol_twin_validation_name not in names:
            errors.append(
                f"missing required bundle entry: {protocol_twin_validation_name}"
            )
        else:
            try:
                twin_validation = _json_loads(
                    payloads[protocol_twin_validation_name]
                )
            except Exception as exc:
                errors.append(
                    f"invalid protocol twin validation: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(twin_validation, dict):
                    errors.append(
                        "protocol twin validation must be a JSON object"
                    )
                elif twin_validation != recomputed_twin_validation:
                    errors.append(
                        "protocol twin validation report does not exactly match "
                        "recomputed protocol validation"
                    )
        protocol_twin_material_valid = (
            len(errors) == protocol_twin_error_start
        )

        study_names = {
            "root": prefix + "v2/artifacts/study-root-v3.json",
            "arms": prefix + "v2/artifacts/study-arm-results.json",
            "ablations": (
                prefix + "v2/artifacts/study-ablation-results.json"
            ),
            "validation": (
                prefix + "v2/artifacts/study-root-v3-validation.json"
            ),
        }
        study_error_start = len(errors)
        study_material_valid = False
        study_payloads: dict[str, dict] = {}
        for label, name in study_names.items():
            if name not in names:
                errors.append(f"missing required bundle entry: {name}")
                continue
            try:
                value = _json_loads(payloads[name])
            except Exception as exc:
                errors.append(
                    f"invalid study {label}: {type(exc).__name__}: {exc}"
                )
                continue
            if not isinstance(value, dict):
                errors.append(f"study {label} must be a JSON object")
                continue
            study_payloads[label] = value
        if "root" in study_payloads:
            errors.extend(
                _study_source_binding_errors(
                    study_payloads["root"],
                    payloads,
                    prefix,
                )
            )
        if (
            set(study_payloads) == set(study_names)
            and isinstance(receipt_index, dict)
            and isinstance(receipt_validation, dict)
            and isinstance(receipt_hashes, list)
            and isinstance(blob_hashes, list)
        ):
            with tempfile.TemporaryDirectory() as tmp:
                store = Path(tmp)
                _materialize_receipt_store(
                    store,
                    payloads,
                    receipt_prefix,
                    receipt_hashes,
                    blob_hashes,
                )
                try:
                    study_issues, recomputed_study_validation = (
                        validate_study_materials(
                            study_payloads["root"],
                            study_payloads["arms"],
                            study_payloads["ablations"],
                            twin=protocol_twin,
                            twin_validation=recomputed_twin_validation,
                            receipt_index=receipt_index,
                            receipt_validation=receipt_validation,
                            receipt_store=store,
                        )
                    )
                except Exception as exc:
                    errors.append(
                        "bundled study root validation raised instead of "
                        f"returning issues: {type(exc).__name__}: {exc}"
                    )
                else:
                    errors.extend(
                        "bundled study root "
                        f"{issue['code']} at {issue['path']}: "
                        f"{issue['message']}"
                        for issue in study_issues
                    )
                    if (
                        study_payloads["validation"]
                        != recomputed_study_validation
                    ):
                        errors.append(
                            "study root validation report does not exactly "
                            "match recomputation"
                        )
        study_material_valid = len(errors) == study_error_start

        study_benchmark_name = (
            prefix + "v2/artifacts/study-root-dag-benchmark.json"
        )
        if study_benchmark_name not in names:
            errors.append(
                f"missing required bundle entry: {study_benchmark_name}"
            )
        else:
            try:
                study_benchmark = _json_loads(
                    payloads[study_benchmark_name]
                )
            except Exception as exc:
                errors.append(
                    "invalid study root DAG benchmark: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(study_benchmark, dict):
                    errors.append(
                        "study root DAG benchmark must be a JSON object"
                    )
                elif (
                    receipt_material_valid
                    and protocol_twin_material_valid
                    and study_material_valid
                    and isinstance(protocol_twin, dict)
                    and isinstance(recomputed_twin_validation, dict)
                    and isinstance(receipt_index, dict)
                    and isinstance(receipt_validation, dict)
                    and isinstance(receipt_hashes, list)
                    and isinstance(blob_hashes, list)
                ):
                    cache_key = (
                        sha256(payloads[protocol_twin_name]),
                        sha256(
                            payloads[protocol_twin_validation_name]
                        ),
                        sha256(payloads[receipt_index_name]),
                        sha256(payloads[receipt_validation_name]),
                        _study_source_material_sha256(
                            payloads,
                            prefix,
                        ),
                    )
                    cached_benchmark = _STUDY_BENCHMARK_CACHE.get(
                        cache_key
                    )
                    if cached_benchmark is None:
                        with tempfile.TemporaryDirectory() as tmp:
                            store = Path(tmp)
                            _materialize_receipt_store(
                                store,
                                payloads,
                                receipt_prefix,
                                receipt_hashes,
                                blob_hashes,
                            )
                            try:
                                (
                                    benchmark_errors,
                                    recomputed_benchmark,
                                ) = run_benchmark(
                                    twin=protocol_twin,
                                    twin_validation=(
                                        recomputed_twin_validation
                                    ),
                                    receipt_index=receipt_index,
                                    receipt_validation=receipt_validation,
                                    receipt_store=store,
                                )
                            except Exception as exc:
                                errors.append(
                                    "study root DAG benchmark recomputation "
                                    "raised instead of returning errors: "
                                    f"{type(exc).__name__}: {exc}"
                                )
                            else:
                                cached_benchmark = (
                                    tuple(benchmark_errors),
                                    recomputed_benchmark,
                                )
                                _STUDY_BENCHMARK_CACHE[cache_key] = (
                                    cached_benchmark
                                )
                    if cached_benchmark is not None:
                        benchmark_errors, recomputed_benchmark = (
                            cached_benchmark
                        )
                        errors.extend(
                            "recomputed study root DAG benchmark: "
                            f"{error}"
                            for error in benchmark_errors
                        )
                        if study_benchmark != recomputed_benchmark:
                            errors.append(
                                "study root DAG benchmark does not "
                                "exactly match recomputation"
                            )

        scorer_simulation_name = (
            prefix
            + "v2/artifacts/scorer-operating-characteristics.json"
        )
        if scorer_simulation_name not in names:
            errors.append(
                f"missing required bundle entry: {scorer_simulation_name}"
            )
        else:
            try:
                scorer_simulation = _json_loads(
                    payloads[scorer_simulation_name]
                )
            except Exception as exc:
                errors.append(
                    "invalid scorer operating characteristics: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if not isinstance(scorer_simulation, dict):
                    errors.append(
                        "scorer operating characteristics must be a JSON object"
                    )
                else:
                    try:
                        (
                            simulation_errors,
                            recomputed_simulation,
                        ) = _recomputed_scorer_simulation()
                    except Exception as exc:
                        errors.append(
                            "scorer operating-characteristic recomputation "
                            "raised instead of returning errors: "
                            f"{type(exc).__name__}: {exc}"
                        )
                    else:
                        errors.extend(
                            "recomputed scorer operating characteristics: "
                            f"{error}"
                            for error in simulation_errors
                        )
                        if scorer_simulation != recomputed_simulation:
                            errors.append(
                                "scorer operating characteristics do not "
                                "exactly match recomputation"
                            )

        health_name = prefix + "hosted-demo/healthcheck.public-report.json"
        if health_name not in names:
            errors.append(f"missing required bundle entry: {health_name}")
        else:
            try:
                health = _json_loads(payloads[health_name])
            except Exception as exc:
                errors.append(f"invalid hosted-demo healthcheck: {type(exc).__name__}: {exc}")
            else:
                if not isinstance(health, dict):
                    errors.append(
                        "hosted-demo healthcheck must be a JSON object"
                    )
                else:
                    if health.get("status") != "PASS":
                        errors.append("hosted-demo healthcheck status must be PASS")
                    if (
                        health.get("networkCalls") != 0
                        or health.get("modelCalls") != 0
                    ):
                        errors.append(
                            "hosted-demo healthcheck must be provider-free"
                        )
                    if health.get("candidateOnly") is not True:
                        errors.append("hosted-demo candidateOnly must be true")
                    if health.get("canClaimAGI") is not False:
                        errors.append("hosted-demo canClaimAGI must be false")

        for language in ("ZH", "EN"):
            pdf_name = prefix + f"submission/GOAI-AI4R-Open-Exploration-{language}.pdf"
            if pdf_name not in names:
                errors.append(f"missing required bundle entry: {pdf_name}")
                continue
            try:
                reader = PdfReader(io.BytesIO(payloads[pdf_name]))
                pages = len(reader.pages)
                metadata = reader.metadata or {}
            except Exception as exc:
                errors.append(f"{pdf_name}: invalid PDF: {type(exc).__name__}: {exc}")
                continue
            if pages != 4:
                errors.append(f"{pdf_name}: expected 4 pages, got {pages}")
            for field in ("/CreationDate", "/ModDate"):
                if metadata.get(field) != INVARIANT_PDF_DATE:
                    errors.append(
                        f"{pdf_name}: expected invariant {field}="
                        f"{INVARIANT_PDF_DATE!r}, got {metadata.get(field)!r}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "bundle",
        type=Path,
        nargs="?",
        default=Path("dist/GOAI-AI4R-Open-Exploration.zip"),
    )
    args = parser.parse_args()
    errors = validate(args.bundle)
    if errors:
        print("BUNDLE VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("BUNDLE VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
