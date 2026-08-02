#!/usr/bin/env python3
"""Tests for the deterministic ill-posedness-verification tier.

Covers every verdict branch of :func:`verify_ill_posed`:

* the five ill-posedness detectors each yield ``abstain`` with a documented
  ``reason_code`` (ABSTAIN IS THE CORRECT ANSWER for an ill-posed problem);
* a square, uniquely-solvable system yields ``accepted`` (well-posed);
* problems outside coverage yield ``abstain`` (fail-closed, never a guess);
* the claim ceiling is preserved on every result.
"""
from __future__ import annotations

import unittest

from v2.verify_ill_posed import (
    CLAIM_CEILING,
    IllPosedResult,
    _graph_has_cycle,
    _sympy_available,
    verify_ill_posed,
)


class ContradictorySystemTests(unittest.TestCase):
    """Detector 1: contradictory linear systems."""

    def test_simple_contradiction_abstains(self) -> None:
        r = verify_ill_posed("x + y = 3, x + y = 5")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "contradictory_system")

    def test_contradiction_with_solve_for_prefix(self) -> None:
        # Detector 1 must win over detector 2 (missing constraint).
        r = verify_ill_posed("solve for x: x + y = 3, x + y = 5")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "contradictory_system")

    def test_three_equation_contradiction(self) -> None:
        r = verify_ill_posed("x = 1, x = 2, x = 3")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "contradictory_system")

    def test_reason_mentions_empty_solution_set(self) -> None:
        r = verify_ill_posed("x + y = 3, x + y = 5")
        self.assertIn("no solution", r.reason.lower())


class MissingConstraintTests(unittest.TestCase):
    """Detector 2: under-determined 'solve for x'."""

    def test_more_unknowns_than_equations(self) -> None:
        r = verify_ill_posed("solve for x: x + y = 5")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "missing_constraint")

    def test_reason_names_unknown_and_equation_counts(self) -> None:
        r = verify_ill_posed("solve for x: x + y + z = 5")
        self.assertIn("unknown", r.reason.lower())
        self.assertIn("equation", r.reason.lower())

    def test_two_unknowns_one_equation(self) -> None:
        r = verify_ill_posed("solve for n: 2*n + m = 10")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "missing_constraint")

    def test_square_system_not_flagged_as_missing(self) -> None:
        # x + y = 3, x - y = 1 → 2 eqs, 2 unknowns → well-posed, not missing.
        r = verify_ill_posed("solve for x: x + y = 3, x - y = 1")
        self.assertNotEqual(r.reason_code, "missing_constraint")


class EmptyFeasibleRegionTests(unittest.TestCase):
    """Detector 3: contradictory bounds."""

    def test_opposite_bounds_on_origin(self) -> None:
        r = verify_ill_posed("x < 0 and x > 0")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "empty_feasible_region")

    def test_bounds_with_maximize_prefix(self) -> None:
        r = verify_ill_posed("maximize x subject to x < 0 and x > 0")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "empty_feasible_region")

    def test_bounds_with_swapped_numbers(self) -> None:
        r = verify_ill_posed("x > 5 and x < 3")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "empty_feasible_region")

    def test_inclusive_opposite_bounds(self) -> None:
        r = verify_ill_posed("x <= 0 and x >= 1")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "empty_feasible_region")

    def test_consistent_bounds_not_flagged(self) -> None:
        # x > 0 and x < 5 is a valid range → must NOT be flagged ill-posed.
        r = verify_ill_posed("x > 0 and x < 5")
        self.assertNotEqual(r.reason_code, "empty_feasible_region")

    def test_reason_mentions_empty_region(self) -> None:
        r = verify_ill_posed("x < 0 and x > 0")
        self.assertIn("empty", r.reason.lower())


class CircularDependencyTests(unittest.TestCase):
    """Detector 4: cycles in a dependency graph."""

    def test_two_node_cycle(self) -> None:
        r = verify_ill_posed("A depends on B, B depends on A")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "circular_dependency")

    def test_three_node_cycle(self) -> None:
        r = verify_ill_posed(
            "A depends on B, B depends on C, C depends on A"
        )
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "circular_dependency")

    def test_requires_synonym(self) -> None:
        r = verify_ill_posed("A requires B, B requires A")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "circular_dependency")

    def test_acyclic_chain_not_flagged(self) -> None:
        r = verify_ill_posed("A depends on B, B depends on C")
        self.assertNotEqual(r.reason_code, "circular_dependency")

    def test_single_edge_not_a_cycle(self) -> None:
        r = verify_ill_posed("A depends on B")
        self.assertNotEqual(r.reason_code, "circular_dependency")

    def test_graph_has_cycle_helper(self) -> None:
        cyclic = {"A": {"B"}, "B": {"A"}}
        acyclic = {"A": {"B"}, "B": {"C"}}
        self.assertTrue(_graph_has_cycle(cyclic))
        self.assertFalse(_graph_has_cycle(acyclic))


