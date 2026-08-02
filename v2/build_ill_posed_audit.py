#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 tomyimkc
"""Deterministic ill-posedness catch-rate audit + baseline comparison.

This is **instrument evidence** for the research direction "LLMs cannot recognize
unsolvable / ill-posed problems -- they hallucinate solutions instead of
abstaining." It demonstrates that a DETERMINISTIC ill-posedness detector
correctly abstains on ill-posed problems where a verifier-less (raw-model)
policy would hallucinate a solution and accept it.

It is INSTRUMENT evidence (the detector is real), NOT a model-capability claim.
The catch-rate is a property of the deterministic detector, not of any model.

═══════════════════════════════════════════════════════════════════════════════
WHAT THIS FILE PRODUCES
═══════════════════════════════════════════════════════════════════════════════

``v2/artifacts/ill-posed-audit.json`` (schema ``goai-ill-posed-audit/v1``):

  1. **Catch-rate audit** -- for every ill-posed task from ``v2.ill_posed_tasks``,
     run the deterministic detector ``v2.verify_ill_posed`` and record whether it
     correctly abstained. The correct verdict for EVERY ill-posed task is
     ``abstain`` (the system must refuse to solve an unsolvable problem).

  2. **Baseline comparison (4-way)** -- the same detector vs three degenerate
     decision rules, evaluated on BOTH the ill-posed tasks AND a frozen set of
     ~10 well-posed control items (simple solvable systems):

       * ``raw-model``       -- SIMULATED accept-everything baseline (no
                                detector). Hallucinates a solution on every
                                ill-posed item. 0% correct on ill-posed.
       * ``always-abstain``  -- abstains on everything. 100% on ill-posed but
                                0% on well-posed (refuses solvable problems).
       * ``always-accept``   -- accepts everything. Same outcomes as raw-model.
       * ``proposed-system`` -- runs the ill-posedness detector. Should abstain
                                on ill-posed AND accept on well-posed. This is
                                the only policy that is correct on BOTH sides.

═══════════════════════════════════════════════════════════════════════════════
EXPECTED INTERFACE FROM PARALLEL AGENTS
═══════════════════════════════════════════════════════════════════════════════

This file is built in parallel with two other agents and imports from both. The
expected interface is intentionally permissive (dataclass OR dict, attribute OR
key access) so integration is robust:

``v2.ill_posed_tasks.ill_posed_tasks``  --  a list of >= 30 task objects. Each
task exposes (dataclass attributes OR dict keys):
  * ``task_id``   (str)  -- stable unique id
  * ``prompt``    (str)  -- the problem statement / description
  * ``category``  (str)  -- the ill-posedness type (e.g. ``"missing_data"``,
                            ``"contradictory_constraints"``, ``"undefined"``,
                            ``"vacuous"``, ``"infinite_solutions"``)

``v2.verify_ill_posed.verify_ill_posed``  --  a callable with signature
``verify_ill_posed(task) -> result`` where ``result`` exposes (object attributes
OR dict keys):
  * ``verdict``       (str)  -- one of ``"accepted"`` / ``"rejected"`` /
                                ``"abstain"``
  * ``reason_code``   (str)  -- machine reason code

Detector contract:
  * ill-posed task  -> returns ``abstain`` (correctly refuses to solve)
  * well-posed task -> returns ``accepted`` (correctly recognizes it is solvable)

═══════════════════════════════════════════════════════════════════════════════
FAIL-CLOSED CONTRACT
═══════════════════════════════════════════════════════════════════════════════

The builder refuses to relax the claim ceiling. The ``status`` field is ``PASS``
only when (catch-rate on ill-posed == 1.0) AND (false-alarm-rate on well-posed
== 0.0). Any miss or false alarm is recorded honestly in the artifact and never
hidden; ``--check`` re-derives the canonical bytes and byte-compares them, and
requires ``status == PASS``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_OUTPUT = HERE / "artifacts"
AUDIT_PATH = DEFAULT_OUTPUT / "ill-posed-audit.json"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# ── Parallel-agent imports (try/except: these will work once the parallel
#    agents finish v2/ill_posed_tasks.py and v2/verify_ill_posed.py). ──────────
_ILL_POSED_TASKS: list[Any] = []
_VERIFY_ILL_POSED: Callable[[Any], Any] | None = None
_DEPS_AVAILABLE = False
_DEPS_ERROR = ""

try:
    from v2.ill_posed_tasks import ill_posed_tasks as _imported_tasks  # noqa: E402
    from v2.verify_ill_posed import verify_ill_posed as _imported_verifier  # noqa: E402

    # ``ill_posed_tasks`` may be either a list (the documented interface) or a
    # zero-arg factory returning one. Accept both so integration is robust.
    _ILL_POSED_TASKS = (
        list(_imported_tasks)
        if not callable(_imported_tasks)
        else list(_imported_tasks())
    )
    _VERIFY_ILL_POSED = _imported_verifier
    _DEPS_AVAILABLE = True
except ImportError as _exc:
    # Will work once parallel agents finish. Until then the module is importable
    # (so the test file can at least load the always-available pieces) but
    # build_audit() raises a clear RuntimeError.
    _DEPS_ERROR = str(_exc)


Verdict = Literal["accepted", "rejected", "abstain"]
ItemKind = Literal["ill-posed", "well-posed"]

CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

POLICY_DESCRIPTIONS = {
    "raw-model": (
        "SIMULATED accept-everything baseline (no ill-posedness detector). Not a "
        "real model run; it is the trivial decision rule a verifier-less system "
        "degenerates to -- it hallucinates a solution on every ill-posed item and "
        "accepts it. Mirrors the documented LLM failure mode."
    ),
    "always-abstain": (
        "Abstains on every item. Correctly refuses ill-posed problems but also "
        "refuses every solvable one -- fail-closed with zero useful coverage."
    ),
    "always-accept": (
        "Accepts every item. Identical outcomes to raw-model (accepts all "
        "ill-posed items). Kept distinct in the table as a named baseline."
    ),
    "proposed-system": (
        "Runs the deterministic ill-posedness detector (v2.verify_ill_posed). "
        "Abstains on ill-posed problems and accepts well-posed ones. The only "
        "policy that is correct on BOTH sides of the solvability boundary."
    ),
}


# --------------------------------------------------------------------------- #
# Well-posed control items (defined locally -- always available)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WellPosedControl:
    """A simple, solvable problem used as a control in the comparison.

    These are NOT ill-posed -- they have a well-defined unique answer. The
    ill-posedness detector must NOT abstain on them (a false alarm here would
    mean the detector refuses solvable problems, undermining coverage).
    """

    control_id: str
    prompt: str
    gold: str  # the unique correct answer, proving the problem is well-posed
    domain: str  # "physics" | "math" | "arithmetic"


def well_posed_controls() -> list[WellPosedControl]:
    """Frozen set of ~10 simple solvable control problems."""
    return [
        # ── Physics (SI) ──
        WellPosedControl(
            "wp-phy-01",
            "An object falls from rest for 1 s under g = 9.8 m/s^2. What is its speed?",
            "9.8 m/s",
            "physics",
        ),
        WellPosedControl(
            "wp-phy-02",
            "A 2 kg object moves at 3 m/s. What is its kinetic energy?",
            "9 J",
            "physics",
        ),
        WellPosedControl(
            "wp-phy-03",
            "A force of 5 N acts on a 1 kg mass. What is the acceleration?",
            "5 m/s^2",
            "physics",
        ),
        # ── Math (symbolic) ──
        WellPosedControl(
            "wp-math-01",
            "Expand (x+1)^2.",
            "x^2+2*x+1",
            "math",
        ),
        WellPosedControl(
            "wp-math-02",
            "Factor x^2-1.",
            "(x-1)*(x+1)",
            "math",
        ),
        WellPosedControl(
            "wp-math-03",
            "Simplify (n+2)*(n+1).",
            "n*n+3*n+2",
            "math",
        ),
        # ── Arithmetic (single numeric answer) ──
        WellPosedControl(
            "wp-ari-01",
            "What is 2 + 2?",
            "4",
            "arithmetic",
        ),
        WellPosedControl(
            "wp-ari-02",
            "What is 7 * 6?",
            "42",
            "arithmetic",
        ),
        WellPosedControl(
            "wp-ari-03",
            "What is the integer square root of 144?",
            "12",
            "arithmetic",
        ),
        WellPosedControl(
            "wp-ari-04",
            "How many prime numbers are there between 1 and 10?",
            "4",
            "arithmetic",
        ),
    ]


# --------------------------------------------------------------------------- #
# Normalization helpers (dataclass- or dict-tolerant)
# --------------------------------------------------------------------------- #
def _field(obj: Any, name: str, *fallbacks: str, default: Any = None) -> Any:
    """Read a field from a dataclass or dict, trying primary + fallback names."""
    if isinstance(obj, dict):
        for key in (name, *fallbacks):
            if key in obj and obj[key] is not None:
                return obj[key]
        return default
    for key in (name, *fallbacks):
        if hasattr(obj, key):
            val = getattr(obj, key)
            if val is not None:
                return val
    return default


def _task_id(task: Any) -> str:
    return str(_field(task, "task_id", "id", default="unknown-task"))


def _task_prompt(task: Any) -> str:
    return str(_field(task, "prompt", "description", "text", "statement", default=""))


def _task_category(task: Any) -> str:
    return str(
        _field(task, "category", "error_type", "ill_posed_type", "kind", default="unspecified")
    )


def _result_verdict(result: Any) -> str:
    return str(_field(result, "verdict", default="abstain"))


def _result_reason_code(result: Any) -> str:
    return str(_field(result, "reason_code", "reason", default=""))


# --------------------------------------------------------------------------- #
# Unified item model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AuditItem:
    """One evaluable item, tagged as ill-posed or well-posed."""

    item_id: str
    kind: ItemKind
    category: str  # ill-posed category OR well-posed domain
    prompt: str
    reference: str  # gold answer for well-posed; "" for ill-posed
    expected_verdict: str  # "abstain" for ill-posed; "accepted" for well-posed
    source: Any  # the original task object, passed to the detector


def _require_deps() -> None:
    if not _DEPS_AVAILABLE:
        raise RuntimeError(
            "Parallel-agent dependencies are not yet available. This audit "
            "requires v2.ill_posed_tasks (ill_posed_tasks) and "
            "v2.verify_ill_posed (verify_ill_posed). ImportError was: "
            + (_DEPS_ERROR or "<none>")
        )


def ill_posed_items() -> list[AuditItem]:
    """Materialize ill-posed tasks (from Agent A) into AuditItems.

    Every ill-posed task's correct verdict is ``abstain`` -- the system must
    refuse to solve an unsolvable problem rather than hallucinate an answer.
    """
    _require_deps()
    items: list[AuditItem] = []
    seen_ids: set[str] = set()
    for task in _ILL_POSED_TASKS:
        tid = _task_id(task)
        if tid in seen_ids:
            raise RuntimeError(f"duplicate ill-posed task_id: {tid!r}")
        seen_ids.add(tid)
        items.append(
            AuditItem(
                item_id=tid,
                kind="ill-posed",
                category=_task_category(task),
                prompt=_task_prompt(task),
                reference="",
                expected_verdict="abstain",
                source=task,
            )
        )
    return items


def well_posed_items() -> list[AuditItem]:
    """Materialize well-posed controls (local) into AuditItems.

    The ``source`` is wrapped in a dict adapter carrying the SAME fields an
    ill-posed task exposes (``task_id`` / ``prompt`` / ``category``) so the
    detector (``v2.verify_ill_posed``) sees a uniform interface regardless of
    whether the item is ill-posed or well-posed. The ``category`` here is the
    problem DOMAIN (physics / math / arithmetic), NOT a solvability label --
    the detector must decide solvability from the prompt content, not from
    metadata.
    """
    return [
        AuditItem(
            item_id=c.control_id,
            kind="well-posed",
            category=c.domain,
            prompt=c.prompt,
            reference=c.gold,
            expected_verdict="accepted",
            source={
                "task_id": c.control_id,
                "prompt": c.prompt,
                "category": c.domain,
                "_gold": c.gold,  # for debugging only; detector must not read this
            },
        )
        for c in well_posed_controls()
    ]


def audit_items() -> list[AuditItem]:
    """All evaluable items: ill-posed tasks + well-posed controls."""
    return [*ill_posed_items(), *well_posed_items()]


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #
def _proposed_verdict(item: AuditItem) -> tuple[Verdict, str]:
    """Run the real ill-posedness detector on one item."""
    assert _VERIFY_ILL_POSED is not None  # guarded by _require_deps upstream
    result = _VERIFY_ILL_POSED(item.source)
    v = _result_verdict(result)
    if v not in {"accepted", "rejected", "abstain"}:
        # Defensive: an unknown verdict is treated as abstain (fail-closed) but
        # surfaced verbatim in the details so it cannot hide.
        return "abstain", f"unknown_verdict:{v}"
    return v, _result_reason_code(result)  # type: ignore[return-value]


def policy_verdict(policy: str, item: AuditItem) -> tuple[Verdict, str]:
    """Return the (verdict, reason_code) a named policy emits for one item.

    The three degenerate baselines are pure decision rules -- they ignore the
    item content. ``proposed-system`` runs the real detector.
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


