---
title: Distributing local .ai/ content to providers (dev-plan)
---

# Multi-provider distribution of local `.ai/` content (dev-plan)

> **Status:** development plan, feature NOT implemented. The document records the task and target design,
> to skiller was able to replace the role `php artisan boost:update` as a cross-provider generator
> context for AI-agents. Reference-implementation «hands» — pilot in the project `sibintek-insiders`
> (see section [Migration from Boost](#migration-with-boost)).

## Why

Ecosystem Projects (Laravel) keep the agent context source of truth in its own directory
`.ai/`: `.ai/guidelines/*.md` (permanent rules) and `.ai/skills/<name>/SKILL.md` (narrow contexts).
Today is the giveaway of this **local** content on providers does **Laravel Boost** (`boost:update`):
generates `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`, puts skills in `.claude/skills`/`.cursor/skills`,
writes `.cursor/rules/*.mdc`. We want to remove this role from Boost (leave Boost only MCP) and give
her **skiller** — to a single ecosystem distributor to Cursor/Gemini/Codex worked the same way as Claude.

## Problem / gap

skiller is giving away today **only your registry** (`env.root/skills/<bucket>`), not local `.ai/`
consumer:

- `vendor.py` `collect_skills()` (≈`vendor.py:154`) and `skillset.py` `resolve_skillset()`
  (`skillset.py:130-179`) resolve selection against registry index (`skills.json`), doesn't mind the directory
  target project. The source is always the registry.
- Hub Generator (`scripts/generate-hub.sh` — thin launcher on top `lib/skiller/hub.py`) can
  write controlled block to `CLAUDE.md`/`AGENTS.md` (markers
  `<!-- swissknifeman:hub:start/end -->`) — but this **index** installed skills, not
  **text aggregation** `.ai/guidelines/*.md`. Block form provider-dependent: targets with native
  skills listing (`CLAUDE.md`, Boost-fragment, `AGENTS.md`) get the short form without
  confirmed by the native set of names. For `AGENTS.md` generator reads real offline
  `codex debug prompt-input` from cwd project; saves unconfirmed names.
  Unlisted targets (`GEMINI.md`, layouts Cursor) get the full form; `--full-index` returns index
  all purposes. Reduction is allowed only after machine verification of detection - see.
  [installation.md](./guide/installation) («Block form: by target channel, not by project»).
- Fan-out of providers is narrow: `AGENT_DEFAULTS` (`common.py:23`) only knows skill paths for
  `claude`/`cursor`/`generic`. No generation `.cursor/rules/*.mdc`, `GEMINI.md`, no aggregation
  guidelines.

Summary: «local `.ai/` → all providers» has nothing to close now. We need a new ability.

## Team Target Design

New command (working name) **`skiller distribute`** (alternative - expand `vendor --source`):

```bash
skiller distribute [--source .ai] [--providers claude,cursor,gemini,agents] \
                   [--target DIR] [--dry-run]
```

- **source** — arbitrary local project directory (`.ai/skills` + `.ai/guidelines`), NOT registry;
- idempotent, merge-only, backup `*.bak` (convention skiller);
- coexists with registry `connect`/`vendor` (different sources - do not conflict).

## Provider Matrix

| Provider | guidelines → | skills → | skill format |
|:--|:--|:--|:--|
| **claude** | `CLAUDE.md` | `.claude/skills/<name>` (symlink to `.ai/skills/<name>`) | `SKILL.md` as is |
| **cursor** | `.cursor/rules/<slug>.mdc` (frontmatter `alwaysApply: true`) | `.cursor/skills/<name>` (symlink) | `SKILL.md` as is |
| **gemini** | `GEMINI.md` | — | — |
| **agents/codex** | `AGENTS.md` | — | — |

Implementation: expand `AGENT_DEFAULTS` (`common.py:23`) to table target-paths per-provider
(guidelines-file + skills-directory + strategy), be placed in a single provider registry.

## Aggregation engine guidelines

- input: `.ai/guidelines/*.md` (top-level markdown, sort by name);
- output: concatenation into provider file with managed header + delimited `=== <name> ===`
  (same style as Boost-block - backwards compatibility of perception);
- for `cursor` — wrap in frontmatter `.mdc` (`alwaysApply: true`);
- **not-md formats** (`.blade.php` etc.) **ignore** — they require rendering Boost (Blade+Roster),
  not responsible skiller. Managed block - between markers, so as not to overwrite manual content.

## Symlink vs copy

Now vendor only **copies** (`shutil.copytree`, `vendor.py`). For **local** source
skills are already in the project (`.ai/skills/`) — duplicating with a copy is pointless: we use **symlinks**
`.claude/skills/<name> → ../../.ai/skills/<name>` (as done manually in the pilot insiders). Strategy
per-provider: registry source → copy (like now), local source → symlink.

## Idempotency / manifest / lock

- reuse `.swissknifeman-manifest.json` (section for distribute-source) and `skills-lock.json`
  (`lock.py` already distinguishes between sources `swissknifeman`/`laravel-boost`/`local` — add `local-ai`);
- cleaning stale — only managed-entries distribute; manual symlinks/do not touch files;
- marking `managed: true` + source path as in `skillset.py:316-322`.

## Migration from Boost

Recipe «Boost → only MCP» (worked out manually in the pilot `sibintek-insiders`):

1. `boost.json`: `guidelines:false`, `skills:[]`, `mcp:true` (Boost remains MCP-server).
2. Demolish Boost-skill installations (`.claude/skills`/`.cursor/skills` — non-symlink package directories)
   and Boost-guideline-artifacts (`.cursor/rules/laravel-boost.mdc`, `.ai/guidelines/*.blade.php`).
3. Unhook `@php artisan boost:update` from `composer.json` `post-update-cmd`.
4. Distribute local `.ai/` via skiller (target feature); before it - temporary
   `scripts/build-agent-docs.sh` in the project (Claude-only).

Rolling out to other similarly structured projects (`flexcrm`, `sova` and others - the same
`<laravel-boost-guidelines>` + `.ai/` + symlinks) — with the same command.

## Phases (milestones)

1. **M1 — provider-registry**: table target-paths per-provider from `AGENT_DEFAULTS`; only claude
   (parity with `scripts/build-agent-docs.sh`).
2. **M2 — aggregation guidelines**: concatenation engine `.ai/guidelines/*.md` → `CLAUDE.md`/`AGENTS.md`,
   managed markers, skill index.
3. **M3 — cursor**: `.cursor/rules/*.mdc` + symlinks `.cursor/skills`.
4. **M4 — gemini/agents** + lock/manifest integration, `--dry-run`, cleaning stale.
5. **M5 — migration helper**: `skiller distribute --from-boost` (automates the migration recipe).

## Test plan

- `scripts/test.sh` (unittest, stdlib-only, without network/php) — consumer fixtures in tmpdir:
  synthetic `.ai/guidelines/*.md` + `.ai/skills/*/SKILL.md`;
- checks: idempotency (rerun does not change the bytes), merge-only (manual content intact),
  symlinks point to `.ai/skills`, managed block is limited by markers, `--dry-run` without entry;
- `scripts/validate.sh` green; after editing the registry - `skiller registry`.

## Explicit design choice Codex plugins

```bash
packages/skiller/bin/skiller connect --target /path/to/project --native-codex --dry-run
packages/skiller/bin/skiller connect --target /path/to/project --native-codex
```

`--native-codex` requires Python 3.11+ (stdlib `tomllib`) and agrees `[plugins."<name>@swissknifeman"].enabled` in the design
`.codex/config.toml` with set selected Connect. Selected plugins receive `true`,
other known and inherited Swissknifeman-plugins - `false`. Global defaults,
third-party plugins, permissions, others TOML-fields and comments are retained. Before change is done
full parse/render preflight; the modified file has `.bak`, restart is idempotent.
Non-standard inline/dotted layout plugin tables is rejected until the project is changed;
use separate `[plugins."name@swissknifeman"]` tables. Codex reads the design
configuration in trusted projects. The flag does not set cache: availability `.agents/plugins/bundles`
is not enough for native activation. Install missing plugins explicitly `codex plugin add`,
then check `codex plugin list --json` and `codex debug prompt-input` from cwd consumer.

In combination with `--hub` native selection is applied before hub generation; for ordinary
project are updated `CLAUDE.md` and `AGENTS.md` with text saved outside managed-blocks.
B Boost-project retains the existing path through guideline-fragment.

`--cleanup-codex-vendored` archives manifest-declared legacy copies separate from installation.
`--cleanup-codex-links` archives only recognized managed links: or native replacement
matches all source files of the skill, or this exact path is explicitly disabled in the project
`[[skills.config]]`. If there is a mismatch, someone else's ownership or the changed link, the data is saved.
Unique local skills remain without explicit disabling. This also allows you to remove old
links in clients where project-level per-skill selection does not yet affect discovery.

## Codex publication — consumer-acceptance gate

> Not applicable `skiller distribute` (the feature above remains unimplemented dev-plan) — this
> separate, already WORKING check of an existing distribution Codex-plugins via
> `.agents/plugins/marketplace.json`. Placed on this page as the only place
> where the behavior of multi-provider distribution is documented Codex.

**Why.** Internal generator/unit-checks (`test_codex_publication.py` etc.) are verified
only STATIC schema of generated artifacts - they never ask anything from
present `codex` CLI. Azguard, 2026-07-21: this check class was GREEN, and fresh
Codex-session not seen `task-plan-run`/`task-plan-exec` — sibling-plugin `task` was
invisible to native marketplace discovery. Package-level GREEN without going through the entire chain
`source → marketplace → install/cache → clean consumer → fresh session` is not release
GREEN.

**What it checks** `packages/skiller/tests/test_codex_consumer_acceptance.py`:

1. Independent (not via `publication.render_codex_publication`) inventory expected
   Codex-plugins - compiled directly from disk (`buckets.json`, `configs/core-policy.json`,
   `skm/.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` neighboring packets) — is verified
   with what really gives `codex plugin list --available --json` from isolated
   `CODEX_HOME`.
2. Installation `task@swissknifeman` to isolated temp `CODEX_HOME` + cache reconciliation
   byte-for-byte with source, without touching the real one `~/.codex`.
3. `codex debug prompt-input` (offline render prompt'and models, without network/auth) from temp
   consumer-directory OUTSIDE the repository - confirms that `task-plan-run`
   is visible by name and is resolved from the isolated cache, not from the repository
   `.agents/skills` (the latter is a proven source of false GREEN, see test
   `test_repo_local_skills_would_mask_a_real_publication_failure`: same run from root
   of the repository really mixes it up `.agents/skills` in discovery).
4. Drift of exported surface without version bump — RED (`InventoryDriftDetectionCase`,
   does not require live `codex`).

**Explicit behavior when there is no `codex`.** `scripts/validate.sh` (gate 18) prints
`SKIP: ... gate was NOT run` and remains green if the binary `codex` not found in `PATH` —
skip and GREEN are distinguishable in the output. Locally (where `codex` installed) gate is executed
live run; in CI binary is not available today - the gate is there SKIP, installation issue `codex`
in CI-runner outside the scope of this item'a.

## Current operator boundary

The M1–M5 distribution design above remains a roadmap, not an instruction to delete or rewrite a
consumer. For committed provider distribution, first inspect the generated root
`docs/provider-support.md` matrix and run a no-write command:

```bash
packages/skiller/bin/skiller connect --dry-run
packages/skiller/bin/skiller sync --target <project> --dry-run
```

`connect` updates the Claude Code marketplace projection; `sync` writes selected managed skill
projections only when the project's config selects that channel. `sync --repair` is a separate
managed-drift operation, not a general overwrite. Unsupported capabilities, missing provider
evidence, and a skipped consumer-acceptance probe remain non-green. Apply only after the command's
ownership/backup gate is satisfied; preserve the managed preimage and use the same declared target
for readback or rollback. Neither command authorizes a release, tag, or publication.

## Related

- [Compatible with Laravel Boost](./boost-compatibility) — current coexistence model (Boost like
  skill source vs skiller); this document describes the next step - removing the distribution from Boost.
