#!/usr/bin/env python3
"""Validate the frozen v2 task manifest against available deterministic tiers."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[6]
for path in (PACKAGE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import demo
from v2.lean_verify import verify_source

DEFAULT_MANIFEST = PACKAGE_ROOT / "v2" / "artifacts" / "task-manifest.jsonl"
DEFAULT_OUTPUT = PACKAGE_ROOT / "v2" / "artifacts" / "task-validation.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lean_source(gold: dict) -> str:
    theorem = str(gold.get("theorem") or "").strip()
    proof = str(gold.get("proof") or "").strip()
    if not theorem or not proof:
        return ""
    return (
        "import Mathlib\n"
        "open BigOperators Real Nat Topology Rat\n\n"
        f"{theorem}\n  {proof}\n"
    )


def _git_commit(path: Path) -> str | None:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return value if len(value) == 40 else None


def validate(
    manifest: Path,
    *,
    lean_project: Path | None = None,
    require_lean: bool = False,
    timeout_s: int = 60,
    lean_version: str = "4.24.0",
) -> tuple[list[str], dict]:
    errors: list[str] = []
    rows: list[dict] = []
    for line_number, line in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {line_number}: row must be an object")
            continue
        rows.append(row)

    counts = Counter()
    receipts: list[dict] = []
    for row in rows:
        task_id = str(row.get("task_id") or "")
        domain = row.get("domain")
        split = row.get("split")
        if split == "frontier-gap":
            reason = row.get("expected_abstain_reason")
            ok = (
                row.get("expected_terminal") == "abstain"
                and isinstance(reason, str)
                and bool(reason)
            )
            verdict = "abstain" if ok else "invalid"
            why = reason or "missing expected abstain reason"
        elif domain == "physics":
            gold = str(row.get("gold") or "")
            result = demo.verify_physics(gold, gold)
            verdict, why = result.verdict, result.reason_code
            ok = verdict == "accepted"
        elif domain == "symbolic":
            gold = str(row.get("gold") or "")
            result = demo.verify_math(gold, gold)
            verdict, why = result.verdict, result.reason_code
            ok = verdict == "accepted" or (
                not demo._sympy_available()
                and verdict == "abstain"
                and why == "sympy_unavailable"
            )
        elif domain == "lean":
            source = _lean_source(row.get("gold") or {})
            if not source:
                verdict, why, ok = "invalid", "missing Lean theorem/proof", False
            elif lean_project is None:
                verdict, why = "abstain", "lean_project_not_supplied"
                ok = not require_lean
            else:
                verdict, why = verify_source(source, lean_project, timeout_s)
                ok = verdict == "accepted"
        else:
            verdict, why, ok = "invalid", f"unknown domain {domain!r}", False

        counts[f"{domain}:{verdict}"] += 1
        receipts.append(
            {
                "taskId": task_id,
                "domain": domain,
                "split": split,
                "verdict": verdict,
                "reason": why,
                "valid": ok,
            }
        )
        if not ok:
            errors.append(f"{task_id}: {verdict}: {why}")

    lean_commit = _git_commit(lean_project) if lean_project else None
    if require_lean and lean_project is not None and lean_commit is None:
        errors.append("pinned Lean project commit could not be resolved")
    summary = {
        "schema": "goai-frontier-task-validation/v1",
        "manifest": manifest.name,
        "manifestSha256": _sha256(manifest),
        "taskCount": len(rows),
        "validCount": sum(receipt["valid"] for receipt in receipts),
        "invalidCount": sum(not receipt["valid"] for receipt in receipts),
        "leanVersion": lean_version if lean_project else None,
        "leanProjectLabel": "pinned-miniF2F-lean4" if lean_project else None,
        "leanProjectRepository": (
            "yangky11/miniF2F-lean4" if lean_project else None
        ),
        "leanProjectCommit": lean_commit,
        "leanRequired": require_lean,
        "counts": dict(sorted(counts.items())),
        "receipts": receipts,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return errors, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--lean-project", type=Path)
    parser.add_argument("--require-lean", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--lean-version", default="4.24.0")
    args = parser.parse_args()
    errors, summary = validate(
        args.manifest,
        lean_project=args.lean_project,
        require_lean=args.require_lean,
        timeout_s=args.timeout,
        lean_version=args.lean_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        print("TASK VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        f"TASK VALIDATION: PASS ({summary['validCount']}/{summary['taskCount']}; "
        f"Lean {'required' if args.require_lean else 'optional'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
