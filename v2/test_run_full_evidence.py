#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Tests for the single-command execution-log builder.

These tests cover the orchestration layer of ``run_full_evidence``: the module
registry, the per-module runner (including FAIL/SKIP capture via dependency
injection), the JSONL log + JSON summary structure, the claim-ceiling
preservation, and the ``--check`` currency contract (idempotency + tamper
detection).

They do NOT assert any module's specific metric values beyond what is needed
to confirm the plumbing -- the per-module test files own those invariants.
All artifacts here are written to a per-test temp directory so the real
``v2/artifacts`` tree is never touched.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from v2 import run_full_evidence as rfe


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class ModuleRegistryTests(unittest.TestCase):
    def test_registry_has_exactly_the_seven_required_modules(self) -> None:
        specs = rfe.module_specs()
        names = [s.module_name for s in specs]
        self.assertEqual(len(specs), 7)
        # The brief's required module set, in declared run order.
        self.assertEqual(
            names,
            [
                "logic-error-catch-rate-audit",
                "baseline-comparison",
                "self-correction-audit",
                "error-rag-audit",
                "ill-posed-tasks",
                "ill-posed-audit",
                "stage-a",
            ],
        )

    def test_orders_are_one_through_seven_in_sequence(self) -> None:
        specs = rfe.module_specs()
        self.assertEqual([s.order for s in specs], list(range(1, 8)))

    def test_every_spec_has_a_build_and_metrics_fn(self) -> None:
        for spec in rfe.module_specs():
            self.assertTrue(callable(spec.build), spec.module_name)
            self.assertTrue(callable(spec.metrics_fn), spec.module_name)
            self.assertIsInstance(str(spec.artifact_path), str)

    def test_module_names_are_unique(self) -> None:
        names = [s.module_name for s in rfe.module_specs()]
        self.assertEqual(len(names), len(set(names)))


# --------------------------------------------------------------------------- #
# Runner: per-module execution and status capture
# --------------------------------------------------------------------------- #
class RunnerStatusTests(unittest.TestCase):
    """The runner must capture each module's real payload, not just exit codes.

    Uses synthetic ModuleSpecs with injected build/metrics functions so the
    PASS / FAIL / SKIP paths can be exercised deterministically without
    depending on the real (and slow) evidence modules.
    """

    def _spec(
        self,
        name: str,
        *,
        payload: dict,
        order: int = 1,
        metrics_fn=None,
    ) -> rfe.ModuleSpec:
        if metrics_fn is None:
            metrics_fn = lambda p: {"value": p.get("value")}  # noqa: E731
        return rfe.ModuleSpec(
            module_name=name,
            build=lambda payload=payload: payload,  # noqa: E731
            metrics_fn=metrics_fn,
            artifact_path=Path("/tmp/synthetic") / f"{name}.json",
            order=order,
        )

    def test_pass_module_captures_payload_metrics(self) -> None:
        spec = self._spec("ok", payload={"status": "PASS", "value": 42}, order=1)
        run = rfe._run_one(spec)
        self.assertEqual(run.status, "PASS")
        self.assertEqual(run.key_metrics, {"value": 42})
        self.assertGreater(run.duration_seconds, 0.0)
        self.assertTrue(run.timestamp)  # ISO-8601 present
        self.assertFalse(run.error)

    def test_module_status_is_authoritative_when_present(self) -> None:
        """A module reporting status=FAIL in its payload must be recorded FAIL."""
        spec = self._spec("flaky", payload={"status": "FAIL", "value": 7})
        run = rfe._run_one(spec)
        self.assertEqual(run.status, "FAIL")
        # The build itself succeeded, so this is a recorded FAIL, not a SKIP.
        self.assertFalse(run.error)

    def test_build_without_status_field_defaults_to_pass(self) -> None:
        """Modules with no top-level status (e.g. stage-a) PASS on a clean build."""
        spec = self._spec("statusless", payload={"familyCount": 24})
        run = rfe._run_one(spec)
        self.assertEqual(run.status, "PASS")

    def test_raising_build_is_recorded_as_skip_with_error(self) -> None:
        def boom() -> dict:
            raise RuntimeError("synthetic explosion")

        spec = rfe.ModuleSpec(
            module_name="bomb",
            build=boom,
            metrics_fn=lambda p: {},
            artifact_path=Path("/tmp/bomb.json"),
            order=2,
        )
        run = rfe._run_one(spec)
        self.assertEqual(run.status, "SKIP")
        self.assertIn("synthetic explosion", run.error)
        self.assertIn("RuntimeError", run.error)

    def test_metrics_extraction_failure_is_recorded_as_fail(self) -> None:
        spec = self._spec(
            "bad-metrics",
            payload={"status": "PASS"},
            metrics_fn=lambda p: (_ for _ in ()).throw(KeyError("missing")),
        )
        run = rfe._run_one(spec)
        self.assertEqual(run.status, "FAIL")
        self.assertIn("metrics extraction failed", run.error)


