#!/usr/bin/env python3
"""Fail-closed, human-gated verification-frontier expansion.

The model may propose a missing specification or verifier extension, but it
cannot approve or promote its own proposal. A frontier-gap task remains
``abstain`` unless two independent reviewers approve the candidate, every
declared extension test passes, and deterministic re-verification accepts the
original candidate.

This module is environment infrastructure. It is not a model-capability result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

Verdict = Literal["accepted", "rejected", "abstain"]
Domain = Literal["physics", "symbolic", "lean"]
AbstainReason = Literal[
    "missing_executable_spec",
    "missing_verifier",
    "ambiguous_target",
    "unsupported_domain",
    "resource_limit",
    "tool_failure",
    "insufficient_evidence",
    "formalization_failed",
]
ProposalType = Literal[
    "specification",
    "verifier",
    "clarification",
    "resource",
    "evidence",
]
Reviewer = Literal["owner", "expert-ai", "scientific-expert"]
Decision = Literal["approve_candidate", "reject", "defer"]

OPEN_CONTROL_RUNGS = frozenset({"open", "open-control", "open-unformalized"})
REQUIRED_REVIEWERS = frozenset({"owner", "expert-ai"})


@dataclass(frozen=True)
class FrontierTask:
    problem_id: str
    domain: Domain
    rung: str
    prompt: str
    initial_coverage: bool
    expected_abstain_reason: AbstainReason | None = None
    open_control: bool = False


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    reason_code: str
    reason: str
    verifier: str

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reasonCode": self.reason_code,
            "reason": self.reason,
            "verifier": self.verifier,
        }


@dataclass(frozen=True)
class FrontierProposal:
    schema: str
    proposal_id: str
    episode_id: str
    problem_id: str
    domain: Domain
    abstain_reason: AbstainReason
    proposal_type: ProposalType
    summary: str
    candidate_specification: str | None
    candidate_verifier: str | None
    test_ids: tuple[str, ...]
    requested_authority: tuple[str, ...]
    candidateOnly: bool = True
    canClaimAGI: bool = False

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "proposalId": self.proposal_id,
            "episodeId": self.episode_id,
            "problemId": self.problem_id,
            "domain": self.domain,
            "abstainReason": self.abstain_reason,
            "proposalType": self.proposal_type,
            "summary": self.summary,
            "candidateSpecification": self.candidate_specification,
            "candidateVerifier": self.candidate_verifier,
            "testIds": list(self.test_ids),
            "requestedAuthority": list(self.requested_authority),
            "candidateOnly": self.candidateOnly,
            "canClaimAGI": self.canClaimAGI,
        }


@dataclass(frozen=True)
class ReviewDecision:
    schema: str
    proposal_id: str
    reviewer: Reviewer
    decision: Decision
    reason_codes: tuple[str, ...]
    notes: str
    reviewed_at: str
    saw_aggregate_results: bool

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "proposalId": self.proposal_id,
            "reviewer": self.reviewer,
            "decision": self.decision,
            "reasonCodes": list(self.reason_codes),
            "notes": self.notes,
            "reviewedAt": self.reviewed_at,
            "sawAggregateResults": self.saw_aggregate_results,
        }


@dataclass(frozen=True)
class ExtensionTest:
    test_id: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class ExpansionReceipt:
    schema: str
    episode_id: str
    problem_id: str
    proposal_id: str
    pre_gate_verdict: Verdict
    terminal_verdict: Verdict
    terminal_reason_code: str
    approved_reviewers: tuple[str, ...]
    tests_passed: int
    tests_total: int
    pre_gate_covered: bool
    post_gate_covered: bool
    coverage_delta: int
    candidateOnly: bool = True
    canClaimAGI: bool = False

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "episodeId": self.episode_id,
            "problemId": self.problem_id,
            "proposalId": self.proposal_id,
            "preGateVerdict": self.pre_gate_verdict,
            "terminalVerdict": self.terminal_verdict,
            "terminalReasonCode": self.terminal_reason_code,
            "approvedReviewers": list(self.approved_reviewers),
            "testsPassed": self.tests_passed,
            "testsTotal": self.tests_total,
            "preGateCovered": self.pre_gate_covered,
            "postGateCovered": self.post_gate_covered,
            "coverageDelta": self.coverage_delta,
            "candidateOnly": self.candidateOnly,
            "canClaimAGI": self.canClaimAGI,
        }


_PROPOSAL_TYPES: dict[AbstainReason, ProposalType] = {
    "missing_executable_spec": "specification",
    "missing_verifier": "verifier",
    "ambiguous_target": "clarification",
    "unsupported_domain": "verifier",
    "resource_limit": "resource",
    "tool_failure": "resource",
    "insufficient_evidence": "evidence",
    "formalization_failed": "specification",
}


def propose_extension(
    task: FrontierTask,
    *,
    episode_id: str,
    abstain_reason: AbstainReason,
    candidate_specification: str | None = None,
    candidate_verifier: str | None = None,
    test_ids: Sequence[str] = (),
) -> FrontierProposal:
    """Create a bounded candidate extension without approving it."""
    if not episode_id.strip():
        raise ValueError("episode_id is required")
    if task.open_control or task.rung in OPEN_CONTROL_RUNGS:
        summary = (
            "Preserve abstention: open-control tasks cannot be promoted by "
            "frontier expansion."
        )
        candidate_specification = None
        candidate_verifier = None
        test_ids = ()
        requested_authority = ()
    else:
        requested_authority = ("run_extension_tests",)
        summary = {
            "missing_executable_spec": (
                "Draft the smallest executable contract that preserves the "
                "task's stated target."
            ),
            "missing_verifier": (
                "Draft a verifier interface plus positive, negative, and "
                "fail-closed tests."
            ),
            "ambiguous_target": "Request one bounded clarification before verification.",
            "unsupported_domain": (
                "Queue a domain adapter proposal without granting execution authority."
            ),
            "resource_limit": "Request a bounded resource grant with a recorded cost ceiling.",
            "tool_failure": "Retry once or request a declared independent fallback.",
            "insufficient_evidence": "Request the minimum external evidence needed for a check.",
            "formalization_failed": (
                "Preserve the failed formalization and draft a reviewed replacement."
            ),
        }[abstain_reason]

    proposal_id = f"{episode_id}:frontier"
    return FrontierProposal(
        schema="goai-frontier-proposal/v1",
        proposal_id=proposal_id,
        episode_id=episode_id,
        problem_id=task.problem_id,
        domain=task.domain,
        abstain_reason=abstain_reason,
        proposal_type=_PROPOSAL_TYPES[abstain_reason],
        summary=summary,
        candidate_specification=candidate_specification,
        candidate_verifier=candidate_verifier,
        test_ids=tuple(test_ids),
        requested_authority=requested_authority,
    )


def validate_proposal(task: FrontierTask, proposal: FrontierProposal) -> list[str]:
    errors: list[str] = []
    if proposal.schema != "goai-frontier-proposal/v1":
        errors.append("unsupported proposal schema")
    if proposal.problem_id != task.problem_id:
        errors.append("proposal problem_id does not match task")
    if proposal.domain != task.domain:
        errors.append("proposal domain does not match task")
    if proposal.candidateOnly is not True:
        errors.append("proposal candidateOnly must be true")
    if proposal.canClaimAGI is not False:
        errors.append("proposal canClaimAGI must be false")
    if task.expected_abstain_reason and (
        proposal.abstain_reason != task.expected_abstain_reason
    ):
        errors.append("proposal abstain reason does not match frozen task label")
    if task.open_control or task.rung in OPEN_CONTROL_RUNGS:
        if proposal.candidate_specification or proposal.candidate_verifier:
            errors.append("open-control proposal must not include a promotable extension")
        if proposal.test_ids:
            errors.append("open-control proposal must not request extension tests")
    elif proposal.proposal_type in {"specification", "verifier"}:
        if not (proposal.candidate_specification or proposal.candidate_verifier):
            errors.append("candidate specification or verifier is required")
        if not proposal.test_ids:
            errors.append("candidate extension requires at least one test")
    return errors


def _approved_reviewers(
    proposal: FrontierProposal,
    decisions: Sequence[ReviewDecision],
) -> tuple[str, ...]:
    approved: set[str] = set()
    for decision in decisions:
        if decision.proposal_id != proposal.proposal_id:
            continue
        if decision.saw_aggregate_results:
            continue
        if decision.decision == "approve_candidate":
            approved.add(decision.reviewer)
    return tuple(sorted(approved))


def evaluate_frontier_expansion(
    task: FrontierTask,
    *,
    pre_gate: VerificationResult,
    proposal: FrontierProposal,
    decisions: Sequence[ReviewDecision],
    tests: Sequence[ExtensionTest],
    reverify: Callable[[], VerificationResult],
) -> tuple[VerificationResult, ExpansionReceipt]:
    """Apply the human gate, tests, and deterministic re-verification."""
    validation_errors = validate_proposal(task, proposal)
    approved = _approved_reviewers(proposal, decisions)
    passed = sum(1 for test in tests if test.passed)

    def finish(result: VerificationResult, post_covered: bool) -> tuple[
        VerificationResult, ExpansionReceipt
    ]:
        pre_covered = pre_gate.verdict != "abstain"
        receipt = ExpansionReceipt(
            schema="goai-frontier-expansion/v1",
            episode_id=proposal.episode_id,
            problem_id=task.problem_id,
            proposal_id=proposal.proposal_id,
            pre_gate_verdict=pre_gate.verdict,
            terminal_verdict=result.verdict,
            terminal_reason_code=result.reason_code,
            approved_reviewers=approved,
            tests_passed=passed,
            tests_total=len(tests),
            pre_gate_covered=pre_covered,
            post_gate_covered=post_covered,
            coverage_delta=int(post_covered) - int(pre_covered),
        )
        return result, receipt

    if pre_gate.verdict != "abstain":
        return finish(pre_gate, post_covered=True)
    if task.open_control or task.rung in OPEN_CONTROL_RUNGS:
        return finish(
            VerificationResult(
                "abstain",
                "open_control_not_promotable",
                "open-control tasks cannot cross the verification frontier",
                "frontier-gate",
            ),
            post_covered=False,
        )
    if validation_errors:
        return finish(
            VerificationResult(
                "abstain",
                "invalid_frontier_proposal",
                "; ".join(validation_errors),
                "frontier-gate",
            ),
            post_covered=False,
        )
    if not REQUIRED_REVIEWERS.issubset(approved):
        return finish(
            VerificationResult(
                "abstain",
                "human_gate_incomplete",
                "owner and expert-ai approval are both required",
                "frontier-gate",
            ),
            post_covered=False,
        )
    expected_tests = set(proposal.test_ids)
    observed_tests = {test.test_id for test in tests}
    if observed_tests != expected_tests or any(not test.passed for test in tests):
        return finish(
            VerificationResult(
                "abstain",
                "extension_tests_failed",
                "extension tests are missing, extra, or not all passing",
                "frontier-gate",
            ),
            post_covered=False,
        )

    result = reverify()
    if result.verdict == "accepted":
        return finish(result, post_covered=True)
    return finish(result, post_covered=result.verdict != "abstain")
