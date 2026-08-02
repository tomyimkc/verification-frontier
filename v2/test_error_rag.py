#!/usr/bin/env python3
"""Tests for the RAG-assisted novel-error verifier-rule proposal scaffold."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2 import error_rag


class KnowledgeBaseTests(unittest.TestCase):
    def test_knowledge_base_has_about_twenty_patterns(self) -> None:
        kb = error_rag.knowledge_base()
        # ~20 known patterns; require at least 18 to allow minor curation drift.
        self.assertGreaterEqual(len(kb), 18)
        self.assertLessEqual(len(kb), 30)

    def test_every_pattern_uses_a_known_tier(self) -> None:
        for pattern in error_rag.knowledge_base():
            self.assertIn(pattern.tier, error_rag.TIERS, pattern.error_type)

    def test_every_pattern_carrys_a_verifier_rule(self) -> None:
        for pattern in error_rag.knowledge_base():
            self.assertTrue(pattern.verifier_rule.strip(), pattern.error_type)
            self.assertEqual(pattern.claim_ceiling, "development-only")

    def test_known_taxonomy_error_types_are_present(self) -> None:
        types = {p.error_type for p in error_rag.knowledge_base()}
        for expected in (
            "dimension_mismatch",
            "not_equivalent",
            "proof_placeholder",
            "sign_error",
            "value_outside_tolerance",
        ):
            self.assertIn(expected, types)

    def test_covers_all_four_tiers(self) -> None:
        tiers = {p.tier for p in error_rag.knowledge_base()}
        self.assertEqual(tiers, set(error_rag.TIERS))


class RetrieverTests(unittest.TestCase):
    def test_tokenize_drops_short_tokens_and_symbols(self) -> None:
        # 3+-char alphanumeric only; operators and 1-2 char tokens dropped.
        self.assertEqual(error_rag._tokenize("x^2 + ab the"), {"the"})

    def test_jaccard_basic(self) -> None:
        self.assertEqual(error_rag._jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(error_rag._jaccard(set(), {"a"}), 0.0)
        self.assertEqual(error_rag._jaccard({"a"}, set()), 0.0)

    def test_retrieve_returns_at_most_top_k(self) -> None:
        hits = error_rag.retrieve_similar_errors("dimension mismatch units", top_k=2)
        self.assertLessEqual(len(hits), 2)
        self.assertGreater(len(hits), 0)

    def test_retrieve_is_sorted_descending(self) -> None:
        hits = error_rag.retrieve_similar_errors("proof placeholder admit", top_k=5)
        scores = [h.score for h in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_retrieve_finds_dimension_mismatch_for_units_query(self) -> None:
        hits = error_rag.retrieve_similar_errors(
            "candidate and reference have incompatible physical dimensions", top_k=3
        )
        self.assertTrue(hits, "expected at least one hit")
        self.assertEqual(hits[0].pattern.error_type, "dimension_mismatch")

    def test_retrieve_finds_proof_placeholder_for_sorry_query(self) -> None:
        hits = error_rag.retrieve_similar_errors(
            "candidate proof uses sorry admit placeholder tactic", top_k=3
        )
        top_types = {h.pattern.error_type for h in hits[:2]}
        self.assertTrue(top_types & {"proof_placeholder", "admit_placeholder"})

    def test_retrieve_finds_lineage_for_attribution_query(self) -> None:
        hits = error_rag.retrieve_similar_errors(
            "attributes a work to a forbidden lineage merge author", top_k=3
        )
        top_types = {h.pattern.error_type for h in hits[:2]}
        self.assertTrue(top_types & {"lineage_merge", "misattribution"})

    def test_retrieve_top_k_zero_returns_empty(self) -> None:
        self.assertEqual(error_rag.retrieve_similar_errors("dimension", top_k=0), [])

    def test_retrieve_is_deterministic(self) -> None:
        a = error_rag.retrieve_similar_errors("symbolic equivalence sign", top_k=4)
        b = error_rag.retrieve_similar_errors("symbolic equivalence sign", top_k=4)
        self.assertEqual([h.pattern.error_type for h in a], [h.pattern.error_type for h in b])
        self.assertEqual([h.score for h in a], [h.score for h in b])


class ProposalTests(unittest.TestCase):
    def test_proposal_is_advisory_and_pending(self) -> None:
        novel = error_rag.NovelError(
            "novel-1", "incompatible physical dimensions mismatch"
        )
        hits = error_rag.retrieve_similar_errors(novel.description, top_k=3)
        proposal = error_rag.propose_new_verifier_rule(novel, hits)
        self.assertEqual(proposal.approval_status, "pending")
        self.assertTrue(proposal.candidateOnly)
        self.assertFalse(proposal.canClaimAGI)
        self.assertEqual(proposal.schema, "goai-error-rag-proposal/v1")

    def test_proposal_grounded_in_retrieved_basis(self) -> None:
        novel = error_rag.NovelError(
            "novel-2", "candidate proof uses a sorry placeholder"
        )
        hits = error_rag.retrieve_similar_errors(novel.description, top_k=3)
        proposal = error_rag.propose_new_verifier_rule(novel, hits)
        self.assertTrue(proposal.retrieved_basis, "expected non-empty basis")
        self.assertIn("advisory only", proposal.candidate_verifier)

    def test_proposal_with_no_hits_is_low_confidence_and_unspecified(self) -> None:
        novel = error_rag.NovelError("novel-3", "zzz qqq xyzzy")
        proposal = error_rag.propose_new_verifier_rule(novel, [])
        self.assertEqual(proposal.confidence, "low")
        self.assertEqual(proposal.proposed_tier, "unspecified")
        self.assertEqual(proposal.top_similarity, 0.0)
        self.assertIn("No sufficiently similar", proposal.candidate_verifier)

    def test_proposed_tier_is_a_valid_tier_when_hits_exist(self) -> None:
        novel = error_rag.NovelError("novel-4", "units dimension mismatch")
        hits = error_rag.retrieve_similar_errors(novel.description, top_k=3)
        proposal = error_rag.propose_new_verifier_rule(novel, hits)
        self.assertIn(proposal.proposed_tier, error_rag.TIERS)


class WouldCatchHeuristicTests(unittest.TestCase):
    def test_low_confidence_does_not_catch(self) -> None:
        novel = error_rag.NovelError("n", "zzz qqq xyzzy nonsense")
        hits = error_rag.retrieve_similar_errors(novel.description, top_k=3)
        proposal = error_rag.propose_new_verifier_rule(novel, hits)
        self.assertFalse(error_rag._would_proposal_catch_error(proposal, hits))

    def test_similar_pattern_would_catch(self) -> None:
        novel = error_rag.NovelError(
            "n", "candidate and reference have incompatible physical dimensions"
        )
        hits = error_rag.retrieve_similar_errors(novel.description, top_k=3)
        proposal = error_rag.propose_new_verifier_rule(novel, hits)
        self.assertTrue(error_rag._would_proposal_catch_error(proposal, hits))


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = error_rag.run_error_rag_audit()

    def test_schema_and_evidence_class(self) -> None:
        self.assertEqual(self.audit["schema"], "goai-error-rag-audit/v1")
        self.assertEqual(self.audit["evidenceClass"], "development-only")

    def test_claim_ceiling_preserved(self) -> None:
        self.assertTrue(self.audit["candidateOnly"])
        self.assertFalse(self.audit["canClaimAGI"])
        self.assertFalse(self.audit["winnerLevelEligible"])
        self.assertFalse(self.audit["winnerLevelGateMet"])
        self.assertFalse(self.audit["scientificOutcome"])
        self.assertFalse(self.audit["capabilityClaim"])

    def test_method_is_pure_stdlib(self) -> None:
        method = self.audit["method"]
        self.assertIn("no embeddings", method["retriever"])
        self.assertEqual(method["knowledge_base_size"], len(error_rag.knowledge_base()))

    def test_totals_are_consistent_with_entries(self) -> None:
        entries = self.audit["entries"]
        totals = self.audit["totals"]
        self.assertEqual(totals["novel_errors"], len(entries))
        self.assertEqual(
            totals["would_catch_if_implemented"],
            sum(1 for e in entries if e["would_catch_if_implemented"]),
        )
        self.assertEqual(
            totals["low_confidence_proposals"],
            sum(1 for e in entries if e["proposed_rule"]["confidence"] == "low"),
        )

    def test_every_proposal_is_pending_and_candidate_only(self) -> None:
        for entry in self.audit["entries"]:
            rule = entry["proposed_rule"]
            self.assertEqual(rule["approvalStatus"], "pending", entry["novel_error"]["error_id"])
            self.assertTrue(rule["candidateOnly"])
            self.assertFalse(rule["canClaimAGI"])

    def test_unseen_error_is_low_confidence_and_not_caught(self) -> None:
        unseen = [e for e in self.audit["entries"] if "unseen" in e["novel_error"]["error_id"]]
        self.assertTrue(unseen, "expected a completely-unseen novel error")
        self.assertEqual(unseen[0]["proposed_rule"]["confidence"], "low")
        self.assertFalse(unseen[0]["would_catch_if_implemented"])

    def test_at_least_one_known_paraphrase_would_be_caught(self) -> None:
        caught = sum(1 for e in self.audit["entries"] if e["would_catch_if_implemented"])
        self.assertGreater(caught, 0, "expected at least one paraphrased novel error to be caught")


class WriteAndCheckTests(unittest.TestCase):
    def test_write_then_check_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "error-rag-audit.json"
            error_rag.write_audit(out)
            self.assertTrue(out.is_file())
            expected = error_rag._canonical_bytes(error_rag.run_error_rag_audit())
            self.assertEqual(out.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
