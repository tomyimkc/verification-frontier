#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Lightweight step-level CoT checker for the HF Space demo.

This is a SIMPLIFIED demo companion to the full step_verifier that is being
built separately in the submission package. It is intentionally **self-contained**:
it imports only from the local ``demo.py`` / ``units.py`` (the provider-free
verifier environment bundled in this Space) and never from ``v2/``.

For each parsed chain-of-thought step it returns one of three verdicts:

* ``✅ verified``  — the step contains an equation whose two sides balance
  numerically (SymPy on a restricted grammar, both sides pure numbers) AND/OR
  whose two sides carry consistent SI dimensions (via the bundled units engine).
* ``❌ error``     — the step contains an equation with a confirmed arithmetic
  slip (two pure-number sides that disagree within tolerance) OR a confirmed
  SI-dimension mismatch (e.g. ``m/s`` vs ``m/s^2``).
* ``⏸️ unchecked`` — the step has no machine-checkable equation, or only
  symbolic/compound expressions we cannot reduce (e.g. ``P = I^2 * R``). This is
  the fail-closed outcome: we never pretend to have verified what we cannot parse.

Scope note (intentional): this checker verifies the **internal consistency** of
each step — does the arithmetic balance, do the units agree with each other. It
does NOT check semantic correctness against ground truth (a step can be
internally consistent yet conceptually wrong, e.g. multiplying by 3.6 instead of
dividing). Semantic correctness is the job of the deterministic verifier exposed
on Tab ② Step 4 and on Tab ④. This clean separation is the whole point of the
demo: step-level checking catches arithmetic slips; the deterministic verifier
catches conceptual errors.

Claim ceiling: candidateOnly:true, canClaimAGI:false. This is a demo
instrument, not a confirmatory result.
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make the bundled demo + units importable when this file is loaded by Gradio
# from any cwd (HF Space launches app.py from the Space root, which is fine,
# but being explicit keeps imports robust under ad-hoc test runs too).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import demo  # noqa: E402  (provider-free verifier environment bundled in Space)
from units import format_dim, parse_quantity, parse_unit, same_dim  # noqa: E402


CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "simplifiedDemoChecker": True,
}

VERIFIED = "verified"     # ✅
ERROR = "error"           # ❌
UNCHECKED = "unchecked"   # ⏸️

ICON = {VERIFIED: "✅", ERROR: "❌", UNCHECKED: "⏸️"}

# Relative tolerance for the numeric-balance check. Matches demo.RTOL (1%) so the
# step checker and the deterministic SI verifier agree on what "close" means; a
# model that rounds 20/4.9 = 4.0816... to 4.08 should still be ✅.
_RTOL = 1e-2

# Multi-letter pure-alpha unit symbols (>= 3 chars) that are NOT prose. Built
# from the bundled units engine so we stay self-contained. A pure-alpha token of
# length >= 3 that is not in this set is treated as a prose word (Use, answer,
# Step, Therefore, ...) and the candidate equation is rejected as non-math.
_ALLOWED_ALPHA3 = {
    name.lower()
    for name in (
        "mol", "cd", "ohm", "Wb", "Hz", "rad", "sr", "min", "day", "atm",
        "bar", "eV",
    )
}


def _sympy_available() -> bool:
    try:
        import sympy  # noqa: F401
        return True
    except ImportError:
        return False


# Restricted AST grammar for evaluating a single arithmetic expression.
# Same shape as demo._safe_sympy_expression: never eval(), never expose builtins.
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd, ast.FloorDiv,
)

# Step bodies often start with a "N." / "Step N:" prefix from _parse_cot_steps;
# strip it so it does not pollute an equation segment. The delimiter (., ), :)
# MUST be followed by whitespace or end-of-string, otherwise a leading decimal
# such as "5.0" would have its "5." stripped (turning it into "0").
_LEADING_NUM = re.compile(r"^\s*\d{1,2}[\.\):](?=\s|$)\s*")


@dataclass(frozen=True)
class StepVerdict:
    """Per-step verdict for the demo CoT checker."""

    index: int
    verdict: str          # one of VERIFIED / ERROR / UNCHECKED
    icon: str             # ✅ / ❌ / ⏸️
    summary: str          # short human-readable explanation
    text: str             # the original step text (echoed for the UI)
    detail: dict          # machine-readable findings (equations, units, etc.)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "verdict": self.verdict,
            "icon": self.icon,
            "summary": self.summary,
            "text": self.text,
            "detail": self.detail,
        }


