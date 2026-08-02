#!/usr/bin/env python3
"""Deterministic tests for the compact GOAI exploration environment."""
from __future__ import annotations

import copy
import json
import os
import stat
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle
import demo
import verify_artifacts
import verify_bundle
from v2 import protocol_twin, study_root


def _source_bundle() -> Path:
    return Path(__file__).resolve().parent / "dist" / (
        "GOAI-AI4R-Open-Exploration.zip"
    )


def _write_mutated_bundle(
    target: Path,
    *,
    replacements: dict[str, bytes] | None = None,
    additions: list[tuple[zipfile.ZipInfo, bytes]] | None = None,
    mutate_info=None,
) -> None:
    replacements = replacements or {}
    additions = additions or []
    prefix = "goai-ai4r-open-exploration/"
    manifest_name = prefix + "MANIFEST.sha256"
    with zipfile.ZipFile(_source_bundle()) as source:
        entries = [
            (copy.copy(info), source.read(info.filename))
            for info in source.infolist()
        ]
    payloads = {info.filename: data for info, data in entries}
    payloads.update(replacements)
    manifest_rows = payloads[manifest_name].decode("utf-8").splitlines()
    changed_names = set(replacements)
    changed_names.update(info.filename for info, _ in additions)
    for name in sorted(changed_names):
        if name == manifest_name or not name.startswith(prefix):
            continue
        relative = name.removeprefix(prefix)
        data = (
            replacements[name]
            if name in replacements
            else next(data for info, data in additions if info.filename == name)
        )
        replacement_row = f"{verify_bundle.sha256(data)}  {relative}"
        for index, row in enumerate(manifest_rows):
            if row.endswith(f"  {relative}"):
                manifest_rows[index] = replacement_row
                break
        else:
            manifest_rows.append(replacement_row)
    payloads[manifest_name] = (
        "\n".join(manifest_rows) + "\n"
    ).encode("utf-8")

    with zipfile.ZipFile(target, "w") as archive:
        for info, original_data in entries:
            if mutate_info is not None:
                info = mutate_info(info)
            archive.writestr(info, payloads.get(info.filename, original_data))
        for info, data in additions:
            archive.writestr(info, data)


