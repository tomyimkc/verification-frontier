#!/usr/bin/env python3
"""Fail-closed validation for generated GOAI benchmark artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(output_dir: Path) -> list[str]:
    errors: list[str] = []
    summary_path = output_dir / "benchmark-summary.json"
    episodes_path = output_dir / "episodes.jsonl"
    if not summary_path.is_file():
        return [f"missing {summary_path}"]
    if not episodes_path.is_file():
        return [f"missing {episodes_path}"]

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid {summary_path}: {type(exc).__name__}: {exc}"]
    if not isinstance(summary, dict):
        return [f"invalid {summary_path}: expected a JSON object"]
    if summary.get("candidateOnly") is not True:
        errors.append("candidateOnly must be true")
    if summary.get("canClaimAGI") is not False:
        errors.append("canClaimAGI must be false")
    if summary.get("environment", {}).get("lean") != "external_receipt_only_not_bundled":
        errors.append("Lean status must remain external_receipt_only_not_bundled")

    row_count = 0
    terminal_by_episode: dict[str, int] = {}
    for line_number, line in enumerate(
        episodes_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        row_count += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {line_number}: expected a JSON object")
            continue
        if row.get("candidateOnly") is not True or row.get("canClaimAGI") is not False:
            errors.append(f"line {line_number}: claim ceiling missing")
        if row.get("rung") == "open-unformalized" and row.get("verdict") == "accepted":
            errors.append(f"line {line_number}: open-unformalized item was accepted")
        if row.get("terminal"):
            episode_id = row.get("episode_id")
            if not isinstance(episode_id, str) or not episode_id.strip():
                errors.append(f"line {line_number}: terminal row missing episode_id")
                continue
            terminal_by_episode[episode_id] = terminal_by_episode.get(episode_id, 0) + 1

    if row_count == 0:
        errors.append("episodes.jsonl is empty")
    expected_episodes = len(summary.get("environment", {}).get("policies", [])) * int(
        summary.get("environment", {}).get("problems", 0)
    )
    if len(terminal_by_episode) != expected_episodes:
        errors.append(
            f"terminal episode count {len(terminal_by_episode)} != expected {expected_episodes}"
        )
    duplicated = [episode for episode, count in terminal_by_episode.items() if count != 1]
    if duplicated:
        errors.append(f"episodes with non-single terminal rows: {duplicated}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    errors = validate(args.output_dir)
    if errors:
        print("ARTIFACT VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("ARTIFACT VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
