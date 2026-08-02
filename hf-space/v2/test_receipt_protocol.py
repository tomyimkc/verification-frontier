#!/usr/bin/env python3
"""Tests for the content-addressed extension receipt protocol."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

from v2 import build_receipt_rehearsal as rehearsal
from v2.build_receipt_rehearsal import (
    STORE_MARKER,
    STORE_MARKER_CONTENT,
    build,
    build_chain,
)
from v2.receipt_protocol import (
    canonical_json_bytes,
    load_receipt,
    validate_extension_chain,
    validate_result_receipts,
    write_blob,
    write_receipt,
)


class ReceiptProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = root / "receipts"
        self.index = root / "index.json"
        self.validation = root / "validation.json"
        errors, report = build(self.store, self.index, self.validation)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.index_payload = json.loads(self.index.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def chain_for(self, domain: str) -> str:
        for digest in self.index_payload["chainSha256s"]:
            receipt, errors = load_receipt(self.store, digest)
            self.assertEqual(errors, [])
            assert receipt is not None
            if receipt["domain"] == domain:
                return digest
        raise AssertionError(f"missing {domain} chain")

    def test_three_development_chains_pass(self) -> None:
        self.assertEqual(self.index_payload["receiptCount"], 34)
        self.assertEqual(self.index_payload["blobCount"], 60)
        for digest in self.index_payload["chainSha256s"]:
            errors, report = validate_extension_chain(self.store, digest)
            self.assertEqual(errors, [])
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["evidenceClass"], "development-only")
            self.assertEqual(
                len(report["transferExecutionReceiptSha256s"]),
                2,
            )
            self.assertTrue(
                report["transferExecutionReceiptsValidated"]
            )
            self.assertTrue(report["candidateOnly"])
            self.assertFalse(report["canClaimAGI"])

    def test_missing_transfer_execution_receipt_fails_closed(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        execution_digest = transfer["transferTasks"][0][
            "executionReceiptSha256"
        ]
        (self.store / f"{execution_digest}.json").unlink()
        errors, report = validate_extension_chain(self.store, digest)
        self.assertTrue(
            any("missing receipt file" in error for error in errors)
        )
        self.assertFalse(
            report["transferExecutionReceiptsValidated"]
        )
        self.assertEqual(report["status"], "INVALID")

    def test_duplicate_transfer_task_binding_is_rejected(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        duplicate_parent = copy.deepcopy(transfer["transferTasks"][0])
        execution, errors = load_receipt(
            self.store,
            duplicate_parent["executionReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert execution is not None
        execution["validOutputSha256"] = write_blob(
            self.store,
            b"distinct replayed valid output",
        )
        execution["safetyOutputSha256"] = write_blob(
            self.store,
            b"distinct replayed safety output",
        )
        duplicate_parent["executionReceiptSha256"] = write_receipt(
            self.store,
            execution,
        )
        transfer["transferTasks"].append(duplicate_parent)
        chain["transferReceiptSha256"] = write_receipt(
            self.store,
            transfer,
        )
        forged_digest = write_receipt(self.store, chain)
        forged_errors, report = validate_extension_chain(
            self.store,
            forged_digest,
        )
        self.assertTrue(
            any(
                "duplicate transfer taskId" in error
                for error in forged_errors
            ),
            forged_errors,
        )
        self.assertFalse(
            report["transferExecutionReceiptsValidated"]
        )

    def test_duplicate_transfer_pair_id_is_rejected(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        first_parent, second_parent = transfer["transferTasks"]
        second_execution, errors = load_receipt(
            self.store,
            second_parent["executionReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert second_execution is not None
        second_parent["pairId"] = first_parent["pairId"]
        second_execution["pairId"] = first_parent["pairId"]
        second_parent["executionReceiptSha256"] = write_receipt(
            self.store,
            second_execution,
        )
        chain["transferReceiptSha256"] = write_receipt(
            self.store,
            transfer,
        )
        forged_digest = write_receipt(self.store, chain)
        forged_errors, report = validate_extension_chain(
            self.store,
            forged_digest,
        )
        self.assertIn(
            "transfer receipt contains duplicate transfer pairId values",
            forged_errors,
        )
        self.assertFalse(
            report["transferExecutionReceiptsValidated"]
        )

    def test_transfer_execution_receipt_reuse_is_rejected(self) -> None:
        digest = self.chain_for("lean")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        transfer["transferTasks"][1]["executionReceiptSha256"] = (
            transfer["transferTasks"][0]["executionReceiptSha256"]
        )
        chain["transferReceiptSha256"] = write_receipt(
            self.store,
            transfer,
        )
        forged_digest = write_receipt(self.store, chain)
        forged_errors, report = validate_extension_chain(
            self.store,
            forged_digest,
        )
        self.assertIn(
            "transfer tasks must link distinct execution receipts",
            forged_errors,
        )
        self.assertFalse(
            report["transferExecutionReceiptsValidated"]
        )

    def test_cross_descendant_output_digest_reuse_is_rejected(self) -> None:
        digest = self.chain_for("symbolic")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        first_parent, second_parent = transfer["transferTasks"]
        first_execution, errors = load_receipt(
            self.store,
            first_parent["executionReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert first_execution is not None
        second_execution, errors = load_receipt(
            self.store,
            second_parent["executionReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert second_execution is not None
        second_execution["validOutputSha256"] = first_execution[
            "validOutputSha256"
        ]
        second_parent["executionReceiptSha256"] = write_receipt(
            self.store,
            second_execution,
        )
        chain["transferReceiptSha256"] = write_receipt(
            self.store,
            transfer,
        )
        forged_digest = write_receipt(self.store, chain)
        forged_errors, report = validate_extension_chain(
            self.store,
            forged_digest,
        )
        self.assertIn(
            "transfer execution output digests must be globally distinct",
            forged_errors,
        )
        self.assertFalse(
            report["transferExecutionReceiptsValidated"]
        )

    def test_transfer_valid_and_safety_outputs_must_be_distinct(self) -> None:
        digest = self.chain_for("symbolic")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        parent = transfer["transferTasks"][0]
        execution, errors = load_receipt(
            self.store,
            parent["executionReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert execution is not None
        execution["safetyOutputSha256"] = execution[
            "validOutputSha256"
        ]
        parent["executionReceiptSha256"] = write_receipt(
            self.store,
            execution,
        )
        chain["transferReceiptSha256"] = write_receipt(
            self.store,
            transfer,
        )
        forged_digest = write_receipt(self.store, chain)
        forged_errors, report = validate_extension_chain(
            self.store,
            forged_digest,
        )
        self.assertTrue(
            any(
                "valid and safety output digests must differ" in error
                for error in forged_errors
            ),
            forged_errors,
        )
        self.assertFalse(
            report["transferExecutionReceiptsValidated"]
        )

    def test_tampered_receipt_fails_content_hash(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        proposal_digest = chain["proposalSha256"]
        path = self.store / f"{proposal_digest}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["taskId"] = "tampered"
        path.write_bytes(canonical_json_bytes(payload))
        errors, report = validate_extension_chain(self.store, digest)
        self.assertTrue(any("content hash mismatch" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")

    def test_missing_reviewer_receipt_fails_closed(self) -> None:
        digest = self.chain_for("symbolic")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        missing = chain["reviewDecisionSha256s"][0]
        (self.store / f"{missing}.json").unlink()
        errors, report = validate_extension_chain(self.store, digest)
        self.assertTrue(any("missing receipt file" in error for error in errors))
        self.assertTrue(any("owner and expert-ai" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")

    def test_missing_evidence_blob_fails_closed(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        proposal, errors = load_receipt(self.store, chain["proposalSha256"])
        self.assertEqual(errors, [])
        assert proposal is not None
        candidate = proposal["candidateSha256"]
        (self.store / "blobs" / f"{candidate}.blob").unlink()
        errors, report = validate_extension_chain(self.store, digest)
        self.assertTrue(any("missing evidence blob" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")

    def test_write_blob_rejects_symlinked_or_non_directory_blob_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            outside = root / "outside"
            store.mkdir()
            outside.mkdir()
            (store / "blobs").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                ValueError,
                "receipt blob directory must not be a symlink",
            ):
                write_blob(store, b"must stay inside the receipt store")
            self.assertEqual(list(outside.iterdir()), [])

        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            store.mkdir()
            (store / "blobs").write_text("not a directory\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "receipt blob directory must be a directory",
            ):
                write_blob(store, b"must not replace a non-directory")

    def test_receipt_writers_reject_symlinked_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            store = root / "store"
            store.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                ValueError,
                "receipt store must not be a symlink",
            ):
                write_receipt(store, {"candidateOnly": True, "canClaimAGI": False})
            with self.assertRaisesRegex(
                ValueError,
                "receipt store must not be a symlink",
            ):
                write_blob(store, b"must not escape")
            self.assertEqual(list(outside.iterdir()), [])

    def test_unmarked_store_is_not_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "not-a-rehearsal"
            store.mkdir()
            unrelated = store / "unrelated.json"
            unrelated.write_text('{"keep": true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unmarked"):
                build(
                    store,
                    root / "index.json",
                    root / "validation.json",
                )
            self.assertTrue(unrelated.is_file())

    def test_empty_unmarked_store_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "empty-unmarked-store"
            store.mkdir()
            with self.assertRaisesRegex(ValueError, "unmarked"):
                build(
                    store,
                    root / "index.json",
                    root / "validation.json",
                )
            self.assertTrue(store.is_dir())
            self.assertEqual(list(store.iterdir()), [])

    def test_symlinked_store_is_not_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            (outside / STORE_MARKER).write_text("marker\n", encoding="utf-8")
            unrelated = outside / ("a" * 64 + ".json")
            unrelated.write_text('{"keep": true}\n', encoding="utf-8")
            store = root / "receipt-rehearsal"
            store.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinked receipt rehearsal store"):
                build(
                    store,
                    root / "index.json",
                    root / "validation.json",
                )
            self.assertTrue(unrelated.is_file())

    def test_ancestor_symlink_store_is_rejected_without_external_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            redirect = root / "redirect"
            redirect.symlink_to(outside, target_is_directory=True)
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path contains a symlink"):
                build(
                    redirect / "receipt-rehearsal",
                    root / "index.json",
                    root / "validation.json",
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((outside / "receipt-rehearsal").exists())

    def test_uid_zero_owned_redirect_is_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            redirect = root / "root-owned-redirect"
            redirect.symlink_to(outside, target_is_directory=True)
            original_lstat = Path.lstat

            def lstat_with_root_owner(path: Path):
                metadata = original_lstat(path)
                if path == redirect:
                    return SimpleNamespace(
                        st_mode=metadata.st_mode,
                        st_uid=0,
                    )
                return metadata

            with mock.patch.object(Path, "lstat", lstat_with_root_owner):
                with self.assertRaisesRegex(ValueError, "path contains a symlink"):
                    build(
                        redirect / "receipt-rehearsal",
                        root / "index.json",
                        root / "validation.json",
                    )
            self.assertEqual(list(outside.iterdir()), [])

    def test_tmp_alias_cannot_make_two_sidecars_alias_the_same_file(self) -> None:
        if Path("/tmp").resolve() != Path("/private/tmp").resolve():
            self.skipTest("macOS /tmp alias is unavailable")
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            canonical_root = Path(tmp)
            alias_root = Path("/tmp") / canonical_root.relative_to("/private/tmp")
            with self.assertRaisesRegex(ValueError, "must be distinct paths"):
                build(
                    canonical_root / "store",
                    alias_root / "same-sidecar.json",
                    canonical_root / "same-sidecar.json",
                )

    def test_casefold_aliases_cannot_make_two_sidecars_the_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = root / "CaseDir"
            case_dir.mkdir()
            with self.assertRaisesRegex(ValueError, "must be distinct paths"):
                build(
                    root / "store",
                    case_dir / "same.json",
                    root / "casedir" / "same.json",
                )

    def test_symlinked_blob_directory_is_not_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "receipt-rehearsal"
            store.mkdir()
            (store / STORE_MARKER).write_text(
                STORE_MARKER_CONTENT,
                encoding="utf-8",
            )
            outside = root / "outside"
            outside.mkdir()
            unrelated = outside / ("b" * 64 + ".blob")
            unrelated.write_bytes(b"keep")
            local_receipt = store / ("c" * 64 + ".json")
            local_receipt.write_text('{"keep": true}\n', encoding="utf-8")
            (store / "blobs").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                ValueError,
                "unrelated entries|symlinked receipt rehearsal blob directory",
            ):
                build(
                    store,
                    root / "index.json",
                    root / "validation.json",
                )
            self.assertEqual(unrelated.read_bytes(), b"keep")
            self.assertTrue(local_receipt.is_file())

    def test_symlinked_sidecars_are_replaced_without_modifying_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_target = root / "index-target.txt"
            validation_target = root / "validation-target.txt"
            index_target.write_text("keep-index\n", encoding="utf-8")
            validation_target.write_text("keep-validation\n", encoding="utf-8")
            index = root / "index.json"
            validation = root / "validation.json"
            index.symlink_to(index_target)
            validation.symlink_to(validation_target)
            errors, report = build(root / "store", index, validation)
            self.assertEqual(errors, [])
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(index.is_symlink())
            self.assertFalse(validation.is_symlink())
            self.assertEqual(
                index_target.read_text(encoding="utf-8"),
                "keep-index\n",
            )
            self.assertEqual(
                validation_target.read_text(encoding="utf-8"),
                "keep-validation\n",
            )

    def test_failed_rebuild_preserves_previous_store_and_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            before_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            before_index = index.read_bytes()
            before_validation = validation.read_bytes()
            with mock.patch(
                "v2.build_receipt_rehearsal.build_chain",
                side_effect=RuntimeError("injected staging failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected staging failure"):
                    build(store, index, validation)
            after_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_store, before_store)
            self.assertEqual(index.read_bytes(), before_index)
            self.assertEqual(validation.read_bytes(), before_validation)

    def test_failed_first_sidecar_publication_rolls_back_store_and_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            before_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            before_index = index.read_bytes()
            before_validation = validation.read_bytes()
            original_atomic_write = rehearsal._atomic_write_at

            def fail_on_first_sidecar(
                path: Path,
                data: bytes,
                **kwargs,
            ) -> None:
                if path.name == index.name:
                    raise RuntimeError("injected first-sidecar publication failure")
                original_atomic_write(path, data, **kwargs)

            with mock.patch(
                "v2.build_receipt_rehearsal._atomic_write_at",
                side_effect=fail_on_first_sidecar,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "first-sidecar publication failure",
                ):
                    build(store, index, validation)
            after_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_store, before_store)
            self.assertEqual(index.read_bytes(), before_index)
            self.assertEqual(validation.read_bytes(), before_validation)

    def test_sidecar_publication_does_not_overwrite_unknown_racer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            canonical_index = rehearsal._canonical_target_path(index)
            unrelated = b'{"createdBy":"unknown-racer"}\n'
            original_link = os.link
            injected = False

            def inject_unknown_sidecar(src, dst, *args, **kwargs):
                nonlocal injected
                if (
                    not injected
                    and kwargs.get("src_dir_fd") is not None
                    and kwargs.get("dst_dir_fd") is not None
                    and str(dst) == canonical_index.name
                ):
                    descriptor = os.open(
                        dst,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=kwargs["dst_dir_fd"],
                    )
                    try:
                        os.write(descriptor, unrelated)
                    finally:
                        os.close(descriptor)
                    injected = True
                return original_link(src, dst, *args, **kwargs)

            with mock.patch(
                "v2.build_receipt_rehearsal.os.link",
                side_effect=inject_unknown_sidecar,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "unknown receipt rehearsal sidecar|unknown post-crash target",
                ):
                    build(store, index, validation)
            self.assertTrue(injected)
            self.assertEqual(canonical_index.read_bytes(), unrelated)

    def test_startup_recovers_prepared_partial_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            before_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            before_index = index.read_bytes()
            before_validation = validation.read_bytes()
            targets = tuple(
                rehearsal._canonical_target_path(path)
                for path in (store, index, validation)
            )
            new_fingerprints = tuple(
                rehearsal._path_fingerprint(
                    target,
                    is_store=position == 0,
                )
                for position, target in enumerate(targets)
            )
            transaction = rehearsal._transaction_payload(
                targets,
                "a" * 32,
                phase="prepared",
                new_fingerprints=new_fingerprints,
            )
            journal = rehearsal._transaction_journal_path(*targets)
            rehearsal._atomic_write(
                journal,
                canonical_json_bytes(transaction),
            )
            for entry in transaction["entries"]:
                os.replace(entry["target"], entry["backup"])
            shutil.copytree(
                Path(transaction["entries"][0]["backup"]),
                targets[0],
            )
            with mock.patch(
                "v2.build_receipt_rehearsal._build_generation_at",
                side_effect=RuntimeError("stop after startup recovery"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "stop after startup recovery",
                ):
                    build(store, index, validation)
            after_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_store, before_store)
            self.assertEqual(index.read_bytes(), before_index)
            self.assertEqual(validation.read_bytes(), before_validation)
            self.assertFalse(journal.exists())

    def test_prepared_recovery_survives_partial_new_store_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            targets = tuple(
                rehearsal._canonical_target_path(path)
                for path in (store, index, validation)
            )
            original_fingerprints = tuple(
                rehearsal._path_fingerprint(
                    target,
                    is_store=position == 0,
                )
                for position, target in enumerate(targets)
            )
            transaction = rehearsal._transaction_payload(
                targets,
                "f" * 32,
                phase="prepared",
                new_fingerprints=original_fingerprints,
            )
            journal = rehearsal._transaction_journal_path(*targets)
            rehearsal._atomic_write(
                journal,
                canonical_json_bytes(transaction),
            )
            for position, entry in enumerate(transaction["entries"]):
                target = Path(entry["target"])
                backup = Path(entry["backup"])
                os.replace(target, backup)
                if position == 0:
                    shutil.copytree(backup, target)
                else:
                    shutil.copy2(backup, target)

            original_rmtree = rehearsal.shutil.rmtree
            interrupted = False

            def interrupt_new_store_garbage_cleanup(
                path,
                *,
                dir_fd=None,
                **kwargs,
            ) -> None:
                nonlocal interrupted
                if not interrupted and ".garbage-" in str(path):
                    garbage = root / str(path)
                    receipt = next(garbage.glob("*.json"))
                    receipt.unlink()
                    interrupted = True
                    raise OSError("injected partial prepared cleanup")
                original_rmtree(path, dir_fd=dir_fd, **kwargs)

            with mock.patch(
                "v2.build_receipt_rehearsal.shutil.rmtree",
                side_effect=interrupt_new_store_garbage_cleanup,
            ):
                rehearsal._recover_publication_transaction(
                    journal,
                    targets,
                )
            self.assertTrue(interrupted)
            self.assertFalse(journal.exists())
            self.assertEqual(
                tuple(
                    rehearsal._path_fingerprint(
                        target,
                        is_store=position == 0,
                    )
                    for position, target in enumerate(targets)
                ),
                original_fingerprints,
            )

            errors, report = build(store, index, validation)
            self.assertEqual(errors, [])
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(
                (root / f".{store.name}.garbage-{'f' * 32}").exists()
            )

    def test_prepared_recovery_preserves_unknown_new_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            targets = tuple(
                rehearsal._canonical_target_path(path)
                for path in (store, index, validation)
            )
            index_bytes = index.read_bytes()
            new_fingerprints = (
                rehearsal._path_fingerprint(store, is_store=True),
                {
                    "kind": "file",
                    "sha256": __import__("hashlib").sha256(
                        index_bytes
                    ).hexdigest(),
                },
                rehearsal._path_fingerprint(
                    validation,
                    is_store=False,
                ),
            )
            index.unlink()
            transaction = rehearsal._transaction_payload(
                targets,
                "b" * 32,
                phase="prepared",
                new_fingerprints=new_fingerprints,
            )
            journal = rehearsal._transaction_journal_path(*targets)
            rehearsal._atomic_write(
                journal,
                canonical_json_bytes(transaction),
            )
            unrelated = b'{"createdBy":"another-process"}\n'
            index.write_bytes(unrelated)
            with self.assertRaisesRegex(
                ValueError,
                "unknown post-crash target",
            ):
                build(store, index, validation)
            self.assertEqual(index.read_bytes(), unrelated)
            self.assertTrue(journal.is_file())

    def test_committed_recovery_keeps_backups_on_unknown_current_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            targets = tuple(
                rehearsal._canonical_target_path(path)
                for path in (store, index, validation)
            )
            new_fingerprints = tuple(
                rehearsal._path_fingerprint(
                    target,
                    is_store=position == 0,
                )
                for position, target in enumerate(targets)
            )
            transaction = rehearsal._transaction_payload(
                targets,
                "c" * 32,
                phase="committed",
                new_fingerprints=new_fingerprints,
            )
            journal = rehearsal._transaction_journal_path(*targets)
            rehearsal._atomic_write(
                journal,
                canonical_json_bytes(transaction),
            )
            for position, entry in enumerate(transaction["entries"]):
                target = Path(entry["target"])
                backup = Path(entry["backup"])
                os.replace(target, backup)
                if position == 0:
                    shutil.copytree(backup, target)
                else:
                    shutil.copy2(backup, target)
            index.write_bytes(b'{"corrupted":true}\n')
            with self.assertRaisesRegex(
                ValueError,
                "target fingerprint mismatch",
            ):
                build(store, index, validation)
            self.assertTrue(journal.is_file())
            for entry in transaction["entries"]:
                self.assertTrue(os.path.lexists(entry["backup"]))

    def test_committed_recovery_survives_partial_store_backup_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            targets = tuple(
                rehearsal._canonical_target_path(path)
                for path in (store, index, validation)
            )
            new_fingerprints = tuple(
                rehearsal._path_fingerprint(
                    target,
                    is_store=position == 0,
                )
                for position, target in enumerate(targets)
            )
            transaction = rehearsal._transaction_payload(
                targets,
                "d" * 32,
                phase="committed",
                new_fingerprints=new_fingerprints,
            )
            journal = rehearsal._transaction_journal_path(*targets)
            rehearsal._atomic_write(
                journal,
                canonical_json_bytes(transaction),
            )
            for position, entry in enumerate(transaction["entries"]):
                target = Path(entry["target"])
                backup = Path(entry["backup"])
                os.replace(target, backup)
                if position == 0:
                    shutil.copytree(backup, target)
                else:
                    shutil.copy2(backup, target)

            original_rmtree = rehearsal.shutil.rmtree
            interrupted = False

            def interrupt_store_garbage_cleanup(
                path,
                *,
                dir_fd=None,
                **kwargs,
            ) -> None:
                nonlocal interrupted
                if not interrupted and ".garbage-" in str(path):
                    garbage = root / str(path)
                    receipt = next(garbage.glob("*.json"))
                    receipt.unlink()
                    interrupted = True
                    raise OSError("injected partial receipt backup cleanup")
                original_rmtree(path, dir_fd=dir_fd, **kwargs)

            with mock.patch(
                "v2.build_receipt_rehearsal.shutil.rmtree",
                side_effect=interrupt_store_garbage_cleanup,
            ):
                rehearsal._recover_publication_transaction(
                    journal,
                    targets,
                )
            self.assertTrue(interrupted)
            self.assertFalse(journal.exists())
            self.assertEqual(
                tuple(
                    rehearsal._path_fingerprint(
                        target,
                        is_store=position == 0,
                    )
                    for position, target in enumerate(targets)
                ),
                new_fingerprints,
            )

            errors, report = build(store, index, validation)
            self.assertEqual(errors, [])
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(
                (root / f".{store.name}.garbage-{'d' * 32}").exists()
            )

    def test_receipt_orphan_gc_preserves_unowned_pattern_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            targets = tuple(
                rehearsal._canonical_target_path(path)
                for path in (store, index, validation)
            )
            unrelated = root / f".{store.name}.garbage-{'e' * 32}"
            unrelated.mkdir()
            sentinel = unrelated / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            rehearsal._recover_publication_transaction(
                rehearsal._transaction_journal_path(*targets),
                targets,
            )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_exception_after_committed_journal_write_restores_previous_generation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            index = root / "index.json"
            validation = root / "validation.json"
            build(store, index, validation)
            before_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            before_index = index.read_bytes()
            before_validation = validation.read_bytes()
            original_atomic_write = rehearsal._atomic_write_at

            def raise_after_committed_journal(
                path: Path,
                data: bytes,
                **kwargs,
            ) -> None:
                original_atomic_write(path, data, **kwargs)
                try:
                    payload = json.loads(data)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return
                if (
                    payload.get("schema") == rehearsal.TRANSACTION_SCHEMA
                    and payload.get("phase") == "committed"
                ):
                    raise RuntimeError(
                        "injected post-commit-journal exception"
                    )

            with mock.patch(
                "v2.build_receipt_rehearsal._atomic_write_at",
                side_effect=raise_after_committed_journal,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "post-commit-journal exception",
                ):
                    build(store, index, validation)
            after_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_store, before_store)
            self.assertEqual(index.read_bytes(), before_index)
            self.assertEqual(validation.read_bytes(), before_validation)

    def test_non_sha_64_character_file_blocks_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            store.mkdir()
            (store / STORE_MARKER).write_text(
                STORE_MARKER_CONTENT,
                encoding="utf-8",
            )
            unrelated = store / ("z" * 64 + ".json")
            unrelated.write_text('{"keep": true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unrelated entries"):
                build(store, root / "index.json", root / "validation.json")
            self.assertTrue(unrelated.is_file())

    def test_sha_shaped_unrelated_file_blocks_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            store.mkdir()
            (store / STORE_MARKER).write_text(
                STORE_MARKER_CONTENT,
                encoding="utf-8",
            )
            unrelated = store / ("0" * 64 + ".json")
            unrelated.write_text('{"keep":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "bytes do not match its filename",
            ):
                build(store, root / "index.json", root / "validation.json")
            self.assertTrue(unrelated.is_file())

    def test_confirmatory_self_declaration_is_rejected(self) -> None:
        digest = self.chain_for("lean")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        chain["evidenceClass"] = "confirmatory"
        chain["confirmatoryEligible"] = True
        forged_digest = __import__("hashlib").sha256(
            canonical_json_bytes(chain)
        ).hexdigest()
        (self.store / f"{forged_digest}.json").write_bytes(
            canonical_json_bytes(chain)
        )
        errors, report = validate_extension_chain(self.store, forged_digest)
        self.assertTrue(any("confirmatory receipt validation is disabled" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")

    def test_nonstandard_json_constant_returns_invalid_without_raising(self) -> None:
        data = b'{"candidateOnly":true,"canClaimAGI":false,"x":NaN}\n'
        digest = __import__("hashlib").sha256(data).hexdigest()
        path = self.store / f"{digest}.json"
        path.write_bytes(data)
        receipt, errors = load_receipt(self.store, digest)
        self.assertIsNone(receipt)
        self.assertTrue(any("invalid receipt JSON" in error for error in errors))

    def test_explicit_empty_transfer_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "two distinct transfer IDs"):
                build_chain(
                    Path(tmp) / "store",
                    "physics",
                    transfer_ids=[],
                )

    def test_content_address_publish_never_overwrites_racing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            original_link = os.link

            def inject_racing_destination(
                src: str,
                dst: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                fd = os.open(
                    dst,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=dst_dir_fd,
                )
                try:
                    os.write(fd, b"racing destination")
                finally:
                    os.close(fd)
                raise FileExistsError(dst)

            with mock.patch(
                "v2.receipt_protocol.os.link",
                side_effect=inject_racing_destination,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "collision or racing destination",
                ):
                    write_receipt(
                        store,
                        {"candidateOnly": True, "canClaimAGI": False},
                    )
            destinations = list(store.glob("*.json"))
            self.assertEqual(len(destinations), 1)
            self.assertEqual(destinations[0].read_bytes(), b"racing destination")
            self.assertIsNotNone(original_link)

    def test_content_address_publish_uses_one_directory_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            store.mkdir()
            moved = root / "moved-store"
            original_open = os.open
            redirected = False

            def rename_before_temp_open(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                nonlocal redirected
                if dir_fd is not None and not redirected:
                    store.rename(moved)
                    store.mkdir()
                    redirected = True
                return original_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with mock.patch(
                "v2.receipt_protocol.os.open",
                side_effect=rename_before_temp_open,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "directory changed during publication",
                ):
                    write_receipt(
                        store,
                        {"candidateOnly": True, "canClaimAGI": False},
                    )
            self.assertTrue(redirected)
            self.assertEqual(list(store.iterdir()), [])
            self.assertEqual(list(moved.iterdir()), [])

    def test_temp_creation_failure_closes_open_directory_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            store.mkdir()
            original_open = os.open
            captured: dict[str, int] = {}

            def fail_descriptor_relative_open(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                if dir_fd is None:
                    descriptor = original_open(path, flags, mode)
                    captured["directory"] = descriptor
                    return descriptor
                raise OSError("injected temporary creation failure")

            with mock.patch(
                "v2.receipt_protocol.os.open",
                side_effect=fail_descriptor_relative_open,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "temporary creation failure",
                ):
                    write_receipt(
                        store,
                        {"candidateOnly": True, "canClaimAGI": False},
                    )
            with self.assertRaises(OSError):
                os.fstat(captured["directory"])

    def test_atomic_write_fdopen_failure_closes_temporary_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output.json"
            captured: dict[str, int | str] = {}
            original_open = os.open

            def capture_temporary_open(
                name,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                descriptor = original_open(
                    name,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )
                if dir_fd is not None and str(name).startswith(".output.json-"):
                    captured["descriptor"] = descriptor
                    captured["name"] = str(name)
                return descriptor

            with (
                mock.patch(
                    "v2.build_receipt_rehearsal.os.open",
                    side_effect=capture_temporary_open,
                ),
                mock.patch(
                    "v2.build_receipt_rehearsal.os.fdopen",
                    side_effect=OSError("injected fdopen failure"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "fdopen failure"):
                    rehearsal._atomic_write(path, b"{}\n")
            descriptor = int(captured["descriptor"])
            with self.assertRaises(OSError):
                os.fstat(descriptor)
            self.assertFalse((path.parent / str(captured["name"])).exists())

    def test_atomic_write_parent_swap_does_not_touch_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "output"
            parent.mkdir()
            moved = root / "moved-output"
            outside = root / "outside"
            outside.mkdir()
            path = parent / "index.json"
            original_open = os.open
            swapped = False

            def swap_before_temporary_open(
                name,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                nonlocal swapped
                if (
                    dir_fd is not None
                    and str(name).startswith(".index.json-")
                    and not swapped
                ):
                    parent.rename(moved)
                    parent.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return original_open(
                    name,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with mock.patch(
                "v2.build_receipt_rehearsal.os.open",
                side_effect=swap_before_temporary_open,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "directory changed during publication",
                ):
                    rehearsal._atomic_write(path, b'{"safe":true}\n')
            self.assertTrue(swapped)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual(list(moved.iterdir()), [])

    def test_receipt_transaction_parent_swap_does_not_touch_outside_targets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "publication"
            parent.mkdir()
            moved = root / "moved-publication"
            outside = root / "outside"
            outside.mkdir()
            store = parent / "store"
            index = parent / "index.json"
            validation = parent / "validation.json"
            build(store, index, validation)
            original_store = {
                path.relative_to(store).as_posix(): path.read_bytes()
                for path in store.rglob("*")
                if path.is_file()
            }
            original_index = index.read_bytes()
            original_validation = validation.read_bytes()

            outside_store = outside / store.name
            outside_store.mkdir()
            (outside_store / "sentinel.txt").write_text(
                "outside-store\n",
                encoding="utf-8",
            )
            outside_index = outside / index.name
            outside_validation = outside / validation.name
            outside_index.write_bytes(b"outside-index\n")
            outside_validation.write_bytes(b"outside-validation\n")

            original_replace = os.replace
            swapped = False

            def swap_parent_before_first_backup(
                source,
                destination,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal swapped
                if (
                    src_dir_fd is not None
                    and dst_dir_fd is not None
                    and source == store.name
                    and str(destination).startswith(f".{store.name}.backup-")
                    and not swapped
                ):
                    parent.rename(moved)
                    parent.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return original_replace(
                    source,
                    destination,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            with mock.patch(
                "v2.build_receipt_rehearsal.os.replace",
                side_effect=swap_parent_before_first_backup,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "directory changed during publication",
                ):
                    build(store, index, validation)
            self.assertTrue(swapped)
            self.assertEqual(
                (outside_store / "sentinel.txt").read_text(encoding="utf-8"),
                "outside-store\n",
            )
            self.assertEqual(outside_index.read_bytes(), b"outside-index\n")
            self.assertEqual(
                outside_validation.read_bytes(),
                b"outside-validation\n",
            )
            self.assertEqual(
                {
                    path.relative_to(moved / store.name).as_posix():
                    path.read_bytes()
                    for path in (moved / store.name).rglob("*")
                    if path.is_file()
                },
                original_store,
            )
            self.assertEqual((moved / index.name).read_bytes(), original_index)
            self.assertEqual(
                (moved / validation.name).read_bytes(),
                original_validation,
            )

    def test_receipt_generation_parent_swap_does_not_touch_symlink_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "publication"
            parent.mkdir()
            moved = root / "moved-publication"
            outside = root / "outside"
            outside.mkdir()
            store = parent / "store"
            index = parent / "index.json"
            validation = parent / "validation.json"
            original_build_generation = rehearsal._build_generation_at
            swapped = False

            def swap_parent_before_generation(
                staging_descriptor: int,
                store_name: str,
            ):
                nonlocal swapped
                parent.rename(moved)
                parent.symlink_to(outside, target_is_directory=True)
                swapped = True
                return original_build_generation(
                    staging_descriptor,
                    store_name,
                )

            with mock.patch(
                "v2.build_receipt_rehearsal._build_generation_at",
                side_effect=swap_parent_before_generation,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "directory changed during publication",
                ):
                    build(store, index, validation)
            self.assertTrue(swapped)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual(list(moved.iterdir()), [])

    def test_result_row_must_match_chain_links(self) -> None:
        digest = self.chain_for("physics")
        errors, report = validate_extension_chain(self.store, digest)
        self.assertEqual(errors, [])
        result = {
            "extensionReceiptSha256": digest,
            "reviewDecisionSha256s": report["reviewDecisionSha256s"],
            "transferTaskIds": report["transferTaskIds"],
            "transferPassed": True,
            "protectedSuiteReceiptSha256": report[
                "protectedSuiteReceiptSha256"
            ],
            "protectedSuitePassed": True,
        }
        self.assertEqual(validate_result_receipts(self.store, result), [])
        result["transferTaskIds"] = ["unlinked-a", "unlinked-b"]
        errors = validate_result_receipts(self.store, result)
        self.assertIn(
            "result transfer task IDs do not match extension chain",
            errors,
        )

    def test_transfer_execution_binds_the_sealed_safety_sibling(self) -> None:
        digest = build_chain(
            self.store,
            "physics",
            generator_family="physics-family",
            extension_class="physics.class",
            trigger_task_id="trigger-valid",
            transfer_ids=["pair-a-valid", "pair-b-valid"],
        )
        errors, report = validate_extension_chain(self.store, digest)
        self.assertEqual(errors, [])
        task = {
            "taskId": "trigger-valid",
            "pairId": "trigger-pair",
            "domain": "physics",
            "component": "frontier",
            "member": "valid",
            "generatorFamily": "physics-family",
            "extensionClass": "physics.class",
        }
        known_tasks = {
            task_id: {
                **task,
                "taskId": task_id,
                "pairId": pair_id,
                "component": "transfer",
                "member": member,
            }
            for task_id, pair_id, member in (
                ("pair-a-valid", "pair-a", "valid"),
                ("pair-a-safety", "pair-a", "safety"),
                ("pair-b-valid", "pair-b", "valid"),
                ("pair-b-safety", "pair-b", "safety"),
            )
        }
        result = {
            **task,
            "extensionReceiptSha256": digest,
            "reviewDecisionSha256s": report["reviewDecisionSha256s"],
            "transferTaskIds": report["transferTaskIds"],
            "transferPassed": True,
            "protectedSuiteReceiptSha256": report[
                "protectedSuiteReceiptSha256"
            ],
            "protectedSuitePassed": True,
        }
        self.assertEqual(
            validate_result_receipts(
                self.store,
                result,
                task=task,
                task_manifest_sha256=report["taskManifestSha256"],
                known_transfer_tasks=known_tasks,
            ),
            [],
        )

        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        parent = transfer["transferTasks"][0]
        execution, errors = load_receipt(
            self.store,
            parent["executionReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert execution is not None
        parent["safetyTaskId"] = "pair-b-safety"
        execution["safetyTaskId"] = "pair-b-safety"
        parent["executionReceiptSha256"] = write_receipt(
            self.store,
            execution,
        )
        chain["transferReceiptSha256"] = write_receipt(
            self.store,
            transfer,
        )
        forged_digest = write_receipt(self.store, chain)
        forged_errors, forged_report = validate_extension_chain(
            self.store,
            forged_digest,
        )
        self.assertTrue(
            any(
                "duplicate safetyTaskId" in error
                for error in forged_errors
            ),
            forged_errors,
        )
        self.assertFalse(
            forged_report["transferExecutionReceiptsValidated"]
        )

    def test_result_cannot_reuse_chain_across_domain_or_family(self) -> None:
        digest = self.chain_for("physics")
        errors, report = validate_extension_chain(self.store, digest)
        self.assertEqual(errors, [])
        task = {
            "taskId": "lean-unrelated-valid",
            "domain": "lean",
            "generatorFamily": "unrelated.lean.family",
            "extensionClass": "lean.unrelated",
        }
        result = {
            **task,
            "extensionReceiptSha256": digest,
            "reviewDecisionSha256s": report["reviewDecisionSha256s"],
            "transferTaskIds": report["transferTaskIds"],
            "transferPassed": True,
            "protectedSuiteReceiptSha256": report[
                "protectedSuiteReceiptSha256"
            ],
            "protectedSuitePassed": True,
        }
        errors = validate_result_receipts(
            self.store,
            result,
            task=task,
            task_manifest_sha256=report["taskManifestSha256"],
        )
        self.assertIn(
            "extension chain domain does not match manifest task",
            errors,
        )
        self.assertIn(
            "extension chain generatorFamily does not match manifest task",
            errors,
        )

    def test_chain_trigger_must_match_scored_task(self) -> None:
        digest = self.chain_for("physics")
        errors, report = validate_extension_chain(self.store, digest)
        self.assertEqual(errors, [])
        task = {
            "taskId": "different-physics-trigger",
            "pairId": "different-physics-trigger-pair",
            "domain": report["domain"],
            "component": "frontier",
            "generatorFamily": report["generatorFamily"],
            "extensionClass": report["extensionClass"],
            "member": "valid",
        }
        result = {
            **task,
            "extensionReceiptSha256": digest,
            "reviewDecisionSha256s": report["reviewDecisionSha256s"],
            "transferTaskIds": report["transferTaskIds"],
            "transferPassed": True,
            "protectedSuiteReceiptSha256": report[
                "protectedSuiteReceiptSha256"
            ],
            "protectedSuitePassed": True,
        }
        known_tasks = {
            task["taskId"]: task,
            **{
                transfer_id: {
                    **task,
                    "taskId": transfer_id,
                    "pairId": "sealed-transfer-pair",
                    "member": member,
                }
                for transfer_id, member in zip(
                    report["transferTaskIds"],
                    ("valid", "safety"),
                    strict=True,
                )
            },
        }
        errors = validate_result_receipts(
            self.store,
            result,
            task=task,
            task_manifest_sha256=report["taskManifestSha256"],
            known_transfer_tasks=known_tasks,
        )
        self.assertIn(
            "extension chain triggerTaskId does not match scored manifest task",
            errors,
        )

    def test_trigger_cannot_count_as_transfer_sibling(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        transfer["transferTasks"][0]["taskId"] = chain["triggerTaskId"]
        chain["transferReceiptSha256"] = write_receipt(self.store, transfer)
        forged_chain_digest = write_receipt(self.store, chain)
        errors, report = validate_extension_chain(
            self.store,
            forged_chain_digest,
        )
        self.assertIn("trigger task cannot count as a transfer task", errors)
        self.assertEqual(report["status"], "INVALID")

    def test_transfer_receipt_trigger_must_match_chain(self) -> None:
        digest = self.chain_for("symbolic")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        transfer, errors = load_receipt(
            self.store,
            chain["transferReceiptSha256"],
        )
        self.assertEqual(errors, [])
        assert transfer is not None
        transfer["triggerTaskId"] = "different-trigger"
        chain["transferReceiptSha256"] = write_receipt(self.store, transfer)
        forged_chain_digest = write_receipt(self.store, chain)
        errors, report = validate_extension_chain(
            self.store,
            forged_chain_digest,
        )
        self.assertIn("transfer triggerTaskId does not match chain", errors)
        self.assertEqual(report["status"], "INVALID")

    def test_proposal_task_id_must_match_chain_trigger(self) -> None:
        digest = self.chain_for("physics")
        chain, errors = load_receipt(self.store, digest)
        self.assertEqual(errors, [])
        assert chain is not None
        proposal, errors = load_receipt(self.store, chain["proposalSha256"])
        self.assertEqual(errors, [])
        assert proposal is not None
        proposal["taskId"] = "different-proposal-task"
        chain["proposalSha256"] = write_receipt(self.store, proposal)
        forged_chain_digest = write_receipt(self.store, chain)
        errors, report = validate_extension_chain(
            self.store,
            forged_chain_digest,
        )
        self.assertIn(
            "proposal receipt taskId does not match chain triggerTaskId",
            errors,
        )
        self.assertEqual(report["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
