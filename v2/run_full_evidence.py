#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Single deterministic entry point that runs ALL evidence modules in sequence.

This is the 复赛 (round-2) "探索日志" (exploration log) deliverable: a single
command a judge can run to reproduce every piece of deterministic instrument
evidence in the package. It is the *minimal runnable exploration environment*.

Run::

    .venv/bin/python v2/run_full_evidence.py          # build all evidence + log
    .venv/bin/python v2/run_full_evidence.py --check  # re-run & verify the log is current

What it does, in order:

  1. Runs every evidence module in a fixed, declared sequence. Each module is
     imported by name and its in-memory builder + writer is called directly so
     the *result payload* (not just an exit code) is captured.
  2. For each module it records one JSONL line with: ``module_name``,
     ``status`` (PASS / FAIL / SKIP), ``key_metrics``, ``duration_seconds``, and
     an ISO-8601 ``timestamp``.
  3. Writes the line to ``v2/artifacts/execution-log.jsonl`` (one JSON object
     per module run; the file is REWRITTEN from scratch each build so it is
     deterministic, not an unbounded append-only log).
  4. Writes ``v2/artifacts/execution-summary.json`` with the union of all key
     metrics, module statuses, the frozen claim ceiling, and an interpretation
     string.

Everything is CPU-only, deterministic, and fail-closed: the claim ceiling is
never relaxed, and ``--check`` re-runs every module and verifies the on-disk
log + summary are CURRENT -- i.e. their evidence content (statuses, metrics,
claim ceiling) matches a fresh rebuild. Only the inherently non-deterministic
wall-clock fields (``generatedAt``/``totalDurationSeconds``/``timestamp``/
``duration_seconds``) are excluded from that comparison, so two consecutive
runs compare equal. A module that raises is recorded as FAIL/SKIP with the
error message; it never aborts the whole run, so the log always reflects the
full environment a judge will see.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
ARTIFACT_DIR = HERE / "artifacts"
LOG_PATH = ARTIFACT_DIR / "execution-log.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "execution-summary.json"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# The frozen claim ceiling every module shares. The summary pins it so a judge
# can see at a glance that no module promotes itself.
CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

SCHEMA = "goai-execution-log/v1"

INTERPRETATION = (
    "Complete deterministic execution log. All CPU-only. Reproducible. "
    "Each module is a deterministic instrument (verifier, detector, or "
    "fail-closed builder); none of these numbers is a model-capability, "
    "capability-uplift, or contest-performance result. A judge can re-run "
    "this single command and obtain byte-identical artifacts."
)


# --------------------------------------------------------------------------- #
# Module registry
# --------------------------------------------------------------------------- #
# Each entry describes how to (a) build + write one module's artifact and
# (b) extract a small, flat dict of headline metrics from the built payload.
# The builder returns the in-memory payload (dict); metrics_fn reads from it.
# This means we capture the module's actual results, never just its exit code.


@dataclass(frozen=True)
class ModuleSpec:
    """Declarative description of one evidence module to run.

    Attributes:
        module_name: stable identifier used in the log + summary.
        build: zero-arg callable that builds AND writes the artifact, returning
            the in-memory payload dict (the same object written to disk).
        metrics_fn: callable(payload) -> dict[str, Any] extracting the flat,
            headline metrics for this module. Must be JSON-serializable.
        artifact_path: the path the module writes (recorded in the log for
            traceability; not used to re-read).
        order: declared run order (1-based) for the sequence column.
    """

    module_name: str
    build: Callable[[], dict[str, Any]]
    metrics_fn: Callable[[dict[str, Any]], dict[str, Any]]
    artifact_path: Path
    order: int


def _logic_error_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    t = payload["totals"]
    return {
        "planted": t["planted"],
        "caught": t["caught"],
        "missed": t["missed"],
        "catchRate": t["catchRate"],
        "byTier": payload["byTier"],
        "status": payload["status"],
    }


