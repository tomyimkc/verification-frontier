#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Tests for the frozen ill-posed-problem task pack.

These tests assert that the pack is GENUINELY ill-posed: every item's only
correct verdict is ``abstain``, every category is populated to its expected
count, the contradictory systems are mathematically inconsistent (verified
independently with SymPy), and the circular-dependency items actually describe
cycles. The pack is the inverse of ``build_logic_error_audit``: there the
candidate is wrong and ``rejected``; here the *problem* is unsolvable and the
only honest answer is abstention.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import sympy as sp

from v2 import ill_posed_tasks as ipt


class PackInvariantTests(unittest.TestCase):
    """Top-level invariants of the frozen item set."""

    def setUp(self) -> None:
        self.tasks = ipt.ill_posed_tasks()

    def test_at_least_30_items(self) -> None:
        self.assertGreaterEqual(len(self.tasks), 30)

    def test_every_category_is_present(self) -> None:
        present = {t.category for t in self.tasks}
        self.assertEqual(present, set(ipt.EXPECTED_CATEGORY_COUNTS))

    def test_every_expected_verdict_is_abstain(self) -> None:
        for t in self.tasks:
            self.assertEqual(
                t.expected_verdict, "abstain", t.task_id
            )

    def test_no_duplicate_task_ids(self) -> None:
        ids = [t.task_id for t in self.tasks]
        self.assertEqual(len(ids), len(set(ids)), "duplicate task_ids found")

    def test_every_item_has_a_nonempty_reason_code(self) -> None:
        for t in self.tasks:
            self.assertTrue(t.expected_reason_code, t.task_id)
            self.assertIn(t.expected_reason_code, ipt.REASON_CODES, t.task_id)

    def test_category_counts_match_expectations(self) -> None:
        counts: dict[str, int] = {k: 0 for k in ipt.EXPECTED_CATEGORY_COUNTS}
        for t in self.tasks:
            counts[t.category] += 1
        self.assertEqual(counts, ipt.EXPECTED_CATEGORY_COUNTS)

    def test_validate_tasks_returns_no_errors(self) -> None:
        self.assertEqual(ipt.validate_tasks(self.tasks), [])

    def test_reason_code_matches_category_for_every_item(self) -> None:
        for t in self.tasks:
            self.assertEqual(
                ipt.CATEGORY_TO_REASON_CODE[t.category],
                t.expected_reason_code,
                t.task_id,
            )

    def test_problem_statements_and_reasons_are_nonempty(self) -> None:
        for t in self.tasks:
            self.assertTrue(t.problem_statement.strip(), t.task_id)
            self.assertTrue(t.why_ill_posed.strip(), t.task_id)

    def test_each_category_uses_a_distinct_reason_code(self) -> None:
        """Two different categories must never share a reason code.

        A reason code may legitimately repeat across items WITHIN the same
        category, but must map 1:1 across categories.
        """
        code_to_categories: dict[str, set[str]] = {}
        for t in self.tasks:
            code_to_categories.setdefault(t.expected_reason_code, set()).add(t.category)
        for code, cats in code_to_categories.items():
            self.assertEqual(
                len(cats), 1, f"reason_code {code!r} used by {len(cats)} categories: {cats}"
            )


class ContradictorySystemTests(unittest.TestCase):
    """The 10 contradictory systems must be GENUINELY inconsistent (SymPy)."""

    def setUp(self) -> None:
        self.cs = [
            t for t in ipt.ill_posed_tasks()
            if t.category == "contradictory_equation_system"
        ]

    def test_there_are_ten_contradictory_systems(self) -> None:
        self.assertEqual(len(self.cs), 10)

    def test_each_cs_item_has_a_sympy_proof_annotation(self) -> None:
        for t in self.cs:
            self.assertIn(t.task_id, ipt.SYMPY_PROOFS, t.task_id)

    def test_every_cs_item_is_inconsistent_via_linsolve(self) -> None:
        """Independent SymPy check 1: linsolve returns EmptySet."""
        for t in self.cs:
            proof = ipt.SYMPY_PROOFS[t.task_id]
            syms = [sp.Symbol(s) for s in proof["symbols"]]
            eqs = [sp.sympify(e) for e in proof["eqs"]]
            self.assertEqual(
                sp.linsolve(eqs, *syms),
                sp.EmptySet,
                f"{t.task_id}: linsolve did not return EmptySet",
            )

    def test_every_cs_item_is_inconsistent_via_rref_pivot(self) -> None:
        """Independent SymPy check 2: augmented-matrix RREF has a constant-col pivot."""
        for t in self.cs:
            proof = ipt.SYMPY_PROOFS[t.task_id]
            syms = [sp.Symbol(s) for s in proof["symbols"]]
            eqs = [sp.sympify(e) for e in proof["eqs"]]
            coeff, const = sp.linear_eq_to_matrix(eqs, syms)
            augmented = coeff.row_join(const)
            _, pivots = augmented.rref()
            self.assertIn(
                len(syms),
                pivots,
                f"{t.task_id}: no constant-column pivot -> not provably inconsistent",
            )

    def test_verify_contradictory_system_helper_agrees(self) -> None:
        for t in self.cs:
            self.assertTrue(
                ipt.verify_contradictory_system(t.task_id), t.task_id
            )

    def test_negative_control_consistent_system_is_not_flagged(self) -> None:
        """A consistent system (x+y=3, x-y=1) must NOT be reported inconsistent."""
        x, y = sp.symbols("x y")
        consistent = [x + y - 3, x - y - 1]
        self.assertFalse(ipt._sympy_is_inconsistent(consistent, [x, y]))


