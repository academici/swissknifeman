# Reproducible Skill Migration as Inert Data (`P09.06`)

This document records the deterministic migration of neutral donor skills from the legacy `swissknifeman` repository (`packages/skiller/skills/` and `packages/*/skills/`) into SKM v2 extension packs (`urn:skm:extensions:pack:v1` and `urn:skm:extensions:skill-manifest:v1`).

## Architectural Boundary: Skills as Pure Data

In legacy v1, `packages/skiller` coupled skill authoring, publication, provider projection (`.claude-plugin`, `.codex-plugin`, `skills.json`, `_index.md`), executable `scripts/`, and `evals/` inside a Python package. In SKM v2:

- **Zero code execution or legacy imports**: [`tools/migrate_skills.py`](../../tools/migrate_skills.py) reads donor directories strictly as UTF-8 text and JSON documents. No donor Python package is imported, and executable `scripts/` are never copied into skill packs.
- **Strict schema & compatibility gate**: Every generated pack is validated in memory through `build_candidate(..., scan=True)` against [`pack.v1.json`](../../src/skm/schemas/extensions/pack.v1.json), [`skill-manifest.v1.json`](../../src/skm/schemas/extensions/skill-manifest.v1.json), `validate_layout`, and `check_resource`, requiring `CompatVerdict.CLEAN` before any file is written.
- **Isolation from built-in `core` sync**: Built-in synchronization (`PackagedBuiltinPacks`) discovers packaged manifests recursively under `resources/packs/` and reserves `trust = "builtin"` exclusively for [`resources/packs/core/pack.toml`](../../resources/packs/core/pack.toml). Migrated packs live one level deeper under `resources/packs/migrated-local/<slug>/` and `resources/packs/migrated-upstream/<slug>/` with `trust = "third_party"`, `priority = -100`, and **no `[config]` table** (preserving security invariant S26).

## Corpus reconciliation

The original P09.06 migration classified 198 of 218 donor skills as migrated and 20 as excluded.
Core 2.1.0 revised that classification. The current export counts the same 209 skiller skills and
9 skills from the other donor packages. Its 18 migrated packs contain 106 local skills and 28 upstream skills.
The per-skill records and exclusion reasons are in [the export](../../resources/overlays/exports.json).

| Export field | Count |
|---|---:|
| `source_total` | 218 |
| `migrated` | 134 |
| `excluded` | 84 |
| `packs` | 18 |

## Migrated Topic Packs

Neutral local skills (`provenance.source = "local"`) and upstream-mirrored skills (`provenance.source = "upstream"`) are emitted into separate packs so operators can enable or audit upstream mirrors independently of authored topic packs:

| Topic | Local Pack (`migrated-local/`) | Skills | Upstream Pack (`migrated-upstream/`) | Skills |
|---|---|---:|---|---:|
| `ai` | `migrated-ai` | 1 | `migrated-upstream-ai` | 3 |
| `architect` | `migrated-architect` | 12 | `migrated-upstream-architect` | 3 |
| `business` | `migrated-business` | 23 | `migrated-upstream-business` | 7 |
| `devops` | `migrated-devops` | 10 | `migrated-upstream-devops` | 1 |
| `frontend` | `migrated-frontend` | 4 | `migrated-upstream-frontend` | 2 |
| `general` | `migrated-general` | 21 | `migrated-upstream-general` | 2 |
| `laravel-php` | `migrated-laravel-php` | 13 | `migrated-upstream-laravel-php` | 8 |
| `platforms` | `migrated-platforms` | 11 | — | 0 |
| `python` | `migrated-python` | 2 | — | 0 |
| `quality-security` | `migrated-quality-security` | 9 | `migrated-upstream-quality-security` | 2 |

Exact SHA-256 pack and resource digests are pinned in [`resources/overlays/exports.json`](../../resources/overlays/exports.json).

Every skill manifest declares a non-empty `roles` list drawn from the seven-role enum (`scout`, `executor`, `reviewer`, `triager`, `advisor`, `researcher`, `registrar`). A skill with no declared role is not selectable. `tools/check_skills.py` (`make check-skills`, also part of `make check`) refuses an empty or unknown role, a missing or unparsable `SKILL.md`, a `requires` target that does not exist, and a scan root that is missing or not a directory. A `requires` edge whose dependency shares no role with the parent is a warning: selection will not expand it. `requirement-critic` stays `reviewer` while `brd` stays `advisor`, and `laravel-security-audit` stays `reviewer` while `static-analysis` stays `scout`, so those reviewer audits do not pull the authoring skills into the closure.

## Normalization Rules

1. **`SKILL.md` Frontmatter (`§4.2`)**:
   - UTF-8 BOMs (`\ufeff`) are stripped and line endings are normalized to `\n`.
   - Legacy frontmatter keys (`bucket`, `version`, `risk`, `persona`, `tags`, `requires`, `produces_for`, `outputs`, `snippets`, `adapters`, `sha256`, `when_to_use`, `disable-model-invocation`) are removed from `SKILL.md` so only `name` (matching directory key) and single-line `description` (`1..1024` chars) remain, verified by `parse_skill_frontmatter`.
   - Duplicate directory names across buckets are disambiguated deterministically via declared frontmatter key (`php/naming-conventions` -> `php-naming-conventions`).
