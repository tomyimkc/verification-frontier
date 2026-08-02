#!/usr/bin/env python3
"""Build a deterministic, upload-ready GOAI source bundle."""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUNDLE = DIST / "GOAI-AI4R-Open-Exploration.zip"
CHECKSUM = DIST / "GOAI-AI4R-Open-Exploration.zip.sha256"
FIXED_TIME = (2026, 7, 31, 0, 0, 0)
BUNDLE_TRANSACTION_SCHEMA = "goai-bundle-publication-transaction/v1"
BUNDLE_GARBAGE_SCHEMA = "goai-bundle-garbage-owner/v1"

REQUIRED = {
    "README.md",
    "PROJECT.md",
    "OFFICIAL-RULES-CHECK.md",
    "RELATED-WORK.md",
    "EXECUTIVE-SUMMARY.md",
    "JUDGING-CROSSWALK.md",
    "EVIDENCE-TO-CLAIM-MATRIX.md",
    "ARCHITECTURE.md",
    "FAILURE-SHOWCASE.md",
    "REPRODUCIBILITY-QUICKSTART.md",
    "RESEARCH-POSITION.md",
    "CORE-CONSTRAINTS-COMPLIANCE.md",
    "LICENSE",
    "demo.py",
    "units.py",
    "test_demo.py",
    "build_bundle.py",
    "verify_bundle.py",
    "verify_artifacts.py",
    "requirements.txt",
    "requirements-docs.txt",
    "requirements-models.txt",
    "requirements-stage-a-gpu.txt",
    ".dockerignore",
    "run_all.sh",
    "artifacts/episodes.jsonl",
    "artifacts/benchmark-summary.json",
    "evidence/ladder-summary.json",
    "submission/submission-zh.md",
    "submission/submission-en.md",
    "submission/submission-metadata.json",
    "submission/problem-definition-zh.md",
    "submission/pdf_contract.py",
    "submission/build_pdfs.py",
    "submission/GOAI-AI4R-Open-Exploration-ZH.pdf",
    "submission/GOAI-AI4R-Open-Exploration-EN.pdf",
    "hosted-demo/README.md",
    "hosted-demo/Dockerfile",
    "hosted-demo/app.py",
    "hosted-demo/demo_logic.py",
    "hosted-demo/healthcheck.py",
    "hosted-demo/healthcheck.public-report.json",
    "hosted-demo/requirements.txt",
    "hosted-demo/test_demo_logic.py",
    "v2/README.md",
    "v2/__init__.py",
    "v2/PREREGISTRATION.md",
    "v2/FRONTIER-EXPANSION-SPEC.md",
    "v2/PROTOCOL-TWIN-SPEC.md",
    "v2/STUDY-ROOT-V3-SPEC.md",
    "v2/NEXT-GATES-SPEC.md",
    "v2/HUMAN-GATE-RUBRIC.md",
    "v2/DEVELOPMENT-FAILURES.md",
    "v2/EXPERT-VALIDATION.md",
    "v2/EXPERT-POSTBUILD-AUDIT.md",
    "v2/EXPERT-READINESS-AUDIT.md",
    "v2/EXPERT-CORRECTNESS-AUDIT.md",
    "v2/EXPERT-STAGE-A-AUDIT.md",
    "v2/frontier.py",
    "v2/lean_verify.py",
    "v2/build_task_manifest.py",
    "v2/confirmatory_scoring.py",
    "v2/protocol_twin.py",
    "v2/study_root.py",
    "v2/stage_a.py",
    "v2/stage_a_model.py",
    "v2/stage_a_pro6000.py",
    "v2/build_stage_a_result.py",
    "v2/build_logic_error_audit.py",
    "v2/build_baseline_comparison.py",
    "v2/self_correct.py",
    "v2/error_rag.py",
    "v2/verify_provenance.py",
    "v2/verify_ill_posed.py",
    "v2/ill_posed_tasks.py",
    "v2/build_ill_posed_audit.py",
    "v2/benchmark_study_root.py",
    "v2/simulate_scorer.py",
    "v2/receipt_protocol.py",
    "v2/build_receipt_rehearsal.py",
    "v2/benchmark_receipt_protocol.py",
    "v2/run_model_attempts.py",
    "v2/score_confirmatory.py",
    "v2/validate_task_manifest.py",
    "v2/test_frontier.py",
    "v2/test_lean_verify.py",
    "v2/test_protocol_twin.py",
    "v2/test_study_root.py",
    "v2/test_benchmark_study_root.py",
    "v2/test_simulate_scorer.py",
    "v2/test_stage_a.py",
    "v2/test_stage_a_model.py",
    "v2/test_stage_a_pro6000.py",
    "v2/test_stage_a_result.py",
    "v2/test_logic_error_audit.py",
    "v2/test_verify_provenance.py",
    "v2/test_baseline_comparison.py",
    "v2/test_self_correct.py",
    "v2/test_error_rag.py",
    "v2/test_verify_ill_posed.py",
    "v2/test_ill_posed_tasks.py",
    "v2/test_ill_posed_audit.py",
    "v2/test_run_model_attempts.py",
    "v2/test_receipt_protocol.py",
    "v2/test_score_confirmatory.py",
    "v2/test_task_manifest.py",
    "v2/test_validate_task_manifest.py",
    "v2/artifacts/synthetic-rehearsal-seal.manifest.json",
    "v2/artifacts/synthetic-rehearsal-validation.json",
    "v2/artifacts/task-manifest.jsonl",
    "v2/artifacts/task-manifest-summary.json",
    "v2/artifacts/task-validation.json",
    "v2/artifacts/receipt-rehearsal-index.json",
    "v2/artifacts/receipt-rehearsal-validation.json",
    "v2/artifacts/receipt-protocol-benchmark.json",
    "v2/artifacts/protocol-twin.json",
    "v2/artifacts/protocol-twin-validation.json",
    "v2/artifacts/study-arm-results.json",
    "v2/artifacts/study-ablation-results.json",
    "v2/artifacts/study-root-v3.json",
    "v2/artifacts/study-root-v3-validation.json",
    "v2/artifacts/study-root-dag-benchmark.json",
    "v2/artifacts/scorer-operating-characteristics.json",
    "v2/artifacts/stage-a-manifest.json",
    "v2/artifacts/stage-a-readiness.json",
    "v2/artifacts/stage-a-development-result.json",
    "v2/artifacts/logic-error-catch-rate.json",
    "v2/artifacts/baseline-comparison.json",
    "v2/artifacts/self-correction-audit.json",
    "v2/artifacts/error-rag-audit.json",
    "v2/artifacts/ill-posed-tasks.json",
    "v2/artifacts/ill-posed-audit.json",
}


