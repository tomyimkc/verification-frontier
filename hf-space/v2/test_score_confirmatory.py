#!/usr/bin/env python3
"""Tests for strict family-clustered SFPA scoring."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from v2 import score_confirmatory
from v2.build_receipt_rehearsal import build_chain
from v2.protocol_twin import build_protocol_twin, validate_protocol_twin
from v2.receipt_protocol import validate_extension_chain, write_blob
from v2.study_root import build_study_materials

ARMS = (
    "B0-raw-model",
    "B1-fixed-verifier",
    "B2-fixed-refinement",
    "B3-act-or-abstain",
    "B4-human-only",
    "B5-proposed",
)
MODELS = ("qwen", "deepseek")


def tasks() -> list[dict]:
    rows: list[dict] = []
    for domain in ("physics", "symbolic", "lean"):
        for family_index in range(10):
            family = f"{domain}-family-{family_index:02d}"
            for sibling in range(2):
                pair_id = f"{family}-pair-{sibling}"
                for member in ("valid", "safety"):
                    rows.append(
                        {
                            "taskId": f"{pair_id}-{member}",
                            "pairId": pair_id,
                            "domain": domain,
                            "component": "frontier",
                            "member": member,
                            "generatorFamily": family,
                            "extensionClass": f"{domain}.class-{family_index:02d}",
                        }
                    )
        for control in range(4):
            pair_id = f"{domain}-control-{control:02d}"
            for member in ("valid", "safety"):
                rows.append(
                    {
                        "taskId": f"{pair_id}-{member}",
                        "pairId": pair_id,
                        "domain": domain,
                        "component": "control",
                        "member": member,
                        "generatorFamily": f"{domain}-control-family-{control:02d}",
                        "extensionClass": f"{domain}.covered-control",
                    }
                )
    return rows


def transfer_tasks() -> list[dict]:
    rows: list[dict] = []
    for domain in ("physics", "symbolic", "lean"):
        for family_index in range(10):
            family = f"{domain}-family-{family_index:02d}"
            extension_class = f"{domain}.class-{family_index:02d}"
            for sibling in range(2):
                pair_id = f"{family}-transfer-{sibling}"
                for member in ("valid", "safety"):
                    rows.append(
                        {
                            "schema": "goai-frontier-transfer-task/v1",
                            "taskId": f"{pair_id}-{member}",
                            "pairId": pair_id,
                            "domain": domain,
                            "component": "transfer",
                            "member": member,
                            "generatorFamily": family,
                            "extensionClass": extension_class,
                            "candidateOnly": True,
                            "canClaimAGI": False,
                        }
                    )
    return rows


def result(
    task: dict,
    *,
    arm: str,
    model: str,
    replicate: int,
    decision: str,
    receipt: dict | None = None,
) -> dict:
    row = {
        "schema": "goai-frontier-confirmatory-result/v1",
        "taskId": task["taskId"],
        "pairId": task["pairId"],
        "domain": task["domain"],
        "generatorFamily": task["generatorFamily"],
        "extensionClass": task["extensionClass"],
        "arm": arm,
        "modelFamily": model,
        "replicate": replicate,
        "decision": decision,
        "protectedSuitePassed": True,
        "candidateOnly": True,
        "canClaimAGI": False,
    }
    if arm == "B5-proposed" and task["component"] == "frontier" and task["member"] == "valid":
        if receipt is None:
            raise ValueError("proposed-arm valid rows require a receipt chain")
        row.update(
            {
                "transferPassed": True,
                "transferTaskIds": receipt["transferTaskIds"],
                "extensionReceiptSha256": receipt["chainSha256"],
                "reviewDecisionSha256s": receipt["reviewDecisionSha256s"],
                "protectedSuiteReceiptSha256": receipt[
                    "protectedSuiteReceiptSha256"
                ],
            }
        )
    return row


class ScoreConfirmatoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.receipt_store = root / "receipts"
        self.tasks = tasks()
        self.transfer_tasks = transfer_tasks()
        manifest_sha256 = write_blob(
            self.receipt_store,
            score_confirmatory.task_manifest_bytes(self.tasks),
        )
        transfer_manifest_sha256 = write_blob(
            self.receipt_store,
            score_confirmatory.task_manifest_bytes(self.transfer_tasks),
        )
        self.receipts: dict[str, dict] = {}
        frontier_families = sorted(
            {
                task["generatorFamily"]
                for task in self.tasks
                if task["component"] == "frontier"
            }
        )
        for family in frontier_families:
            family_tasks = [
                task
                for task in self.tasks
                if task["generatorFamily"] == family
                and task["component"] == "frontier"
            ]
            domain = family_tasks[0]["domain"]
            extension_class = family_tasks[0]["extensionClass"]
            family_transfer_tasks = [
                task
                for task in self.transfer_tasks
                if task["generatorFamily"] == family
            ]
            for trigger_task in (
                task for task in family_tasks if task["member"] == "valid"
            ):
                transfer_ids = sorted(
                    task["taskId"]
                    for task in family_transfer_tasks
                    if task["member"] == "valid"
                )
                digest = build_chain(
                    self.receipt_store,
                    domain,
                    generator_family=family,
                    extension_class=extension_class,
                    task_manifest_sha256=manifest_sha256,
                    transfer_task_manifest_sha256=transfer_manifest_sha256,
                    trigger_task_id=trigger_task["taskId"],
                    transfer_ids=transfer_ids,
                )
                chain_errors, report = validate_extension_chain(
                    self.receipt_store,
                    digest,
                )
                self.assertEqual(chain_errors, [])
                self.receipts[trigger_task["taskId"]] = report
        self.frontier_pairs = sorted(
            {task["pairId"] for task in self.tasks if task["component"] == "frontier"}
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def complete_results(self, proposed_success_pairs: int = 30) -> list[dict]:
        successful = set(self.frontier_pairs[:proposed_success_pairs])
        rows: list[dict] = []
        for arm in ARMS:
            for model in MODELS:
                for replicate in range(3):
                    for task in self.tasks:
                        if task["component"] == "control":
                            decision = "accepted" if task["member"] == "valid" else "rejected"
                        elif task["member"] == "safety":
                            decision = "rejected"
                        elif arm == "B5-proposed" and task["pairId"] in successful:
                            decision = "accepted"
                        else:
                            decision = "abstain"
                        rows.append(
                            result(
                                task,
                                arm=arm,
                                model=model,
                                replicate=replicate,
                                decision=decision,
                                receipt=self.receipts.get(task["taskId"]),
                            )
                        )
        return rows

    def test_complete_large_safe_effect_passes(self) -> None:
        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=500,
            permutation_samples=2_000,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertEqual(errors, [])
        self.assertEqual(report["pairCount"], 60)
        self.assertEqual(report["independentClusterCount"], 30)
        self.assertEqual(report["status"], "DEVELOPMENT_ONLY")
        self.assertTrue(report["scoringInputsValid"])
        self.assertFalse(report["protocolValid"])
        self.assertFalse(report["studyRootBound"])
        self.assertFalse(report["studyRootScorerInputsBound"])
        self.assertFalse(
            report["constructedArmFixtureRowsValidated"]
        )
        self.assertFalse(
            report["constructedB6FixtureRowsValidated"]
        )
        self.assertFalse(
            report["constructedAblationFixtureRowsValidated"]
        )
        self.assertFalse(report["actualB6RowsValidated"])
        self.assertFalse(report["actualAblationRowsValidated"])
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])
        self.assertTrue(all(report["winnerLevelThresholds"].values()))

    def test_development_study_root_binds_complete_manifests(self) -> None:
        selected = [
            report["chainSha256"]
            for _, report in sorted(self.receipts.items())
            if report["domain"] in {"physics", "symbolic", "lean"}
        ][:3]
        receipt_digests = sorted(
            path.stem for path in self.receipt_store.glob("*.json")
        )
        blob_digests = sorted(
            path.stem
            for path in (self.receipt_store / "blobs").glob("*.blob")
        )
        selected_reports = []
        for digest in selected:
            chain_errors, chain_report = validate_extension_chain(
                self.receipt_store,
                digest,
            )
            self.assertEqual(chain_errors, [])
            selected_reports.append(chain_report)
        receipt_index = {
            "schema": "goai-frontier-receipt-rehearsal-index/v1",
            "status": "PASS",
            "evidenceClass": "development-only",
            "confirmatoryEligible": False,
            "chainSha256s": selected,
            "receiptSha256s": receipt_digests,
            "receiptCount": len(receipt_digests),
            "blobSha256s": blob_digests,
            "blobCount": len(blob_digests),
            "candidateOnly": True,
            "canClaimAGI": False,
        }
        receipt_validation = {
            "schema": "goai-frontier-receipt-rehearsal-validation/v1",
            "status": "PASS",
            "chainCount": len(selected),
            "validChainCount": len(selected),
            "receiptCount": len(receipt_digests),
            "blobCount": len(blob_digests),
            "reports": selected_reports,
            "errors": [],
            "candidateOnly": True,
            "canClaimAGI": False,
        }
        twin = build_protocol_twin()
        twin_errors, twin_validation = validate_protocol_twin(twin)
        self.assertEqual(twin_errors, [])
        root, arms, ablations = build_study_materials(
            twin=twin,
            twin_validation=twin_validation,
            receipt_index=receipt_index,
            receipt_validation=receipt_validation,
            receipt_store=self.receipt_store,
        )
        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
            study_root=root,
            study_arm_results=arms,
            study_ablation_results=ablations,
            study_receipt_index=receipt_index,
            study_receipt_validation=receipt_validation,
        )
        self.assertEqual(errors, [])
        self.assertTrue(report["studyRootBound"])
        self.assertFalse(report["studyRootScorerInputsBound"])
        self.assertTrue(
            report["constructedArmFixtureRowsValidated"]
        )
        self.assertTrue(
            report["constructedB6FixtureRowsValidated"]
        )
        self.assertTrue(
            report["constructedAblationFixtureRowsValidated"]
        )
        self.assertFalse(report["actualB6RowsValidated"])
        self.assertFalse(report["actualAblationRowsValidated"])
        self.assertTrue(report["transferExecutionReceiptsValidated"])
        self.assertFalse(report["protocolValid"])
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])

    def test_missing_baselines_replicates_and_controls_is_invalid(self) -> None:
        rows = [
            row
            for row in self.complete_results(36)
            if row["arm"] in {"B1-fixed-verifier", "B5-proposed"}
            and row["replicate"] == 0
            and next(task for task in self.tasks if task["taskId"] == row["taskId"])[
                "component"
            ]
            == "frontier"
        ]
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertTrue(any("missing required arm/model" in error for error in errors))
        self.assertFalse(report["winnerLevelGateMet"])

    def test_control_regression_fails_gate(self) -> None:
        rows = self.complete_results(36)
        control_id = next(
            task["taskId"]
            for task in self.tasks
            if task["component"] == "control" and task["member"] == "safety"
        )
        for row in rows:
            if row["arm"] == "B5-proposed" and row["taskId"] == control_id:
                row["decision"] = "accepted"
                break
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertEqual(errors, [])
        self.assertGreater(report["controlRegressionCount"], 0)
        self.assertFalse(report["winnerLevelGateMet"])

    def test_model_specific_strongest_baseline_cannot_be_hidden(self) -> None:
        rows = self.complete_results(36)
        pair_rank = {pair_id: index for index, pair_id in enumerate(self.frontier_pairs)}
        task_by_id = {task["taskId"]: task for task in self.tasks}
        for row in rows:
            task = task_by_id[row["taskId"]]
            if task["component"] != "frontier" or task["member"] != "valid":
                continue
            rank = pair_rank[task["pairId"]]
            if row["arm"] == "B1-fixed-verifier":
                row["decision"] = (
                    "accepted"
                    if (
                        row["modelFamily"] == "qwen" and rank < 12
                    )
                    or (
                        row["modelFamily"] == "deepseek" and rank < 36
                    )
                    else "abstain"
                )
            elif row["arm"] == "B4-human-only":
                row["decision"] = (
                    "accepted"
                    if row["modelFamily"] == "qwen" and rank < 48
                    else "abstain"
                )
            elif (
                row["arm"] == "B5-proposed"
                and row["modelFamily"] == "deepseek"
            ):
                row["decision"] = "accepted" if rank < 48 else "abstain"

        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=500,
            permutation_samples=2_000,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            report["strongestNonOracleBaseline"],
            "B1-fixed-verifier",
        )
        self.assertEqual(
            report["modelFamilyStrongestNonOracleBaseline"]["qwen"],
            "B4-human-only",
        )
        self.assertAlmostEqual(report["modelFamilyDeltas"]["qwen"], -0.20)
        self.assertFalse(
            report["winnerLevelThresholds"]["positiveRequiredModelFamilies"]
        )
        self.assertFalse(report["winnerLevelGateMet"])

    def test_unlinked_transfer_receipt_is_invalid(self) -> None:
        rows = self.complete_results(36)
        targets: list[dict] = []
        seen_task_ids: set[str] = set()
        for row in rows:
            if (
                row["arm"] == "B5-proposed"
                and row.get("transferPassed") is True
                and row["taskId"] not in seen_task_ids
            ):
                targets.append(row)
                seen_task_ids.add(row["taskId"])
                if len(targets) == 2:
                    break
        targets[0].pop("extensionReceiptSha256")
        targets[1]["reviewDecisionSha256s"] = []
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertTrue(
            any(
                targets[0]["taskId"] in error and "extension receipt" in error
                for error in errors
            )
        )
        self.assertTrue(
            any(
                targets[1]["taskId"] in error and "review decision" in error
                for error in errors
            )
        )
        self.assertFalse(report["winnerLevelGateMet"])

    def test_receipt_cache_cannot_hide_later_row_identity_corruption(self) -> None:
        rows = self.complete_results(36)
        target = next(
            row
            for row in rows
            if row["arm"] == "B5-proposed"
            and row["replicate"] == 1
            and row.get("transferPassed") is True
        )
        target["domain"] = "lean" if target["domain"] != "lean" else "physics"
        target["generatorFamily"] = "corrupted-family"
        target["extensionClass"] = "corrupted.class"
        target["pairId"] = "corrupted-pair"
        target["schema"] = "corrupted-result-schema"
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertTrue(
            any(
                target["taskId"] in error
                and (
                    "does not match manifest task" in error
                    or "invalid result schema" in error
                )
                for error in errors
            ),
            errors,
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["protocolValid"])
        self.assertFalse(report["winnerLevelGateMet"])

    def test_pseudoreplicated_15_family_pack_cannot_pass(self) -> None:
        rows = self.complete_results(36)
        for task in self.tasks:
            if task["component"] == "frontier":
                task["generatorFamily"] = (
                    f"{task['domain']}-collapsed-{int(task['pairId'].split('-')[-3]) // 2}"
                )
        task_by_id = {task["taskId"]: task for task in self.tasks}
        for row in rows:
            row["generatorFamily"] = task_by_id[row["taskId"]]["generatorFamily"]
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertTrue(any("independent generator" in error for error in errors))
        self.assertLess(report["independentClusterCount"], 30)
        self.assertFalse(report["winnerLevelGateMet"])

    def test_thirty_unbalanced_families_cannot_pass(self) -> None:
        rows = self.complete_results(36)
        for domain in ("physics", "symbolic", "lean"):
            pair_ids = sorted(
                {
                    task["pairId"]
                    for task in self.tasks
                    if task["component"] == "frontier"
                    and task["domain"] == domain
                }
            )
            assignments = {
                pair_id: (
                    f"{domain}-unbalanced-00"
                    if index < 11
                    else f"{domain}-unbalanced-{index - 10:02d}"
                )
                for index, pair_id in enumerate(pair_ids)
            }
            for task in self.tasks:
                if (
                    task["component"] == "frontier"
                    and task["domain"] == domain
                ):
                    task["generatorFamily"] = assignments[task["pairId"]]
        task_by_id = {task["taskId"]: task for task in self.tasks}
        for row in rows:
            row["generatorFamily"] = task_by_id[row["taskId"]]["generatorFamily"]
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertEqual(report["independentClusterCount"], 30)
        self.assertTrue(
            any("expected 2 frontier pairs" in error for error in errors),
            errors,
        )
        self.assertFalse(
            report["winnerLevelThresholds"]["preregisteredClusterStructureMet"]
        )
        self.assertFalse(report["winnerLevelGateMet"])

    def test_malformed_result_returns_invalid_receipt(self) -> None:
        rows = self.complete_results(36)
        rows[0] = {
            "arm": "B0-raw-model",
            "modelFamily": "qwen",
            "replicate": "not-an-integer",
            "taskId": self.tasks[0]["taskId"],
        }
        errors, report = score_confirmatory.score(
            self.tasks,
            rows,
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertTrue(any("malformed result row" in error for error in errors))
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["winnerLevelGateMet"])

    def test_development_receipts_cannot_support_confirmatory_score(self) -> None:
        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            transfer_tasks=self.transfer_tasks,
        )
        self.assertTrue(
            any(
                "evidenceClass must be 'confirmatory'" in error
                for error in errors
            ),
            errors,
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["winnerLevelGateMet"])

    def test_missing_receipt_store_is_invalid(self) -> None:
        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=100,
            permutation_samples=200,
            transfer_tasks=self.transfer_tasks,
        )
        self.assertIn(
            "receipt store is required to verify proposed-arm extension links",
            errors,
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["winnerLevelGateMet"])

    def test_development_scorer_cannot_self_declare_protocol_validity(self) -> None:
        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=self.transfer_tasks,
        )
        self.assertEqual(errors, [])
        self.assertTrue(report["scoringInputsValid"])
        self.assertFalse(report["protocolValid"])
        self.assertFalse(report["studyRootBound"])
        self.assertFalse(report["winnerLevelEligible"])
        self.assertFalse(report["winnerLevelGateMet"])

    def test_missing_auxiliary_transfer_manifest_is_invalid(self) -> None:
        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
        )
        self.assertIn("sealed auxiliary transfer manifest is required", errors)
        self.assertFalse(report["scoringInputsValid"])
        self.assertEqual(report["status"], "INVALID")

    def test_auxiliary_transfer_manifest_must_be_disjoint_from_primary(self) -> None:
        overlapping_transfer_tasks = copy.deepcopy(self.transfer_tasks)
        primary_safety = next(
            task
            for task in self.tasks
            if task["component"] == "frontier"
            and task["member"] == "safety"
        )
        transfer_pair_id = overlapping_transfer_tasks[0]["pairId"]
        for task in overlapping_transfer_tasks:
            if task["pairId"] == transfer_pair_id:
                task["pairId"] = primary_safety["pairId"]
                if task["member"] == "valid":
                    task["taskId"] = primary_safety["taskId"]

        errors, report = score_confirmatory.score(
            self.tasks,
            self.complete_results(36),
            bootstrap_samples=100,
            permutation_samples=200,
            receipt_store=self.receipt_store,
            receipt_evidence_class="development-only",
            transfer_tasks=overlapping_transfer_tasks,
        )
        self.assertTrue(
            any("transfer taskId sets overlap" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("transfer pairId sets overlap" in error for error in errors),
            errors,
        )
        self.assertFalse(report["scoringInputsValid"])
        self.assertEqual(report["status"], "INVALID")
        self.assertFalse(report["winnerLevelGateMet"])


if __name__ == "__main__":
    unittest.main()
