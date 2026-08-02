#!/usr/bin/env python3
"""Tests for the deterministic provenance-verification tier."""
from __future__ import annotations

import unittest

from v2.verify_provenance import (
    CLAIM_CEILING,
    DO_NOT_ATTRIBUTE_TO,
    TRUE_KB,
    UNCERTAIN_CONFIDENCE,
    ProvenanceResult,
    verify_provenance,
    verify_provenance_text,
)


class ProvenanceVerifierTests(unittest.TestCase):
    def test_accepted_when_claimed_matches_gold(self) -> None:
        for claim, work in [
            ("Plato", "The Republic"),
            ("Marcus Aurelius", "Meditations"),
            ("Confucius", "Analects"),
            ("Arrian", "Enchiridion"),
        ]:
            r = verify_provenance(claim, work)
            self.assertEqual(r.verdict, "accepted", f"{claim} → {work}")
            self.assertEqual(r.reason_code, "grounding_match")
            self.assertEqual(r.tier, "provenance-grounding")

    def test_accepted_normalizes_qualifiers(self) -> None:
        r = verify_provenance(
            "Confucius (compiled by his disciples)", "Analects"
        )
        self.assertEqual(r.verdict, "accepted")

    def test_rejected_for_lineage_merge(self) -> None:
        for claim, work in [
            ("Socrates", "The Republic"),
            ("Epictetus", "Meditations"),
            ("Marcus Aurelius", "Enchiridion"),
            ("Seneca", "Meditations"),
        ]:
            r = verify_provenance(claim, work)
            self.assertEqual(r.verdict, "rejected", f"{claim} → {work}")
            self.assertEqual(r.reason_code, "lineage_merge")

    def test_rejected_for_misattribution_against_gold(self) -> None:
        r = verify_provenance("Herodotus", "The Republic")
        self.assertEqual(r.verdict, "rejected")
        self.assertEqual(r.reason_code, "misattribution")

    def test_abstain_for_uncertain_confidence(self) -> None:
        for work in ["Dao De Jing", "Zhuangzi", "I Ching"]:
            r = verify_provenance("Anyone", work)
            self.assertEqual(r.verdict, "abstain", work)
            self.assertEqual(r.reason_code, "uncertain_authorship")

    def test_abstain_for_off_kb_work(self) -> None:
        r = verify_provenance("Kant", "Critique of Judgment")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unsupported_specification")

    def test_abstain_for_unparseable_work(self) -> None:
        r = verify_provenance("Plato", "")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "unparseable_work")

    def test_never_silent_pass_on_uncertain(self) -> None:
        """A legendary work must never be accepted — abstain, not silent pass."""
        r = verify_provenance("Laozi", "Dao De Jing")
        self.assertNotEqual(r.verdict, "accepted")

    def test_claim_ceiling_preserved(self) -> None:
        r = verify_provenance("Plato", "The Republic")
        d = r.to_dict()
        self.assertTrue(d["candidateOnly"])
        self.assertFalse(d["canClaimAGI"])

    def test_forbidden_set_disjoint_from_gold(self) -> None:
        """Non-circularity: no author is both gold and forbidden for one work."""
        for work, golds in TRUE_KB.items():
            forbidden = DO_NOT_ATTRIBUTE_TO.get(work, [])
            for f in forbidden:
                from v2.verify_provenance import _normalize_author
                fn = _normalize_author(f)
                self.assertFalse(
                    any(fn == _normalize_author(g) for g in golds),
                    f"{work}: '{f}' is both gold and forbidden",
                )

    def test_uncertain_works_not_acceptable_even_with_correct_author(self) -> None:
        """Even the 'correct' author of a legendary work cannot be accepted."""
        r = verify_provenance("Laozi", "Dao De Jing")
        self.assertEqual(r.verdict, "abstain")


class ProvenanceTextVerifierTests(unittest.TestCase):
    def test_extracts_author_from_text(self) -> None:
        r = verify_provenance_text("Plato wrote the Republic.", "The Republic")
        self.assertEqual(r.verdict, "accepted")

    def test_rejects_proof_placeholder(self) -> None:
        for placeholder in ["sorry", "admit", ""]:
            r = verify_provenance_text(placeholder, "The Republic")
            self.assertEqual(r.verdict, "rejected", repr(placeholder))
            self.assertEqual(r.reason_code, "proof_placeholder")

    def test_abstains_when_no_author_extracted(self) -> None:
        r = verify_provenance_text("the weather is nice", "The Republic")
        self.assertEqual(r.verdict, "abstain")
        self.assertEqual(r.reason_code, "no_author_extracted")

    def test_detects_lineage_merge_in_text(self) -> None:
        r = verify_provenance_text(
            "Socrates is the author of the Republic.", "The Republic"
        )
        self.assertEqual(r.verdict, "rejected")


if __name__ == "__main__":
    unittest.main()
