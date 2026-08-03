#!/usr/bin/env python3
"""Deterministic well-posedness CONFIRMATION detector (the false-alarm closer).

WHY THIS EXISTS
---------------
The ill-posedness detector (``v2.verify_ill_posed``) can only DETECT
ill-posedness. It cannot CONFIRM well-posedness, so it abstains on every
well-posed free-text question it does not structurally recognize. That makes
its false-alarm rate 1.0 on the well-posed control items the false-alarm audit
uses (every solvable physics / math / arithmetic prompt is reported as
``unsupported_specification``).

This module is the narrow, fail-closed complement: it confirms well-posedness
for the *specific* shapes the false-alarm audit plants as controls, and
abstains on everything else. It never guesses.

TWO CONFIRMATION PATHS (everything else -> abstain)
---------------------------------------------------
1. ``unique_linear_system`` -- a ``Solve:`` (or ``solve for``) prompt over an
   exactly-determined linear system: N independent equations in N unknowns
   where SymPy ``linsolve`` returns exactly one solution -> ``accepted``.

2. ``simple_arithmetic``    -- a ``What is <expr>?`` prompt whose body is a
   plain arithmetic expression (ints / ``+ - * / ^`` only, no free symbols)
   that evaluates to a single rational number -> ``accepted``.

EVERYTHING ELSE (open questions, symbolic 'expand'/'factor' prompts, free-text
physics word problems, paradoxes, ... ) yields ``abstain``. This is intentional
and fail-closed: this tier only says ``accepted`` when it can PROVE
well-posedness, and a proof requires an actual solved value.

Claim ceiling: candidateOnly:true, canClaimAGI:false. This is instrument
evidence about a deterministic detector, NOT a model-capability claim.

Note: this module deliberately mirrors the ``v2.verify_ill_posed`` interface
(``WellPosedResult`` dataclass with ``verdict`` / ``reason_code`` / ``reason``
/ ``tier`` / ``candidateOnly`` / ``canClaimAGI`` and a ``to_dict()``) so the
false-alarm audit can swap it in as a confirmation tier without touching its
normalization layer.
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


# Restricted arithmetic grammar. Identical in spirit to the one in
# ``v2.verify_ill_posed`` / ``demo._safe_sympy_expression``: only literal
# arithmetic is permitted, never attribute access or calls. A Name node is
# allowed ONLY for the single placeholder ``x`` in the linear-system path
# (handled separately); the arithmetic path forbids Names entirely so a free
# symbol can never sneak through as a "well-posed" arithmetic question.
_ARITH_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.FloorDiv, ast.USub, ast.UAdd,
)


@dataclass(frozen=True)
class WellPosedResult:
    """Three-state deterministic verdict mirroring ``IllPosedResult``.

    - ``accepted``: well-posedness was CONFIRMED (a solved value exists).
    - ``abstain``  : outside this tier's narrow coverage (fail-closed).
    - ``rejected`` : never returned (this tier confirms, it does not refute).
    """

    verdict: str
    reason_code: str
    reason: str
    tier: str = "well-posedness-detector"
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


# --------------------------------------------------------------------------- #
# Safe parsing helpers (never eval user input)
# --------------------------------------------------------------------------- #
# Caret is the documented input form for powers (``2^3``) across this package
# (see ``demo._safe_sympy_expression``); SymPy / Python want ``**``.
_CARET_TO_POW = str.maketrans({"^": "**"})


def _normalize_caret(expr: str) -> str:
    return expr.translate(_CARET_TO_POW)


def _safe_arithmetic(expr_str: str, sp=None):
    """Parse a literal arithmetic expression with a restricted AST grammar.

    Returns the sympified value on success, or ``None`` if the input is not a
    closed-form arithmetic expression over integer/rational constants.
    Raises ``ValueError`` if the grammar rejects a node (Call / Attribute /
    Name / dunder) -- the input is parsed, never evaluated.
    """
    if sp is None:
        try:
            import sympy as sp
        except ImportError:
            return None
    normalized = _normalize_caret(expr_str)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, _ARITH_NODES):
            raise ValueError(
                f"grammar rejects node {type(node).__name__} in {expr_str!r}"
            )
    try:
        value = sp.sympify(ast.unparse(tree.body), evaluate=True)
    except Exception:
        return None
    # Reject anything that still carries a free symbol -- arithmetic only.
    if getattr(value, "free_symbols", None):
        return None
    return value


# --------------------------------------------------------------------------- #
# Linear-equation extraction (mirrors v2.verify_ill_posed._extract_equations
# but operates on a system the user wants SOLVED rather than checked).
# --------------------------------------------------------------------------- #
# Names may include a digit-suffixed variable (``x1``) or Greek (``a``).
_EQ_RE = re.compile(
    r"([a-zA-Z][a-zA-Z0-9_\*\+\-\/\(\)\^\s]*?)\s*=\s*([a-zA-Z0-9_\*\+\-\/\(\)\^\s\.\-]+)"
)

# Linear-system intent prefixes. Matches "Solve:", "Solve for x:", "solve the
# system:", or a bare "solve for x:" -- all forms the control items use.
_SOLVE_INTENT_RE = re.compile(r"solve", re.IGNORECASE)


def _linear_safe_expression(expr_str: str, sp):
    """Parse ``lhs - rhs`` for a linear system with the restricted grammar.

    Names ARE permitted here (linear unknowns), unlike the arithmetic path.
    Returns the sympified ``lhs - rhs`` expression or ``None``.
    """
    normalized = _normalize_caret(expr_str)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None
    # Names + arithmetic ops only (no calls, no attributes, no dunders).
    allowed = _ARITH_NODES + (ast.Name,)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            return None
    try:
        return sp.sympify(ast.unparse(tree.body), evaluate=True)
    except Exception:
        return None


def _extract_linear_equations(text: str, sp) -> list:
    """Extract ``lhs - rhs`` sympy expressions for every ``=`` in the text."""
    eqs = []
    for m in _EQ_RE.finditer(text):
        lhs = m.group(1).strip()
        rhs = m.group(2).strip()
        parsed = _linear_safe_expression(f"({lhs}) - ({rhs})", sp)
        if parsed is not None:
            eqs.append(parsed)
    return eqs


def _free_symbols(exprs: list) -> list:
    syms = set()
    for e in exprs:
        syms |= e.free_symbols
    return sorted(syms, key=lambda s: s.name)


# --------------------------------------------------------------------------- #
# Confirmation detector 1: uniquely-solvable linear system
# --------------------------------------------------------------------------- #
def _confirm_unique_linear_system(text: str) -> WellPosedResult | None:
    """Accept an exactly-determined linear system with a unique solution.

    Requires (a) explicit solve intent, (b) N independent equations in N
    unknowns, (c) SymPy ``linsolve`` returning exactly one solution. Any
    deviation -> ``None`` (fall through to fail-closed abstention).
    """
    if not _sympy_available():
        return None
    if not _SOLVE_INTENT_RE.search(text):
        return None
    import sympy as sp
    eqs = _extract_linear_equations(text, sp)
    if not eqs:
        return None
    syms = _free_symbols(eqs)
    if not syms:
        return None
    # Square-system requirement: #equations == #unknowns.
    if len(eqs) != len(syms):
        return None
    try:
        result = sp.linsolve(eqs, *syms)
    except Exception:
        return None
    # EmptySet -> no solution (ill-posed, not our job; abstain).
    # FiniteSet-of-one-tuple -> unique solution (well-posed).
    if result == sp.EmptySet:
        return None
    try:
        sols = list(result)
    except Exception:
        return None
    if len(sols) != 1:
        return None
    return WellPosedResult(
        "accepted",
        "unique_linear_system",
        f"the {len(eqs)}x{len(syms)} system has a unique solution "
        f"(SymPy linsolve); it is well-posed",
    )


# --------------------------------------------------------------------------- #
# Confirmation detector 2: simple closed-form arithmetic
# --------------------------------------------------------------------------- #
# "What is <expr>?" -- capture the body up to the question mark / end.
_WHAT_IS_RE = re.compile(
    r"\bwhat\s+is\s+(.+?)\s*\??\s*$", re.IGNORECASE | re.DOTALL,
)


def _confirm_simple_arithmetic(text: str) -> WellPosedResult | None:
    """Accept a ``What is <arithmetic>?`` prompt whose body is a closed form.

    The body must be a pure arithmetic expression (no free symbols). Anything
    wordy ("what is the integer square root of 144", "how many primes ...")
    fails the grammar / leaves a free symbol and falls through to abstain --
    those are out of this tier's narrow coverage by design.
    """
    if not _sympy_available():
        return None
    m = _WHAT_IS_RE.search(text)
    if not m:
        return None
    body = m.group(1).strip()
    if not body:
        return None
    try:
        value = _safe_arithmetic(body)
    except ValueError:
        # Grammar rejected a non-arithmetic node -> not in coverage.
        return None
    if value is None:
        return None
    return WellPosedResult(
        "accepted",
        "simple_arithmetic",
        f"the arithmetic expression evaluates to the closed form {value}; "
        "it is well-posed",
    )


def verify_well_posed(problem_text: Any) -> WellPosedResult:
    """Three-state deterministic well-posedness CONFIRMATION verdict.

    - ``accepted``: well-posedness was CONFIRMED by one of the two narrow
      detectors (unique linear system, or simple closed-form arithmetic).
    - ``abstain``  : outside coverage. This includes ALL free-text word
      problems, symbolic ``expand`` / ``factor`` prompts, open questions, and
      anything the grammar cannot prove has a solved value. Fail-closed.
    - ``rejected`` : never returned (this tier confirms; it does not refute).

    Accepts either a string (the problem text) or an object exposing a
    ``problem_statement`` / ``prompt`` / ``description`` / ``text`` attribute
    or key -- the SAME coercion ``verify_ill_posed`` uses, so the false-alarm
    audit can pass identical task objects to both tiers.
    """
    # Mirror the task-object coercion in v2.verify_ill_posed.verify_ill_posed.
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
        return WellPosedResult(
            "abstain", "unparseable_problem", "empty or unparseable problem"
        )

    # Confirmations in order (cheapest / most-specific first). The first
    # detector that PROVES well-posedness wins; otherwise we fall through to
    # fail-closed abstention.
    for detector in (
        _confirm_unique_linear_system,
        _confirm_simple_arithmetic,
    ):
        result = detector(text)
        if result is not None:
            return result

    return WellPosedResult(
        "abstain",
        "unsupported_specification",
        "the well-posedness tier cannot confirm this problem is solvable; "
        "it is outside current coverage (fail-closed)",
    )
