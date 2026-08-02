#!/usr/bin/env python3
"""Offline tests for the v2 model-attempt runner."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2 import build_task_manifest, run_model_attempts


class RunModelAttemptsTests(unittest.TestCase):
    def test_dry_run_writes_no_secret_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-runner-") as tmp:
            root = Path(tmp)
            build_task_manifest.write_manifest(root)
            output = root / "attempts.jsonl"
            run_manifest = root / "run.json"
            plan = run_model_attempts.run_attempts(
                manifest=root / "task-manifest.jsonl",
                output=output,
                run_manifest_path=run_manifest,
                model_specs=("mock",),
                attempts=1,
                limit=2,
                dry_run=True,
            )
            self.assertEqual(plan["taskCount"], 2)
            self.assertFalse(output.exists())
            payload = run_manifest.read_text(encoding="utf-8")
            self.assertNotIn("api_key", payload.casefold())
            self.assertEqual(plan["evidenceClass"], "development-only")
            self.assertRegex(plan["runnerSha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(plan["modelClientSha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(plan["candidateOnly"])
            self.assertFalse(plan["canClaimAGI"])

    def test_mock_run_is_jsonl_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-runner-") as tmp:
            root = Path(tmp)
            build_task_manifest.write_manifest(root)
            manifest = root / "task-manifest.jsonl"
            output = root / "attempts.jsonl"
            run_manifest = root / "run.json"
            kwargs = dict(
                manifest=manifest,
                output=output,
                run_manifest_path=run_manifest,
                model_specs=("mock",),
                attempts=2,
                limit=3,
                dry_run=False,
                resume=True,
            )
            run_model_attempts.run_attempts(**kwargs)
            first = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(first), 6)
            run_model_attempts.run_attempts(**kwargs)
            second = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(first, second)
            rows = [json.loads(line) for line in second]
            self.assertTrue(all(row["candidateOnly"] for row in rows))
            self.assertTrue(all(not row["canClaimAGI"] for row in rows))
            self.assertTrue(all(row["requestedModelSpec"] == "mock" for row in rows))
            self.assertTrue(
                all(row["evidenceClass"] == "development-only" for row in rows)
            )

    def test_confirmatory_run_is_disabled_without_seal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-runner-") as tmp:
            root = Path(tmp)
            build_task_manifest.write_manifest(root)
            with self.assertRaisesRegex(RuntimeError, "disabled in this milestone"):
                run_model_attempts.run_attempts(
                    manifest=root / "task-manifest.jsonl",
                    output=root / "attempts.jsonl",
                    run_manifest_path=root / "run.json",
                    model_specs=("mock",),
                    attempts=1,
                    limit=1,
                    dry_run=True,
                    evidence_class="confirmatory",
                )

    def test_confirmatory_run_rejects_matching_minimal_seal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-runner-") as tmp:
            root = Path(tmp)
            summary = build_task_manifest.write_manifest(root)
            seal = root / "seal.json"
            seal.write_text(
                json.dumps(
                    {
                        "privateTaskManifestSha256": summary["sha256"],
                        "status": "ready-for-confirmatory",
                        "confirmatoryEligible": True,
                        "outcomesViewedAtSeal": False,
                        "candidateOnly": True,
                        "canClaimAGI": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "readiness-receipt lifecycle"):
                run_model_attempts.run_attempts(
                    manifest=root / "task-manifest.jsonl",
                    output=root / "attempts.jsonl",
                    run_manifest_path=root / "run.json",
                    model_specs=("mock",),
                    attempts=1,
                    limit=1,
                    dry_run=True,
                    evidence_class="confirmatory",
                    confirmatory_seal=seal,
                )
            self.assertFalse((root / "run.json").exists())

    def test_camelcase_manifest_is_resumable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goai-v2-runner-") as tmp:
            root = Path(tmp)
            manifest = root / "confirmatory.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "taskId": "sealed-001-valid",
                        "pairId": "sealed-001",
                        "domain": "physics",
                        "component": "frontier",
                        "member": "valid",
                        "generatorFamily": "family-001",
                        "extensionClass": "physics.example",
                        "prompt": "Return the declared candidate.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output = root / "attempts.jsonl"
            run_manifest = root / "run.json"
            kwargs = dict(
                manifest=manifest,
                output=output,
                run_manifest_path=run_manifest,
                model_specs=("mock",),
                attempts=1,
                dry_run=False,
                resume=True,
                evidence_class="development-only",
            )
            run_model_attempts.run_attempts(**kwargs)
            run_model_attempts.run_attempts(**kwargs)
            rows = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["taskId"], "sealed-001-valid")
            self.assertEqual(rows[0]["pairId"], "sealed-001")
            self.assertEqual(rows[0]["component"], "frontier")


if __name__ == "__main__":
    unittest.main()