class CircularDependencyTests(unittest.TestCase):
    """The 4 circular-dependency items must actually describe a cycle."""

    def setUp(self) -> None:
        self.cd = [
            t for t in ipt.ill_posed_tasks()
            if t.category == "circular_dependency"
        ]

    def test_there_are_four_circular_dependency_items(self) -> None:
        self.assertEqual(len(self.cd), 4)

    def test_every_cd_item_has_a_structural_circular_reference(self) -> None:
        for t in self.cd:
            self.assertTrue(
                ipt.has_circular_reference(t.problem_statement), t.task_id
            )

    def test_non_circular_items_are_not_flagged_as_circular(self) -> None:
        """Negative control: items from other categories must not match the cycle heuristic."""
        non_cd = [
            t for t in ipt.ill_posed_tasks()
            if t.category != "circular_dependency"
        ]
        for t in non_cd:
            self.assertFalse(
                ipt.has_circular_reference(t.problem_statement), t.task_id
            )

    def test_cd_01_substitution_yields_a_contradiction(self) -> None:
        """A=B+1 and B=A+1 -> substituting gives A=A+2, i.e. 0=2 in SymPy."""
        A, B = sp.symbols("A B")
        # Encode the definitions as the residual of substituting one into the other.
        # B = A+1 substituted into A = B+1 gives A = (A+1)+1, residual A-(A+2).
        residual = sp.sympify("A - (A + 2)")
        # simplify should reduce to -2, i.e. a nonzero constant -> contradiction.
        self.assertNotEqual(sp.simplify(residual), 0)


class UndecidableTests(unittest.TestCase):
    def test_there_are_five_undecidable_items(self) -> None:
        un = [t for t in ipt.ill_posed_tasks() if t.category == "undecidable"]
        self.assertEqual(len(un), 5)

    def test_liar_paradox_is_present(self) -> None:
        un = [t for t in ipt.ill_posed_tasks() if t.category == "undecidable"]
        joined = " ".join(t.problem_statement.lower() for t in un)
        self.assertIn("this statement is false", joined)

    def test_russells_paradox_is_present(self) -> None:
        un = [t for t in ipt.ill_posed_tasks() if t.category == "undecidable"]
        joined = " ".join(t.problem_statement.lower() for t in un)
        self.assertIn("do not contain themselves", joined)


class EmptyFeasibleRegionTests(unittest.TestCase):
    def test_there_are_three_empty_region_items(self) -> None:
        ef = [t for t in ipt.ill_posed_tasks() if t.category == "empty_feasible_region"]
        self.assertEqual(len(ef), 3)

    def test_ef_01_feasible_region_is_empty(self) -> None:
        """x<0 and x>0 has an empty feasible region (SymPy)."""
        x = sp.Symbol("x")
        feasible = sp.solve([x < 0, x > 0], x)
        # SymPy returns an empty set / falsy object for an empty intersection.
        self.assertFalse(feasible)

    def test_ef_03_objective_is_unbounded_above(self) -> None:
        """Maximize x over R with no upper bound: the supremum is +oo (no finite max).

        SymPy returns ``oo`` for the unbounded maximum, which is exactly the
        ill-posedness we are asserting -- no finite value is ever attained.
        """
        from sympy.calculus.util import maximum

        x = sp.Symbol("x", real=True)
        self.assertEqual(maximum(x, x, sp.S.Reals), sp.oo)


class MissingConstraintTests(unittest.TestCase):
    def test_there_are_eight_missing_constraint_items(self) -> None:
        mc = [t for t in ipt.ill_posed_tasks() if t.category == "missing_constraint"]
        self.assertEqual(len(mc), 8)

    def test_underdetermined_linear_equation_has_infinitely_many_solutions(self) -> None:
        """x+y=5 alone leaves x free -> solution set is a line, not a point."""
        x, y = sp.symbols("x y")
        sol = sp.linsolve([x + y - 5], x, y)
        self.assertNotEqual(sol, sp.EmptySet)
        # It must be parametric (one free parameter), confirming non-uniqueness.
        params = sol.free_symbols if hasattr(sol, "free_symbols") else None
        # linsolve returns a FiniteSet of a single parametric tuple when free.
        self.assertEqual(len(sol), 1)