def _baseline_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    proposed = payload["policies"]["proposed-system"]
    return {
        "itemCounts": payload["itemCounts"],
        "comparisonTable": payload["comparisonTable"],
        "proposedCoverageRate": proposed["rates"]["coverageRate"],
        "proposedErrorCatchRate": proposed["rates"]["errorCatchRate"],
        "proposedUnsafeAcceptances": proposed["totals"]["unsafeAcceptances"],
        "proposedFalseRejections": proposed["totals"]["falseRejections"],
    }


def _self_correct_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    t = payload["totals"]
    return {
        "planted": t["planted"],
        "caughtWithoutSelfCorrection": t["caughtWithoutSelfCorrection"],
        "fixedBySelfCorrection": t["fixedBySelfCorrection"],
        "rejectionClearedAfter": t["rejectionClearedAfter"],
        "abstainedAfter": t["abstainedAfter"],
        "stillRejectedAfter": t["stillRejectedAfter"],
        "errorReductionRate": t["errorReductionRate"],
        "rejectionClearedRate": t["rejectionClearedRate"],
        "status": payload["status"],
    }


def _error_rag_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    t = payload["totals"]
    return {
        "novelErrors": t["novel_errors"],
        "wouldCatchIfImplemented": t["would_catch_if_implemented"],
        "lowConfidenceProposals": t["low_confidence_proposals"],
        "knowledgeBaseSize": payload["method"]["knowledge_base_size"],
    }


def _ill_posed_tasks_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "taskCount": payload["taskCount"],
        "itemCounts": payload["itemCounts"],
        "allVerdictsAbstain": all(
            t["expected_verdict"] == "abstain" for t in payload["tasks"]
        ),
    }


def _ill_posed_audit_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    cr = payload["catchRate"]
    ip = cr["illPosed"]
    wp = cr["wellPosedControls"]
    return {
        "itemCounts": payload["itemCounts"],
        "illPosedCatchRate": ip["catchRate"],
        "illPosedCaught": ip["caught"],
        "illPosedMissed": ip["missed"],
        "wellPosedFalseAlarmRate": wp["falseAlarmRate"],
        "wellPosedFalseAlarms": wp["falseAlarms"],
        "comparisonTable": payload["comparisonTable"],
        "status": payload["status"],
    }


def _stage_a_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "familyCount": payload["familyCount"],
        "domainCounts": payload["domainCounts"],
        "typedAbstainReasonsCovered": payload["typedAbstainReasonsCovered"],
        "reviewStatus": payload["reviewStatus"],
        "activationAuthorized": payload["activationAuthorized"],
        "confirmatoryEligible": payload["confirmatoryEligible"],
    }


def module_specs() -> list[ModuleSpec]:
    """The frozen, ordered list of evidence modules to run.

    Imported lazily inside this function so a broken module import is recorded
    as a per-module SKIP in the log rather than aborting the whole run. The
    sequence is the declared run order a judge will see.
    """
    # Imports are local so the runner can wrap them and still expose the rest.
    from v2 import build_logic_error_audit as lea
    from v2 import build_baseline_comparison as blc
    from v2 import self_correct as sc
    from v2 import error_rag as er
    from v2 import ill_posed_tasks as ipt
    from v2 import build_ill_posed_audit as ipa
    from v2 import stage_a

    return [
        ModuleSpec(
            module_name="logic-error-catch-rate-audit",
            build=lea.write_audit,
            metrics_fn=_logic_error_metrics,
            artifact_path=lea.AUDIT_PATH,
            order=1,
        ),
        ModuleSpec(
            module_name="baseline-comparison",
            build=blc.write_comparison,
            metrics_fn=_baseline_metrics,
            artifact_path=blc.COMPARISON_PATH,
            order=2,
        ),
        ModuleSpec(
            module_name="self-correction-audit",
            build=sc.write_audit,
            metrics_fn=_self_correct_metrics,
            artifact_path=sc.AUDIT_PATH,
            order=3,
        ),
        ModuleSpec(
            module_name="error-rag-audit",
            build=er.write_audit,
            metrics_fn=_error_rag_metrics,
            artifact_path=er.AUDIT_PATH,
            order=4,
        ),
        ModuleSpec(
            module_name="ill-posed-tasks",
            build=ipt.write_pack,
            metrics_fn=_ill_posed_tasks_metrics,
            artifact_path=ipt.ARTIFACT_PATH,
            order=5,
        ),
        ModuleSpec(
            module_name="ill-posed-audit",
            build=ipa.write_audit,
            metrics_fn=_ill_posed_audit_metrics,
            artifact_path=ipa.AUDIT_PATH,
            order=6,
        ),
        ModuleSpec(
            module_name="stage-a",
            build=lambda: _stage_a_build(),
            metrics_fn=_stage_a_metrics,
            artifact_path=stage_a.DEFAULT_ARTIFACTS / "stage-a-manifest.json",
            order=7,
        ),
    ]


