#!/usr/bin/env python3
"""Build deterministic public development-only receipt-chain rehearsals."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import uuid
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from v2.receipt_protocol import (
    KNOWN_SYSTEM_ALIASES,
    canonical_json_bytes,
    sha256_bytes,
    validate_extension_chain,
    write_blob,
    write_blob_at,
    write_receipt,
    write_receipt_at,
)

HERE = Path(__file__).resolve().parent
DEFAULT_STORE = HERE / "artifacts" / "receipt-rehearsal"
DEFAULT_INDEX = HERE / "artifacts" / "receipt-rehearsal-index.json"
DEFAULT_VALIDATION = HERE / "artifacts" / "receipt-rehearsal-validation.json"
STAMP = "2026-07-31T00:00:00Z"
STORE_MARKER = ".goai-receipt-rehearsal-store"
STORE_MARKER_CONTENT = (
    "GOAI public development-only receipt rehearsal store\n"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_SCHEMA = "goai-frontier-receipt-publication-transaction/v1"
GARBAGE_SCHEMA = "goai-frontier-receipt-garbage-owner/v1"


def common(schema: str) -> dict:
    return {
        "schema": schema,
        "evidenceClass": "development-only",
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def build_chain(
    store: Path,
    domain: str,
    *,
    store_descriptor: int | None = None,
    generator_family: str | None = None,
    extension_class: str | None = None,
    task_manifest_sha256: str | None = None,
    transfer_task_manifest_sha256: str | None = None,
    trigger_task_id: str | None = None,
    transfer_ids: list[str] | None = None,
) -> str:
    def put_blob(data: bytes) -> str:
        if store_descriptor is not None:
            return write_blob_at(store_descriptor, data)
        return write_blob(store, data)

    def put_receipt(receipt: dict) -> str:
        if store_descriptor is not None:
            return write_receipt_at(store_descriptor, receipt)
        return write_receipt(store, receipt)

    generator_family = generator_family or f"development.{domain}.family"
    extension_class = extension_class or f"{domain}.development-extension"
    extension_id = f"{generator_family}:extension"
    proposal_id = f"{extension_id}:proposal"
    candidate_hash = put_blob(f"{extension_id}:candidate".encode("utf-8"))
    trigger_task = (
        trigger_task_id or f"{generator_family}:development-trigger"
    )
    if task_manifest_sha256 is None:
        task_manifest_sha256 = put_blob(
            f"development-manifest:{domain}".encode("utf-8")
        )
    if transfer_task_manifest_sha256 is None:
        transfer_task_manifest_sha256 = put_blob(
            f"development-transfer-manifest:{domain}".encode("utf-8")
        )

    proposal = {
        **common("goai-frontier-proposal-receipt/v2"),
        "proposalId": proposal_id,
        "extensionId": extension_id,
        "taskId": trigger_task,
        "triggerTaskId": trigger_task,
        "domain": domain,
        "generatorFamily": generator_family,
        "extensionClass": extension_class,
        "taskManifestSha256": task_manifest_sha256,
        "transferTaskManifestSha256": transfer_task_manifest_sha256,
        "candidateSha256": candidate_hash,
        "createdAt": STAMP,
    }
    proposal_hash = put_receipt(proposal)

    decision_hashes: list[str] = []
    for reviewer in ("owner", "expert-ai"):
        decision = {
            **common("goai-frontier-decision-receipt/v2"),
            "proposalId": proposal_id,
            "proposalSha256": proposal_hash,
            "reviewer": reviewer,
            "decision": "approve_candidate",
            "reasonCodes": ["development-protocol-rehearsal"],
            "reviewedAt": STAMP,
            "reviewDurationSec": 60,
            "sawAggregateResults": False,
            "sawHiddenGold": False,
        }
        decision_hashes.append(put_receipt(decision))

    tests = []
    categories = (
        "positive",
        "positive",
        "negative",
        "negative",
        "malformed",
        "timeout",
        "rollback",
    )
    for index, category in enumerate(categories, start=1):
        tests.append(
            {
                "testId": f"{domain}-{category}-{index}",
                "category": category,
                "passed": True,
                "exitStatus": 0,
                "outputSha256": put_blob(
                    f"{extension_id}:{category}:{index}:output".encode("utf-8")
                ),
            }
        )
    test_receipt = {
        **common("goai-frontier-test-receipt/v2"),
        "proposalSha256": proposal_hash,
        "candidateSha256": candidate_hash,
        "tests": tests,
    }
    test_hash = put_receipt(test_receipt)

    base_hash = put_blob(f"{domain}:base-verifier".encode("utf-8"))
    activation = {
        **common("goai-frontier-activation-receipt/v2"),
        "proposalSha256": proposal_hash,
        "testReceiptSha256": test_hash,
        "reviewDecisionSha256s": sorted(decision_hashes),
        "baseVerifierSha256": base_hash,
        "extensionBundleSha256": put_blob(
            f"{extension_id}:bundle".encode("utf-8")
        ),
        "status": "candidate-activated",
        "activatedAt": STAMP,
    }
    activation_hash = put_receipt(activation)

    if transfer_ids is None:
        transfer_ids = [
            f"{generator_family}:transfer-a",
            f"{generator_family}:transfer-b",
        ]
    if len(set(transfer_ids)) < 2:
        raise ValueError("receipt chain requires two distinct transfer IDs")
    transfer_tasks = []
    for task_id in transfer_ids:
        if task_id.endswith("-valid"):
            pair_id = task_id[: -len("-valid")]
            safety_task_id = f"{pair_id}-safety"
        else:
            pair_id = f"{task_id}:pair"
            safety_task_id = f"{task_id}:safety"
        execution = {
            **common("goai-frontier-transfer-execution-receipt/v1"),
            "activationReceiptSha256": activation_hash,
            "triggerTaskId": trigger_task,
            "taskId": task_id,
            "pairId": pair_id,
            "safetyTaskId": safety_task_id,
            "validDecision": "accepted",
            "safetyDecision": "rejected",
            "passed": True,
            "safetyPreserved": True,
            "exitStatus": 0,
            "runnerMode": "cpu-development-fixture",
            "validOutputSha256": put_blob(
                f"{extension_id}:{task_id}:valid-output".encode("utf-8")
            ),
            "safetyOutputSha256": put_blob(
                f"{extension_id}:{safety_task_id}:safety-output".encode(
                    "utf-8"
                )
            ),
        }
        execution_hash = put_receipt(execution)
        transfer_tasks.append(
            {
                "taskId": task_id,
                "pairId": pair_id,
                "safetyTaskId": safety_task_id,
                "executionReceiptSha256": execution_hash,
            }
        )
    transfer = {
        **common("goai-frontier-transfer-receipt/v3"),
        "activationReceiptSha256": activation_hash,
        "triggerTaskId": trigger_task,
        "transferTasks": transfer_tasks,
    }
    transfer_hash = put_receipt(transfer)

    protected = {
        **common("goai-frontier-protected-suite-receipt/v2"),
        "activationReceiptSha256": activation_hash,
        "suiteManifestSha256": put_blob(
            f"{extension_id}:protected-manifest".encode("utf-8")
        ),
        "passed": True,
        "exitStatus": 0,
        "regressionCount": 0,
        "unsafeAcceptanceCount": 0,
        "outputSha256": put_blob(
            f"{extension_id}:protected-output".encode("utf-8")
        ),
    }
    protected_hash = put_receipt(protected)

    rollback = {
        **common("goai-frontier-rollback-receipt/v2"),
        "activationReceiptSha256": activation_hash,
        "passed": True,
        "exitStatus": 0,
        "restoredBundleSha256": base_hash,
        "outputSha256": put_blob(
            f"{extension_id}:rollback-output".encode("utf-8")
        ),
    }
    rollback_hash = put_receipt(rollback)

    lean_hash = None
    if domain == "lean":
        lean = {
            **common("goai-frontier-lean-receipt/v2"),
            "activationReceiptSha256": activation_hash,
            "sourceSha256": put_blob(
                f"{extension_id}:lean-source".encode("utf-8")
            ),
            "command": ["lake", "env", "lean", "Main.lean"],
            "timeoutSec": 60,
            "exitStatus": 0,
            "stdoutSha256": put_blob(
                f"{extension_id}:lean-stdout".encode("utf-8")
            ),
            "stderrSha256": put_blob(
                f"{extension_id}:lean-stderr".encode("utf-8")
            ),
            "noUnsafeEscapes": True,
            "passed": True,
        }
        lean_hash = put_receipt(lean)

    chain = {
        **common("goai-frontier-extension-chain/v3"),
        "extensionId": extension_id,
        "proposalId": proposal_id,
        "domain": domain,
        "generatorFamily": generator_family,
        "extensionClass": extension_class,
        "triggerTaskId": trigger_task,
        "taskManifestSha256": task_manifest_sha256,
        "transferTaskManifestSha256": transfer_task_manifest_sha256,
        "proposalSha256": proposal_hash,
        "reviewDecisionSha256s": sorted(decision_hashes),
        "testReceiptSha256": test_hash,
        "activationReceiptSha256": activation_hash,
        "transferReceiptSha256": transfer_hash,
        "protectedSuiteReceiptSha256": protected_hash,
        "rollbackReceiptSha256": rollback_hash,
        "leanReceiptSha256": lean_hash,
        "confirmatoryEligible": False,
    }
    return put_receipt(chain)


def _reject_symlink_ancestors(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            expected_target = KNOWN_SYSTEM_ALIASES.get(current)
            observed_target = Path(os.path.realpath(current))
            if expected_target is None or observed_target != expected_target:
                raise ValueError(f"{label} path contains a symlink: {current}")


def _canonical_target_path(path: Path) -> Path:
    """Resolve parent aliases while preserving a replaceable final symlink."""
    return path.parent.resolve(strict=False) / path.name


def _normalized_path_parts(path: Path) -> tuple[str, ...]:
    return tuple(
        unicodedata.normalize("NFC", part).casefold()
        for part in path.parts
    )


def _paths_alias(left: Path, right: Path) -> bool:
    if _normalized_path_parts(left) == _normalized_path_parts(right):
        return True
    if os.path.lexists(left) and os.path.lexists(right):
        try:
            return os.path.samefile(left, right)
        except OSError:
            return False
    return False


def _path_is_within(path: Path, directory: Path) -> bool:
    path_parts = _normalized_path_parts(path)
    directory_parts = _normalized_path_parts(directory)
    return (
        len(path_parts) > len(directory_parts)
        and path_parts[: len(directory_parts)] == directory_parts
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _validate_existing_receipt(path: Path) -> None:
    data = path.read_bytes()
    if sha256_bytes(data) != path.stem:
        raise ValueError(
            "refusing to replace receipt store with a receipt whose bytes "
            f"do not match its filename: {path.name}"
        )
    try:
        payload = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"refusing to replace receipt store with invalid JSON: {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            "refusing to replace receipt store with a non-object receipt: "
            f"{path.name}"
        )
    if canonical_json_bytes(payload) != data:
        raise ValueError(
            "refusing to replace receipt store with non-canonical JSON: "
            f"{path.name}"
        )


def _validate_existing_blob(path: Path) -> None:
    if sha256_bytes(path.read_bytes()) != path.stem:
        raise ValueError(
            "refusing to replace receipt store with a blob whose bytes "
            f"do not match its filename: {path.name}"
        )


def _validate_existing_store(store: Path) -> None:
    _reject_symlink_ancestors(store, "receipt rehearsal store")
    if store.is_symlink():
        raise ValueError("refusing to replace a symlinked receipt rehearsal store")
    if not store.exists():
        return
    if not store.is_dir():
        raise ValueError("receipt rehearsal store must be a directory")
    entries = list(store.iterdir())
    marker = store / STORE_MARKER
    if (
        marker.is_symlink()
        or not marker.is_file()
        or marker.read_text(encoding="utf-8") != STORE_MARKER_CONTENT
    ):
        raise ValueError(
            "refusing to replace an unmarked or unsafe receipt rehearsal store"
        )
    unexpected = [
        path.name
        for path in entries
        if path.name != STORE_MARKER
        and not (
            path.is_file()
            and not path.is_symlink()
            and path.suffix == ".json"
            and SHA256.fullmatch(path.stem)
        )
        and not (
            path.is_dir()
            and not path.is_symlink()
            and path.name == "blobs"
        )
    ]
    if unexpected:
        raise ValueError(
            f"refusing to replace receipt store with unrelated entries: {unexpected}"
        )
    for path in entries:
        if path.suffix == ".json" and SHA256.fullmatch(path.stem):
            _validate_existing_receipt(path)
    blob_dir = store / "blobs"
    if blob_dir.is_symlink():
        raise ValueError(
            "refusing to replace a symlinked receipt rehearsal blob directory"
        )
    if blob_dir.is_dir():
        unexpected_blobs = [
            path.name
            for path in blob_dir.iterdir()
            if not (
                path.is_file()
                and not path.is_symlink()
                and path.suffix == ".blob"
                and SHA256.fullmatch(path.stem)
            )
        ]
        if unexpected_blobs:
            raise ValueError(
                "refusing to replace receipt store with unrelated blobs: "
                f"{unexpected_blobs}"
            )
        for path in blob_dir.iterdir():
            _validate_existing_blob(path)


def _read_regular_file_at(
    directory_descriptor: int,
    name: str,
    label: str,
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(
        name,
        flags,
        dir_fd=directory_descriptor,
    )
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


def _open_directory_at(
    directory_descriptor: int,
    name: str,
    label: str,
) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(
        name,
        flags,
        dir_fd=directory_descriptor,
    )
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} is not a directory: {name}")
    return descriptor


def _validate_existing_store_at(
    directory_descriptor: int,
    name: str,
) -> None:
    try:
        metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(
            "refusing to replace a symlinked receipt rehearsal store"
        )
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("receipt rehearsal store must be a directory")
    store_descriptor = _open_directory_at(
        directory_descriptor,
        name,
        "receipt rehearsal store",
    )
    try:
        entries = sorted(os.listdir(store_descriptor))
        if STORE_MARKER not in entries:
            raise ValueError(
                "refusing to replace an unmarked or unsafe receipt rehearsal store"
            )
        marker_metadata = os.stat(
            STORE_MARKER,
            dir_fd=store_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(marker_metadata.st_mode)
            or _read_regular_file_at(
                store_descriptor,
                STORE_MARKER,
                "receipt rehearsal store marker",
            ).decode("utf-8")
            != STORE_MARKER_CONTENT
        ):
            raise ValueError(
                "refusing to replace an unmarked or unsafe receipt rehearsal store"
            )
        if "blobs" in entries:
            blob_metadata = os.stat(
                "blobs",
                dir_fd=store_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(blob_metadata.st_mode):
                raise ValueError(
                    "refusing to replace a symlinked receipt rehearsal "
                    "blob directory"
                )
            if not stat.S_ISDIR(blob_metadata.st_mode):
                raise ValueError(
                    "refusing to replace receipt store with unrelated "
                    "entries: ['blobs']"
                )
        unexpected = []
        for entry in entries:
            if entry == STORE_MARKER:
                continue
            entry_metadata = os.stat(
                entry,
                dir_fd=store_descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISREG(entry_metadata.st_mode)
                and entry.endswith(".json")
                and SHA256.fullmatch(Path(entry).stem)
            ):
                data = _read_regular_file_at(
                    store_descriptor,
                    entry,
                    "receipt rehearsal receipt",
                )
                if sha256_bytes(data) != Path(entry).stem:
                    raise ValueError(
                        "refusing to replace receipt store with a receipt whose "
                        f"bytes do not match its filename: {entry}"
                    )
                try:
                    payload = json.loads(
                        data.decode("utf-8"),
                        parse_constant=_reject_json_constant,
                    )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    ValueError,
                ) as exc:
                    raise ValueError(
                        "refusing to replace receipt store with invalid JSON: "
                        f"{entry}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ValueError(
                        "refusing to replace receipt store with a non-object "
                        f"receipt: {entry}"
                    )
                if canonical_json_bytes(payload) != data:
                    raise ValueError(
                        "refusing to replace receipt store with non-canonical "
                        f"JSON: {entry}"
                    )
                continue
            if stat.S_ISDIR(entry_metadata.st_mode) and entry == "blobs":
                continue
            unexpected.append(entry)
        if unexpected:
            raise ValueError(
                "refusing to replace receipt store with unrelated entries: "
                f"{unexpected}"
            )
        if "blobs" not in entries:
            return
        blob_descriptor = _open_directory_at(
            store_descriptor,
            "blobs",
            "receipt rehearsal blob directory",
        )
        try:
            unexpected_blobs = []
            for entry in sorted(os.listdir(blob_descriptor)):
                entry_metadata = os.stat(
                    entry,
                    dir_fd=blob_descriptor,
                    follow_symlinks=False,
                )
                if not (
                    stat.S_ISREG(entry_metadata.st_mode)
                    and entry.endswith(".blob")
                    and SHA256.fullmatch(Path(entry).stem)
                ):
                    unexpected_blobs.append(entry)
                    continue
                data = _read_regular_file_at(
                    blob_descriptor,
                    entry,
                    "receipt rehearsal blob",
                )
                if sha256_bytes(data) != Path(entry).stem:
                    raise ValueError(
                        "refusing to replace receipt store with a blob whose "
                        f"bytes do not match its filename: {entry}"
                    )
            if unexpected_blobs:
                raise ValueError(
                    "refusing to replace receipt store with unrelated blobs: "
                    f"{unexpected_blobs}"
                )
        finally:
            os.close(blob_descriptor)
    finally:
        os.close(store_descriptor)


def _store_fingerprint_at(
    directory_descriptor: int,
    name: str,
) -> dict:
    _validate_existing_store_at(directory_descriptor, name)
    store_descriptor = _open_directory_at(
        directory_descriptor,
        name,
        "receipt rehearsal store",
    )
    rows: list[dict[str, str]] = []
    try:
        for entry in sorted(os.listdir(store_descriptor)):
            metadata = os.stat(
                entry,
                dir_fd=store_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISREG(metadata.st_mode):
                rows.append(
                    {
                        "path": entry,
                        "sha256": sha256_bytes(
                            _read_regular_file_at(
                                store_descriptor,
                                entry,
                                "receipt rehearsal store file",
                            )
                        ),
                    }
                )
                continue
            if stat.S_ISDIR(metadata.st_mode) and entry == "blobs":
                blob_descriptor = _open_directory_at(
                    store_descriptor,
                    entry,
                    "receipt rehearsal blob directory",
                )
                try:
                    for blob in sorted(os.listdir(blob_descriptor)):
                        rows.append(
                            {
                                "path": f"blobs/{blob}",
                                "sha256": sha256_bytes(
                                    _read_regular_file_at(
                                        blob_descriptor,
                                        blob,
                                        "receipt rehearsal blob",
                                    )
                                ),
                            }
                        )
                finally:
                    os.close(blob_descriptor)
                continue
            raise ValueError(
                f"receipt store fingerprint encountered unsafe path: {entry}"
            )
    finally:
        os.close(store_descriptor)
    return {
        "kind": "directory",
        "sha256": sha256_bytes(canonical_json_bytes({"files": rows})),
    }


def _path_fingerprint_at(
    directory_descriptor: int,
    name: str,
    *,
    is_store: bool,
) -> dict | None:
    try:
        metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    if is_store:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(
                f"cannot fingerprint unsafe publication path: {name}"
            )
        return _store_fingerprint_at(directory_descriptor, name)
    if stat.S_ISLNK(metadata.st_mode):
        return {
            "kind": "symlink",
            "target": os.readlink(name, dir_fd=directory_descriptor),
        }
    if stat.S_ISREG(metadata.st_mode):
        return {
            "kind": "file",
            "sha256": sha256_bytes(
                _read_regular_file_at(
                    directory_descriptor,
                    name,
                    "receipt publication sidecar",
                )
            ),
        }
    raise ValueError(f"cannot fingerprint unsafe publication path: {name}")


def _path_matches_fingerprint_at(
    directory_descriptor: int,
    name: str,
    fingerprint: dict | None,
    *,
    is_store: bool,
) -> bool:
    try:
        return (
            _path_fingerprint_at(
                directory_descriptor,
                name,
                is_store=is_store,
            )
            == fingerprint
        )
    except (OSError, ValueError):
        return False


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


def _atomic_write_at(
    path: Path,
    data: bytes,
    *,
    directory_descriptor: int,
    directory_identity: tuple[int, int],
    replace: bool,
    require_lexical_identity: bool = True,
) -> None:
    temporary_descriptor = -1
    temporary_name = f".{path.name}-{uuid.uuid4().hex}.tmp"
    temporary_exists = False
    try:
        if require_lexical_identity:
            _assert_output_directory_identity(
                path.parent,
                directory_descriptor,
                directory_identity,
                "receipt rehearsal output",
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        temporary_descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        temporary_exists = True
        handle = os.fdopen(temporary_descriptor, "wb")
        temporary_descriptor = -1
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if require_lexical_identity:
            _assert_output_directory_identity(
                path.parent,
                directory_descriptor,
                directory_identity,
                "receipt rehearsal output",
            )
        if replace:
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            temporary_exists = False
        else:
            try:
                os.link(
                    temporary_name,
                    path.name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise ValueError(
                    "refusing to overwrite an unknown receipt rehearsal "
                    f"sidecar: {path}"
                ) from exc
            os.unlink(temporary_name, dir_fd=directory_descriptor)
            temporary_exists = False
        if require_lexical_identity:
            _assert_output_directory_identity(
                path.parent,
                directory_descriptor,
                directory_identity,
                "receipt rehearsal output",
            )
        os.fsync(directory_descriptor)
    except BaseException:
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass  # A racing cleanup already removed the temporary.
        raise


def _atomic_write(
    path: Path,
    data: bytes,
    *,
    replace: bool = True,
) -> None:
    _reject_symlink_ancestors(path, "receipt rehearsal output")
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_ancestors(path, "receipt rehearsal output")
    directory_descriptor = -1
    try:
        directory_descriptor, directory_identity = (
            _open_stable_output_directory(
                path.parent,
                "receipt rehearsal output",
            )
        )
        _atomic_write_at(
            path,
            data,
            directory_descriptor=directory_descriptor,
            directory_identity=directory_identity,
            replace=replace,
        )
    finally:
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _transaction_journal_path(
    store: Path,
    index_path: Path,
    validation_path: Path,
) -> Path:
    identity = json.dumps(
        [
            list(_normalized_path_parts(path))
            for path in (store, index_path, validation_path)
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:16]
    return store.parent / f".goai-receipt-publication-{suffix}.json"


def _transaction_lock_path(
    targets: tuple[Path, Path, Path],
) -> Path:
    identity = json.dumps(
        [list(_normalized_path_parts(path)) for path in targets],
        separators=(",", ":"),
    ).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()
    return Path(tempfile.gettempdir()).resolve() / (
        f"goai-receipt-publication-{suffix}.lock"
    )


def _acquire_transaction_lock(targets: tuple[Path, Path, Path]) -> int:
    path = _transaction_lock_path(targets)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _store_fingerprint(path: Path) -> dict:
    _validate_existing_store(path)
    rows = []
    for entry in sorted(path.rglob("*")):
        if entry.is_dir():
            continue
        if entry.is_symlink() or not entry.is_file():
            raise ValueError(
                f"receipt store fingerprint encountered unsafe path: {entry}"
            )
        rows.append(
            {
                "path": entry.relative_to(path).as_posix(),
                "sha256": sha256_bytes(entry.read_bytes()),
            }
        )
    return {
        "kind": "directory",
        "sha256": sha256_bytes(
            canonical_json_bytes({"files": rows})
        ),
    }


def _path_fingerprint(path: Path, *, is_store: bool) -> dict | None:
    if not os.path.lexists(path):
        return None
    if is_store:
        return _store_fingerprint(path)
    if path.is_symlink():
        return {
            "kind": "symlink",
            "target": os.readlink(path),
        }
    if path.is_file():
        return {
            "kind": "file",
            "sha256": sha256_bytes(path.read_bytes()),
        }
    raise ValueError(f"cannot fingerprint unsafe publication path: {path}")


def _valid_fingerprint(value: object, *, allow_none: bool) -> bool:
    if value is None:
        return allow_none
    if not isinstance(value, dict):
        return False
    if value.get("kind") == "symlink":
        return (
            set(value) == {"kind", "target"}
            and isinstance(value.get("target"), str)
        )
    if value.get("kind") in {"file", "directory"}:
        return (
            set(value) == {"kind", "sha256"}
            and SHA256.fullmatch(str(value.get("sha256") or "")) is not None
        )
    return False


def _path_matches_fingerprint(
    path: Path,
    fingerprint: dict | None,
    *,
    is_store: bool,
) -> bool:
    try:
        return _path_fingerprint(path, is_store=is_store) == fingerprint
    except (OSError, ValueError):
        return False


def _transaction_payload(
    targets: tuple[Path, Path, Path],
    nonce: str,
    *,
    phase: str,
    new_fingerprints: tuple[dict, dict, dict],
    directory_descriptor: int | None = None,
) -> dict:
    entries = []
    for index, (target, new_fingerprint) in enumerate(
        zip(targets, new_fingerprints)
    ):
        if directory_descriptor is None:
            old_fingerprint = _path_fingerprint(
                target,
                is_store=index == 0,
            )
        else:
            old_fingerprint = _path_fingerprint_at(
                directory_descriptor,
                target.name,
                is_store=index == 0,
            )
        had_original = old_fingerprint is not None
        backup = (
            target.with_name(f".{target.name}.backup-{nonce}")
            if had_original
            else None
        )
        entries.append(
            {
                "target": str(target),
                "backup": str(backup) if backup is not None else None,
                "hadOriginal": had_original,
                "oldFingerprint": old_fingerprint,
                "newFingerprint": new_fingerprint,
            }
        )
    return {
        "schema": TRANSACTION_SCHEMA,
        "phase": phase,
        "nonce": nonce,
        "entries": entries,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def _validated_transaction_payload(
    journal: Path,
    targets: tuple[Path, Path, Path],
    *,
    expected_nonce: str | None = None,
    directory_descriptor: int | None = None,
) -> dict:
    if directory_descriptor is None:
        if journal.is_symlink() or not journal.is_file():
            raise ValueError("receipt publication journal is not a regular file")
        data = journal.read_bytes()
    else:
        try:
            data = _read_regular_file_at(
                directory_descriptor,
                journal.name,
                "receipt publication journal",
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError(
                "receipt publication journal is not a regular file"
            ) from exc
    try:
        payload = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("receipt publication journal is invalid JSON") from exc
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        raise ValueError("receipt publication journal is not a canonical object")
    if payload.get("schema") != TRANSACTION_SCHEMA:
        raise ValueError("receipt publication journal schema is invalid")
    if payload.get("phase") not in {"prepared", "committed"}:
        raise ValueError("receipt publication journal phase is invalid")
    nonce = str(payload.get("nonce") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("receipt publication journal nonce is invalid")
    if expected_nonce is not None and nonce != expected_nonce:
        raise ValueError("receipt publication journal owner nonce mismatch")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != len(targets):
        raise ValueError("receipt publication journal entries are invalid")
    for entry, target in zip(entries, targets):
        if not isinstance(entry, dict):
            raise ValueError("receipt publication journal entry is invalid")
        if entry.get("target") != str(target):
            raise ValueError("receipt publication journal target mismatch")
        had_original = entry.get("hadOriginal")
        if not isinstance(had_original, bool):
            raise ValueError(
                "receipt publication journal hadOriginal is invalid"
            )
        expected_backup = (
            str(target.with_name(f".{target.name}.backup-{nonce}"))
            if had_original
            else None
        )
        if entry.get("backup") != expected_backup:
            raise ValueError("receipt publication journal backup mismatch")
        old_fingerprint = entry.get("oldFingerprint")
        new_fingerprint = entry.get("newFingerprint")
        if not _valid_fingerprint(
            old_fingerprint,
            allow_none=not had_original,
        ):
            raise ValueError(
                "receipt publication journal old fingerprint is invalid"
            )
        if had_original is not (old_fingerprint is not None):
            raise ValueError(
                "receipt publication journal old fingerprint presence mismatch"
            )
        if not _valid_fingerprint(new_fingerprint, allow_none=False):
            raise ValueError(
                "receipt publication journal new fingerprint is invalid"
            )
    if payload.get("candidateOnly") is not True:
        raise ValueError("receipt publication journal candidateOnly is invalid")
    if payload.get("canClaimAGI") is not False:
        raise ValueError("receipt publication journal canClaimAGI is invalid")
    return payload


def _remove_transaction_path_at(
    directory_descriptor: int,
    path: Path,
    *,
    is_store: bool,
) -> None:
    try:
        metadata = os.stat(
            path.name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if is_store:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(
                f"refusing to remove unexpected transaction path: {path}"
            )
        _validate_existing_store_at(directory_descriptor, path.name)
        shutil.rmtree(path.name, dir_fd=directory_descriptor)
    elif stat.S_ISLNK(metadata.st_mode) or stat.S_ISREG(metadata.st_mode):
        os.unlink(path.name, dir_fd=directory_descriptor)
    else:
        raise ValueError(
            f"refusing to remove unexpected transaction path: {path}"
        )
    os.fsync(directory_descriptor)


def _transaction_garbage_name(target: Path, nonce: str) -> str:
    return f".{target.name}.garbage-{nonce}"


def _transaction_garbage_owner_name(target: Path, nonce: str) -> str:
    return f"{_transaction_garbage_name(target, nonce)}.owner.json"


def _transaction_garbage_payload(
    source: Path,
    target: Path,
    nonce: str,
    *,
    is_store: bool,
) -> dict:
    return {
        "schema": GARBAGE_SCHEMA,
        "nonce": nonce,
        "targetName": target.name,
        "sourceName": source.name,
        "garbageName": _transaction_garbage_name(target, nonce),
        "isStore": is_store,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def _write_transaction_garbage_owner_at(
    directory_descriptor: int,
    source: Path,
    target: Path,
    nonce: str,
    *,
    is_store: bool,
) -> None:
    payload = _transaction_garbage_payload(
        source,
        target,
        nonce,
        is_store=is_store,
    )
    data = canonical_json_bytes(payload)
    owner_name = _transaction_garbage_owner_name(target, nonce)
    try:
        existing = _read_regular_file_at(
            directory_descriptor,
            owner_name,
            "receipt garbage owner",
        )
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing != data:
            raise ValueError("receipt garbage owner manifest mismatch")
        return
    metadata = os.fstat(directory_descriptor)
    _atomic_write_at(
        Path(owner_name),
        data,
        directory_descriptor=directory_descriptor,
        directory_identity=(metadata.st_dev, metadata.st_ino),
        replace=False,
        require_lexical_identity=False,
    )


def _load_transaction_garbage_owner_at(
    directory_descriptor: int,
    owner_name: str,
    targets: tuple[Path, Path, Path],
) -> dict | None:
    try:
        data = _read_regular_file_at(
            directory_descriptor,
            owner_name,
            "receipt garbage owner",
        )
    except (FileNotFoundError, OSError, ValueError):
        return None
    try:
        payload = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        return None
    nonce = str(payload.get("nonce") or "")
    matching_target = next(
        (
            target
            for target in targets
            if target.name == payload.get("targetName")
        ),
        None,
    )
    if (
        payload.get("schema") != GARBAGE_SCHEMA
        or not re.fullmatch(r"[0-9a-f]{32}", nonce)
        or matching_target is None
        or owner_name
        != _transaction_garbage_owner_name(matching_target, nonce)
        or payload.get("sourceName")
        not in {
            matching_target.name,
            f".{matching_target.name}.backup-{nonce}",
        }
        or payload.get("garbageName")
        != _transaction_garbage_name(matching_target, nonce)
        or payload.get("isStore") is not (matching_target == targets[0])
        or payload.get("candidateOnly") is not True
        or payload.get("canClaimAGI") is not False
    ):
        return None
    return payload


def _quarantine_transaction_path_at(
    directory_descriptor: int,
    source: Path,
    target: Path,
    nonce: str,
    *,
    is_store: bool,
) -> None:
    garbage_name = _transaction_garbage_name(target, nonce)
    try:
        metadata = os.stat(
            source.name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if is_store:
        safe_kind = stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(
            metadata.st_mode
        )
    else:
        safe_kind = stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(
            metadata.st_mode
        )
    if not safe_kind:
        return
    try:
        os.stat(
            garbage_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        _write_transaction_garbage_owner_at(
            directory_descriptor,
            source,
            target,
            nonce,
            is_store=is_store,
        )
        os.replace(
            source.name,
            garbage_name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
        os.fsync(directory_descriptor)


def _quarantine_transaction_backup_at(
    directory_descriptor: int,
    backup: Path,
    target: Path,
    nonce: str,
    *,
    is_store: bool,
) -> None:
    _quarantine_transaction_path_at(
        directory_descriptor,
        backup,
        target,
        nonce,
        is_store=is_store,
    )


def _cleanup_transaction_garbage_at(
    directory_descriptor: int,
    targets: tuple[Path, Path, Path],
) -> None:
    owner_patterns = [
        re.compile(
            rf"^\.{re.escape(target.name)}\.garbage-[0-9a-f]{{32}}"
            r"\.owner\.json$"
        )
        for target in targets
    ]
    for owner_name in os.listdir(directory_descriptor):
        if not any(
            pattern.fullmatch(owner_name) for pattern in owner_patterns
        ):
            continue
        payload = _load_transaction_garbage_owner_at(
            directory_descriptor,
            owner_name,
            targets,
        )
        if payload is None:
            continue
        garbage_name = payload["garbageName"]
        try:
            metadata = os.stat(
                garbage_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if payload["isStore"]:
                if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(
                    metadata.st_mode
                ):
                    continue
                shutil.rmtree(garbage_name, dir_fd=directory_descriptor)
            else:
                if not (
                    stat.S_ISREG(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                ):
                    continue
                os.unlink(garbage_name, dir_fd=directory_descriptor)
            os.fsync(directory_descriptor)
        except FileNotFoundError:
            pass  # The quarantined path was already collected.
        except OSError:
            continue
        try:
            os.unlink(owner_name, dir_fd=directory_descriptor)
            os.fsync(directory_descriptor)
        except FileNotFoundError:
            pass  # The owner manifest was already finalized.


def _recover_publication_transaction(
    journal: Path,
    targets: tuple[Path, Path, Path],
    *,
    force_phase: str | None = None,
    expected_nonce: str | None = None,
    directory_descriptor: int | None = None,
) -> None:
    own_descriptor = False
    if len({target.parent for target in targets}) != 1:
        raise ValueError(
            "receipt publication transaction targets must share one parent"
        )
    if directory_descriptor is None:
        directory_descriptor, _ = _open_stable_output_directory(
            targets[0].parent,
            "receipt publication transaction",
        )
        own_descriptor = True
    assert directory_descriptor is not None
    try:
        try:
            os.stat(
                journal.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            _cleanup_transaction_garbage_at(
                directory_descriptor,
                targets,
            )
            return
        payload = _validated_transaction_payload(
            journal,
            targets,
            expected_nonce=expected_nonce,
            directory_descriptor=directory_descriptor,
        )
        store_target = targets[0]
        entries = payload["entries"]
        phase = force_phase or payload["phase"]
        if phase == "prepared":
            for entry in reversed(entries):
                target = Path(entry["target"])
                backup_value = entry["backup"]
                is_store = target == store_target
                old_fingerprint = entry["oldFingerprint"]
                new_fingerprint = entry["newFingerprint"]
                if backup_value is None:
                    if (
                        _path_fingerprint_at(
                            directory_descriptor,
                            target.name,
                            is_store=is_store,
                        )
                        is None
                    ):
                        continue
                    if not _path_matches_fingerprint_at(
                        directory_descriptor,
                        target.name,
                        new_fingerprint,
                        is_store=is_store,
                    ):
                        raise ValueError(
                            "prepared receipt publication found an unknown "
                            f"post-crash target: {target}"
                        )
                    _quarantine_transaction_path_at(
                        directory_descriptor,
                        target,
                        target,
                        payload["nonce"],
                        is_store=is_store,
                    )
                    continue
                backup = Path(backup_value)
                backup_fingerprint = _path_fingerprint_at(
                    directory_descriptor,
                    backup.name,
                    is_store=is_store,
                )
                if backup_fingerprint is not None:
                    if backup_fingerprint != old_fingerprint:
                        raise ValueError(
                            "prepared receipt publication backup fingerprint "
                            f"mismatch: {backup}"
                        )
                    current_fingerprint = _path_fingerprint_at(
                        directory_descriptor,
                        target.name,
                        is_store=is_store,
                    )
                    if current_fingerprint is not None:
                        if current_fingerprint != new_fingerprint:
                            raise ValueError(
                                "prepared receipt publication found an unknown "
                                f"current target: {target}"
                            )
                        _quarantine_transaction_path_at(
                            directory_descriptor,
                            target,
                            target,
                            payload["nonce"],
                            is_store=is_store,
                        )
                    os.replace(
                        backup.name,
                        target.name,
                        src_dir_fd=directory_descriptor,
                        dst_dir_fd=directory_descriptor,
                    )
                    os.fsync(directory_descriptor)
                elif not _path_matches_fingerprint_at(
                    directory_descriptor,
                    target.name,
                    old_fingerprint,
                    is_store=is_store,
                ):
                    raise ValueError(
                        "prepared receipt publication cannot prove the original "
                        f"target survived: {target}"
                    )
        else:
            for entry in entries:
                target = Path(entry["target"])
                is_store = target == store_target
                if not _path_matches_fingerprint_at(
                    directory_descriptor,
                    target.name,
                    entry["newFingerprint"],
                    is_store=is_store,
                ):
                    raise ValueError(
                        "committed receipt publication target fingerprint "
                        "mismatch: "
                        f"{target}"
                    )
            for entry in entries:
                target = Path(entry["target"])
                is_store = target == store_target
                backup_value = entry["backup"]
                if backup_value is None:
                    continue
                backup = Path(backup_value)
                _quarantine_transaction_backup_at(
                    directory_descriptor,
                    backup,
                    target,
                    payload["nonce"],
                    is_store=is_store,
                )
            os.unlink(journal.name, dir_fd=directory_descriptor)
            os.fsync(directory_descriptor)
            _cleanup_transaction_garbage_at(
                directory_descriptor,
                targets,
            )
            return
        os.unlink(journal.name, dir_fd=directory_descriptor)
        os.fsync(directory_descriptor)
        _cleanup_transaction_garbage_at(
            directory_descriptor,
            targets,
        )
    finally:
        if own_descriptor:
            os.close(directory_descriptor)


def _build_generation_at(
    staging_descriptor: int,
    store_name: str,
) -> tuple[list[str], dict, dict]:
    """Build and validate one generation without re-resolving its path."""
    store_descriptor = _open_directory_at(
        staging_descriptor,
        store_name,
        "receipt rehearsal staging store",
    )
    try:
        store_metadata = os.fstat(store_descriptor)
        store_identity = (store_metadata.st_dev, store_metadata.st_ino)
        _atomic_write_at(
            Path(STORE_MARKER),
            STORE_MARKER_CONTENT.encode("utf-8"),
            directory_descriptor=store_descriptor,
            directory_identity=store_identity,
            replace=False,
            require_lexical_identity=False,
        )

        store_label = Path("<descriptor-bound-receipt-store>")
        chain_hashes = [
            build_chain(
                store_label,
                domain,
                store_descriptor=store_descriptor,
            )
            for domain in ("physics", "symbolic", "lean")
        ]
        reports = []
        errors: list[str] = []
        for digest in chain_hashes:
            chain_errors, report = validate_extension_chain(
                store_label,
                digest,
                store_fd=store_descriptor,
            )
            errors.extend(f"{digest}: {error}" for error in chain_errors)
            reports.append(report)

        receipt_hashes = sorted(
            Path(name).stem
            for name in os.listdir(store_descriptor)
            if name.endswith(".json") and SHA256.fullmatch(Path(name).stem)
        )
        blob_descriptor = _open_directory_at(
            store_descriptor,
            "blobs",
            "receipt rehearsal staging blob store",
        )
        try:
            blob_hashes = sorted(
                Path(name).stem
                for name in os.listdir(blob_descriptor)
                if name.endswith(".blob") and SHA256.fullmatch(Path(name).stem)
            )
        finally:
            os.close(blob_descriptor)
        index = {
            "schema": "goai-frontier-receipt-rehearsal-index/v1",
            "status": "PASS" if not errors else "INVALID",
            "evidenceClass": "development-only",
            "confirmatoryEligible": False,
            "chainSha256s": chain_hashes,
            "receiptSha256s": receipt_hashes,
            "receiptCount": len(receipt_hashes),
            "blobSha256s": blob_hashes,
            "blobCount": len(blob_hashes),
            "candidateOnly": True,
            "canClaimAGI": False,
        }
        validation = {
            "schema": "goai-frontier-receipt-rehearsal-validation/v1",
            "status": "PASS" if not errors else "INVALID",
            "chainCount": len(chain_hashes),
            "validChainCount": sum(
                report["status"] == "PASS" for report in reports
            ),
            "receiptCount": len(receipt_hashes),
            "blobCount": len(blob_hashes),
            "reports": reports,
            "errors": errors,
            "candidateOnly": True,
            "canClaimAGI": False,
        }
        return errors, index, validation
    finally:
        os.close(store_descriptor)


def _build_locked(
    store: Path,
    index_path: Path,
    validation_path: Path,
) -> tuple[list[str], dict]:
    original_targets = (store, index_path, validation_path)
    for path, label in zip(
        original_targets,
        (
            "receipt rehearsal store",
            "receipt rehearsal sidecar",
            "receipt rehearsal sidecar",
        ),
    ):
        _reject_symlink_ancestors(path, label)
    store, index_path, validation_path = (
        _canonical_target_path(path)
        for path in original_targets
    )
    targets = (store, index_path, validation_path)
    if any(
        _paths_alias(left, right)
        for index, left in enumerate(targets)
        for right in targets[index + 1 :]
    ):
        raise ValueError("receipt rehearsal store and sidecars must be distinct paths")
    if len({target.parent for target in targets}) != 1:
        raise ValueError(
            "receipt rehearsal store and sidecars must share one parent directory"
        )
    store_abs = store
    for sidecar in (index_path, validation_path):
        sidecar_abs = sidecar
        if _path_is_within(sidecar_abs, store_abs):
            raise ValueError("receipt rehearsal sidecars must be outside the store")
    store.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_ancestors(store, "receipt rehearsal store")
    parent_descriptor, parent_identity = _open_stable_output_directory(
        store.parent,
        "receipt publication parent",
    )
    staging_descriptor = -1
    staging_name = f".{store.name}-generation-{uuid.uuid4().hex}"
    staging_created = False
    journal = _transaction_journal_path(*targets)
    try:
        _recover_publication_transaction(
            journal,
            targets,
            directory_descriptor=parent_descriptor,
        )
        _validate_existing_store_at(parent_descriptor, store.name)
        for sidecar in (index_path, validation_path):
            sidecar_fingerprint = _path_fingerprint_at(
                parent_descriptor,
                sidecar.name,
                is_store=False,
            )
            if (
                sidecar_fingerprint is not None
                and sidecar_fingerprint.get("kind") not in {"file", "symlink"}
            ):
                raise ValueError(
                    "receipt rehearsal sidecar must be a regular file or "
                    f"replaceable symlink: {sidecar}"
                )
        _assert_output_directory_identity(
            store.parent,
            parent_descriptor,
            parent_identity,
            "receipt publication parent",
        )
        os.mkdir(
            staging_name,
            0o700,
            dir_fd=parent_descriptor,
        )
        staging_created = True
        staging_descriptor = _open_directory_at(
            parent_descriptor,
            staging_name,
            "receipt rehearsal staging root",
        )
        os.mkdir("store", 0o700, dir_fd=staging_descriptor)
        errors, index, validation = _build_generation_at(
            staging_descriptor,
            "store",
        )
        _assert_output_directory_identity(
            store.parent,
            parent_descriptor,
            parent_identity,
            "receipt publication parent",
        )
        if errors:
            return errors, validation
        index_bytes = (
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        validation_bytes = (
            json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")

        nonce = uuid.uuid4().hex
        new_fingerprints = (
            _store_fingerprint_at(staging_descriptor, "store"),
            {
                "kind": "file",
                "sha256": sha256_bytes(index_bytes),
            },
            {
                "kind": "file",
                "sha256": sha256_bytes(validation_bytes),
            },
        )
        transaction = _transaction_payload(
            targets,
            nonce,
            phase="prepared",
            new_fingerprints=new_fingerprints,
            directory_descriptor=parent_descriptor,
        )
        _atomic_write_at(
            journal,
            canonical_json_bytes(transaction),
            directory_descriptor=parent_descriptor,
            directory_identity=parent_identity,
            replace=True,
        )
        try:
            for entry in transaction["entries"]:
                backup_value = entry["backup"]
                if backup_value is not None:
                    target = Path(entry["target"])
                    backup = Path(backup_value)
                    _assert_output_directory_identity(
                        store.parent,
                        parent_descriptor,
                        parent_identity,
                        "receipt publication parent",
                    )
                    os.replace(
                        target.name,
                        backup.name,
                        src_dir_fd=parent_descriptor,
                        dst_dir_fd=parent_descriptor,
                    )
                    os.fsync(parent_descriptor)
            _assert_output_directory_identity(
                store.parent,
                parent_descriptor,
                parent_identity,
                "receipt publication parent",
            )
            os.replace(
                "store",
                store.name,
                src_dir_fd=staging_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.fsync(parent_descriptor)
            _atomic_write_at(
                index_path,
                index_bytes,
                directory_descriptor=parent_descriptor,
                directory_identity=parent_identity,
                replace=False,
            )
            _atomic_write_at(
                validation_path,
                validation_bytes,
                directory_descriptor=parent_descriptor,
                directory_identity=parent_identity,
                replace=False,
            )
            transaction["phase"] = "committed"
            _atomic_write_at(
                journal,
                canonical_json_bytes(transaction),
                directory_descriptor=parent_descriptor,
                directory_identity=parent_identity,
                replace=True,
            )
        except BaseException:
            _recover_publication_transaction(
                journal,
                targets,
                force_phase="prepared",
                expected_nonce=nonce,
                directory_descriptor=parent_descriptor,
            )
            raise
        _recover_publication_transaction(
            journal,
            targets,
            directory_descriptor=parent_descriptor,
        )
        _assert_output_directory_identity(
            store.parent,
            parent_descriptor,
            parent_identity,
            "receipt publication parent",
        )
        return errors, validation
    finally:
        if staging_descriptor >= 0:
            os.close(staging_descriptor)
        if staging_created:
            try:
                shutil.rmtree(
                    staging_name,
                    dir_fd=parent_descriptor,
                )
            except FileNotFoundError:
                pass  # Publication or recovery already removed staging.
        os.close(parent_descriptor)


def build(
    store: Path,
    index_path: Path,
    validation_path: Path,
) -> tuple[list[str], dict]:
    for path, label in zip(
        (store, index_path, validation_path),
        (
            "receipt rehearsal store",
            "receipt rehearsal sidecar",
            "receipt rehearsal sidecar",
        ),
    ):
        _reject_symlink_ancestors(path, label)
    canonical_targets = tuple(
        _canonical_target_path(path)
        for path in (store, index_path, validation_path)
    )
    lock_descriptor = -1
    try:
        lock_descriptor = _acquire_transaction_lock(canonical_targets)
        return _build_locked(*canonical_targets)
    finally:
        if lock_descriptor >= 0:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            finally:
                os.close(lock_descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    args = parser.parse_args()
    errors, validation = build(args.store, args.index, args.validation)
    if errors:
        print("RECEIPT REHEARSAL: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "RECEIPT REHEARSAL: PASS "
        f"({validation['validChainCount']}/{validation['chainCount']} chains; "
        f"{validation['receiptCount']} receipts; "
        f"{validation['blobCount']} evidence blobs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
