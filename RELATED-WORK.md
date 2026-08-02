> 🌐 简体中文 / Simplified Chinese: [`zh/相关工作.md`](相关工作.md)

# Claim-safe related-work comparison

Checked against public primary sources on 2026-07-31.

## RLVP — Reinforcement Learning with Verifiable Physics

- Reference: arXiv:2607.10474.
- Uses executable PDE solver programs.
- Combines hard program-validity checks with continuous physics-based residual
  and numerical-comparison rewards.
- Therefore it must not be described as a wholly binary verifier.

**Boundary:** this GOAI package is not a physics-RL training method. It exposes
three environment states across compact SI and symbolic checks and records how
reference policies respond.

## EG-VAR — Evidence-Grounded Verified Agentic Reasoning

- Reference: arXiv:2607.12650.
- Uses Lean as kernel authority.
- Treats unresolved residual cases as honest abstention.
- Reports verification-surface behavior rather than validated capability gain.
- Therefore it must not be described as treating abstention merely as a failure
  to minimize.

**Boundary:** this GOAI package emphasizes a small reusable exploration
environment, cross-oracle coverage reasons, deterministic baselines, and JSONL
episode receipts.

## Recursive Epistemic Engines for Verifiable Open-Ended Scientific Agents

- Reference: ICML 2026 AI4Science workshop / OpenReview.
- Defines a “Novelty Horizon” at the joint boundary of generation and
  verification.
- Discusses verifier-defined safe regions and abstention or bounded execution
  beyond that region.
- Therefore this submission does not claim to originate the verification
  frontier or novelty-boundary concept.

**Boundary:** this package is an executable operationalization over SI,
symbolic-equivalence, and external formal-proof evidence, with explicit
contract tests and artifact validation.

## AgentAbstain

- Reference: arXiv:2607.10059.
- Systematically evaluates agentic abstention using paired solvable and
  unsolvable environments across browser, code, and data tasks.
- Therefore calibrated agent abstention is not presented as a new general idea.

**Boundary:** this package focuses on scientific verifier coverage and on
separating executable-check results from items lacking executable scientific
specifications.

## Other adjacent systems

AI Scientist, AI Co-Scientist, Coscientist, and DiscoveryBench address broader
research automation, hypothesis generation, experiment planning, or discovery
evaluation. This submission does not claim that every adjacent system relies
only on an LLM judge. Its narrower claim is that the included correctness path
uses deterministic SI/SymPy checks and records missing coverage explicitly.

## Permitted novelty wording

Use:

> The contest-period contribution is a compact integration: an executable
> three-state verifier-coverage environment, deterministic reference policies,
> iterative JSONL episodes, and explicit separation between model evidence and
> environment-designed abstention.

Do not use:

- “first”;
- “uncrowded cell”;
- “almost no system can verify”;
- “RLVP is binary”;
- “EG-VAR minimizes abstention as failure”;
- “the abstain boundary proves where the model’s knowledge ends”;
- “open-rung abstention proves calibrated model uncertainty.”
