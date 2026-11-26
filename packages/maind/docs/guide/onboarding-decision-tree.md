# Decision Tree: Project Setup

Complete checklist of scenarios for onboarding and operating a project in the ecosystem **academici**.
This **single source of truth** by configuration branches - each layer in the format
**question → options → action/condition**. Purpose: pick up **optimal** set for the project,
rather than include «everything in a row». If the choice is not obvious - **ask user**, don't guess.

> One input for the entire tree: `maind onboard <project|path>` (orchestrates skiller + harness +
> memory + graph). Point changes - `skiller …` / `harness …` / `maind sync …`.

## Layer 0 - Project Type (detect)

**Question:** what is the project stack? Automatically detected (`core/project.py`,
order from specific to general):

| Marker at root | Type | Profile (`profiles/<type>.json`) |
|:--|:--|:--|
| `.obsidian/` | `obsidian-vault` | quality |
| `composer.json` + `artisan` | `laravel-project` | system, architect, php, devops, quality, operator |
| `composer.json` | `php-package` | php, devops, … |
| `pubspec.yaml` | `dart-flutter` | … |
| `pyproject.toml`/`requirements.txt`/`setup.py` | `python-backend` | system, architect, python, devops, quality, operator |
| `package.json` + UI-framework (vue/nuxt/react/…) | `node-frontend` | system, architect, frontend, quality, devops |
| `package.json` | `node-package` | system, oss-dev, quality, devops |
| — no markers - | `standalone` | **`["*"]` = put everything** |

**⚠ Condition - type NOT recognized (`standalone`):** this **not** signal «put everything».
- Auto/non-interactive (`--yes`): is set **minimum set** (`general, oss-dev, system`) +
  loud warn with a prompt to specify a profile (`autodetect-fallback`, see `resolve_selection`).
- Interactive (`skiller integrate` wizard): ask for a profile from the list.
- Explicit «put everything» is possible only consciously: `--profile standalone`.

## Layer 1 - Memory Mechanism

**Question:** how to maintain memory/project context? `maind onboard --memory <…>` (default `manual`).

| Option | Action | When |
|:--|:--|:--|
| **manual** (rec.) | mAInd via MCP/CLI upon request; without SessionStart digest; `autoMemoryEnabled:false` | default for ecosystem nodes |
| **maind** | explicitly enable SessionStart digest mAInd | only with measured benefit of auto-context |
| **native** | return native auto-memory Claude Code; `MODE=off`, revert hook | project outside the ecosystem |
| **off** | memory disabled | temporarily/special case |

## Layer 2 - Namespaces (connection isolation)

**Question:** in which namespace is the project alive? `--namespace a,b` (default `["axioma", <id>]`).
Memory **general inside** namespace, **isolated between**.

- **General** (ecosystem/grocery) — links a group: e.g. `dterema` for back+front one product.
- **Separate personal** — is different for each subproject: for example. `dterema-cms` (back), `dterema-web` (front).
- **Wildcard `*`** — infrastructure visible to everyone (`global`): core packages (corex/azguard/…).

**Condition - several subprojects of one product:** give general grocery ns (connection) **and**
separate personal for each (insulation). New ns register in section `namespaces` hub.

## Layer 3 - Skill Channel (ALWAYS ask)

**Question:** how to deliver skills? The choice changes what goes into the repo.

| Channel | Command | Granularity | In the repo | When |
|:--|:--|:--|:--|:--|
| **connect** | `skiller connect` | entire bucket (`enabledPlugins`) | no | satisfied «whole bucket», no commit required, auto-update from the registry; ⚠️ needs registry access swissknifeman (marketplace = local path) |
| **vendor** | `skiller sync` (`.swissknifeman/config.json`) | individual skills (+`skills-lock.json`) | yes | set control, visibility and commit to repo, selection of positions; **the project is given to external developers without swissknifeman** (files in the repo) |

Selection tree: the project goes to third-party developers / need commit in git / point selection →
**vendor**; otherwise (your environment, ecosystem) → **connect**. Laravel Boost — **only MCP**.

The channel is requested on onboarding and is forwarded with a flag `--skills-channel connect|vendor`
(`maind onboard` / `swissknifeman setup` / `skiller integrate`). When `vendor` `integrate` for
Claude-of the project generates itself `.swissknifeman/config.json` from the profile and applies `sync` (physical. copies
in `.claude/skills/`). Channel selection concerns **only skills** — memory/graph/MCP do not depend on it.

## Layer 4 - Profile/buckets (optimal set)

**Question:** what role buckets? By default - from type profile (Layer 0). **Not** include `php`/
`python`/`mobile` on a clean front and vice versa. CORE (`general`, `oss-dev`) is always heard
(`--no-core` disables). Not obvious → ask (2-3 curated option).

## Layer 5 - Environment (harness)