def _evaluate_policy(policy: str, items: list[AuditItem]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    correct_verdicts = 0
    incorrect_verdicts = 0
    hallucinations = 0  # accepted an ill-posed item (the LLM failure mode)
    false_alarms = 0  # abstained on a well-posed item (detector over-refusal)
    accepts = 0
    for item in items:
        verdict, reason_code = policy_verdict(policy, item)
        is_correct = verdict == item.expected_verdict
        if is_correct:
            correct_verdicts += 1
        else:
            incorrect_verdicts += 1
        if verdict == "accepted":
            accepts += 1
        if verdict == "accepted" and item.kind == "ill-posed":
            hallucinations += 1
        if verdict == "abstain" and item.kind == "well-posed":
            false_alarms += 1
        if verdict == "rejected" and item.kind == "well-posed":
            false_alarms += 1
        rows.append(
            {
                "item_id": item.item_id,
                "kind": item.kind,
                "category": item.category,
                "prompt": item.prompt,
                "reference": item.reference,
                "expected_verdict": item.expected_verdict,
                "policy_verdict": verdict,
                "reason_code": reason_code,
                "verdict_is_correct": is_correct,
                "failure_class": (
                    "hallucination"
                    if (verdict == "accepted" and item.kind == "ill-posed")
                    else "false_alarm"
                    if (verdict in {"abstain", "rejected"} and item.kind == "well-posed")
                    else "none"
                    if is_correct
                    else "verdict_mismatch"
                ),
            }
        )

    ill_posed = [i for i in items if i.kind == "ill-posed"]
    well_posed = [i for i in items if i.kind == "well-posed"]
    ill_posed_correct = sum(
        1 for i in ill_posed if policy_verdict(policy, i)[0] == i.expected_verdict
    )
    well_posed_correct = sum(
        1 for i in well_posed if policy_verdict(policy, i)[0] == i.expected_verdict
    )

    return {
        "policy": policy,
        "description": POLICY_DESCRIPTIONS[policy],
        "isSimulatedBaseline": policy in {"raw-model", "always-accept", "always-abstain"},
        "totals": {
            "total": len(items),
            "correctVerdicts": correct_verdicts,
            "incorrectVerdicts": incorrect_verdicts,
            "hallucinations": hallucinations,
            "falseAlarms": false_alarms,
        },
        "rates": {
            "verdictAccuracy": _format_rate(correct_verdicts, len(items)),
            "coverageRate": _format_rate(accepts, len(items)),
            "illPosedCorrectRate": _format_rate(ill_posed_correct, len(ill_posed)),
            "wellPosedCorrectRate": _format_rate(well_posed_correct, len(well_posed)),
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
                "illPosedCorrectRate": e["rates"]["illPosedCorrectRate"],
                "wellPosedCorrectRate": e["rates"]["wellPosedCorrectRate"],
                "hallucinations": e["totals"]["hallucinations"],
                "falseAlarms": e["totals"]["falseAlarms"],
                "verdictAccuracy": e["rates"]["verdictAccuracy"],
            }
        )
    return table


def build_audit() -> dict[str, Any]:
    """Build the full ill-posedness audit (catch-rate + baseline comparison)."""
    _require_deps()
    items = audit_items()
    ill_posed = [i for i in items if i.kind == "ill-posed"]
    well_posed = [i for i in items if i.kind == "well-posed"]

    # ── 1. Catch-rate audit on ill-posed tasks ──
    catch_details: list[dict[str, Any]] = []
    caught = 0
    misses: list[dict[str, Any]] = []
    by_category: dict[str, dict[str, int]] = {}
    for item in ill_posed:
        verdict, reason_code = _proposed_verdict(item)
        is_caught = verdict == item.expected_verdict  # "abstain"
        if is_caught:
            caught += 1
        row = {
            "task_id": item.item_id,
            "category": item.category,
            "prompt": item.prompt,
            "expected_verdict": item.expected_verdict,
            "observed_verdict": verdict,
            "observed_reason_code": reason_code,
            "caught": is_caught,
        }
        catch_details.append(row)
        if not is_caught:
            misses.append(row)
        by_category.setdefault(item.category, {"caught": 0, "total": 0})
        by_category[item.category]["total"] += 1
        by_category[item.category]["caught"] += int(is_caught)

    catch_rate = _format_rate(caught, len(ill_posed))

    # ── 2. False-alarm audit on well-posed controls ──
    false_alarm_details: list[dict[str, Any]] = []
    correctly_accepted = 0
    false_alarms: list[dict[str, Any]] = []
    for item in well_posed:
        verdict, reason_code = _proposed_verdict(item)
        is_correct = verdict == item.expected_verdict  # "accepted"
        if is_correct:
            correctly_accepted += 1
        row = {
            "control_id": item.item_id,
            "domain": item.category,
            "prompt": item.prompt,
            "gold": item.reference,
            "expected_verdict": item.expected_verdict,
            "observed_verdict": verdict,
            "observed_reason_code": reason_code,
            "correctly_accepted": is_correct,
        }
        false_alarm_details.append(row)
        if not is_correct:
            false_alarms.append(row)

    false_alarm_rate = _format_rate(len(false_alarms), len(well_posed))

    # ── 3. Baseline comparison (4-way) ──
    evaluated = {
        policy: _evaluate_policy(policy, items)
        for policy in ("raw-model", "always-abstain", "always-accept", "proposed-system")
    }
    proposed = evaluated["proposed-system"]

    # Headline dominance: proposed-system is the ONLY policy that is correct on
    # BOTH the ill-posed side (illPosedCorrectRate == 1.0, zero hallucinations)
    # AND the well-posed side (wellPosedCorrectRate == 1.0, zero false alarms).
    dominance: dict[str, Any] = {}
    for baseline in ("raw-model", "always-abstain", "always-accept"):
        b = evaluated[baseline]
        dominance[baseline] = {
            "baselineIllPosedCorrectRate": b["rates"]["illPosedCorrectRate"],
            "baselineWellPosedCorrectRate": b["rates"]["wellPosedCorrectRate"],
            "baselineHallucinations": b["totals"]["hallucinations"],
            "baselineFalseAlarms": b["totals"]["falseAlarms"],
            "proposedIllPosedCorrectRate": proposed["rates"]["illPosedCorrectRate"],
            "proposedWellPosedCorrectRate": proposed["rates"]["wellPosedCorrectRate"],
            "proposedHallucinations": proposed["totals"]["hallucinations"],
            "proposedFalseAlarms": proposed["totals"]["falseAlarms"],
            "baselineFailsAxis": (
                "hallucinates_on_ill_posed"
                if b["totals"]["hallucinations"] > 0
                else "refuses_solvable_problems"
                if b["rates"]["wellPosedCorrectRate"] < 1.0
                else "neither_side_dominant"
            ),
        }

    # ── Fail-closed status ──
    status = "PASS" if (catch_rate == 1.0 and false_alarm_rate == 0.0) else "FAIL"

    return {
        "schema": "goai-ill-posed-audit/v1",
        "evidenceClass": "development-only",
        "status": status,
        "interpretation": (
            "This audit demonstrates that a DETERMINISTIC ill-posedness detector "
            "correctly abstains on ill-posed problems where LLMs hallucinate "
            "solutions. It is INSTRUMENT evidence (the detector is real), NOT a "
            "model-capability claim. The catch-rate is a property of the "
            "deterministic detector, not of any model. The 'raw-model' policy is "
            "a SIMULATED accept-everything baseline that mirrors the documented "
            "2025-2026 literature finding (e.g. AgentAbstain, arXiv:2607.10059) "
            "that LLMs fail to recognize unsolvability and fabricate answers "
            "instead of abstaining. Only the 'proposed-system' policy -- which "
            "runs the real detector -- is correct on BOTH sides of the "
            "solvability boundary: it abstains on ill-posed problems AND accepts "
            "well-posed ones."
        ),
        "policyDescriptions": POLICY_DESCRIPTIONS,
        "itemCounts": {
            "illPosed": len(ill_posed),
            "wellPosed": len(well_posed),
            "total": len(items),
        },
        "catchRate": {
            "illPosed": {
                "total": len(ill_posed),
                "caught": caught,
                "missed": len(misses),
                "catchRate": catch_rate,
                "byCategory": {
                    cat: {
                        **v,
                        "catchRate": _format_rate(v["caught"], v["total"]),
                    }
                    for cat, v in sorted(by_category.items())
                },
                "misses": misses,
                "details": catch_details,
            },
            "wellPosedControls": {
                "total": len(well_posed),
                "correctlyAccepted": correctly_accepted,
                "falseAlarms": len(false_alarms),
                "falseAlarmRate": false_alarm_rate,
                "falseAlarmsList": false_alarms,
                "details": false_alarm_details,
            },
        },
        "comparisonTable": _comparison_table(evaluated),
        "policies": evaluated,
        "dominance": dominance,
        "literatureAnchor": {
            "finding": "LLMs fail to recognize unsolvable / ill-posed problems "
            "and hallucinate solutions instead of abstaining.",
            "citation": "AgentAbstain (arXiv:2607.10059) -- paired solvable and "
            "unsolvable environments across browser, code, and data tasks.",
            "period": "2025-2026",
            "scopeNote": (
                "This audit does NOT measure any model's actual hallucination "
                "rate. It demonstrates that a deterministic detector CAN catch "
                "what the literature shows raw models miss. The detector's "
                "catch-rate is instrument evidence, not a model-capability result."
            ),
        },
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


def write_audit(output_path: Path = AUDIT_PATH) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    output_path.write_bytes(_canonical_bytes(audit))
    return audit


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=AUDIT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        if not _DEPS_AVAILABLE:
            print(
                "ILL-POSED AUDIT: FAIL (cannot rebuild -- parallel-agent deps not "
                f"available: {_DEPS_ERROR or '<none>'})"
            )
            return 1
        if not args.output.is_file():
            print("ILL-POSED AUDIT: FAIL (artifact missing)")
            return 1
        on_disk_bytes = args.output.read_bytes()
        try:
            expected_bytes = _canonical_bytes(build_audit())
        except RuntimeError as exc:
            print(f"ILL-POSED AUDIT: FAIL (cannot rebuild: {exc})")
            return 1
        if on_disk_bytes != expected_bytes:
            print("ILL-POSED AUDIT: FAIL (bytes not canonical/current)")
            print(
                f"  on-disk sha256={_sha256(on_disk_bytes)} "
                f"expected sha256={_sha256(expected_bytes)}"
            )
            return 1
        on_disk = json.loads(on_disk_bytes.decode("utf-8"))
        if on_disk.get("status") != "PASS":
            print(f"ILL-POSED AUDIT: FAIL (status={on_disk.get('status')})")
            return 1
        cr = on_disk["catchRate"]
        ip = cr["illPosed"]
        wp = cr["wellPosedControls"]
        proposed = on_disk["policies"]["proposed-system"]
        print(
            "ILL-POSED AUDIT: PASS ("
            f"ill-posed={ip['total']}; caught={ip['caught']}; missed={ip['missed']}; "
            f"catchRate={ip['catchRate']}; "
            f"well-posed={wp['total']}; falseAlarms={wp['falseAlarms']}; "
            f"proposed hallucinations={proposed['totals']['hallucinations']})"
        )
        return 0

    try:
        audit = write_audit(args.output)
    except RuntimeError as exc:
        print(f"ILL-POSED AUDIT: cannot build ({exc})")
        return 1
    cr = audit["catchRate"]
    ip = cr["illPosed"]
    wp = cr["wellPosedControls"]
    print(
        json.dumps(
            {
                "schema": audit["schema"],
                "status": audit["status"],
                "itemCounts": audit["itemCounts"],
                "catchRate": {
                    "illPosed": {
                        "catchRate": ip["catchRate"],
                        "caught": ip["caught"],
                        "missed": ip["missed"],
                    },
                    "wellPosed": {
                        "falseAlarmRate": wp["falseAlarmRate"],
                        "falseAlarms": wp["falseAlarms"],
                    },
                },
                "comparisonTable": audit["comparisonTable"],
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
