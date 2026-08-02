#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Frozen set of genuinely ill-posed problems for the verification frontier.

Every item in this pack is **unsolvable as stated** — a mathematician would
agree there is no determinate answer. The only honest verdict for each is
``abstain``. This is the inverse of ``build_logic_error_audit``: there the
candidate is wrong and ``rejected``; here the *problem itself* is ill-posed.

Categories and counts (frozen):
  - contradictory_equation_system : 10  (no solution; SymPy linsolve → EmptySet)
  - missing_constraint            :  8  (underdetermined; free symbols > equations)
  - undecidable                   :  5  (self-referential / paradoxical)
  - circular_dependency           :  4  (A→B→A cycle)
  - empty_feasible_region         :  3  (contradictory bounds / unbounded objective)

Claim ceiling: candidateOnly:true, canClaimAGI:false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ARTIFACT_PATH = HERE / "artifacts" / "ill-posed-tasks.json"

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

EXPECTED_CATEGORY_COUNTS: dict[str, int] = {
    "contradictory_equation_system": 10,
    "missing_constraint": 8,
    "undecidable": 5,
    "circular_dependency": 4,
    "empty_feasible_region": 3,
}

REASON_CODES: set[str] = {
    "contradictory_system",
    "missing_constraint",
    "undecidable",
    "circular_dependency",
    "empty_feasible_region",
}

CATEGORY_TO_REASON_CODE: dict[str, str] = {
    "contradictory_equation_system": "contradictory_system",
    "missing_constraint": "missing_constraint",
    "undecidable": "undecidable",
    "circular_dependency": "circular_dependency",
    "empty_feasible_region": "empty_feasible_region",
}


@dataclass(frozen=True)
class IllPosedTask:
    task_id: str
    category: str
    problem_statement: str
    why_ill_posed: str
    expected_verdict: str = "abstain"
    expected_reason_code: str = ""
    candidateOnly: bool = True
    canClaimAGI: bool = False


# ── SymPy proofs for contradictory systems (independent verification) ────────
SYMPY_PROOFS: dict[str, dict[str, Any]] = {
    "cs-01": {"symbols": ["x", "y"], "eqs": ["x + y - 3", "x + y - 5"]},
    "cs-02": {"symbols": ["x"], "eqs": ["2*x - 6", "2*x - 8"]},
    "cs-03": {"symbols": ["x", "y"], "eqs": ["x - y - 1", "x - y + 1"]},
    "cs-04": {"symbols": ["x", "y", "z"], "eqs": ["x + y + z - 6", "x + y + z - 9"]},
    "cs-05": {"symbols": ["x"], "eqs": ["x - 5", "x + 3"]},
    "cs-06": {"symbols": ["x", "y"], "eqs": ["3*x + 2*y - 12", "3*x + 2*y - 18"]},
    "cs-07": {"symbols": ["a", "b"], "eqs": ["a + 2*b - 10", "a + 2*b - 4"]},
    "cs-08": {"symbols": ["x", "y", "z"], "eqs": ["x + y - 5", "x + y - 5", "x + y - 7"]},
    "cs-09": {"symbols": ["p", "q"], "eqs": ["p - q - 2", "p - q + 2"]},
    "cs-10": {"symbols": ["x"], "eqs": ["5*x - 25", "5*x - 30"]},
}


def _sympy_is_inconsistent(eqs: list, syms: list) -> bool:
    """Return True iff the linear system has no solution (EmptySet)."""
    import sympy as sp

    try:
        result = sp.linsolve(eqs, *syms)
        return result == sp.EmptySet
    except Exception:
        return False


def verify_contradictory_system(task_id: str) -> bool:
    """Independent SymPy verification that a CS item is genuinely inconsistent."""
    proof = SYMPY_PROOFS.get(task_id)
    if not proof:
        return False
    import sympy as sp

    syms = [sp.Symbol(s) for s in proof["symbols"]]
    eqs = [sp.sympify(e) for e in proof["eqs"]]
    return _sympy_is_inconsistent(eqs, syms)


# ── Circular-dependency detection ────────────────────────────────────────────
_DEPENDS_RE = re.compile(
    r"(\w+)\s*(?:depends\s+on|requires?|needs?)\s*(\w+)", re.IGNORECASE
)


