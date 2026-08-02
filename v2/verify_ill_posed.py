#!/usr/bin/env python3
"""Deterministic ill-posedness detector for the verification frontier.

Five detectors, run in order (cheapest/most-specific first):

1. ``contradictory_system`` — linear system with no solution (SymPy linsolve → EmptySet).
2. ``missing_constraint`` — "solve for x" with more unknowns than equations.
3. ``empty_feasible_region`` — contradictory inequality bounds (SymPy).
4. ``circular_dependency`` — cycle in a "A depends on B" graph (DFS 3-colour).
5. ``undecidable`` — narrow keyword anchors for known paradoxes.

A detected ill-posed problem yields ``abstain`` — because the verifier cannot
solve a problem with no solution; abstaining is the CORRECT answer.

Claim ceiling: candidateOnly:true, canClaimAGI:false.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}


def _sympy_available() -> bool:
    try:
        import sympy  # noqa: F401
        return True
    except ImportError:
        return False


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd, ast.FloorDiv,
)


def _safe_sympy_expression(expr_str: str, sp=None):
    """Parse a math expression with a restricted AST grammar (never eval).

    Returns the sympified expression on success, None on parse failure.
    Raises ValueError if the grammar rejects the input (malicious nodes).
    """
    if sp is None:
        try:
            import sympy as sp
        except ImportError:
            return None
    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"grammar rejects node {type(node).__name__} in {expr_str!r}")
    try:
        return sp.sympify(ast.unparse(tree.body), evaluate=True)
    except Exception:
        return None


@dataclass(frozen=True)
class IllPosedResult:
    verdict: str
    reason_code: str
    reason: str
    tier: str = "ill-posedness-detector"
    candidateOnly: bool = True
    canClaimAGI: bool = False

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reasonCode": self.reason_code,
            "reason": self.reason,
            "tier": self.tier,
            "candidateOnly": self.candidateOnly,
            "canClaimAGI": self.canClaimAGI,
        }


_EQ_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9_\*\+\-\/\(\)\^\s]*?)\s*=\s*([a-zA-Z0-9_\*\+\-\/\(\)\^\s\.\-]+)")
_SOLVE_FOR_RE = re.compile(r"solve\s+for\s+(\w+)", re.IGNORECASE)
_DEPENDS_RE = re.compile(r"(\w+)\s*(?:depends\s+on|requires?|needs?)\s*(\w+)", re.IGNORECASE)


def _extract_equations(text: str) -> list[str]:
    """Extract 'lhs - rhs' expressions from text containing '=' signs."""
    eqs = []
    for m in _EQ_RE.finditer(text):
        lhs = m.group(1).strip()
        rhs = m.group(2).strip()
        expr = f"({lhs}) - ({rhs})"
        try:
            parsed = _safe_sympy_expression(expr)
            if parsed is not None:
                eqs.append(parsed)
        except ValueError:
            continue
    return eqs


def _free_symbols(exprs: list) -> set:
    syms = set()
    for e in exprs:
        syms |= e.free_symbols
    return syms


def _check_contradictory_system(text: str) -> IllPosedResult | None:
    if not _sympy_available():
        return None
    eqs = _extract_equations(text)
    if len(eqs) < 2:
        return None
    import sympy as sp
    syms = sorted(_free_symbols(eqs), key=lambda s: s.name)
    if not syms:
        return None
    try:
        result = sp.linsolve(eqs, *syms)
        if result == sp.EmptySet:
            return IllPosedResult(
                "abstain", "contradictory_system",
                f"the system has no solution (SymPy linsolve returned EmptySet for {len(eqs)} equations in {len(syms)} unknowns)",
            )
    except Exception:
        pass
    return None


def _check_missing_constraint(text: str) -> IllPosedResult | None:
    m = _SOLVE_FOR_RE.search(text)
    if not m:
        return None
    if not _sympy_available():
        return None
    eqs = _extract_equations(text)
    if not eqs:
        return None
    syms = _free_symbols(eqs)
    if len(syms) > len(eqs):
        return IllPosedResult(
            "abstain", "missing_constraint",
            f"underdetermined: {len(syms)} unknowns but only {len(eqs)} equation(s); "
            "the system has infinitely many solutions",
        )
    return None


def _check_empty_feasible_region(text: str) -> IllPosedResult | None:
    if not _sympy_available():
        return None
    import sympy as sp
    # Extract inequality pairs like "x < 0 and x > 0"
    bounds = re.findall(r"(\w+)\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)", text)
    if len(bounds) < 2:
        return None
    # Group bounds by variable
    var_bounds: dict[str, list[tuple[str, float]]] = {}
    for var, op, val in bounds:
        var_bounds.setdefault(var, []).append((op, float(val)))
    for var, ops in var_bounds.items():
        if len(ops) < 2:
            continue
        x = sp.Symbol(var)
        try:
            inequalities = []
            for op, val in ops:
                if op == "<": inequalities.append(x < val)
                elif op == ">": inequalities.append(x > val)
                elif op == "<=": inequalities.append(x <= val)
                elif op == ">=": inequalities.append(x >= val)
            feasible = sp.reduce_inequalities(inequalities, x)
            if feasible == sp.false or feasible == sp.BooleanFalse:
                return IllPosedResult(
                    "abstain", "empty_feasible_region",
                    f"the feasible region for {var} is empty: contradictory bounds",
                )
        except Exception:
            pass
    return None


def _graph_has_cycle(graph: dict[str, set[str]]) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for nbr in graph.get(node, set()):
            c = color.get(nbr, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(nbr):
                return True
        color[node] = BLACK
        return False

    return any(dfs(n) for n in graph if color.get(n, WHITE) == WHITE)


def _check_circular_dependency(text: str) -> IllPosedResult | None:
    edges: dict[str, set[str]] = {}
    for m in _DEPENDS_RE.finditer(text):
        a, b = m.group(1).lower(), m.group(2).lower()
        edges.setdefault(a, set()).add(b)
    if not edges:
        return None
    if _graph_has_cycle(edges):
        return IllPosedResult(
            "abstain", "circular_dependency",
            "the dependency graph contains a cycle; the system cannot be resolved",
        )
    return None


_PARADOX_PATTERNS = [
    re.compile(r"this\s+(?:statement|sentence)\s+is\s+false", re.IGNORECASE),
    re.compile(r"i\s+am\s+lying", re.IGNORECASE),
    re.compile(r"do\s+not\s+contain\s+themselves", re.IGNORECASE),
    re.compile(r"set\s+of\s+all\s+sets\s+that\s+do\s+not\s+contain\s+themselves", re.IGNORECASE),
    re.compile(r"barber.*shaves.*who\s+do\s+not\s+shave\s+themselves", re.IGNORECASE),
    re.compile(r"barber.*shaves.*do\s+not\s+shave\s+themselves", re.IGNORECASE),
    re.compile(r"barber.*shaves\s+everyone", re.IGNORECASE),
    re.compile(r"this\s+question\s+is\s+unanswerable", re.IGNORECASE),
]


def _check_undecidable(text: str) -> IllPosedResult | None:
    for pattern in _PARADOX_PATTERNS:
        if pattern.search(text):
            return IllPosedResult(
                "abstain", "undecidable",
                "the proposition is self-referential or paradoxical; "
                "it is undecidable within the given framework",
            )
    return None


def verify_ill_posed(problem_text: Any) -> IllPosedResult:
    """Three-state deterministic verdict for a problem's well-posedness.

    - ``accepted``: the problem is a confirmed well-posed solvable system.
    - ``abstain``: the problem is ill-posed (detectors 1-5) or outside coverage.
    - ``rejected``: never returned (ill-posed → abstain is the correct answer).

    Accepts either a string (the problem text) or an object with a
    ``problem_statement`` / ``prompt`` / ``description`` attribute/key.
    """
    # Handle task objects (from ill_posed_tasks.IllPosedTask)
    if problem_text is not None and not isinstance(problem_text, str):
        for attr in ("problem_statement", "prompt", "description", "text"):
            val = getattr(problem_text, attr, None)
            if val is None and isinstance(problem_text, dict):
                val = problem_text.get(attr)
            if val:
                problem_text = val
                break
    text = (problem_text or "").strip() if isinstance(problem_text, str) else ""
    if not text:
        return IllPosedResult("abstain", "unparseable_problem", "empty or unparseable problem")

    # Detectors in order (cheapest/most-specific first)
    for detector in (
        _check_contradictory_system,
        _check_missing_constraint,
        _check_empty_feasible_region,
        _check_circular_dependency,
        _check_undecidable,
    ):
        result = detector(text)
        if result is not None:
            return result

    # Try to confirm well-posedness: a square system with a unique solution
    if _sympy_available():
        import sympy as sp
        eqs = _extract_equations(text)
        syms = sorted(_free_symbols(eqs), key=lambda s: s.name) if eqs else []
        if eqs and len(eqs) == len(syms) and "solve" in text.lower():
            try:
                result = sp.linsolve(eqs, *syms)
                if result != sp.EmptySet and len(result) == 1:
                    return IllPosedResult(
                        "accepted", "well_posed_system",
                        "the system is well-posed with a unique solution",
                    )
            except Exception:
                pass

    # Fail-closed: cannot determine well-posedness
    return IllPosedResult(
        "abstain", "unsupported_specification",
        "the verifier cannot determine whether this problem is well-posed; "
        "it is outside current coverage",
    )
