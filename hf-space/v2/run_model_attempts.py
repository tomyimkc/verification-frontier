#!/usr/bin/env python3
"""Run frozen GOAI v2 prompts through declared model providers.

Secrets are read only through the provider environment variables already used
by ``agent.model``. Secret values are never written to artifacts or printed.
The complete model text is retained, together with provider/model/usage/error
receipts. No cross-provider fallback is permitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[6]
for path in (PACKAGE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent.model import ModelClient, ModelConfig, ModelResult, resolve_config

DEFAULT_MANIFEST = PACKAGE_ROOT / "v2" / "artifacts" / "task-manifest.jsonl"
DEFAULT_OUTPUT = PACKAGE_ROOT / "v2" / "artifacts" / "raw-model-attempts.jsonl"
DEFAULT_RUN_MANIFEST = PACKAGE_ROOT / "v2" / "artifacts" / "run-manifest.json"
DEFAULT_MODELS = (
    "openrouter:qwen/qwen3.7-max",
    "openrouter:deepseek/deepseek-v4-pro",
    "zai:glm-5.2",
)

SYSTEM = """You are participating in a preregistered scientific-verification study.
Follow the requested output format exactly. Do not claim to have solved an open
problem. If the task is under-specified or lacks a checkable target, state that
briefly instead of inventing missing evidence. No tools or external browsing are
available."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PACKAGE_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def git_dirty() -> bool:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=REPO_ROOT,
                text=True,
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return True


def load_rows(
    manifest: Path,
    *,
    domains: set[str] | None = None,
    splits: set[str] | None = None,
    limit: int = 0,
) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"manifest line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"manifest line {line_number}: row must be an object")
        if domains and row.get("domain") not in domains:
            continue
        row_split = row.get("split") or row.get("component")
        if splits and row_split not in splits:
            continue
        rows.append(row)
        if limit and len(rows) >= limit:
            break
    return rows


def prompt_for(row: dict) -> str:
    domain = row.get("domain")
    prompt = str(row.get("prompt") or "")
    if domain == "physics":
        instruction = (
            "Return only the final numeric value with SI units. If the target is "
            "not executable from the supplied information, return "
            "`ABSTAIN: <short reason>`."
        )
    elif domain == "symbolic":
        instruction = (
            "Return only the final symbolic expression. If assumptions, domain, "
            "or verifier support are missing, return `ABSTAIN: <short reason>`."
        )
    elif domain == "lean":
        instruction = (
            "For an executable Lean theorem, return only the proof body that "
            "follows `by`, with no markdown. If no faithful executable theorem is "
            "supplied, return `ABSTAIN: <short reason>`."
        )
    else:
        instruction = "Return `ABSTAIN: unsupported domain`."
    task_id = row.get("task_id") or row.get("taskId")
    return f"{instruction}\n\nTask ID: {task_id}\n{prompt}"


def result_row(
    *,
    row: dict,
    requested_spec: str,
    replicate: int,
    cfg: ModelConfig,
    result: ModelResult,
    started_at: str,
    completed_at: str,
    evidence_class: str,
) -> dict:
    requested_gateway = requested_spec.split(":", 1)[0]
    task_id = row.get("task_id") or row.get("taskId")
    split = row.get("split") or row.get("component")
    rung = row.get("rung") or row.get("component")
    return {
        "schema": "goai-frontier-model-attempt/v1",
        "taskId": task_id,
        "pairId": row.get("pairId"),
        "domain": row.get("domain"),
        "split": split,
        "rung": rung,
        "component": row.get("component"),
        "member": row.get("member"),
        "generatorFamily": row.get("generatorFamily"),
        "extensionClass": row.get("extensionClass"),
        "requestedModelSpec": requested_spec,
        "requestedGateway": requested_gateway,
        "resolvedProvider": requested_gateway,
        "resolvedProtocol": result.provider,
        "resolvedModel": result.model,
        "endpointHost": urlparse(cfg.base_url).hostname,
        "replicate": replicate,
        "seedRequested": cfg.seed,
        "temperature": cfg.temperature,
        "maxTokens": cfg.max_tokens,
        "startedAt": started_at,
        "completedAt": completed_at,
        "ok": result.ok,
        "response": result.text,
        "error": result.error,
        "promptTokens": result.prompt_tokens,
        "completionTokens": result.completion_tokens,
        "cacheTokens": result.cache_tokens,
        "latencySec": result.latency_sec,
        "reportedCostUsd": result.cost_usd,
        "finishReason": result.finish_reason,
        "fallbackUsed": result.fallback_used,
        "attempts": [asdict(attempt) for attempt in result.attempts],
        "evidenceClass": evidence_class,
        "candidateOnly": True,
        "canClaimAGI": False,
    }


def existing_keys(output: Path) -> set[tuple[str, str, int]]:
    keys: set[tuple[str, str, int]] = set()
    if not output.is_file():
        return keys
    for line in output.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        keys.add(
            (
                str(row.get("taskId") or ""),
                str(row.get("requestedModelSpec") or ""),
                int(row.get("replicate") or 0),
            )
        )
    return keys


