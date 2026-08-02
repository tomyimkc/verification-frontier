#!/usr/bin/env python3
"""Concurrency-safe Lean source verification for GOAI receipts."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

_PLACEHOLDER = re.compile(r"\b(sorry|admit)\b", re.IGNORECASE)


def verify_source(
    source: str,
    project: Path,
    timeout_s: int,
) -> tuple[str, str]:
    """Elaborate a complete Lean source using a unique scratch file.

    The repository-wide ladder helper uses one fixed ``LadderProbe.lean`` path,
    which is unsafe when independent validations share a pinned Mathlib project.
    This GOAI wrapper creates a unique file for every call and always removes it.
    """
    if _PLACEHOLDER.search(source):
        return "rejected", "proof still contains sorry/admit"
    scratch: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=project,
            prefix=".goai-lean-probe-",
            suffix=".lean",
            delete=False,
        ) as handle:
            handle.write(source)
            scratch = Path(handle.name)
        proc = subprocess.run(
            ["lake", "env", "lean", scratch.name],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return "abstain", f"lean_unavailable: {type(exc).__name__}"
    finally:
        if scratch is not None:
            try:
                scratch.unlink()
            except OSError:
                # Best-effort cleanup must not mask the verifier result.
                pass
    output = (proc.stderr or "") + (proc.stdout or "")
    if (
        proc.returncode == 0
        and "error:" not in output.casefold()
        and not _PLACEHOLDER.search(output)
    ):
        return "accepted", "elaborated clean under pinned Mathlib"
    return "rejected", f"lean: {output.strip()[:200]}"
