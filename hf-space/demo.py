#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""GOAI AI for Research submission: fail-closed verification environment.

This compact environment exposes verifier *coverage* as an explicit research
state.  At each step a deterministic verifier returns one of:

* ``accepted``: the supplied check establishes the candidate under its contract.
* ``rejected``: the supplied check establishes that the candidate is wrong.
* ``abstain``: the environment lacks an applicable check or executable
  specification.  This is fail-closed and is never treated as acceptance.

The executable package contains SI dimensional/value checks and an optional
SymPy symbolic-equivalence tier.  Lean-backed results are supplied as a pinned
external evidence receipt; the compact package does not claim to bundle Lean.

The environment includes four deterministic reference policies and emits
JSONL episode traces.  It is an environment/instrument demonstration, not a
model-capability result.  ``candidateOnly:true`` and ``canClaimAGI:false``.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shlex
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from units import format_dim, parse_quantity, same_dim

Verdict = Literal["accepted", "rejected", "abstain"]
Action = Literal[
    "keep_and_stop",
    "revise",
    "stop_rejected",
    "mark_unsupported_and_stop",
]
RTOL = 1e-2
MAX_SYMBOLIC_INPUT_CHARS = 256
MAX_SYMBOLIC_AST_NODES = 96
MAX_SYMBOLIC_AST_DEPTH = 24
MAX_SYMBOLIC_INTEGER_BITS = 128
MAX_SYMBOLIC_EXPONENT = 16
SYMBOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,15}$")


@dataclass(frozen=True)
class Problem:
    problem_id: str
    rung: str
    tier: str
    prompt: str
    gold: str | None
    specification_status: str = "executable"


@dataclass(frozen=True)
class Result:
    verdict: Verdict
    reason_code: str
    reason: str
    tier: str

    def __str__(self) -> str:
        return (
            f"{self.verdict.upper():8} [{self.tier}] "
            f"{self.reason_code}: {self.reason}"
        )


@dataclass(frozen=True)
class StepRecord:
    schema: str
    episode_id: str
    policy: str
    problem_id: str
    rung: str
    step: int
    observation: str
    proposal: str
    verifier_tier: str
    verdict: Verdict
    reason_code: str
    reason: str
    next_action: Action
    terminal: bool
    candidateOnly: bool = True
    canClaimAGI: bool = False


PROBLEMS = [
    Problem(
        problem_id="free-fall",
        rung="closed",
        tier="physics",
        prompt="Free-fall for 1 s from rest at g=9.8 m/s^2. What is the speed?",
        gold="9.8 m/s",
    ),
    Problem(
        problem_id="kinetic-energy",
        rung="closed",
        tier="physics",
        prompt="A 2 kg object moves at 3 m/s. What is its kinetic energy?",
        gold="9 J",
    ),
    Problem(
        problem_id="expand-square",
        rung="closed",
        tier="math",
        prompt="Expand (x+1)^2.",
        gold="x^2+2*x+1",
    ),
    Problem(
        problem_id="hf01-quad",
        rung="held-out",
        tier="math",
        prompt="Simplify (n+2)*(n+1).",
        gold="n*n+3*n+2",
    ),
    Problem(
        problem_id="hf02-linear",
        rung="held-out",
        tier="math",
        prompt="Show that 3*n+7 equals 7+n+n+n.",
        gold="7+n+n+n",
    ),
    Problem(
        problem_id="riemann-zeros",
        rung="open-unformalized",
        tier="formal-proof",
        prompt="Prove that all non-trivial zeta zeros lie on Re(s)=1/2.",
        gold=None,
        specification_status="unsupported",
    ),
]
PROBLEM_BY_ID = {problem.problem_id: problem for problem in PROBLEMS}


