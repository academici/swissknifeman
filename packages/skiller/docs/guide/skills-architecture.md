# Skills architecture: real state

> **Read first** before any sentence «rewrite the skills architecture».
> This document documents how the system works **actually** — so that audits and
> agents did not project on top of the wrong picture. Numbers (skill counters/buckets)
> — source of truth `skills.json` and `skills/_index.md`, here are approximate.

## TL;DR

skiller — this **registry of ready-made, hierarchically organized EN-only skills** with
dependency graph, which is distributed to projects through two independent channels. Skills
**are not monolithic**, they have **yes** frontmatter, dependencies and implicit layers. Bodies
reads skills in runtime **agent itself (Claude Code)**, and not Python-process skiller —
therefore «skill loading cache» inside skiller has no caller (see §7).

## 1. Where do the skills and EN-only model

- Skill is **directory** with file `SKILL.md`: `skills/<bucket>/<name>/SKILL.md`.
- For local and upstream-skills `SKILL.md` — the only one canonical carrier.
  Provider projections, registry, locks and marketplace are generated from it by the command
  `skiller registry`; parallel locale-source and source-hash marker no.
- External (upstream) skills: provenance/Sinka strategy live in `upstream.json`
  (see `upstream-sync`).
- **Internal** repository skills (`.claude/skills/*`, e.g. `package-architecture`)
  — single `SKILL.md`, are not bilingual and cannot be heard (soft lint in `validate.sh`).

Details: [Anatomy of a skill](./skill-anatomy.md), [Creating skills](./creating-skills.md).

## 2. Frontmatter and metadata

Everyone `SKILL.md` carries the frontmatter (`SKILL_TEMPLATE.md` — canonical schema):

```yaml
name · bucket · version · description · risk · invocation_intent · capabilities ·
inputs · outputs · resources · provenance · sha256
```

- **`invocation_intent`** — semantic policy `automatic|explicit`; for `write` and
  `external` required explicit intent.
- **`capabilities`, `inputs`, `outputs`, `resources`** — provider-neutral Skill Core;
  provider-native controls are not included in shared frontmatter.
- **`provenance`** — local/upstream source and refresh ownership.

`scripts/generate-skill-template.py --check` verifies the generated template copy, while
`scripts/check-translations.sh --strict` enforces the EN canonical source and forbids provider
controls in the shared carrier. Both checks are included in `validate.sh`.

Metadata source of truth - `skills.json` (is generated `skiller registry`).

## 3. Buckets and grouping

Skills are grouped into buckets by **domain + roles** (and not «one bucket = one language»):

- by role: `architect`, `oss-dev`, `pm`, `founder`, `operator`, `quality`, …;
- by technology: `php` + thin `laravel-*` (`laravel-testing/auth/data-layer/…`),
  `frontend` + `frontend-*` (`vue/nuxt/tailwind/…`), `devops`, `python`, …;
- by business domain: `legal`, `finance`, `marketing`, `security`, …

Bucket metadata (description/category/tags) are required in `buckets.json` (1:1 with
directories, checks `validate.sh`). See [Taxonomy](./skill-taxonomy.md).

## 4. Implicit levels (tiering) — already exists

«Base layer that is distributed to everyone» **already** is encoded, just not in the directory tree:

- `CORE_SKILLS` / `CORE_PLUGIN` (`lib/skiller/config.py`, declaratively in `configs/core-policy.json`) —
  token-saving **core**, is distributed to EVERY project by default (`--no-core` disables). B
  **connect** this is curated marketplace-plugin `core` (`source:"./"` + `skills[]` via links, without
  copies) — loads EXACTLY those listed in `CORE_SKILLS` skills instead of whole buckets
  `general`+`oss-dev` (was ~1956 resident ⊕ tier-0 current; current resident CORE — command
  `skiller budget --check-core`, number/kernel composition changes, no hardcode snapshot in dock). B
  **vendor** — the same `CORE_SKILLS` file by file. `CORE_BUCKETS` left for autodetect-fallback and
  migration-tips.
- `profiles/*.json` — sets of buckets by project type (autodetect → profile).
- `presets/*.json` — named cross-cutting skill clusters (vendor).
- opt. field `level` (§2) gives this explicitly in the frontmatter, without moving files.

Therefore **re-cutting skills into a tree `core/foundation/extension` not required** —
benefit (self-documenting layers) is reached by the field `level`; moving price (193
canons, 49 plugin names, consumer locks) is disproportionate. A full analysis of rejected proposals is in section 9 below.

## 5. Two distribution channels

| Channel | What it does | Granularity | Config |
|:--|:--|:--|:--|
| **connect** | bucket = plugin Claude Code marketplace; writes `enabledPlugins` in `.claude/settings.local.json`; skills are NOT copied, they are automatically updated from the registry | **bucket-granular** (skill-level `exclude` ignored) | `.swissknife.json` |
| **vendor (`sync`)** | physically copies skills to `.claude/skills/`; files are committed to the project repo; for projects without registry access | **skill-granular** (`include`/`exclude` by skills) | `.swissknifeman/config.json` |

