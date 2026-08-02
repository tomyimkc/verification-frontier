#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Deterministic POLICY comparison: proposed verifier vs. degenerate baselines.

This harness compares four decision *policies* on (a) the frozen set of planted
logic errors from ``build_logic_error_audit`` and (b) a frozen set of known-correct
answers. It is an instrument/policy comparison, NOT a model benchmark.

The four policies
-----------------
* ``raw-model``        -- a SIMULATED "accept everything" baseline (no verifier).
                         It does not represent a real model run; it is the trivial
                         accept-all decision rule a system without a verifier
                         degenerates to. High coverage, accepts ALL planted errors.
* ``always-abstain``   -- rejects/abstains on every item. Zero unsafe acceptance,
                         zero coverage.
* ``always-accept``    -- accepts everything. Identical outcomes to ``raw-model``
                         (100% coverage, accepts all planted errors). Kept distinct
                         in the table because it is a different named baseline.
* ``proposed-system``  -- the deterministic verifier (``demo.verify_problem``).
                         Rejects planted errors, accepts correct SI/sympy answers,
                         and abstains on items its executable coverage does not
                         reach. This is the gold-standard policy under comparison.

For each policy x item we record the verdict and whether it matches the item's
expected verdict. The summary demonstrates that only ``proposed-system`` combines
non-zero coverage with non-zero error-catch-rate, while the three accept-all /
abstain-all baselines each sacrifice one of those axes.

It is fail-closed: the builder refuses to relax the claim ceiling, and the
``--check`` mode re-derives the canonical bytes and byte-compares them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Literal

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_OUTPUT = HERE / "artifacts"
COMPARISON_PATH = DEFAULT_OUTPUT / "baseline-comparison.json"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import demo  # noqa: E402
from v2 import build_logic_error_audit  # noqa: E402

Verdict = Literal["accepted", "rejected", "abstain"]
ItemKind = Literal["planted-error", "correct-answer"]

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

POLICY_DESCRIPTIONS = {
    "raw-model": (
        "SIMULATED accept-everything baseline (no verifier). Not a real model run; "
        "it is the trivial decision rule a verifier-less system degenerates to."
    ),
    "always-abstain": "Abstains/rejects on every item. Fail-closed but zero coverage.",
    "always-accept": "Accepts every item. Same outcomes as raw-model; named for clarity.",
    "proposed-system": (
        "The deterministic verifier (demo.verify_problem). Rejects planted errors, "
        "accepts correct SI/sympy answers, abstains on uncovered formal-proof items."
    ),
}


# --------------------------------------------------------------------------- #
# Correct-answer set
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CorrectAnswer:
    """A candidate that SHOULD be accepted by a sound verifier."""

    answer_id: str
    tier: str  # "si" | "sympy" | "formal-proof"
    candidate: str
    reference: str
    # For SI/sympy the expected verdict is "accepted". For valid Lean proofs the
    # package's honest fail-closed behavior is "abstain" (no bundled Lean), which
    # we still score as a CORRECT verdict -- abstaining on a real proof is not an
    # error, it is honest missing coverage. We never accept a formal proof without
    # a checking certificate.
    expected_verdict: str
    expected_reason_code: str


def _si_correct(
    candidate: str, reference: str, *, answer_id: str
) -> CorrectAnswer:
    return CorrectAnswer(
        answer_id, "si", candidate, reference, "accepted", "dimension_and_value_match"
    )


def _sym_correct(
    candidate: str, reference: str, *, answer_id: str
) -> CorrectAnswer:
    return CorrectAnswer(
        answer_id, "sympy", candidate, reference, "accepted", "symbolically_equivalent"
    )


def _lean_correct(
    candidate: str, *, answer_id: str
) -> CorrectAnswer:
    # A valid-looking proof term. The package does NOT bundle Lean, so the honest
    # verdict is abstain (unsupported_tier). This is a CORRECT verdict: the system
    # refuses to claim a proof it cannot check.
    return CorrectAnswer(
        answer_id,
        "formal-proof",
        candidate,
        "have h : True := trivial",
        "abstain",
        "unsupported_tier",
    )