class VerificationEnvironmentTests(unittest.TestCase):
    def test_dimension_trap_is_rejected(self) -> None:
        result = demo.verify_physics("9.8 m/s^2", "9.8 m/s")
        self.assertEqual(result.verdict, "rejected")
        self.assertEqual(result.reason_code, "dimension_mismatch")

    def test_open_unformalized_never_accepts(self) -> None:
        problem = demo.PROBLEM_BY_ID["riemann-zeros"]
        for proposal in ("", "have h : True := trivial", "a polished proof sketch"):
            with self.subTest(proposal=proposal):
                result = demo.verify_problem(problem, proposal)
                self.assertEqual(result.verdict, "abstain")
                self.assertEqual(result.reason_code, "unsupported_specification")

    def test_proof_placeholder_is_rejected_before_coverage_abstention(self) -> None:
        problem = demo.PROBLEM_BY_ID["riemann-zeros"]
        result = demo.verify_problem(problem, "by\n  sorry")
        self.assertEqual(result.verdict, "rejected")
        self.assertEqual(result.reason_code, "proof_placeholder")

    def test_scripted_refinement_is_multistep(self) -> None:
        records = demo.run_episode(
            demo.PROBLEM_BY_ID["free-fall"],
            "scripted-refine",
        )
        self.assertEqual([record.verdict for record in records], ["rejected", "accepted"])
        self.assertEqual(records[0].next_action, "revise")
        self.assertEqual(records[-1].next_action, "keep_and_stop")

    def test_symbolic_tier_is_explicit_about_availability(self) -> None:
        result = demo.verify_math("x^2+2*x+1", "(x+1)^2")
        if demo._sympy_available():
            self.assertEqual(result.verdict, "accepted")
        else:
            self.assertEqual(result.verdict, "abstain")
            self.assertEqual(result.reason_code, "sympy_unavailable")

    def test_symbolic_parser_never_evaluates_python(self) -> None:
        if not demo._sympy_available():
            self.skipTest("SymPy is unavailable")
        attacks = (
            'eval("0")',
            'exec("x=1")',
            '__import__("os")',
            "(1).__class__",
            "x[0]",
            "'string'",
            "x**1000",
            "((((((2**16)**16)**16)**16)**16)**16)",
            "x" * (demo.MAX_SYMBOLIC_INPUT_CHARS + 1),
        )
        with mock.patch("builtins.eval") as forbidden_eval:
            for attack in attacks:
                with self.subTest(attack=attack):
                    result = demo.verify_math(attack, "0")
                    self.assertEqual(result.verdict, "abstain")
                    self.assertEqual(result.reason_code, "expression_unparseable")
        forbidden_eval.assert_not_called()

    def test_symbolic_length_cap_applies_after_caret_normalization(self) -> None:
        source = "^" * demo.MAX_SYMBOLIC_INPUT_CHARS
        with mock.patch.object(demo.ast, "parse") as parse:
            with self.assertRaisesRegex(ValueError, "length limit"):
                demo._safe_sympy_expression(source, None)
        parse.assert_not_called()

    def test_benchmark_artifacts_preserve_claim_ceiling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-test-") as tmp:
            output_dir = Path(tmp)
            summary = demo.run_benchmark(output_dir)
            self.assertTrue(summary["candidateOnly"])
            self.assertFalse(summary["canClaimAGI"])
            self.assertTrue((output_dir / "episodes.jsonl").is_file())
            self.assertTrue((output_dir / "benchmark-summary.json").is_file())
            rows = [
                json.loads(line)
                for line in (output_dir / "episodes.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertGreater(len(rows), 0)
            self.assertFalse(
                any(
                    row["rung"] == "open-unformalized"
                    and row["verdict"] == "accepted"
                    for row in rows
                )
            )

    def test_terminal_receipt_requires_episode_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-artifact-test-") as tmp:
            output_dir = Path(tmp)
            demo.run_benchmark(output_dir)
            rows = [
                json.loads(line)
                for line in (output_dir / "episodes.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            terminal = next(row for row in rows if row["terminal"])
            terminal.pop("episode_id")
            (output_dir / "episodes.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            errors = verify_artifacts.validate(output_dir)
            self.assertTrue(
                any("terminal row missing episode_id" in error for error in errors),
                errors,
            )

    def test_bundle_validator_handles_missing_and_corrupt_archives(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            root = Path(tmp)
            missing_errors = verify_bundle.validate(root / "missing.zip")
            self.assertTrue(any("missing bundle" in error for error in missing_errors))
            corrupt = root / "corrupt.zip"
            corrupt.write_bytes(b"not a zip")
            corrupt_errors = verify_bundle.validate(corrupt)
            self.assertTrue(any("invalid bundle" in error for error in corrupt_errors))

    def test_committed_bundle_is_valid(self) -> None:
        errors = verify_bundle.validate(_source_bundle())
        self.assertEqual(errors, [], errors)

    def test_bundle_builder_rejects_required_source_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-source-symlink-") as tmp:
            root = Path(tmp)
            outside = root / "outside-secret.txt"
            outside.write_text("SECRET-BYTES\n", encoding="utf-8")
            required = root / "required.txt"
            required.symlink_to(outside)
            dist = root / "dist"
            with (
                mock.patch.object(build_bundle, "ROOT", root),
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", dist / "bundle.zip"),
                mock.patch.object(
                    build_bundle,
                    "CHECKSUM",
                    dist / "bundle.zip.sha256",
                ),
                mock.patch.object(build_bundle, "REQUIRED", {"required.txt"}),
                mock.patch.object(
                    build_bundle,
                    "receipt_rehearsal_files",
                    return_value=set(),
                ),
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "must not be a symlink",
                ):
                    build_bundle.main()

    def test_bundle_builder_rejects_source_swapped_to_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-source-swap-") as tmp:
            root = Path(tmp)
            outside = root / "outside-secret.txt"
            outside.write_text("SECRET-BYTES\n", encoding="utf-8")
            required = root / "required.txt"
            required.write_text("safe bytes\n", encoding="utf-8")
            dist = root / "dist"
            original_open = build_bundle.os.open
            swapped = False

            def swap_before_final_open(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                nonlocal swapped
                if path == "required.txt" and dir_fd is not None and not swapped:
                    required.unlink()
                    required.symlink_to(outside)
                    swapped = True
                return original_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with (
                mock.patch.object(build_bundle, "ROOT", root),
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", dist / "bundle.zip"),
                mock.patch.object(
                    build_bundle,
                    "CHECKSUM",
                    dist / "bundle.zip.sha256",
                ),
                mock.patch.object(build_bundle, "REQUIRED", {"required.txt"}),
                mock.patch.object(
                    build_bundle,
                    "receipt_rehearsal_files",
                    return_value=set(),
                ),
                mock.patch.object(
                    build_bundle.os,
                    "open",
                    side_effect=swap_before_final_open,
                ),
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "unable to safely open|required source changed",
                ):
                    build_bundle.main()
            self.assertTrue(swapped)

    def test_bundle_builder_preserves_previous_outputs_on_archive_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-failure-") as tmp:
            root = Path(tmp)
            (root / "required.txt").write_text("safe\n", encoding="utf-8")
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"previous bundle")
            checksum.write_bytes(b"previous checksum")
            with (
                mock.patch.object(build_bundle, "ROOT", root),
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
                mock.patch.object(build_bundle, "REQUIRED", {"required.txt"}),
                mock.patch.object(
                    build_bundle,
                    "receipt_rehearsal_files",
                    return_value=set(),
                ),
                mock.patch.object(
                    build_bundle.zipfile.ZipFile,
                    "writestr",
                    side_effect=OSError("injected archive write failure"),
                ),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "archive write failure",
                ):
                    build_bundle.main()
            self.assertEqual(bundle.read_bytes(), b"previous bundle")
            self.assertEqual(checksum.read_bytes(), b"previous checksum")

    def test_bundle_directory_exchange_preserves_previous_on_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-publish-") as tmp:
            root = Path(tmp)
            (root / "required.txt").write_text("safe\n", encoding="utf-8")
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"previous bundle")
            checksum.write_bytes(b"previous checksum")

            with (
                mock.patch.object(build_bundle, "ROOT", root),
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
                mock.patch.object(build_bundle, "REQUIRED", {"required.txt"}),
                mock.patch.object(
                    build_bundle,
                    "receipt_rehearsal_files",
                    return_value=set(),
                ),
                mock.patch.object(verify_bundle, "validate", return_value=[]),
                mock.patch.object(
                    build_bundle,
                    "_exchange_directories",
                    side_effect=OSError(
                        "injected directory exchange failure"
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "directory exchange failure",
                ):
                    build_bundle.main()
            self.assertEqual(bundle.read_bytes(), b"previous bundle")
            self.assertEqual(checksum.read_bytes(), b"previous checksum")

    def test_bundle_post_exchange_fsync_failure_restores_previous_pair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-fsync-") as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"old bundle")
            checksum.write_bytes(b"old checksum")
            staged = root / f".dist.generation-{'b' * 32}"
            staged.mkdir()
            (staged / bundle.name).write_bytes(b"new bundle")
            (staged / checksum.name).write_bytes(b"new checksum")
            original_fsync = build_bundle.os.fsync
            failed = False

            def fail_first_parent_fsync_after_exchange(descriptor: int) -> None:
                nonlocal failed
                if (
                    not failed
                    and bundle.read_bytes() == b"new bundle"
                    and (staged / bundle.name).read_bytes() == b"old bundle"
                ):
                    failed = True
                    raise OSError("injected post-exchange fsync failure")
                original_fsync(descriptor)

            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
                mock.patch.object(
                    build_bundle.os,
                    "fsync",
                    side_effect=fail_first_parent_fsync_after_exchange,
                ),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "post-exchange fsync failure",
                ):
                    build_bundle._publish_bundle_directory(staged)
            self.assertTrue(failed)
            self.assertEqual(bundle.read_bytes(), b"old bundle")
            self.assertEqual(checksum.read_bytes(), b"old checksum")
            self.assertFalse(staged.exists())
            self.assertFalse(
                (root / ".dist.publication-transaction.json").exists()
            )

    def test_prepared_bundle_transaction_recovers_after_exchange(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-recover-") as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"old bundle")
            checksum.write_bytes(b"old checksum")
            staged = root / f".dist.generation-{'c' * 32}"
            staged.mkdir()
            (staged / bundle.name).write_bytes(b"new bundle")
            (staged / checksum.name).write_bytes(b"new checksum")

            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
            ):
                parent_descriptor, _ = (
                    build_bundle._open_stable_output_directory(
                        root,
                        "test publication parent",
                    )
                )
                try:
                    transaction = {
                        "schema": build_bundle.BUNDLE_TRANSACTION_SCHEMA,
                        "phase": "prepared",
                        "nonce": "d" * 32,
                        "hadPrevious": True,
                        "stagedName": staged.name,
                        "oldFingerprint": (
                            build_bundle._bundle_directory_fingerprint_at(
                                parent_descriptor,
                                dist.name,
                            )
                        ),
                        "newFingerprint": (
                            build_bundle._bundle_directory_fingerprint_at(
                                parent_descriptor,
                                staged.name,
                            )
                        ),
                    }
                    build_bundle._write_bundle_transaction_at(
                        parent_descriptor,
                        transaction,
                    )
                    build_bundle._exchange_directories(
                        parent_descriptor,
                        dist.name,
                        staged.name,
                    )
                    os.fsync(parent_descriptor)
                    build_bundle._recover_bundle_publication_transaction(
                        parent_descriptor
                    )
                finally:
                    os.close(parent_descriptor)
            self.assertEqual(bundle.read_bytes(), b"old bundle")
            self.assertEqual(checksum.read_bytes(), b"old checksum")
            self.assertFalse(staged.exists())
            self.assertFalse(
                (root / ".dist.publication-transaction.json").exists()
            )

    def test_committed_bundle_recovery_survives_partial_backup_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-partial-") as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"old bundle")
            checksum.write_bytes(b"old checksum")
            staged = root / f".dist.generation-{'9' * 32}"
            staged.mkdir()
            (staged / bundle.name).write_bytes(b"new bundle")
            (staged / checksum.name).write_bytes(b"new checksum")

            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
            ):
                parent_descriptor, _ = (
                    build_bundle._open_stable_output_directory(
                        root,
                        "test publication parent",
                    )
                )
                try:
                    transaction = {
                        "schema": build_bundle.BUNDLE_TRANSACTION_SCHEMA,
                        "phase": "prepared",
                        "nonce": "8" * 32,
                        "hadPrevious": True,
                        "stagedName": staged.name,
                        "oldFingerprint": (
                            build_bundle._bundle_directory_fingerprint_at(
                                parent_descriptor,
                                dist.name,
                            )
                        ),
                        "newFingerprint": (
                            build_bundle._bundle_directory_fingerprint_at(
                                parent_descriptor,
                                staged.name,
                            )
                        ),
                    }
                    build_bundle._write_bundle_transaction_at(
                        parent_descriptor,
                        transaction,
                    )
                    build_bundle._exchange_directories(
                        parent_descriptor,
                        dist.name,
                        staged.name,
                    )
                    os.fsync(parent_descriptor)
                    transaction["phase"] = "committed"
                    build_bundle._write_bundle_transaction_at(
                        parent_descriptor,
                        transaction,
                    )

                    original_rmtree = build_bundle.shutil.rmtree
                    interrupted = False

                    def interrupt_garbage_cleanup(
                        path,
                        *,
                        dir_fd=None,
                        **kwargs,
                    ) -> None:
                        nonlocal interrupted
                        if not interrupted and ".garbage-" in str(path):
                            garbage = root / str(path)
                            (garbage / bundle.name).unlink()
                            interrupted = True
                            raise OSError("injected partial backup cleanup")
                        original_rmtree(path, dir_fd=dir_fd, **kwargs)

                    with mock.patch.object(
                        build_bundle.shutil,
                        "rmtree",
                        side_effect=interrupt_garbage_cleanup,
                    ):
                        build_bundle._recover_bundle_publication_transaction(
                            parent_descriptor
                        )
                    self.assertTrue(interrupted)
                    self.assertFalse(
                        build_bundle._entry_exists_at(
                            parent_descriptor,
                            build_bundle._bundle_transaction_name(),
                        )
                    )
                    self.assertEqual(bundle.read_bytes(), b"new bundle")
                    build_bundle._recover_bundle_publication_transaction(
                        parent_descriptor
                    )
                finally:
                    os.close(parent_descriptor)
            self.assertEqual(bundle.read_bytes(), b"new bundle")
            self.assertEqual(checksum.read_bytes(), b"new checksum")
            self.assertFalse(staged.exists())
            self.assertFalse(
                (root / f".dist.garbage-{'8' * 32}").exists()
            )

    def test_bundle_orphan_gc_preserves_unowned_pattern_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-unowned-") as tmp:
            root = Path(tmp)
            dist = root / "dist"
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            unrelated = root / f".dist.garbage-{'a' * 32}"
            unrelated.mkdir()
            sentinel = unrelated / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
            ):
                parent_descriptor, _ = (
                    build_bundle._open_stable_output_directory(
                        root,
                        "test publication parent",
                    )
                )
                try:
                    build_bundle._recover_bundle_publication_transaction(
                        parent_descriptor
                    )
                finally:
                    os.close(parent_descriptor)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_failed_commit_journal_durability_rolls_back_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-commit-") as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"old bundle")
            checksum.write_bytes(b"old checksum")
            staged = root / f".dist.generation-{'a' * 32}"
            staged.mkdir()
            (staged / bundle.name).write_bytes(b"new bundle")
            (staged / checksum.name).write_bytes(b"new checksum")
            original_write_transaction = (
                build_bundle._write_bundle_transaction_at
            )
            failed = False

            def fail_after_committed_journal_write(
                parent_descriptor: int,
                payload: dict,
            ) -> None:
                nonlocal failed
                original_write_transaction(parent_descriptor, payload)
                if payload["phase"] == "committed" and not failed:
                    failed = True
                    raise OSError("injected committed-journal durability failure")

            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
                mock.patch.object(
                    build_bundle,
                    "_write_bundle_transaction_at",
                    side_effect=fail_after_committed_journal_write,
                ),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "committed-journal durability failure",
                ):
                    build_bundle._publish_bundle_directory(staged)
            self.assertTrue(failed)
            self.assertEqual(bundle.read_bytes(), b"old bundle")
            self.assertEqual(checksum.read_bytes(), b"old checksum")
            self.assertFalse(staged.exists())
            self.assertFalse(
                (root / ".dist.publication-transaction.json").exists()
            )

    def test_bundle_directory_exchange_publishes_pair_together(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-exchange-") as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            bundle = dist / "bundle.zip"
            checksum = dist / "bundle.zip.sha256"
            bundle.write_bytes(b"old bundle")
            checksum.write_bytes(b"old checksum")
            staged = root / f".dist.generation-{'e' * 32}"
            staged.mkdir()
            (staged / bundle.name).write_bytes(b"new bundle")
            (staged / checksum.name).write_bytes(b"new checksum")
            original_rmtree = build_bundle.shutil.rmtree
            observed: dict[str, bytes] = {}

            def inspect_exchanged_pair(
                path,
                *,
                dir_fd=None,
                **kwargs,
            ) -> None:
                observed["new_bundle"] = bundle.read_bytes()
                observed["new_checksum"] = checksum.read_bytes()
                old_root = root / str(path)
                observed["old_bundle"] = (
                    old_root / bundle.name
                ).read_bytes()
                observed["old_checksum"] = (
                    old_root / checksum.name
                ).read_bytes()
                original_rmtree(path, dir_fd=dir_fd, **kwargs)

            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(build_bundle, "BUNDLE", bundle),
                mock.patch.object(build_bundle, "CHECKSUM", checksum),
                mock.patch.object(
                    build_bundle.shutil,
                    "rmtree",
                    side_effect=inspect_exchanged_pair,
                ),
            ):
                build_bundle._publish_bundle_directory(staged)
            self.assertEqual(observed["new_bundle"], b"new bundle")
            self.assertEqual(observed["new_checksum"], b"new checksum")
            self.assertEqual(observed["old_bundle"], b"old bundle")
            self.assertEqual(observed["old_checksum"], b"old checksum")

    def test_bundle_publication_parent_swap_does_not_touch_outside_pair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-publish-swap-") as tmp:
            root = Path(tmp)
            parent = root / "publication"
            parent.mkdir()
            moved = root / "moved-publication"
            outside = root / "outside"
            outside.mkdir()
            dist = parent / "dist"
            staged = parent / f".dist.generation-{'f' * 32}"
            outside_dist = outside / dist.name
            outside_staged = outside / staged.name
            for directory, bundle_bytes, checksum_bytes in (
                (dist, b"old bundle", b"old checksum"),
                (staged, b"new bundle", b"new checksum"),
                (outside_dist, b"outside bundle", b"outside checksum"),
                (outside_staged, b"outside staged", b"outside staged checksum"),
            ):
                directory.mkdir()
                (directory / "bundle.zip").write_bytes(bundle_bytes)
                (directory / "bundle.zip.sha256").write_bytes(checksum_bytes)
            original_exchange = build_bundle._exchange_directories
            swapped = False

            def swap_before_exchange(
                directory_descriptor: int,
                left_name: str,
                right_name: str,
            ) -> None:
                nonlocal swapped
                if not swapped:
                    parent.rename(moved)
                    parent.symlink_to(outside, target_is_directory=True)
                    swapped = True
                original_exchange(
                    directory_descriptor,
                    left_name,
                    right_name,
                )

            with (
                mock.patch.object(build_bundle, "DIST", dist),
                mock.patch.object(
                    build_bundle,
                    "BUNDLE",
                    dist / "bundle.zip",
                ),
                mock.patch.object(
                    build_bundle,
                    "CHECKSUM",
                    dist / "bundle.zip.sha256",
                ),
                mock.patch.object(
                    build_bundle,
                    "_exchange_directories",
                    side_effect=swap_before_exchange,
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "directory changed during publication",
                ):
                    build_bundle._publish_bundle_directory(staged)
            self.assertTrue(swapped)
            self.assertEqual(
                (outside_dist / "bundle.zip").read_bytes(),
                b"outside bundle",
            )
            self.assertEqual(
                (outside_dist / "bundle.zip.sha256").read_bytes(),
                b"outside checksum",
            )
            self.assertEqual(
                (outside_staged / "bundle.zip").read_bytes(),
                b"outside staged",
            )
            self.assertEqual(
                (outside_staged / "bundle.zip.sha256").read_bytes(),
                b"outside staged checksum",
            )

    def test_staged_bundle_parent_swap_does_not_touch_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-stage-swap-") as tmp:
            root = Path(tmp)
            staged = root / "staged"
            staged.mkdir()
            moved = root / "moved-staged"
            outside = root / "outside"
            outside.mkdir()
            target = staged / "bundle.zip"
            original_open = os.open
            swapped = False

            def swap_before_file_open(
                name,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                nonlocal swapped
                if dir_fd is not None and name == target.name and not swapped:
                    staged.rename(moved)
                    staged.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return original_open(
                    name,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with mock.patch.object(
                build_bundle.os,
                "open",
                side_effect=swap_before_file_open,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "directory changed during publication",
                ):
                    build_bundle._write_staged_file(target, b"bundle bytes")
            self.assertTrue(swapped)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual(list(moved.iterdir()), [])

    def test_bundle_builder_rejects_in_place_source_rewrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-source-rewrite-") as tmp:
            root = Path(tmp)
            required = root / "required.bin"
            required.write_bytes(b"A" * (2 * 1024 * 1024 + 17))
            original_read = build_bundle.os.read
            modified = False

            def mutate_after_first_chunk(descriptor: int, size: int) -> bytes:
                nonlocal modified
                data = original_read(descriptor, size)
                if data and not modified:
                    with required.open("r+b") as handle:
                        handle.seek(1024 * 1024)
                        handle.write(b"B" * 4096)
                        handle.flush()
                        os.fsync(handle.fileno())
                    modified = True
                return data

            with (
                mock.patch.object(build_bundle, "ROOT", root),
                mock.patch.object(
                    build_bundle.os,
                    "read",
                    side_effect=mutate_after_first_chunk,
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "changed during bundle read",
                ):
                    build_bundle.validated_source_file("required.bin")
            self.assertTrue(modified)

    def test_bundle_builder_rejects_intermediate_directory_swap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-dir-swap-") as tmp:
            root = Path(tmp)
            source_dir = root / "sub"
            source_dir.mkdir()
            required = source_dir / "required.txt"
            required.write_text("ORIGINAL\n", encoding="utf-8")
            moved = root / "moved-sub"
            original_open = build_bundle.os.open
            swapped = False

            def swap_directory_before_open(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                nonlocal swapped
                if path == "sub" and dir_fd is not None and not swapped:
                    source_dir.rename(moved)
                    source_dir.mkdir()
                    required.write_text("REPLACEMENT\n", encoding="utf-8")
                    swapped = True
                return original_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with (
                mock.patch.object(build_bundle, "ROOT", root),
                mock.patch.object(
                    build_bundle.os,
                    "open",
                    side_effect=swap_directory_before_open,
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "source directory changed",
                ):
                    build_bundle.validated_source_file(
                        "sub/required.txt"
                    )
            self.assertTrue(swapped)

    def test_bundle_rejects_optional_lean_receipt(self) -> None:
        source = Path(__file__).resolve().parent / "dist" / (
            "GOAI-AI4R-Open-Exploration.zip"
        )
        prefix = "goai-ai4r-open-exploration/"
        validation_name = prefix + "v2/artifacts/task-validation.json"
        manifest_name = prefix + "MANIFEST.sha256"
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "optional-lean.zip"
            with zipfile.ZipFile(source) as archive:
                payloads = {
                    info.filename: archive.read(info.filename)
                    for info in archive.infolist()
                }
            validation = json.loads(payloads[validation_name])
            validation["leanRequired"] = False
            validation["leanProjectCommit"] = None
            payloads[validation_name] = (
                json.dumps(validation, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            manifest_rows = payloads[manifest_name].decode("utf-8").splitlines()
            relative = "v2/artifacts/task-validation.json"
            manifest_rows = [
                (
                    f"{verify_bundle.sha256(payloads[validation_name])}  {relative}"
                    if row.endswith(f"  {relative}")
                    else row
                )
                for row in manifest_rows
            ]
            payloads[manifest_name] = ("\n".join(manifest_rows) + "\n").encode()
            with zipfile.ZipFile(target, "w") as archive:
                for name, data in payloads.items():
                    archive.writestr(name, data)
            errors = verify_bundle.validate(target)
            self.assertTrue(
                any("leanRequired must be True" in error for error in errors),
                errors,
            )

    def test_bundle_rejects_protocol_twin_claim_or_contact_drift(self) -> None:
        source = Path(__file__).resolve().parent / "dist" / (
            "GOAI-AI4R-Open-Exploration.zip"
        )
        prefix = "goai-ai4r-open-exploration/"
        twin_name = prefix + "v2/artifacts/protocol-twin.json"
        manifest_name = prefix + "MANIFEST.sha256"
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "mutated-protocol-twin.zip"
            with zipfile.ZipFile(source) as archive:
                payloads = {
                    info.filename: archive.read(info.filename)
                    for info in archive.infolist()
                }
            twin = json.loads(payloads[twin_name])
            twin["modelCallCount"] = 1
            payloads[twin_name] = (
                json.dumps(twin, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            relative = "v2/artifacts/protocol-twin.json"
            manifest_rows = payloads[manifest_name].decode("utf-8").splitlines()
            manifest_rows = [
                (
                    f"{verify_bundle.sha256(payloads[twin_name])}  {relative}"
                    if row.endswith(f"  {relative}")
                    else row
                )
                for row in manifest_rows
            ]
            payloads[manifest_name] = ("\n".join(manifest_rows) + "\n").encode()
            with zipfile.ZipFile(target, "w") as archive:
                for name, data in payloads.items():
                    archive.writestr(name, data)
            errors = verify_bundle.validate(target)
            self.assertTrue(
                any(
                    "protocol twin modelCallCount must be 0" in error
                    or "protocol twin root hash mismatch" in error
                    for error in errors
                ),
                errors,
            )

    def test_bundle_rejects_resealed_protocol_semantic_drift(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        twin_name = prefix + "v2/artifacts/protocol-twin.json"
        validation_name = (
            prefix + "v2/artifacts/protocol-twin-validation.json"
        )
        with zipfile.ZipFile(_source_bundle()) as archive:
            twin = json.loads(archive.read(twin_name))
        task = next(
            row
            for row in twin["tasks"]
            if row["taskId"] == "twin-physics-valid-transfer-fail"
        )
        task["transferPassed"] = True
        twin["trajectories"] = protocol_twin.build_trajectories(twin["tasks"])
        twin["armRuns"] = protocol_twin.build_arm_runs(
            twin["tasks"],
            twin["trajectories"],
        )
        twin["ablationRuns"] = protocol_twin.build_ablation_runs(
            twin["tasks"],
            twin["trajectories"],
        )
        twin = protocol_twin.seal_protocol_twin(twin)
        twin_errors, twin_validation = protocol_twin.validate_protocol_twin(
            twin
        )
        self.assertTrue(twin_errors)
        replacements = {
            twin_name: (
                json.dumps(twin, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
            validation_name: (
                json.dumps(twin_validation, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        }
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "resealed-semantic-drift.zip"
            _write_mutated_bundle(target, replacements=replacements)
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "frozen canonical build" in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_malformed_protocol_task_returns_errors(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        twin_name = prefix + "v2/artifacts/protocol-twin.json"
        with zipfile.ZipFile(_source_bundle()) as archive:
            twin = json.loads(archive.read(twin_name))
        twin["tasks"][0] = []
        twin = protocol_twin.seal_protocol_twin(twin)
        replacement = (
            json.dumps(twin, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "malformed-protocol-task.zip"
            _write_mutated_bundle(
                target,
                replacements={twin_name: replacement},
            )
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "task 0: expected object" in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_rejects_protocol_twin_validation_report_drift(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        validation_name = (
            prefix + "v2/artifacts/protocol-twin-validation.json"
        )
        with zipfile.ZipFile(_source_bundle()) as archive:
            validation = json.loads(archive.read(validation_name))
        validation["errors"] = ["fabricated validation error"]
        validation["fabricatedField"] = True
        replacement = (
            json.dumps(validation, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "mutated-protocol-validation.zip"
            _write_mutated_bundle(
                target,
                replacements={validation_name: replacement},
            )
            errors = verify_bundle.validate(target)
        self.assertIn(
            "protocol twin validation report does not exactly match "
            "recomputed protocol validation",
            errors,
        )

    def test_bundle_rejects_resealed_study_dag_report_drift(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        report_name = (
            prefix + "v2/artifacts/study-root-dag-benchmark.json"
        )
        with zipfile.ZipFile(_source_bundle()) as archive:
            report = json.loads(archive.read(report_name))
        report["validCases"] = []
        report["invalidCases"] = []
        report["stableTypedIssueCodes"] = []
        report["errors"] = ["fabricated error"]
        replacement = (
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "mutated-study-dag-report.zip"
            _write_mutated_bundle(
                target,
                replacements={report_name: replacement},
            )
            errors = verify_bundle.validate(target)
        self.assertIn(
            "study root DAG benchmark does not exactly match recomputation",
            errors,
        )

    def test_bundle_rejects_resealed_study_bound_source_drift(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        with zipfile.ZipFile(_source_bundle()) as archive:
            source_payloads = {
                name: archive.read(prefix + "v2/" + name)
                for name in study_root.SOURCE_FILES
            }
        for name in study_root.SOURCE_FILES:
            with self.subTest(name=name):
                bundle_name = prefix + "v2/" + name
                replacement = (
                    source_payloads[name]
                    + b"\n# resealed Study Root source drift\n"
                )
                with tempfile.TemporaryDirectory(
                    prefix="goai-bundle-test-"
                ) as tmp:
                    target = Path(tmp) / (
                        "mutated-study-source-"
                        + name.replace("/", "-")
                        + ".zip"
                    )
                    _write_mutated_bundle(
                        target,
                        replacements={bundle_name: replacement},
                    )
                    errors = verify_bundle.validate(target)
                self.assertIn(
                    f"Study Root source binding hash mismatch: {name}",
                    errors,
                )

    def test_bundle_rejects_resealed_scorer_simulation_drift(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        report_name = (
            prefix
            + "v2/artifacts/scorer-operating-characteristics.json"
        )
        with zipfile.ZipFile(_source_bundle()) as archive:
            report = json.loads(archive.read(report_name))
        report["nullFalsePositiveRate"] = 0.99
        report["prospectiveAlternativeDetectionRate"] = 0.0
        report["negativeControls"] = []
        report["operatingCharacteristicGates"] = {}
        report["errors"] = ["fabricated error"]
        replacement = (
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "mutated-scorer-simulation.zip"
            _write_mutated_bundle(
                target,
                replacements={report_name: replacement},
            )
            errors = verify_bundle.validate(target)
        self.assertIn(
            "scorer operating characteristics do not exactly match "
            "recomputation",
            errors,
        )

    def test_bundle_rejects_receipt_validation_report_drift(self) -> None:
        source = Path(__file__).resolve().parent / "dist" / (
            "GOAI-AI4R-Open-Exploration.zip"
        )
        prefix = "goai-ai4r-open-exploration/"
        validation_name = (
            prefix + "v2/artifacts/receipt-rehearsal-validation.json"
        )
        manifest_name = prefix + "MANIFEST.sha256"
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "mutated-receipt-validation.zip"
            with zipfile.ZipFile(source) as archive:
                payloads = {
                    info.filename: archive.read(info.filename)
                    for info in archive.infolist()
                }
            validation = json.loads(payloads[validation_name])
            validation["reports"][0]["domain"] = "fabricated-domain"
            validation["errors"] = ["fabricated validation error"]
            payloads[validation_name] = (
                json.dumps(validation, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            relative = "v2/artifacts/receipt-rehearsal-validation.json"
            manifest_rows = payloads[manifest_name].decode("utf-8").splitlines()
            manifest_rows = [
                (
                    f"{verify_bundle.sha256(payloads[validation_name])}  {relative}"
                    if row.endswith(f"  {relative}")
                    else row
                )
                for row in manifest_rows
            ]
            payloads[manifest_name] = ("\n".join(manifest_rows) + "\n").encode()
            with zipfile.ZipFile(target, "w") as archive:
                for name, data in payloads.items():
                    archive.writestr(name, data)
            errors = verify_bundle.validate(target)
            self.assertIn(
                "receipt rehearsal validation report does not exactly match "
                "recomputed chain validation",
                errors,
            )

    def test_bundle_rejects_entire_private_v2_subtree(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        private_name = (
            prefix + "v2/private/confirmatory-transfer-tasks.jsonl"
        )
        private_payload = b'{"sealed":true}\n'
        private_info = build_bundle.zip_info(private_name)
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "private-transfer-leak.zip"
            _write_mutated_bundle(
                target,
                additions=[(private_info, private_payload)],
            )
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "forbidden archive entries" in error
                and private_name in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_rejects_normalized_private_path_aliases(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        names = (
            prefix + "v2/./private/secret.json",
            prefix + "v2//private/secret.json",
            prefix + "v2/private",
        )
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            root = Path(tmp)
            for index, name in enumerate(names):
                with self.subTest(name=name):
                    target = root / f"private-alias-{index}.zip"
                    _write_mutated_bundle(
                        target,
                        additions=[
                            (
                                build_bundle.zip_info(name),
                                b'{"private":true}\n',
                            )
                        ],
                    )
                    errors = verify_bundle.validate(target)
                    self.assertTrue(
                        any(
                            "unsafe archive entry names" in error
                            or "forbidden archive entries" in error
                            or "does not exactly match builder allowlist" in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_bundle_rejects_non_allowlisted_regular_entries(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        cases = {
            prefix + ".env": b"EXAMPLE_API_KEY=not-a-real-secret\n",
            prefix + "arbitrary-notes.txt": b"unexpected public file\n",
        }
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            root = Path(tmp)
            for index, (name, payload) in enumerate(cases.items()):
                with self.subTest(name=name):
                    target = root / f"unexpected-entry-{index}.zip"
                    _write_mutated_bundle(
                        target,
                        additions=[(build_bundle.zip_info(name), payload)],
                    )
                    errors = verify_bundle.validate(target)
                    self.assertTrue(
                        any(
                            "does not exactly match builder allowlist" in error
                            and name in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_bundle_rejects_noncanonical_zip_container_channels(self) -> None:
        source_bytes = _source_bundle().read_bytes()
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            root = Path(tmp)

            prepended = root / "prepended.zip"
            prepended.write_bytes(b"PRIVATE-PREFIX\n" + source_bytes)
            self.assertTrue(
                any(
                    "deterministic canonical archive" in error
                    for error in verify_bundle.validate(prepended)
                )
            )

            commented = root / "commented.zip"
            with zipfile.ZipFile(_source_bundle()) as source:
                entries = [
                    (copy.copy(info), source.read(info.filename))
                    for info in source.infolist()
                ]
            with zipfile.ZipFile(commented, "w") as archive:
                for info, data in entries:
                    archive.writestr(info, data)
                archive.comment = b"PRIVATE-COMMENT"
            self.assertTrue(
                any(
                    "deterministic canonical archive" in error
                    for error in verify_bundle.validate(commented)
                )
            )

            extra = root / "extra-field.zip"

            def add_extra_field(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
                if info.filename.endswith("/LICENSE"):
                    payload = b"PRIVATE-EXTRA"
                    info.extra = struct.pack("<HH", 0xCAFE, len(payload)) + payload
                return info

            _write_mutated_bundle(extra, mutate_info=add_extra_field)
            self.assertTrue(
                any(
                    "deterministic canonical archive" in error
                    for error in verify_bundle.validate(extra)
                )
            )

    def test_bundle_corrupt_member_returns_structured_error(self) -> None:
        data = bytearray(_source_bundle().read_bytes())
        with zipfile.ZipFile(_source_bundle()) as archive:
            info = archive.getinfo(
                "goai-ai4r-open-exploration/LICENSE"
            )
        position = data.find(b"PK\x01\x02")
        while position >= 0:
            name_length, extra_length, comment_length = struct.unpack_from(
                "<HHH",
                data,
                position + 28,
            )
            name_start = position + 46
            name = bytes(
                data[name_start : name_start + name_length]
            ).decode("utf-8")
            if name == info.filename:
                crc = struct.unpack_from("<I", data, position + 16)[0]
                struct.pack_into("<I", data, position + 16, crc ^ 0x01)
                break
            position = data.find(
                b"PK\x01\x02",
                name_start + name_length + extra_length + comment_length,
            )
        self.assertGreaterEqual(position, 0)
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "bad-crc.zip"
            target.write_bytes(data)
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "cannot read archive entry" in error
                and "BadZipFile" in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_hostile_json_returns_structured_error(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        twin_name = prefix + "v2/artifacts/protocol-twin.json"
        hostile = b'{"huge":' + (b"9" * 5000) + b"}\n"
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "hostile-json.zip"
            _write_mutated_bundle(
                target,
                replacements={twin_name: hostile},
            )
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "invalid protocol twin: ValueError" in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_enforces_claim_ceiling_on_every_public_json(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        target_name = "evidence/ladder-summary.json"
        manifest_name = "MANIFEST.sha256"
        with zipfile.ZipFile(_source_bundle()) as archive:
            payloads = {
                info.filename.removeprefix(prefix): archive.read(info)
                for info in archive.infolist()
            }
        value = json.loads(payloads[target_name])
        value["candidateOnly"] = False
        value["canClaimAGI"] = True
        payloads[target_name] = (
            json.dumps(value, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        rows = payloads[manifest_name].decode("utf-8").splitlines()
        rows = [
            (
                f"{verify_bundle.sha256(payloads[target_name])}  "
                f"{target_name}"
                if row.endswith(f"  {target_name}")
                else row
            )
            for row in rows
        ]
        payloads[manifest_name] = ("\n".join(rows) + "\n").encode()
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "claim-ceiling-drift.zip"
            target.write_bytes(build_bundle.canonical_bundle_bytes(payloads))
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "candidateOnly must be true" in error
                and target_name in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any(
                "canClaimAGI must be false" in error
                and target_name in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_resource_limits_precede_member_reads(self) -> None:
        with (
            mock.patch.object(
                verify_bundle,
                "MAX_TOTAL_UNCOMPRESSED_BYTES",
                1,
            ),
            mock.patch.object(
                verify_bundle.zipfile.ZipFile,
                "read",
                side_effect=AssertionError(
                    "member read occurred before aggregate limit"
                ),
            ),
        ):
            errors = verify_bundle.validate(_source_bundle())
        self.assertTrue(
            any("total uncompressed size exceeds" in error for error in errors),
            errors,
        )

        with (
            mock.patch.object(verify_bundle, "MAX_ARCHIVE_ENTRIES", 1),
            mock.patch.object(
                verify_bundle.zipfile.ZipFile,
                "read",
                side_effect=AssertionError(
                    "member read occurred before entry-count limit"
                ),
            ),
        ):
            errors = verify_bundle.validate(_source_bundle())
        self.assertTrue(
            any("entry count exceeds limit" in error for error in errors),
            errors,
        )

    def test_bundle_container_memory_error_returns_structured_error(self) -> None:
        source = _source_bundle()
        original_read_bytes = Path.read_bytes

        def fail_container_read(path: Path) -> bytes:
            if path == source:
                raise MemoryError("injected container allocation failure")
            return original_read_bytes(path)

        with mock.patch.object(
            Path,
            "read_bytes",
            fail_container_read,
        ):
            errors = verify_bundle.validate(source)
        self.assertTrue(
            any(
                "cannot compare canonical bundle bytes: MemoryError" in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_unsupported_compression_returns_structured_error(self) -> None:
        data = bytearray(_source_bundle().read_bytes())
        with zipfile.ZipFile(_source_bundle()) as archive:
            first = archive.infolist()[0]
        struct.pack_into("<H", data, first.header_offset + 8, 99)
        central = data.find(b"PK\x01\x02")
        self.assertGreaterEqual(central, 0)
        struct.pack_into("<H", data, central + 10, 99)
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "unsupported-compression.zip"
            target.write_bytes(data)
            errors = verify_bundle.validate(target)
        self.assertTrue(
            any(
                "cannot read archive entry" in error
                and "NotImplementedError" in error
                for error in errors
            ),
            errors,
        )

    def test_bundle_rejects_zip_symlink_entry_with_escaping_target(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        license_name = prefix + "LICENSE"
        escaping_target = b"../../outside-secret"

        def make_license_symlink(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
            if info.filename == license_name:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            return info

        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            target = Path(tmp) / "zip-symlink.zip"
            _write_mutated_bundle(
                target,
                replacements={license_name: escaping_target},
                mutate_info=make_license_symlink,
            )
            errors = verify_bundle.validate(target)
        self.assertIn(
            f"archive entry is not a regular file: {license_name}",
            errors,
        )

    def test_bundle_wrong_json_top_level_types_return_errors(self) -> None:
        prefix = "goai-ai4r-open-exploration/"
        cases = {
            prefix + "v2/artifacts/synthetic-rehearsal-seal.manifest.json":
                "synthetic rehearsal seal must be a JSON object",
            prefix + "v2/artifacts/task-validation.json":
                "strict task validation must be a JSON object",
            prefix + "v2/artifacts/receipt-protocol-benchmark.json":
                "receipt protocol benchmark must be a JSON object",
            prefix + "v2/artifacts/protocol-twin-validation.json":
                "protocol twin validation must be a JSON object",
            prefix + "hosted-demo/healthcheck.public-report.json":
                "hosted-demo healthcheck must be a JSON object",
        }
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            root = Path(tmp)
            for index, (name, expected_error) in enumerate(cases.items()):
                with self.subTest(name=name):
                    target = root / f"wrong-type-{index}.zip"
                    _write_mutated_bundle(
                        target,
                        replacements={name: b"[]\n"},
                    )
                    errors = verify_bundle.validate(target)
                    self.assertIn(expected_error, errors)

    def test_run_all_preserves_strict_lean_receipt(self) -> None:
        script = (
            Path(__file__).resolve().parent / "run_all.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("OPTIONAL_VALIDATION_RECEIPT=$(mktemp", script)
        self.assertIn(
            'v2/validate_task_manifest.py --output "$OPTIONAL_VALIDATION_RECEIPT"',
            script,
        )

    def test_bundle_validator_rejects_unsafe_and_malformed_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-bundle-test-") as tmp:
            bundle = Path(tmp) / "unsafe.zip"
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr("../escape.txt", "no")
                archive.writestr(
                    "goai-ai4r-open-exploration/MANIFEST.sha256",
                    "malformed-row\n",
                )
            errors = verify_bundle.validate(bundle)
            self.assertTrue(
                any("outside required prefix" in error for error in errors),
                errors,
            )
            self.assertTrue(any("unsafe archive entry" in error for error in errors), errors)
            self.assertTrue(any("manifest line 1" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