def _clean_step_text(text: str) -> str:
    """Strip a leading "N." numbering, LaTeX markup, and surrounding whitespace."""
    s = (text or "").strip()
    # Strip LaTeX markup so equations like \[ 3 \, \text{kg} \cdot 4 \, \text{m/s} = 12 \] become parseable
    s = s.replace("\\[", "").replace("\\]", "")
    s = s.replace("\\boxed{", "").replace("\\(", "").replace("\\)", "")
    s = s.replace("\\text{", " ").replace("\\,", " ")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = s.replace("\\frac", "").replace("\\approx", "=")
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\\\", "")
    return _LEADING_NUM.sub("", s).strip()


def _safe_eval(expr_str: str, sp=None):
    """Parse and evaluate a math expression with a restricted AST grammar.

    Returns the evaluated sympy expression on success, or None if the
    expression is empty / unparseable / uses forbidden syntax. Never calls
    eval() and never exposes builtins.
    """
    expr_str = (expr_str or "").strip()
    if not expr_str:
        return None
    # Normalise common ASCII-isms the model emits.
    expr_str = (
        expr_str.replace("^", "**")
        .replace("⊗", "*")
        .replace("·", "*")
        .replace("×", "*")
    )
    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return None
    if sp is None:
        try:
            import sympy as sp  # noqa: F811
        except ImportError:
            return None
    try:
        value = sp.sympify(ast.unparse(tree.body), evaluate=True)
    except Exception:
        return None
    # sympify resolves several bare names to non-expression sympy singletons:
    # Q -> AssumptionKeys, N -> function, S -> SingletonRegistry, O -> type,
    # beta/gamma -> FunctionClass. Those are ordinary physics variable names
    # (heat, newtons, entropy, Lorentz factor -- and this demo ships a Lorentz
    # challenge), and they carry no .free_symbols, so letting them through
    # raised AttributeError downstream. Fail closed instead.
    if not isinstance(value, sp.Expr):
        return None
    return value


def _looks_like_math(seg: str) -> bool:
    """Heuristic: is this equation segment a math expression or prose?

    Rejects segments that contain prose words (a pure-alpha token of length >= 3
    that is not a known unit symbol, e.g. "Use", "answer", "Therefore"). Accepts
    segments with at least one digit, or a math operator, or a single bare
    variable name. This is what stops ``Use h = 0.5*g*t^2`` from being parsed as
    an equation with LHS "Use h".
    """
    s = (seg or "").strip()
    if not s:
        return False
    tokens = s.split()
    has_digit = any(re.search(r"\d", t) for t in tokens)
    for tok in tokens:
        if re.fullmatch(r"[A-Za-z]+", tok):
            if len(tok) >= 3 and tok.lower() not in _ALLOWED_ALPHA3:
                return False  # a prose word
    if has_digit:
        return True
    if re.search(r"[+\-*/^()×·⊗]", s):
        return True
    # single bare variable like "P", "t", "x"
    if len(tokens) == 1 and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", tokens[0]):
        return True
    return False


def _split_on_single_eq(s: str) -> list[str]:
    """Split on a genuine math '=', ignoring '==', '>=', '<=', '!=', ':=', '=>'."""
    return re.split(r"(?<![<>!=:~-])=(?![=>])", s)


def _clean_segment(seg: str) -> str:
    """Strip leading numbering and prose lead-ins from an equation segment.

    Models frequently write ``3. Calculate: 4 * 10 = 50`` or ``Step 2: P = 40``.
    We want to evaluate the math part ``4 * 10`` / ``P = 40``, not the prose.
    Strips: a leading "N." / "Step N:" numbering, and a leading prose label
    ending in a colon ("Calculate:", "Substitute:", "Solve:", etc.). Math after
    the last colon is kept.
    """
    s = (seg or "").strip()
    # Drop a leading "N." / "N)" / "Step N:" numbering.
    s = _LEADING_NUM.sub("", s).strip()
    # If there is a prose lead-in followed by a colon, keep what is after the
    # LAST colon (a math expression may contain colons rarely; the last one is
    # the safest split point). Only strip if what follows looks like math.
    if ":" in s:
        after = s.rsplit(":", 1)[1].strip()
        if after and _looks_like_math(after):
            s = after
    return s.strip()


def _extract_chains(text: str) -> list[list[str]]:
    """Return equation chains found in the step text.

    A chain is a list of segments joined by '=' (so ``A = B = C`` becomes
    ``["A", "B", "C"]``). Lines are split on commas/semicolons first so that
    ``x + y = 3, x + y = 5`` yields two chains. Each segment is cleaned of
    leading prose ("Calculate:", "Step 2:") and only chains whose cleaned
    segments all pass ``_looks_like_math`` are kept, which filters out prose.
    """
    chains: list[list[str]] = []
    for line in text.splitlines():
        for clause in re.split(r"[,;]", line):
            clause = clause.strip().strip(".").strip()
            if "=" not in clause:
                continue
            parts = _split_on_single_eq(clause)
            if len(parts) < 2:
                continue
            segs = [_clean_segment(p) for p in parts]
            if all(s and _looks_like_math(s) for s in segs):
                chains.append(segs)
    return chains