def archive_name(path: Path) -> str:
    return f"goai-ai4r-open-exploration/{path.relative_to(ROOT).as_posix()}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = stat.S_IFREG | (0o755 if executable else 0o644)
    info.external_attr = mode << 16
    info.create_system = 3
    return info


def canonical_bundle_bytes(payloads: dict[str, bytes]) -> bytes:
    """Return the one allowed deterministic ZIP representation."""
    manifest_name = "MANIFEST.sha256"
    if manifest_name not in payloads:
        raise ValueError("canonical bundle payloads require MANIFEST.sha256")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for relative in sorted(
            name for name in payloads if name != manifest_name
        ):
            executable = Path(relative).suffix in {".py", ".sh"}
            archive.writestr(
                zip_info(
                    f"goai-ai4r-open-exploration/{relative}",
                    executable,
                ),
                payloads[relative],
            )
        archive.writestr(
            zip_info(
                "goai-ai4r-open-exploration/MANIFEST.sha256"
            ),
            payloads[manifest_name],
        )
    return output.getvalue()


def _open_stable_output_directory(
    path: Path,
    label: str,
) -> tuple[int, tuple[int, int]]:
    try:
        initial = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} directory does not exist: {path}") from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISDIR(initial.st_mode):
        raise ValueError(f"{label} directory is unsafe: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or identity != (initial.st_dev, initial.st_ino)
        ):
            raise ValueError(f"{label} directory changed during publication")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, identity


def _assert_output_directory_identity(
    path: Path,
    descriptor: int,
    identity: tuple[int, int],
    label: str,
) -> None:
    opened = os.fstat(descriptor)
    try:
        current = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(
            f"{label} directory changed during publication"
        ) from exc
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != identity
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != identity
    ):
        raise ValueError(f"{label} directory changed during publication")