class RunAllTests(unittest.TestCase):
    def test_run_all_does_not_raise_even_when_a_module_skips(self) -> None:
        """The runner never aborts the whole sequence on a module error."""
        good = rfe.ModuleSpec(
            module_name="good",
            build=lambda: {"status": "PASS"},  # noqa: E731
            metrics_fn=lambda p: {"ok": True},
            artifact_path=Path("/tmp/good.json"),
            order=1,
        )
        bad = rfe.ModuleSpec(
            module_name="bad",
            build=lambda: (_ for _ in ()).throw(ValueError("nope")),  # noqa: E731
            metrics_fn=lambda p: {},
            artifact_path=Path("/tmp/bad.json"),
            order=2,
        )
        with mock.patch.object(rfe, "module_specs", return_value=[good, bad]):
            runs = rfe.run_all()
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].status, "PASS")
        self.assertEqual(runs[1].status, "SKIP")
        self.assertIn("nope", runs[1].error)


# --------------------------------------------------------------------------- #
# Log + summary structure
# --------------------------------------------------------------------------- #
class LogSummaryStructureTests(unittest.TestCase):
    """Write to temp dirs and assert the on-disk structure."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.log_path = self.tmp / "execution-log.jsonl"
        self.summary_path = self.tmp / "execution-summary.json"
        # Synthetic runs covering PASS, FAIL, and SKIP.
        self.runs = [
            rfe.ModuleRun(
                module_name="alpha",
                order=1,
                status="PASS",
                key_metrics={"catchRate": 1.0, "planted": 10},
                duration_seconds=0.5,
                timestamp="2026-08-01T00:00:00Z",
                artifact_path="/tmp/alpha.json",
            ),
            rfe.ModuleRun(
                module_name="beta",
                order=2,
                status="FAIL",
                key_metrics={"catchRate": 0.5},
                duration_seconds=0.25,
                timestamp="2026-08-01T00:00:01Z",
                artifact_path="/tmp/beta.json",
            ),
            rfe.ModuleRun(
                module_name="gamma",
                order=3,
                status="SKIP",
                key_metrics={},
                duration_seconds=0.0,
                timestamp="2026-08-01T00:00:02Z",
                artifact_path="/tmp/gamma.json",
                error="ImportError: missing dep",
            ),
        ]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_log_has_one_jsonl_line_per_run_in_order(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        lines = [
            ln for ln in self.log_path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        self.assertEqual(len(lines), 3)
        objs = [json.loads(ln) for ln in lines]
        self.assertEqual([o["module_name"] for o in objs], ["alpha", "beta", "gamma"])
        self.assertEqual([o["order"] for o in objs], [1, 2, 3])

    def test_every_log_line_has_required_fields(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            for key in (
                "module_name",
                "status",
                "key_metrics",
                "duration_seconds",
                "timestamp",
            ):
                self.assertIn(key, obj, key)

    def test_skip_error_is_recorded_in_log_line(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        lines = [ln for ln in self.log_path.read_text().splitlines() if ln.strip()]
        gamma = json.loads(lines[2])
        self.assertEqual(gamma["status"], "SKIP")
        self.assertIn("error", gamma)
        self.assertIn("ImportError", gamma["error"])

    def test_summary_schema_and_counts(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema"], rfe.SCHEMA)
        self.assertEqual(summary["totalModules"], 3)
        self.assertEqual(summary["passedCount"], 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(summary["skippedCount"], 1)
        self.assertEqual(summary["overallStatus"], "FAIL")

    def test_summary_modules_list_preserves_order_and_status(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        modules = summary["modules"]
        self.assertEqual([m["module_name"] for m in modules], ["alpha", "beta", "gamma"])
        self.assertEqual([m["status"] for m in modules], ["PASS", "FAIL", "SKIP"])

    def test_summary_claim_ceiling_is_locked(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        ceiling = summary["claimCeiling"]
        self.assertTrue(ceiling["candidateOnly"])
        self.assertFalse(ceiling["canClaimAGI"])
        self.assertFalse(ceiling["winnerLevelEligible"])
        self.assertFalse(ceiling["winnerLevelGateMet"])
        # The ceiling is also pinned at the top level for easy discovery.
        self.assertTrue(summary["candidateOnly"])
        self.assertFalse(summary["canClaimAGI"])

    def test_summary_interpretation_mentions_reproducible(self) -> None:
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        interp = summary["interpretation"]
        self.assertIn("deterministic", interp)
        self.assertIn("CPU-only", interp)
        self.assertIn("Reproducible", interp)

    def test_all_metrics_namespaced_by_module(self) -> None:
        """allMetrics flattens every module's metrics under its own namespace."""
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        all_m = summary["allMetrics"]
        self.assertEqual(all_m["alpha.catchRate"], 1.0)
        self.assertEqual(all_m["alpha.planted"], 10)
        self.assertEqual(all_m["beta.catchRate"], 0.5)