For external Codex connect-project canonical carrier — self-contained
marketplace under `.agents/plugins/`. If in the same project there is vendor-config,
`skiller update` continues to update independent Claude-copies to
`.claude/skills/`, but does not create a duplicate Codex vendor tree
`.agents/skills/`. Explicit `skiller sync` remains independent vendor-operation
and follows provider selection project.

Legacy `skiller vendor --agent cursor|generic` — copies to `.cursor/.ai` (for Claude
deprecated, use `sync`). See [Vendor-mode](./vendor-mode.md).

## 6. Two project configs (important - common source of confusion)

In the system **two** project config with **different roles**. They do not need to be merged:

- **`.swissknife.json`** — easy config for `connect` (+ legacy vendor):
  `project_type/buckets/exclude/presets/agent/skills_path` (+ `memory_brain`,
  `coordinator_ignore` and fields agent-framework `shape/stacks/skills_map`). Full
  list - `CONFIG_KEYS` (`lib/skiller/common.py`), validator `config.validate_config`.
  **bucket-granular.**
- **`.swissknifeman/config.json`** — canonical source of truth **vendor-mode**:
  `version/mode/agent/skills_path/presets/include/buckets/exclude`. Keys -
  `SKILLSET_KEYS` (`lib/skiller/skillset.py`), validator `load_skillset_config`.
  **skill-granular.**

Bridge: at first `sync`/`init` `.swissknifeman/config.json` **lazily materializes**
from the project profile (or from legacy `.swissknife.json`), non-destructive. Separate
migration commands are not needed.

JSON-diagrams of both configs - `schema/*.json` (autocompletion in the editor via
`$schema`). Runtime validation remains manual and stdlib-only; circuits are kept in sync
with gate code `tests/test_schema.py` and checking `skiller doctor`.

Bootstrap: **`skiller init`** creates `.swissknifeman/config.json` from autodetect
(without copying skills - this does `sync`).

## 7. How skills are consumed in runtime (and why «download cache» no)

**Cannot read skill bodies skiller, and the agent himself (Claude Code):**

- vendor → skills are physically located in `.claude/skills/<name>/SKILL.md`; Claude Code
  loads them from disk **himself**.
- connect → marketplace points to the registry; Claude Code reads `SKILL.md` from there.

Python-process skiller **never reads the skill body in runtime** — no function
`load_skill`, no `loader.py`. skiller only **copies files** (vendor),
**registers plugins** (connect) and **parses frontmatter** (registry/budget/vendor —
for metadata, not for body distribution).

Consequence: **caching subsystem «loading skills» inside skiller does not have
caller** — there is nothing to cache. Saves tokens on repeated requests
**prompt caching** on the side Anthropic/Claude Code (automatically, «no proxy
needed») — for its effectiveness, it is the stable order and size of the skills that is important, not ours
subsystem. Token mathematics is calculated by a single module `budget.py` (`skiller budget`).

## 8. Artifacts sync and drift detection

- `skills-lock.json` — map installed: `managed:true` + `sha256` (by `SKILL.md`) +
  `content_sha256` (by **entire directory** skill) — distinguishes our vendor-copies from
  aliens/manual; sync touches only `managed`. **Incremental sync** (`plan_sync`):
  copies only `add`/`update`, unchanged `keep` does not touch, retired `managed` prunit.
  Drift is caught by `content_sha256`, therefore changes to `snippets/`/`references/` (with unchanged
  `SKILL.md`) also trigger `update`. Old locks without `content_sha256` degrade correctly
  (drift by `SKILL.md`), field beforepopulated at the next sync without recopying.
- `.swissknifeman-manifest.json` — reinstallation manifest (`installed_at/profile/…`).
- Resolve dependencies: `vendor.build_requires_index` + `resolve_requires`
  (transitive bypass `requires`) — at stage **samples** (setup-time), is not in runtime.

## 9. What is NOT included here and why

Peer reviewed audit (`research/swissknifeman_skills_architecture.md`,
`research/swissknife_cache_and_config.md`) suggested several things, **rejected**
after checking with the code:

| Audit proposal | Solution | Reason |
|:--|:--|:--|
| 3-level directory refactoring | **rejected** | goal already solved skill-granular vendor; price churn disproportionate; opt. field `level` allows self-documentation without moving |
| Caching subsystem (`SkillMemoryCache`/disk) | **rejected** | no caller (§7); prompt caching automatic |
| `core/resolver.py`, `core/project.py` for the config | **rejected** | resolve already in `vendor.py`; `core/project.py` already exists (type detector) |
| Single `swissknife.json` | **is not entered** | two configs have different roles (§6) |

Accepted for implementation: `skiller init`, JSON-schemas + checks `doctor`, opt. field
`level`, this documentation. Full review - in decision-record header research-docs.

## Related Documents

- [Anatomy of a skill](./skill-anatomy.md) · [Taxonomy](./skill-taxonomy.md)
- [Vendor-mode (sync)](./vendor-mode.md) · [Profiles and auto-detection](./profiles.md)
- [Registry skills.json](./registry.md) · [Token budget](./budget.md)
- [Methodology: Anti-Bloat](./methodology.md)
