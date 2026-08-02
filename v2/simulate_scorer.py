#!/usr/bin/env python3
"""Deterministic operating-characteristic simulation for the frozen scorer gate.

The simulation exercises the same family-cluster bootstrap, sign-flip, and
winner-threshold logic used by ``confirmatory_scoring.py``.  It uses synthetic
family deltas only and therefore remains development-only instrument evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from v2.confirmatory_scoring import _cluster_bootstrap, _mean, _sign_flip

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "artifacts" / "scorer-operating-characteristics.json"
DEFAULT_SIMULATIONS_PER_HYPOTHESIS = 12_000
BOOTSTRAP_SAMPLES = 32
PERMUTATION_SAMPLES = 64
DOMAINS = ("physics", "symbolic", "lean")
WILSON_Z_95 = 1.959963984540054


def _wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = WILSON_Z_95,
) -> tuple[float, float]:
    """Return the two-sided Wilson score interval for a binomial rate."""
    if total <= 0:
        raise ValueError("Wilson interval total must be positive")
    if successes < 0 or successes > total:
        raise ValueError("Wilson interval successes must be within total")
    rate = successes / total
    z_squared = z * z
    denominator = 1.0 + z_squared / total
    center = (rate + z_squared / (2.0 * total)) / denominator
    radius = (
        z
        * math.sqrt(
            rate * (1.0 - rate) / total
            + z_squared / (4.0 * total * total)
        )
        / denominator
    )
    lower = 0.0 if successes == 0 else max(0.0, center - radius)
    upper = 1.0 if successes == total else min(1.0, center + radius)
    return lower, upper


def evaluate_primary_gate(
    deltas: list[float],
    *,
    model_deltas: tuple[float, float] | None = None,
    unsafe_acceptances: int = 0,
    control_regressions: int = 0,
    independent_clusters: int | None = None,
    bootstrap_samples: int = BOOTSTRAP_SAMPLES,
    permutation_samples: int = PERMUTATION_SAMPLES,
    bootstrap_seed: int = 20_260_731,
    permutation_seed: int = 20_260_732,
) -> dict[str, Any]:
    cluster_deltas = {
        f"family-{index:02d}": value
        for index, value in enumerate(deltas)
    }
    cluster_domains = {
        f"family-{index:02d}": DOMAINS[index % len(DOMAINS)]
        for index in range(len(deltas))
    }
    delta = _mean(deltas)
    ci_low, ci_high = _cluster_bootstrap(
        cluster_deltas,
        cluster_domains,
        bootstrap_samples,
        seed=bootstrap_seed,
    )
    p_value = _sign_flip(
        cluster_deltas,
        permutation_samples,
        seed=permutation_seed,
    )
    if model_deltas is None:
        qwen = _mean(deltas[::2])
        deepseek = _mean(deltas[1::2])
        model_deltas = (qwen, deepseek)
    cluster_count = (
        len(deltas)
        if independent_clusters is None
        else independent_clusters
    )
    thresholds = {
        "zeroUnsafeAcceptances": unsafe_acceptances == 0,
        "deltaAtLeast20pp": delta >= 0.20,
        "ciLowerAboveZero": ci_low > 0,
        "pairedPBelow0_05": p_value < 0.05,
        "positiveRequiredModelFamilies": all(
            value > 0 for value in model_deltas
        ),
        "noCoveredControlRegression": control_regressions == 0,
        "minimumIndependentClustersMet": cluster_count >= 30,
    }
    return {
        "deltaSFPA": delta,
        "familyClusterBootstrap95CI": [ci_low, ci_high],
        "familyClusterSignFlipPValue": p_value,
        "modelFamilyDeltas": {
            "qwen": model_deltas[0],
            "deepseek": model_deltas[1],
        },
        "independentClusterCount": cluster_count,
        "unsafeAcceptanceCount": unsafe_acceptances,
        "controlRegressionCount": control_regressions,
        "thresholds": thresholds,
        "gateMet": all(thresholds.values()),
    }


def _draw_null(rng: random.Random) -> list[float]:
    return [
        rng.choices((-1.0, 0.0, 1.0), weights=(1, 2, 1), k=1)[0]
        for _ in range(30)
    ]


def _draw_alternative(rng: random.Random) -> list[float]:
    return [
        rng.choices((-0.5, 0.0, 0.5, 1.0), weights=(1, 2, 10, 7), k=1)[0]
        for _ in range(30)
    ]


def _negative_controls() -> list[tuple[str, dict[str, Any]]]:
    strong = [0.5] * 30
    controls: list[tuple[str, dict[str, Any]]] = [
        (
            "unsafe-acceptance",
            {"deltas": strong, "unsafe_acceptances": 1},
        ),
        (
            "control-regression",
            {"deltas": strong, "control_regressions": 1},
        ),
        (
            "insufficient-clusters",
            {"deltas": strong[:29], "independent_clusters": 29},
        ),
        (
            "delta-below-20pp",
            {"deltas": [0.0] * 24 + [0.5] * 6},
        ),
        (
            "ci-crosses-zero",
            {"deltas": [-1.0] * 8 + [0.0] * 8 + [1.0] * 14},
        ),
        (
            "permutation-not-significant",
            {"deltas": [-0.5, 0.5] * 15},
        ),
        (
            "qwen-direction-negative",
            {"deltas": strong, "model_deltas": (-0.1, 0.5)},
        ),
        (
            "deepseek-direction-negative",
            {"deltas": strong, "model_deltas": (0.5, -0.1)},
        ),
        (
            "both-model-directions-zero",
            {"deltas": strong, "model_deltas": (0.0, 0.0)},
        ),
        (
            "all-zero-null",
            {"deltas": [0.0] * 30},
        ),
        (
            "symmetric-large-null",
            {"deltas": [-1.0, 1.0] * 15},
        ),
        (
            "negative-effect",
            {"deltas": [-0.5] * 30},
        ),
    ]
    return controls


def simulate(
    simulations_per_hypothesis: int = DEFAULT_SIMULATIONS_PER_HYPOTHESIS,
) -> tuple[list[str], dict[str, Any]]:
    if simulations_per_hypothesis <= 0:
        raise ValueError("simulations_per_hypothesis must be positive")
    null_rng = random.Random(20_260_801)
    alternative_rng = random.Random(20_260_802)
    null_gate_count = 0
    alternative_gate_count = 0
    null_delta_sum = 0.0
    alternative_delta_sum = 0.0
    for index in range(simulations_per_hypothesis):
        null_report = evaluate_primary_gate(
            _draw_null(null_rng),
            bootstrap_seed=30_000_000 + index,
            permutation_seed=40_000_000 + index,
        )
        null_gate_count += int(null_report["gateMet"])
        null_delta_sum += float(null_report["deltaSFPA"])
        alternative_report = evaluate_primary_gate(
            _draw_alternative(alternative_rng),
            bootstrap_seed=50_000_000 + index,
            permutation_seed=60_000_000 + index,
        )
        alternative_gate_count += int(alternative_report["gateMet"])
        alternative_delta_sum += float(
            alternative_report["deltaSFPA"]
        )

    negative_controls = []
    errors: list[str] = []
    for index, (control_id, kwargs) in enumerate(_negative_controls()):
        result = evaluate_primary_gate(
            **kwargs,
            bootstrap_seed=70_000_000 + index,
            permutation_seed=80_000_000 + index,
        )
        rejected = not result["gateMet"]
        if not rejected:
            errors.append(f"negative control passed the gate: {control_id}")
        negative_controls.append(
            {
                "controlId": control_id,
                "status": "PASS" if rejected else "FAIL",
                "failedThresholds": sorted(
                    key
                    for key, value in result["thresholds"].items()
                    if not value
                ),
                "deltaSFPA": result["deltaSFPA"],
                "familyClusterBootstrap95CI": result[
                    "familyClusterBootstrap95CI"
                ],
                "familyClusterSignFlipPValue": result[
                    "familyClusterSignFlipPValue"
                ],
            }
        )

    null_false_positive_rate = null_gate_count / simulations_per_hypothesis
    alternative_detection_rate = (
        alternative_gate_count / simulations_per_hypothesis
    )
    null_wilson_low, null_wilson_high = _wilson_interval(
        null_gate_count,
        simulations_per_hypothesis,
    )
    alternative_wilson_low, alternative_wilson_high = _wilson_interval(
        alternative_gate_count,
        simulations_per_hypothesis,
    )
    operating_gates = {
        "nullFalsePositiveWilson95CIUpperAtMost0_05": (
            null_wilson_high <= 0.05
        ),
        "alternativeDetectionWilson95CILowerAtLeast0_80": (
            alternative_wilson_low >= 0.80
        ),
        "allNegativeControlsReject": not errors,
    }
    if not all(operating_gates.values()):
        errors.append("one or more operating-characteristic gates failed")
    report = {
        "schema": "goai-frontier-scorer-operating-characteristics/v2",
        "status": "PASS" if not errors else "INVALID",
        "simulationDesign": {
            "null": "symmetric family deltas in {-1,0,1}",
            "prospectiveAlternative": (
                "large consistent positive family deltas with sparse "
                "zero/negative heterogeneity"
            ),
            "independentClusters": 30,
            "bootstrapSamplesPerSimulation": BOOTSTRAP_SAMPLES,
            "permutationSamplesPerSimulation": PERMUTATION_SAMPLES,
            "sameFrozenFunctionsAsScorer": [
                "_cluster_bootstrap",
                "_sign_flip",
            ],
            "interpretation": (
                "development-only implementation smoke at one easy "
                "alternative point; not confirmatory power or MDE evidence"
            ),
        },
        "nullSimulations": simulations_per_hypothesis,
        "prospectiveAlternativeSimulations": simulations_per_hypothesis,
        "nullGateCount": null_gate_count,
        "nullFalsePositiveRate": null_false_positive_rate,
        "nullFalsePositiveWilson95CI": [
            null_wilson_low,
            null_wilson_high,
        ],
        "nullMeanDelta": null_delta_sum / simulations_per_hypothesis,
        "prospectiveAlternativeGateCount": alternative_gate_count,
        "prospectiveAlternativeDetectionRate": alternative_detection_rate,
        "prospectiveAlternativeDetectionWilson95CI": [
            alternative_wilson_low,
            alternative_wilson_high,
        ],
        "prospectiveAlternativeMeanDelta": (
            alternative_delta_sum / simulations_per_hypothesis
        ),
        "negativeControlCount": len(negative_controls),
        "negativeControls": negative_controls,
        "operatingCharacteristicGates": operating_gates,
        "errors": errors,
        "confirmatoryPowerAnalysisComplete": False,
        "scientificOutcome": False,
        "statisticsEligible": False,
        "confirmatoryEligible": False,
        "winnerLevelEligible": False,
        "winnerLevelGateMet": False,
        "modelContact": False,
        "modelCallCount": 0,
        "networkCallCount": 0,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--simulations-per-hypothesis",
        type=int,
        default=DEFAULT_SIMULATIONS_PER_HYPOTHESIS,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    errors, report = simulate(args.simulations_per_hypothesis)
    expected = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if args.check:
        if not args.output.is_file() or args.output.read_text(
            encoding="utf-8"
        ) != expected:
            print(f"SCORER OPERATING CHARACTERISTICS STALE: {args.output}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected, encoding="utf-8")
    print(
        "SCORER OPERATING CHARACTERISTICS: "
        f"{report['status']} "
        f"(null={report['nullGateCount']}/{report['nullSimulations']}; "
        "alternative="
        f"{report['prospectiveAlternativeGateCount']}/"
        f"{report['prospectiveAlternativeSimulations']}; "
        f"negativeControls={report['negativeControlCount']})"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