| Solution | Options | Action |
|:--|:--|:--|
| **permissions-presets** | base, laravel, php, node, python, docker, … | autodetect by stack; merge in `settings.json` |
| **MCP-servers** | context7, playwright, fetch, github, … | dev-default `context7` (except obsidian) + profile + `--mcp` |
| **auto-approve** | strict / permissive / bypass / off | `[harness.hooks.auto_approve]` → `.swissknifeman/hooks.env` + PreToolUse-hook |
| **brain-memory** | file / federation / agentmemory / off | `.swissknife.json` + memory-hook |

### PHP-tools: PAO (invariant for php/laravel-projects)

**Question:** for `laravel-project`/`php-package` (PHP≥8.3) — is installed `laravel/pao`
(agent-optimized output PHP-tests/analysis, direct token saving - tests/PHPStan/Rector/
Artisan collapse into ~20-token JSON instead of thousands of lines)? Onboarding detection by file
facts (`composer.lock`/`vendor/laravel/pao` + `php -v`) and acts like this:

| Status | Action |
|:--|:--|
| not php-type / PHP < 8.3 | skip (not applicable / not supported) |
| conscious opt-out (`project.pao_opt_out`) | skip, without warn |
| missing, interactive session | ask whether to install `composer require laravel/pao --dev` |
| missing, `--yes`/non-interactive | **do not set silently** — loud warn with recommendation |
| is already installed | skip, `status:ok` |

Invariant: **php-project (≥8.3) ⇒ `laravel/pao` set OR frozen opt-out.**
Visibility of absence in diagnostics - doctor-gate; skill instruction
for agent - `php/pao` (`packages/skiller/skills/php/pao/SKILL.md`).

## Layer 6 - Deploy (MCP + code graph)

- **MCP-targets:** `.mcp.json` (claude) always; `.cursor/mcp.json` if available `.cursor/`; vscode by flag.
- **Code graph (Serena):** `--with-code` → MCP-code server + `.serena/project.yml` (language by type,
  ignores). No binary Serena → pass with warn.

## Layer 7 - Graph

- **derive column** from the sources of truth (composer/package/docs/skills-lock) → project store + index.
- Disabled `graph.enabled=false` / `--dry-run`.

## Layer 8 - Agent-packs

Subagents by profile (`profile.agent_pack` + `model_tiers`): laravel→`backend-laravel`,
python→`python-backend`, frontend→`node-frontend`. Profile without `agent_pack` → pass.

## Layer 9 - Brain doc-sync

`--with-brain` → two-way sync tip `docs/` with Brain-shaft (needed `repo:` in
frontmatter control-notes). Commands - `~/Vaults/Brain/bin/brain status|sync <proj>`.

**Doc-folders and their visibility** are read from the config and are not guessed by name. Folder model -
`{id, vault, repo, visibility}` (party name and status untied): source of truth - frontmatter
control-notes Brain, maind caches in `docs_folders`. Default `visibility` by project type
(`core.docs_visibility_for`): **package/library** (`php-package`/`node-package`/`dart-flutter`)
→ `docs` **public** (public VitePress-documentation); **product** (`laravel-project`/
`node-frontend`/`python-backend`/…) → `docs` **private** (internal). During onboarding
`_ensure_project` sets default by type; redefined in frontmatter (flat keys
`docs_folders`/`docs_public`/`docs_repo_map` — option A, parser naive). The public folder is not
carries `[[wikilinks]]` (gate brain). Part - Brain `docs/workflow/docs-watcher.md`.

> **Internal AI-agent pack guide** (`subagents-and-workflows.md`) lives in `.claude/guidelines/`,
> NOT in `docs/` — this is an agent artifact, not public documentation (otherwise it would have leaked into publication
> and in Brain-valt). agent-pack stack packs (backend-laravel etc.) write it there by default.

## Layer 10 - Operation (ongoing)

| Task | Command | Branches |
|:--|:--|:--|
| **reroll artifacts** | `maind sync [--only mcp,graph,…] [--project\|--namespace\|--all] [--mode install\|update\|auto]` | provisioner-order: mcp → code-graph → graph → memory-hook → health-hook → health-doc → ecosystem-skill → setup-skill → agent-pack |
| **change skill channel** | `skiller status` → connect/vendor (Layer 3) | connect↔vendor; lock does not lose other people's records |
| **migration** | `maind migrate …` | legacy `.maind.json`→`config.json`, adapter-normalization |
| **diagnostics** | `maind health` (round-trip), `skiller status`, `maind doctor` | health=connected — gate «really writes», and not «raised» |

## Principles

- **Optimal, not maximum.** Set for stack and role; «everything in a row» — only consciously.
- **Not obvious → ask.** AskUserQuestion with 2-3 curated options, no guessing.
- **Always ask for skill channel** (connect vs vendor) — it changes what is committed.
- Related docs: [Namespaces](./namespaces.md) · [Sync](./sync.md) · [Healthcheck](./health.md) ·
  [Code graph](./code-graph.md) · skiller `integration-checklist`.
