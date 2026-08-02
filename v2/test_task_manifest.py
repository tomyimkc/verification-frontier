#!/usr/bin/env python3
"""Tests for the frozen GOAI v2 task-manifest builder."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2 import build_task_manifest


class TaskManifestTests(unittest.TestCase):
    def test_frozen_counts_and_claim_ceiling(self) -> None:
        tasks = build_task_manifest.build_tasks()
        self.assertEqual(build_task_manifest.validate(tasks), [])
        self.assertEqual(len(tasks), 150)
        self.assertTrue(all(task.candidateOnly for task in tasks))
        self.assertTrue(all(not task.canClaimAGI for task in tasks))

    def test_manifest_is_deterministic(self) -> None:
        first = build_task_manifest.canonical_rows(
            build_task_manifest.build_tasks()
        )
        second = build_task_manifest.canonical_rows(
            build_task_manifest.build_tasks()
        )
        self.assertEqual(first, second)

    def test_written_summary_matches_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-manifest-") as tmp:
            root = Path(tmp)
            summary = build_task_manifest.write_manifest(root)
            rows = [
                json.loads(line)
                for line in (root / "task-manifest.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(summary["taskCount"], 150)
            self.assertEqual(len(rows), 150)
            self.assertEqual(summary["openControlCount"], 3)
            self.assertTrue(summary["candidateOnly"])
            self.assertFalse(summary["canClaimAGI"])


if __name__ == "__main__":
    unittest.main()