def has_circular_reference(text: str) -> bool:
    """Detect whether a dependency description contains a cycle (DFS 3-colour)."""
    edges: dict[str, list[str]] = {}
    for m in _DEPENDS_RE.finditer(text):
        a, b = m.group(1).lower(), m.group(2).lower()
        edges.setdefault(a, []).append(b)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for nbr in edges.get(node, []):
            c = color.get(nbr, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(nbr):
                return True
        color[node] = BLACK
        return False

    return any(dfs(n) for n in edges if color.get(n, WHITE) == WHITE)


# ── Task definitions ─────────────────────────────────────────────────────────


def _t(
    task_id: str,
    category: str,
    problem_statement: str,
    why_ill_posed: str,
) -> IllPosedTask:
    return IllPosedTask(
        task_id=task_id,
        category=category,
        problem_statement=problem_statement,
        why_ill_posed=why_ill_posed,
        expected_verdict="abstain",
        expected_reason_code=CATEGORY_TO_REASON_CODE[category],
    )


def ill_posed_tasks() -> list[IllPosedTask]:
    """Return the frozen set of 30 genuinely ill-posed problems."""
    tasks: list[IllPosedTask] = []

    # ── 10 contradictory equation systems ──
    cs_items = [
        ("cs-01", "Solve the system: x + y = 3, x + y = 5.", "The two equations contradict: x+y cannot be both 3 and 5 simultaneously."),
        ("cs-02", "Solve for x: 2x = 6 and 2x = 8.", "2x cannot equal both 6 and 8; the system is inconsistent."),
        ("cs-03", "Solve: x - y = 1, x - y = -1.", "x-y cannot be both 1 and -1; no solution exists."),
        ("cs-04", "Solve the system: x + y + z = 6, x + y + z = 9.", "The sum cannot be both 6 and 9; the equations are contradictory."),
        ("cs-05", "Find x such that x = 5 and x = -3.", "x cannot be both 5 and -3; the constraints are contradictory."),
        ("cs-06", "Solve: 3x + 2y = 12, 3x + 2y = 18.", "3x+2y cannot be both 12 and 18; no solution."),
        ("cs-07", "Solve: a + 2b = 10, a + 2b = 4.", "a+2b cannot be both 10 and 4; the system has no solution."),
        ("cs-08", "Solve: x + y = 5, x + y = 5, x + y = 7.", "The third equation contradicts the first two; no solution."),
        ("cs-09", "Solve: p - q = 2, p - q = -2.", "p-q cannot be both 2 and -2; the system is inconsistent."),
        ("cs-10", "Find x: 5x = 25, 5x = 30.", "5x cannot be both 25 and 30; the system is contradictory."),
    ]
    for tid, stmt, why in cs_items:
        tasks.append(_t(tid, "contradictory_equation_system", stmt, why))

    # ── 8 missing-constraint problems ──
    mc_items = [
        ("mc-01", "Solve for x: x + y = 5.", "Two unknowns (x, y) but only one equation; the system is underdetermined with infinitely many solutions."),
        ("mc-02", "Find the area of a triangle.", "No dimensions (base, height, or sides) are given; the area cannot be determined."),
        ("mc-03", "Solve for x: x + y + z = 10.", "Three unknowns but only one equation; infinitely many solutions exist."),
        ("mc-04", "What is the speed of the car?", "No distance, time, or reference frame is specified; speed cannot be determined."),
        ("mc-05", "Solve: 2x + 3y = 12.", "Two unknowns, one equation; underdetermined."),
        ("mc-06", "Find the value of x.", "No equation, constraint, or relationship involving x is provided."),
        ("mc-07", "Solve for x and y: 3x - y = 7.", "Two unknowns, one equation; infinitely many solutions."),
        ("mc-08", "Calculate the final temperature.", "No initial temperature, heat input, mass, or specific heat is given."),
    ]
    for tid, stmt, why in mc_items:
        tasks.append(_t(tid, "missing_constraint", stmt, why))

    # ── 5 undecidable / self-referential propositions ──
    un_items = [
        ("un-01", "This statement is false.", "The Liar paradox: if true then false, if false then true; it is undecidable within classical logic."),
        ("un-02", "Does the set of all sets that do not contain themselves contain itself?", "Russell's paradox: either answer leads to a contradiction; the set cannot consistently exist."),
        ("un-03", "The following sentence is true. The previous sentence is false.", "A two-step Liar cycle; both sentences cannot have consistent truth values."),
        ("un-04", "A barber shaves all those, and only those, who do not shave themselves. Does the barber shave himself?", "The Barber paradox: either answer leads to a contradiction; the barber cannot consistently exist."),
        ("un-05", "Is this question unanswerable?", "Self-referential: answering 'yes' proves it is answerable (contradiction); 'no' also leads to paradox."),
    ]
    for tid, stmt, why in un_items:
        tasks.append(_t(tid, "undecidable", stmt, why))

    # ── 4 circular-dependency problems ──
    cd_items = [
        ("cd-01", "A depends on B. B depends on A. Find the value of A.", "Circular dependency: A requires B which requires A; neither can be resolved without breaking the cycle."),
        ("cd-02", "X depends on Y. Y depends on X. What is the value of X?", "Circular dependency: each variable depends on the other; the system cannot be resolved."),
        ("cd-03", "A depends on B to complete first. B depends on A to complete first. When will A finish?", "Circular dependency in scheduling; each task requires the other to finish first."),
        ("cd-04", "A depends on B, B depends on C, C depends on A. Find A.", "Three-node circular dependency; the cycle A→B→C→A prevents resolution."),
    ]
    for tid, stmt, why in cd_items:
        tasks.append(_t(tid, "circular_dependency", stmt, why))

    # ── 3 empty-feasible-region problems ──
    ef_items = [
        ("ef-01", "Maximize x subject to: x < 0 and x > 0.", "The constraints are contradictory (x cannot be both negative and positive); the feasible region is empty."),
        ("ef-02", "Minimize x subject to: x >= 10 and x <= 5.", "No x can satisfy both x>=10 and x<=5; the feasible region is empty."),
        ("ef-03", "Maximize x over all real numbers with no upper bound.", "The objective is unbounded above; no finite maximum exists, so the optimization is ill-posed."),
    ]
    for tid, stmt, why in ef_items:
        tasks.append(_t(tid, "empty_feasible_region", stmt, why))

    return tasks


def validate_tasks(tasks: list[IllPosedTask]) -> list[str]:
    errors: list[str] = []
    if len(tasks) < 30:
        errors.append(f"expected at least 30 tasks, got {len(tasks)}")
    ids = [t.task_id for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate task_id")
    for t in tasks:
        if t.expected_verdict != "abstain":
            errors.append(f"{t.task_id}: expected_verdict must be 'abstain'")
        if t.expected_reason_code not in REASON_CODES:
            errors.append(f"{t.task_id}: invalid reason_code {t.expected_reason_code!r}")
        if not t.problem_statement.strip():
            errors.append(f"{t.task_id}: empty problem_statement")
        if not t.why_ill_posed.strip():
            errors.append(f"{t.task_id}: empty why_ill_posed")
    counts: dict[str, int] = {k: 0 for k in EXPECTED_CATEGORY_COUNTS}
    for t in tasks:
        counts[t.category] = counts.get(t.category, 0) + 1
    if counts != EXPECTED_CATEGORY_COUNTS:
        for cat, expected in EXPECTED_CATEGORY_COUNTS.items():
            actual = counts.get(cat, 0)
            if actual != expected:
                errors.append(f"category {cat}: expected {expected}, got {actual}")
    # reason_code must map 1:1 across categories
    code_to_cat: dict[str, set[str]] = {}
    for t in tasks:
        code_to_cat.setdefault(t.expected_reason_code, set()).add(t.category)
    for code, cats in code_to_cat.items():
        if len(cats) > 1:
            errors.append(f"reason_code {code!r} used by multiple categories: {cats}")
    # Verify CS items are genuinely inconsistent via SymPy proofs
    for t in tasks:
        if t.category == "contradictory_equation_system":
            if t.task_id not in SYMPY_PROOFS:
                errors.append(f"{t.task_id}: missing SYMPY_PROOFS annotation")
            elif not verify_contradictory_system(t.task_id):
                errors.append(f"{t.task_id}: SYMPY_PROOFS annotation is not actually inconsistent")
    return errors


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def build_pack() -> dict[str, Any]:
    tasks = ill_posed_tasks()
    errors = validate_tasks(tasks)
    if errors:
        raise ValueError("invalid ill-posed task pack: " + "; ".join(errors))
    # Attach SymPy proofs to CS items in the serialized output
    task_dicts = []
    for t in tasks:
        d = asdict(t)
        if t.task_id in SYMPY_PROOFS:
            d["sympy_proof"] = SYMPY_PROOFS[t.task_id]
        task_dicts.append(d)
    # Count items by category
    item_counts: dict[str, int] = {}
    for t in tasks:
        item_counts[t.category] = item_counts.get(t.category, 0) + 1
    item_counts["total"] = len(tasks)
    by_category = {k: item_counts.get(k, 0) for k in EXPECTED_CATEGORY_COUNTS}
    return {
        "schema": "goai-ill-posed-tasks/v1",
        "evidenceClass": "development-only",
        "taskCount": len(tasks),
        "itemCounts": {"total": len(tasks), "byCategory": by_category},
        "expectedCategoryCounts": EXPECTED_CATEGORY_COUNTS,
        "reasonCodes": sorted(REASON_CODES),
        "categoryToReasonCode": CATEGORY_TO_REASON_CODE,
        "tasks": task_dicts,
        "interpretation": (
            "Every item is genuinely ill-posed. The only honest verdict is abstain. "
            "LLMs hallucinate solutions; the deterministic verifier correctly abstains. "
            "This is instrument evidence, NOT a model-capability claim."
        ),
        "scientificOutcome": False,
        "capabilityClaim": False,
        "isModelBenchmark": False,
        **CLAIM_CEILING,
    }


def write_pack(output: Path = ARTIFACT_PATH) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    pack = build_pack()
    output.write_bytes(_canonical_bytes(pack))
    return pack


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Command-line interface for the ill-posed task pack.

    Modes:
      * (default)  build the pack and write its canonical bytes to --output;
      * ``--check``         re-derive canonical bytes and byte-compare the on-disk
                             artifact (fail-closed: no silent relaxation);
      * ``--validate-only`` run validate_tasks and report, write/check nothing.

    Mirrors the ``--check`` / build / canonical-bytes contract used by
    ``build_logic_error_audit`` and ``build_baseline_comparison`` so the pack
    participates in the same fail-closed audit discipline.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ARTIFACT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive canonical bytes and byte-compare against the on-disk artifact",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="run validate_tasks and print the result; write/check nothing",
    )
    args = parser.parse_args(argv)

    if args.validate_only:
        errors = validate_tasks(ill_posed_tasks())
        if errors:
            print("ILL-POSED TASKS: VALIDATION FAIL")
            for e in errors:
                print(f"  - {e}")
            return 1
        print("ILL-POSED TASKS: VALIDATION PASS (0 errors)")
        return 0

    if args.check:
        if not args.output.is_file():
            print("ILL-POSED TASKS: FAIL (artifact missing)")
            return 1
        on_disk_bytes = args.output.read_bytes()
        try:
            expected_bytes = _canonical_bytes(build_pack())
        except ValueError as exc:
            print(f"ILL-POSED TASKS: FAIL (build raised: {exc})")
            return 1
        if on_disk_bytes != expected_bytes:
            print("ILL-POSED TASKS: FAIL (bytes not canonical/current)")
            print(
                f"  on-disk sha256={_sha256(on_disk_bytes)} "
                f"expected sha256={_sha256(expected_bytes)}"
            )
            return 1
        on_disk = json.loads(on_disk_bytes.decode("utf-8"))
        bad = [
            t["task_id"] for t in on_disk["tasks"] if t["expected_verdict"] != "abstain"
        ]
        if bad:
            print(f"ILL-POSED TASKS: FAIL ({len(bad)} items not abstain: {bad})")
            return 1
        counts = on_disk["itemCounts"]
        print(
            "ILL-POSED TASKS: PASS "
            f"(total={counts['total']}; "
            f"byCategory={counts['byCategory']}; "
            f"all verdicts=abstain)"
        )
        return 0

    pack = write_pack(args.output)
    print(
        json.dumps(
            {
                "schema": pack["schema"],
                "evidenceClass": pack["evidenceClass"],
                "itemCounts": pack["itemCounts"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
