# Canon of root instructions

Mechanism `harness instructions` manages twelve root projections/batch
instructions (six scope × two providers: `CLAUDE.md`/`AGENTS.md` at the root and one at a time
on `skiller`/`harness`/`maind`/`analyst`/`task`) from ONE source - without manual
synchronization between Claude Code and Codex.

## Source and targets

Source - fragments `packages/harness/configs/common/instructions/**` (rule on
file) plus `catalog.json` (76 semantic ID: 56 general + 20 provider-extension,
D86). Each of the twelve targets is rendered from the directory slice in its own way scope and
provider; provider-specific extensions - an additive layer on top of the general rules
(`root.provider-parity`), is not a replacement. Machine reference with accurate map «scope →
target → counters» — [`provider-instructions.md`](./provider-instructions) (is generated
`operator_reference()`, pins with byte-to-byte test - can't be corrected by hand).

One semantic ID can carry SEVERAL `obligations` (list, not a single field):
`root.plan-lifecycle` with ` carries two - the original one about placement
plans and a new commitment to the provenance of the author's model (which model designed
part of the plan, three carriers by name - `Authoring Model` in Meta, column Update Log,
`actor` log). Each entry `compatibility_assertions` must be substring'body ohm
fragment AND mirrored byte-by-byte in `tests/fixtures_data/instruction-compatibility-v1.json`
(`_validate_compatibility_fixture`) — list expansion requires editing in both places.

## Managed blocks

In each target, the rule lives between a pair HTML-markers
(`<!-- swissknifeman:instructions:<scope>:<provider>:<common|extension>:begin/end -->`).
**Manual editing of content between markers is permanently disabled**: next run
`check`/`repair` will see a hash discrepancy and raise `managed-drift` at step `[9/10]`
`packages/harness/scripts/validate.sh`. Bytes outside blocks (file header, sections,
not covered by the catalog) are saved verbatim - only fragments are edited and
regeneration.

## Three observations

- **`stale-source`** — the source fragment has changed, and the target still carries the old render.
  Repaired normally `apply --authorize <target>` (creation/update).
- **`managed-drift`** — contents of a controlled block changed BY the mechanism (manual
  edit, someone else's commit). Repairs ONLY `repair` with explicit `--observed-hash` for each
  drifting target and `--preimage-dir` (see below) — narrowing of the check, `|| true` or
  target exclusion from the gate is prohibited.
- **`ownership-conflict`** — target exists, but does not carry markers or records in
  `.swissknifeman/provider-artifacts.lock.json` (typical case - manually written
  `CLAUDE.md` before implementing the mechanism). `apply`/`repair` such a target is not touched; way
  out — `adopt` (below).

## Five operations `harness instructions`

```
harness instructions <plan|check|adopt|apply|repair> [--target P]
  [--scope a,b] [--provider a,b] [--authorize a,b]
  [--owner-decision D#] [--mapping FILE] [--preimage-dir DIR]
  [--observed-hash path=hash,...] [--json]
```

- **`plan`** — no-write snapshot: what is being rendered and how it compares to the current one
  tree. Doesn't write anything.
- **`check`** — same plus mandatory literal coverage gate (see below); modular
  entry point for CI/validate.sh — `python3 -m harness.instructions --check`, verdict
  must match `harness instructions check` byte-to-byte.
- **`adopt`** — owner-gated accepting an EXISTING unmanaged file under
  control: MUST require all three - `--owner-decision D#` (authority
  solutions), `--mapping FILE` (sectional map «source → semantic ID»,
  covering the entire file) and `--preimage-dir DIR` (where byte-to-byte is written
  pre-image BEFORE mutation, restore-path - `rollback_adoption`). Refuses any
  target that is not `ownership-conflict`.
- **`apply`** — writes EXACTLY the goals listed `--authorize` (missing/create or
  stale-source/update); the list must match BOTH in composition AND IN ORDER with what
  planned `plan` — otherwise `INSTRUCTION_WRITE_FORBIDDEN`.
- **`repair`** — repairs `managed-drift`: same list-and-order in `--authorize`, plus
  `--observed-hash target=hash` on EACH drifting target (proof that
  operator saw the current status), plus `--preimage-dir adjacent-backup`
  (literal string - pre-image is written next to the target, not in a separate directory).

**Order of targets in `--authorize` — ALPHABETICAL order `target_path`** (authoritative
wording). Any other order (for example, «first root, then batch»)
gives `INSTRUCTION_WRITE_FORBIDDEN`, because the mechanism compares tuples positionally.
Failure prints this entire order (via `--authorize`-compatible string in
diagnostics `INSTRUCTION_WRITE_FORBIDDEN`) — is copied literally into the re-call,
without a second blind attempt.

`plan` and `check` — no-write; `apply`/`repair`/`adopt` are written only after an explicit
operator authorization.

### Provider-safe operations

Provider projections remain additive over this shared instruction contract. Before a change, run
`harness instructions plan` or `check` for the exact target and inspect the provider-qualified
result; an `unsupported`, missing, or non-clean result is not a fallback to another provider.
`apply`, `repair`, and `adopt` each require their own explicit authority and preserve the preimage
needed by the documented rollback path. A failed readback stays non-green: restore only the
declared owned preimage, then repeat `check`. Do not treat a dry-run, generated reference, or this
page as permission to mutate a project or publish a release.

## Adoption-mode: rollback

Each `adopt` before the mutation writes pre-image in `--preimage-dir` and writes it
hash/path to `semantic_metadata.adoption` corresponding lock-entries. Rollback -
`rollback_adoption`: byte-to-byte recovery from pre-image and removal lock-records;
without recorded pre-image rollback fail-closed (fails rather than approximates).

## Three machine gates

- **Drift gate `[9/10]`** — penultimate step `packages/harness/scripts/validate.sh`:
  `python3 -m harness.instructions --check`, green only if all twelve targets
  `clean`. The only one CI-carrier for today (`analyst` in this CI not covered).
- **Equality gate provenance covering literals** — `validate_literal_coverage` checks
  digest current compatibility source and his presence assertions in the live directory.
  Fixture is being regenerated `generate-provider-instructions.py`. Historical section-hash
  remains readable, the archive matrix does not define the current semantics.
- **Canon size gate** — `validate_canon_size`, same input `--check`: each
  the existing projection must fit into the ceiling of its class both in rows and
  by token valuation. Rule «canon of instructions ≤ 200 lines» after
  ` lives here, not in prose (details - below).

## Canon Size Ceiling

The carrier of the rule is four named constants `lib/harness/instructions.py`, two each
per artifact class; «magical» there are no numbers in the body of the check.

| Class | Goals | Lines | Tokens |
|:--|:--|:--|:--|
| root | `CLAUDE.md`, `AGENTS.md` | `ROOT_CANON_LINE_LIMIT` = 200 | `ROOT_CANON_TOKEN_LIMIT` = 6 000 |
| batch | `packages/<name>/{CLAUDE,AGENTS}.md` | `PACKAGE_CANON_LINE_LIMIT` = 100 | `PACKAGE_CANON_TOKEN_LIMIT` = 3 000 |

Root class row ceiling - upstream recommendation Claude Code («keep `CLAUDE.md`
files under 200 lines and move reference material to skills»), and not the current size
file; token inferred from the observed density of this canon on the row ceiling
(~28 current/line × 200 ≈ 5 600 → 6 000) and independently converges with the budget frame:
6 000 — 37 % target'and the first move is 16,000. The batch class is twice as strict because
the package projection is loaded IN ADDITION to the root one when the agent enters the package.

Three gate properties that are important not to lose when editing:

- **The entire file is measured**, and not just managed blocks: the session pays for the entire
  `CLAUDE.md`, including bytes outside the markers, and the upstream recommendation is also about the file.
- **Token valuation is the same formula as `skiller budget`**: both import
  `aicore.content.budget.estimate_tokens` from the shared foundation, so there is one implementation and no copy
  to drift. The test `tests/test_instruction_size_gate.py::test_token_estimate_is_the_aicore_function` pins that
  the gate uses that very function. Two independent accounts of one file would be a guaranteed dispute of numbers.
- **Finding size is not diagnostic.** Code table `InstructionDiagnostic`
  frozen by contract `provider-instruction-contract` v1.0.0; seventeenth code bumped
  would be a frozen contract, and reusing someone else's would lie in the machine field.
  Therefore the gate is additive: its own type `CanonSizeFinding` and new report key
  `size_findings` over immutable ones `targets`/`diagnostics`/`green`. Like gate
  covering literals, it is connected ONLY to `check`: in `plan`/`apply`/`repair` red
  the size verdict would jam exactly the operation with which it is repaired.

## Relation to layers `control-surface`

In terms of the three layers of the umbrella source `control-surface` (canonical → generated →
effective): fragments + `catalog.json` — canonical, twelve projections - generated
(drift is corrected by regeneration, not editing the file), what the agent actually sees in
sessions, — effective.

## Current semantics and historical provenance

Current literal coverage is generated `scripts/generate-provider-instructions.py` from
`tests/fixtures_data/instruction-compatibility-v1.json`. `--check` checks both projections.
The archival matrix remains historical evidence, but does not impose the canceled requirements
current rules. Old section-hash provenance read; new file-hash links
coverage with current compatibility source. Change runtime-policy updates this source
and semantic tests, after which they are regenerated normally root/provider carriers.

Root requires package guides, scope/authority and truthful evidence. General doctor/health
is executed when setting up the environment or symptoms; directory transition and number item do not require
new session. A regular task can be completed according to a brief without a plan.