def correct_answers() -> list[CorrectAnswer]:
    """The frozen set of known-correct answers a sound verifier should handle."""
    return [
        # ── SI dimension + value correct (including unit-equivalence cases) ──
        _si_correct("9.8 m/s", "9.8 m/s", answer_id="ok-si-01"),
        _si_correct("9.81 m/s", "9.8 m/s", answer_id="ok-si-02"),
        _si_correct("9 J", "9 J", answer_id="ok-si-03"),
        _si_correct("1000 g", "1 kg", answer_id="ok-si-04"),
        _si_correct("2 kg", "2000 g", answer_id="ok-si-05"),
        _si_correct("1 kW", "1000 W", answer_id="ok-si-06"),
        _si_correct("60 s", "1 min", answer_id="ok-si-07"),
        _si_correct("0 m/s", "0 m/s", answer_id="ok-si-08"),
        # ── SymPy equivalence correct (same polynomial, different surface form) ──
        _sym_correct("(x+1)^2", "(x+1)^2", answer_id="ok-sym-01"),
        _sym_correct("x^2+2*x+1", "(x+1)^2", answer_id="ok-sym-02"),
        _sym_correct("x*x+2*x+1", "(x+1)^2", answer_id="ok-sym-03"),
        _sym_correct("1+2*x+x^2", "(x+1)^2", answer_id="ok-sym-04"),
        _sym_correct("(x+1)*(x+1)", "(x+1)^2", answer_id="ok-sym-05"),
        # ── Valid proof terms: honest verdict is abstain (Lean not bundled) ──
        _lean_correct("have h : True := trivial", answer_id="ok-lean-01"),
        _lean_correct("rfl", answer_id="ok-lean-02"),
        _lean_correct("by simp", answer_id="ok-lean-03"),
    ]


# --------------------------------------------------------------------------- #
# Unified item model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ComparisonItem:
    """One evaluable item, tagged as a planted error or a correct answer."""

    item_id: str
    kind: ItemKind
    tier: str
    candidate: str
    reference: str
    # For a planted error: "rejected". For an SI/sympy correct answer: "accepted".
    # For a formal-proof correct answer: "abstain" (honest missing coverage).
    expected_verdict: str
    expected_reason_code: str


def comparison_items() -> list[ComparisonItem]:
    """Materialize planted errors + correct answers into one ordered item list."""
    items: list[ComparisonItem] = []
    for e in build_logic_error_audit.planted_errors():
        items.append(
            ComparisonItem(
                item_id=e.error_id,
                kind="planted-error",
                tier=e.tier,
                candidate=e.candidate,
                reference=e.reference,
                expected_verdict=e.expected_verdict,  # "rejected"
                expected_reason_code=e.expected_reason_code,
            )
        )
    for a in correct_answers():
        items.append(
            ComparisonItem(
                item_id=a.answer_id,
                kind="correct-answer",
                tier=a.tier,
                candidate=a.candidate,
                reference=a.reference,
                expected_verdict=a.expected_verdict,
                expected_reason_code=a.expected_reason_code,
            )
        )
    return items


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #
def _proposed_verdict(item: ComparisonItem) -> tuple[Verdict, str]:
    """Run the real deterministic verifier on one item and return (verdict, reason)."""
    if item.tier == "si":
        result = demo.verify_physics(item.candidate, item.reference)
    elif item.tier == "sympy":
        result = demo.verify_math(item.candidate, item.reference)
    elif item.tier in {"lean-placeholder", "formal-proof"}:
        # Route through verify_problem so sorry/admit are rejected before the
        # coverage abstention fires, and valid proofs abstain honestly.
        result = demo.verify_problem(
            demo.Problem(
                problem_id=f"baseline:{item.item_id}",
                rung="closed",
                tier="formal-proof",
                prompt="baseline comparison",
                gold=item.reference,
            ),
            item.candidate,
        )
    else:
        result = demo.Result(
            "abstain", "unsupported_tier", f"no tier for {item.tier!r}", "coverage"
        )
    return result.verdict, result.reason_code


def policy_verdict(policy: str, item: ComparisonItem) -> tuple[Verdict, str]:
    """Return the (verdict, reason_code) a named policy emits for one item.

    The three degenerate baselines are pure decision rules -- they ignore the
    item content. ``proposed-system`` runs the real verifier.
    """
    if policy == "raw-model":
        return "accepted", "simulated_accept_all"
    if policy == "always-accept":
        return "accepted", "accept_all"
    if policy == "always-abstain":
        return "abstain", "abstain_all"
    if policy == "proposed-system":
        return _proposed_verdict(item)
    raise KeyError(f"unknown policy: {policy}")


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def _format_rate(numer: int, denom: int) -> float:
    return round(numer / denom, 4) if denom else 0.0


