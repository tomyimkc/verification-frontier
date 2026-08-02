#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Tests for the deterministic policy-comparison harness.

These tests assert the *policy* properties of the comparison, NOT any model
capability. The proposed-system is the real verifier; the other three policies
are degenerate decision rules.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from v2 import build_baseline_comparison as bc


class ComparisonSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.comparison = bc.build_comparison()

    def test_schema_and_evidence_class(self) -> None:
        self.assertEqual(self.comparison["schema"], "goai-baseline-comparison/v1")
        self.assertEqual(self.comparison["evidenceClass"], "development-only")

    def test_claim_ceiling_is_locked(self) -> None:
        for key in ("candidateOnly", "canClaimAGI", "winnerLevelEligible", "winnerLevelGateMet"):
            self.assertIn(key, self.comparison["claimCeiling"], key)
        self.assertTrue(self.comparison["candidateOnly"])
        self.assertFalse(self.comparison["canClaimAGI"])
        self.assertFalse(self.comparison["winnerLevelEligible"])
        self.assertFalse(self.comparison["winnerLevelGateMet"])
        self.assertFalse(self.comparison["scientificOutcome"])
        self.assertFalse(self.comparison["capabilityClaim"])
        self.assertFalse(self.comparison["isModelBenchmark"])

    def test_interpretation_names_it_as_policy_comparison_not_benchmark(self) -> None:
        interp = self.comparison["interpretation"]
        self.assertIn("DETERMINISTIC policy comparison", interp)
        self.assertIn("NOT a model-capability benchmark", interp)
        self.assertIn("SIMULATED", interp)
        self.assertIn("raw-model", interp)

    def test_all_four_policies_present(self) -> None:
        self.assertEqual(
            set(self.comparison["policies"].keys()),
            {"raw-model", "always-abstain", "always-accept", "proposed-system"},
        )
        self.assertEqual(len(self.comparison["comparisonTable"]), 4)

    def test_comparison_table_has_one_row_per_policy(self) -> None:
        rows = self.comparison["comparisonTable"]
        names = {r["policy"] for r in rows}
        self.assertEqual(names, {"raw-model", "always-abstain", "always-accept", "proposed-system"})
        for r in rows:
            for field in (
                "coverageRate",
                "errorCatchRate",
                "unsafeAcceptances",
                "falseRejections",
                "verdictAccuracy",
            ):
                self.assertIn(field, r, (r["policy"], field))


class ItemSetTests(unittest.TestCase):
    def test_items_are_planted_errors_plus_correct_answers(self) -> None:
        items = bc.comparison_items()
        kinds = {i.kind for i in items}
        self.assertEqual(kinds, {"planted-error", "correct-answer"})
        planted = [i for i in items if i.kind == "planted-error"]
        correct = [i for i in items if i.kind == "correct-answer"]
        # Planted errors come from the shared audit module.
        from v2 import build_logic_error_audit

        self.assertEqual(len(planted), len(build_logic_error_audit.planted_errors()))
        # Every planted error expects to be rejected.
        for i in planted:
            self.assertEqual(i.expected_verdict, "rejected")
        # Every correct answer expects accepted OR (for formal proofs) abstain.
        for i in correct:
            self.assertIn(i.expected_verdict, {"accepted", "abstain"})

    def test_correct_answer_set_covers_all_three_dimensions(self) -> None:
        answers = bc.correct_answers()
        tiers = {a.tier for a in answers}
        self.assertEqual(tiers, {"si", "sympy", "formal-proof"})
        self.assertGreaterEqual(len(answers), 12)

    def test_correct_si_and_sympy_answers_expect_acceptance(self) -> None:
        for a in bc.correct_answers():
            if a.tier in {"si", "sympy"}:
                self.assertEqual(a.expected_verdict, "accepted", a.answer_id)

    def test_correct_formal_proof_answers_expect_abstain(self) -> None:
        """The package does not bundle Lean; honest verdict for a real proof is abstain."""
        lean = [a for a in bc.correct_answers() if a.tier == "formal-proof"]
        self.assertGreaterEqual(len(lean), 2)
        for a in lean:
            self.assertEqual(a.expected_verdict, "abstain", a.answer_id)
            self.assertEqual(a.expected_reason_code, "unsupported_tier", a.answer_id)

    def test_correct_answer_invariants_hold_under_real_verifier(self) -> None:
        """The build-time invariant: the real verifier must produce each correct
        answer's expected verdict. If this fails, the gold-standard row is a lie."""
        for item in bc.comparison_items():
            if item.kind == "correct-answer":
                verdict, reason = bc._proposed_verdict(item)
                self.assertEqual(
                    verdict,
                    item.expected_verdict,
                    f"{item.item_id}: {verdict} != {item.expected_verdict}",
                )


class PolicyBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.comparison = bc.build_comparison()

    def test_raw_model_accepts_everything(self) -> None:
        rm = self.comparison["policies"]["raw-model"]
        self.assertTrue(rm["isSimulatedBaseline"])
        for d in rm["details"]:
            self.assertEqual(d["policy_verdict"], "accepted")
        # High coverage, but accepts ALL planted errors.
        self.assertEqual(rm["rates"]["coverageRate"], 1.0)
        planted = [d for d in rm["details"] if d["kind"] == "planted-error"]
        self.assertEqual(rm["totals"]["unsafeAcceptances"], len(planted))
        self.assertEqual(rm["rates"]["errorCatchRate"], 0.0)

    def test_always_accept_matches_raw_model_outcomes(self) -> None:
        aa = self.comparison["policies"]["always-accept"]
        rm = self.comparison["policies"]["raw-model"]
        self.assertTrue(aa["isSimulatedBaseline"])
        self.assertEqual(aa["totals"], rm["totals"])
        self.assertEqual(aa["rates"], rm["rates"])

    def test_always_abstain_has_zero_coverage_and_zero_unsafe_acceptance(self) -> None:
        abst = self.comparison["policies"]["always-abstain"]
        self.assertTrue(abst["isSimulatedBaseline"])
        self.assertEqual(abst["rates"]["coverageRate"], 0.0)
        self.assertEqual(abst["totals"]["unsafeAcceptances"], 0)
        self.assertEqual(abst["rates"]["errorCatchRate"], 0.0)
        # It abstains even on correct answers -> false_rejections stay 0 because
        # abstain is not a rejection, but verdict_accuracy collapses.
        self.assertEqual(abst["totals"]["falseRejections"], 0)

    def test_proposed_system_is_the_real_verifier(self) -> None:
        proposed = self.comparison["policies"]["proposed-system"]
        self.assertFalse(proposed["isSimulatedBaseline"])
        # Perfect verdict accuracy on this planted+correct set.
        self.assertEqual(proposed["rates"]["verdictAccuracy"], 1.0)
        self.assertEqual(proposed["totals"]["incorrectVerdicts"], 0)
        # Catches every planted error, accepts no planted error.
        self.assertEqual(proposed["rates"]["errorCatchRate"], 1.0)
        self.assertEqual(proposed["totals"]["unsafeAcceptances"], 0)
        # Does not reject any correct answer.
        self.assertEqual(proposed["totals"]["falseRejections"], 0)

    def test_proposed_system_rejects_lean_placeholders_not_abstains(self) -> None:
        """sorry/admit planted errors must be REJECTED before coverage abstention."""
        proposed = self.comparison["policies"]["proposed-system"]
        lean_planted = [
            d
            for d in proposed["details"]
            if d["tier"] == "lean-placeholder" and d["kind"] == "planted-error"
        ]
        self.assertGreaterEqual(len(lean_planted), 2)
        for d in lean_planted:
            self.assertEqual(d["policy_verdict"], "rejected", d["item_id"])
            self.assertEqual(d["reason_code"], "proof_placeholder", d["item_id"])

    def test_proposed_system_accepts_si_and_sympy_correct_answers(self) -> None:
        proposed = self.comparison["policies"]["proposed-system"]
        accepted_si_sym = [
            d
            for d in proposed["details"]
            if d["kind"] == "correct-answer"
            and d["tier"] in {"si", "sympy"}
            and d["policy_verdict"] == "accepted"
        ]
        self.assertGreaterEqual(len(accepted_si_sym), 12)

    def test_proposed_system_abstains_on_valid_formal_proofs(self) -> None:
        """A real proof term must NOT be accepted without a checking certificate;
        the honest verdict is abstain (Lean not bundled)."""
        proposed = self.comparison["policies"]["proposed-system"]
        lean_correct = [
            d
            for d in proposed["details"]
            if d["kind"] == "correct-answer" and d["tier"] == "formal-proof"
        ]
        self.assertGreaterEqual(len(lean_correct), 2)
        for d in lean_correct:
            self.assertEqual(d["policy_verdict"], "abstain", d["item_id"])
            self.assertNotEqual(d["policy_verdict"], "accepted", d["item_id"])


class DominanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.comparison = bc.build_comparison()

    def test_proposed_system_beats_every_baseline_on_joint_axes(self) -> None:
        proposed = self.comparison["policies"]["proposed-system"]
        # The proposed system is the ONLY policy with coverage > 0 AND
        # errorCatchRate == 1.0 AND zero unsafe acceptances.
        self.assertGreater(proposed["rates"]["coverageRate"], 0.0)
        self.assertEqual(proposed["rates"]["errorCatchRate"], 1.0)
        self.assertEqual(proposed["totals"]["unsafeAcceptances"], 0)

        for baseline in ("raw-model", "always-abstain", "always-accept"):
            b = self.comparison["policies"][baseline]
            joint_ok = (
                b["rates"]["coverageRate"] > 0.0
                and b["rates"]["errorCatchRate"] == 1.0
                and b["totals"]["unsafeAcceptances"] == 0
            )
            self.assertFalse(joint_ok, baseline)

    def test_dominance_block_records_failure_axis(self) -> None:
        dom = self.comparison["dominance"]
        self.assertEqual(set(dom.keys()), {"raw-model", "always-abstain", "always-accept"})
        self.assertEqual(dom["raw-model"]["baselineFailsAxis"], "unsafe_acceptance")
        self.assertEqual(dom["always-accept"]["baselineFailsAxis"], "unsafe_acceptance")
        self.assertEqual(dom["always-abstain"]["baselineFailsAxis"], "zero_coverage")
        for baseline, info in dom.items():
            self.assertEqual(info["proposedErrorCatchRate"], 1.0, baseline)
            self.assertEqual(info["proposedUnsafeAcceptances"], 0, baseline)


class RoundTripTests(unittest.TestCase):
    def test_write_then_check_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "baseline-comparison.json"
            bc.write_comparison(out)
            expected = bc._canonical_bytes(bc.build_comparison())
            self.assertEqual(out.read_bytes(), expected)

    def test_check_detects_tampered_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "baseline-comparison.json"
            bc.write_comparison(out)
            tampered = json.loads(out.read_text(encoding="utf-8"))
            tampered["policies"]["proposed-system"]["totals"]["unsafeAcceptances"] = 1
            out.write_text(
                json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            # Byte-compare must now fail.
            self.assertNotEqual(out.read_bytes(), bc._canonical_bytes(bc.build_comparison()))


if __name__ == "__main__":
    unittest.main()