class HeadlineMetricsTests(unittest.TestCase):
    def test_headline_pulls_named_metrics_from_owning_modules(self) -> None:
        runs = [
            rfe.ModuleRun(
                module_name="logic-error-catch-rate-audit",
                order=1,
                status="PASS",
                key_metrics={"catchRate": 1.0, "planted": 67, "missed": 0},
            ),
            rfe.ModuleRun(
                module_name="ill-posed-audit",
                order=6,
                status="FAIL",
                key_metrics={
                    "illPosedCatchRate": 1.0,
                    "illPosedCaught": 30,
                    "illPosedMissed": 0,
                    "wellPosedFalseAlarmRate": 1.0,
                },
            ),
            rfe.ModuleRun(
                module_name="self-correction-audit",
                order=3,
                status="PASS",
                key_metrics={
                    "errorReductionRate": 0.8358,
                    "rejectionClearedRate": 1.0,
                },
            ),
            rfe.ModuleRun(
                module_name="stage-a",
                order=7,
                status="PASS",
                key_metrics={"familyCount": 24, "domainCounts": {"lean": 8}},
            ),
        ]
        hm = rfe._headline_metrics(runs)
        self.assertEqual(hm["catchRate"], 1.0)
        self.assertEqual(hm["illPosedCatchRate"], 1.0)
        self.assertEqual(hm["selfCorrectionRate"], 0.8358)
        self.assertEqual(hm["stageAFamilyCount"], 24)
        self.assertEqual(hm["wellPosedFalseAlarmRate"], 1.0)