POLICY_PLANS: dict[str, dict[str, list[str]]] = {
    "always-answer": {
        "free-fall": ["9.8 m/s^2"],
        "kinetic-energy": ["9 J"],
        "expand-square": ["x^2+2*x+1"],
        "hf01-quad": ["n*n+3*n+2"],
        "hf02-linear": ["7+n+n+n"],
        "riemann-zeros": ["have h : True := trivial"],
    },
    "abstain-all": {problem.problem_id: [""] for problem in PROBLEMS},
    "single-shot": {
        "free-fall": ["9.8 m/s^2"],
        "kinetic-energy": ["9 J"],
        "expand-square": ["x^2+2*x+2"],
        "hf01-quad": ["n*n+3*n+3"],
        "hf02-linear": ["7+n+n"],
        "riemann-zeros": ["sorry"],
    },
    "scripted-refine": {
        "free-fall": ["9.8 m/s^2", "9.8 m/s"],
        "kinetic-energy": ["8 J", "9 J"],
        "expand-square": ["x^2+2*x+2", "x^2+2*x+1"],
        "hf01-quad": ["n*n+3*n+3", "n*n+3*n+2"],
        "hf02-linear": ["7+n+n", "7+n+n+n"],
        "riemann-zeros": ["sorry", "have h : True := trivial"],
    },
}


def _sympy_available() -> bool:
    try:
        import sympy  # noqa: F401

        return True
    except ImportError:
        return False


def verify_physics(candidate: str, gold: str, *, rtol: float = RTOL) -> Result:
    """Verify SI dimension and numeric value under a documented tolerance."""
    ok_candidate, value_candidate, dim_candidate = parse_quantity(candidate)
    ok_gold, value_gold, dim_gold = parse_quantity(gold)

    if not ok_candidate:
        return Result(
            "abstain",
            "candidate_unparseable",
            f"candidate cannot be parsed as an SI quantity: {candidate!r}",
            "si",
        )
    if not ok_gold:
        return Result(
            "abstain",
            "reference_unparseable",
            f"reference cannot be parsed as an SI quantity: {gold!r}",
            "si",
        )
    if not same_dim(dim_candidate, dim_gold):
        return Result(
            "rejected",
            "dimension_mismatch",
            (
                f"candidate {format_dim(dim_candidate)} versus "
                f"reference {format_dim(dim_gold)}"
            ),
            "si",
        )

    if value_gold == 0:
        close = abs(value_candidate) <= rtol
    else:
        close = abs(value_candidate - value_gold) <= rtol * abs(value_gold)
    if close:
        return Result(
            "accepted",
            "dimension_and_value_match",
            f"value {value_candidate} is within {rtol:.0%} of {value_gold}",
            "si",
        )
    return Result(
        "rejected",
        "value_mismatch",
        f"value {value_candidate} is outside {rtol:.0%} of {value_gold}",
        "si",
    )