def _evaluate_policy(
    policy: str, items: list[ComparisonItem]
) -> dict[str, Any]:
    rows = []
    correct_verdicts = 0
    incorrect_verdicts = 0
    unsafe_acceptances = 0  # accepted a planted error
    false_rejections = 0  # rejected a correct answer
    accepts = 0
    for item in items:
        verdict, reason_code = policy_verdict(policy, item)
        is_correct = verdict == item.expected_verdict
        kind_correct = (
            "planted-error" if item.kind == "planted-error"
            else "correct-answer"
        )
        if is_correct:
            correct_verdicts += 1
        else:
            incorrect_verdicts += 1
        if verdict == "accepted":
            accepts += 1
        if verdict == "accepted" and item.kind == "planted-error":
            unsafe_acceptances += 1
        if verdict == "rejected" and item.kind == "correct-answer":
            false_rejections += 1
        rows.append(
            {
                "item_id": item.item_id,
                "kind": item.kind,
                "tier": item.tier,
                "candidate": item.candidate,
                "reference": item.reference,
                "expected_verdict": item.expected_verdict,
                "policy_verdict": verdict,
                "reason_code": reason_code,
                "verdict_is_correct": is_correct,
                "failure_class": (
                    "unsafe_acceptance"
                    if (verdict == "accepted" and item.kind == "planted-error")
                    else "false_rejection"
                    if (verdict == "rejected" and item.kind == "correct-answer")
                    else "none"
                    if is_correct
                    else "verdict_mismatch"
                ),
                "kind_label": kind_correct,
            }
        )

    planted = [i for i in items if i.kind == "planted-error"]
    correct = [i for i in items if i.kind == "correct-answer"]
    planted_caught = sum(
        1
        for i in planted
        if policy_verdict(policy, i)[0] == i.expected_verdict  # "rejected"
    )
    correct_accepted = sum(
        1 for i in correct if policy_verdict(policy, i)[0] == i.expected_verdict
    )

    return {
        "policy": policy,
        "description": POLICY_DESCRIPTIONS[policy],
        "isSimulatedBaseline": policy in {"raw-model", "always-accept", "always-abstain"},
        "totals": {
            "total": len(items),
            "correctVerdicts": correct_verdicts,
            "incorrectVerdicts": incorrect_verdicts,
            "unsafeAcceptances": unsafe_acceptances,
            "falseRejections": false_rejections,
        },
        "rates": {
            "verdictAccuracy": _format_rate(correct_verdicts, len(items)),
            "coverageRate": _format_rate(accepts, len(items)),
            "errorCatchRate": _format_rate(planted_caught, len(planted)),
            "correctAcceptanceRate": _format_rate(correct_accepted, len(correct)),
        },
        "details": rows,
    }


