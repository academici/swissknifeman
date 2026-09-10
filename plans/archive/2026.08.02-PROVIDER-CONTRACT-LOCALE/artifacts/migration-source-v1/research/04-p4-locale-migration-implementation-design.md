# P4 locale runtime and English-source migration implementation design

## Traceability

| Requirement or fact | Destination |
|:--|:--|
| English default; response, plan and diagnostics resolve independently | P4.1 shared locale runtime and provider-owned render contexts |
| English is the sole semantic source; Russian is rendered, never parallel canon | P4.2 admission ledger and P4.3–P4.6 carrier batches |
| Existing RU→EN skill ownership cannot be reversed by renaming or stamping alone | P4.2 direction-aware validator and P4.3 skill batch |
| Provider outputs remain independently owned | P4.1 render boundary and P4.4 generated-provider checks |
| Generated artifacts are never hand-edited | P4.6 terminal regeneration/readback |
| Comments and development docs become compact English without translating machine tokens | P4.5 code prose and P4.6 docs batches |

Sources: `brief/00-brief.md`, `findings/06-p2-locale-authoring-verification-2026-08-02.md`,
`findings/08-p4-locale-migration-recon-2026-08-02.md`,
`research/02-p2-locale-authoring-design.md`, `research/03-p3-control-plane-implementation-design.md`,
and the frozen P2/P3 artifacts once their producer items are terminal.

## Ownership and runtime design

Locale is a provider-neutral domain adjacent to, not inside, provider selection. A stdlib-only
`core/locale/` package owns immutable surface/tag/provenance values, resolution, catalog lookup,
placeholder/literal preservation and deterministic render diagnostics. It accepts already-read
descriptors from P3; it reads no environment, project, user or provider file itself. Harness,
Task, Skiller and Maind remain responsible for their own source catalogs and rendered targets.
Provider adapters receive the same resolved locale context and cannot persist it as adapter
intent or write another provider's output.

P4.1 proves the runtime on fixture catalogs before canonical prose is migrated. This separates
the renderer's correctness from translation quality and lets P4.2 test malformed tags, missing
keys, fallback, interpolation and provider isolation without using the production corpus as its
own oracle.

## Migration design

The P2 carrier matrix becomes one cumulative machine-readable admission ledger. Each row names
semantic source, locale overlay, owner/generator, preimage hash, immutable tokens, independent
English/Russian review evidence, status and rollback. P4.2 implements no-write inventory/check/
plan first; apply accepts only an admitted row whose preimage still matches. A grep hit is a
candidate, never authority. Existing English bytes may be retained when review proves them;
the migration is about source ownership and enforceability, not mandatory churn.

The implementation is split into sequential carrier batches:

1. P4.3 skills and skill-authoring/provenance;
2. P4.4 task commands, plugin/provider-rendered text and diagnostic catalogs;
3. P4.5 comments, docstrings and test descriptions across code/scripts;
4. P4.6 development docs plus terminal regeneration/readback.

Each item consumes the previous ledger revision and publishes the exact next revision, so the
items are not parallelizable without creating competing ledger/generated-output writers. Within
P4.3–P4.6, however, the measured corpus is split into deterministic committed checkpoints:
P4.3 ≤12 skill units; P4.4 ≤10 command/plugin/diagnostic rows and one package cwd; P4.5
≤12 files and ≤40 prose spans, whichever limit fires first, and one cwd; P4.6 ≤10 docs
files and one cwd. Every checkpoint carries preimages, commit, validation, rollback, next-row
pointer and a separate read-only reviewer verdict. Resume starts at the first non-accepted row;
author/reviewer identity equality, a missing checkpoint, or two failed review/fix rounds stops
for plan-design rather than skipping work.

No parallel Workflow script is declared. Multi-package items use the explicit per-cwd carrier
in `roadmap.md`: fresh package sessions produce scoped evidence while one root coordinator owns
the cumulative ledger, integration and item close. P4.6 is the terminal coherence item required
by the plan protocol: earlier source batches may leave only the exact `deferred-derived-only`
set defined by D50/`roadmap.md` stale. Each nonzero owner dry-run must classify to that
recomputed ordered set and no other error is accepted. A distinct terminal-regeneration stage
starts only after all source checkpoints are accepted, freezes the plan hash and exact
alphabetically ordered Harness authorization set, regenerates that set once, checks both provider
projections, proves every in-scope ledger row terminal with an empty deferred set, and leaves all
package/docs validation green and a byte-stable second run.

## Review and stop conditions

All six items route to `implementation/high`, `manual`, `Review=full`: runtime/API and validator
changes are public-contract work, while every content checkpoint changes canon followed by the
fleet. Author/renderer self-approval is invalid. A reviewer is read-only and records a distinct
identity; `FIX_REQUIRED` yields a separate fix commit and fresh review, with two rounds maximum.
Missing frozen P2/P3 input, preimage drift, unknown owner, changed parser literal, missing
independent review, cross-provider target access or a non-green readback stops the current batch
and preserves its resume pointer; it is never converted into an inferred translation or bulk
overwrite.

## Pre-mortem

- A marker flips direction while reviewers still edit RU as source → P4.2 requires one declared
  writer and P4.3 changes authoring instructions/tests before admitting the skill corpus.
- Translation changes a parser literal, placeholder or command → immutable-token parity and
  negative fixtures block admission in P4.2 and every batch.
- One provider renders Russian while the other silently falls back → P4.1/P4.4 pair fixtures and
  P4.6 readback preserve separate provider rows.
- Generated projections are published from a half-migrated corpus → P4.6 is the single terminal
  regeneration item; earlier items name expected derived drift.
- Grep misses prose or mistakes fixture literals for prose → the ledger is built from declared
  owners plus extension-aware parsers; P4.6 refuses any unclassified candidate or absent row.
- The current dirty tree is staged with migration work → every item uses explicit Files paths,
  preimage hashes and no `git add -A`/`git commit -a`; foreign changes remain untouched.

## Verification

- **RAG:** no new external fact class. BCP 47/casing/fallback input is the already captured
  2026-08-02 P2 evidence; all ownership, generator and corpus claims are repo-grounded by the
  P4 finding.
- **Unverified → repeat pass:** exact P2 catalog envelope and P3 status/diagnostic class names
  must be read from their frozen artifacts immediately before execution; the phase forbids
  inference from this design document when those inputs are absent or incompatible.
- **Workarounds/[POSSIBLE-DEFECT]:** none. Existing English prose is retained only by explicit
  semantic admission, not to reduce migration effort.
