# Independent expert-AI correctness audit

**Review date:** July 31, 2026  
**Scope:** public package, hosted demo, receipt protocol, and scorer  
**Review mode:** read-only adversarial correctness review  
**Initial verdict:** **NO-GO for hosted deployment** and **NO-GO for
confirmatory execution**

The reviewer found one critical hosted-demo defect and seven evidence,
portability, or schema defects. The current development branch implements the
following dispositions; final merge still requires the complete package suite
and an independent re-audit.

## Finding dispositions

### P0 — public symbolic parser evaluated Python

The original SymPy `parse_expr` path could evaluate attacker-controlled Python.

**Disposition:** replaced by a restricted Python-AST reader that directly
constructs SymPy nodes. Calls, attributes, subscripts, strings, comprehensions,
unknown syntax, oversized inputs, deep ASTs, huge integers, and large or
non-literal exponents fail closed. Regression tests cover `eval`, `exec`,
`__import__`, attributes, subscripts, oversized inputs, and exponent abuse.

### P1 — receipt chains were not bound to scored task/family identity

**Disposition:** proposal and chain receipts now bind domain, generator family,
extension class, trigger task, task-manifest hash, and extension identity.
Scoring passes the exact manifest task into receipt validation. Transfer IDs
must resolve to valid members in the same sealed manifest, domain, family, and
extension class. Cross-domain and cross-family reuse fail.

### P1 — evidence hashes did not resolve to evidence bytes

**Disposition:** candidate, test output, base verifier, extension bundle,
protected-suite manifest/output, rollback output, and Lean source/stdout/stderr
hashes now resolve through a content-addressed blob store. Missing, symlinked,
or mutated blobs fail. The public rehearsal contains 45 evidence blobs in
addition to 28 JSON receipts.

### P1 — development fixtures could set a winner flag

**Disposition:** development scoring reports `status:"DEVELOPMENT_ONLY"`,
`protocolValid:true`, `winnerLevelEligible:false`, and
`winnerLevelGateMet:false`. The winner calculation remains ineligible unless a
future reviewed code change allows confirmatory receipts. Confirmatory model
execution remains unconditionally disabled.

### P2 — public validation artifact leaked an absolute local path

**Disposition:** the strict Lean receipt now records portable Lean version,
repository, project label, and commit identity. Bundle validation rejects
host-local paths in public JSON/JSONL artifacts.

### P2 — rehearsal rebuilding could delete unrelated JSON

**Disposition:** the builder requires a dedicated store marker and refuses to
clean unmarked or unexpected content. A regression test confirms an unrelated
sentinel survives a refused build.

### P2 — documented camelCase schemas serialized as snake_case

**Disposition:** public proposal, decision, verification-result, and expansion
receipt serializers are explicit and tested against exact key contracts.

### P2 — hosted status displayed unvalidated seal metadata

**Disposition:** one strict public-seal validator now checks schema, counts,
claim ceiling, status, hashes, and `outcomesViewedAtSeal:false`. Public status
returns an explicit validation state; the provider-free healthcheck fails when
the seal is invalid.

## Remaining boundary

These corrections address public deployment safety and development evidence
integrity. They do not supply a private 30-family benchmark, real independent
review decisions, confirmatory transfer outcomes, mandatory ablations, power
validation, scientific-domain review, or OS-level Lean sandboxing.

**Current verdict remains:** **NO-GO for confirmatory execution** and
**CONDITIONAL GO for preliminary upload as an infrastructure proposal**.

`candidateOnly:true`; `canClaimAGI:false`.

## Final re-audit

After the dispositions above, the same independent reviewer returned
**GO for merging this development milestone** and found no remaining P0/P1
defects. The re-audit verified 58 focused tests, the 7/7 receipt benchmark,
bundle validation, claims lint, nested-power rejection, and hard-disabled
winner eligibility.

The re-audit separately retained **NO-GO for confirmatory execution**.