def _segment_quantity(seg: str) -> tuple[float | None, tuple | None, str | None]:
    """If ``seg`` is a clean "number + unit" (e.g. ``9.8 m/s^2``), return its
    SI value, dimension, and the raw unit string. Otherwise return all-None.

    "Clean" means: a single leading number followed by a unit expression whose
    only digits are exponent markers (``^2``). This excludes compound
    expressions like ``72000 m / 3600 s`` (which has a standalone 3600) — those
    are left for the numeric check or reported unchecked, never falsely flagged.
    """
    s = (seg or "").strip()
    if not s:
        return None, None, None
    m = re.match(r"^([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s+(.+)$", s)
    if not m:
        return None, None, None
    num_str, unit_str = m.group(1), m.group(2).strip()
    # A real unit symbol may contain digits only as exponents (^2, ^-1). Any
    # other digit means this is a compound numeric expression, not a quantity.
    unit_no_exp = re.sub(r"\^[-+]?\d+(?:\.\d+)?", "", unit_str)
    if re.search(r"\d", unit_no_exp):
        return None, None, None
    ok, factor, dim = parse_unit(unit_str)
    if not ok:
        return None, None, None
    try:
        value = float(num_str) * factor
    except ValueError:
        return None, None, None
    return value, dim, unit_str


def _written_precision_tolerance(text: str | None) -> float | None:
    """Half a unit in the last decimal place the answer was WRITTEN to.

    A model that writes ``1/0.6 = 1.667`` has rounded, not erred: the true value
    1.66667 differs by 3.3e-4, which its own 3-decimal presentation cannot
    express. Returns None when no numeric literal is present.
    """
    if not text:
        return None
    m = re.search(r"[-+]?\d*\.?\d+", text)
    if not m:
        return None
    literal = m.group(0)
    decimals = len(literal.split(".")[1]) if "." in literal else 0
    return 0.5 * (10.0 ** -decimals)


def _numeric_equal(l_expr, r_expr, rhs_text: str | None = None) -> bool | None:
    """Three-state arithmetic balance: True / False / None (abstain).

    A flat 1% relative tolerance was previously used here, which silently
    ACCEPTED "500 * 4.18 * 60 = 125000" (true value 125400, error 400, well
    inside 1% of a six-figure number). A silent pass is the one outcome this
    project exists to prevent, so the comparison is now three-state:

      * agrees to floating-point precision            -> True  (verified)
      * differs by more than the written precision    -> False (error)
      * differs only by what rounding could explain   -> None  (abstain)

    The middle case is reported as unchecked rather than verified, because the
    step checker cannot tell a rounded presentation from a small real error.
    """
    if l_expr is None or r_expr is None:
        return None
    if getattr(l_expr, "free_symbols", None) or getattr(r_expr, "free_symbols", None):
        return None
    try:
        lv = float(l_expr)
        rv = float(r_expr)
    except (TypeError, ValueError):
        return None

    scale = max(abs(lv), abs(rv), 1.0)
    diff = abs(lv - rv)
    if diff <= 1e-9 * scale:
        return True

    rounding = _written_precision_tolerance(rhs_text)
    if rounding is not None and diff <= rounding:
        return None  # explainable by the precision the answer was written to
    return False


def _check_pair(lhs: str, rhs: str, sp) -> dict:
    """Check one equation pair (adjacent segments in a chain).

    Returns a dict with numeric/units booleans (or None when a check does not
    apply) plus dimension strings for the UI. A None never contributes to a
    pass or fail — only a hard False does.
    """
    out: dict[str, Any] = {
        "lhs": lhs, "rhs": rhs,
        "numeric": None, "units": None,
        "lhsUnitDim": None, "rhsUnitDim": None,
        "reason": "",
    }

    # --- Numeric balance via SymPy on the safe grammar ---
    if sp is not None:
        l_expr = _safe_eval(lhs, sp)
        r_expr = _safe_eval(rhs, sp)
        out["numeric"] = _numeric_equal(l_expr, r_expr, rhs)
        if out["numeric"] is False:
            out["reason"] = "numeric mismatch (arithmetic does not balance)"

    # --- Unit consistency via the bundled SI units engine ---
    l_val, l_dim, l_unit = _segment_quantity(lhs)
    r_val, r_dim, r_unit = _segment_quantity(rhs)
    if l_dim is not None:
        out["lhsUnitDim"] = format_dim(l_dim)
    if r_dim is not None:
        out["rhsUnitDim"] = format_dim(r_dim)
    if l_dim is not None and r_dim is not None:
        out["units"] = same_dim(l_dim, r_dim)
        if not out["units"]:
            out["reason"] = (
                f"unit dimension mismatch: {out['lhsUnitDim']} vs {out['rhsUnitDim']}"
            )

    return out


