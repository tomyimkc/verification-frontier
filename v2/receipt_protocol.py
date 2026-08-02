#!/usr/bin/env python3
"""Content-addressed receipts for verification-frontier extensions.

The public v2 environment originally linked opaque SHA-256 strings.  This
module makes those links executable: every referenced JSON file must exist,
match its content hash, preserve the claim ceiling, and form a complete,
internally consistent proposal -> review -> test -> activation -> transfer ->
protected-suite -> rollback chain.

Confirmatory use remains disabled.  The public artifacts built by this
milestone are development-only protocol rehearsals.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_REVIEWERS = frozenset({"owner", "expert-ai"})
REQUIRED_TEST_COUNTS = {
    "positive": 2,
    "negative": 2,
    "malformed": 1,
    "timeout": 1,
    "rollback": 1,
}
RECEIPT_SCHEMAS = {
    "proposal": "goai-frontier-proposal-receipt/v2",
    "decision": "goai-frontier-decision-receipt/v2",
    "tests": "goai-frontier-test-receipt/v2",
    "activation": "goai-frontier-activation-receipt/v2",
    "transfer": "goai-frontier-transfer-receipt/v3",
    "transfer-execution": "goai-frontier-transfer-execution-receipt/v1",
    "protected": "goai-frontier-protected-suite-receipt/v2",
    "rollback": "goai-frontier-rollback-receipt/v2",
    "lean": "goai-frontier-lean-receipt/v2",
    "chain": "goai-frontier-extension-chain/v3",
}
KNOWN_SYSTEM_ALIASES = {
    Path("/tmp"): Path("/private/tmp"),
    Path("/var"): Path("/private/var"),
}


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    """Return one deterministic JSON representation for hashing and storage."""
    if not isinstance(value, dict):
        raise TypeError("receipt must be a JSON object")
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


def sha256_json(value: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _claim_errors(receipt: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if receipt.get("candidateOnly") is not True:
        errors.append(f"{label}: candidateOnly must be true")
    if receipt.get("canClaimAGI") is not False:
        errors.append(f"{label}: canClaimAGI must be false")
    return errors


def _hash_error(value: Any, label: str) -> list[str]:
    return [] if SHA256.fullmatch(str(value or "")) else [f"{label}: invalid SHA-256"]


def _receipt_path(store: Path, digest: str) -> Path:
    if not SHA256.fullmatch(digest):
        raise ValueError("receipt digest must be lowercase SHA-256")
    return store / f"{digest}.json"


def _blob_path(store: Path, digest: str) -> Path:
    if not SHA256.fullmatch(digest):
        raise ValueError("blob digest must be lowercase SHA-256")
    return store / "blobs" / f"{digest}.blob"


def _ensure_no_symlink_components(path: Path, label: str) -> None:
    """Reject an existing symlink in any component without resolving through it."""
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


def _ensure_plain_directory(path: Path, label: str, *, parents: bool) -> None:
    """Create a directory without accepting a pre-existing redirecting path."""
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    _ensure_no_symlink_components(path, label)
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"{label} must be a directory: {path}")
        return
    path.mkdir(parents=parents, exist_ok=False)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} is not a safe directory: {path}")


def _read_content_addressed_file(
    directory_fd: int,
    filename: str,
    label: str,
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(filename, flags, dir_fd=directory_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"{label} is not a regular file: {filename}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _open_directory_at(
    parent_fd: int,
    name: str,
    label: str,
) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ValueError(f"{label} is unsafe or unavailable: {name}") from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} is not a directory: {name}")
    return descriptor


def _ensure_directory_at(
    parent_fd: int,
    name: str,
    label: str,
) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass  # Another writer created the same directory first.
    return _open_directory_at(parent_fd, name, label)


def _publish_content_addressed_at(
    directory_fd: int,
    filename: str,
    data: bytes,
    *,
    temporary_prefix: str,
) -> None:
    """Publish immutable bytes using only an already-open directory."""
    directory_metadata = os.fstat(directory_fd)
    if not stat.S_ISDIR(directory_metadata.st_mode):
        raise ValueError("content-addressed destination is not a directory")
    fd: int | None = None
    tmp_name: str | None = None
    try:
        temporary_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            temporary_flags |= os.O_NOFOLLOW
        for _ in range(128):
            candidate = f"{temporary_prefix}{secrets.token_hex(16)}.tmp"
            try:
                fd = os.open(
                    candidate,
                    temporary_flags,
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            tmp_name = candidate
            break
        else:
            raise FileExistsError(
                "could not allocate a unique content-addressed temporary file"
            )
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(
                tmp_name,
                filename,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            try:
                existing = _read_content_addressed_file(
                    directory_fd,
                    filename,
                    "content-addressed destination",
                )
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"content-address destination is unsafe: {filename}"
                ) from exc
            if existing != data:
                raise ValueError(
                    "content-address collision or racing destination: "
                    f"{filename}"
                )
        os.unlink(tmp_name, dir_fd=directory_fd)
        tmp_name = None
        os.fsync(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass  # A racing cleanup already removed the temporary.


def _publish_content_addressed(
    directory: Path,
    filename: str,
    data: bytes,
    *,
    temporary_prefix: str,
) -> None:
    """Publish immutable bytes without replacing a racing destination."""
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    directory_fd = os.open(directory, directory_flags)
    directory_identity = os.fstat(directory_fd)
    fd: int | None = None
    tmp_name: str | None = None
    created_destination = False
    try:
        temporary_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            temporary_flags |= os.O_NOFOLLOW
        for _ in range(128):
            candidate = (
                f"{temporary_prefix}{secrets.token_hex(16)}.tmp"
            )
            try:
                fd = os.open(
                    candidate,
                    temporary_flags,
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            tmp_name = candidate
            break
        else:
            raise FileExistsError(
                "could not allocate a unique content-addressed temporary file"
            )
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(
                tmp_name,
                filename,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            created_destination = True
        except FileExistsError:
            try:
                existing = _read_content_addressed_file(
                    directory_fd,
                    filename,
                    "content-addressed destination",
                )
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"content-address destination is unsafe: {directory / filename}"
                ) from exc
            if existing != data:
                raise ValueError(
                    "content-address collision or racing destination: "
                    f"{directory / filename}"
                )
        try:
            current_identity = os.stat(directory, follow_symlinks=False)
        except OSError as exc:
            current_identity = None
            identity_error = exc
        else:
            identity_error = None
        if (
            current_identity is None
            or not stat.S_ISDIR(current_identity.st_mode)
            or (
                current_identity.st_dev,
                current_identity.st_ino,
            )
            != (
                directory_identity.st_dev,
                directory_identity.st_ino,
            )
        ):
            if created_destination:
                os.unlink(filename, dir_fd=directory_fd)
            raise ValueError(
                "content-addressed directory changed during publication"
            ) from identity_error
        os.fsync(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def write_blob(store: Path, data: bytes) -> str:
    """Write immutable evidence bytes under their SHA-256 filename."""
    if not isinstance(data, bytes):
        raise TypeError("evidence blob must be bytes")
    digest = sha256_bytes(data)
    _ensure_plain_directory(store, "receipt store", parents=True)
    blob_dir = store / "blobs"
    _ensure_plain_directory(blob_dir, "receipt blob directory", parents=False)
    destination = _blob_path(store, digest)
    _publish_content_addressed(
        blob_dir,
        destination.name,
        data,
        temporary_prefix=".blob-",
    )
    return digest


def write_blob_at(store_fd: int, data: bytes) -> str:
    """Write immutable evidence bytes below an already-open receipt store."""
    if not isinstance(data, bytes):
        raise TypeError("evidence blob must be bytes")
    digest = sha256_bytes(data)
    blob_fd = _ensure_directory_at(
        store_fd,
        "blobs",
        "receipt blob directory",
    )
    try:
        _publish_content_addressed_at(
            blob_fd,
            f"{digest}.blob",
            data,
            temporary_prefix=".blob-",
        )
    finally:
        os.close(blob_fd)
    return digest


def load_blob(
    store: Path,
    digest: str,
    *,
    store_fd: int | None = None,
) -> tuple[bytes | None, list[str]]:
    if not SHA256.fullmatch(str(digest or "")):
        return None, [f"invalid evidence blob digest {digest!r}"]
    if store_fd is not None:
        try:
            blob_fd = _open_directory_at(
                store_fd,
                "blobs",
                "receipt blob directory",
            )
        except ValueError:
            return None, [f"missing evidence blob {digest}.blob"]
        try:
            data = _read_content_addressed_file(
                blob_fd,
                f"{digest}.blob",
                "evidence blob",
            )
        except FileNotFoundError:
            return None, [f"missing evidence blob {digest}.blob"]
        except (OSError, ValueError) as exc:
            return None, [
                f"cannot read evidence blob {digest}.blob: {type(exc).__name__}"
            ]
        finally:
            os.close(blob_fd)
        if sha256_bytes(data) != digest:
            return None, [f"evidence blob content hash mismatch: {digest}.blob"]
        return data, []
    path = _blob_path(store, digest)
    try:
        _ensure_no_symlink_components(path, "evidence blob")
    except ValueError as exc:
        return None, [str(exc)]
    if not path.exists():
        return None, [f"missing evidence blob {digest}.blob"]
    if path.is_symlink():
        return None, [f"evidence blob must not be a symlink: {digest}.blob"]
    if not path.is_file():
        return None, [f"evidence blob path is not a file: {digest}.blob"]
    data = path.read_bytes()
    if sha256_bytes(data) != digest:
        return None, [f"evidence blob content hash mismatch: {digest}.blob"]
    return data, []


def _blob_errors(
    store: Path,
    digest: Any,
    label: str,
    *,
    store_fd: int | None = None,
) -> list[str]:
    if not SHA256.fullmatch(str(digest or "")):
        return [f"{label}: invalid SHA-256"]
    _, errors = load_blob(store, str(digest), store_fd=store_fd)
    return [f"{label}: {error}" for error in errors]


def write_receipt(store: Path, receipt: dict[str, Any]) -> str:
    """Atomically write a canonical receipt under its SHA-256 filename."""
    data = canonical_json_bytes(receipt)
    digest = sha256_bytes(data)
    _ensure_plain_directory(store, "receipt store", parents=True)
    destination = _receipt_path(store, digest)
    _publish_content_addressed(
        store,
        destination.name,
        data,
        temporary_prefix=".receipt-",
    )
    return digest


def write_receipt_at(store_fd: int, receipt: dict[str, Any]) -> str:
    """Write one canonical receipt below an already-open receipt store."""
    data = canonical_json_bytes(receipt)
    digest = sha256_bytes(data)
    _publish_content_addressed_at(
        store_fd,
        f"{digest}.json",
        data,
        temporary_prefix=".receipt-",
    )
    return digest


def load_receipt(
    store: Path,
    digest: str,
    *,
    store_fd: int | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Load one receipt while rejecting traversal, symlinks, and hash mismatch."""
    if not SHA256.fullmatch(str(digest or "")):
        return None, [f"invalid receipt digest {digest!r}"]
    if store_fd is not None:
        try:
            data = _read_content_addressed_file(
                store_fd,
                f"{digest}.json",
                "receipt",
            )
        except FileNotFoundError:
            return None, [f"missing receipt file {digest}.json"]
        except (OSError, ValueError) as exc:
            return None, [
                f"cannot read receipt {digest}.json: {type(exc).__name__}"
            ]
    else:
        path = _receipt_path(store, digest)
        try:
            _ensure_no_symlink_components(path, "receipt")
        except ValueError as exc:
            return None, [str(exc)]
        if not path.exists():
            return None, [f"missing receipt file {digest}.json"]
        if path.is_symlink():
            return None, [f"receipt file must not be a symlink: {digest}.json"]
        if not path.is_file():
            return None, [f"receipt path is not a file: {digest}.json"]
        try:
            data = path.read_bytes()
        except OSError as exc:
            return None, [
                f"cannot read receipt {digest}.json: {type(exc).__name__}"
            ]
    if sha256_bytes(data) != digest:
        return None, [f"receipt content hash mismatch: {digest}.json"]
    try:
        receipt = json.loads(
            data,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return None, [f"invalid receipt JSON {digest}.json: {type(exc).__name__}"]
    if not isinstance(receipt, dict):
        return None, [f"receipt must be a JSON object: {digest}.json"]
    try:
        canonical = canonical_json_bytes(receipt)
    except (TypeError, ValueError, RecursionError) as exc:
        return None, [
            f"invalid receipt JSON {digest}.json: {type(exc).__name__}"
        ]
    if canonical != data:
        return None, [f"receipt is not canonical JSON: {digest}.json"]
    return receipt, []


def _load_typed(
    store: Path,
    digest: str,
    receipt_type: str,
    *,
    store_fd: int | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    receipt, errors = load_receipt(store, digest, store_fd=store_fd)
    if receipt is None:
        return None, errors
    label = f"{receipt_type} receipt {digest}"
    errors.extend(_claim_errors(receipt, label))
    expected_schema = RECEIPT_SCHEMAS[receipt_type]
    if receipt.get("schema") != expected_schema:
        errors.append(
            f"{label}: schema must be {expected_schema!r}, "
            f"got {receipt.get('schema')!r}"
        )
    if receipt.get("evidenceClass") not in {"development-only", "confirmatory"}:
        errors.append(f"{label}: invalid evidenceClass")
    return receipt, errors


def _same_evidence_class(
    receipts: Iterable[tuple[str, dict[str, Any]]],
    expected: str,
) -> list[str]:
    return [
        f"{label}: evidenceClass does not match chain"
        for label, receipt in receipts
        if receipt.get("evidenceClass") != expected
    ]


def validate_extension_chain(
    store: Path,
    chain_digest: str,
    *,
    store_fd: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate a complete content-addressed extension receipt chain."""
    errors: list[str] = []
    chain, chain_errors = _load_typed(
        store,
        chain_digest,
        "chain",
        store_fd=store_fd,
    )
    errors.extend(chain_errors)
    if chain is None:
        return errors, {
            "schema": "goai-frontier-receipt-validation/v1",
            "status": "INVALID",
            "chainSha256": chain_digest,
            "errors": errors,
            "candidateOnly": True,
            "canClaimAGI": False,
        }

    evidence_class = str(chain.get("evidenceClass") or "")
    if evidence_class == "confirmatory":
        errors.append("confirmatory receipt validation is disabled in this milestone")
    if evidence_class == "development-only":
        if chain.get("confirmatoryEligible") is not False:
            errors.append(
                "development-only chain confirmatoryEligible must be false"
            )
    elif chain.get("confirmatoryEligible") is not True:
        errors.append("confirmatory chain confirmatoryEligible must be true")

    domain = str(chain.get("domain") or "")
    if domain not in {"physics", "symbolic", "lean"}:
        errors.append(f"chain: invalid domain {domain!r}")
    proposal_id = str(chain.get("proposalId") or "")
    extension_id = str(chain.get("extensionId") or "")
    generator_family = str(chain.get("generatorFamily") or "")
    extension_class = str(chain.get("extensionClass") or "")
    trigger_task_id = str(chain.get("triggerTaskId") or "")
    if not proposal_id:
        errors.append("chain: proposalId is required")
    if not extension_id:
        errors.append("chain: extensionId is required")
    if not generator_family:
        errors.append("chain: generatorFamily is required")
    if not extension_class:
        errors.append("chain: extensionClass is required")
    if not trigger_task_id:
        errors.append("chain: triggerTaskId is required")
    errors.extend(
        _blob_errors(
            store,
            chain.get("taskManifestSha256"),
            "chain task manifest",
            store_fd=store_fd,
        )
    )
    errors.extend(
        _blob_errors(
            store,
            chain.get("transferTaskManifestSha256"),
            "chain transfer task manifest",
            store_fd=store_fd,
        )
    )

    link_fields = {
        "proposal": chain.get("proposalSha256"),
        "tests": chain.get("testReceiptSha256"),
        "activation": chain.get("activationReceiptSha256"),
        "transfer": chain.get("transferReceiptSha256"),
        "protected": chain.get("protectedSuiteReceiptSha256"),
        "rollback": chain.get("rollbackReceiptSha256"),
    }
    for label, digest in link_fields.items():
        errors.extend(_hash_error(digest, f"chain {label} link"))

    decision_digests = chain.get("reviewDecisionSha256s")
    if not isinstance(decision_digests, list):
        errors.append("chain reviewDecisionSha256s must be a list")
        decision_digests = []
    if len(decision_digests) != 2 or len(set(map(str, decision_digests))) != 2:
        errors.append("chain must link exactly two distinct review decisions")
    for digest in decision_digests:
        errors.extend(_hash_error(digest, "chain decision link"))

    lean_digest = chain.get("leanReceiptSha256")
    if domain == "lean":
        errors.extend(_hash_error(lean_digest, "chain Lean link"))
    elif lean_digest is not None:
        errors.append("non-Lean chain must not link a Lean receipt")

    loaded: dict[str, dict[str, Any]] = {}
    for label, digest in link_fields.items():
        if SHA256.fullmatch(str(digest or "")):
            receipt, receipt_errors = _load_typed(
                store,
                str(digest),
                label,
                store_fd=store_fd,
            )
            errors.extend(receipt_errors)
            if receipt is not None:
                loaded[label] = receipt
    decisions: list[tuple[str, dict[str, Any]]] = []
    for digest in decision_digests:
        if not SHA256.fullmatch(str(digest or "")):
            continue
        receipt, receipt_errors = _load_typed(
            store,
            str(digest),
            "decision",
            store_fd=store_fd,
        )
        errors.extend(receipt_errors)
        if receipt is not None:
            decisions.append((str(digest), receipt))
    if domain == "lean" and SHA256.fullmatch(str(lean_digest or "")):
        receipt, receipt_errors = _load_typed(
            store,
            str(lean_digest),
            "lean",
            store_fd=store_fd,
        )
        errors.extend(receipt_errors)
        if receipt is not None:
            loaded["lean"] = receipt

    errors.extend(
        _same_evidence_class(
            [(label, receipt) for label, receipt in loaded.items()]
            + [(f"decision {digest}", receipt) for digest, receipt in decisions],
            evidence_class,
        )
    )

    proposal = loaded.get("proposal")
    if proposal is not None:
        if proposal.get("proposalId") != proposal_id:
            errors.append("proposal receipt proposalId does not match chain")
        if proposal.get("extensionId") != extension_id:
            errors.append("proposal receipt extensionId does not match chain")
        if proposal.get("domain") != domain:
            errors.append("proposal receipt domain does not match chain")
        if proposal.get("taskId") != trigger_task_id:
            errors.append(
                "proposal receipt taskId does not match chain triggerTaskId"
            )
        for field, expected in (
            ("generatorFamily", generator_family),
            ("extensionClass", extension_class),
            ("triggerTaskId", trigger_task_id),
            ("taskManifestSha256", chain.get("taskManifestSha256")),
            (
                "transferTaskManifestSha256",
                chain.get("transferTaskManifestSha256"),
            ),
        ):
            if proposal.get(field) != expected:
                errors.append(f"proposal receipt {field} does not match chain")
        errors.extend(
            _blob_errors(
                store,
                proposal.get("candidateSha256"),
                "proposal candidateSha256",
                store_fd=store_fd,
            )
        )

    reviewers: set[str] = set()
    proposal_digest = str(chain.get("proposalSha256") or "")
    for digest, decision in decisions:
        reviewer = str(decision.get("reviewer") or "")
        reviewers.add(reviewer)
        label = f"decision receipt {digest}"
        if decision.get("proposalSha256") != proposal_digest:
            errors.append(f"{label}: proposalSha256 does not match chain")
        if decision.get("proposalId") != proposal_id:
            errors.append(f"{label}: proposalId does not match chain")
        if decision.get("decision") != "approve_candidate":
            errors.append(f"{label}: decision must be approve_candidate")
        if decision.get("sawAggregateResults") is not False:
            errors.append(f"{label}: sawAggregateResults must be false")
        if decision.get("sawHiddenGold") is not False:
            errors.append(f"{label}: sawHiddenGold must be false")
        duration = decision.get("reviewDurationSec")
        if not isinstance(duration, (int, float)) or duration < 0:
            errors.append(f"{label}: reviewDurationSec must be non-negative")
    if reviewers != REQUIRED_REVIEWERS:
        errors.append(
            "review receipts must contain exactly owner and expert-ai approvals"
        )

    tests = loaded.get("tests")
    if tests is not None:
        if tests.get("proposalSha256") != proposal_digest:
            errors.append("test receipt proposalSha256 does not match chain")
        if proposal is not None and (
            tests.get("candidateSha256") != proposal.get("candidateSha256")
        ):
            errors.append("test receipt candidateSha256 does not match proposal")
        cases = tests.get("tests")
        if not isinstance(cases, list):
            errors.append("test receipt tests must be a list")
            cases = []
        categories: Counter[str] = Counter()
        test_ids: set[str] = set()
        for index, case in enumerate(cases):
            label = f"test receipt case {index}"
            if not isinstance(case, dict):
                errors.append(f"{label}: must be an object")
                continue
            test_id = str(case.get("testId") or "")
            if not test_id:
                errors.append(f"{label}: testId is required")
            elif test_id in test_ids:
                errors.append(f"{label}: duplicate testId {test_id}")
            test_ids.add(test_id)
            category = str(case.get("category") or "")
            categories[category] += 1
            if category not in REQUIRED_TEST_COUNTS:
                errors.append(f"{label}: unsupported category {category!r}")
            if case.get("passed") is not True:
                errors.append(f"{label}: passed must be true")
            if case.get("exitStatus") != 0:
                errors.append(f"{label}: exitStatus must be zero")
            errors.extend(
                _blob_errors(
                    store,
                    case.get("outputSha256"),
                    f"{label} output",
                    store_fd=store_fd,
                )
            )
        for category, minimum in REQUIRED_TEST_COUNTS.items():
            if categories[category] < minimum:
                errors.append(
                    f"test receipt requires at least {minimum} {category} "
                    f"case(s), got {categories[category]}"
                )

    activation = loaded.get("activation")
    activation_digest = str(chain.get("activationReceiptSha256") or "")
    if activation is not None:
        if activation.get("proposalSha256") != proposal_digest:
            errors.append("activation proposalSha256 does not match chain")
        if activation.get("testReceiptSha256") != chain.get("testReceiptSha256"):
            errors.append("activation testReceiptSha256 does not match chain")
        activation_decisions = activation.get("reviewDecisionSha256s")
        if (
            not isinstance(activation_decisions, list)
            or set(map(str, activation_decisions)) != set(map(str, decision_digests))
        ):
            errors.append("activation review decision links do not match chain")
        if activation.get("status") != "candidate-activated":
            errors.append("activation status must be candidate-activated")
        errors.extend(
            _blob_errors(
                store,
                activation.get("baseVerifierSha256"),
                "activation baseVerifierSha256",
                store_fd=store_fd,
            )
        )
        errors.extend(
            _blob_errors(
                store,
                activation.get("extensionBundleSha256"),
                "activation extensionBundleSha256",
                store_fd=store_fd,
            )
        )

    transfer = loaded.get("transfer")
    transfer_task_ids: list[str] = []
    transfer_pair_ids: list[str] = []
    transfer_safety_task_ids: list[str] = []
    transfer_parent_bindings: list[tuple[str, str, str]] = []
    transfer_execution_digests: list[str] = []
    transfer_execution_receipts: list[tuple[str, dict[str, Any]]] = []
    transfer_execution_bindings: list[dict[str, str]] = []
    transfer_output_digests: list[str] = []
    transfer_execution_receipts_validated = False
    if transfer is not None:
        transfer_error_start = len(errors)
        if transfer.get("activationReceiptSha256") != activation_digest:
            errors.append("transfer activationReceiptSha256 does not match chain")
        transfer_trigger_task_id = str(transfer.get("triggerTaskId") or "")
        if transfer_trigger_task_id != trigger_task_id:
            errors.append("transfer triggerTaskId does not match chain")
        transfer_tasks = transfer.get("transferTasks")
        if not isinstance(transfer_tasks, list):
            errors.append("transfer receipt transferTasks must be a list")
            transfer_tasks = []
        for index, task in enumerate(transfer_tasks):
            if not isinstance(task, dict):
                errors.append(f"transfer task {index}: must be an object")
                continue
            task_id = str(task.get("taskId") or "")
            if not task_id:
                errors.append(f"transfer task {index}: taskId is required")
            transfer_task_ids.append(task_id)
            pair_id = str(task.get("pairId") or "")
            safety_task_id = str(task.get("safetyTaskId") or "")
            transfer_pair_ids.append(pair_id)
            transfer_safety_task_ids.append(safety_task_id)
            transfer_parent_bindings.append(
                (task_id, pair_id, safety_task_id)
            )
            if not pair_id:
                errors.append(f"transfer task {index}: pairId is required")
            if not safety_task_id:
                errors.append(
                    f"transfer task {index}: safetyTaskId is required"
                )
            execution_digest = str(
                task.get("executionReceiptSha256") or ""
            )
            errors.extend(
                _hash_error(
                    execution_digest,
                    f"transfer task {index} execution receipt",
                )
            )
            if not SHA256.fullmatch(execution_digest):
                continue
            execution, execution_errors = _load_typed(
                store,
                execution_digest,
                "transfer-execution",
                store_fd=store_fd,
            )
            errors.extend(execution_errors)
            if execution is None:
                continue
            transfer_execution_digests.append(execution_digest)
            transfer_execution_receipts.append(
                (execution_digest, execution)
            )
            transfer_execution_bindings.append(
                {
                    "taskId": task_id,
                    "pairId": pair_id,
                    "safetyTaskId": safety_task_id,
                    "executionReceiptSha256": execution_digest,
                }
            )
            label = f"transfer execution receipt {execution_digest}"
            expected_links = {
                "activationReceiptSha256": activation_digest,
                "triggerTaskId": trigger_task_id,
                "taskId": task_id,
                "pairId": pair_id,
                "safetyTaskId": safety_task_id,
            }
            for field, expected in expected_links.items():
                if execution.get(field) != expected:
                    errors.append(
                        f"{label}: {field} does not match transfer parent"
                    )
            if execution.get("validDecision") != "accepted":
                errors.append(
                    f"{label}: validDecision must be accepted"
                )
            if execution.get("safetyDecision") not in {
                "rejected",
                "abstain",
            }:
                errors.append(
                    f"{label}: safetyDecision must be rejected or abstain"
                )
            if execution.get("passed") is not True:
                errors.append(f"{label}: passed must be true")
            if execution.get("safetyPreserved") is not True:
                errors.append(
                    f"{label}: safetyPreserved must be true"
                )
            if execution.get("exitStatus") != 0:
                errors.append(f"{label}: exitStatus must be zero")
            if execution.get("runnerMode") != "cpu-development-fixture":
                errors.append(
                    f"{label}: runnerMode must be cpu-development-fixture"
                )
            valid_output_digest = str(
                execution.get("validOutputSha256") or ""
            )
            safety_output_digest = str(
                execution.get("safetyOutputSha256") or ""
            )
            if (
                SHA256.fullmatch(valid_output_digest)
                and SHA256.fullmatch(safety_output_digest)
                and valid_output_digest == safety_output_digest
            ):
                errors.append(
                    f"{label}: valid and safety output digests must differ"
                )
            transfer_output_digests.extend(
                (valid_output_digest, safety_output_digest)
            )
            for field in (
                "validOutputSha256",
                "safetyOutputSha256",
            ):
                errors.extend(
                    _blob_errors(
                        store,
                        execution.get(field),
                        f"{label} {field}",
                        store_fd=store_fd,
                    )
                )
        if len(set(transfer_task_ids)) < 2:
            errors.append("transfer receipt requires two distinct transfer tasks")
        if len(set(transfer_task_ids)) != len(transfer_task_ids):
            errors.append(
                "transfer receipt contains duplicate transfer taskId values"
            )
        if len(set(transfer_pair_ids)) != len(transfer_pair_ids):
            errors.append(
                "transfer receipt contains duplicate transfer pairId values"
            )
        if len(set(transfer_safety_task_ids)) != len(
            transfer_safety_task_ids
        ):
            errors.append(
                "transfer receipt contains duplicate safetyTaskId values"
            )
        if len(set(transfer_parent_bindings)) != len(
            transfer_parent_bindings
        ):
            errors.append(
                "transfer receipt contains duplicate task/pair/safety bindings"
            )
        if trigger_task_id in set(transfer_task_ids):
            errors.append("trigger task cannot count as a transfer task")
        if len(transfer_execution_receipts) != len(transfer_tasks):
            errors.append(
                "every transfer task must link exactly one execution receipt"
            )
        if len(set(transfer_execution_digests)) != len(
            transfer_execution_digests
        ):
            errors.append(
                "transfer tasks must link distinct execution receipts"
            )
        hashed_output_digests = [
            digest
            for digest in transfer_output_digests
            if SHA256.fullmatch(digest)
        ]
        if len(set(hashed_output_digests)) != len(
            hashed_output_digests
        ):
            errors.append(
                "transfer execution output digests must be globally distinct"
            )
        errors.extend(
            _same_evidence_class(
                [
                    (f"transfer execution {digest}", receipt)
                    for digest, receipt in transfer_execution_receipts
                ],
                evidence_class,
            )
        )
        transfer_execution_receipts_validated = (
            len(errors) == transfer_error_start
            and len(transfer_tasks) >= 2
            and len(transfer_execution_receipts)
            == len(transfer_tasks)
            and len(transfer_execution_digests)
            == len(transfer_tasks)
            and len(transfer_output_digests)
            == 2 * len(transfer_tasks)
        )

    protected = loaded.get("protected")
    if protected is not None:
        if protected.get("activationReceiptSha256") != activation_digest:
            errors.append(
                "protected-suite activationReceiptSha256 does not match chain"
            )
        if protected.get("passed") is not True:
            errors.append("protected-suite passed must be true")
        if protected.get("exitStatus") != 0:
            errors.append("protected-suite exitStatus must be zero")
        if protected.get("regressionCount") != 0:
            errors.append("protected-suite regressionCount must be zero")
        if protected.get("unsafeAcceptanceCount") != 0:
            errors.append(
                "protected-suite unsafeAcceptanceCount must be zero"
            )
        errors.extend(
            _blob_errors(
                store,
                protected.get("suiteManifestSha256"),
                "protected-suite manifest",
                store_fd=store_fd,
            )
        )
        errors.extend(
            _blob_errors(
                store,
                protected.get("outputSha256"),
                "protected-suite output",
                store_fd=store_fd,
            )
        )

    rollback = loaded.get("rollback")
    if rollback is not None:
        if rollback.get("activationReceiptSha256") != activation_digest:
            errors.append("rollback activationReceiptSha256 does not match chain")
        if rollback.get("passed") is not True:
            errors.append("rollback passed must be true")
        if rollback.get("exitStatus") != 0:
            errors.append("rollback exitStatus must be zero")
        if activation is not None and (
            rollback.get("restoredBundleSha256")
            != activation.get("baseVerifierSha256")
        ):
            errors.append("rollback did not restore the base verifier hash")
        errors.extend(
            _blob_errors(
                store,
                rollback.get("outputSha256"),
                "rollback output",
                store_fd=store_fd,
            )
        )

    lean = loaded.get("lean")
    if lean is not None:
        if lean.get("activationReceiptSha256") != activation_digest:
            errors.append("Lean activationReceiptSha256 does not match chain")
        if lean.get("passed") is not True or lean.get("exitStatus") != 0:
            errors.append("Lean receipt must record a passing zero-exit check")
        if lean.get("noUnsafeEscapes") is not True:
            errors.append("Lean receipt noUnsafeEscapes must be true")
        command = lean.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part for part in command)
        ):
            errors.append("Lean command must be a non-empty argv list")
        timeout = lean.get("timeoutSec")
        if not isinstance(timeout, int) or timeout <= 0:
            errors.append("Lean timeoutSec must be a positive integer")
        for field in ("sourceSha256", "stdoutSha256", "stderrSha256"):
            errors.extend(
                _blob_errors(
                    store,
                    lean.get(field),
                    f"Lean {field}",
                    store_fd=store_fd,
                )
            )

    report = {
        "schema": "goai-frontier-receipt-validation/v1",
        "status": "PASS" if not errors else "INVALID",
        "chainSha256": chain_digest,
        "extensionId": extension_id,
        "domain": domain,
        "generatorFamily": generator_family,
        "extensionClass": extension_class,
        "triggerTaskId": trigger_task_id,
        "taskManifestSha256": chain.get("taskManifestSha256"),
        "transferTaskManifestSha256": chain.get(
            "transferTaskManifestSha256"
        ),
        "evidenceClass": evidence_class,
        "receiptCount": (
            len(loaded)
            + len(decisions)
            + len(transfer_execution_receipts)
            + 1
        ),
        "transferTaskIds": sorted(transfer_task_ids),
        "transferExecutionReceiptSha256s": sorted(
            transfer_execution_digests
        ),
        "transferExecutionBindings": sorted(
            transfer_execution_bindings,
            key=lambda value: (
                value["taskId"],
                value["pairId"],
                value["safetyTaskId"],
            ),
        ),
        "transferExecutionReceiptsValidated": (
            transfer_execution_receipts_validated
        ),
        "reviewDecisionSha256s": sorted(map(str, decision_digests)),
        "protectedSuiteReceiptSha256": chain.get(
            "protectedSuiteReceiptSha256"
        ),
        "errors": errors,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return errors, report


def validate_result_receipts(
    store: Path,
    result: dict[str, Any],
    *,
    required_evidence_class: str | None = None,
    task: dict[str, Any] | None = None,
    task_manifest_sha256: str | None = None,
    transfer_task_manifest_sha256: str | None = None,
    known_transfer_tasks: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Validate and cross-check a scored proposed-arm result row."""
    chain_digest = str(result.get("extensionReceiptSha256") or "")
    errors, report = validate_extension_chain(
        store,
        chain_digest,
    )
    if errors:
        return errors
    if (
        required_evidence_class is not None
        and report.get("evidenceClass") != required_evidence_class
    ):
        errors.append(
            "extension receipt evidenceClass must be "
            f"{required_evidence_class!r}, got {report.get('evidenceClass')!r}"
        )
    if task_manifest_sha256 is not None and (
        report.get("taskManifestSha256") != task_manifest_sha256
    ):
        errors.append("extension chain task manifest hash does not match scorer input")
    if transfer_task_manifest_sha256 is not None and (
        report.get("transferTaskManifestSha256")
        != transfer_task_manifest_sha256
    ):
        errors.append(
            "extension chain transfer task manifest hash does not match scorer input"
        )
    if task is not None:
        expected = {
            "taskId": str(task.get("taskId") or ""),
            "pairId": str(task.get("pairId") or ""),
            "domain": str(task.get("domain") or ""),
            "generatorFamily": str(task.get("generatorFamily") or ""),
            "extensionClass": str(task.get("extensionClass") or ""),
        }
        for field, value in expected.items():
            if str(result.get(field) or "") != value:
                errors.append(f"result {field} does not match manifest task")
        for field in ("domain", "generatorFamily", "extensionClass"):
            if report.get(field) != expected[field]:
                errors.append(f"extension chain {field} does not match manifest task")
        if report.get("triggerTaskId") != expected["taskId"]:
            errors.append(
                "extension chain triggerTaskId does not match scored manifest task"
            )
    result_decisions = sorted(
        str(value) for value in result.get("reviewDecisionSha256s") or []
    )
    if result_decisions != report["reviewDecisionSha256s"]:
        errors.append("result review decision hashes do not match extension chain")
    result_transfer = sorted(
        str(value) for value in result.get("transferTaskIds") or []
    )
    if result_transfer != report["transferTaskIds"]:
        errors.append("result transfer task IDs do not match extension chain")
    if known_transfer_tasks is not None and task is not None:
        sealed_transfer_siblings = 0
        transfer_pair_ids: set[str] = set()
        execution_bindings = {
            str(value.get("taskId") or ""): value
            for value in report.get("transferExecutionBindings", [])
            if isinstance(value, dict)
        }
        for transfer_id in report["transferTaskIds"]:
            transfer_task = known_transfer_tasks.get(transfer_id)
            if transfer_task is None:
                errors.append(f"transfer task ID is absent from sealed manifest: {transfer_id}")
                continue
            valid_sibling = True
            if transfer_task.get("domain") != task.get("domain"):
                errors.append(f"transfer task domain mismatch: {transfer_id}")
                valid_sibling = False
            if transfer_task.get("generatorFamily") != task.get("generatorFamily"):
                errors.append(f"transfer task family mismatch: {transfer_id}")
                valid_sibling = False
            if transfer_task.get("extensionClass") != task.get("extensionClass"):
                errors.append(f"transfer task extension class mismatch: {transfer_id}")
                valid_sibling = False
            if transfer_task.get("component") != "transfer":
                errors.append(f"transfer task must be an auxiliary transfer task: {transfer_id}")
                valid_sibling = False
            member = str(transfer_task.get("member") or "")
            if member != "valid":
                errors.append(f"transfer task must be a valid member: {transfer_id}")
                valid_sibling = False
            binding = execution_bindings.get(transfer_id)
            if binding is None:
                errors.append(
                    "transfer task is missing a descendant execution binding: "
                    f"{transfer_id}"
                )
                valid_sibling = False
            else:
                if binding.get("pairId") != transfer_task.get("pairId"):
                    errors.append(
                        "transfer execution pairId does not match sealed "
                        f"manifest: {transfer_id}"
                    )
                    valid_sibling = False
                safety_task_id = str(
                    binding.get("safetyTaskId") or ""
                )
                safety_task = known_transfer_tasks.get(safety_task_id)
                if safety_task is None:
                    errors.append(
                        "transfer execution safetyTaskId is absent from sealed "
                        f"manifest: {safety_task_id}"
                    )
                    valid_sibling = False
                elif (
                    safety_task.get("pairId") != transfer_task.get("pairId")
                    or safety_task.get("member") != "safety"
                    or safety_task.get("domain") != task.get("domain")
                    or safety_task.get("generatorFamily")
                    != task.get("generatorFamily")
                    or safety_task.get("extensionClass")
                    != task.get("extensionClass")
                ):
                    errors.append(
                        "transfer execution safety task does not match the "
                        f"sealed valid sibling: {transfer_id}"
                    )
                    valid_sibling = False
            if valid_sibling:
                sealed_transfer_siblings += 1
                transfer_pair_ids.add(str(transfer_task.get("pairId") or ""))
        if sealed_transfer_siblings < 2:
            errors.append(
                "extension chain requires at least two distinct sealed valid "
                "transfer siblings"
            )
        if sealed_transfer_siblings >= 2 and len(transfer_pair_ids) < 2:
            errors.append(
                "valid transfer siblings must come from at least two distinct "
                "auxiliary transfer pairs"
            )
        safety_pairs = {
            str(value.get("pairId") or "")
            for value in known_transfer_tasks.values()
            if value.get("component") == "transfer"
            and value.get("member") == "safety"
            and value.get("domain") == task.get("domain")
            and value.get("generatorFamily") == task.get("generatorFamily")
            and value.get("extensionClass") == task.get("extensionClass")
        }
        missing_safety_pairs = sorted(transfer_pair_ids - safety_pairs)
        if missing_safety_pairs:
            errors.append(
                "valid transfer siblings are missing paired sealed safety tasks: "
                + ", ".join(missing_safety_pairs)
            )
    if result.get("transferPassed") is not True:
        errors.append("result transferPassed must be true")
    if (
        result.get("protectedSuiteReceiptSha256")
        != report["protectedSuiteReceiptSha256"]
    ):
        errors.append(
            "result protected-suite receipt hash does not match extension chain"
        )
    if result.get("protectedSuitePassed") is not True:
        errors.append("result protectedSuitePassed must be true")
    return errors