class ParadoxDetectorTests(unittest.TestCase):
    """Detector 5: self-referential / paradoxical."""

    def test_liar_sentence(self) -> None:
        for text in [
            "this sentence is false",
            "this statement is false",
            "I am lying",
        ]:
            r = verify_ill_posed(text)
            self.assertEqual(r.verdict, "abstain", text)
            self.assertEqual(r.reason_code, "undecidable", text)

    def test_russell_set(self) -> None:
        r = verify_ill_posed("consider the set of all sets that do not contain themselves")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "undecidable")

    def test_barber_paradox(self) -> None:
        r = verify_ill_posed("the barber who shaves everyone lives in town")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "undecidable")


class WellPosedAcceptanceTests(unittest.TestCase):
    """The only path to ``accepted``."""

    def test_square_unique_system_accepted(self) -> None:
        r = verify_ill_posed("solve for x: x + y = 3, x - y = 1")
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "well_posed_system")

    def test_single_variable_linear_accepted(self) -> None:
        r = verify_ill_posed("solve for x: 2*x = 4")
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "well_posed_system")

    def test_three_by_three_unique_accepted(self) -> None:
        r = verify_ill_posed(
            "solve for x: x + y + z = 6, x - y = 0, y - z = 0"
        )
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "well_posed_system")

    def test_square_system_without_solve_for_not_accepted(self) -> None:
        # No explicit "solve for" intent → cannot confirm well-posedness.
        r = verify_ill_posed("x + y = 3, x - y = 1")
        self.assertNotEqual(r.verdict, "accepted")


class FailClosedTests(unittest.TestCase):
    """Fail-closed: outside coverage → abstain, never a guess."""

    def test_open_question_abstains(self) -> None:
        r = verify_ill_posed("what is the meaning of life?")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unsupported_specification")

    def test_empty_text_abstains(self) -> None:
        r = verify_ill_posed("")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unparseable_problem")

    def test_none_text_abstains(self) -> None:
        r = verify_ill_posed(None)  # type: ignore[arg-type]
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unparseable_problem")

    def test_unrelated_math_abstains(self) -> None:
        r = verify_ill_posed("expand (x+1)^2")
        self.assertEqual(r.verdict, "abstain")

    def test_tier_label_is_correct(self) -> None:
        r = verify_ill_posed("x + y = 3, x + y = 5")
        self.assertEqual(r.tier, "ill-posedness-detector")


class ClaimCeilingTests(unittest.TestCase):
    """The claim ceiling is frozen on every result, in every branch."""

    def test_ceiling_constants(self) -> None:
        self.assertTrue(CLAIM_CEILING["candidateOnly"])
        self.assertFalse(CLAIM_CEILING["canClaimAGI"])

    def test_to_dict_preserves_ceiling_on_accept(self) -> None:
        d = verify_ill_posed("solve for x: 2*x = 4").to_dict()
        self.assertTrue(d["candidateOnly"])
        self.assertFalse(d["canClaimAGI"])
        self.assertEqual(d["tier"], "ill-posedness-detector")

    def test_to_dict_preserves_ceiling_on_abstain(self) -> None:
        d = verify_ill_posed("this sentence is false").to_dict()
        self.assertTrue(d["candidateOnly"])
        self.assertFalse(d["canClaimAGI"])

    def test_result_is_frozen(self) -> None:
        r = verify_ill_posed("solve for x: 2*x = 4")
        with self.assertRaises(Exception):
            r.verdict = "rejected"  # type: ignore[misc]


class SafeParseTests(unittest.TestCase):
    """The safe-parse grammar never evaluates user input."""

    def test_call_syntax_is_rejected_by_grammar(self) -> None:
        # The restricted AST grammar rejects Call / Attribute / dunder nodes
        # outright — user input is parsed, never evaluated.
        import sympy as sp

        from v2.verify_ill_posed import _safe_sympy_expression

        for malicious in [
            "__import__('os')",
            "os.system('rm -rf')",
            "open('x')",
            "x.__class__",
        ]:
            with self.assertRaises(
                ValueError,
                msg=f"grammar must reject {malicious!r}",
            ):
                _safe_sympy_expression(malicious, sp)

    def test_user_input_with_dunder_not_executed(self) -> None:
        # A malicious-looking equation must not raise or execute.
        r = verify_ill_posed("x = x.__class__")
        self.assertEqual(r.verdict, "abstain")

    def test_safe_parse_accepts_plain_linear_expression(self) -> None:
        import sympy as sp

        from v2.verify_ill_posed import _safe_sympy_expression

        expr = _safe_sympy_expression("x + y - 3", sp)
        self.assertEqual(len(expr.free_symbols), 2)


@unittest.skipUnless(_sympy_available(), "SymPy not installed; algebraic tier abstains")
class SymPyDependentTests(unittest.TestCase):
    """Extra coverage that depends on SymPy being present."""

    def test_contradictory_nonlinear_via_abstain(self) -> None:
        # Non-linear contradictory systems may parse but are out of linsolve's
        # linear scope → must fall through to fail-closed abstention (never
        # accepted, never silently 'solved').
        r = verify_ill_posed("solve for x: x*x = 1, x*x = 2")
        self.assertNotEqual(r.verdict, "accepted")


if __name__ == "__main__":
    unittest.main()