def _safe_sympy_expression(source: str, sp):
    """Build a SymPy expression from a small non-evaluating AST grammar."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("symbolic expression is empty")
    normalized_source = source.replace("^", "**")
    if len(normalized_source) > MAX_SYMBOLIC_INPUT_CHARS:
        raise ValueError("symbolic expression exceeds the length limit")
    tree = ast.parse(normalized_source, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_SYMBOLIC_AST_NODES:
        raise ValueError("symbolic expression exceeds the AST node limit")

    symbols: dict[str, object] = {}

    def build(node, depth: int = 0):
        if depth > MAX_SYMBOLIC_AST_DEPTH:
            raise ValueError("symbolic expression exceeds the depth limit")
        if isinstance(node, ast.Expression):
            return build(node.body, depth + 1)
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("only numeric constants are allowed")
            if isinstance(value, int):
                if value.bit_length() > MAX_SYMBOLIC_INTEGER_BITS:
                    raise ValueError("integer literal is too large")
                return sp.Integer(value)
            if not math.isfinite(value):
                raise ValueError("non-finite constants are forbidden")
            return sp.Float(repr(value))
        if isinstance(node, ast.Name):
            if not SYMBOL_NAME.fullmatch(node.id):
                raise ValueError("symbol name is not allowed")
            symbols.setdefault(node.id, sp.Symbol(node.id))
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = build(node.operand, depth + 1)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = build(node.left, depth + 1)
            right = build(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                if not isinstance(node.right, ast.Constant) or isinstance(
                    node.right.value,
                    bool,
                ):
                    raise ValueError("exponent must be an integer literal")
                exponent = node.right.value
                if not isinstance(exponent, int) or abs(exponent) > MAX_SYMBOLIC_EXPONENT:
                    raise ValueError("exponent is outside the permitted range")
                if any(
                    isinstance(descendant, ast.Pow)
                    for descendant in ast.walk(node.left)
                ):
                    raise ValueError("nested powers are forbidden")
                return left ** exponent
        raise ValueError(f"forbidden symbolic syntax: {type(node).__name__}")

    expression = build(tree)
    if int(sp.count_ops(expression, visual=False)) > MAX_SYMBOLIC_AST_NODES:
        raise ValueError("computed expression exceeds the operation limit")
    if expression.is_Integer and abs(int(expression)).bit_length() > 4096:
        raise ValueError("computed integer exceeds the bit-size limit")
    if expression.is_Rational and (
        abs(int(expression.p)).bit_length() > 4096
        or abs(int(expression.q)).bit_length() > 4096
    ):
        raise ValueError("computed rational exceeds the bit-size limit")
    return expression


def verify_math(candidate: str, gold: str) -> Result:
    """Verify symbolic equivalence using a restricted, non-evaluating grammar."""
    if not _sympy_available():
        return Result(
            "abstain",
            "sympy_unavailable",
            "the optional symbolic-equivalence tier is not installed",
            "sympy",
        )
    try:
        import sympy as sp
        expression_candidate = _safe_sympy_expression(candidate, sp)
        expression_gold = _safe_sympy_expression(gold, sp)
        if sp.simplify(expression_candidate - expression_gold) == 0:
            return Result(
                "accepted",
                "symbolically_equivalent",
                f"candidate is equivalent to {gold!r}",
                "sympy",
            )
        return Result(
            "rejected",
            "not_symbolically_equivalent",
            f"candidate {expression_candidate!r} is not equivalent to {expression_gold!r}",
            "sympy",
        )
    except Exception as exc:
        return Result(
            "abstain",
            "expression_unparseable",
            f"symbolic parser could not evaluate the candidate: {type(exc).__name__}",
            "sympy",
        )


def verify_problem(problem: Problem, proposal: str) -> Result:
    """Route a proposal to an applicable verifier or expose missing coverage."""
    lowered = proposal.lower()
    if "sorry" in lowered or "admit" in lowered:
        return Result(
            "rejected",
            "proof_placeholder",
            "'sorry' and 'admit' are not proof certificates",
            "contract",
        )
    if problem.specification_status != "executable":
        return Result(
            "abstain",
            "unsupported_specification",
            (
                "no executable proposition and accepted verification procedure "
                "were supplied for this item"
            ),
            "coverage",
        )
    if problem.tier == "physics":
        assert problem.gold is not None
        return verify_physics(proposal, problem.gold)
    if problem.tier == "math":
        assert problem.gold is not None
        return verify_math(proposal, problem.gold)
    return Result(
        "abstain",
        "unsupported_tier",
        f"no verifier is registered for tier {problem.tier!r}",
        "coverage",
    )


def run_episode(problem: Problem, policy: str) -> list[StepRecord]:
    """Run one deterministic propose -> verify -> act episode."""
    if policy not in POLICY_PLANS:
        raise KeyError(f"unknown policy: {policy}")
    proposals = POLICY_PLANS[policy].get(problem.problem_id, [""])
    episode_id = f"{policy}:{problem.problem_id}"
    records: list[StepRecord] = []

    for index, proposal in enumerate(proposals, start=1):
        result = verify_problem(problem, proposal)
        has_next = index < len(proposals)
        if result.verdict == "accepted":
            action: Action = "keep_and_stop"
            terminal = True
        elif result.verdict == "abstain":
            action = "mark_unsupported_and_stop"
            terminal = True
        elif has_next:
            action = "revise"
            terminal = False
        else:
            action = "stop_rejected"
            terminal = True

        records.append(
            StepRecord(
                schema="goai-exploration-step/v1",
                episode_id=episode_id,
                policy=policy,
                problem_id=problem.problem_id,
                rung=problem.rung,
                step=index,
                observation=problem.prompt,
                proposal=proposal,
                verifier_tier=result.tier,
                verdict=result.verdict,
                reason_code=result.reason_code,
                reason=result.reason,
                next_action=action,
                terminal=terminal,
            )
        )
        if terminal:
            break
    return records


def _terminal_record(records: list[StepRecord]) -> StepRecord:
    if not records or not records[-1].terminal:
        raise ValueError("episode did not produce a terminal record")
    return records[-1]


def run_benchmark(output_dir: Path) -> dict:
    """Run all reference policies and write JSONL traces plus a summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_path = output_dir / "episodes.jsonl"
    summary_path = output_dir / "benchmark-summary.json"
    all_records: list[StepRecord] = []
    policy_summaries: dict[str, dict] = {}

    for policy in POLICY_PLANS:
        counts = {"accepted": 0, "rejected": 0, "abstain": 0}
        steps = 0
        open_accepts = 0
        for problem in PROBLEMS:
            records = run_episode(problem, policy)
            terminal = _terminal_record(records)
            counts[terminal.verdict] += 1
            steps += len(records)
            if problem.rung == "open-unformalized" and terminal.verdict == "accepted":
                open_accepts += 1
            all_records.extend(records)
        policy_summaries[policy] = {
            "terminalVerdicts": counts,
            "steps": steps,
            "openUnformalizedAccepted": open_accepts,
        }

    with episode_path.open("w", encoding="utf-8") as handle:
        for record in all_records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "schema": "goai-verification-ladder-benchmark/v1",
        "candidateOnly": True,
        "canClaimAGI": False,
        "environment": {
            "problems": len(PROBLEMS),
            "policies": list(POLICY_PLANS),
            "si": "available",
            "sympy": "available" if _sympy_available() else "unavailable_fail_closed",
            "lean": "external_receipt_only_not_bundled",
        },
        "policies": policy_summaries,
        "interpretation": {
            "closedAndHeldOut": (
                "terminal verdicts reflect the executable verifier available in this run"
            ),
            "openUnformalized": (
                "abstention is environment contract behavior caused by missing executable "
                "specifications; it is not evidence that a model recognized an unsolved problem"
            ),
            "claimCeiling": (
                "environment/instrument evidence only; no model capability or AGI claim"
            ),
        },
        "artifacts": {
            "episodes": episode_path.name,
            "summary": summary_path.name,
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def selfcheck() -> int:
    """Exercise every verdict branch and the iterative episode contract."""
    print("=" * 76)
    print(" Fail-Closed Verification Ladder — self-check")
    print(" SI=embedded | SymPy=optional | Lean=external receipt only")
    print(" candidateOnly:true | canClaimAGI:false\n")
    failures = 0

    physics_cases = [
        ("9.8 m/s", "9.8 m/s", "accepted"),
        ("9.8 m/s^2", "9.8 m/s", "rejected"),
        ("9.8 J", "9.8 m/s", "rejected"),
        ("8.91 J", "9.0 J", "accepted"),
        ("3 ohm", "3 V/A", "accepted"),
        ("unparseable", "3 V/A", "abstain"),
    ]
    print("SI verifier:")
    for candidate, gold, expected in physics_cases:
        result = verify_physics(candidate, gold)
        ok = result.verdict == expected
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] {candidate!r} vs {gold!r}: {result}")

    print("\nSymbolic verifier:")
    symbolic_cases = [
        ("x^2+2*x+1", "(x+1)^2", "accepted"),
        ("x^2+2*x+2", "(x+1)^2", "rejected"),
    ]
    for candidate, gold, expected_if_available in symbolic_cases:
        result = verify_math(candidate, gold)
        expected = expected_if_available if _sympy_available() else "abstain"
        ok = result.verdict == expected
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] {candidate!r} vs {gold!r}: {result}")

    print("\nCoverage contract:")
    open_problem = PROBLEM_BY_ID["riemann-zeros"]
    coverage_cases = [
        ("sorry", "rejected", "proof_placeholder"),
        ("have h : True := trivial", "abstain", "unsupported_specification"),
        ("", "abstain", "unsupported_specification"),
    ]
    for proposal, verdict, reason_code in coverage_cases:
        result = verify_problem(open_problem, proposal)
        ok = result.verdict == verdict and result.reason_code == reason_code
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] {proposal!r}: {result}")

    print("\nIterative episodes:")
    expected_episodes = {
        "free-fall": (2, "accepted", ["rejected", "accepted"]),
        "riemann-zeros": (2, "abstain", ["rejected", "abstain"]),
    }
    for problem_id, (expected_steps, terminal_verdict, sequence) in expected_episodes.items():
        records = run_episode(PROBLEM_BY_ID[problem_id], "scripted-refine")
        observed = [record.verdict for record in records]
        ok = (
            len(records) == expected_steps
            and _terminal_record(records).verdict == terminal_verdict
            and observed == sequence
        )
        failures += 0 if ok else 1
        print(
            f"  [{'ok' if ok else 'FAIL'}] {problem_id}: "
            f"steps={len(records)} verdicts={observed}"
        )

    print("\nBenchmark artifact contract:")
    with tempfile.TemporaryDirectory(prefix="goai-verification-") as tmp:
        output_dir = Path(tmp)
        summary = run_benchmark(output_dir)
        rows = (output_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
        open_accepts = sum(
            details["openUnformalizedAccepted"]
            for details in summary["policies"].values()
        )
        ok = (
            len(rows) > 0
            and open_accepts == 0
            and summary["candidateOnly"] is True
            and summary["canClaimAGI"] is False
        )
        failures += 0 if ok else 1
        print(
            f"  [{'ok' if ok else 'FAIL'}] rows={len(rows)} "
            f"open_unformalized_accepts={open_accepts}"
        )

    if failures:
        print(f"\nSELF-CHECK FAILED: {failures} check(s) failed.")
        return 1
    print("\nSELF-CHECK PASSED: verifier, coverage, episode, and artifact contracts hold.")
    return 0


def interactive() -> int:
    print("Fail-Closed Verification Ladder (interactive)")
    print("Commands: ladder | verify <problem-id> <proposal> | episode <policy> <id>")
    print("          benchmark [output-dir] | policies | quit\n")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        parts = shlex.split(line)
        command = parts[0].lower()
        if command in {"quit", "exit", "q"}:
            return 0
        if command == "ladder":
            for problem in PROBLEMS:
                print(
                    f"  [{problem.rung:18}/{problem.tier:12}] "
                    f"{problem.problem_id:16} {problem.prompt}"
                )
            continue
        if command == "policies":
            print("  " + "\n  ".join(POLICY_PLANS))
            continue
        if command == "verify" and len(parts) >= 3:
            problem = PROBLEM_BY_ID.get(parts[1])
            if problem is None:
                print(f"  unknown problem: {parts[1]}")
                continue
            proposal = " ".join(parts[2:])
            print(f"  {verify_problem(problem, proposal)}")
            continue
        if command == "episode" and len(parts) == 3:
            policy, problem_id = parts[1], parts[2]
            problem = PROBLEM_BY_ID.get(problem_id)
            if policy not in POLICY_PLANS or problem is None:
                print("  unknown policy or problem")
                continue
            for record in run_episode(problem, policy):
                print(
                    f"  step={record.step} verdict={record.verdict} "
                    f"action={record.next_action} proposal={record.proposal!r}"
                )
            continue
        if command == "benchmark":
            output_dir = Path(parts[1]) if len(parts) == 2 else Path("artifacts")
            summary = run_benchmark(output_dir)
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            continue
        print("  invalid command")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--selfcheck", action="store_true", help="run deterministic checks")
    mode.add_argument("--benchmark", action="store_true", help="write benchmark artifacts")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
        help="benchmark output directory (default: artifacts)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.selfcheck:
        return selfcheck()
    if args.benchmark:
        summary = run_benchmark(args.output_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return interactive()


if __name__ == "__main__":
    raise SystemExit(main())
