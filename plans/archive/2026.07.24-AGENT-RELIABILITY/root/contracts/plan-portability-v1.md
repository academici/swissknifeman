# Plan Portability v1 (P2.1)

RAG:— (plan-grounded: D23/D25/D26/D47/D57/D64; repo-grounded:
`root/contracts/task-contract-v1.md:115-133,187-200`,
`root/contracts/source-evidence-verification-v1.md`,
`packages/skiller/skills/general/plan-protocol/SKILL.md` §8;
synthesis: `research/06-p2.1-contract-boundary.md` §1).

## Scope

This contract seals **who assigns a portability tier, by what признаки, and what the lint
predicate rejects** — plus the one rule that decides whether a path is provenance or an
execution input.

It is a **layer on top of** the frozen P0.2 Task Contract (D64). P0.2 already owns the tier
ENUM, both `PORTABILITY_*` reason codes, the `privacy` block and the
`semantic_carrier` + `provider_renderers` pair. This contract owns none of that and cites all of
it. What P0.2 does **not** own is the classification rule itself: given a task, which tier is
correct. A tier assigned wrongly passes P0.2's input check vacuously, because an empty
`execution_inputs` list is legal for `brief-acceptance` — that gap is what this contract closes.

It seals semantics only. The self-conformance fixture over this plan belongs to P2.2 (D47) and
is not built here.

## Frozen upstream

| Fact | Owner | Source |
|:--|:--|:--|
| Tier enum `brief-acceptance` / `committed-bundle` and what each means | P0.2 | `root/contracts/task-contract-v1.md:115-133` |
| `PORTABILITY_INPUT_MISSING`, `PORTABILITY_EXTERNAL_INPUT` | P0.2 | `root/contracts/task-contract-v1.md:115-133` |
| `privacy` (minimization + excluded classes), `semantic_carrier`, `provider_renderers` | P0.2 | `root/contracts/task-contract-v1.md:115-133` |
| The three neutral `context` values and their Russian command-file projections | P0.2 / plan-protocol §8 | `root/contracts/task-contract-v1.md:187-200` |
| Cold-start self-sufficiency of a launch block and its scope-payload | plan-protocol §8 | `packages/skiller/skills/general/plan-protocol/SKILL.md:578-620` |
| Evidence proof classes and the rule that `pinned-not-recomputable`/`unknown` may ground a hypothesis but never a deterministic acceptance predicate | P0.1 / P0.2 | `root/contracts/task-contract-v1.md:101-113` |

Neither `PORTABILITY_*` code is re-minted. The one condition this layer adds —
a tier that contradicts the classification rule — is `PORTABILITY_TIER_MISCLASSIFIED`, declared
with its `distinct_from` justification in
`artifacts/P2.1/state-transition-cases.json::new_reason_codes`.

## Classification rule

The tier is assigned by the WORK, not by the author's preference:

```text
tier(work) := committed-bundle   if work.sessions == "multi"
                                 OR work.risk == "high"
                                 OR work.handoff
                                 OR work.audit
              brief-acceptance   otherwise
```

- **Who assigns it.** The root supervisor that compiles the Task Contract, before dispatch —
  never the item executor, and never a subagent: the portability decision is part of the
  root-only slice (`task-contract-v1.md:167-178`), so a subagent receives a resolved tier, not
  the classification problem.
- **When it is re-assigned.** Only when one of the four признаки changes (a single-session task
  grows a handoff, a low-risk task is re-classified high). A re-assignment is recorded like any
  other contract revision, with the previous hash in `supersedes`.
- **The lint predicate rejects**, in this order: (1) a tier that the rule above does not yield
  for the declared work; (2) `committed-bundle` with an empty `execution_inputs`
  (`PORTABILITY_INPUT_MISSING`, P0.2); (3) a path present in both `execution_inputs` and
  `provenance_only`; (4) an input that is absolute, `~`-rooted, parent-escaping, URL-shaped or
  otherwise host-bound (`PORTABILITY_EXTERNAL_INPUT`, P0.2); (5) a `produced-by-predecessor`
  input without a named producer (P0.2).

Five worked cases — including a `tmp/`-spelled path that is provenance for the right reason —
are materialized in `artifacts/P2.1/state-transition-cases.json::portability_cases`, and the
validator recomputes every tier from the rule rather than trusting the declared value.

## Provenance vs execution input — by ROLE, not by spelling (D47)

A path is an **execution input** when the item actually READS it: it appears in the item's
`Inputs`, `Required Reads` or `Validation`. A path is **provenance** when it explains where
something came from and nothing in the item reads it.

The rule is the ROLE, **explicitly not a substring match on `tmp/`**. Two consequences that a
substring rule would get wrong in both directions:

- a committed, repo-relative path whose directory name merely contains `tmp` and which the item
  genuinely reads is an execution input — the name is not the test;
- a scratch note the executor happened to consult but that no field of the item names is
  provenance, wherever it lives.

