# Generated Artifact Version v1 (P1.1)

RAG:— (plan-grounded: D7/D23/D27/D36/D47; repo-grounded:
`packages/skiller/lib/skiller/registry.py` (`check_drift`, `write_plugin_manifests`),
`packages/skiller/lib/skiller/publication.py` (publication units, locks),
`packages/task/lib/task/command_render.py` (`plan_codex_command_apply`, publication lock),
`core.provider_lock`).

## Scope

This contract freezes **how a generated artifact changes version and how an item proves it
changed only what it owns**. It seals the ledger and the guard; it publishes nothing. The
five baseline owners named here — **P1.2, P1.3, P1.5, P2.2, P2.3** — are the only items
that carry an item-owned baseline file under this plan.

## Version-first and generator-closed

Every canonical/package publication change is **version-first and generator-closed** (D27):

1. bump the exact package/plugin/publication-unit version **before** generation;
2. regenerate the **complete** declared tree, locks and both repository marketplaces;
3. prove a read-only second check is a **no-op** (`skiller registry --check`,
   `render-provider-commands.py --check`);
4. pass the exact diff-scope guard below.

`packages/skiller/configs/publication-versions.json` separates the package API SemVer from
finite per-unit versions, so an unaffected bucket manifest stays **byte-identical**. Reusing
one `(name, version)` tuple for different tree bytes is forbidden — the tuple is an
immutable claim about a tree hash, and a same-version cache with different content is
exactly the incomplete-cache defect `findings/03` recorded. G1 may choose release versions
but may never reuse a tuple for different bytes.

## The frozen ledger (approved by P1.1)

| Owner | Unit | Carrier | From → To |
|:--|:--|:--|:--|
| P1.2 | skiller package API | `packages/skiller/package.json` | `0.4.0` → `0.4.1` |
| P1.2 | `core` | publication unit | `0.4.0` → `0.4.1` |
| P1.2 | `skm` | publication unit | `0.4.0` → `0.4.1` |
| P1.2 | `repository-bootstrap` | publication unit | absent → `0.1.0` |
| P1.3 | task plugin/routing | `plugin_version` | `0.3.0` → `0.3.1` |
| P1.3 | harness package | `packages/harness/package.json` | `0.2.0` → `0.3.0` |
| P1.3 | harness plugin | `packages/harness/.claude-plugin/plugin.json` | `0.1.0` → `0.2.0` |
| P1.5 | skiller package API | `packages/skiller/package.json` | `0.4.1` → `0.4.2` |
| P1.5 | `repository-bootstrap` | publication unit | `0.1.0` → `0.2.0` |
| P2.2 | `plan-protocol` skill canon | `packages/skiller/skills/general/plan-protocol/SKILL.md` | `2.11.0` → `2.12.0` |
| P2.2 | skiller package API | `packages/skiller/package.json` | `0.4.2` → `0.5.0` |
| P2.2 | `general` | publication unit | `0.4.1` → `0.5.0` |
| P2.2 | `core` | publication unit | `0.4.1` → `0.5.0` |
| P2.2 | task plugin/routing | `plugin_version` | `0.3.1` → `0.4.0` |
| P2.3 | task plugin/routing | `plugin_version` | `0.4.0` → `0.5.0` |

Every `From` value was read from the repository at freeze time (`packages/skiller/package.json`
`0.4.0`, `packages/harness/package.json` `0.2.0`, `packages/harness/.claude-plugin/plugin.json`
`0.1.0`, `packages/task/configs/command-routing.json` `plugin_version 0.3.0`,
`plan-protocol` SKILL `2.11.0`), so the ledger is a measurement, not an assumption.

**Byte-identical guards.** While P1.5 adds the class-B record, the 13 class-A canonical
sources, their 26 projections and their lock bytes stay byte-identical; while P2.2
publishes, `repository-bootstrap` stays `0.2.0` and byte-identical. Any other publication
unit not named for an owner must remain byte-identical during that owner's generation.

## The item baseline carrier (D36)

`artifacts/<owner>/base-sha.txt` is the **sole** producer of `ITEM_BASE_SHA`.

- It is created **after all Required Reads and before any other item-owned write**, from the
  exact current `HEAD`, and only when every owner path except that carrier is clean.
- On resume the existing file is **validated and reused byte-for-byte, never recomputed**:
  exactly one lowercase 40-hex line, object type `commit`, ancestor of `HEAD`, and the
  owner's declared carrier path.
- A missing carrier with dirty owner paths, a malformed / non-commit / non-ancestor SHA, an
  owner/path mismatch and any overwrite attempt **fail closed**.
- `baseline --verify-and-print` is the only mode that emits the value; it never writes.
- The carrier is committed with the item's `Files`.

Dirty owner paths stop the capture — they are never stashed, reverted, reset or "tidied":
that remains a commit-hygiene rule of the plan, and this guard obeys it.

## Diff-scope guard with foreign-commit attribution (D47)

For the range `$ITEM_BASE_SHA..HEAD` plus the working tree, every changed path is classified:

| Class | Rule |
|:--|:--|
| `owned` | the path matches the owner's declared path set |
| `foreign-commit` | the path lies **outside** the owner set and was changed **only** by commits outside this item's own commit set → reported, excluded from undeclared drift |
| `undeclared drift` | the path lies outside the owner set and is not attributable to a foreign commit → failure |
| fail closed | a **foreign commit touched an owner path** → failure naming the exact commit(s) and path, plus an Owner question |

The item's own commit set is derived, not asserted: a commit in the range belongs to the
item when its entire footprint stays inside the owner path set or the plan carve-out
`plans/**`. Attribution **never mutates, reverts or widens** — it classifies and reports.
Parallel work by another plan therefore neither corrupts this item's proof nor becomes its
silent payload.

Retained alongside attribution, unchanged in strength:

- **private-source leakage** — the private/source-only bucket
  `packages/skiller/skills/repository-bootstrap/` may not be published as an ordinary unit,
  sourced by one, or listed in a unit's `skills[]` in either marketplace;
- **version/tuple completeness** — every declared bump of the owner is materialised in its
  exact carrier (`package.json` version, `publication-versions.json` unit,
  `command-routing.json` `plugin_version`);
- **byte-identical guards** — a guarded path touched inside the range is a failure;
- **no-op second check** — the guard is deterministic: a second run on an unchanged tree
  prints byte-identical output.

The guard's report is machine-readable JSON (`owner`, `baseline`, `head`, `own_commits`,
`owned`, `undeclared_drift`, `foreign_commit`, `failures`) and its exit code is non-zero
whenever `failures` is non-empty.

## Consumers

P1.2, P1.3 and P1.5 run `baseline --capture-or-verify` as step (0) and `generated-scope`
in their Validation; P2.2 and P2.3 do the same for the execution seam; P4.3 re-runs the
generated checks read-only and reopens the owning item on drift. No consumer may invent a
baseline ref, populate `ITEM_BASE_SHA` from anywhere else, relax a failure into a warning,
or extend its owner path set to swallow drift.
