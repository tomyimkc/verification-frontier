#!/usr/bin/env python3
"""CLI and compatibility exports for strict confirmatory scoring."""
from __future__ import annotations

from v2.confirmatory_scoring import (
    main,
    score,
    task_manifest_bytes,
    task_manifest_sha256,
)

__all__ = ("main", "score", "task_manifest_bytes", "task_manifest_sha256")


if __name__ == "__main__":
    raise SystemExit(main())
