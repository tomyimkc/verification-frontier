#!/usr/bin/env python3
"""CPU-only tests for the guarded Pro6000 Stage A preflight."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from v2 import stage_a_pro6000

PLAIN_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


class StageAPro6000Tests(unittest.TestCase):
    def test_gpu_dependency_pins_are_mutually_reviewed(self) -> None:
        requirements = (
            Path(stage_a_pro6000.__file__).resolve().parents[1]
            / "requirements-stage-a-gpu.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("transformers==5.13.1", requirements)
        self.assertIn("accelerate==1.10.1", requirements)
        self.assertIn("huggingface-hub==1.5.0", requirements)
        self.assertNotIn("huggingface-hub==0.36.0", requirements)
        self.assertIn("safetensors==0.8.0", requirements)
        self.assertNotIn("safetensors==0.6.2", requirements)

    def test_only_reviewed_model_and_modes_are_accepted(self) -> None:
        minimums = {}
        for mode in stage_a_pro6000.MODES:
            payload = stage_a_pro6000.validate_dispatch(
                mode,
                "Qwen/Qwen2.5-7B-Instruct",
            )
            minimums[mode] = payload["minimumFreeGiB"]
            self.assertFalse(payload["confirmatoryExecutionAllowed"])
            self.assertFalse(payload["winnerLevelEligible"])
            self.assertFalse(payload["winnerLevelGateMet"])
            self.assertTrue(
                payload["preciseCacheFeasibilityCheckedByHostPreflight"]
            )
        self.assertEqual(minimums["preflight"], 32.0)
        self.assertEqual(minimums["development-smoke"], 20.0)
        self.assertEqual(minimums["stage-a-run"], 20.0)
        with self.assertRaisesRegex(ValueError, "unreviewed model"):
            stage_a_pro6000.validate_dispatch(
                "preflight",
                "unreviewed/30b-model",
            )
        with self.assertRaisesRegex(ValueError, "unsupported mode"):
            stage_a_pro6000.validate_dispatch(
                "confirmatory",
                "Qwen/Qwen2.5-7B-Instruct",
            )

    def test_storage_selection_prefers_roomiest_eligible_plain_path(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="goai-storage-",
            dir=PLAIN_TEMP_ROOT,
        ) as tmp:
            root = Path(tmp)
            small = root / "small"
            large = root / "large"
            small.mkdir()
            large.mkdir()
            free = {
                small: 40 * 1024**3,
                large: 50 * 1024**3,
            }
            selected, rows = stage_a_pro6000.select_storage_root(
                [small, large],
                minimum_free_gib=32,
                disk_usage_fn=lambda path: SimpleNamespace(free=free[path]),
                probe_fn=lambda path, prefix: None,
            )
            self.assertEqual(selected, large.resolve())
            self.assertEqual(sum(row["eligible"] for row in rows), 2)

    def test_below_floor_storage_fails_before_gpu_or_model_contact(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="goai-storage-low-",
            dir=PLAIN_TEMP_ROOT,
        ) as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "no plain writable"):
                stage_a_pro6000.select_storage_root(
                    [root],
                    minimum_free_gib=32,
                    disk_usage_fn=lambda path: SimpleNamespace(
                        free=31 * 1024**3
                    ),
                    probe_fn=lambda path, prefix: None,
                )

    def test_development_floor_accepts_warm_cache_headroom(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="goai-storage-warm-",
            dir=PLAIN_TEMP_ROOT,
        ) as tmp:
            root = Path(tmp)
            observed_free = int(21.046 * 1024**3)
            selected, rows = stage_a_pro6000.select_storage_root(
                [root],
                minimum_free_gib=stage_a_pro6000.storage_floor_gib(
                    "stage-a-run",
                    "Qwen/Qwen2.5-7B-Instruct",
                ),
                disk_usage_fn=lambda path: SimpleNamespace(
                    free=observed_free
                ),
                probe_fn=lambda path, prefix: None,
            )
            self.assertEqual(selected, root.resolve())
            self.assertTrue(rows[0]["eligible"])
            with self.assertRaisesRegex(RuntimeError, "32.0 GiB"):
                stage_a_pro6000.select_storage_root(
                    [root],
                    minimum_free_gib=stage_a_pro6000.storage_floor_gib(
                        "preflight",
                        "Qwen/Qwen2.5-7B-Instruct",
                    ),
                    disk_usage_fn=lambda path: SimpleNamespace(
                        free=observed_free
                    ),
                    probe_fn=lambda path, prefix: None,
                )

    def test_precise_host_cache_gate_remains_stricter_when_cache_is_cold(
        self,
    ) -> None:
        observed_free = int(21.046 * 1024**3)
        operational_only_free = int(20.9 * 1024**3)
        cold_missing = 15_242_807_270
        required = stage_a_pro6000.required_model_cache_free_bytes(
            cold_missing
        )
        self.assertGreater(operational_only_free, 20 * 1024**3)
        self.assertGreater(required, operational_only_free)
        self.assertLess(required, observed_free)
        self.assertLess(
            stage_a_pro6000.required_model_cache_free_bytes(0),
            observed_free,
        )
        with self.assertRaisesRegex(ValueError, "non-negative"):
            stage_a_pro6000.required_model_cache_free_bytes(-1)

    def test_symlink_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="goai-storage-link-",
            dir=PLAIN_TEMP_ROOT,
        ) as tmp:
            root = Path(tmp)
            target = root / "target"
            link = root / "link"
            target.mkdir()
            os.symlink(target, link)
            with self.assertRaisesRegex(RuntimeError, "no plain writable"):
                stage_a_pro6000.select_storage_root(
                    [link],
                    minimum_free_gib=1,
                    disk_usage_fn=lambda path: SimpleNamespace(
                        free=100 * 1024**3
                    ),
                    probe_fn=lambda path, prefix: None,
                )

    def test_artifact_boundary_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="goai-boundary-",
            dir=PLAIN_TEMP_ROOT,
        ) as tmp:
            root = Path(tmp)
            selected = root / "selected"
            run = selected / "runs" / "1-1"
            other = root / "other"
            run.mkdir(parents=True)
            other.mkdir()
            with self.assertRaisesRegex(RuntimeError, "differs"):
                stage_a_pro6000.validate_artifact_boundary(
                    run_dir=other,
                    expected_run_dir=str(run),
                    expected_root=str(selected),
                    fallback_run_dir=root / "fallback",
                )


if __name__ == "__main__":
    unittest.main()
