#!/usr/bin/env python3
"""Deterministic provenance-verification tier for the GOAI Open Exploration package.

Composes a grounding oracle (TRUE / MISATTRIBUTION / ABSTAIN) with a
``doNotAttributeTo`` lineage gate, exposing the accepted / rejected / abstain
verdict interface that the verification-frontier environment expects.

This tier is the **primary** domain of the Sample-F (humanities-computing)
reframe: "can an agent safely expand which philosophical attributions it can
verify?" It is grounded in a small, committed, externally-sourced knowledge base
(true attributions) and a non-circular lineage-separation rule set
(``doNotAttributeTo``), both of which are vendored here so the package is
self-contained.

It is **deterministic and fail-closed**: an attribution is accepted only when an
executable check establishes it; rejected only when an executable check refutes
it; abstained whenever no executable check can decide. Coverage is bounded by the
embedded KB: off-KB works abstain rather than guess, which is the point.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# ─────────────────────────────────────────────────────────────────────────────
# Claim ceiling (frozen — must never relax)
# ─────────────────────────────────────────────────────────────────────────────
CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

Verdict = Literal["accepted", "rejected", "abstain"]

# ─────────────────────────────────────────────────────────────────────────────
# Embedded knowledge base (externally sourced, non-circular)
#
# TRUE_KB: work → documented correct author(s). Sourced from Wikidata /
# scholarly consensus. This is the *grounding* oracle, physically separate from
# the gate's doNotAttributeTo rules below (the non-circularity guarantee: the
# rule is the treatment; the label comes from the external citation, not the
# gate).
#
# DO_NOT_ATTRIBUTE_TO: work → authors the work must NOT be attributed to
# (lineage-merges, pseudepigrapha, interlocutor/translator/editor confusions).
# Derived from the corpus dispute docs (docs/04-Disputes/) and the gate records.
#
# UNCERTAIN_CONFIDENCE: works whose authorship is legendary / compiled / partly
# lost → the honest verdict is abstain (no executable check can establish a
# single author), never a silent pass.
# ─────────────────────────────────────────────────────────────────────────────

TRUE_KB: dict[str, list[str]] = {
    "the republic": ["plato"],
    "dao de jing": ["laozi"],
    "analects": ["confucius"],
    "mencius": ["mencius"],
    "zhuangzi": ["zhuang zhou"],
    "nicomachean ethics": ["aristotle"],
    "meditations": ["marcus aurelius"],
    "enchiridion": ["arrian"],
    "the prince": ["niccolo machiavelli"],
    "critique of pure reason": ["immanuel kant"],
    "beyond good and evil": ["friedrich nietzsche"],
    "the communist manifesto": ["karl marx"],
}

# Each work → authors it must NOT be attributed to (lineage separations).
DO_NOT_ATTRIBUTE_TO: dict[str, list[str]] = {
    "dao de jing": ["confucius", "plato", "zhuangzi"],
    "the republic": ["socrates", "aristotle"],
    "analects": ["laozi"],
    "mencius": ["confucius"],
    "meditations": ["epictetus", "seneca"],
    "enchiridion": ["marcus aurelius", "epictetus"],
    "beyond good and evil": ["freud"],
    "the communist manifesto": ["nietzsche"],
    "the prince": ["kant"],
    "zhuangzi": ["laozi", "confucius"],
}

# Works whose authorship confidence is legendary/compiled → abstain, not accept.
UNCERTAIN_CONFIDENCE: set[str] = {
    "dao de jing",  # Laozi historicity provisional
    "zhuangzi",     # inner vs outer chapters; multi-author
    "i ching",      # legendary attribution to Fu Xi / Wen Wang
}

# ─────────────────────────────────────────────────────────────────────────────
# Author normalization (so "Confucius (compiled by his disciples)" ≈ "Confucius")
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_author(name: str) -> str:
    """Lowercase, drop parenthetical/qualifier noise for head comparison."""
    base = re.sub(r"\(.*?\)", "", name or "").lower()
    base = re.split(r"\b(?:and|compiled|attributed|with|recording)\b", base)[0]
    return re.sub(r"[^a-z0-9 ]", "", base).strip()


def _normalize_work(work: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (work or "").lower()).strip()


def _authors_match(claimed: str, gold: str) -> bool:
    c = _normalize_author(claimed)
    g = _normalize_author(gold)
    if not c or not g:
        return False
    return c == g or c in g or g in c


# ───────────────────────────────────────────────────────── determination ─────


@dataclass(frozen=True)
class ProvenanceResult:
    verdict: Verdict
    reason_code: str
    reason: str
    tier: str = "provenance-grounding"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reasonCode": self.reason_code,
            "reason": self.reason,
            "tier": self.tier,
            "candidateOnly": True,
            "canClaimAGI": False,
        }


def _is_forbidden(work: str, claimed_author: str) -> bool:
    """True iff the claimed author is explicitly in the work's doNotAttributeTo list."""
    w = _normalize_work(work)
    forbidden = DO_NOT_ATTRIBUTE_TO.get(w, [])
    claimed = _normalize_author(claimed_author)
    return any(
        claimed and (claimed == _normalize_author(f) or claimed in _normalize_author(f))
        for f in forbidden
    )