# --------------------------------------------------------------------------- #
# Check mode: currency contract + tamper detection
# --------------------------------------------------------------------------- #
class CheckModeTests(unittest.TestCase):
    """--check must pass on a freshly-built log and fail on any tampering."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.log_path = self.tmp / "execution-log.jsonl"
        self.summary_path = self.tmp / "execution-summary.json"
        # Build once with synthetic runs so the on-disk artifacts exist.
        self.runs = [
            rfe.ModuleRun(
                module_name="alpha",
                order=1,
                status="PASS",
                key_metrics={"catchRate": 1.0},
                duration_seconds=0.1,
                timestamp="2026-08-01T00:00:00Z",
                artifact_path="/tmp/alpha.json",
            ),
            rfe.ModuleRun(
                module_name="beta",
                order=2,
                status="FAIL",
                key_metrics={"catchRate": 0.5},
                duration_seconds=0.1,
                timestamp="2026-08-01T00:00:01Z",
                artifact_path="/tmp/beta.json",
            ),
        ]
        rfe.write_log_and_summary(
            self.runs, log_path=self.log_path, summary_path=self.summary_path
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _check(self) -> int:
        """Run check against the temp paths, patching run_all to return the
        same synthetic runs (so currency holds without rebuilding real modules)."""
        with mock.patch.object(rfe, "run_all", return_value=self.runs):
            return rfe.check(log_path=self.log_path, summary_path=self.summary_path)

    def test_check_passes_on_freshly_built_artifacts(self) -> None:
        self.assertEqual(self._check(), 0)

    def test_check_returns_nonzero_when_summary_missing(self) -> None:
        self.summary_path.unlink()
        self.assertEqual(self._check(), 1)

    def test_check_returns_nonzero_when_log_missing(self) -> None:
        self.log_path.unlink()
        self.assertEqual(self._check(), 1)

    def test_check_detects_summary_metric_tampering(self) -> None:
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        summary["keyMetrics"]["catchRate"] = 0.0  # tamper
        self.summary_path.write_text(json.dumps(summary))
        self.assertEqual(self._check(), 1)

    def test_check_detects_log_status_tampering(self) -> None:
        lines = [ln for ln in self.log_path.read_text().splitlines() if ln.strip()]
        first = json.loads(lines[0])
        first["status"] = "SKIP"  # tamper a module status
        lines[0] = json.dumps(first, separators=(",", ":"))
        self.log_path.write_text("\n".join(lines) + "\n")
        self.assertEqual(self._check(), 1)

    def test_check_ignores_timestamp_drift(self) -> None:
        """A rebuilt summary with different timing fields must still be current.

        This is the core reproducibility contract: WHEN/HOW LONG are not part
        of the equality check; the EVIDENCE is.
        """
        drifted = [
            rfe.ModuleRun(
                module_name=r.module_name,
                order=r.order,
                status=r.status,
                key_metrics=dict(r.key_metrics),
                duration_seconds=999.0,  # totally different timing
                timestamp="1999-01-01T00:00:00Z",
                artifact_path=r.artifact_path,
            )
            for r in self.runs
        ]
        with mock.patch.object(rfe, "run_all", return_value=drifted):
            # The on-disk artifacts still carry the ORIGINAL timing; check must
            # pass because the evidence content is identical.
            self.assertEqual(
                rfe.check(log_path=self.log_path, summary_path=self.summary_path),
                0,
            )

    def test_check_reports_module_failures_but_still_current(self) -> None:
        """A module FAIL is honest evidence, not a check failure.

        The on-disk log records beta=FAIL; check must still return 0 because
        the log faithfully reproduces the (failing) module's output.
        """
        rc = self._check()
        self.assertEqual(rc, 0)


class StripTimingTests(unittest.TestCase):
    """The timing-stripping helper is the heart of the check contract."""

    def test_removes_timing_keys_at_all_levels(self) -> None:
        obj = {
            "generatedAt": "2026-01-01T00:00:00Z",
            "totalDurationSeconds": 1.5,
            "modules": [
                {"name": "a", "duration_seconds": 0.5, "status": "PASS", "timestamp": "t1"},
                {"name": "b", "duration_seconds": 0.5, "status": "FAIL", "timestamp": "t2"},
            ],
            "keyMetrics": {"catchRate": 1.0},
        }
        stripped = rfe._strip_timing(obj)
        self.assertNotIn("generatedAt", stripped)
        self.assertNotIn("totalDurationSeconds", stripped)
        for m in stripped["modules"]:
            self.assertNotIn("duration_seconds", m)
            self.assertNotIn("timestamp", m)
        # Non-timing content is preserved exactly.
        self.assertEqual(stripped["keyMetrics"], {"catchRate": 1.0})
        self.assertEqual([m["name"] for m in stripped["modules"]], ["a", "b"])
        self.assertEqual([m["status"] for m in stripped["modules"]], ["PASS", "FAIL"])

    def test_strip_then_fingerprint_is_deterministic(self) -> None:
        a = {"x": 1, "timestamp": "a", "duration_seconds": 1.0}
        b = {"x": 1, "timestamp": "b", "duration_seconds": 2.0}
        self.assertEqual(rfe._canonical_bytes(rfe._strip_timing(a)), rfe._canonical_bytes(rfe._strip_timing(b)))


# --------------------------------------------------------------------------- #
# CLI smoke (build + check round-trip, fully self-contained)
# --------------------------------------------------------------------------- #
class CLISmokeTests(unittest.TestCase):
    """End-to-end exercise of the ``main`` CLI entry points.

    These build REAL artifacts into a per-test temp directory and then run
    ``--check`` against them. They are self-contained: they do NOT depend on
    the committed ``v2/artifacts/execution-*`` files being current, because
    a unit-test process can exercise sympy/Lean-verifier internals differently
    than the canonical build process. The contract under test is that build
    writes the artifacts and check verifies them, in the same process.
    """

    def _build_into(self, tmp: Path) -> tuple[Path, Path]:
        log_path = tmp / "execution-log.jsonl"
        summary_path = tmp / "execution-summary.json"
        with mock.patch("sys.stdout"):
            rc = rfe.main(
                ["--log-path", str(log_path), "--summary-path", str(summary_path)]
            )
        # By default the build exits 0 whenever the artifacts are written,
        # because a module's honest status=FAIL is recorded evidence, not a
        # build error. (The real ill-posed-audit reports FAIL.)
        self.assertEqual(rc, 0)
        self.assertTrue(log_path.is_file(), "build must write the log")
        self.assertTrue(summary_path.is_file(), "build must write the summary")
        return log_path, summary_path

    def test_build_writes_log_and_summary_with_seven_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path, summary_path = self._build_into(Path(tmp))
            log_lines = [
                ln for ln in log_path.read_text().splitlines() if ln.strip()
            ]
            self.assertEqual(len(log_lines), 7)  # one JSONL line per module
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["totalModules"], 7)
            self.assertEqual(summary["schema"], rfe.SCHEMA)

    def test_check_passes_on_freshly_built_artifacts(self) -> None:
        """--check against artifacts built in THIS process must return 0."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path, summary_path = self._build_into(Path(tmp))
            with mock.patch("sys.stdout"):
                rc = rfe.main(
                    [
                        "--check",
                        "--log-path", str(log_path),
                        "--summary-path", str(summary_path),
                    ]
                )
            self.assertEqual(rc, 0)

    def test_check_detects_tampering_after_build(self) -> None:
        """Tampering a freshly-built summary must flip --check to non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path, summary_path = self._build_into(Path(tmp))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            # Tamper a headline metric.
            if summary["keyMetrics"]:
                first_key = next(iter(summary["keyMetrics"]))
                summary["keyMetrics"][first_key] = "TAMPERED"
            else:
                summary["keyMetrics"] = {"injected": True}
            summary_path.write_text(json.dumps(summary))
            with mock.patch("sys.stdout"):
                rc = rfe.main(
                    [
                        "--check",
                        "--log-path", str(log_path),
                        "--summary-path", str(summary_path),
                    ]
                )
            self.assertEqual(rc, 1)

    def test_strict_flag_fails_build_when_a_module_did_not_pass(self) -> None:
        """--strict makes a recorded module FAIL fail the build (exit 1).

        The real ill-posed-audit honestly reports FAIL (it abstains on
        well-posed controls), so --strict against the real module set must
        return non-zero while the default build returns 0.
        """
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "execution-log.jsonl"
            summary_path = Path(tmp) / "execution-summary.json"
            # Default build: exits 0 (FAIL is recorded evidence).
            with mock.patch("sys.stdout"):
                default_rc = rfe.main(
                    ["--log-path", str(log_path), "--summary-path", str(summary_path)]
                )
            self.assertEqual(default_rc, 0)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            # Only assert the strict contract if there really is a non-PASS
            # module in this environment; otherwise the flag is vacuous.
            if summary["overallStatus"] != "PASS":
                with mock.patch("sys.stdout"):
                    strict_rc = rfe.main(
                        [
                            "--strict",
                            "--log-path", str(log_path),
                            "--summary-path", str(summary_path),
                        ]
                    )
                self.assertEqual(strict_rc, 1)


if __name__ == "__main__":
    unittest.main()