2. **`manifest.toml` (`urn:skm:extensions:skill-manifest:v1`)**:
   - `selection.json` and frontmatter fields map into `kind` (`procedure` -> `workflow`, `contract`/`tool` -> `domain`), `risk` (`read` -> `low`, `draft` -> `medium`, `write`/`exec` -> `high`), `roles`, `requires`, `requires_tools` (`<srv>-mcp` -> `mcp__<srv>__tools`), `exclusive_group`, `replaced_by`, `[triggers]`, and `conflicts_with`.
   - Pack-level `[[exclusive_groups]]` definitions are ported from donor `packages/skiller/configs/exclusive-groups.json` for every group referenced by a pack's skills.
3. **Provenance & Deterministic Digests**:
   - `upstream.json` entries with valid `repo` and mirrored local files emit `provenance.source = "upstream"`, `repo`, `strategy`, SPDX `license`, `upstream_sha`, `audit_verdict`, quoted ISO date strings (`fetched_at`, `audit_at`), and `[[compat_accepted]]` waivers where audited.
   - Any empty `sha256` in `upstream.json` `files[]` is deterministically computed from the normalized local file bytes (`hashlib.sha256`).
   - Reference-only link records without vendored files (`voice-ai` `kind = "reference-only"`) normalize to `provenance.source = "local"`.
4. **Layout Hygiene & File-Count Compaction**:
   - Allowed payload paths are strictly `SKILL.md`, `manifest.toml`, `references/**`, `snippets/**`, and `examples/**`.
   - Singular `reference/` directories are normalized to `references/` with relative links updated.
   - When an upstream reference skill exceeds the 200-file resource limit (`vueuse-functions`, 266 files), `references/catalog.md` is kept untouched under its upstream SHA-256 while per-function leaves are deterministically bundled into `references/bundle-<a..z>.md` without losing text.
   - Generated and legacy artifacts (`evals/`, `scripts/`, `selection.json`, `upstream.json`, `compat-report.json`, `SYNC.md`, `GENERATION.md`, `_index.md`, `skills.json`, `.claude-plugin`, `.codex-plugin`) are dropped.
5. **Machine-Translation Policy**:
   - Skills containing machine-translation markers (`machine-translated`, `translated automatically`, `autotranslated`, `машинный перевод`) are flagged in `exports.json["machine_translation_policy"]["flagged_skills"]` (`0` flagged in the current corpus) and blocked from `core` promotion until human editorial review.

## Excluded Skills & Operator Overlays (Criterion G36)

Eighty-four donor skills are excluded from neutral packs and cataloged in [`resources/overlays/exports.json`](../../resources/overlays/exports.json) with all four G36 answers (`users`, `extension_point`, `compatible_without_it`, `removal_test`). See [`docs/extensions/overlays.md`](../extensions/overlays.md) for packaging and enabling operator overlays:

- Eight skills already ship in core, including `code-review` (`already_in_core`).
- The export records 56 skills pruned from the packaged catalog (`pruned_from_builtin_packs`) and one moved to an agent pack (`moved_to_agent_pack`).
- **`personal_overlay_bucket` (`6`)**: `axioma-doctrine`, `axioma-glossary`, `axioma-stack`, `ecosystem-map` (`axioma`), `azguard` (`azguard`), `botkit` (`botkit`).
- **`legacy_monorepo_package` (`9`)**: `session-observer` (`analyst`), `brain-locator` (`brain`), `agent-packs` (`harness`), `cross-project-coordinator`, `local-topology`, `shared-memory`, `swissknifeman-locator` (`maind`), `plan-protocol`, `workflow-craft` (`planner`).
- **`ecosystem_coupled_skill` (`3`)**: `skills-ssot`, `mcp-advisor` (`general`), `defensibility` (`founder`).
- **`personal_language_overlay` (`1`)**: `writing-style` (`general` — prescribes Russian-by-default prose for internal code artifacts).

## Reproduction & Verification Commands

Preview the migration without touching the filesystem (`--dry-run`):

```bash
uv run --frozen python tools/migrate_skills.py \
  --source ../swissknifeman \
  --output resources/packs \
  --overlay-export resources/overlays/exports.json \
  --dry-run
```

Regenerate all migrated packs and [`resources/overlays/exports.json`](../../resources/overlays/exports.json) deterministically:

```bash
uv run --frozen python tools/migrate_skills.py \
  --source ../swissknifeman \
  --output resources/packs \
  --overlay-export resources/overlays/exports.json
```

Run the integration and PostgreSQL installation suite ([`tests/integration/extensions/test_migrated_packs.py`](../../tests/integration/extensions/test_migrated_packs.py)):

```bash
uv run --frozen pytest -q tests/integration/extensions/test_migrated_packs.py
```