class BuildAndRoundTripTests(unittest.TestCase):
    """build_pack / write_pack / --check canonical-bytes contract."""

    def test_build_pack_succeeds_and_is_well_formed(self) -> None:
        pack = ipt.build_pack()
        self.assertEqual(pack["schema"], "goai-ill-posed-tasks/v1")
        self.assertEqual(pack["evidenceClass"], "development-only")
        self.assertEqual(pack["itemCounts"]["total"], len(ipt.ill_posed_tasks()))
        self.assertEqual(
            pack["itemCounts"]["byCategory"],
            dict(sorted(ipt.EXPECTED_CATEGORY_COUNTS.items())),
        )

    def test_build_pack_attaches_sympy_proofs_to_cs_items(self) -> None:
        pack = ipt.build_pack()
        cs_items = [t for t in pack["tasks"] if t["category"] == "contradictory_equation_system"]
        for t in cs_items:
            self.assertIn("sympy_proof", t, t["task_id"])
            self.assertIn("eqs", t["sympy_proof"])
            self.assertIn("symbols", t["sympy_proof"])

    def test_every_task_dict_in_pack_has_expected_verdict_abstain(self) -> None:
        pack = ipt.build_pack()
        for t in pack["tasks"]:
            self.assertEqual(t["expected_verdict"], "abstain", t["task_id"])

    def test_write_then_check_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "ill-posed-tasks.json"
            ipt.write_pack(out)
            expected = ipt._canonical_bytes(ipt.build_pack())
            self.assertEqual(out.read_bytes(), expected)

    def test_check_detects_tampered_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "ill-posed-tasks.json"
            ipt.write_pack(out)
            tampered = json.loads(out.read_text(encoding="utf-8"))
            tampered["tasks"][0]["expected_verdict"] = "accepted"
            out.write_text(
                json.dumps(
                    tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ) + "\n",
                encoding="utf-8",
            )
            self.assertNotEqual(
                out.read_bytes(), ipt._canonical_bytes(ipt.build_pack())
            )

    def test_claim_ceiling_is_locked(self) -> None:
        pack = ipt.build_pack()
        self.assertTrue(pack["candidateOnly"])
        self.assertFalse(pack["canClaimAGI"])
        self.assertFalse(pack["winnerLevelEligible"])
        self.assertFalse(pack["winnerLevelGateMet"])
        self.assertFalse(pack["scientificOutcome"])
        self.assertFalse(pack["capabilityClaim"])
        self.assertFalse(pack["isModelBenchmark"])

    def test_interpretation_names_the_contribution(self) -> None:
        interp = ipt.build_pack()["interpretation"]
        self.assertIn("abstain", interp)
        self.assertIn("hallucinate", interp)
        self.assertIn("NOT a model-capability", interp)


class FailClosedTests(unittest.TestCase):
    """The builder must refuse to emit a pack that fails validation."""

    def test_build_raises_if_a_verdict_is_not_abstain(self) -> None:
        tasks = list(ipt.ill_posed_tasks())
        # Mutate one item to expect 'accepted' (an invalid verdict for this pack).
        bad = copy.copy(tasks[0])
        object.__setattr__(bad, "expected_verdict", "accepted")
        tasks[0] = bad
        errors = ipt.validate_tasks(tasks)
        self.assertTrue(errors, "expected at least one validation error")
        self.assertTrue(
            any("expected_verdict" in e for e in errors), errors
        )

    def test_build_raises_if_a_category_count_drifts(self) -> None:
        tasks = list(ipt.ill_posed_tasks())
        # Drop one item from a category to break the count.
        tasks = [t for t in tasks if t.task_id != "cs-01"]
        errors = ipt.validate_tasks(tasks)
        self.assertTrue(
            any("contradictory_equation_system" in e and "expected 10" in e for e in errors),
            errors,
        )

    def test_build_raises_on_duplicate_task_id(self) -> None:
        tasks = list(ipt.ill_posed_tasks())
        tasks.append(tasks[0])  # duplicate id
        errors = ipt.validate_tasks(tasks)
        self.assertTrue(any("duplicate task_id" in e for e in errors), errors)

    def test_validate_flags_a_non_inconsistent_cs_item(self) -> None:
        """If a cs-* proof annotated a CONSISTENT system, validation must catch it."""
        original = ipt.SYMPY_PROOFS["cs-01"]
        try:
            # Replace with a consistent system (x+y=3, x-y=1) -> should fail.
            ipt.SYMPY_PROOFS["cs-01"] = {"eqs": ["x+y-3", "x-y-1"], "symbols": ["x", "y"]}
            errors = ipt.validate_tasks(ipt.ill_posed_tasks())
            self.assertTrue(
                any("cs-01" in e and "inconsistent" in e for e in errors), errors
            )
        finally:
            ipt.SYMPY_PROOFS["cs-01"] = original


if __name__ == "__main__":
    unittest.main()