def _comparison_table(evaluated: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One compact row per policy for the headline comparison."""
    table = []
    for policy in ("raw-model", "always-abstain", "always-accept", "proposed-system"):
        e = evaluated[policy]
        table.append(
            {
                "policy": policy,
                "isSimulatedBaseline": e["isSimulatedBaseline"],
                "coverageRate": e["rates"]["coverageRate"],
                "errorCatchRate": e["rates"]["errorCatchRate"],
                "unsafeAcceptances": e["totals"]["unsafeAcceptances"],
                "falseRejections": e["totals"]["falseRejections"],
                "verdictAccuracy": e["rates"]["verdictAccuracy"],
            }
        )
    return table


def build_comparison() -> dict[str, Any]:
    items = comparison_items()
    # Validate invariant: every correct-answer's expected verdict is actually
    # produced by the real verifier for that candidate. This guards the honesty
    # of the gold-standard policy row -- if the verifier drifts, build fails loud.
    for item in items:
        if item.kind == "correct-answer":
            real_verdict, real_reason = _proposed_verdict(item)
            if real_verdict != item.expected_verdict:
                raise RuntimeError(
                    f"correct-answer {item.item_id}: verifier returned "
                    f"{real_verdict}/{real_reason}, expected {item.expected_verdict}"
                )

    evaluated = {
        policy: _evaluate_policy(policy, items)
        for policy in ("raw-model", "always-abstain", "always-accept", "proposed-system")
    }
    proposed = evaluated["proposed-system"]
    n_planted = sum(1 for i in items if i.kind == "planted-error")

    # The headline dominance check: proposed-system must strictly beat every
    # baseline on the joint (coverage > 0) AND (errorCatchRate == 1.0) AND
    # (unsafeAcceptances == 0) axes. Baselines fail at least one axis.
    dominance = {}
    for baseline in ("raw-model", "always-abstain", "always-accept"):
        b = evaluated[baseline]
        dominance[baseline] = {
            "baselineCoverageRate": b["rates"]["coverageRate"],
            "baselineErrorCatchRate": b["rates"]["errorCatchRate"],
            "baselineUnsafeAcceptances": b["totals"]["unsafeAcceptances"],
            "proposedCoverageRate": proposed["rates"]["coverageRate"],
            "proposedErrorCatchRate": proposed["rates"]["errorCatchRate"],
            "proposedUnsafeAcceptances": proposed["totals"]["unsafeAcceptances"],
            "baselineFailsAxis": (
                "unsafe_acceptance"
                if b["totals"]["unsafeAcceptances"] > 0
                else "zero_coverage"
                if b["rates"]["coverageRate"] == 0.0
                else "error_catch_zero"
            ),
        }

    return {
        "schema": "goai-baseline-comparison/v1",
        "evidenceClass": "development-only",
        "interpretation": (
            "This is a DETERMINISTIC policy comparison on planted errors and "
            "known-correct answers. It is NOT a model-capability benchmark -- it "
            "compares verifier POLICIES, not model outputs. The 'raw-model' policy "
            "is a SIMULATED accept-everything baseline (no verifier), not a real "
            "model run. Only the 'proposed-system' policy executes the real "
            "deterministic verifier."
        ),
        "policyDescriptions": POLICY_DESCRIPTIONS,
        "itemCounts": {
            "plantedErrors": n_planted,
            "correctAnswers": len(items) - n_planted,
            "total": len(items),
        },
        "comparisonTable": _comparison_table(evaluated),
        "policies": evaluated,
        "dominance": dominance,
        "claimCeiling": CLAIM_CEILING,
        "scientificOutcome": False,
        "capabilityClaim": False,
        "isModelBenchmark": False,
        **CLAIM_CEILING,
    }


# --------------------------------------------------------------------------- #
# Canonical bytes + write/check
# --------------------------------------------------------------------------- #
def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_comparison(output_path: Path = COMPARISON_PATH) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    comparison = build_comparison()
    output_path.write_bytes(_canonical_bytes(comparison))
    return comparison


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=COMPARISON_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        if not args.output.is_file():
            print("BASELINE COMPARISON: FAIL (artifact missing)")
            return 1
        on_disk_bytes = args.output.read_bytes()
        expected_bytes = _canonical_bytes(build_comparison())
        if on_disk_bytes != expected_bytes:
            # Rebuild to a temp location to surface the diff without clobbering.
            print("BASELINE COMPARISON: FAIL (bytes not canonical/current)")
            print(
                f"  on-disk sha256={hashlib.sha256(on_disk_bytes).hexdigest()} "
                f"expected sha256={hashlib.sha256(expected_bytes).hexdigest()}"
            )
            return 1
        on_disk = json.loads(on_disk_bytes.decode("utf-8"))
        proposed = on_disk["policies"]["proposed-system"]
        t = proposed["totals"]
        r = proposed["rates"]
        if t["unsafeAcceptances"] != 0:
            print(
                f"BASELINE COMPARISON: FAIL "
                f"(proposed-system unsafeAcceptances={t['unsafeAcceptances']})"
            )
            return 1
        if r["errorCatchRate"] != 1.0:
            print(
                f"BASELINE COMPARISON: FAIL "
                f"(proposed-system errorCatchRate={r['errorCatchRate']})"
            )
            return 1
        print(
            "BASELINE COMPARISON: PASS ("
            f"policies=4; items={t['total']}; "
            f"proposed coverage={r['coverageRate']}; "
            f"errorCatch={r['errorCatchRate']}; "
            f"unsafeAccepts={t['unsafeAcceptances']})"
        )
        return 0

    comparison = write_comparison(args.output)
    print(
        json.dumps(
            {
                "schema": comparison["schema"],
                "evidenceClass": comparison["evidenceClass"],
                "itemCounts": comparison["itemCounts"],
                "comparisonTable": comparison["comparisonTable"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