def _write_staged_file(
    path: Path,
    data: bytes,
    *,
    directory_descriptor: int | None = None,
    directory_identity: tuple[int, int] | None = None,
) -> None:
    own_directory_descriptor = directory_descriptor is None
    if directory_descriptor is None:
        directory_descriptor, directory_identity = (
            _open_stable_output_directory(
                path.parent,
                "bundle staging output",
            )
        )
    assert directory_descriptor is not None
    assert directory_identity is not None
    descriptor = -1
    created = False
    try:
        _assert_output_directory_identity(
            path.parent,
            directory_descriptor,
            directory_identity,
            "bundle staging output",
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(
            path.name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        created = True
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _assert_output_directory_identity(
            path.parent,
            directory_descriptor,
            directory_identity,
            "bundle staging output",
        )
        os.fsync(directory_descriptor)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        if created and directory_descriptor >= 0:
            try:
                os.unlink(path.name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass  # A racing cleanup already removed the staged file.
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if own_directory_descriptor:
            os.close(directory_descriptor)


def _bundle_lock_path() -> Path:
    identity = hashlib.sha256(
        str(DIST.resolve(strict=False)).encode("utf-8")
    ).hexdigest()
    return Path(tempfile.gettempdir()).resolve() / (
        f"goai-bundle-publication-{identity}.lock"
    )


def _acquire_bundle_lock() -> int:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(_bundle_lock_path(), flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _validate_dist_directory(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"bundle output directory is unsafe: {path}")
    expected = {BUNDLE.name, CHECKSUM.name}
    observed = {entry.name for entry in path.iterdir()}
    if observed != expected:
        raise ValueError(
            "bundle output directory contains unexpected entries: "
            f"{sorted(observed - expected)}"
        )
    for entry in path.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise ValueError(f"bundle output is not a regular file: {entry}")


def _validate_dist_directory_at(
    parent_descriptor: int,
    name: str,
    *,
    allow_missing: bool = True,
) -> bool:
    try:
        metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        if allow_missing:
            return False
        raise ValueError(f"bundle output directory is missing: {name}")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"bundle output directory is unsafe: {name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(
        name,
        flags,
        dir_fd=parent_descriptor,
    )
    try:
        expected = {BUNDLE.name, CHECKSUM.name}
        observed = set(os.listdir(descriptor))
        if observed != expected:
            raise ValueError(
                "bundle output directory contains unexpected entries: "
                f"{sorted(observed - expected)}"
            )
        for entry in sorted(observed):
            entry_metadata = os.stat(
                entry,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(entry_metadata.st_mode):
                raise ValueError(
                    f"bundle output is not a regular file: {name}/{entry}"
                )
    finally:
        os.close(descriptor)
    return True


def _bundle_transaction_name() -> str:
    return f".{DIST.name}.publication-transaction.json"


def _entry_exists_at(parent_descriptor: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _read_regular_file_at(
    directory_descriptor: int,
    name: str,
    label: str,
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} is not a regular file: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _bundle_directory_fingerprint_at(
    parent_descriptor: int,
    name: str,
) -> dict[str, str] | None:
    if not _validate_dist_directory_at(parent_descriptor, name):
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    try:
        return {
            "bundleSha256": sha256(
                _read_regular_file_at(
                    descriptor,
                    BUNDLE.name,
                    "bundle publication archive",
                )
            ),
            "checksumSha256": sha256(
                _read_regular_file_at(
                    descriptor,
                    CHECKSUM.name,
                    "bundle publication checksum",
                )
            ),
        }
    finally:
        os.close(descriptor)


def _canonical_transaction_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_bundle_transaction_at(
    parent_descriptor: int,
    payload: dict,
) -> None:
    data = _canonical_transaction_bytes(payload)
    journal_name = _bundle_transaction_name()
    temporary_name = f".{journal_name}-{uuid.uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary_name,
            journal_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_exists = False
        os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass


def _load_bundle_transaction_at(
    parent_descriptor: int,
) -> dict | None:
    journal_name = _bundle_transaction_name()
    if not _entry_exists_at(parent_descriptor, journal_name):
        return None
    try:
        data = _read_regular_file_at(
            parent_descriptor,
            journal_name,
            "bundle publication transaction",
        )
    except OSError as exc:
        raise ValueError("bundle publication transaction is unsafe") from exc
    if len(data) > 64 * 1024:
        raise ValueError("bundle publication transaction is oversized")
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("bundle publication transaction is invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or _canonical_transaction_bytes(payload) != data
        or payload.get("schema") != BUNDLE_TRANSACTION_SCHEMA
        or payload.get("phase") not in {"prepared", "committed"}
        or not isinstance(payload.get("nonce"), str)
        or not re.fullmatch(r"[0-9a-f]{32}", payload["nonce"])
        or not isinstance(payload.get("hadPrevious"), bool)
        or not isinstance(payload.get("stagedName"), str)
        or not re.fullmatch(
            rf"\.{re.escape(DIST.name)}\.generation-[0-9a-f]{{32}}",
            payload["stagedName"],
        )
        or not isinstance(payload.get("newFingerprint"), dict)
        or set(payload["newFingerprint"]) != {
            "bundleSha256",
            "checksumSha256",
        }
        or not all(
            re.fullmatch(r"[0-9a-f]{64}", str(value))
            for value in payload["newFingerprint"].values()
        )
    ):
        raise ValueError("bundle publication transaction is invalid")
    old_fingerprint = payload.get("oldFingerprint")
    if payload["hadPrevious"]:
        if (
            not isinstance(old_fingerprint, dict)
            or set(old_fingerprint) != {
                "bundleSha256",
                "checksumSha256",
            }
            or not all(
                re.fullmatch(r"[0-9a-f]{64}", str(value))
                for value in old_fingerprint.values()
            )
        ):
            raise ValueError(
                "bundle publication transaction old fingerprint is invalid"
            )
    elif old_fingerprint is not None:
        raise ValueError(
            "bundle publication transaction unexpectedly records an old pair"
        )
    return payload


def _remove_bundle_transaction_at(parent_descriptor: int) -> None:
    os.unlink(_bundle_transaction_name(), dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)


def _bundle_garbage_name(nonce: str) -> str:
    return f".{DIST.name}.garbage-{nonce}"


def _bundle_garbage_owner_name(nonce: str) -> str:
    return f"{_bundle_garbage_name(nonce)}.owner.json"


def _bundle_garbage_payload(staged_name: str, nonce: str) -> dict:
    return {
        "schema": BUNDLE_GARBAGE_SCHEMA,
        "nonce": nonce,
        "sourceName": staged_name,
        "garbageName": _bundle_garbage_name(nonce),
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def _write_bundle_garbage_owner_at(
    parent_descriptor: int,
    staged_name: str,
    nonce: str,
) -> None:
    payload = _bundle_garbage_payload(staged_name, nonce)
    data = _canonical_transaction_bytes(payload)
    owner_name = _bundle_garbage_owner_name(nonce)
    try:
        existing = _read_regular_file_at(
            parent_descriptor,
            owner_name,
            "bundle garbage owner",
        )
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing != data:
            raise ValueError("bundle garbage owner manifest mismatch")
        return
    temporary_name = f".{owner_name}-{uuid.uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(
                temporary_name,
                owner_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing = _read_regular_file_at(
                parent_descriptor,
                owner_name,
                "bundle garbage owner",
            )
            if existing != data:
                raise ValueError("bundle garbage owner manifest mismatch")
        os.unlink(temporary_name, dir_fd=parent_descriptor)
        temporary_exists = False
        os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass


def _load_bundle_garbage_owner_at(
    parent_descriptor: int,
    owner_name: str,
) -> dict | None:
    try:
        data = _read_regular_file_at(
            parent_descriptor,
            owner_name,
            "bundle garbage owner",
        )
    except (FileNotFoundError, OSError, ValueError):
        return None
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    nonce = str(payload.get("nonce") or "")
    if (
        _canonical_transaction_bytes(payload) != data
        or payload.get("schema") != BUNDLE_GARBAGE_SCHEMA
        or not re.fullmatch(r"[0-9a-f]{32}", nonce)
        or owner_name != _bundle_garbage_owner_name(nonce)
        or payload.get("garbageName") != _bundle_garbage_name(nonce)
        or not isinstance(payload.get("sourceName"), str)
        or not re.fullmatch(
            rf"\.{re.escape(DIST.name)}\.generation-[0-9a-f]{{32}}",
            payload["sourceName"],
        )
        or payload.get("candidateOnly") is not True
        or payload.get("canClaimAGI") is not False
    ):
        return None
    return payload


def _quarantine_bundle_backup_at(
    parent_descriptor: int,
    staged_name: str,
    nonce: str,
) -> str | None:
    garbage_name = _bundle_garbage_name(nonce)
    try:
        metadata = os.stat(
            staged_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return garbage_name if _entry_exists_at(
            parent_descriptor,
            garbage_name,
        ) else None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return None
    if _entry_exists_at(parent_descriptor, garbage_name):
        return garbage_name
    _write_bundle_garbage_owner_at(
        parent_descriptor,
        staged_name,
        nonce,
    )
    os.replace(
        staged_name,
        garbage_name,
        src_dir_fd=parent_descriptor,
        dst_dir_fd=parent_descriptor,
    )
    os.fsync(parent_descriptor)
    return garbage_name


def _cleanup_bundle_garbage_at(parent_descriptor: int) -> None:
    owner_pattern = re.compile(
        rf"^\.{re.escape(DIST.name)}\.garbage-[0-9a-f]{{32}}"
        r"\.owner\.json$"
    )
    for owner_name in os.listdir(parent_descriptor):
        if not owner_pattern.fullmatch(owner_name):
            continue
        payload = _load_bundle_garbage_owner_at(
            parent_descriptor,
            owner_name,
        )
        if payload is None:
            continue
        garbage_name = payload["garbageName"]
        try:
            metadata = os.stat(
                garbage_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(
                metadata.st_mode
            ):
                shutil.rmtree(garbage_name, dir_fd=parent_descriptor)
            else:
                continue
            os.fsync(parent_descriptor)
        except FileNotFoundError:
            pass  # The quarantined directory was already collected.
        except OSError:
            continue
        try:
            os.unlink(owner_name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        except FileNotFoundError:
            pass  # The owner manifest was already finalized.


def _recover_bundle_publication_transaction(
    parent_descriptor: int,
    *,
    force_phase: str | None = None,
) -> None:
    payload = _load_bundle_transaction_at(parent_descriptor)
    if payload is None:
        _cleanup_bundle_garbage_at(parent_descriptor)
        return
    staged_name = payload["stagedName"]
    old_fingerprint = payload["oldFingerprint"]
    new_fingerprint = payload["newFingerprint"]
    current = _bundle_directory_fingerprint_at(
        parent_descriptor,
        DIST.name,
    )
    phase = force_phase or payload["phase"]
    if phase not in {"prepared", "committed"}:
        raise ValueError("invalid forced bundle transaction recovery phase")
    if phase == "prepared":
        if payload["hadPrevious"]:
            if current == new_fingerprint:
                staged = _bundle_directory_fingerprint_at(
                    parent_descriptor,
                    staged_name,
                )
                if staged != old_fingerprint:
                    raise ValueError(
                        "cannot safely recover prepared bundle publication"
                    )
                _exchange_directories(
                    parent_descriptor,
                    DIST.name,
                    staged_name,
                )
                os.fsync(parent_descriptor)
                current = old_fingerprint
            if current != old_fingerprint:
                raise ValueError(
                    "cannot safely recover prepared bundle publication"
                )
        else:
            if current == new_fingerprint:
                if _entry_exists_at(parent_descriptor, staged_name):
                    raise ValueError(
                        "cannot safely recover prepared first bundle publication"
                    )
                os.replace(
                    DIST.name,
                    staged_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
                os.fsync(parent_descriptor)
                current = None
            if current is not None:
                raise ValueError(
                    "cannot safely recover prepared first bundle publication"
                )
        _quarantine_bundle_backup_at(
            parent_descriptor,
            staged_name,
            payload["nonce"],
        )
        _remove_bundle_transaction_at(parent_descriptor)
        _cleanup_bundle_garbage_at(parent_descriptor)
        return

    if current != new_fingerprint:
        raise ValueError("committed bundle publication fingerprint mismatch")
    _quarantine_bundle_backup_at(
        parent_descriptor,
        staged_name,
        payload["nonce"],
    )
    _remove_bundle_transaction_at(parent_descriptor)
    _cleanup_bundle_garbage_at(parent_descriptor)


def _exchange_directories(
    directory_descriptor: int,
    left_name: str,
    right_name: str,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    left_bytes = os.fsencode(left_name)
    right_bytes = os.fsencode(right_name)
    if sys.platform == "darwin" and hasattr(library, "renameatx_np"):
        result = library.renameatx_np(
            directory_descriptor,
            left_bytes,
            directory_descriptor,
            right_bytes,
            0x00000002,
        )
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        result = library.renameat2(
            directory_descriptor,
            left_bytes,
            directory_descriptor,
            right_bytes,
            0x00000002,
        )
    else:
        raise RuntimeError(
            "atomic directory exchange is unavailable on this platform"
        )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            f"{left_name} <-> {right_name}",
        )


def _publish_bundle_directory(
    staged_directory: Path,
    *,
    parent_descriptor: int | None = None,
    parent_identity: tuple[int, int] | None = None,
) -> None:
    if staged_directory.parent != DIST.parent:
        raise ValueError(
            "bundle staging and output directories must share one parent"
        )
    own_parent_descriptor = parent_descriptor is None
    if parent_descriptor is None:
        parent_descriptor, parent_identity = _open_stable_output_directory(
            DIST.parent,
            "bundle publication parent",
        )
    assert parent_descriptor is not None
    assert parent_identity is not None
    try:
        _recover_bundle_publication_transaction(parent_descriptor)
        _assert_output_directory_identity(
            DIST.parent,
            parent_descriptor,
            parent_identity,
            "bundle publication parent",
        )
        _validate_dist_directory_at(
            parent_descriptor,
            staged_directory.name,
            allow_missing=False,
        )
        dist_exists = _validate_dist_directory_at(
            parent_descriptor,
            DIST.name,
        )
        old_fingerprint = _bundle_directory_fingerprint_at(
            parent_descriptor,
            DIST.name,
        )
        new_fingerprint = _bundle_directory_fingerprint_at(
            parent_descriptor,
            staged_directory.name,
        )
        assert new_fingerprint is not None
        transaction = {
            "schema": BUNDLE_TRANSACTION_SCHEMA,
            "phase": "prepared",
            "nonce": uuid.uuid4().hex,
            "hadPrevious": dist_exists,
            "stagedName": staged_directory.name,
            "oldFingerprint": old_fingerprint,
            "newFingerprint": new_fingerprint,
        }
        _write_bundle_transaction_at(parent_descriptor, transaction)
        try:
            if dist_exists:
                _exchange_directories(
                    parent_descriptor,
                    DIST.name,
                    staged_directory.name,
                )
            else:
                os.replace(
                    staged_directory.name,
                    DIST.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
            os.fsync(parent_descriptor)
            _assert_output_directory_identity(
                DIST.parent,
                parent_descriptor,
                parent_identity,
                "bundle publication parent",
            )
            transaction["phase"] = "committed"
            _write_bundle_transaction_at(parent_descriptor, transaction)
        except BaseException:
            _recover_bundle_publication_transaction(
                parent_descriptor,
                force_phase="prepared",
            )
            raise

        _recover_bundle_publication_transaction(parent_descriptor)
        _assert_output_directory_identity(
            DIST.parent,
            parent_descriptor,
            parent_identity,
            "bundle publication parent",
        )
    finally:
        if own_parent_descriptor:
            os.close(parent_descriptor)


def validated_source_file(relative: str) -> tuple[Path, bytes, int]:
    """Open and read one required source without following path redirects."""
    relative_path = PurePosixPath(relative)
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or not relative_path.parts
    ):
        raise ValueError(f"required source path is unsafe: {relative}")
    path = ROOT / relative
    directory_paths = [ROOT]
    current_path = ROOT
    for part in relative_path.parts[:-1]:
        current_path /= part
        directory_paths.append(current_path)
    directory_metadata: list[os.stat_result] = []
    for directory_path in directory_paths:
        try:
            value = directory_path.lstat()
        except FileNotFoundError as exc:
            raise ValueError(
                f"missing required source directory: {directory_path}"
            ) from exc
        if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
            raise ValueError(
                f"required source directory is unsafe: {directory_path}"
            )
        directory_metadata.append(value)
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {relative}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"required source file must not be a symlink: {relative}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"required source file is not regular: {relative}")
    root = ROOT.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"required source file escapes package root: {relative}")
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    file_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW
    current_fd = -1
    file_fd = -1
    try:
        current_fd = os.open(ROOT, directory_flags)
        opened_root = os.fstat(current_fd)
        if (
            opened_root.st_dev,
            opened_root.st_ino,
        ) != (
            directory_metadata[0].st_dev,
            directory_metadata[0].st_ino,
        ):
            raise ValueError("package root changed during bundle build")
        for index, part in enumerate(relative_path.parts[:-1], start=1):
            next_fd = -1
            try:
                next_fd = os.open(
                    part,
                    directory_flags,
                    dir_fd=current_fd,
                )
                opened_directory = os.fstat(next_fd)
                if (
                    opened_directory.st_dev,
                    opened_directory.st_ino,
                ) != (
                    directory_metadata[index].st_dev,
                    directory_metadata[index].st_ino,
                ):
                    raise ValueError(
                        "required source directory changed during bundle build: "
                        f"{directory_paths[index]}"
                    )
            except BaseException:
                if next_fd >= 0:
                    os.close(next_fd)
                raise
            previous_fd = current_fd
            current_fd = next_fd
            os.close(previous_fd)
        file_fd = os.open(
            relative_path.parts[-1],
            file_flags,
            dir_fd=current_fd,
        )
        opened_metadata = os.fstat(file_fd)
        if not stat.S_ISREG(opened_metadata.st_mode):
            raise ValueError(
                f"required source file is not regular: {relative}"
            )
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )

        def metadata_identity(value: os.stat_result) -> tuple[int, ...]:
            return tuple(int(getattr(value, field)) for field in stable_fields)

        def read_all() -> bytes:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)

        first_read = read_all()
        after_first_read = os.fstat(file_fd)
        os.lseek(file_fd, 0, os.SEEK_SET)
        second_read = read_all()
        after_second_read = os.fstat(file_fd)
        if (
            metadata_identity(opened_metadata)
            != metadata_identity(after_first_read)
            or metadata_identity(opened_metadata)
            != metadata_identity(after_second_read)
            or first_read != second_read
        ):
            raise ValueError(
                "required source changed during bundle read: "
                f"{relative}"
            )
        final_metadata = path.lstat()
        if (
            not stat.S_ISREG(final_metadata.st_mode)
            or metadata_identity(final_metadata)
            != metadata_identity(opened_metadata)
        ):
            raise ValueError(
                "required source changed during bundle build: "
                f"{relative}"
            )
        final_resolved = path.resolve(strict=True)
        if final_resolved != root and root not in final_resolved.parents:
            raise ValueError(
                f"required source file escapes package root: {relative}"
            )
        for directory_path, initial_value in zip(
            directory_paths,
            directory_metadata,
        ):
            final_value = directory_path.lstat()
            if (
                stat.S_ISLNK(final_value.st_mode)
                or not stat.S_ISDIR(final_value.st_mode)
                or (final_value.st_dev, final_value.st_ino)
                != (initial_value.st_dev, initial_value.st_ino)
            ):
                raise ValueError(
                    "required source directory changed during bundle build: "
                    f"{directory_path}"
                )
        return path, first_read, opened_metadata.st_mode
    except OSError as exc:
        raise ValueError(
            f"unable to safely open required source file {relative}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if current_fd >= 0:
            os.close(current_fd)


def receipt_rehearsal_files() -> set[str]:
    """Resolve the public receipt allowlist from its content-addressed index."""
    index_path = ROOT / "v2/artifacts/receipt-rehearsal-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"cannot build bundle; invalid receipt rehearsal index: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(index, dict):
        raise SystemExit("cannot build bundle; receipt rehearsal index is not an object")
    expected = {
        "status": "PASS",
        "evidenceClass": "development-only",
        "confirmatoryEligible": False,
        "receiptCount": 34,
        "blobCount": 60,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    for field, value in expected.items():
        if index.get(field) != value:
            raise SystemExit(
                f"cannot build bundle; receipt rehearsal index {field} must be "
                f"{value!r}, got {index.get(field)!r}"
            )
    digests = index.get("receiptSha256s")
    chains = index.get("chainSha256s")
    if (
        not isinstance(digests, list)
        or len(digests) != 34
        or len(set(map(str, digests))) != 34
        or not all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in digests)
    ):
        raise SystemExit(
            "cannot build bundle; receipt rehearsal index must explicitly list "
            "34 distinct SHA-256 receipts"
        )
    if (
        not isinstance(chains, list)
        or len(chains) != 3
        or len(set(map(str, chains))) != 3
        or not set(map(str, chains)).issubset(set(map(str, digests)))
    ):
        raise SystemExit(
            "cannot build bundle; receipt rehearsal index must list three "
            "content-addressed chains"
        )
    blobs = index.get("blobSha256s")
    if (
        not isinstance(blobs, list)
        or len(blobs) != 60
        or len(set(map(str, blobs))) != 60
        or not all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in blobs)
    ):
        raise SystemExit(
            "cannot build bundle; receipt rehearsal index must explicitly list "
            "60 distinct evidence blobs"
        )
    files = {
        f"v2/artifacts/receipt-rehearsal/{digest}.json"
        for digest in map(str, digests)
    }
    files.update(
        f"v2/artifacts/receipt-rehearsal/blobs/{digest}.blob"
        for digest in map(str, blobs)
    )
    files.add(
        "v2/artifacts/receipt-rehearsal/"
        ".goai-receipt-rehearsal-store"
    )
    return files


def main() -> int:
    required = set(REQUIRED)
    required.update(receipt_rehearsal_files())
    files: list[tuple[Path, bytes, int]] = []
    source_errors: list[str] = []
    for relative in sorted(required):
        try:
            files.append(validated_source_file(relative))
        except (OSError, ValueError) as exc:
            source_errors.append(str(exc))
    if source_errors:
        raise SystemExit(
            "cannot build bundle; unsafe or missing required files: "
            + "; ".join(source_errors)
        )

    manifest_rows: list[str] = []
    payloads: dict[str, bytes] = {}
    for path, data, mode in files:
        relative = path.relative_to(ROOT).as_posix()
        payloads[relative] = data
        manifest_rows.append(f"{sha256(data)}  {relative}")
    manifest = ("\n".join(manifest_rows) + "\n").encode("utf-8")
    payloads["MANIFEST.sha256"] = manifest
    bundle_bytes = canonical_bundle_bytes(payloads)
    digest = sha256(bundle_bytes)
    checksum_bytes = f"{digest}  {BUNDLE.name}\n".encode("utf-8")

    DIST.parent.mkdir(parents=True, exist_ok=True)
    lock_descriptor = _acquire_bundle_lock()
    parent_descriptor = -1
    staged_descriptor = -1
    staged_name = f".{DIST.name}.generation-{uuid.uuid4().hex}"
    staged_directory = DIST.parent / staged_name
    staged_created = False
    try:
        parent_descriptor, parent_identity = _open_stable_output_directory(
            DIST.parent,
            "bundle publication parent",
        )
        _recover_bundle_publication_transaction(parent_descriptor)
        os.mkdir(staged_name, 0o700, dir_fd=parent_descriptor)
        staged_created = True
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        staged_descriptor = os.open(
            staged_name,
            directory_flags,
            dir_fd=parent_descriptor,
        )
        staged_metadata = os.fstat(staged_descriptor)
        staged_identity = (
            staged_metadata.st_dev,
            staged_metadata.st_ino,
        )
        _assert_output_directory_identity(
            DIST.parent,
            parent_descriptor,
            parent_identity,
            "bundle publication parent",
        )
        _assert_output_directory_identity(
            staged_directory,
            staged_descriptor,
            staged_identity,
            "bundle staging directory",
        )
        staged_bundle = staged_directory / BUNDLE.name
        staged_checksum = staged_directory / CHECKSUM.name
        _write_staged_file(
            staged_bundle,
            bundle_bytes,
            directory_descriptor=staged_descriptor,
            directory_identity=staged_identity,
        )
        _write_staged_file(
            staged_checksum,
            checksum_bytes,
            directory_descriptor=staged_descriptor,
            directory_identity=staged_identity,
        )
        os.fsync(staged_descriptor)
        import verify_bundle

        _assert_output_directory_identity(
            DIST.parent,
            parent_descriptor,
            parent_identity,
            "bundle publication parent",
        )
        _assert_output_directory_identity(
            staged_directory,
            staged_descriptor,
            staged_identity,
            "bundle staging directory",
        )
        staged_errors = verify_bundle.validate(staged_bundle)
        _assert_output_directory_identity(
            DIST.parent,
            parent_descriptor,
            parent_identity,
            "bundle publication parent",
        )
        _assert_output_directory_identity(
            staged_directory,
            staged_descriptor,
            staged_identity,
            "bundle staging directory",
        )
        if staged_errors:
            raise SystemExit(
                "cannot publish invalid staged bundle: "
                + "; ".join(staged_errors)
            )
        _publish_bundle_directory(
            staged_directory,
            parent_descriptor=parent_descriptor,
            parent_identity=parent_identity,
        )
    finally:
        if staged_descriptor >= 0:
            os.close(staged_descriptor)
        if staged_created and parent_descriptor >= 0:
            try:
                if (
                    not _entry_exists_at(
                        parent_descriptor,
                        _bundle_transaction_name(),
                    )
                    and _validate_dist_directory_at(
                    parent_descriptor,
                    staged_name,
                    )
                ):
                    shutil.rmtree(
                        staged_name,
                        dir_fd=parent_descriptor,
                    )
                    os.fsync(parent_descriptor)
            except FileNotFoundError:
                pass  # Publication or recovery already removed staging.
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)
    print(f"built {BUNDLE.relative_to(ROOT)}")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