Host, chat, mAInd and foreign repositories are provenance by construction: nothing about them is
recoverable by a cold session from committed bytes. `tmp/` is the usual home of provenance, and
that is a consequence of the role rule, not its definition.

**Diff-scope corollary (D47).** The same role test decides ownership of a drifted path: a path
changed only by a foreign commit and lying outside the item's owner set is classified
`foreign-commit`, not undeclared drift; a foreign commit touching an owner path is a fail-closed
stop with a named question. Stash/revert/reset of foreign edits stays forbidden by commit
hygiene.

## Bundle requirements — stated once, here

A `committed-bundle` is not "everything we had". It carries, and this is the only place the
requirement is written:

- **Minimization.** Only what an execution input is actually read for. `privacy.minimized` is
  true and `privacy.excluded_classes` names what was left out — raw bodies, chain-of-thought,
  tool payloads, secrets (P0.2 owns the field; this is the requirement on its use).
- **A deterministic manifest and a verifier.** The bundle's integrity is recomputable, not
  attested: hashes are recomputed, never trusted as written, and the verifier is committed with
  the bundle (`root/contracts/source-evidence-verification-v1.md`).
- **Complete dependency closure.** An input that references another artifact brings it, or the
  bundle is not self-contained and a cold session fails on the second file.
- **One neutral semantic carrier with provider renderers.** A rendered Claude or Codex
  invocation is a projection; it never becomes the source of truth. The `context` value travels
  as the neutral literal, and the Russian command-file strings are its projections
  (`task-contract-v1.md:187-200`).
- **Proof class.** No public acceptance predicate may rest on a `pinned-not-recomputable` or
  `unknown` quantity; such material travels as labelled context only.

## Boundaries (И1–И3)

| Not touched here | Owner (plan AND item) | Reason | ПРОХОД |
|:--|:--|:--|:--|
| The tier enum and both `PORTABILITY_*` codes | **P0.2** (terminal) | re-minting them creates two carriers of one fact — the duplicate-SSOT failure this plan exists to cure | a genuinely new condition → a new code here with a `distinct_from` justification, never a redefinition of an existing one |
| The self-conformance fixture over this plan's own paths | `2026.07.24-AGENT-RELIABILITY` **P2.2** (D47) | building it here would fork the fixture the compiler item owns | needed earlier → D# + move it into P2.2's Scope |
| `packages/**` and the `plan-protocol` canon (incl. §8 launch-block form) | **P2.2**, then P2.3 | single owner of the canon bump; the launch-block form is already canon and is cited, not re-specified | the form must change → D# + the edit lands in P2.2 |
| `artifacts/P2.1/base-sha.txt` and `assert_generated_scope.py` | **P1.1** (`baseline_owners` = P1.2, P1.3, P1.5, P2.2, P2.3) | P2.1 is absent from `baseline_owners`, so claiming a baseline here would write into a frozen P1.1 artifact | a real need for a drift gate → D# + an edit of the map by P1.1's owner |

**Freeze semantics (И2).** Frozen as `v1` at the close of P2.1, extension **additive**: a new
признак in the classification rule is a **major** bump (it re-classifies existing work), a new
bundle requirement or lint rejection reason is **minor**, wording is **patch**.

## Contribution gate (D23)

- **Existing extension points surveyed first.** P0.2 already carries the tier enum, both codes,
  `privacy`, the carrier/renderer pair and the `context` values; `source-evidence-verification-v1`
  already carries manifest/verifier discipline; `plan-protocol` §8 already carries launch-block
  self-sufficiency. The classification RULE and the role-based provenance test are the only
  things missing, and they are the only things added.
- **Named consumers:** `P2.2` (compiler and the self-conformance fixture), `P2.5` (end-to-end
  bank), `P3.3` (behavioral eval release gate), `P4.3` (Owner packet).
- **Alternatives considered (≥2).** (a) *Extend `task-contract-v1` with the classification rule*
  — rejected: P0.2 is frozen and consumed by three phases; the change would be breaking where a
  sibling contract is additive (И10). (b) *Detect provenance by a path prefix (`tmp/`, absolute,
  `~`)* — rejected as the RULE (it stays a P0.2 REJECTION check): a prefix test misclassifies a
  read committed path whose directory contains `tmp` and silently accepts a scratch file
  relocated into the repo. The role test is the only one that survives both directions.
- **SemVer/ADR result:** new contract at `v1`, additive to the frozen set; no existing contract
  changes version. The ADR is this section plus D26/D47/D64.

## Consumers

`P2.2` compiles the tier and runs the lint predicate and the self-conformance fixture over this
plan's own items; `P2.5` proves the bundle requirements end to end against the historical corpus;
`P3.3` gates a release on behavioral evals whose inputs are classified by this rule; `P4.3`
assembles the Owner packet from a bundle that satisfies it. No consumer may add a tier: the enum
is P0.2's, and a fifth признак in the classification rule is a major bump of this contract, not a
local extension.