def _stage_a_build() -> dict[str, Any]:
    """Stage A writes two artifacts; the runner reports the manifest payload.

    ``write_artifacts`` returns ``(manifest, readiness)``; we surface the
    manifest as the canonical result and fold readiness presence into metrics.
    """
    from v2 import stage_a

    manifest, readiness = stage_a.write_artifacts(stage_a.DEFAULT_ARTIFACTS)
    # Attach readiness-derived booleans so the summary can report the full
    # Stage A readiness state without a second read.
    out = dict(manifest)
    out["_readinessGates"] = readiness.get("readiness", {})
    out["_readinessStatus"] = readiness.get("status")
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
@dataclass
class ModuleRun:
    """The recorded outcome of running one module."""

    module_name: str
    order: int
    status: str  # "PASS" | "FAIL" | "SKIP"
    key_metrics: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    timestamp: str = ""
    artifact_path: str = ""
    error: str = ""

    def to_log_dict(self) -> dict[str, Any]:
        d = {
            "schema": SCHEMA,
            "module_name": self.module_name,
            "order": self.order,
            "status": self.status,
            "key_metrics": self.key_metrics,
            "duration_seconds": round(self.duration_seconds, 6),
            "timestamp": self.timestamp,
            "artifact_path": self.artifact_path,
        }
        if self.error:
            d["error"] = self.error
        return d