def verify_provenance(claimed_author: str, work: str) -> ProvenanceResult:
    """Three-state deterministic verdict for a (claimed_author, work) pair.

    - ``accepted``: the work is in the KB, is not uncertain-confidence, the
      claimed author matches a documented gold author, and the author is not in
      the work's doNotAttributeTo list.
    - ``rejected``: an executable check refutes the attribution — either the
      claimed author is forbidden (lineage merge) or contradicts every gold
      author.
    - ``abstain``: no executable check can decide — the work is off-KB or its
      authorship confidence is legendary/compiled.

    This never guesses. Off-KB works abstain; uncertain-confidence works abstain.
    """
    w = _normalize_work(work)
    if not w:
        return ProvenanceResult(
            "abstain", "unparseable_work",
            "the work cannot be parsed; no executable check can decide",
        )

    # Uncertain-confidence works → abstain (legendary/compiled; never a silent pass).
    if w in UNCERTAIN_CONFIDENCE:
        return ProvenanceResult(
            "abstain", "uncertain_authorship",
            f"'{work}' has legendary/compiled authorship confidence; "
            "no single-author executable check can establish it",
        )

    # Off-KB → abstain (fail-closed: never assert, never vouch).
    gold_authors = TRUE_KB.get(w)
    if not gold_authors:
        return ProvenanceResult(
            "abstain", "unsupported_specification",
            f"'{work}' is outside the current provenance verifier coverage",
        )

    # Forbidden lineage merge → rejected.
    if _is_forbidden(work, claimed_author):
        forbidden = DO_NOT_ATTRIBUTE_TO.get(w, [])
        return ProvenanceResult(
            "rejected", "lineage_merge",
            f"'{claimed_author}' is a documented lineage-merge for '{work}' "
            f"(forbidden: {', '.join(forbidden)})",
        )

    # Grounding: does the claimed author match a gold author?
    if any(_authors_match(claimed_author, g) for g in gold_authors):
        return ProvenanceResult(
            "accepted", "grounding_match",
            f"'{claimed_author}' matches the documented gold author(s) "
            f"for '{work}' ({', '.join(gold_authors)})",
        )

    # In KB but contradicts every gold author → rejected.
    return ProvenanceResult(
        "rejected", "misattribution",
        f"'{claimed_author}' contradicts the documented gold author(s) "
        f"for '{work}' ({', '.join(gold_authors)})",
    )


def verify_provenance_text(candidate_text: str, work: str) -> ProvenanceResult:
    """Verify a free-text candidate answer about a work's authorship.

    Extracts an asserted author from the candidate text (simple heuristic) and
    delegates to :func:`verify_provenance`. This is the demo/episode-facing
    entry point. For model outputs it should be combined with the
    ``provenance_faithful`` clause-scoped gate from the parent repository (not
    vendored here) to detect corrections vs assertions; here we provide the
    deterministic grounding tier only.
    """
    # Reject obvious proof placeholders before any coverage abstention.
    stripped = (candidate_text or "").strip().lower()
    if stripped in {"sorry", "admit", ""}:
        return ProvenanceResult(
            "rejected", "proof_placeholder",
            "'sorry'/'admit'/empty are not authorship certificates",
        )
    # Heuristic: pull the first capitalized author-like token from the text.
    # The demo/episode surface uses this; the model-proposal surface uses the
    # structured (claimed_author, work) form via verify_provenance directly.
    author = _extract_author(candidate_text)
    if author is None:
        return ProvenanceResult(
            "abstain", "no_author_extracted",
            "no authorship assertion could be extracted from the candidate text",
        )
    return verify_provenance(author, work)


_AUTHOR_HINTS = [
    "plato", "socrates", "aristotle", "confucius", "laozi", "mencius",
    "zhuangzi", "marcus aurelius", "epictetus", "arrian", "seneca",
    "nietzsche", "kant", "marx", "machiavelli", "freud",
]


def _extract_author(text: str) -> str | None:
    """Best-effort author extraction from free text (demo-facing only)."""
    low = (text or "").lower()
    for hint in _AUTHOR_HINTS:
        if hint in low:
            return hint
    return None
