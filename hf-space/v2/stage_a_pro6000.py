#!/usr/bin/env python3
"""Fail-closed Pro6000 preflight for GOAI Stage A development runs.

Storage selection runs before a GPU claim, CUDA query, model-hub contact, or
model load. Host/model feasibility runs only after the workflow has acquired
the exact ``pro6000-gpu`` holder. The helper never deletes caches and supports
only the reviewed 7B development model.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

MODES = ("preflight", "development-smoke", "stage-a-run")
REVIEWED_MODELS = {
    "Qwen/Qwen2.5-7B-Instruct": {
        "minimumFreeGiB": 32.0,
        "minimumDevelopmentFreeGiB": 20.0,
        "minimumVramMiB": 90000,
        "expectedGpuSubstring": "RTX PRO 6000 Blackwell",
    }
}
CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}
EXCLUDED_ROOTS = (
    Path("/"),
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
    Path("/run"),
    Path("/boot"),
)


def canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload))


def validate_dispatch(mode: str, model: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"unsupported mode {mode!r}; expected one of {MODES}")
    if model not in REVIEWED_MODELS:
        raise ValueError(
            f"unreviewed model {model!r}; allowed={sorted(REVIEWED_MODELS)}"
        )
    minimum_free_gib = storage_floor_gib(mode, model)
    return {
        "schema": "goai-stage-a-pro6000-dispatch/v1",
        "mode": mode,
        "model": model,
        "minimumFreeGiB": minimum_free_gib,
        "coldCacheMinimumFreeGiB": REVIEWED_MODELS[model]["minimumFreeGiB"],
        "developmentMinimumFreeGiB": REVIEWED_MODELS[model][
            "minimumDevelopmentFreeGiB"
        ],
        "preciseCacheFeasibilityCheckedByHostPreflight": True,
        "developmentOnly": True,
        "confirmatoryExecutionAllowed": False,
        **CLAIM_CEILING,
    }


def storage_floor_gib(mode: str, model: str) -> float:
    if mode not in MODES:
        raise ValueError(f"unsupported mode {mode!r}; expected one of {MODES}")
    if model not in REVIEWED_MODELS:
        raise ValueError(
            f"unreviewed model {model!r}; allowed={sorted(REVIEWED_MODELS)}"
        )
    policy = REVIEWED_MODELS[model]
    if mode == "preflight":
        return float(policy["minimumFreeGiB"])
    return float(policy["minimumDevelopmentFreeGiB"])


def required_model_cache_free_bytes(missing_bytes: int) -> int:
    if missing_bytes < 0:
        raise ValueError("missing_bytes must be non-negative")
    return math.ceil(missing_bytes * 1.20 + 4 * 1024**3)


def _first_symlink_component(path: Path) -> Path | None:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode):
            return current
    return None


def _excluded(path: Path) -> bool:
    if path == Path("/"):
        return True
    return any(
        root != Path("/") and (path == root or root in path.parents)
        for root in EXCLUDED_ROOTS
    )


def storage_candidates(
    environ: dict[str, str] | None = None,
) -> list[Path]:
    env = os.environ if environ is None else environ
    raw = [
        Path("/workspace"),
        Path("/data"),
        Path("/mnt/data"),
        Path("/scratch"),
        Path(env.get("HOME", "~")).expanduser(),
    ]
    for key in ("RUNNER_TEMP", "GITHUB_WORKSPACE"):
        value = env.get(key)
        if value:
            raw.append(Path(value).expanduser().parent)
    seen: set[str] = set()
    output: list[Path] = []
    for candidate in raw:
        absolute = Path(os.path.abspath(os.fspath(candidate)))
        key = os.fspath(absolute)
        if key in seen:
            continue
        seen.add(key)
        output.append(absolute)
    return output


def _write_exec_probe(path: Path, prefix: str) -> None:
    directory = Path(tempfile.mkdtemp(prefix=prefix, dir=path))
    probe = directory / "probe.sh"
    try:
        probe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        probe.chmod(0o700)
        proc = subprocess.run(
            [str(probe)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode != 0:
            raise OSError(f"execution probe failed with rc={proc.returncode}")
    finally:
        probe.unlink(missing_ok=True)
        directory.rmdir()


def select_storage_root(
    candidates: Sequence[Path],
    *,
    minimum_free_gib: float,
    disk_usage_fn: Callable[[Path], Any] = shutil.disk_usage,
    probe_fn: Callable[[Path, str], None] = _write_exec_probe,
) -> tuple[Path, list[dict]]:
    if minimum_free_gib <= 0:
        raise ValueError("minimum_free_gib must be positive")
    rows: list[dict] = []
    eligible: list[tuple[int, Path]] = []
    floor_bytes = math.ceil(minimum_free_gib * (1024**3))
    for candidate in candidates:
        requested = Path(os.path.abspath(os.fspath(candidate)))
        row: dict[str, Any] = {
            "path": str(requested),
            "eligible": False,
        }
        symlink = _first_symlink_component(requested)
        if symlink is not None:
            row["reason"] = "symlinked-path-component"
            row["symlinkComponent"] = str(symlink)
            rows.append(row)
            continue
        try:
            info = os.lstat(requested)
        except OSError:
            row["reason"] = "absent"
            rows.append(row)
            continue
        if not stat.S_ISDIR(info.st_mode):
            row["reason"] = "not-directory"
            rows.append(row)
            continue
        resolved = requested.resolve(strict=True)
        if resolved != requested:
            row["reason"] = "path-alias"
            rows.append(row)
            continue
        if _excluded(resolved):
            row["reason"] = "excluded-system-root"
            rows.append(row)
            continue
        if not os.access(resolved, os.W_OK | os.X_OK):
            row["reason"] = "not-writable-searchable"
            rows.append(row)
            continue
        try:
            probe_fn(resolved, ".goai-stage-a-write-probe-")
            usage = disk_usage_fn(resolved)
        except OSError as exc:
            row["reason"] = f"probe-failed:{type(exc).__name__}"
            rows.append(row)
            continue
        free_bytes = int(usage.free)
        row["freeBytes"] = free_bytes
        row["freeGiB"] = round(free_bytes / (1024**3), 3)
        if free_bytes < floor_bytes:
            row["reason"] = "below-model-specific-free-space-floor"
            rows.append(row)
            continue
        row["eligible"] = True
        row["reason"] = "eligible"
        rows.append(row)
        eligible.append((free_bytes, resolved))
    if not eligible:
        observed = ", ".join(
            f"{row['path']}={row.get('freeGiB', '?')}GiB:{row['reason']}"
            for row in rows
        )
        raise RuntimeError(
            f"no plain writable executable filesystem has >= "
            f"{minimum_free_gib:.1f} GiB free; observed {observed or 'none'}"
        )
    return max(eligible, key=lambda item: item[0])[1], rows


def _ensure_plain_directory(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"managed path must remain relative: {relative}")
    root = Path(os.path.abspath(os.fspath(root)))
    if _first_symlink_component(root) is not None:
        raise RuntimeError(f"storage root contains a symlink: {root}")
    root = root.resolve(strict=True)
    root_device = os.lstat(root).st_dev
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"managed directory is a symlink: {current}")
        if not current.exists():
            current.mkdir(mode=0o700)
        info = os.lstat(current)
        if not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"managed path is not a directory: {current}")
        if info.st_dev != root_device or os.path.ismount(current):
            raise RuntimeError(f"managed path crosses a mount boundary: {current}")
        if current.resolve(strict=True) != current:
            raise RuntimeError(f"managed path has an alias component: {current}")
    return current


def _ensure_fallback(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    symlink = _first_symlink_component(absolute)
    if symlink is not None:
        raise RuntimeError(f"fallback path contains a symlink: {symlink}")
    absolute.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not absolute.is_dir() or absolute.resolve(strict=True) != absolute:
        raise RuntimeError(f"fallback path is not a plain directory: {absolute}")
    return absolute


def prepare_storage(
    *,
    mode: str,
    model: str,
    run_id: str,
    run_attempt: str,
    github_env: Path,
    github_output: Path,
    fallback_run_dir: Path,
    candidates: Sequence[Path] | None = None,
) -> dict:
    validate_dispatch(mode, model)
    if not re.fullmatch(r"[0-9]+", run_id):
        raise ValueError("run_id must contain only digits")
    if not re.fullmatch(r"[0-9]+", run_attempt):
        raise ValueError("run_attempt must contain only digits")
    fallback = _ensure_fallback(fallback_run_dir)
    minimum = storage_floor_gib(mode, model)
    cold_cache_minimum = float(REVIEWED_MODELS[model]["minimumFreeGiB"])
    development_minimum = float(
        REVIEWED_MODELS[model]["minimumDevelopmentFreeGiB"]
    )
    try:
        selected, candidate_rows = select_storage_root(
            storage_candidates() if candidates is None else candidates,
            minimum_free_gib=minimum,
        )
        runtime_root = _ensure_plain_directory(
            selected,
            Path("goai-stage-a-pro6000"),
        )
        run_dir = _ensure_plain_directory(
            selected,
            Path("goai-stage-a-pro6000")
            / "runs"
            / f"{run_id}-{run_attempt}",
        )
        hf_home = _ensure_plain_directory(
            selected,
            Path("goai-stage-a-pro6000") / "cache" / "huggingface",
        )
        hf_hub = _ensure_plain_directory(
            selected,
            Path("goai-stage-a-pro6000")
            / "cache"
            / "huggingface"
            / "hub",
        )
        pip_cache = _ensure_plain_directory(
            selected,
            Path("goai-stage-a-pro6000") / "cache" / "pip",
        )
        torch_home = _ensure_plain_directory(
            selected,
            Path("goai-stage-a-pro6000") / "cache" / "torch",
        )
        venv = runtime_root / "venv-transformers-cu128"
        if venv.exists():
            if venv.is_symlink() or venv.resolve(strict=True) != venv:
                raise RuntimeError(f"venv path is not plain: {venv}")
            if os.lstat(venv).st_dev != os.lstat(selected).st_dev:
                raise RuntimeError("venv crosses the selected storage device")
        payload = {
            "schema": "goai-stage-a-storage-selection/v1",
            "status": "selected",
            "mode": mode,
            "model": model,
            "selectedRoot": str(selected),
            "runDir": str(run_dir),
            "minimumFreeGiB": minimum,
            "coldCacheMinimumFreeGiB": cold_cache_minimum,
            "developmentMinimumFreeGiB": development_minimum,
            "preciseCacheFeasibilityCheckedByHostPreflight": True,
            "candidates": candidate_rows,
            "modelContacted": False,
            "cudaContacted": False,
            "gpuClaimed": False,
            "developmentOnly": True,
            "confirmatoryExecutionAllowed": False,
            **CLAIM_CEILING,
        }
        _write_json(run_dir / "storage-selection.json", payload)
        env_values = {
            "GOAI_STORAGE_ROOT": selected,
            "GOAI_RUNTIME_ROOT": runtime_root,
            "GOAI_RUN_DIR": run_dir,
            "GOAI_VENV": venv,
            "HF_HOME": hf_home,
            "HF_HUB_CACHE": hf_hub,
            "HUGGINGFACE_HUB_CACHE": hf_hub,
            "PIP_CACHE_DIR": pip_cache,
            "TORCH_HOME": torch_home,
        }
        with github_env.open("a", encoding="utf-8") as stream:
            for key, value in env_values.items():
                text = os.fspath(value)
                if "\n" in text or "\r" in text:
                    raise RuntimeError(f"unsafe newline in {key}")
                stream.write(f"{key}={text}\n")
        with github_output.open("a", encoding="utf-8") as stream:
            stream.write(f"storage_root={selected}\n")
            stream.write(f"run_dir={run_dir}\n")
        return payload
    except Exception as exc:
        _write_json(
            fallback / "storage-selection.json",
            {
                "schema": "goai-stage-a-storage-selection/v1",
                "status": "blocked",
                "mode": mode,
                "model": model,
                "minimumFreeGiB": minimum,
                "coldCacheMinimumFreeGiB": cold_cache_minimum,
                "developmentMinimumFreeGiB": development_minimum,
                "preciseCacheFeasibilityCheckedByHostPreflight": True,
                "error": f"{type(exc).__name__}: {exc}",
                "modelContacted": False,
                "cudaContacted": False,
                "gpuClaimed": False,
                "developmentOnly": True,
                "confirmatoryExecutionAllowed": False,
                **CLAIM_CEILING,
            },
        )
        raise


def _run_nvidia_smi() -> dict:
    proc = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"nvidia-smi failed rc={proc.returncode}: {proc.stderr.strip()[:200]}"
        )
    rows = [
        [part.strip() for part in line.split(",")]
        for line in proc.stdout.splitlines()
        if line.strip()
    ]
    if len(rows) != 1 or len(rows[0]) != 3:
        raise RuntimeError(f"expected exactly one GPU row, observed {rows!r}")
    name, memory_text, driver = rows[0]
    return {
        "name": name,
        "memoryMiB": int(memory_text),
        "driverVersion": driver,
    }


def _model_cache_snapshot(
    *,
    hf_hub: Path,
    model: str,
    revision: str,
    siblings: Sequence[Any],
) -> tuple[int, int]:
    repository_dir = hf_hub / ("models--" + model.replace("/", "--"))
    snapshot = repository_dir / "snapshots" / revision
    total = 0
    cached = 0
    for sibling in siblings:
        size = int(getattr(sibling, "size", 0) or 0)
        filename = str(getattr(sibling, "rfilename", "") or "")
        if not filename:
            continue
        total += size
        path = snapshot / filename
        try:
            if path.is_file() and path.stat().st_size == size:
                cached += size
        except OSError:
            # Concurrent cache mutation is treated as "not proven cached."
            continue
    return total, cached


def host_preflight(
    *,
    model: str,
    expected_runner_name: str,
    out: Path,
) -> dict:
    validate_dispatch("preflight", model)
    runner_name = os.environ.get("RUNNER_NAME", "")
    if runner_name != expected_runner_name:
        raise RuntimeError(
            f"runner identity mismatch: {runner_name!r} != {expected_runner_name!r}"
        )
    architecture = platform.machine()
    if architecture not in {"x86_64", "AMD64"}:
        raise RuntimeError(f"unexpected runner architecture: {architecture}")
    gpu = _run_nvidia_smi()
    expected_gpu = REVIEWED_MODELS[model]["expectedGpuSubstring"]
    if expected_gpu not in gpu["name"]:
        raise RuntimeError(
            f"unexpected GPU identity: {gpu['name']!r}; expected {expected_gpu!r}"
        )
    if gpu["memoryMiB"] < REVIEWED_MODELS[model]["minimumVramMiB"]:
        raise RuntimeError(
            f"insufficient VRAM: {gpu['memoryMiB']} MiB"
        )

    import huggingface_hub
    import torch
    import transformers

    if not torch.cuda.is_available():
        raise RuntimeError("installed torch cannot access CUDA")
    torch_name = torch.cuda.get_device_name(0)
    if expected_gpu not in torch_name:
        raise RuntimeError(
            f"torch CUDA device mismatch: {torch_name!r}"
        )
    info = huggingface_hub.HfApi().model_info(
        model,
        files_metadata=True,
    )
    revision = str(info.sha or "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError(f"model hub returned non-immutable revision {revision!r}")
    hf_hub = Path(
        os.environ.get(
            "HF_HUB_CACHE",
            Path(os.environ["HF_HOME"]) / "hub",
        )
    )
    total_bytes, cached_bytes = _model_cache_snapshot(
        hf_hub=hf_hub,
        model=model,
        revision=revision,
        siblings=info.siblings or (),
    )
    missing_bytes = max(0, total_bytes - cached_bytes)
    free_bytes = shutil.disk_usage(hf_hub).free
    required_free_bytes = required_model_cache_free_bytes(missing_bytes)
    if free_bytes < required_free_bytes:
        raise RuntimeError(
            f"model cache infeasible: free={free_bytes} required={required_free_bytes}"
        )
    payload = {
        "schema": "goai-stage-a-pro6000-host-preflight/v1",
        "status": "passed",
        "runnerName": runner_name,
        "architecture": architecture,
        "gpu": gpu,
        "torch": {
            "version": torch.__version__,
            "cudaVersion": torch.version.cuda,
            "cudaAvailable": True,
            "deviceName": torch_name,
        },
        "transformersVersion": transformers.__version__,
        "huggingfaceHubVersion": huggingface_hub.__version__,
        "model": {
            "id": model,
            "resolvedRevision": revision,
            "repositoryBytes": total_bytes,
            "cachedBytes": cached_bytes,
            "missingBytes": missing_bytes,
            "requiredFreeBytes": required_free_bytes,
            "observedFreeBytes": free_bytes,
            "cacheFeasible": True,
        },
        "gpuClaimRequiredBeforeThisReceipt": True,
        "modelWeightsLoaded": False,
        "developmentOnly": True,
        "confirmatoryExecutionAllowed": False,
        **CLAIM_CEILING,
    }
    _write_json(out, payload)
    github_env = os.environ.get("GITHUB_ENV")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_env:
        with Path(github_env).open("a", encoding="utf-8") as stream:
            stream.write(f"MODEL_REVISION={revision}\n")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"model_revision={revision}\n")
    return payload


def validate_artifact_boundary(
    *,
    run_dir: Path,
    expected_run_dir: str,
    expected_root: str,
    fallback_run_dir: Path,
) -> dict:
    actual = Path(os.path.abspath(os.fspath(run_dir)))
    fallback = Path(os.path.abspath(os.fspath(fallback_run_dir)))
    if expected_run_dir:
        expected = Path(os.path.abspath(expected_run_dir))
        root = Path(os.path.abspath(expected_root))
        if actual != expected:
            raise RuntimeError(
                f"run directory differs from storage output: {actual} != {expected}"
            )
        if root not in actual.parents:
            raise RuntimeError("run directory escapes selected storage root")
        source = "selected-storage"
    else:
        if expected_root:
            raise RuntimeError("unexpected storage root without selected run directory")
        if actual != fallback:
            raise RuntimeError(
                f"run directory differs from fixed fallback: {actual} != {fallback}"
            )
        source = "pre-selection-fallback"
    symlink = _first_symlink_component(actual)
    if symlink is not None:
        raise RuntimeError(f"artifact path contains a symlink: {symlink}")
    if not actual.is_dir() or actual.resolve(strict=True) != actual:
        raise RuntimeError(f"artifact path is not a plain directory: {actual}")
    payload = {
        "schema": "goai-stage-a-artifact-boundary/v1",
        "status": "accepted",
        "source": source,
        "runDir": str(actual),
        "developmentOnly": True,
        **CLAIM_CEILING,
    }
    _write_json(actual / "artifact-boundary.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--mode", required=True)
    validate_parser.add_argument("--model", required=True)

    storage_parser = subparsers.add_parser("storage")
    storage_parser.add_argument("--mode", required=True)
    storage_parser.add_argument("--model", required=True)
    storage_parser.add_argument("--run-id", required=True)
    storage_parser.add_argument("--run-attempt", required=True)
    storage_parser.add_argument("--github-env", type=Path, required=True)
    storage_parser.add_argument("--github-output", type=Path, required=True)
    storage_parser.add_argument("--fallback-run-dir", type=Path, required=True)

    host_parser = subparsers.add_parser("host")
    host_parser.add_argument("--model", required=True)
    host_parser.add_argument(
        "--expected-runner-name",
        default="pro6000-blackwell",
    )
    host_parser.add_argument("--out", type=Path, required=True)

    boundary_parser = subparsers.add_parser("artifact-boundary")
    boundary_parser.add_argument("--run-dir", type=Path, required=True)
    boundary_parser.add_argument("--expected-run-dir", default="")
    boundary_parser.add_argument("--expected-root", default="")
    boundary_parser.add_argument("--fallback-run-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "validate":
        payload = validate_dispatch(args.mode, args.model)
    elif args.command == "storage":
        payload = prepare_storage(
            mode=args.mode,
            model=args.model,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            github_env=args.github_env,
            github_output=args.github_output,
            fallback_run_dir=args.fallback_run_dir,
        )
    elif args.command == "host":
        try:
            payload = host_preflight(
                model=args.model,
                expected_runner_name=args.expected_runner_name,
                out=args.out,
            )
        except Exception as exc:
            _write_json(
                args.out,
                {
                    "schema": "goai-stage-a-pro6000-host-preflight/v1",
                    "status": "blocked",
                    "model": args.model,
                    "expectedRunnerName": args.expected_runner_name,
                    "errorType": type(exc).__name__,
                    "error": str(exc)[:1000],
                    "gpuClaimRequiredBeforeThisReceipt": True,
                    "modelWeightsLoaded": False,
                    "developmentOnly": True,
                    "confirmatoryExecutionAllowed": False,
                    **CLAIM_CEILING,
                },
            )
            raise
    else:
        payload = validate_artifact_boundary(
            run_dir=args.run_dir,
            expected_run_dir=args.expected_run_dir,
            expected_root=args.expected_root,
            fallback_run_dir=args.fallback_run_dir,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
