#!/usr/bin/env python3
"""Tests for v2 manifest verification."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2 import build_task_manifest, validate_task_manifest


class ValidateTaskManifestTests(unittest.TestCase):
    def test_nonlean_tiers_and_optional_lean_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-validation-") as tmp:
            root = Path(tmp)
            build_task_manifest.write_manifest(root)
            errors, summary = validate_task_manifest.validate(
                root / "task-manifest.jsonl",
                lean_project=None,
                require_lean=False,
            )
            self.assertEqual(errors, [])
            self.assertEqual(summary["taskCount"], 150)
            self.assertEqual(summary["validCount"], 150)
            self.assertTrue(summary["candidateOnly"])
            self.assertFalse(summary["canClaimAGI"])

    def test_require_lean_fails_closed_without_project(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-validation-") as tmp:
            root = Path(tmp)
            build_task_manifest.write_manifest(root)
            errors, summary = validate_task_manifest.validate(
                root / "task-manifest.jsonl",
                lean_project=None,
                require_lean=True,
            )
            self.assertEqual(len(errors), 40)
            self.assertEqual(summary["invalidCount"], 40)
            self.assertTrue(
                all("lean_project_not_supplied" in error for error in errors),
                errors[:3],
            )

    def test_manifest_corruption_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-validation-") as tmp:
            manifest = Path(tmp) / "manifest.jsonl"
            manifest.write_text("{not-json}\n", encoding="utf-8")
            errors, summary = validate_task_manifest.validate(manifest)
            self.assertTrue(any("invalid JSON" in error for error in errors))
            self.assertEqual(summary["taskCount"], 0)


if __name__ == "__main__":
    unittest.main()
