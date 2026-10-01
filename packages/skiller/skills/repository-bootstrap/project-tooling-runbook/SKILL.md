---
name: project-tooling-runbook
bucket: repository-bootstrap
version: 0.1.1
description: "Use when configuring ecosystem skill delivery, agent-packs, or Brain docs sync; preserve existing channel ownership."
risk: draft
persona: oss-dev
tags: [runbook, skills, docs-sync, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Runbook: project skills (multi-source) + doc-sync (brain)

You manage this. The maind hub (onboarding/memory/graph) is separate, see [ecosystem-integration].
This skill covers **project role skills** (from several sources) and **documentation sync**.

[ecosystem-integration]: ../ecosystem-integration/SKILL.md
[harness-operations]: ../harness-operations/SKILL.md
[maind-overview]: ../maind-overview/SKILL.md
[field-feedback-loop]: ../field-feedback-loop/SKILL.md

## Project skills — source COMPOSITION (not just swissknifeman)

Project skills come from **several independent sources**, each with its own config, that
**peacefully compose into one set**. This is by design — a flexible system, not "swissknifeman
only".

| Source | Own config | What it is |
|:--|:--|:--|
| **swissknifeman** | `skills.json` (registry) → **two install channels** (below) | curated role buckets/skills |
| **Laravel Boost** | `boost.json` (`mcp`/`guidelines`/`skills[]`) | **MCP + guidelines only** — not used as a skills channel (below) |
| **local** (own) | — (just a folder `.claude/skills/<name>/`) | your own skills / rolled out from another hub (e.g. `ecosystem-mcp` from maind) |

### swissknifeman installs skills via two ownership channels

Reuse the project’s configured channel and the owner’s existing authorization. Ask only when
a new channel choice is unresolved and materially changes repository ownership or delivery:

| Channel | Command | What it does | Granularity | In repo |
|:--|:--|:--|:--|:--|
| **connect** (marketplace) | `skiller connect` | enables bucket plugins via `enabledPlugins` in `.claude/settings.local.json`; `extraKnownMarketplaces` points to a **local path to the swissknifeman registry** | **whole bucket only** | skill files NOT copied |
| **vendor** (physical transfer) | `skiller sync` | copies selected skills into `.claude/skills/`, writes `skills-lock.json` (`managed`) | **individual skills** (include/buckets/exclude) | yes, visible and committed |

- **connect** — when you don't need repo commitment and "the whole bucket" is fine. ⚠️
  **Requires access to the swissknifeman registry** (marketplace = local path): a developer
  without the swissknifeman repo won't get the plugins — they won't see the skills. Good for
  your own environment / internal ecosystem.
- **vendor** — when you need to: **hand skills to external developers who don't have
  swissknifeman access** (files live in the project's own repo); see skills in the repo; pick
  exactly the needed items across areas; update from the library via a lock file. Config —
  `.swissknifeman/config.json` (`mode: "vendor"`, `include`/`buckets`/`exclude`). See
  swissknifeman docs → "Vendor mode (sync)" guide.

> **Two configs, don't confuse:** `.swissknife.json` (connect + legacy vendor, bucket-granular)
> vs `.swissknifeman/config.json` (vendor `sync`, skill-granular). Canon — swissknifeman docs
> `guide/skills-architecture.md` §6.

> For an unresolved choice, explain: "connect (bucket plugins, not in repo; needs registry access)" vs
> "vendor (physical skill copies in repo + lock; works for external developers)". Default
> recommendation — **vendor**, if the project is handed to external developers or needs set
> control and repo commitment.

> **Skills only.** The channel choice applies ONLY to skills (they have no other capability
> besides file distribution). Memory/graph/hub MCP tools are configured as usual, independent of
> the skills channel.

**The channel is also asked during onboarding** (`swissknifeman setup` / `maind onboard` /
`skiller integrate`):
- `swissknifeman setup <p>` and `maind onboard <p>` interactively ask `connect/vendor` (flag
  `--skills-channel connect|vendor` for non-interactive; default `connect`).
- `skiller integrate` accepts `--skills-channel`; with `vendor` for a Claude project it **routes
  to modern `sync`** (generates `.swissknifeman/config.json` from a profile → physical copies
  into `.claude/skills/`).
- The `vendor` channel for **Cursor/Gemini** (`.ai/.cursor/skills`) is a separate legacy command
  `skiller vendor --agent cursor|generic` (`--agent claude` deprecated; use `sync`).

**`skills-lock.json`** (committed, like `composer.lock`) is written by **two** commands,
depending on the channel:
- **vendor**: `skiller sync` writes the lock itself — every transferred skill gets a record
  `source: swissknifeman` + **`managed: true`** + `sha256`. On sync, records dropped from the
  config get `managed` removed; **foreign records (not `managed`) are untouched**.
- **connect / mixed**: `skiller lock` (read-only composer) — scans what's installed
  (`.claude|.cursor|.ai/skills`) ∪ `boost.json::skills[]` and stamps `source`: name in the
  registry → `swissknifeman` (wins); in `boost.json::skills` → `laravel-boost`; else → `local`.
  A conflict (name in several sources) is **not lost**: the winner is in `source`, the loser in
  `also_in`. **Boost doesn't "eat" local skills just because it's connected.**

In vendor mode the arbiter is `sync` (config → managed-lock). `lock` is for connect/mixed
projects. Your own local skills are **legitimate** — write them when you need project context
missing from the library (`sync` doesn't overwrite them — they aren't `managed`).

### swissknifeman buckets (roles)

| Role | Bucket | Contents (examples) |
|:--|:--|:--|
| **Architect** | `architect` | architecture, api-design, data-schema, security-design, tech-stack-selection, observability-design |
| **Developer (PHP/Laravel)** | `php` (core) + `laravel-*` | `php`=laravel/structure/DI/database/repositories/patterns/static-analysis; feature buckets: `laravel-testing`, `laravel-filament`, `laravel-livewire`, `laravel-data-layer`, `laravel-auth`, `laravel-architecture`, `laravel-extras`; `php-packages` (package development); `azguard`/`botkit` (own packages) |
| **Frontend** | `frontend` (core) + `frontend-*` | core: web-design-guidelines/document-writer/filepond; feature buckets: `frontend-{vue,nuxt,tailwind,naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}` |
| Other | `quality` `devops` `operator` `system` `founder` `pm` `general` | tests/CI/incidents/conventions/business |

**Profiles** (`profiles/*.json`) = ready-made bucket sets per project type (lean default):
- `laravel-project` → `system, architect, php, laravel-testing, laravel-auth,
  laravel-data-layer, devops, quality, operator` (Filament/Livewire — point-added via a bucket or
  the `laravel-admin` preset).
- `php-package`, `obsidian-vault`, `standalone`.

**Presets** (`presets/*.json`) = named cross-cutting stacks layered on buckets (vendor):
`laravel-admin`, `laravel-enterprise`, `laravel-inertia`, `laravel-livewire-stack` + frontend/
architect/pm/general/quality clusters. In `.swissknifeman/config.json`: `presets: [...]` (+
`include`/`exclude`). Details — `docs/guide/presets.md`.

### ⚠️ Pick the OPTIMAL set for the project — don't dump "everything"

When "set up a project" is requested (onboarding, adding/changing skills or plugins), **pick
exactly the relevant set** for the project's stack and role, not every bucket at once. Extra
roles (`php`/`python`/`mobile` on a pure frontend, frontend on a backend package, etc.) are
noise: they clutter context and devalue curation.

- The stack **determines** the set: frontend (Nuxt/Vue) → `frontend (+ general, quality,
  devops, system, roles)`; a Laravel service → the `laravel-project` profile (`php, architect,
  …` without frontend); a package → `php-package`.
- Use a **profile** as the base, then add/remove precisely for the specific project.
- **If the optimal set is unclear** (hybrid/unclear stack, several roles, contested buckets) —
  **ASK the user** via AskUserQuestion (offer 2-3 curated options), don't guess and don't
  install to the max "just in case".
- **Unrecognized type** (autodetect → `standalone`): `skiller connect/vendor` now installs a
  MINIMAL core + prints a warning (not "everything"); pass `--profile <type>` explicitly.
  "Install everything" is available only deliberately — `--profile standalone`.

> **Granularity and placement** (general=cross-stack/CORE, stack→stack bucket,
> project→project-local, connect=coarse/vendor=fine, lean SKILL.md) — canon in skiller docs
> `guide/skill-taxonomy.md`. Full tree of every setup layer (memory/ns/channel/environment/graph)
> with branches — canonical maind doc
> ["Decision tree: project setup"](../../../../../packages/maind/docs/guide/onboarding-decision-tree.md).

CLI — `swissknifeman` (run from the project directory; root is searched upward from CWD):

```bash
skiller status                       # what's connected: profile, buckets, channel; ⚠ catches CHANNEL DUPLICATE
                                     #   (bucket both plugin and vendored) — also `swissknifeman skills status`
# --- CONNECT channel (bucket plugins, not in repo) ---
skiller connect --profile laravel-project          # connect by profile
skiller connect --plugins a,b,c                    # desired set; extra Claude entries are retained
skiller connect --plugins ... --dry-run            # preview (preserves permissions/bypass)
# --- VENDOR channel (physical transfer of specific skills into the repo) ---
skiller init                         # create .swissknifeman/config.json (mode:vendor) from autodetect
#   (or manually: include/buckets/exclude; $schema gives editor autocompletion)
skiller sync --dry-run               # plan: +add ~update -remove =keep
skiller sync                         # apply (managed skills in .claude/skills/ + lock)
skiller sync --force                 # overwrite a foreign-occupied path with the library version
# --- common ---
skiller integrate --bundle recommended --yes       # wizard: asks channel (connect/vendor) + hooks/memory/hub
skiller integrate --skills-channel vendor --yes    # vendor without asking → sync into .claude/skills (for externals)
skiller lock [--dry-run]             # source map for connect/mixed projects (read-only composer)
skiller update                       # update a project's connection
```

**Laravel Boost** — keep as an **MCP server** (database-query/tinker/logs/docs) and optionally its
guidelines, but **NOT as a skills channel**. In `boost.json`: `"mcp": true`, `"guidelines": true`
(optional), `"skills": []`. Replace its former skills with direct library equivalents via vendor
(`frontend-backend/inertia-vue`, `frontend-tailwind/tailwind-conventions`,
`frontend-wayfinder/wayfinder`, etc.). A needed
Boost skill missing from the library — import it as external. The `laravel-boost` MCP server
stays in `.mcp.json` (maind appends it on onboarding if the project has `boost.json`).

For an explicitly requested smaller set, update `.swissknife.json::plugins`, disable surplus
`<plugin>@swissknifeman` Claude entries, and run `connect --dry-run` before apply. Connect retains
extra Claude entries and honors an explicit `false`; an exact plugin argument does not trim them.
Codex Connect replaces only its lock-owned bundles and refuses modified preimages. Keep local
skills; archive dangling legacy links separately with their preimages.

Codex project bundles are an available marketplace surface, not native activation. In a trusted
project, `.codex/config.toml` can select installed plugins with
`[plugins."<plugin>@swissknifeman"]` and `enabled = true`. Keep this selection aligned with
`.swissknife.json`; install missing native caches explicitly through Codex CLI and verify their
digests. Use `codex plugin list --json` from the consumer and offline `codex debug prompt-input`
to confirm the selected plugins contribute skills. Global cache versions and project bundle
versions are separate observations; never infer release delivery from a Connect success.

**Adding a role to a project** (resolve the channel from existing configuration first):
- **connect**: `connect --plugins <current>,<new>` (current — in `skiller status` /
  `enabledPlugins`). Preserves `permissions`/`defaultMode` (bypass, see
  [[auto-approve-bypass]]). Afterward — restart the session or `/plugin marketplace update
  swissknifeman`.
- **vendor**: append skills to `.swissknifeman/config.json` (`include`/`buckets`) → `skiller
  sync`. Skills appear in `.claude/skills/` immediately (restart needed for Claude to pick them
  up).

> Typical case "give the project developer+architect skills": laravel-project already gives
> `php` (developer) + `architect` (architect). If the frontend is Vue/Nuxt — add `frontend`.

> **Budget-gate doctrine.** Any new always-on injection (skill/agent/command description, hook
> additionalContext, CLAUDE.md block, MCP server) — before rolling it out, check `skiller budget
> --first-turn` (target ≤7K/warn >10K tokens; fleet — `maind doctor --context`) — root
> CLAUDE.md's "Boundaries" rule; blindly bulk-adding skills violates this doctrine.

## Project agents/roles (agent-packs) — SEPARATE from skills

Skills (connect/vendor) give **knowledge**, but do NOT install **subagents and workflow**.
Roles/agents are a separate subsystem, **`harness agent-packs`**: installs `.claude/agents/*`,
`.claude/workflows/*`, a review-gate hook (SubagentStop), and `.claude/rules/*`. **Without this
step, a large task will NOT unfold into a role-based "slice → test → review"** — you only get the
built-in `/code-review` and ad-hoc subagents. So "set up the project" = skills **AND** agent-packs
(not one instead of the other).

| Pack type | Packs | What it installs |
|:--|:--|:--|
| **stack** (detected by stack) | `backend-laravel` (artisan/composer), `node-frontend` (vite/nuxt), `python-backend` (pyproject), `dart-flutter` (pubspec) | dev-loop subagents slice-builder/test-writer/reviewer (+component-builder/type-checker), workflow, review-gate, rules |
| **role** (layered over a stack) | `role-tech-lead`, `role-maintainer`, `role-cto`, `role-founder` | persona subagents (review-gatekeeper/sprint-planner; issue-triager/contribution-reviewer/release-conductor; …) |

```bash
harness agent-packs list                          # pack catalog + detect
harness agent-packs render --pack <stack> --target . --auto      # detect stack → subagents + review-gate
harness agent-packs render --pack backend-laravel --pack role-tech-lead --target . --auto \
        --answer TEST_DB=<name> --answer CHECK_CMD='<static check>'  # stack+role, override interview
harness agent-packs doctor  --target .            # check; lock — .claude/agent-pack.lock.json
harness agent-packs upgrade --pack <p> --target . # careful upgrade (conflict → *.pack-new)
```

> **Automatic path:** a full `maind onboard` / `swissknifeman setup` with a **project type**
> (`laravel-project`/`node-frontend`/`python-backend`/`dart-flutter`) installs the stack pack
> ITSELF from the profile (`packages/skiller/profiles/<type>.json: agent_pack`; roles —
> `config.role_packs` by `project.roles`). A manual `harness agent-packs render` is needed when a
> project was set up OUTSIDE a full onboarding (e.g. plain `connect`) or its `projects.json`
> record lacks a `type` — then the agent-packs step is easy to miss (a typical cause of "the
> project has no roles/code-review").

> **A stack pack ≠ an exact infra match.** Rendered agents carry origin-pack assumptions (PHP
> binary, DB type, protected `.env`, Pest/PHPUnit). After install, **check and adjust** the
> rendered `.claude/agents/*` + `workflow` + `rules/tests.md` to the project's real infra
> (runner, MySQL/Postgres, test DB, test framework). A pack's `requires.skills` must be covered
> by the connected set (connect/vendor). Subsystem details (pack structure, templating,
> lock/upgrade) — [harness-operations].

## Doc-sync: project docs ↔ Brain vault

Two-way sync of `docs/` and `docs-public/` between the Brain vault and the code repo — CLI
`~/Vaults/Brain/bin/brain` (git 3-way merge, merge-base in `~/.brain/sync/`). Details —
[[brain-doc-sync]]. Briefly:

```bash
~/Vaults/Brain/bin/brain status <proj>             # pair-of-folders state
~/Vaults/Brain/bin/brain sync all <proj> --dry-run # merge preview
~/Vaults/Brain/bin/brain sync all <proj>           # merge (first time = seed from the vault)
```

Precondition: the vault control note (`<Name>.md`) must carry frontmatter `repo:
~/projects/<path>` — otherwise `brain` doesn't see the project.

### Doc folders: name ↔ visibility are decoupled (read from config, not from the name)

A doc folder is modeled as `{id, vault, repo, visibility}`: vault/repo side names can differ, and
**status** (`public`|`private`) is independent of the name. Source of truth — the Brain control
note's frontmatter; maind caches it in `docs_folders`. Default `visibility` **by project type**:
**package/library** → `docs` public (public VitePress docs); **product** (closed
service/frontend) → `docs` private (internal). A public folder carries no `[[wikilinks]]`
(gated).

Set/override — flat frontmatter keys (naive parser, variant A):
```yaml
docs_folders: docs-public        # CSV of vault names (default docs+docs-public)
docs_public:  docs-public        # CSV of vault names that are public (optional)
docs_repo_map: docs-public=docs  # CSV of vault=repo pairs: vault docs-public publishes as repo docs
```
The old flat `["docs","docs-public"]` form is migrated on the fly. Details — Brain
`docs/workflow/docs-watcher.md` (folder model) + `brain-cli.md` (visibility wikilink gate).

> **The agent-pack's internal AI guide** (`subagents-and-workflows.md`) goes into
> **`.claude/guidelines/`**, NOT `docs/`: it's an artifact for agents, not public documentation
> (else it would leak into publication and the Brain vault). harness stack packs
> (backend-laravel etc.) write it there by default (`DOCS_DIR`). `.claude/guidelines/` is
> committed (not gitignored); `docs/` remains for real documentation.

## Machine-specific config hygiene (gitignore + synced `.example`)

> **Fleet map.** Which generated service files belong in `.gitignore` and which are committed is
> one table: `configs/gitignore-policy.json` (policies `ignore` / `commit` / `portable-or-ignore` /
> `project`, owner and reason per file). Check a project with
> `maind doctor --gitignore-drift --project <id>` (read-only; `--block` prints the lines to add).
> Only the repository's own `.gitignore` counts — a user-global excludes file does not protect teammates.

A config that "bakes in" an **absolute local path** (`/home/<user>/…/bin/maind`, a Serena
project path), a **secret** (proxy credentials, a token), or a **personal host:port**, must not
be committed as-is: another developer/CI has a different path, a secret leaks into git history.
Applies to **every** provider's MCP config (`.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`)
and machine-specific content under `.claude/` (`settings.local.json` etc.). Two strategies, in
preference order:

**1) Indirection (preferred) — the config stays portable and gets committed.** Move the
machine-specific value into the environment and reference it from the config: `${VAR:-default}`
(Claude Code expands from the **process environment**; it does NOT read a project `.env` itself —
needs a shell `export` or a wrapper, and a **default is mandatory**, otherwise an unset `${VAR}`
fails to parse the whole config) or a thin wrapper reading `.env` at startup. Then the config
holds no paths or secrets → it can be committed, no `.example` needed. Ecosystem canon —
`${MAIND_BIN:-maind}` for the `maind` server (`deploy.py`).
> Example (playwright proxy): the secret lives only in `.env`
> (`PLAYWRIGHT_MCP_PROXY_SERVER=…`), and the server in `.mcp.json` loads it via a wrapper
> `bash -c 'export …=$(grep … .env); exec npx @playwright/mcp'`. Document the variable in
> `.env.example` (empty placeholder).

**2) gitignore + `.example` (fallback) — when the value must live directly in the file**
(indirection impossible):
- the real file → into `.gitignore` (already tracked — `git rm --cached <file>`);
- a `<file>.example` with **placeholders** is committed alongside:
  `<ABS_PATH_TO_SWISSKNIFEMAN>/packages/maind/bin/maind`, `<REPO_ROOT>`, `<TOKEN>`;
- **sync is mandatory and simultaneous**: edit the real file (added an MCP server, changed
  args/path) — edit `.example` in the **same** change. Same discipline as `.env` ↔
  `.env.example`, not "eventually".

**What's machine-specific** (→ indirection or `.example`): absolute paths `/home/<user>/…`,
`/Users/…`; secrets/tokens/credentials; personal host:port. **What's portable** (commit as-is):
relative commands (`php artisan boost:mcp`), values identical for everyone.

> Before committing: `git diff --cached` on `*.json`/`.mcp.json`/`.claude/*` for absolute paths
> (`/home/`, `/Users/`) and secrets. Found one — move it to `.env` (strategy 1) or gitignore + update
> `.example` (strategy 2).

> **Mechanism vs discipline.** The `maind` binary path is now **indirected**
> (`deploy.py::_maind_entry` writes `${MAIND_BIN:-maind}`, not an absolute path — strategy 1).
> Still machine-specific: the **Serena path** `--project <abs>` in the same `.mcp.json` — maind
> doesn't yet emit an `.example`/gitignore it for that one — this remains **agent discipline**.
> Caught it again — a candidate to fix in maind (indirect the Serena path / emit `.example` +
> append `.gitignore`; `roadmap/mcp-config-example-emit.md`), route it through
> [field-feedback-loop].

## Order: "give the project everything" (full)

Setting up a project = **four layers**: skills (knowledge) **+ agent-packs (roles/agents)** +
harness environment (permissions/mcp/hooks) + maind (memory/graph). The order must touch all
four:

1. Hub onboarding — [ecosystem-integration] (`maind onboard …`, namespace, health=connected).
   Rolls out the **MCP + memory/graph** layers (daemon, `.mcp.json` servers, graph/code graph).
2. Role skills — reuse the authorized channel (connect/vendor), then:
   - connect: `connect --plugins …` (architect+php[+frontend]); or
   - vendor: `.swissknifeman/config.json` (include/buckets) → `skiller sync`.
3. **Agents/roles** — `harness agent-packs render --pack <stack> [--pack <role>] --target .
   --auto` (detect stack → subagents + workflow + review-gate). **Check the rendered agents
   against the project's infra.** Without this step there is no role-based "slice→test→review" —
   see "Agents/roles" above.
4. **MCP / memory / graph** — rolled out by onboarding; point re-roll:
   `maind sync --only mcp,memory,graph,code-graph --project <id>`. (Laravel) Boost — as **MCP**
   (`composer require laravel/boost --dev`, `boost.json: mcp:true, skills:[]`); Boost skills are
   NOT installed.
5. Record the map — vendor: already in `skills-lock.json` from `sync`; connect/mixed: `skiller
   lock`.
6. Doc-sync — `repo:` in the control note + `brain sync all <proj>`.
7. Prompt-free auto-approve — bypass, see [[auto-approve-bypass]].
8. **Config commit hygiene** — `.mcp.json`/`.claude/*` with absolute paths or secrets:
   indirection via `.env`, or gitignore + a synced `.example` (see "Machine-specific config
   hygiene").
9. **Verification — one command:** `swissknifeman status <id>` (unified 4-layer inventory +
   drift→fix); `--all --json` for an agent. Plus `brain status <proj>` (doc-sync).

## Control surface: status → point re-sync

All 4 project layers' state in one command, and point repair of each. Canon —
[Project control surface](../../../../../docs/control-surface.md) (umbrella doc).

```bash
swissknifeman status <id>            # 4 layers: status·mcp[a/m/c]·skills·packs·trust + drift→fix
swissknifeman status --all --json    # whole fleet machine-readable (an agent reads .projects[].fixes)
maind sync --project <id> --only <cap>   # point re-sync: mcp|memory|graph|code-graph|agent-pack|…
```

Loop: `status --json` → read `fixes[]` (each = `{layer, issue, fix}`) → run the exact command
(usually `maind sync --only <cap>`), **not** "reconfigure everything". Machine-readable per
layer: `skiller status --json` (skills) · `harness agent-packs doctor --target . --json` (roles)
· `maind verify --json` (memory/graph proof).

`fixes[]` (drift_hints, probe.py) doesn't yet cover version drift of managed skills themselves
(the skiller registry or the `ecosystem-mcp` template updated but the project never got it) —
that's a separate fleet-wide gate: [ecosystem-integration] §Drift-gate (`skiller doctor
--vendor-drift` + `maind doctor --skill-drift`).

## Links

- [Project control surface](../../../../../docs/control-surface.md) — unified 4-layer status +
  point re-sync.
- [ecosystem-integration] — connecting a project to the mAInd hub (memory/graph/MCP).
- [harness-operations] — the agent-packs subsystem (roles/agents), permissions/mcp/hooks presets.
- [maind-overview] — how the hub and namespaces work.
- memory: [[brain-doc-sync]] · [[auto-approve-bypass]].

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
canonical source is this `SKILL.md`; thin projections —
`.claude/skills/project-tooling-runbook/SKILL.md` and
`.agents/skills/project-tooling-runbook/SKILL.md` (generated by `skiller registry`, never
hand-edited). Bucket `repository-bootstrap` is private/source-only: never published as an
ordinary unit/core/marketplace entry, never vendored/connected into a consumer project.