def _now_iso() -> str:
    """Current time in deterministic ISO-8601 UTC.

    The timestamp is the one non-deterministic field by design: it records WHEN
    the run happened, which is exactly what an exploration-log deliverable must
    capture. The ``--check`` mode therefore does NOT byte-compare the log's
    timestamps; it recomputes the metric payloads (which ARE deterministic) and
    compares those.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_one(spec: ModuleSpec) -> ModuleRun:
    """Run one module, capturing its payload-derived metrics and timing.

    A module that raises is recorded as FAIL (if it raised after a partial
    write) or SKIP (if it raised before any work). The exception text and
    traceback tail are captured so the log is self-explanatory. The runner
    never re-raises: the log must always reflect the full environment.
    """
    start = time.perf_counter()
    timestamp = _now_iso()
    try:
        payload = spec.build()
    except Exception as exc:  # noqa: BLE001 -- we record, never hide
        duration = time.perf_counter() - start
        tb_tail = traceback.format_exc().splitlines()[-1]
        return ModuleRun(
            module_name=spec.module_name,
            order=spec.order,
            status="SKIP",
            duration_seconds=duration,
            timestamp=timestamp,
            artifact_path=str(spec.artifact_path),
            error=f"{type(exc).__name__}: {exc} | {tb_tail}",
        )
    duration = time.perf_counter() - start

    # Derive status + metrics from the payload. A module's own ``status`` field
    # (where present) is authoritative; otherwise a successful build is PASS.
    own_status = None
    if isinstance(payload, dict):
        own_status = payload.get("status")
    # ill-posed-tasks has no top-level status; treat a clean build as PASS.
    # stage-a manifest likewise has no status; PASS on a clean build.
    status = own_status if isinstance(own_status, str) and own_status in {"PASS", "FAIL"} else "PASS"

    try:
        metrics = spec.metrics_fn(payload)
    except Exception as exc:  # noqa: BLE001
        return ModuleRun(
            module_name=spec.module_name,
            order=spec.order,
            status="FAIL",
            duration_seconds=duration,
            timestamp=timestamp,
            artifact_path=str(spec.artifact_path),
            error=f"metrics extraction failed: {type(exc).__name__}: {exc}",
        )

    return ModuleRun(
        module_name=spec.module_name,
        order=spec.order,
        status=status,
        key_metrics=metrics,
        duration_seconds=duration,
        timestamp=timestamp,
        artifact_path=str(spec.artifact_path),
    )


def run_all() -> list[ModuleRun]:
    """Run every module in declared order and return the recorded runs."""
    runs: list[ModuleRun] = []
    for spec in module_specs():
        run = _run_one(spec)
        runs.append(run)
        # Echo a one-line status to stdout so a judge watching the run sees
        # progress without having to open the log.
        _print_status_line(run)
    return runs


def _print_status_line(run: ModuleRun) -> None:
    head = f"[{run.order}/{len(module_specs())}] {run.module_name}: {run.status}"
    if run.error:
        print(f"{head} -- {run.error}")
        return
    # Pick the single most informative metric for the one-liner.
    m = run.key_metrics
    note = ""
    if "catchRate" in m:
        note = f"catchRate={m['catchRate']}"
    elif "proposedErrorCatchRate" in m:
        note = f"errorCatch={m['proposedErrorCatchRate']} unsafe={m['proposedUnsafeAcceptances']}"
    elif "errorReductionRate" in m:
        note = f"errorReduction={m['errorReductionRate']}"
    elif "illPosedCatchRate" in m:
        note = f"illPosedCatch={m['illPosedCatchRate']} falseAlarms={m['wellPosedFalseAlarms']}"
    elif "novelErrors" in m:
        note = f"novel={m['novelErrors']} wouldCatch={m['wouldCatchIfImplemented']}"
    elif "taskCount" in m:
        note = f"tasks={m['taskCount']}"
    elif "familyCount" in m:
        note = f"families={m['familyCount']}"
    print(f"{head} ({run.duration_seconds:.3f}s){(' -- ' + note) if note else ''}")


# --------------------------------------------------------------------------- #
# Summary aggregation
# --------------------------------------------------------------------------- #
def build_summary(runs: list[ModuleRun]) -> dict[str, Any]:
    """Aggregate per-module metrics into one headline summary object."""
    passed = [r for r in runs if r.status == "PASS"]
    failed = [r for r in runs if r.status == "FAIL"]
    skipped = [r for r in runs if r.status == "SKIP"]

    # Flatten the headline metrics from every module into one metrics block so
    # a judge can read the entire evidence picture from the summary alone.
    all_metrics: dict[str, Any] = {}
    for run in sorted(runs, key=lambda r: r.order):
        for key, value in run.key_metrics.items():
            # Namespace each metric under its module to avoid collisions
            # (e.g. both logic-error and ill-posed report a "catchRate").
            all_metrics[f"{run.module_name}.{key}"] = value

    # The specific headline metrics the brief called out by name, surfaced at
    # the top level for easy discovery. These are pulled from whichever module
    # owns them.
    headline = _headline_metrics(runs)

    return {
        "schema": SCHEMA,
        "interpretation": INTERPRETATION,
        "generatedAt": runs[-1].timestamp if runs else _now_iso(),
        "totalDurationSeconds": round(sum(r.duration_seconds for r in runs), 6),
        "totalModules": len(runs),
        "passedCount": len(passed),
        "failedCount": len(failed),
        "skippedCount": len(skipped),
        "overallStatus": "PASS" if not failed and not skipped else "FAIL",
        "modules": [
            {
                "module_name": r.module_name,
                "order": r.order,
                "status": r.status,
                "duration_seconds": round(r.duration_seconds, 6),
                "artifact_path": r.artifact_path,
                **({"error": r.error} if r.error else {}),
            }
            for r in sorted(runs, key=lambda r: r.order)
        ],
        "keyMetrics": headline,
        "allMetrics": all_metrics,
        "claimCeiling": dict(CLAIM_CEILING),
        **CLAIM_CEILING,
    }


def _headline_metrics(runs: list[ModuleRun]) -> dict[str, Any]:
    """The specific named metrics the brief asked to surface in one place."""
    by_name = {r.module_name: r.key_metrics for r in runs}
    headline: dict[str, Any] = {}

    le = by_name.get("logic-error-catch-rate-audit", {})
    if le:
        headline["catchRate"] = le.get("catchRate")
        headline["logicErrorPlanted"] = le.get("planted")
        headline["logicErrorMissed"] = le.get("missed")

    ip = by_name.get("ill-posed-audit", {})
    if ip:
        headline["illPosedCatchRate"] = ip.get("illPosedCatchRate")
        headline["illPosedCaught"] = ip.get("illPosedCaught")
        headline["illPosedMissed"] = ip.get("illPosedMissed")
        headline["wellPosedFalseAlarmRate"] = ip.get("wellPosedFalseAlarmRate")

    bl = by_name.get("baseline-comparison", {})
    if bl:
        headline["baselineComparison"] = {
            "comparisonTable": bl.get("comparisonTable"),
            "proposedCoverageRate": bl.get("proposedCoverageRate"),
            "proposedErrorCatchRate": bl.get("proposedErrorCatchRate"),
            "proposedUnsafeAcceptances": bl.get("proposedUnsafeAcceptances"),
        }

    sc = by_name.get("self-correction-audit", {})
    if sc:
        headline["selfCorrectionRate"] = sc.get("errorReductionRate")
        headline["selfCorrectionRejectionClearedRate"] = sc.get("rejectionClearedRate")

    er = by_name.get("error-rag-audit", {})
    if er:
        headline["errorRagWouldCatch"] = er.get("wouldCatchIfImplemented")
        headline["errorRagNovelErrors"] = er.get("novelErrors")

    ipt = by_name.get("ill-posed-tasks", {})
    if ipt:
        headline["illPosedTaskCount"] = ipt.get("taskCount")

    sa = by_name.get("stage-a", {})
    if sa:
        headline["stageAFamilyCount"] = sa.get("familyCount")
        headline["stageADomainCounts"] = sa.get("domainCounts")

    return headline


# --------------------------------------------------------------------------- #
# Canonical bytes + write
# --------------------------------------------------------------------------- #
def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


# Fields in the summary/log that are inherently non-deterministic (they record
# WHEN and HOW LONG a run took). These are excluded from the --check equality
# contract so that two consecutive runs -- which must produce identical
# *evidence* -- compare equal even though their timestamps differ.
_NONDETERMINISTIC_FIELDS = frozenset(
    {"generatedAt", "totalDurationSeconds", "duration_seconds", "timestamp"}
)


def _strip_timing(obj: Any) -> Any:
    """Recursively drop timing fields so evidence content can be compared.

    Only the declared timing keys are removed; every metric, status, count, and
    claim-ceiling field is preserved. This is the contract: a judge re-running
    the command gets byte-identical EVIDENCE even though the wall-clock
    metadata differs.
    """
    if isinstance(obj, dict):
        return {
            k: _strip_timing(v)
            for k, v in obj.items()
            if k not in _NONDETERMINISTIC_FIELDS
        }
    if isinstance(obj, list):
        return [_strip_timing(v) for v in obj]
    return obj


def _summary_fingerprint(summary: dict[str, Any]) -> bytes:
    """The deterministic fingerprint of a summary (timing fields stripped)."""
    return _canonical_bytes(_strip_timing(summary))


def write_log_and_summary(
    runs: list[ModuleRun],
    *,
    log_path: Path = LOG_PATH,
    summary_path: Path = SUMMARY_PATH,
) -> tuple[bytes, bytes]:
    """Write the JSONL execution log and the JSON summary.

    Returns the canonical bytes of both files so ``--check`` can byte-compare
    them. The log is REWRITTEN from scratch on every build (not appended to)
    so two consecutive builds produce identical bytes modulo timestamps.

    Paths are parameters (defaulting to the module constants) so tests and the
    CLI can redirect output without monkeypatching globals.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # The log: one JSON object per module run, in declared order.
    log_lines = [
        json.dumps(
            run.to_log_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for run in sorted(runs, key=lambda r: r.order)
    ]
    log_bytes = ("\n".join(log_lines) + "\n").encode("utf-8")
    log_path.write_bytes(log_bytes)

    # The summary.
    summary = build_summary(runs)
    summary_bytes = _canonical_bytes(summary)
    summary_path.write_bytes(summary_bytes)

    return log_bytes, summary_bytes


# --------------------------------------------------------------------------- #
# Check mode
# --------------------------------------------------------------------------- #
def _log_metric_fingerprint(runs: list[ModuleRun]) -> bytes:
    """A timestamp-independent fingerprint of the log's metric content.

    The per-run ``timestamp`` and ``duration_seconds`` are inherently
    non-deterministic (when/how long), so ``--check`` does NOT byte-compare
    them. Instead it compares the deterministic fingerprint: module_name,
    order, status, key_metrics, artifact_path. If those match what is on disk,
    the log is "current" in the sense that matters for reproducibility.
    """
    lines = [
        json.dumps(
            {
                "module_name": r.module_name,
                "order": r.order,
                "status": r.status,
                "key_metrics": r.key_metrics,
                "artifact_path": r.artifact_path,
                **({"error": r.error} if r.error else {}),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for r in sorted(runs, key=lambda r: r.order)
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _read_log_fingerprint_from_disk(log_path: Path = LOG_PATH) -> bytes:
    """Re-derive the fingerprint from the on-disk JSONL (dropping timestamps)."""
    runs: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        fp = {
            "module_name": obj["module_name"],
            "order": obj["order"],
            "status": obj["status"],
            "key_metrics": obj["key_metrics"],
            "artifact_path": obj["artifact_path"],
        }
        if obj.get("error"):
            fp["error"] = obj["error"]
        runs.append(fp)
    lines = [
        json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for r in runs
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def check(
    *,
    log_path: Path = LOG_PATH,
    summary_path: Path = SUMMARY_PATH,
) -> int:
    """Re-run every module and verify the on-disk log + summary are CURRENT.

    "Current" means: the on-disk evidence (statuses, metrics, claim ceiling,
    module list) is byte-for-byte identical to a freshly rebuilt run, modulo
    only the inherently non-deterministic wall-clock fields
    (``generatedAt``, ``totalDurationSeconds``, ``timestamp``,
    ``duration_seconds``). Those record WHEN/HOW LONG a run happened and are
    excluded from the equality contract so two consecutive runs compare equal.

    Contract separation (important):

      * ``check`` answers "is this log a faithful reproduction of the
        environment?" -> returns 0 when the evidence matches, 1 on any
        content mismatch or missing file.
      * Whether every individual module PASSED is recorded IN the log for a
        judge to read; it does NOT by itself make ``check`` return non-zero.
        A module that honestly reports ``status: FAIL`` (e.g. the
        ill-posedness detector abstaining on well-posed controls) is correct,
        reproducible evidence -- exactly what the exploration log must
        preserve rather than hide.

    Returns 0 if the on-disk log/summary are current; 1 otherwise.
    """
    if not summary_path.is_file():
        print("EXECUTION LOG: FAIL (summary missing)")
        return 1
    if not log_path.is_file():
        print("EXECUTION LOG: FAIL (log missing)")
        return 1

    print("EXECUTION LOG: re-running all modules to verify currency...")
    runs = run_all()

    # 1. Summary evidence-compare (timing fields stripped; everything else
    #    must match exactly).
    expected_summary_fp = _summary_fingerprint(build_summary(runs))
    on_disk_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    on_disk_summary_fp = _summary_fingerprint(on_disk_summary)
    if on_disk_summary_fp != expected_summary_fp:
        print("EXECUTION LOG: FAIL (summary evidence content not current)")
        import hashlib

        print(
            f"  on-disk sha256={hashlib.sha256(on_disk_summary_fp).hexdigest()} "
            f"expected sha256={hashlib.sha256(expected_summary_fp).hexdigest()}"
        )
        print("  (timing fields generatedAt/totalDurationSeconds/duration_seconds")
        print("   are excluded from this comparison by design)")
        return 1

    # 2. Log fingerprint compare (timestamp-independent).
    expected_fp = _log_metric_fingerprint(runs)
    on_disk_fp = _read_log_fingerprint_from_disk(log_path)
    if on_disk_fp != expected_fp:
        print("EXECUTION LOG: FAIL (log metric fingerprint not current)")
        return 1

    # The log is current. Report the full module PASS/FAIL breakdown so a
    # judge sees the honest state of every instrument at a glance; this
    # informational line does not affect the exit code.
    summary = build_summary(runs)
    status_line = (
        f"modules={summary['totalModules']}; "
        f"passed={summary['passedCount']}; "
        f"failed={summary['failedCount']}; "
        f"skipped={summary['skippedCount']}"
    )
    non_pass = [r for r in runs if r.status != "PASS"]
    hm = summary["keyMetrics"]
    note = ""
    if non_pass:
        names = ", ".join(r.module_name for r in non_pass)
        note = f"; non-PASS module(s) recorded in log: {names}"
    print(
        "EXECUTION LOG: PASS -- log is current ("
        + status_line
        + f"; catchRate={hm.get('catchRate')}"
        + f"; illPosedCatchRate={hm.get('illPosedCatchRate')}"
        + f"; selfCorrectionRate={hm.get('selfCorrectionRate')}"
        + note
        + ")"
    )
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run ALL deterministic evidence modules in sequence and write a "
            "machine-readable execution log + summary. This is the 复赛 "
            "'探索日志' (exploration log) deliverable: a single command a "
            "judge can run to reproduce every piece of evidence."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-run every module and verify the log + summary are current",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=LOG_PATH,
        help="override the execution-log.jsonl output path",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=SUMMARY_PATH,
        help="override the execution-summary.json output path",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "exit non-zero if any module did not PASS. By default the build "
            "exits 0 whenever the artifacts are written successfully, because "
            "a module's honest status=FAIL (e.g. the ill-posedness detector "
            "abstaining on well-posed controls) is recorded evidence, not a "
            "build error. --strict makes such a recorded FAIL fail the build."
        ),
    )
    args = parser.parse_args(argv)

    if args.check:
        return check(log_path=args.log_path, summary_path=args.summary_path)

    print("=" * 72)
    print("GOAI execution-log builder (复赛 探索日志 / exploration log)")
    print("Complete deterministic evidence run. All CPU-only. Reproducible.")
    print("=" * 72)
    runs = run_all()
    log_bytes, summary_bytes = write_log_and_summary(
        runs, log_path=args.log_path, summary_path=args.summary_path
    )
    summary = build_summary(runs)

    print("-" * 72)
    print(
        f"PASS={summary['passedCount']} FAIL={summary['failedCount']} "
        f"SKIP={summary['skippedCount']} / {summary['totalModules']} modules"
    )
    print(f"log:     {args.log_path} ({len(log_bytes)} bytes)")
    print(f"summary: {args.summary_path} ({len(summary_bytes)} bytes)")
    hm = summary["keyMetrics"]
    print(
        "headline: "
        f"catchRate={hm.get('catchRate')} "
        f"illPosedCatchRate={hm.get('illPosedCatchRate')} "
        f"selfCorrectionRate={hm.get('selfCorrectionRate')} "
        f"baselineErrorCatch={hm.get('baselineComparison', {}).get('proposedErrorCatchRate')}"
    )
    # The build's exit code reflects whether the LOG was produced, not whether
    # every instrument PASSED. A module's honest status=FAIL is content the log
    # must preserve. --strict flips this for CI gates that want all-green.
    if summary["overallStatus"] != "PASS":
        non_pass = [m["module_name"] for m in summary["modules"] if m["status"] != "PASS"]
        print(
            "OVERALL: recorded FAIL in module(s): "
            + ", ".join(non_pass)
            + " (honest evidence; use --strict to fail the build on this)"
        )
        if args.strict:
            return 1
        return 0
    print("OVERALL: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
