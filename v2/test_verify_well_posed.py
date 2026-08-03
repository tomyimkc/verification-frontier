#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Tests for the deterministic well-posedness CONFIRMATION tier.

This tier is the narrow, fail-closed complement to ``v2.verify_ill_posed``: it
CONFIRMS well-posedness (returns ``accepted``) only for the two specific shapes
the false-alarm audit needs -- a uniquely-solvable linear system, or a simple
closed-form ``What is <arithmetic>?`` prompt. Everything else abstains.

These tests assert INSTRUMENT properties of the deterministic detector, NOT any
model capability.
"""
from __future__ import annotations

import unittest

from v2.verify_well_posed import (
    CLAIM_CEILING,
    WellPosedResult,
    _normalize_caret,
    _safe_arithmetic,
    _sympy_available,
    verify_well_posed,
)


class UniqueLinearSystemTests(unittest.TestCase):
    """Confirmation detector 1: exactly-determined, uniquely-solvable systems."""

    def test_two_by_two_unique_accepted(self) -> None:
        r = verify_well_posed("Solve: x + y = 3, x - y = 1")
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "unique_linear_system")

    def test_solve_for_prefix_accepted(self) -> None:
        r = verify_well_posed("solve for x: 2*x = 4")
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "unique_linear_system")

    def test_solve_the_system_phrasing_accepted(self) -> None:
        r = verify_well_posed(
            "Solve the system: x + y + z = 6, x - y = 0, y - z = 0"
        )
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "unique_linear_system")

    def test_single_variable_linear_accepted(self) -> None:
        r = verify_well_posed("solve for n: 3*n = 15")
        self.assertEqual(r.verdict, "accepted")

    def test_reason_mentions_unique_solution(self) -> None:
        r = verify_well_posed("Solve: x + y = 3, x - y = 1")
        self.assertIn("unique solution", r.reason.lower())

    def test_underdetermined_not_confirmed(self) -> None:
        # 2 unknowns, 1 equation -> infinitely many solutions -> NOT confirmed.
        r = verify_well_posed("solve for x: x + y = 5")
        self.assertNotEqual(r.verdict, "accepted")
        self.assertEqual(r.verdict, "abstain")

    def test_overdetermined_unique_still_accepted(self) -> None:
        # 2 equations, 1 unknown, consistent -> unique -> accepted (N==N check
        # is on independent equations; a redundant third equation of the same
        # unknown still yields a single solution).
        r = verify_well_posed("Solve: 2*x = 6")
        self.assertEqual(r.verdict, "accepted")

    def test_contradictory_system_not_confirmed(self) -> None:
        # No solution -> ill-posed, not this tier's job -> abstain.
        r = verify_well_posed("Solve: x + y = 3, x + y = 5")
        self.assertNotEqual(r.verdict, "accepted")

    def test_nonlinear_system_not_confirmed(self) -> None:
        # linsolve's linear scope; a quadratic system is out of coverage.
        r = verify_well_posed("Solve: x*x = 4")
        self.assertNotEqual(r.verdict, "accepted")

    def test_system_without_solve_intent_abstains(self) -> None:
        # No "solve" intent -> cannot confirm, even if a system is present.
        r = verify_well_posed("x + y = 3, x - y = 1")
        self.assertEqual(r.verdict, "abstain")


class SimpleArithmeticTests(unittest.TestCase):
    """Confirmation detector 2: ``What is <closed-form>?``."""

    def test_basic_addition_accepted(self) -> None:
        r = verify_well_posed("What is 2 + 2?")
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "simple_arithmetic")

    def test_basic_multiplication_accepted(self) -> None:
        r = verify_well_posed("What is 7 * 6?")
        self.assertEqual(r.verdict, "accepted")

    def test_without_question_mark_accepted(self) -> None:
        r = verify_well_posed("What is 2 + 2")
        self.assertEqual(r.verdict, "accepted")

    def test_lowercase_what_is_accepted(self) -> None:
        r = verify_well_posed("what is 3 * 4?")
        self.assertEqual(r.verdict, "accepted")

    def test_power_with_caret_accepted(self) -> None:
        # Caret is the documented input form for powers across this package.
        r = verify_well_posed("What is 2 ^ 3?")
        self.assertEqual(r.verdict, "accepted")

    def test_subtraction_and_division_accepted(self) -> None:
        r = verify_well_posed("What is 10 - 4?")
        self.assertEqual(r.verdict, "accepted")
        r2 = verify_well_posed("What is 12 / 4?")
        self.assertEqual(r2.verdict, "accepted")

    def test_reason_mentions_closed_form(self) -> None:
        r = verify_well_posed("What is 2 + 2?")
        self.assertIn("closed form", r.reason.lower())

    def test_wordy_arithmetic_not_confirmed(self) -> None:
        # "integer square root of 144" is not a closed-form arithmetic expr.
        r = verify_well_posed("What is the integer square root of 144?")
        self.assertEqual(r.verdict, "abstain")

    def test_count_question_not_confirmed(self) -> None:
        # "How many primes ..." is a word problem, not arithmetic.
        r = verify_well_posed("How many prime numbers are there between 1 and 10?")
        self.assertEqual(r.verdict, "abstain")

    def test_arithmetic_with_variable_not_confirmed(self) -> None:
        # A free symbol disqualifies the body from being closed-form arithmetic.
        r = verify_well_posed("What is x + 2?")
        self.assertEqual(r.verdict, "abstain")

    def test_open_question_with_what_is_not_confirmed(self) -> None:
        r = verify_well_posed("What is the meaning of life?")
        self.assertEqual(r.verdict, "abstain")


class FailClosedTests(unittest.TestCase):
    """Anything this tier cannot PROVE well-posed abstains (never a guess)."""

    def test_physics_word_problem_abstains(self) -> None:
        r = verify_well_posed(
            "An object falls from rest for 1 s under g = 9.8 m/s^2. "
            "What is its speed?"
        )
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unsupported_specification")

    def test_symbolic_expand_abstains(self) -> None:
        r = verify_well_posed("Expand (x+1)^2.")
        self.assertEqual(r.verdict, "abstain")

    def test_symbolic_factor_abstains(self) -> None:
        r = verify_well_posed("Factor x^2-1.")
        self.assertEqual(r.verdict, "abstain")

    def test_symbolic_simplify_abstains(self) -> None:
        r = verify_well_posed("Simplify (n+2)*(n+1).")
        self.assertEqual(r.verdict, "abstain")

    def test_paradox_abstains(self) -> None:
        # This tier confirms well-posedness; a paradox is out of coverage.
        r = verify_well_posed("this sentence is false")
        self.assertEqual(r.verdict, "abstain")

    def test_empty_text_abstains(self) -> None:
        r = verify_well_posed("")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unparseable_problem")

    def test_none_text_abstains(self) -> None:
        r = verify_well_posed(None)  # type: ignore[arg-type]
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unparseable_problem")

    def test_tier_label_is_correct(self) -> None:
        r = verify_well_posed("What is 2 + 2?")
        self.assertEqual(r.tier, "well-posedness-detector")

    def test_rejected_is_never_returned(self) -> None:
        # This tier confirms; it never refutes. No input yields "rejected".
        for txt in [
            "What is 2 + 2?",
            "Expand (x+1)^2.",
            "Solve: x + y = 3, x + y = 5",
            "this sentence is false",
            "",
        ]:
            self.assertNotEqual(verify_well_posed(txt).verdict, "rejected", txt)


class TaskObjectCoercionTests(unittest.TestCase):
    """The same task-object shapes ``verify_ill_posed`` accepts."""

    def test_dict_with_prompt_key(self) -> None:
        r = verify_well_posed({"task_id": "t1", "prompt": "What is 2 + 2?"})
        self.assertEqual(r.verdict, "accepted")

    def test_dict_with_description_key(self) -> None:
        r = verify_well_posed({"description": "What is 7 * 6?"})
        self.assertEqual(r.verdict, "accepted")

    def test_object_with_prompt_attribute(self) -> None:
        class _T:
            def __init__(self, p: str) -> None:
                self.prompt = p

        r = verify_well_posed(_T("What is 2 + 2?"))
        self.assertEqual(r.verdict, "accepted")

    def test_empty_dict_abstains(self) -> None:
        r = verify_well_posed({})
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unparseable_problem")


class FalseAlarmAuditCoverageTests(unittest.TestCase):
    """The exact control items the false-alarm audit plants.

    This tier must CONFIRM (accept) the closed-form arithmetic controls and
    abstain on the rest. It is intentionally narrow -- the gap it closes is the
    arithmetic subset; physics / symbolic-math word problems remain abstained
    until a broader confirmation tier exists.
    """

    @classmethod
    def setUpClass(cls) -> None:
        # Late import so this test module is importable even if the parallel
        # build_ill_posed_audit dependencies are rearranged.
        from v2.build_ill_posed_audit import well_posed_controls

        cls.controls = {(c.control_id, c.prompt, c.domain) for c in well_posed_controls()}

    def _verdict_for(self, prompt: str) -> str:
        return verify_well_posed({"prompt": prompt}).verdict

    def test_arithmetic_closed_form_controls_confirmed(self) -> None:
        # wp-ari-01 / wp-ari-02 are the only controls in this tier's scope.
        self.assertEqual(self._verdict_for("What is 2 + 2?"), "accepted")
        self.assertEqual(self._verdict_for("What is 7 * 6?"), "accepted")

    def test_wordy_arithmetic_controls_abstain(self) -> None:
        # wp-ari-03 / wp-ari-04 are word problems -- no closed form -> abstain.
        self.assertEqual(self._verdict_for("What is the integer square root of 144?"), "abstain")
        self.assertEqual(
            self._verdict_for("How many prime numbers are there between 1 and 10?"),
            "abstain",
        )

    def test_all_physics_and_symbolic_controls_abstain(self) -> None:
        # Free-text physics / symbolic expand-factor-simplify are out of scope.
        for prompt, _domain in [
            ("An object falls from rest for 1 s under g = 9.8 m/s^2. What is its speed?", "physics"),
            ("A 2 kg object moves at 3 m/s. What is its kinetic energy?", "physics"),
            ("A force of 5 N acts on a 1 kg mass. What is the acceleration?", "physics"),
            ("Expand (x+1)^2.", "math"),
            ("Factor x^2-1.", "math"),
            ("Simplify (n+2)*(n+1).", "math"),
        ]:
            self.assertEqual(
                self._verdict_for(prompt),
                "abstain",
                f"expected abstain for {_domain} control: {prompt!r}",
            )

    def test_no_control_is_ever_rejected(self) -> None:
        for _cid, prompt, _domain in self.controls:
            self.assertNotEqual(self._verdict_for(prompt), "rejected")


class ClaimCeilingTests(unittest.TestCase):
    """The claim ceiling is frozen on every result, in every branch."""

    def test_ceiling_constants(self) -> None:
        self.assertTrue(CLAIM_CEILING["candidateOnly"])
        self.assertFalse(CLAIM_CEILING["canClaimAGI"])
        self.assertFalse(CLAIM_CEILING["winnerLevelEligible"])

    def test_to_dict_preserves_ceiling_on_accept(self) -> None:
        d = verify_well_posed("What is 2 + 2?").to_dict()
        self.assertTrue(d["candidateOnly"])
        self.assertFalse(d["canClaimAGI"])
        self.assertEqual(d["tier"], "well-posedness-detector")

    def test_to_dict_preserves_ceiling_on_abstain(self) -> None:
        d = verify_well_posed("Expand (x+1)^2.").to_dict()
        self.assertTrue(d["candidateOnly"])
        self.assertFalse(d["canClaimAGI"])

    def test_result_is_frozen(self) -> None:
        r = verify_well_posed("What is 2 + 2?")
        with self.assertRaises(Exception):
            r.verdict = "rejected"  # type: ignore[misc]


class SafeParseTests(unittest.TestCase):
    """The restricted grammar never evaluates user input."""

    def test_call_syntax_rejected_by_grammar(self) -> None:
        import sympy as sp
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
                _safe_arithmetic(malicious, sp)

    def test_malicious_arithmetic_prompt_does_not_execute(self) -> None:
        # A malicious-looking "what is" prompt must not raise or execute.
        r = verify_well_posed("What is __import__('os').system('rm -rf')?")
        self.assertEqual(r.verdict, "abstain")

    def test_normalize_caret(self) -> None:
        self.assertEqual(_normalize_caret("2^3"), "2**3")
        self.assertEqual(_normalize_caret("x^2+1"), "x**2+1")
        self.assertEqual(_normalize_caret("plain"), "plain")

    def test_safe_arithmetic_rejects_free_symbol(self) -> None:
        import sympy as sp
        # 'x + 2' carries a Name node the arithmetic grammar rejects outright
        # (a free symbol can never be a closed-form arithmetic value). The
        # caller (_confirm_simple_arithmetic) catches this and abstains.
        with self.assertRaises(ValueError):
            _safe_arithmetic("x + 2", sp)

    def test_safe_arithmetic_rejects_free_symbol_at_caller(self) -> None:
        # The end-to-end contract: a "What is x + 2?" prompt abstains rather
        # than propagating the grammar rejection.
        self.assertEqual(verify_well_posed("What is x + 2?").verdict, "abstain")

    def test_safe_arithmetic_accepts_closed_form(self) -> None:
        import sympy as sp
        self.assertEqual(_safe_arithmetic("2 + 2", sp), sp.Integer(4))
        self.assertEqual(_safe_arithmetic("7 * 6", sp), sp.Integer(42))


@unittest.skipUnless(_sympy_available(), "SymPy not installed; confirmation tier abstains")
class SymPyDependentTests(unittest.TestCase):
    """Extra coverage that depends on SymPy being present."""

    def test_large_linear_system_accepted(self) -> None:
        r = verify_well_posed(
            "Solve: a + b + c + d = 10, a - b = 0, b - c = 0, c - d = 0"
        )
        self.assertEqual(r.verdict, "accepted")
        self.assertEqual(r.reason_code, "unique_linear_system")

    def test_arithmetic_with_parentheses_accepted(self) -> None:
        r = verify_well_posed("What is (2 + 3) * 4?")
        self.assertEqual(r.verdict, "accepted")

    def test_result_type_is_wellposed_result(self) -> None:
        self.assertIsInstance(verify_well_posed("What is 2 + 2?"), WellPosedResult)
        self.assertIsInstance(verify_well_posed("nonsense"), WellPosedResult)


if __name__ == "__main__":
    unittest.main()
