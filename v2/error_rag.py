#!/usr/bin/env python3
"""RAG-assisted *proposal* scaffolding for novel logic-error verifier rules.

This module is a development-only scaffold. It demonstrates how an agent can
RETRIEVE similar known error patterns from an embedded knowledge base and
PROPOSE a structured verifier-rule candidate for a novel error type it has not
seen before.

What this is, and is not
------------------------
- This is **RAG-assisted PROPOSAL generation**, not RAG-assisted VERDICT. The
  retrieval here helps an agent draft a new deterministic check; the check
  itself only runs *after* a human approves the proposal.
- The retrieval is pure-stdlib keyword Jaccard similarity (3+-char tokens),
  matching the style of ``agent/retrieval.py``'s ``_score`` helper. There are no
  embedding models and no external API calls.
- The proposed rule follows the spirit of :class:`frontier.FrontierProposal`:
  ``candidateOnly=True``, ``canClaimAGI=False`` — an advisory candidate, never
  self-promoting, never a contest-performance or capability result.

The knowledge base is drawn from the planted-error taxonomy in
``build_logic_error_audit.py`` (dimension_mismatch, not_equivalent,
proof_placeholder, sign_error, ...) plus provenance-grounding patterns from
``verify_provenance.py`` (lineage_merge, misattribution).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
DEFAULT_OUTPUT = HERE / "artifacts"
AUDIT_PATH = DEFAULT_OUTPUT / "error-rag-audit.json"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# Mirrors the claim ceiling used across the package: every artifact is
# development-only and cannot be promoted to a scientific / capability claim.
CLAIM_CEILING = {
    "candidateOnly": True,
    "canClaimAGI": False,
    "winnerLevelEligible": False,
    "winnerLevelGateMet": False,
}

# Tier vocabulary shared with build_logic_error_audit.py (si / sympy /
# lean-placeholder) plus the provenance-grounding tier from verify_provenance.py.
TIERS = ("si", "sympy", "lean", "provenance")

# Minimum Jaccard similarity for a retrieval hit to count as "matched" when
# deciding whether a proposed rule WOULD catch a novel error. Below this the
# retrieval is recorded but the proposal is marked low-confidence and the
# would-catch heuristic returns False (fail-closed for genuinely-unseen cases).
MIN_CONFIDENCE = 0.20


# ──────────────────────────────────────────────────────────────────── knowledge base


@dataclass(frozen=True)
class KnownErrorPattern:
    """One entry in the embedded error-knowledge base.

    Each pattern pairs a known error type with the deterministic verifier rule
    that catches it. These are the patterns the retriever compares novel
    descriptions against.
    """

    error_type: str
    tier: str  # one of TIERS
    description: str
    example_candidate: str
    example_reference: str
    verifier_rule: str  # a short, human-readable description of the deterministic check
    claim_ceiling: str = "development-only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "tier": self.tier,
            "description": self.description,
            "example_candidate": self.example_candidate,
            "example_reference": self.example_reference,
            "verifier_rule": self.verifier_rule,
            "claim_ceiling": self.claim_ceiling,
        }


def _p(
    error_type: str,
    tier: str,
    description: str,
    example_candidate: str,
    example_reference: str,
    verifier_rule: str,
) -> KnownErrorPattern:
    return KnownErrorPattern(
        error_type=error_type,
        tier=tier,
        description=description,
        example_candidate=example_candidate,
        example_reference=example_reference,
        verifier_rule=verifier_rule,
    )


def knowledge_base() -> list[KnownErrorPattern]:
    """The frozen embedded knowledge base of known error patterns.

    ~20 patterns drawn from the planted-error taxonomy plus provenance
    grounding. Each entry is human-curated and corresponds to a real
    deterministic verifier rule already exercised by the package.
    """
    return [
        # ── SI dimension / value logic errors (tier: si) ──
        _p(
            "dimension_mismatch", "si",
            "candidate and reference have incompatible physical dimensions, e.g. "
            "comparing a velocity in m/s to an acceleration in m/s^2",
            "9.8 m/s^2", "9.8 m/s",
            "parse SI units from candidate and reference into base dimensions "
            "(M, L, T, ...) and reject if the dimension vectors differ",
        ),
        _p(
            "force_vs_mass_mismatch", "si",
            "force unit Newton compared to a mass unit kilogram — same kind of "
            "dimension mismatch but in a different physical quantity",
            "5 kg", "5 N",
            "reject when the candidate's SI base-dimension vector does not equal "
            "the reference's base-dimension vector",
        ),
        _p(
            "energy_vs_power_mismatch", "si",
            "energy unit Joule compared to power unit Watt — dimension mismatch "
            "between work and rate of work",
            "12 W", "12 J",
            "reject when candidate and reference reduce to different SI base "
            "dimensions even after unit simplification",
        ),
        _p(
            "pressure_vs_force_mismatch", "si",
            "pressure unit Pascal compared to force unit Newton — dimension "
            "mismatch between distributed and concentrated quantities",
            "100 Pa", "100 N",
            "reject on differing SI base-dimension vectors (L^-1 M T^-2 vs M L T^-2)",
        ),
        _p(
            "value_outside_tolerance", "si",
            "dimensions match but the numeric value differs from the reference "
            "beyond the declared relative tolerance",
            "8.0 m/s", "9.8 m/s",
            "after dimension agreement, compare numeric magnitudes with rtol and "
            "reject if |candidate - reference| / |reference| > rtol",
        ),
        _p(
            "gross_value_error", "si",
            "dimensions match but the candidate value is off by orders of "
            "magnitude, indicating a likely unit-prefix or transcription error",
            "50.0 m/s", "9.8 m/s",
            "reject when the numeric magnitude falls outside the tolerance band "
            "by a large factor",
        ),
        # ── SymPy equivalence logic errors (tier: sympy) ──
        _p(
            "not_equivalent", "sympy",
            "candidate expression is not symbolically equivalent to the reference "
            "expression under sympy.simplify of the difference",
            "x^2+2*x+2", "(x+1)^2",
            "compute simplify(sympy_candidate - sympy_reference); reject if it "
            "does not reduce to zero",
        ),
        _p(
            "sign_error", "sympy",
            "candidate has the correct structure but a wrong sign on a term, so "
            "the symbolic difference is a non-zero constant or polynomial",
            "x^2-2*x+1", "(x+1)^2",
            "symbolic equivalence check rejects any non-zero simplified "
            "difference, including sign-flipped terms",
        ),
        _p(
            "missing_term", "sympy",
            "candidate omits a term present in the reference, leaving the "
            "simplified difference non-zero",
            "2*x+1", "(x+1)^2",
            "reject when simplify(candidate - reference) != 0 (a dropped term "
            "survives simplification)",
        ),
        _p(
            "wrong_degree", "sympy",
            "candidate is a polynomial of a different degree than the reference, "
            "so the two cannot be equivalent",
            "x^3+1", "(x+1)^2",
            "symbolic equivalence check rejects differing polynomial degrees",
        ),
        _p(
            "factorization_error", "sympy",
            "candidate is the expanded form of the reference with one factor "
            "wrong, so simplification does not collapse to zero",
            "x^2+1", "(x+1)^2",
            "reject on simplify(candidate - reference) != 0",
        ),
        # ── Lean proof-placeholder logic errors (tier: lean) ──
        _p(
            "proof_placeholder", "lean",
            "candidate proof uses a placeholder tactic (sorry / admit) instead of "
            "a real proof term",
            "sorry", "have h : True := trivial",
            "scan the candidate proof source for sorry/admit tokens and reject "
            "before any coverage abstention fires",
        ),
        _p(
            "admit_placeholder", "lean",
            "candidate proof uses the admit tactic to discharge a goal without "
            "justification",
            "admit", "have h : True := trivial",
            "reject any proof term containing the admit placeholder token",
        ),
        _p(
            "incomplete_proof", "lean",
            "candidate proof leaves goals open or uses pseudo/axiom-backed "
            "shims rather than a closed derivation",
            "by sorry", "rfl",
            "reject candidate proofs that contain placeholder or pseudo-proof "
            "tokens before invoking the kernel",
        ),
        # ── Provenance grounding logic errors (tier: provenance) ──
        _p(
            "lineage_merge", "provenance",
            "candidate attributes a work to an author documented as a "
            "do-not-attribute lineage-merge for that work",
            "Hesiod", "Homeric Hymns",
            "look up the work's doNotAttributeTo list and reject if the claimed "
            "author appears in it",
        ),
        _p(
            "misattribution", "provenance",
            "candidate attributes a work to an author that contradicts every "
            "documented gold author for that work",
            "Plato", "Iliad",
            "match the claimed author against the work's gold-author set; reject "
            "if it matches none",
        ),
        _p(
            "uncertain_authorship_assertion", "provenance",
            "candidate asserts a single author for a work with legendary or "
            "compiled authorship confidence",
            "the poet", "Homeric Hymns",
            "for works flagged legendary/compiled, abstain rather than accept any "
            "single-author assertion",
        ),
        _p(
            "unsupported_work_assertion", "provenance",
            "candidate asserts an attribution for a work outside the verifier's "
            "knowledge base, with no executable check to decide it",
            "Anon", "Lost Epic",
            "for off-KB works, abstain (fail-closed) rather than vouch for the "
            "assertion",
        ),
        # ── Cross-cutting structural patterns ──
        _p(
            "reason_code_mismatch", "sympy",
            "candidate passes structural shape but the verifier's declared reason "
            "code does not match the expected failure reason",
            "x^2+2*x+2", "(x+1)^2",
            "after rejecting, assert the emitted reason_code equals the expected "
            "symbolic-inequivalence code",
        ),
        _p(
            "tier_routing_error", "si",
            "candidate is routed to the wrong verifier tier, so the check that "
            "should reject it never runs",
            "9.8 m/s^2", "9.8 m/s",
            "validate the tier label before dispatch and reject misrouted "
            "candidates with a routing reason code",
        ),
    ]


# ──────────────────────────────────────────────────────────────────── retrieval


_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def _tokenize(text: str) -> set[str]:
    """3+-character lowercase alphanumeric tokens (style of agent/retrieval.py).

    Symbols and operators (x^2, m/s, *, +) are deliberately dropped — retrieval
    is over the *natural-language description* of the error, not the candidate
    expression itself.
    """
    return set(_TOKEN_RE.findall(text.lower()))


def _jaccard(query_tokens: set[str], body_tokens: set[str]) -> float:
    """Token-set Jaccard similarity: |A ∩ B| / |A ∪ B|."""
    if not query_tokens or not body_tokens:
        return 0.0
    inter = len(query_tokens & body_tokens)
    if inter == 0:
        return 0.0
    return inter / len(query_tokens | body_tokens)


def _pattern_text(pattern: KnownErrorPattern) -> str:
    """The full searchable surface for one knowledge-base entry."""
    return " ".join(
        [
            pattern.error_type.replace("_", " "),
            pattern.tier,
            pattern.description,
            pattern.verifier_rule,
            pattern.example_candidate,
            pattern.example_reference,
        ]
    )


@dataclass(frozen=True)
class RetrievalHit:
    """One retrieved knowledge-base pattern with its similarity score."""

    pattern: KnownErrorPattern
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.pattern.error_type,
            "tier": self.pattern.tier,
            "score": round(self.score, 4),
            "verifier_rule": self.pattern.verifier_rule,
        }


def retrieve_similar_errors(
    candidate_description: str, top_k: int = 3
) -> list[RetrievalHit]:
    """Return the ``top_k`` most similar known error patterns.

    Similarity is symmetric Jaccard over 3+-char tokens of the candidate
    description against each pattern's full searchable surface (error type,
    tier, description, verifier rule, and example fields). Ties are broken by
    the knowledge-base order so retrieval is deterministic.
    """
    if top_k <= 0:
        return []
    query_tokens = _tokenize(candidate_description)
    scored: list[tuple[float, int, KnownErrorPattern]] = []
    for idx, pattern in enumerate(knowledge_base()):
        score = _jaccard(query_tokens, _tokenize(_pattern_text(pattern)))
        scored.append((score, idx, pattern))
    # Sort by descending score, ascending index for deterministic tie-breaking.
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [RetrievalHit(p, s) for s, _, p in scored[:top_k] if s > 0.0]


# ──────────────────────────────────────────────────────────────────── proposal


@dataclass(frozen=True)
class NovelError:
    """A novel error type not present in the embedded knowledge base."""

    error_id: str
    description: str
    example_candidate: str = ""
    example_reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_id": self.error_id,
            "description": self.description,
            "example_candidate": self.example_candidate,
            "example_reference": self.example_reference,
        }


@dataclass(frozen=True)
class VerifierRuleProposal:
    """A STRUCTURED, advisory proposal for a new deterministic verifier rule.

    Mirrors the discipline of :class:`frontier.FrontierProposal`: it is a
    candidate only, never self-approving, never a capability claim. The
    ``candidate_verifier`` field holds the human-readable rule the agent
    proposes; the ``approval_status`` is always ``pending`` until a human
    reviewer signs off.
    """

    schema: str
    proposal_id: str
    novel_error_id: str
    proposed_tier: str
    summary: str
    candidate_verifier: str
    retrieved_basis: tuple[str, ...]  # error_types the proposal is grounded in
    top_similarity: float
    confidence: str  # "high" | "medium" | "low"
    approval_status: str = "pending"  # always pending — human must approve
    candidateOnly: bool = True
    canClaimAGI: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "proposalId": self.proposal_id,
            "novelErrorId": self.novel_error_id,
            "proposedTier": self.proposed_tier,
            "summary": self.summary,
            "candidateVerifier": self.candidate_verifier,
            "retrievedBasis": list(self.retrieved_basis),
            "topSimilarity": round(self.top_similarity, 4),
            "confidence": self.confidence,
            "approvalStatus": self.approval_status,
            "candidateOnly": self.candidateOnly,
            "canClaimAGI": self.canClaimAGI,
        }


def _confidence_for(score: float) -> str:
    if score >= 0.30:
        return "high"
    if score >= MIN_CONFIDENCE:
        return "medium"
    return "low"


def _pick_tier(hits: list[RetrievalHit]) -> str:
    """Plurality vote over the tiers of the retrieved hits."""
    if not hits:
        return "unspecified"
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.pattern.tier] = counts.get(hit.pattern.tier, 0) + 1
    # Tie-break by tier vocabulary order, then alphabetical, for determinism.
    order = {t: i for i, t in enumerate(TIERS)}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], order.get(kv[0], 99), kv[0]))
    return ranked[0][0]


def _synthesize_verifier(
    novel: NovelError, hits: list[RetrievalHit]
) -> str:
    """Compose a human-readable candidate verifier rule from retrieved patterns.

    The rule explicitly names the patterns it generalizes and ends with the
    advisory that it must be reviewed and turned into a deterministic check
    before use.
    """
    if not hits:
        return (
            "No sufficiently similar known pattern was retrieved. Draft a new "
            "deterministic check from first principles and review before use."
        )
    basis_rules = "; ".join(
        f"{hit.pattern.error_type} -> {hit.pattern.verifier_rule}" for hit in hits
    )
    top = hits[0].pattern
    return (
        f"Generalize the {top.tier}-tier check that catches "
        f"'{top.error_type}' ({top.verifier_rule}). Apply the same shape to the "
        f"novel case described as: \"{novel.description}\". Retrieved patterns "
        f"informing this draft: {basis_rules}. "
        f"This is advisory only — a human must approve it and turn it into a "
        f"deterministic, fail-closed verifier before it can affect any verdict."
    )


def propose_new_verifier_rule(
    novel_error: NovelError,
    similar_errors: list[RetrievalHit],
) -> VerifierRuleProposal:
    """Generate a structured, advisory proposal for a new verifier rule.

    The proposal is grounded in ``similar_errors`` (the output of
    :func:`retrieve_similar_errors`). It never auto-approves: the
    ``approval_status`` is always ``pending`` and ``candidateOnly`` is always
    ``True``.
    """
    top_score = similar_errors[0].score if similar_errors else 0.0
    tier = _pick_tier(similar_errors)
    basis = tuple(hit.pattern.error_type for hit in similar_errors)
    summary = (
        f"Propose a new {tier}-tier deterministic check for novel error "
        f"'{novel_error.error_id}', grounded in {len(similar_errors)} retrieved "
        f"known pattern(s). Advisory only — pending human approval."
    )
    candidate_verifier = _synthesize_verifier(novel_error, similar_errors)
    return VerifierRuleProposal(
        schema="goai-error-rag-proposal/v1",
        proposal_id=f"{novel_error.error_id}:rag-proposal",
        novel_error_id=novel_error.error_id,
        proposed_tier=tier,
        summary=summary,
        candidate_verifier=candidate_verifier,
        retrieved_basis=basis,
        top_similarity=top_score,
        confidence=_confidence_for(top_score),
    )


# ──────────────────────────────────────────────────────────────────── dry-run check


def _would_proposal_catch_error(
    proposal: VerifierRuleProposal,
    hits: list[RetrievalHit],
    *,
    min_confidence: float = MIN_CONFIDENCE,
) -> bool:
    """Heuristic: would the *proposed* rule, if implemented, plausibly catch the
    novel error?

    This is a development-only heuristic that says "the retrieval surfaced a
    pattern similar enough that generalizing its rule would plausibly cover the
    novel case". It is NOT a verdict and does not run any check. A real
    implementation requires human approval + a deterministic verifier.
    """
    if not hits:
        return False
    if proposal.confidence == "low":
        return False
    return hits[0].score >= min_confidence


# ──────────────────────────────────────────────────────────────────── audit


def novel_errors() -> list[NovelError]:
    """A frozen set of *novel* error descriptions not in the knowledge base.

    These exercise the retriever against descriptions the KB has not seen
    verbatim: some are paraphrases of known patterns (high retrieval), others
    are genuinely new shapes (low retrieval) to show the fail-closed path.
    """
    return [
        NovelError(
            "novel-units-mismatch",
            "candidate acceleration in meters per second squared is compared to a "
            "reference velocity in meters per second so the units disagree",
            "3.0 m/s^2", "3.0 m/s",
        ),
        NovelError(
            "novel-symbolic-nonequivalence",
            "candidate expression simplifies to a different polynomial than the "
            "reference so they are not symbolically equivalent",
            "x^2+3*x+1", "(x+1)^2",
        ),
        NovelError(
            "novel-proof-gap",
            "candidate proof contains a placeholder gap admitted without a real "
            "justification term",
            "by admit", "rfl",
        ),
        NovelError(
            "novel-wrong-attribution",
            "candidate attributes a work to an author that contradicts the "
            "documented gold author lineage",
            "Aristotle", "Iliad",
        ),
        NovelError(
            "novel-completely-unseen",
            "florp zibbering quax — a wholly invented failure mode with no "
            "physical symbolic proof or provenance analogue anywhere",
            "42 glops", "7 smurfs",
        ),
    ]


def run_error_rag_audit(
    *, novels: list[NovelError] | None = None, top_k: int = 3
) -> dict[str, Any]:
    """Run the RAG-assisted proposal audit over a set of novel errors.

    For each novel error: retrieve similar known patterns, generate a proposed
    verifier rule, and record whether the proposed rule (if implemented) would
    plausibly catch the error. Produces the audit payload written to
    ``v2/artifacts/error-rag-audit.json``.
    """
    novels = novels if novels is not None else novel_errors()
    entries: list[dict[str, Any]] = []
    would_catch_count = 0
    for novel in novels:
        hits = retrieve_similar_errors(novel.description, top_k=top_k)
        proposal = propose_new_verifier_rule(novel, hits)
        would_catch = _would_proposal_catch_error(proposal, hits)
        would_catch_count += int(would_catch)
        entries.append(
            {
                "novel_error": novel.to_dict(),
                "retrieved_patterns": [h.to_dict() for h in hits],
                "proposed_rule": proposal.to_dict(),
                "would_catch_if_implemented": would_catch,
            }
        )
    total = len(entries)
    return {
        "schema": "goai-error-rag-audit/v1",
        "evidenceClass": "development-only",
        "interpretation": (
            "RAG-assisted PROPOSAL generation for novel verifier rules. The "
            "retrieval surfaces similar known error patterns; the agent proposes "
            "a structured, advisory rule. The proposal is candidate-only and "
            "PENDING human approval — it never issues a verdict. The "
            "'wouldCatchIfImplemented' flag is a development-only heuristic, "
            "not a model-capability or contest-performance result."
        ),
        "method": {
            "retriever": "stdlib keyword Jaccard over 3+-char tokens (no embeddings)",
            "top_k": top_k,
            "min_confidence": MIN_CONFIDENCE,
            "knowledge_base_size": len(knowledge_base()),
        },
        "totals": {
            "novel_errors": total,
            "would_catch_if_implemented": would_catch_count,
            "low_confidence_proposals": sum(
                1 for e in entries if e["proposed_rule"]["confidence"] == "low"
            ),
        },
        "entries": entries,
        "scientificOutcome": False,
        "capabilityClaim": False,
        **CLAIM_CEILING,
    }


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_audit(output_path: Path = AUDIT_PATH) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit = run_error_rag_audit()
    output_path.write_bytes(_canonical_bytes(audit))
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAG-assisted novel-error verifier-rule proposal scaffold."
    )
    parser.add_argument("--output", type=Path, default=AUDIT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        if not args.output.is_file():
            print("ERROR RAG AUDIT: FAIL (artifact missing)")
            return 1
        on_disk = json.loads(args.output.read_text(encoding="utf-8"))
        expected = _canonical_bytes(run_error_rag_audit())
        if args.output.read_bytes() != expected:
            print("ERROR RAG AUDIT: FAIL (bytes not canonical/current)")
            return 1
        t = on_disk["totals"]
        print(
            f"ERROR RAG AUDIT: PASS (novel={t['novel_errors']}; "
            f"wouldCatch={t['would_catch_if_implemented']}; "
            f"lowConfidence={t['low_confidence_proposals']})"
        )
        return 0

    audit = write_audit(args.output)
    t = audit["totals"]
    print(
        json.dumps(
            {
                "schema": audit["schema"],
                "method": audit["method"],
                "totals": t,
                **CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