def check_step(step_text: str, index: int = 0) -> StepVerdict:
    """Check a single CoT step. Returns a StepVerdict.

    Logic:
      1. Extract equation chains from the step (prose filtered out).
      2. For each adjacent segment pair, check numeric balance (SymPy, safe
         grammar, pure numbers only) and unit consistency (bundled SI engine,
         clean quantities only).
      3. If ANY pair has a confirmed failure -> ERROR for the step.
      4. Else if ANY pair has a confirmed pass -> VERIFIED.
      5. Else -> UNCHECKED (no check could be decided).
    """
    cleaned = _clean_step_text(step_text)
    sp = None
    if _sympy_available():
        import sympy as sp  # noqa: F811

    chains = _extract_chains(cleaned)
    findings: list[dict] = []
    any_fail = False
    any_pass = False
    for segs in chains:
        for i in range(len(segs) - 1):
            chk = _check_pair(segs[i], segs[i + 1], sp)
            findings.append(chk)
            if chk["numeric"] is False or chk["units"] is False:
                any_fail = True
            if chk["numeric"] is True or chk["units"] is True:
                any_pass = True

    # Surface a leading quantity even when there is no checkable equation, so
    # the UI can explain *why* a step is unchecked rather than leaving it blank.
    # Uses the bundled units engine directly so exponents like ``m/s^2`` are
    # captured whole rather than truncated at the first digit.
    quantity_note = None
    if not findings:
        for clause in re.split(r"[,;\n]", cleaned):
            clause = clause.strip().strip(".:")
            if not clause:
                continue
            # Try the whole clause as a quantity, then peel leading words
            # ("answer = 20 m/s" -> "20 m/s").
            ok, value, dim = parse_quantity(clause)
            if ok and dim:
                quantity_note = {"value": value, "unit": format_dim(dim), "dim": format_dim(dim)}
                break
            m = re.search(
                r"([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s+([A-Za-zΩµμ][^,\n]*?)(?=[\s\.,;]|$)",
                clause,
            )
            if m:
                num_str, unit_str = m.group(1), m.group(2).strip()
                ok, _factor, dim = parse_unit(unit_str)
                if ok and any(dim):
                    quantity_note = {
                        "value": float(num_str),
                        "unit": unit_str,
                        "dim": format_dim(dim),
                    }
                    break

    if any_fail:
        bad = next(
            c for c in findings if c["numeric"] is False or c["units"] is False
        )
        summary = f"equation does not balance: {bad['reason']}"
        verdict = ERROR
    elif any_pass:
        n_num = sum(1 for c in findings if c["numeric"] is True)
        n_unit = sum(1 for c in findings if c["units"] is True)
        parts = []
        if n_num:
            parts.append(f"{n_num} balanced")
        if n_unit:
            parts.append(f"{n_unit} unit-consistent")
        summary = "; ".join(parts) if parts else "checked"
        verdict = VERIFIED
    else:
        if findings:
            summary = "equation present but symbolic/compound (not reducible)"
        elif quantity_note:
            summary = (
                f"contains quantity {quantity_note['value']} {quantity_note['unit']} "
                f"(no checkable equation)"
            )
        else:
            summary = "no machine-checkable equation in this step"
        verdict = UNCHECKED

    detail: dict[str, Any] = {"equations": findings, "quantity": quantity_note}
    return StepVerdict(
        index=index,
        verdict=verdict,
        icon=ICON[verdict],
        summary=summary,
        text=step_text,
        detail=detail,
    )


def check_steps(steps: list) -> list[StepVerdict]:
    """Check a list of parsed CoT steps. Returns one StepVerdict per step.

    Accepts either strings or dicts with a 'raw_text' key (from _parse_cot_steps).
    Empty input returns an empty list.
    """
    if not steps:
        return []
    texts = []
    for s in steps:
        if isinstance(s, dict):
            texts.append(s.get("raw_text", s.get("text", str(s))))
        elif isinstance(s, str):
            texts.append(s)
        else:
            texts.append(str(s))
    return [check_step(t, index=i) for i, t in enumerate(texts)]


def summarize(verdicts: list[StepVerdict]) -> dict:
    """Roll up per-step verdicts into a small summary for the UI."""
    if not verdicts:
        return {"total": 0, "verified": 0, "error": 0, "unchecked": 0, "clean": True}
    counts = {VERIFIED: 0, ERROR: 0, UNCHECKED: 0}
    for v in verdicts:
        counts[v.verdict] += 1
    return {
        "total": len(verdicts),
        "verified": counts[VERIFIED],
        "error": counts[ERROR],
        "unchecked": counts[UNCHECKED],
        "clean": counts[ERROR] == 0,
    }
