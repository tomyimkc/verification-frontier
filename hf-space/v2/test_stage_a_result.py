#!/usr/bin/env python3
"""Tests for the sanitized Stage A development-result artifact."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from v2 import build_stage_a_result


class StageADevelopmentResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = build_stage_a_result.build_result()

    def test_builds_and_validates_with_fail_closed_claim_ceiling(self) -> None:
        self.assertEqual(
            build_stage_a_result.validate_result(self.result), []
        )
        self.assertTrue(self.result["candidateOnly"])
        self.assertFalse(self.result["canClaimAGI"])
        self.assertFalse(self.result["winnerLevelEligible"])
        self.assertFalse(self.result["winnerLevelGateMet"])
        self.assertFalse(self.result["scientificOutcome"])
        self.assertFalse(self.result["capabilityClaim"])
        self.assertFalse(self.result["confirmatoryEligible"])
        self.assertFalse(self.result["activationAuthorized"])

    def test_binds_exact_authorized_run_head_and_model_revision(self) -> None:
        run = self.result["run"]
        self.assertEqual(run["runId"], build_stage_a_result.RUN_ID)
        self.assertEqual(run["mergedHeadSha"], build_stage_a_result.MERGED_HEAD_SHA)
        self.assertEqual(run["gpuHolder"], build_stage_a_result.GPU_HOLDER)
        model = self.result["model"]
        self.assertEqual(
            model["immutableRevision"], build_stage_a_result.MODEL_REVISION
        )
        artifact = self.result["artifact"]
        self.assertEqual(
            artifact["uploadSha256"], build_stage_a_result.ARTIFACT_UPLOAD_SHA256
        )

    def test_preserves_24_family_balance_and_23_24_denominator(self) -> None:
        balance = self.result["familyBalance"]
        self.assertEqual(balance["familyCount"], 24)
        self.assertEqual(
            balance["domainCounts"], {"physics": 8, "symbolic": 8, "lean": 8}
        )
        structured = self.result["structuredOutput"]
        self.assertEqual(structured["denominator"], 24)
        self.assertEqual(structured["jsonParseValid"], 23)
        self.assertEqual(structured["proposalValid"], 23)
        self.assertEqual(structured["invalidCount"], 1)
        self.assertEqual(
            structured["invalidFamilyId"],
            "stage-a-lean-01-executable-contract",
        )
        self.assertTrue(structured["invalidResponseRetained"])

    def test_malformed_error_text_is_preserved_exactly(self) -> None:
        self.assertIn(
            "Invalid control character",
            self.result["structuredOutput"]["invalidError"],
        )

    def test_all_seven_policy_totals_are_zero(self) -> None:
        policy = self.result["policyViolationTotals"]
        self.assertEqual(len(policy), 7)
        self.assertTrue(all(value == 0 for value in policy.values()))

    def test_open_controls_preserved_as_non_promotable(self) -> None:
        preservation = self.result["openControlPreservation"]
        self.assertEqual(preservation["openControlFamilies"], 2)
        self.assertEqual(preservation["preservedAsNonPromotableAbstentions"], 2)

    def test_every_execution_approval_and_activation_gate_is_zero(self) -> None:
        gates = self.result["gates"]
        self.assertTrue(gates)
        self.assertTrue(all(value == 0 for value in gates.values()))

    def test_interpretation_boundary_is_present_and_clamped(self) -> None:
        interp = self.result["interpretation"]
        self.assertIn("AGI", interp["isNotEvidenceOf"])
        self.assertIn("verifier extension", interp["isNotEvidenceOf"])
        self.assertTrue(
            any(
                "structured-output compliance" in claim
                for claim in interp["isEvidenceOf"]
            )
        )

    def test_cleaner_rate_fabrication_is_rejected(self) -> None:
        inflated = copy.deepcopy(self.result)
        inflated["structuredOutput"]["jsonParseValid"] = 24
        inflated["structuredOutput"]["proposalValid"] = 24
        inflated["structuredOutput"]["invalidCount"] = 0
        errors = build_stage_a_result.validate_result(inflated)
        self.assertTrue(errors)

    def test_removing_malformed_disclosure_is_rejected(self) -> None:
        redacted = copy.deepcopy(self.result)
        redacted["structuredOutput"]["invalidResponseRetained"] = False
        errors = build_stage_a_result.validate_result(redacted)
        self.assertTrue(errors)

    def test_relaxing_claim_ceiling_is_rejected(self) -> None:
        overclaim = copy.deepcopy(self.result)
        overclaim["canClaimAGI"] = True
        errors = build_stage_a_result.validate_result(overclaim)
        self.assertTrue(errors)

    def test_write_then_check_round_trips_canonical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "stage-a-development-result.json"
            build_stage_a_result.write_result(out)
            reread = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(build_stage_a_result.validate_result(reread), [])
            expected = build_stage_a_result._canonical_bytes(
                build_stage_a_result.build_result()
            )
            self.assertEqual(out.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
