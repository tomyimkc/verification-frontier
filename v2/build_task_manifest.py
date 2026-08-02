#!/usr/bin/env python3
"""Build and validate the frozen 150-task GOAI v2 benchmark manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "artifacts"


@dataclass(frozen=True)
class Task:
    schema: str
    task_id: str
    domain: str
    split: str
    rung: str
    prompt: str
    verifier: str
    expected_terminal: str
    gold: Any
    expected_abstain_reason: str | None
    open_control: bool
    candidateOnly: bool = True
    canClaimAGI: bool = False


def _task(
    task_id: str,
    domain: str,
    split: str,
    prompt: str,
    verifier: str,
    gold: Any,
    *,
    expected_terminal: str = "accepted",
    reason: str | None = None,
    open_control: bool = False,
) -> Task:
    rung = "frontier-gap" if split == "frontier-gap" else split
    if open_control:
        rung = "open-control"
    return Task(
        schema="goai-frontier-task/v1",
        task_id=task_id,
        domain=domain,
        split=split,
        rung=rung,
        prompt=prompt,
        verifier=verifier,
        expected_terminal=expected_terminal,
        gold=gold,
        expected_abstain_reason=reason,
        open_control=open_control,
    )


def physics_tasks() -> list[Task]:
    tasks: list[Task] = []
    for t in range(1, 11):
        tasks.append(
            _task(
                f"physics-closed-freefall-{t:02d}",
                "physics",
                "executable-closed",
                f"An object falls from rest for {t} s at g=9.8 m/s^2. Give its speed.",
                "si",
                f"{9.8 * t:g} m/s",
            )
        )
    for mass in range(1, 11):
        velocity = mass % 4 + 2
        energy = 0.5 * mass * velocity * velocity
        tasks.append(
            _task(
                f"physics-closed-ke-{mass:02d}",
                "physics",
                "executable-closed",
                (
                    f"A {mass} kg object moves at {velocity} m/s. "
                    "Give its kinetic energy."
                ),
                "si",
                f"{energy:g} J",
            )
        )
    for mass in range(1, 11):
        acceleration = mass % 3 + 2
        force = mass * acceleration
        tasks.append(
            _task(
                f"physics-closed-force-{mass:02d}",
                "physics",
                "executable-closed",
                (
                    f"A {mass} kg mass accelerates at {acceleration} m/s^2. "
                    "Give the net force."
                ),
                "si",
                f"{force:g} N",
            )
        )
    for mass in range(2, 12):
        velocity = (mass % 5) + 1
        momentum = mass * velocity
        tasks.append(
            _task(
                f"physics-heldout-momentum-{mass:02d}",
                "physics",
                "held-out-executable",
                (
                    f"A {mass} kg object moves at {velocity} m/s. "
                    "Give the momentum."
                ),
                "si",
                f"{momentum:g} kg*m/s",
            )
        )

    frontier_rows = [
        (
            "missing-speed-contract",
            "A trajectory log is available. Return the relevant speed.",
            "missing_executable_spec",
        ),
        (
            "missing-tolerance",
            "A simulation and measurement differ slightly. Decide whether they agree.",
            "missing_executable_spec",
        ),
        (
            "missing-temperature-verifier",
            "Convert the reported laboratory temperature from Celsius to Kelvin.",
            "missing_verifier",
        ),
        (
            "missing-vector-verifier",
            "Compute the resultant of the supplied three-dimensional force vectors.",
            "missing_verifier",
        ),
        (
            "ambiguous-acceleration",
            "Report the acceleration; the prompt does not say average or instantaneous.",
            "ambiguous_target",
        ),
        (
            "unsupported-fluid-domain",
            "Estimate turbulent drag from an unregistered CFD state.",
            "unsupported_domain",
        ),
        (
            "resource-orbit",
            "Verify a long-horizon n-body orbit under a fixed compute budget.",
            "resource_limit",
        ),
        (
            "tool-failed-solver",
            "The accepted numerical solver crashed before producing a certificate.",
            "tool_failure",
        ),
        (
            "missing-calibration-data",
            "Validate a sensor claim without the referenced calibration file.",
            "insufficient_evidence",
        ),
        (
            "formalization-units",
            "A prose conservation-law claim has a malformed executable specification.",
            "formalization_failed",
        ),
    ]
    for index, (suffix, prompt, reason) in enumerate(frontier_rows, start=1):
        tasks.append(
            _task(
                f"physics-frontier-{index:02d}-{suffix}",
                "physics",
                "frontier-gap",
                prompt,
                "coverage",
                None,
                expected_terminal="abstain",
                reason=reason,
            )
        )
    return tasks


def symbolic_tasks() -> list[Task]:
    tasks: list[Task] = []
    for a in range(1, 11):
        tasks.append(
            _task(
                f"symbolic-closed-square-{a:02d}",
                "symbolic",
                "executable-closed",
                f"Expand (x+{a})^2.",
                "sympy",
                f"x^2+{2 * a}*x+{a * a}",
            )
        )
    for a in range(1, 11):
        tasks.append(
            _task(
                f"symbolic-closed-diffsq-{a:02d}",
                "symbolic",
                "executable-closed",
                f"Expand (x-{a})*(x+{a}).",
                "sympy",
                f"x^2-{a * a}",
            )
        )
    for a in range(1, 11):
        b = a + 2
        tasks.append(
            _task(
                f"symbolic-closed-product-{a:02d}",
                "symbolic",
                "executable-closed",
                f"Expand (x+{a})*(x+{b}).",
                "sympy",
                f"x^2+{a + b}*x+{a * b}",
            )
        )
    for a in range(2, 12):
        b = a + 3
        tasks.append(
            _task(
                f"symbolic-heldout-cubic-{a:02d}",
                "symbolic",
                "held-out-executable",
                f"Expand (x+{a})*(x^2+{b}).",
                "sympy",
                f"x^3+{a}*x^2+{b}*x+{a * b}",
            )
        )

    frontier_rows = [
        (
            "undefined-assumptions",
            "Simplify sqrt(x^2) without assumptions on x.",
            "missing_executable_spec",
        ),
        (
            "missing-equivalence-domain",
            "Decide whether two expressions are equivalent without a stated domain.",
            "missing_executable_spec",
        ),
        (
            "missing-matrix-verifier",
            "Check equivalence of two symbolic matrix decompositions.",
            "missing_verifier",
        ),
        (
            "missing-distribution-verifier",
            "Verify an equality between generalized functions.",
            "missing_verifier",
        ),
        (
            "ambiguous-normal-form",
            "Put the expression in standard form without defining the normal form.",
            "ambiguous_target",
        ),
        (
            "unsupported-category-theory",
            "Verify equality of two unregistered category-theory constructions.",
            "unsupported_domain",
        ),
        (
            "resource-groebner",
            "Verify a large Groebner-basis certificate beyond the time budget.",
            "resource_limit",
        ),
        (
            "tool-failed-cas",
            "The accepted symbolic engine terminated unexpectedly.",
            "tool_failure",
        ),
        (
            "missing-parameter-evidence",
            "Validate a fitted symbolic law without the referenced observations.",
            "insufficient_evidence",
        ),
        (
            "formalization-piecewise",
            "A piecewise identity was translated with inconsistent branch conditions.",
            "formalization_failed",
        ),
    ]
    for index, (suffix, prompt, reason) in enumerate(frontier_rows, start=1):
        tasks.append(
            _task(
                f"symbolic-frontier-{index:02d}-{suffix}",
                "symbolic",
                "frontier-gap",
                prompt,
                "coverage",
                None,
                expected_terminal="abstain",
                reason=reason,
            )
        )
    return tasks


LEAN_CLOSED: tuple[tuple[str, str, str], ...] = (
    ("nat-add-zero", "theorem t (n : Nat) : n + 0 = n := by", "simp"),
    ("nat-zero-add", "theorem t (n : Nat) : 0 + n = n := by", "simp"),
    ("nat-mul-one", "theorem t (n : Nat) : n * 1 = n := by", "simp"),
    ("nat-one-mul", "theorem t (n : Nat) : 1 * n = n := by", "simp"),
    ("nat-add-comm", "theorem t (n m : Nat) : n + m = m + n := by", "omega"),
    (
        "nat-add-assoc",
        "theorem t (a b c : Nat) : (a + b) + c = a + (b + c) := by",
        "omega",
    ),
    ("nat-mul-comm", "theorem t (n m : Nat) : n * m = m * n := by", "simp [Nat.mul_comm]"),
    (
        "nat-left-distrib",
        "theorem t (a b c : Nat) : a * (b + c) = a*b + a*c := by",
        "simp [Nat.mul_add]",
    ),
    (
        "nat-right-distrib",
        "theorem t (a b c : Nat) : (a + b) * c = a*c + b*c := by",
        "simp [Nat.add_mul]",
    ),
    ("nat-double", "theorem t (n : Nat) : n + n = 2 * n := by", "omega"),
    ("prop-id", "theorem t (p : Prop) : p → p := by", "intro h; exact h"),
    (
        "prop-and-comm",
        "theorem t (p q : Prop) : p ∧ q → q ∧ p := by",
        "intro h; exact ⟨h.2, h.1⟩",
    ),
    (
        "prop-or-comm",
        "theorem t (p q : Prop) : p ∨ q → q ∨ p := by",
        "intro h; rcases h with hp | hq; exact Or.inr hp; exact Or.inl hq",
    ),
    ("prop-and-left", "theorem t (p q : Prop) : p ∧ q → p := by", "intro h; exact h.1"),
    ("prop-and-right", "theorem t (p q : Prop) : p ∧ q → q := by", "intro h; exact h.2"),
    ("prop-not-false", "theorem t : ¬ False := by", "intro h; exact h"),
    ("prop-true", "theorem t : True := by", "trivial"),
    (
        "prop-compose",
        "theorem t (p q r : Prop) : (p → q) → (q → r) → p → r := by",
        "intro hpq hqr hp; exact hqr (hpq hp)",
    ),
    ("prop-and-true", "theorem t (p : Prop) : p ∧ True ↔ p := by", "simp"),
    ("prop-or-false", "theorem t (p : Prop) : p ∨ False ↔ p := by", "simp"),
    ("int-add-zero", "theorem t (x : Int) : x + 0 = x := by", "simp"),
    ("int-sub-self", "theorem t (x : Int) : x - x = 0 := by", "simp"),
    ("int-mul-zero", "theorem t (x : Int) : x * 0 = 0 := by", "simp"),
    ("int-add-comm", "theorem t (x y : Int) : x + y = y + x := by", "ring"),
    ("int-mul-comm", "theorem t (x y : Int) : x * y = y * x := by", "ring"),
    ("eq-symm", "theorem t {α} (a b : α) : a = b → b = a := by", "intro h; exact h.symm"),
    ("list-reverse", "theorem t {α} (xs : List α) : xs.reverse.reverse = xs := by", "simp"),
    (
        "set-subset-refl",
        "theorem t {α} (s : Set α) : s ⊆ s := by",
        "intro x hx; exact hx",
    ),
    ("nat-max-self", "theorem t (n : Nat) : max n n = n := by", "simp"),
    ("nat-min-self", "theorem t (n : Nat) : min n n = n := by", "simp"),
)

LEAN_HELDOUT: tuple[tuple[str, str, str], ...] = (
    ("nat-succ-positive", "theorem t (n : Nat) : 0 < n + 1 := by", "omega"),
    ("nat-add-cancel", "theorem t (a b c : Nat) : a+b = a+c → b=c := by", "omega"),
    ("nat-square-nonneg", "theorem t (n : Int) : 0 ≤ n*n := by", "nlinarith [sq_nonneg n]"),
    ("int-neg-neg", "theorem t (x : Int) : -(-x) = x := by", "simp"),
    ("prop-mp", "theorem t (p q : Prop) : p → (p → q) → q := by", "aesop"),
    ("prop-curry", "theorem t (p q r : Prop) : (p ∧ q → r) → p → q → r := by", "aesop"),
    ("list-append-nil", "theorem t {α} (xs : List α) : xs ++ [] = xs := by", "simp"),
    (
        "list-length-append",
        "theorem t {α} (xs ys : List α) : (xs ++ ys).length = xs.length + ys.length := by",
        "simp",
    ),
    ("set-inter-self", "theorem t {α} (s : Set α) : s ∩ s = s := by", "ext x; simp"),
    ("nat-three-even-six", "theorem t (n : Nat) : 6*n = 2*(3*n) := by", "omega"),
)


def lean_tasks() -> list[Task]:
    tasks: list[Task] = []
    for index, (suffix, theorem, proof) in enumerate(LEAN_CLOSED, start=1):
        tasks.append(
            _task(
                f"lean-closed-{index:02d}-{suffix}",
                "lean",
                "executable-closed",
                f"Complete this Lean 4 + Mathlib proof:\n{theorem}",
                "lean-mathlib",
                {"theorem": theorem, "proof": proof},
            )
        )
    for index, (suffix, theorem, proof) in enumerate(LEAN_HELDOUT, start=1):
        tasks.append(
            _task(
                f"lean-heldout-{index:02d}-{suffix}",
                "lean",
                "held-out-executable",
                f"Complete this Lean 4 + Mathlib proof:\n{theorem}",
                "lean-mathlib",
                {"theorem": theorem, "proof": proof},
            )
        )

    frontier_rows = [
        (
            "missing-natural-language-map",
            "Formalize a prose theorem whose variable domains are unstated.",
            "missing_executable_spec",
            False,
        ),
        (
            "missing-side-conditions",
            "Formalize a division identity without nonzero side conditions.",
            "missing_executable_spec",
            False,
        ),
        (
            "missing-library-verifier",
            "Verify a theorem that depends on an unregistered external Lean library.",
            "missing_verifier",
            False,
        ),
        (
            "ambiguous-quantifiers",
            "Formalize a claim whose quantifier scope has two plausible readings.",
            "ambiguous_target",
            False,
        ),
        (
            "resource-large-proof",
            "Check a proof term that exceeds the frozen elaboration time budget.",
            "resource_limit",
            False,
        ),
        (
            "tool-failed-lean",
            "The pinned Lean process exited before returning a kernel result.",
            "tool_failure",
            False,
        ),
        (
            "formalization-mismatch",
            "The Lean proposition omits a condition present in the prose claim.",
            "formalization_failed",
            False,
        ),
        (
            "riemann-control",
            "Prove that all non-trivial zeta zeros lie on Re(s)=1/2.",
            "missing_executable_spec",
            True,
        ),
        (
            "p-vs-np-control",
            "Prove P is not equal to NP.",
            "missing_executable_spec",
            True,
        ),
        (
            "navier-stokes-control",
            "Prove global regularity for three-dimensional incompressible Navier-Stokes.",
            "missing_executable_spec",
            True,
        ),
    ]
    for index, (suffix, prompt, reason, open_control) in enumerate(
        frontier_rows,
        start=1,
    ):
        tasks.append(
            _task(
                f"lean-frontier-{index:02d}-{suffix}",
                "lean",
                "frontier-gap",
                prompt,
                "coverage",
                None,
                expected_terminal="abstain",
                reason=reason,
                open_control=open_control,
            )
        )
    return tasks


def build_tasks() -> list[Task]:
    return physics_tasks() + symbolic_tasks() + lean_tasks()


def validate(tasks: list[Task]) -> list[str]:
    errors: list[str] = []
    if len(tasks) != 150:
        errors.append(f"expected 150 tasks, got {len(tasks)}")
    ids = [task.task_id for task in tasks]
    prompts = [task.prompt for task in tasks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate task_id")
    if len(prompts) != len(set(prompts)):
        errors.append("duplicate prompt")
    domains = Counter(task.domain for task in tasks)
    if domains != Counter({"physics": 50, "symbolic": 50, "lean": 50}):
        errors.append(f"unexpected domain counts: {dict(domains)}")
    splits = Counter(task.split for task in tasks)
    if splits != Counter(
        {
            "executable-closed": 90,
            "held-out-executable": 30,
            "frontier-gap": 30,
        }
    ):
        errors.append(f"unexpected split counts: {dict(splits)}")
    for task in tasks:
        if task.candidateOnly is not True or task.canClaimAGI is not False:
            errors.append(f"{task.task_id}: invalid claim ceiling")
        if task.split == "frontier-gap":
            if task.expected_terminal != "abstain":
                errors.append(f"{task.task_id}: frontier task must expect abstain")
            if not task.expected_abstain_reason:
                errors.append(f"{task.task_id}: missing frozen abstain reason")
        elif task.gold is None:
            errors.append(f"{task.task_id}: executable task missing gold")
        if task.open_control and task.rung != "open-control":
            errors.append(f"{task.task_id}: open control has wrong rung")
    return errors


def canonical_rows(tasks: list[Task]) -> bytes:
    rows = [
        json.dumps(asdict(task), ensure_ascii=False, sort_keys=True)
        for task in tasks
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def write_manifest(output_dir: Path) -> dict:
    tasks = build_tasks()
    errors = validate(tasks)
    if errors:
        raise SystemExit("TASK MANIFEST INVALID:\n- " + "\n- ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = canonical_rows(tasks)
    manifest_path = output_dir / "task-manifest.jsonl"
    manifest_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    summary = {
        "schema": "goai-frontier-task-manifest-summary/v1",
        "taskCount": len(tasks),
        "domainCounts": dict(Counter(task.domain for task in tasks)),
        "splitCounts": dict(Counter(task.split for task in tasks)),
        "openControlCount": sum(task.open_control for task in tasks),
        "sha256": digest,
        "manifest": manifest_path.name,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    (output_dir / "task-manifest-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = write_manifest(args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
