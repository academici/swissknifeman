# Semantic Identity / Ownership v1 (P1.1)

RAG:— (plan-grounded: D6/D7/D23/D28/D31/D38/D40–D44; repo-grounded:
`findings/03-ssot-runtime-inventory.md`, `findings/12-effective-collision-remeasure.md`,
`packages/skiller/lib/skiller/{registry,publication,skillset}.py`,
`packages/task/lib/task/{command_catalog,command_render}.py`,
`packages/harness/lib/harness/provider_audit.py`).

## Scope

This contract freezes **who owns an effective identity** before P1.2/P1.3/P1.5 change a
single carrier, and it freezes **how a collision is detected** so the terminal P1.4 gate
cannot go green by narrowing the catalog. It seals semantics and maps only; it implements
nothing in `packages/*` (item P1.1 Scope Excluded: source fixes, external plugins, fleet
installations, semantic redesign).

An **effective identity** is the frontmatter `name:` an agent runtime discovers. A
**carrier** is any repository artifact that can publish that identity to a provider: a
publishable unit declared in that provider's repository marketplace, or a root projection
directory under that provider's root skills path.

## Machine carriers

| Artifact | Role |
|:--|:--|
| `artifacts/P1.1/build_effective_inventory.py` | the sole executable owner of detection, capture, generation and both acceptance gates |
| `artifacts/P1.1/effective-inventory.json` | one record per identity per provider: owners, carriers, capabilities, reference closure, version/tree hash, discovery state |
| `artifacts/P1.1/effective-runtime-before-state.json` | the machine-readable observed before-state (schema v1) produced by exactly one named read-only capture mode |
| `artifacts/P1.1/remediation-map.json` | the owner map of every measured collision plus the five baseline owners and their exact path sets |
| `artifacts/P1.1/repository-bootstrap-map.json` | the exact 13-identity / 26-projection class-A map (acceptance: D38) |
| `findings/P1.1-capability-gaps.md` | carrier-literal → capability coverage gaps found while sealing this contract |

## Detection is repo-derived and cold (D44)

The authoritative carrier set is computed **from repository sources only**:

- every publishable unit declared in `.agents/plugins/marketplace.json` (Codex) and
  `.claude-plugin/marketplace.json` (Claude Code) — worst case, **any unit may be enabled**;
- every root projection: `.agents/skills/<name>/SKILL.md`, `.claude/skills/<name>/SKILL.md`.

An identity with **≥2 carriers in one provider** is a collision and requires an owner
record. Identity enumeration of a unit follows the unit's own declaration — marketplace
`skills[]` first, then the unit's provider plugin manifest, and only then a source scan —
because nesting depth differs per unit format; it is never a blind recursive walk of
`source`.

Three consequences are binding:

1. **The committed prose inventory is provenance, never a diff source.**
   `artifacts/source-evidence/runtime/effective-runtime-inventory.json` carries no identity
   record, no unit list and no version (top-level keys `green`/`not_green`/`redactions`/…).
   Its counters are cross-checked where parseable and otherwise classified
   `pinned-not-recomputable`. Diffing collision detection against it is structurally
   impossible, so it may never gate anything (D30/D44).
2. **The observed capture corroborates; it can never subtract.** Exactly one named
   read-only capture mode produces `effective-runtime-before-state.json`. It may confirm a
   repo-derived collision and may reveal which collisions are live, but removing a
   collision from the repo-derived set on its basis is forbidden.
3. **An unreadable provider is `unknown`, not green.** A provider whose enabled set has no
   declared read-only command (today: Claude Code — named debt in `plan.md` §10) is
   recorded `unknown` with a reason. Silence is never a pass.

### Observed before-state, schema v1

Exact top-level keys `schema_version`, `captured_at`, `commands`, `providers`. `commands`
records the **literal argv** of each declared read-only command with its exit code and
status. `providers` carries, per provider, `state` (`read`/`unknown`), `units[{name,
version, enabled, identities[]}]` and `root_projections[{path, identity}]`. Home-relative
paths are sanitized to `$HOME`. Re-running the capture on an unchanged runtime reuses the
existing bytes, so a re-validated item does not manufacture drift out of a timestamp.

## Invariant (i) — root projections exist only in the absence of an enabled unit

> A root projection may exist **only while no enabled unit serves that identity**. After
> remediation, each provider's root set equals **exactly the declared target set**; an
> undeclared root directory is a gate failure, never a "unique carrier".

Ownership, not suppression, resolves a collision: the installed generated bundle is
authoritative, and the duplicate root projection is deleted **after** its own bundle proof.
Conditional discovery filters, suppression metadata and display-prefix or byte-equality
arguments are not proof of identity (`packages/skiller/lib/skiller/publication.py`
renders projections; equality of bytes says nothing about semantic ownership).

## Invariant (ii) — curated `core` and its donor buckets are mutually exclusive

> The curated unit `core` physically copies identities out of the donor buckets `general`,
> `research` and `oss-dev` (`packages/skiller/adapters/codex/core/skills/**`). `core` and
> any donor bucket are therefore **mutually exclusive publications**. Simultaneous
> enablement is a **machine diagnostic** that names the identity, the carriers, the owner
> item and a safe Owner action — and **never a profile write**.

The plan does not change the user-owned enabled set (D42). Nine identities are affected by
construction (`anti-drift`, `compact-responses`, `context-economy`, `mcp-advisor`,
`plan-protocol`, `session-handoff`, `verify-claims`, `gh-review`, `query-craft`); on a live
host where `core` and `research` are enabled together, `query-craft` is the live instance.
This is diagnostics with a named owner (P1.5), not a floor and not a repair.