def _client(cfg: ModelConfig) -> ModelClient:
    return ModelClient(
        cfg,
        fallbacks=[],
        retries=2,
        fallback_policy="never",
    )


def run_attempts(
    *,
    manifest: Path,
    output: Path,
    run_manifest_path: Path,
    model_specs: Iterable[str],
    attempts: int,
    domains: set[str] | None = None,
    splits: set[str] | None = None,
    limit: int = 0,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    timeout_sec: int = 180,
    dry_run: bool = False,
    resume: bool = True,
    evidence_class: str = "development-only",
    confirmatory_seal: Path | None = None,
    client_factory: Callable[[ModelConfig], ModelClient] = _client,
) -> dict:
    rows = load_rows(
        manifest,
        domains=domains,
        splits=splits,
        limit=limit,
    )
    specs = tuple(model_specs)
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if not specs:
        raise ValueError("at least one model spec is required")
    if evidence_class not in {"development-only", "confirmatory"}:
        raise ValueError("evidence_class must be development-only or confirmatory")
    if evidence_class == "confirmatory":
        raise RuntimeError(
            "confirmatory execution is disabled in this milestone until the "
            "hash-linked proposal, review, test, activation, transfer, "
            "protected-suite, rollback, and Lean readiness-receipt lifecycle "
            "is implemented and independently validated"
        )

    configs: dict[str, ModelConfig] = {}
    credentials: dict[str, str] = {}
    for spec in specs:
        cfg = resolve_config(spec)
        cfg.temperature = temperature
        cfg.max_tokens = max_tokens
        cfg.timeout_sec = timeout_sec
        configs[spec] = cfg
        credentials[spec] = (
            "available" if cfg.resolved_key() is not None else "missing"
        )
        if not dry_run and cfg.kind != "mock" and cfg.resolved_key() is None:
            raise RuntimeError(
                f"{spec}: missing credential environment variable {cfg.api_key_env}"
            )

    plan = {
        "schema": "goai-frontier-run-manifest/v1",
        "createdAt": utc_now(),
        "gitCommit": git_commit(),
        "gitWorkingTreeDirty": git_dirty(),
        "runnerSha256": sha256(Path(__file__)),
        "modelClientSha256": sha256(REPO_ROOT / "agent" / "model.py"),
        "taskManifest": public_path(manifest),
        "taskManifestSha256": sha256(manifest),
        "taskCount": len(rows),
        "modelSpecs": list(specs),
        "credentialStatus": credentials,
        "replicates": attempts,
        "temperature": temperature,
        "maxTokens": max_tokens,
        "timeoutSec": timeout_sec,
        "dryRun": dry_run,
        "evidenceClass": evidence_class,
        "confirmatorySeal": (
            public_path(confirmatory_seal)
            if confirmatory_seal is not None
            else None
        ),
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    run_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    run_manifest_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if dry_run:
        return plan

    completed = existing_keys(output) if resume else set()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output.parent,
        prefix=output.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        if resume and output.is_file():
            existing = output.read_text(encoding="utf-8")
            handle.write(existing)
            if existing and not existing.endswith("\n"):
                handle.write("\n")
        try:
            for spec in specs:
                cfg = configs[spec]
                client = client_factory(cfg)
                for row in rows:
                    for replicate in range(attempts):
                        task_id = str(row.get("task_id") or row.get("taskId") or "")
                        if not task_id:
                            raise ValueError("manifest row is missing task_id/taskId")
                        key = (task_id, spec, replicate)
                        if key in completed:
                            continue
                        cfg.seed = replicate
                        started = utc_now()
                        result = client.generate(
                            SYSTEM,
                            prompt_for(row),
                            tools=None,
                            extra_body={"seed": replicate},
                        )
                        finished = utc_now()
                        payload = result_row(
                            row=row,
                            requested_spec=spec,
                            replicate=replicate,
                            cfg=cfg,
                            result=result,
                            started_at=started,
                            completed_at=finished,
                            evidence_class=evidence_class,
                        )
                        handle.write(
                            json.dumps(
                                payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                            + "\n"
                        )
                        handle.flush()
        except BaseException:
            handle.flush()
            os.fsync(handle.fileno())
            tmp_path.replace(output)
            raise
    tmp_path.replace(output)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-manifest", type=Path, default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--domains", nargs="*")
    parser.add_argument("--splits", nargs="*")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--evidence-class",
        choices=("development-only", "confirmatory"),
        default="development-only",
    )
    parser.add_argument("--confirmatory-seal", type=Path)
    args = parser.parse_args()
    plan = run_attempts(
        manifest=args.manifest,
        output=args.output,
        run_manifest_path=args.run_manifest,
        model_specs=args.models,
        attempts=args.attempts,
        domains=set(args.domains) if args.domains else None,
        splits=set(args.splits) if args.splits else None,
        limit=args.limit,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_sec=args.timeout,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        evidence_class=args.evidence_class,
        confirmatory_seal=args.confirmatory_seal,
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
