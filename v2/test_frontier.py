#!/usr/bin/env python3
"""Tests for the human-gated verification-frontier expansion contract."""
from __future__ import annotations

import unittest

from v2.frontier import (
    ExpansionReceipt,
    ExtensionTest,
    FrontierTask,
    ReviewDecision,
    VerificationResult,
    evaluate_frontier_expansion,
    propose_extension,
    validate_proposal,
)


def decision(proposal_id: str, reviewer: str, *, saw_results: bool = False):
    return ReviewDecision(
        schema="goai-frontier-decision/v1",
        proposal_id=proposal_id,
        reviewer=reviewer,
        decision="approve_candidate",
        reason_codes=(),
        notes="test approval",
        reviewed_at="2026-07-31T00:00:00Z",
        saw_aggregate_results=saw_results,
    )


class FrontierExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = FrontierTask(
            problem_id="physics-gap-001",
            domain="physics",
            rung="frontier-gap",
            prompt="Determine the target velocity.",
            initial_coverage=False,
            expected_abstain_reason="missing_executable_spec",
        )
        self.pre_gate = VerificationResult(
            "abstain",
            "missing_executable_spec",
            "no executable target contract",
            "coverage",
        )
        self.proposal = propose_extension(
            self.task,
            episode_id="model:physics-gap-001:0",
            abstain_reason="missing_executable_spec",
            candidate_specification="target: velocity in m/s; tolerance: 1%",
            test_ids=("positive", "dimension-trap", "malformed"),
        )
        self.tests = (
            ExtensionTest("positive", True, "gold accepted"),
            ExtensionTest("dimension-trap", True, "wrong dimension rejected"),
            ExtensionTest("malformed", True, "malformed candidate abstained"),
        )
        self.approvals = (
            decision(self.proposal.proposal_id, "owner"),
            decision(self.proposal.proposal_id, "expert-ai"),
        )

    def test_valid_proposal_preserves_claim_ceiling(self) -> None:
        self.assertEqual(validate_proposal(self.task, self.proposal), [])
        self.assertTrue(self.proposal.candidateOnly)
        self.assertFalse(self.proposal.canClaimAGI)
        self.assertEqual(
            set(self.proposal.to_dict()),
            {
                "schema",
                "proposalId",
                "episodeId",
                "problemId",
                "domain",
                "abstainReason",
                "proposalType",
                "summary",
                "candidateSpecification",
                "candidateVerifier",
                "testIds",
                "requestedAuthority",
                "candidateOnly",
                "canClaimAGI",
            },
        )

    def test_missing_human_approval_preserves_abstention(self) -> None:
        result, receipt = evaluate_frontier_expansion(
            self.task,
            pre_gate=self.pre_gate,
            proposal=self.proposal,
            decisions=(self.approvals[0],),
            tests=self.tests,
            reverify=lambda: VerificationResult(
                "accepted", "verified", "should not run", "si"
            ),
        )
        self.assertEqual(result.verdict, "abstain")
        self.assertEqual(result.reason_code, "human_gate_incomplete")
        self.assertEqual(receipt.coverage_delta, 0)

    def test_reviewer_who_saw_aggregate_results_does_not_count(self) -> None:
        compromised = (
            self.approvals[0],
            decision(
                self.proposal.proposal_id,
                "expert-ai",
                saw_results=True,
            ),
        )
        result, _ = evaluate_frontier_expansion(
            self.task,
            pre_gate=self.pre_gate,
            proposal=self.proposal,
            decisions=compromised,
            tests=self.tests,
            reverify=lambda: VerificationResult(
                "accepted", "verified", "should not run", "si"
            ),
        )
        self.assertEqual(result.reason_code, "human_gate_incomplete")

    def test_missing_or_failed_tests_preserve_abstention(self) -> None:
        result, receipt = evaluate_frontier_expansion(
            self.task,
            pre_gate=self.pre_gate,
            proposal=self.proposal,
            decisions=self.approvals,
            tests=self.tests[:-1],
            reverify=lambda: VerificationResult(
                "accepted", "verified", "should not run", "si"
            ),
        )
        self.assertEqual(result.reason_code, "extension_tests_failed")
        self.assertEqual(receipt.tests_total, 2)
        self.assertEqual(receipt.coverage_delta, 0)

    def test_approved_passing_extension_can_expand_coverage(self) -> None:
        result, receipt = evaluate_frontier_expansion(
            self.task,
            pre_gate=self.pre_gate,
            proposal=self.proposal,
            decisions=self.approvals,
            tests=self.tests,
            reverify=lambda: VerificationResult(
                "accepted",
                "dimension_and_value_match",
                "deterministic SI check passed",
                "si",
            ),
        )
        self.assertEqual(result.verdict, "accepted")
        self.assertIsInstance(receipt, ExpansionReceipt)
        self.assertEqual(receipt.coverage_delta, 1)
        self.assertTrue(receipt.post_gate_covered)
        self.assertTrue(receipt.candidateOnly)
        self.assertFalse(receipt.canClaimAGI)
        self.assertIn("coverageDelta", receipt.to_dict())
        self.assertNotIn("coverage_delta", receipt.to_dict())

    def test_reverification_rejection_is_not_coverage_expansion(self) -> None:
        result, receipt = evaluate_frontier_expansion(
            self.task,
            pre_gate=self.pre_gate,
            proposal=self.proposal,
            decisions=self.approvals,
            tests=self.tests,
            reverify=lambda: VerificationResult(
                "rejected", "dimension_mismatch", "wrong dimension", "si"
            ),
        )
        self.assertEqual(result.verdict, "rejected")
        self.assertEqual(receipt.coverage_delta, 1)
        self.assertTrue(receipt.post_gate_covered)

    def test_open_control_can_never_be_promoted(self) -> None:
        task = FrontierTask(
            problem_id="riemann",
            domain="lean",
            rung="open-control",
            prompt="Prove the Riemann Hypothesis.",
            initial_coverage=False,
            expected_abstain_reason="missing_executable_spec",
            open_control=True,
        )
        proposal = propose_extension(
            task,
            episode_id="model:riemann:0",
            abstain_reason="missing_executable_spec",
            candidate_specification="attempted formalization",
            candidate_verifier="unsafe verifier",
            test_ids=("fake",),
        )
        self.assertIsNone(proposal.candidate_specification)
        self.assertIsNone(proposal.candidate_verifier)
        self.assertEqual(proposal.test_ids, ())
        self.assertEqual(proposal.requested_authority, ())
        approvals = (
            decision(proposal.proposal_id, "owner"),
            decision(proposal.proposal_id, "expert-ai"),
        )
        result, receipt = evaluate_frontier_expansion(
            task,
            pre_gate=VerificationResult(
                "abstain",
                "missing_executable_spec",
                "open problem",
                "coverage",
            ),
            proposal=proposal,
            decisions=approvals,
            tests=(),
            reverify=lambda: VerificationResult(
                "accepted", "fabricated", "must not run", "unsafe"
            ),
        )
        self.assertEqual(result.verdict, "abstain")
        self.assertEqual(result.reason_code, "open_control_not_promotable")
        self.assertEqual(receipt.coverage_delta, 0)

    def test_wrong_frozen_reason_is_rejected(self) -> None:
        proposal = propose_extension(
            self.task,
            episode_id="model:physics-gap-001:1",
            abstain_reason="missing_verifier",
            candidate_verifier="candidate",
            test_ids=("positive",),
        )
        errors = validate_proposal(self.task, proposal)
        self.assertIn(
            "proposal abstain reason does not match frozen task label",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
