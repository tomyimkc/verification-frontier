#!/usr/bin/env python3
"""Tests for concurrency-safe GOAI Lean scratch-file handling."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from v2 import lean_verify


class LeanVerifyTests(unittest.TestCase):
    def test_placeholder_rejected_without_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-lean-") as tmp:
            with mock.patch("v2.lean_verify.subprocess.run") as run:
                verdict, reason = lean_verify.verify_source(
                    "import Mathlib\nexample : True := by sorry\n",
                    Path(tmp),
                    5,
                )
            self.assertEqual(verdict, "rejected")
            self.assertIn("sorry", reason)
            run.assert_not_called()

    def test_unique_scratch_files_are_removed(self) -> None:
        observed: list[str] = []

        def fake_run(command, *, cwd, capture_output, text, timeout):
            del capture_output, text, timeout
            path = Path(cwd) / command[-1]
            self.assertTrue(path.is_file())
            observed.append(path.name)
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory(prefix="goai-lean-") as tmp:
            root = Path(tmp)
            with mock.patch("v2.lean_verify.subprocess.run", side_effect=fake_run):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(
                        pool.map(
                            lambda index: lean_verify.verify_source(
                                f"import Mathlib\nexample : {index} = {index} := by rfl\n",
                                root,
                                5,
                            ),
                            range(24),
                        )
                    )
            self.assertTrue(all(verdict == "accepted" for verdict, _ in results))
            self.assertEqual(len(observed), 24)
            self.assertEqual(len(set(observed)), 24)
            self.assertEqual(list(root.glob(".goai-lean-probe-*.lean")), [])

    def test_nonzero_process_is_rejected(self) -> None:
        completed = subprocess.CompletedProcess(
            ["lake", "env", "lean", "probe.lean"],
            1,
            "",
            "error: unsolved goals",
        )
        with tempfile.TemporaryDirectory(prefix="goai-lean-") as tmp:
            with mock.patch("v2.lean_verify.subprocess.run", return_value=completed):
                verdict, reason = lean_verify.verify_source(
                    "import Mathlib\nexample : False := by contradiction\n",
                    Path(tmp),
                    5,
                )
        self.assertEqual(verdict, "rejected")
        self.assertIn("unsolved goals", reason)


if __name__ == "__main__":
    unittest.main()
