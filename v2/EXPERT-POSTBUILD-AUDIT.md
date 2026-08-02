# Independent expert-AI post-build audit

**Review date:** July 31, 2026
**Review mode:** read-only methodology/statistics audit
**Confirmatory outcomes available:** none
**Verdict:** **NO-GO for confirmatory execution**
**Preliminary upload:** **CONDITIONAL GO as an infrastructure proposal**

## Supported infrastructure

- deterministic public development manifest and counts;
- concurrency-safe unique Lean scratch files;
- claim-ceiling propagation;
- bilingual four-page PDFs;
- current ZIP exclusion of seed, private task rows, credentials, and caches;
- provider-free demo logic and no-login configuration;
- direct development-only model receipts with no fallback.

## Critical findings

### 1. Runner/manifest schema mismatch

The first post-build runner read snake-case `task_id`/`split` fields while the
rehearsal manifest used camel-case `taskId`/`component`. A mock sealed run
therefore produced null task IDs and duplicate resume rows.

**Correction:** the runner now supports both schemas, preserves pair/component/
member/family metadata, rejects missing IDs, and has an end-to-end camel-case
resume test.

### 2. Scorer could falsely pass incomplete evidence

The first scorer could pass with one baseline, one replicate, no controls, and
unlinked transfer booleans.

**Correction:** the scorer now requires:

- all B0-B5 arms;
- both required model families;
- exactly three replicates;
- every frontier and control task;
- a passing protected-suite field;
- linked transfer task IDs;
- extension and independent-review SHA-256 references;
- zero covered-control regression.

### 3. Pseudoreplication

The rehearsal’s 60 frontier pairs came from only 15 generator families with four
parameter variants each. Pair-level resampling therefore overstated independent
sample size.

**Correction:** the target preregistration now requires 30 independent
extension/generator families, two frontier pairs per family. SFPA remains a
60-pair metric, but bootstrap and sign-flip inference cluster by family. The
scorer rejects fewer than 30 independent clusters.

### 4. Structural leakage and constructed tasks

The former public generator and oracle revealed family schemas, perturbations,
and decision rules. Lean generation ignored the seed. Measured rehearsal
diagnostics:

- 70/144 exact rows were seed-independent;
- 14 duplicate prompt rows beyond the first occurrence;
- only 15 frontier generator families;
- Lean claim alignment used literal structured-dictionary equality.

**Correction:** the artifacts are renamed `synthetic-rehearsal-*`, marked
`confirmatoryEligible:false`, and blocked by the runner. Generator, oracle,
seed, exact tasks, and rehearsal validator moved behind the ignored private
boundary and are not bundled.

### 5. Human gate remains scaffolded

The environment gate demonstrates owner + expert approval and all-tests-pass
mechanics, but it does not yet enforce the full frozen rubric’s hash-linked
proposal, decision, test-category, activation, transfer, protected-suite, and
rollback lifecycle.

**Required before confirmatory execution:** implement and validate that complete
receipt chain.

### 6. Lean receipt completeness

Unique scratch files and cleanup are supported. Remaining requirements before a
formal confirmatory run include:

- unsafe-escape/introduced-axiom checks beyond `sorry`/`admit`;
- OS-level execution sandboxing;
- source hash, command, timeout, exit status, and output digest in each receipt;
- clean-CI reproduction of both development and future confirmatory checks.

### 7. ZIP/Docker inclusion policy

The ZIP builder now uses an explicit public-file allowlist, and the Dockerfile
copies only the public runtime files required by the demo. The inspected ZIP and
image contain no private generator/oracle, confirmatory task payload, seed, or
credential material.

**Remaining discipline:** treat every allowlist change as security-sensitive and
rerun bundle plus container-surface audits before public deployment.

## Exact blockers before confirmatory execution

1. privately generate 30 independent families with two sealed frontier pairs
   per family;
2. keep generator/oracle logic private until post-run release;
3. run full repository, known-benchmark, and public-search contamination checks;
4. implement hash-linked proposal, decision, test, activation, transfer,
   protected-suite, and rollback receipts;
5. freeze prompts, models, budgets, extensions, and all arms;
6. reproduce strict Lean and package checks on clean CI;
7. obtain scientific-domain expert review.

## Claim boundary

Winner-level evidence is currently **none**. There is no confirmatory effect,
uncertainty estimate, transfer result, protected-suite result, or independent
scientific reproduction.

The current package is a strong and unusually honest infrastructure proposal.
It is not yet a validated frontier-expansion result.

`candidateOnly:true`; `canClaimAGI:false`.
