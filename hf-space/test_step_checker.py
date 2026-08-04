#!/usr/bin/env python3
"""Regression tests for the demo's step-level checker and answer extraction.

Every case here corresponds to a defect that was live in the deployed Space:

* a **false pass** — a flat 1% relative tolerance accepted
  ``500 * 4.18 * 60 = 125000`` (true 125400, error 400). A silent pass is the one
  outcome this project exists to prevent.
* **crashes** on ordinary physics variable names, because ``sympify`` resolves
  ``Q``/``N``/``S``/``gamma`` to non-expression sympy singletons that have no
  ``.free_symbols``. The Space ships a Lorentz-factor (γ) challenge.
* **blanket abstention** on any step carrying a unit, which made the step column
  useless on realistic model output.
* **answer extraction** failing on prose that spells unit names out.

Run:  python3 -m unittest test_step_checker -v      (needs sympy)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import sympy  # noqa: F401
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("sympy required for the symbolic step checker")

from step_checker import check_step, check_steps, summarize, ERROR, VERIFIED, UNCHECKED
import app


def _verdicts(text: str):
    from app import _split_steps, _strip_trailing_units

    return check_steps([_strip_trailing_units(s) for s in _split_steps(text)])


class NoSilentPass(unittest.TestCase):
    """Wrong arithmetic must never come back verified."""

    def test_heat_capacity_error_is_caught(self) -> None:
        # 500 * 4.18 * 60 = 125400, not 125000. Error of 400 sits inside 1% of a
        # six-figure number, which the old flat tolerance accepted.
        v = _verdicts("1. Q = 500 * 4.18 * 60 = 125000 J")
        self.assertEqual(v[0].verdict, ERROR, v[0].summary)

    def test_momentum_error_is_caught(self) -> None:
        v = _verdicts("1. p = 3*4 = 12 kg*m/s\n2. v = 12 / 5 = 2.6 m/s")
        self.assertEqual(v[1].verdict, ERROR, v[1].summary)

    def test_power_error_is_caught(self) -> None:
        v = _verdicts("1. P = 2**2 * 10 = 45 W")
        self.assertEqual(v[0].verdict, ERROR, v[0].summary)

    def test_correct_arithmetic_verifies(self) -> None:
        v = _verdicts("1. p = 3*4 = 12 kg*m/s\n2. v = 12 / 5 = 2.4 m/s")
        self.assertTrue(all(x.verdict == VERIFIED for x in v), [x.summary for x in v])

    def test_heat_capacity_correct_verifies(self) -> None:
        v = _verdicts("1. Q = 500 * 4.18 * 60 = 125400 J")
        self.assertEqual(v[0].verdict, VERIFIED, v[0].summary)


class RoundingAbstainsRatherThanGuessing(unittest.TestCase):
    """A rounded presentation is neither a pass nor an error."""

    def test_rounded_value_is_unchecked_not_error(self) -> None:
        # 1/0.6 = 1.66667; written to 3 decimals as 1.667. The difference is
        # smaller than the written precision can express, so we must not call it
        # an error — and must not call it verified either.
        v = _verdicts("1. gam = 1 / 0.6 = 1.667")
        self.assertEqual(v[0].verdict, UNCHECKED, v[0].summary)

    def test_rounding_allowance_does_not_swallow_a_real_error(self) -> None:
        # 2.6 vs 2.4 is far larger than one unit in the last written decimal.
        v = _verdicts("1. v = 12 / 5 = 2.6")
        self.assertEqual(v[0].verdict, ERROR, v[0].summary)


class SympyNameCollisionsDoNotCrash(unittest.TestCase):
    """Physics variable names that sympify to non-expressions must fail closed."""

    NAMES = ["Q", "N", "S", "O", "beta", "gamma", "E", "I", "C", "T", "W", "V"]

    def test_no_crash_on_reserved_names(self) -> None:
        for name in self.NAMES:
            with self.subTest(name=name):
                try:
                    verdict = check_step(f"{name} = 2 * 3 = 6", index=0)
                except Exception as exc:  # pragma: no cover
                    self.fail(f"{name!r} raised {type(exc).__name__}: {exc}")
                self.assertIn(verdict.verdict, (VERIFIED, ERROR, UNCHECKED))

    def test_lorentz_gamma_step_does_not_crash(self) -> None:
        # The Space ships a Lorentz-factor challenge, so gamma is reachable.
        report = app.render_step_report("1. gamma = 1 / 0.6 = 1.6667")
        self.assertIsInstance(report, str)
        self.assertTrue(report.strip())


class UnitsDoNotBlockChecking(unittest.TestCase):
    """A trailing unit must not make every realistic step unchecked."""

    def test_unit_bearing_step_is_still_decided(self) -> None:
        v = _verdicts("1. v = 12 / 5 = 2.4 m/s")
        self.assertEqual(v[0].verdict, VERIFIED, v[0].summary)

    def test_velocity_variable_is_not_read_as_the_volt_unit(self) -> None:
        # Stripping units case-insensitively turned "v = ..." into "= ...".
        from app import _strip_trailing_units

        self.assertIn("v", _strip_trailing_units("v = 12 / 5 = 2.4 m/s"))

    def test_compound_unit_is_stripped(self) -> None:
        from app import _strip_trailing_units

        self.assertEqual(_strip_trailing_units("p = 3*4 = 12 kg*m/s").split("=")[-1].strip(), "12")


class AnswerExtraction(unittest.TestCase):
    """Extraction must survive prose that spells unit names out."""

    def test_spelled_out_units_are_extracted(self) -> None:
        self.assertEqual(app._extract("The final velocity is 2.4 meters per second.", "si"), "2.4 m/s")

    def test_joules_spelled_out(self) -> None:
        self.assertEqual(app._extract("Total energy is 125400 joules.", "si"), "125400 J")

    def test_symbol_form_still_works(self) -> None:
        self.assertEqual(app._extract("Therefore v = 2.4 m/s", "si"), "2.4 m/s")


class ReportRendering(unittest.TestCase):
    def test_report_names_the_first_failing_step(self) -> None:
        report = app.render_step_report(
            "1. p = 3*4 = 12 kg*m/s\n2. m = 3 + 2 = 5 kg\n3. v = 12 / 5 = 2.6 m/s"
        )
        self.assertIn("First error at step 3", report)

    def test_report_shows_the_step_as_written(self) -> None:
        # The unit-stripped form is used for checking only; the UI echoes the
        # model's own text.
        report = app.render_step_report("1. v = 12 / 5 = 2.4 m/s")
        self.assertIn("2.4 m/s", report)

    def test_empty_input_is_handled(self) -> None:
        self.assertIsInstance(app.render_step_report(""), str)

    def test_unchecked_is_never_described_as_a_pass(self) -> None:
        report = app.render_step_report("1. The cart is heavy.\n2. Therefore it is slow.")
        self.assertIn("not** a pass", report)


if __name__ == "__main__":
    unittest.main()