## Measured surface and its owner map (frozen)

Repository-derived worst case, measured by the tool named above:

| Provider | Colliding identities | Classes | Unique root carriers (declared enabled set) |
|:--|--:|:--|--:|
| `codex` | 20 | 17 `root-vs-unit`, 9 `unit-vs-unit` | 14 |
| `claude-code` | 9 | 9 `unit-vs-unit` | 13 |

Under the declared enabled set of `findings/12` (23 enabled `@swissknifeman` units,
one read-only `codex plugin list --json`, 2026-07-25) the Codex surface is **16
root↔installed collisions plus one installed↔installed** (`query-craft`) — the shape
D40 records. Every count above is derived from repository bytes plus that declared
enabled-unit literal; no count is pinned.

Owner assignment — every measured collision, every measured class:

| Carriers | Owner | Action |
|:--|:--|:--|
| 6 root core adapters (`anti-drift`, `context-economy`, `plan-protocol`, `query-craft`, `session-handoff`, `verify-claims`) | **P1.2** | delete the root projection after the generated `core` bundle/marketplace proof |
| 6 root task adapters (`task-design`, `task-plan-{audit,close,design,exec,run}`) | **P1.3** | delete the root projection after the generated `task` bundle/marketplace proof |
| 4 root `architect` adapters (`architecture`, `codebase-design`, `domain-modeling`, `package-contribution-protocol`) | **P1.5** | delete the root projection after per-identity ownership proof |
| every `unit-vs-unit` pair (9 identities, both providers) | **P1.5** | D42 mutual-exclusion detector with a non-empty `safe_owner_action` |
| `workflow-craft` root | **P1.5** | generate a class-B root-bootstrap projection with provenance/hash |

A measured collision without an owner item is a **hard failure of P1.1**, not a warning:
`build_effective_inventory.py --check-collision-owners` fails closed and names the
provider, the identity and its carriers.

## Class A — 13 private repository-bootstrap identities

Canonical bilingual sources live only in the private/source-only bucket
`packages/skiller/skills/repository-bootstrap/<identity>/{SKILL.ru.md,SKILL.md}` (D31).
`build_registry` indexes those 13 records for ownership/hash lookup, while
`build_publication_catalog` excludes the bucket from ordinary Claude/Codex bucket units,
from `core` membership and from both marketplaces; consumer `vendor`/`connect` selection
rejects the source-only records instead of copying them into another project.
`skillset.py` may implement that consumer exclusion but is **never** the self-host root
producer — the only producer is `registry.py` → `publication.py` from
`packages/skiller/configs/repository-bootstrap-skills.json`.

Acceptance is exact set equality, not key presence (D38): schema v1 with exact top-level
keys, exactly the 13 sorted identities, the exact nine record keys, both pinned seed
path/hash records, the canonical bilingual formula, two provider projections per identity
and the exact 26-target set, the frozen version/unit/generator/lock literals, and an
explicit `resolution` for every record naming the selected seed and the reason whenever the
two seeds differ.

**Measured seed state (2026-07-25):** three of thirteen pairs are byte-identical; ten
differ because the Codex copy is a mechanical `Claude`→`Codex` string substitution of the
Claude copy — the same class `findings/03` records as 48 blind provider substitutions
producing non-existent paths (`.Codex-plugin`, `configs/Codex`). The Claude bytes are
therefore the undamaged migration seed for every differing pair, and each record says so.

## Class B — public-bucket canon whose unit is not enabled (D43)

Exactly one record today: `workflow-craft`. Canonical source
`packages/skiller/skills/general/workflow-craft/SKILL.md` (public bucket `general`,
currently not enabled), provider set **Codex only**, publication unit
`repository-bootstrap@0.2.0`, single target `.agents/skills/workflow-craft/SKILL.md`, owner
item **P1.5**, precondition «no enabled unit serves this identity».

The Codex-only asymmetry is **declared, not accidental**: a Claude root projection changes
the first-turn budget and requires `skiller budget --first-turn` (CLAUDE.md), which is
outside this scope, so a parity test must assert the asymmetry as declared. Deleting
`.agents/skills/workflow-craft` is rejected: the only legal restoration path — enabling
`general` — is forbidden by invariant (ii). Class-B acceptance lives in the P1.5-owned
extension map, so the class-A map above stays byte-for-byte unchanged.

## Record shape

Each identity record names: semantic ID · canonical owner and source (with SHA-256) ·
projection owner(s) · required capabilities with their per-provider support level ·
complete runtime references (declared and missing) · version/tree hash of every carrier ·
discovery state (`unit-only` / `root-only` / `collision`).

**Capability coverage is measured from actual carrier literals**, not only from
declarations: a carrier that spells an execution literal but declares no matching
capability cannot fail closed on a provider that lacks it. Three such gaps were measured
and are recorded in `findings/P1.1-capability-gaps.md`; the largest is that
`command.interactive-user-input` does not exist in `configs/provider-capabilities.json`
at all, while `task:design` spells `AskUserQuestion`.

## Consumers

P1.2 (class-A sources, root-bootstrap generator, six core deletions), P1.3 (task/harness
projection, six task deletions), P1.5 (four `architect` deletions, class-B record, D42
detector, root-set completeness), P1.4 (cold install/discovery, exactly-once proof over the
declared fixture set of D51). No consumer may delete a root projection without its own
bundle proof, may widen the declared target set silently, or may cite an `unknown`
provider state as green.
