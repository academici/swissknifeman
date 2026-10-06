# Project archetypes: recipes and non-obvious forks

Map of typical ecosystem projects: what is detected, what set is distributed (`profiles/<type>.json`)
and which **non-obvious questions** are resolved during onboarding. The goal is that the agent, having received the project, does not
wondered «what to connect». Full configuration tree - [onboarding-decision-tree](/maind/guide/onboarding-decision-tree);
skill channel selection (connect/vendor) — always **ask the user** (see project-tooling-runbook).

> Source of Recipe Truth - `profiles/*.json` (detect — `core/project.py`).
> The table below should match them; If there is a discrepancy, edit the profile, not the table.

## Through non-obvious forks (for any archetype)

| Fork | Default | When to change |
|:--|:--|:--|
| **Skill channel** | ask | `connect` (plugins, not in repo, need registry access) vs `vendor`/`sync` (physical copies in the repo - for external developers). NOT default - user choice |
| **CORE-distribution** | on (`--no-core` disables) | connect → curated plugin `core` (EXACTLY `CORE_SKILLS`, easy replacement for buckets general+oss-dev; current resident - `skiller budget --check-core`, don't hardcode snapshot); vendor → the same `CORE_SKILLS` (`context-economy`/`anti-drift`/`compact-responses`/`session-handoff`/`mcp-advisor`/`verify-claims`/`query-craft`/`gh-review`) file by file |
| **Memory** | `maind` | `maind` (hub, general) / `native` (agentmemory locally) / `off`. See ecosystem-integration |
| **namespace** | empty → `default` | set groups (`["axioma", …]`) for cross-project communications; `["*"]` — general infrastructure |
| **Code graph (Serena)** | by type (language available) | `--with-code` raises per-project `serena` via `uvx`; not for vault/standalone |
| **Unrecognized** | MINIMUM set (general+oss-dev), NOT «all» | specify the profile explicitly or `--profile standalone` («put everything») |

## Recipes by Type

| Type | Detect (`core/project.py`) | Buckets | MCP | harness-presets | agent-pack |
|:--|:--|:--|:--|:--|:--|
| **laravel-project** | `composer.json` + `artisan` | system, architect, php, laravel-{testing,auth,data-layer}, devops, quality, operator | context7 | base, laravel | backend-laravel |
| **php-package** | `composer.json` (without artisan) | system, oss-dev, php, php-packages, laravel-testing, quality, devops | — | — | — |
| **node-frontend** | `package.json` + UI-framework/collector | system, architect, frontend, frontend-{vue,vite,linting,tailwind}, quality, devops | context7, playwright | base, node | node-frontend |
| **node-package** | `package.json` (without UI) | system, oss-dev, quality, devops | context7 | base, node | — |
| **python-backend** | `pyproject.toml`/`requirements.txt`/`setup.py` | system, architect, python, devops, quality, operator | context7 | base, python | python-backend |
| **blender** | `*.blend` / `blender_manifest.toml` / `import bpy` | blender, blender-modeling, python, quality | context7 | base, python | — |
| **dart-flutter** | `pubspec.yaml` | system, architect, mobile, quality | context7 | base | dart-flutter |
| **obsidian-vault** | `.obsidian/` | system, architect, pm, founder, operator, roles, finance, legal, marketing, sales, research, creative | — | — | — |
| **standalone** | default (nothing matched clearly) | `*` (all - only by explicit `--profile standalone`) | — | — | — |

## Non-obvious questions about specific archetypes

- **node-frontend → what front stack?** Profile distributes **Vue-SPA** set (`frontend-vue`/`vite`).
  For **Nuxt** add `frontend-nuxt` (there is a bucket, but it’s not included in the profile - otherwise it would be reaching out to everyone
  Vue-projects); for React/Svelte there is no profile yet - set the buckets explicitly. `playwright` MCP enabled
  (e2e), `figma` MCP — connected manually (not in the catalog `harness mcp`).
- **blender → addon or modeling?** `blender` (general) + `blender-modeling` (parametrics). Code graph
  Serena — `python`. Wednesday Blender non-standard (built-in python); preset `python` — starting
  period, check the interpreter.
- **obsidian-vault → not dev-project.** Roles are distributed/domain buckets (pm/founder/research/…), NOT
  dev-stack; code-graph/Serena and dev-presets are NOT needed; memory is useful (knowledge base).
- **php-package vs laravel-project.** Package (without `artisan`) — `oss-dev`+`php-packages` (development
  package, releases), without laravel-app-buckets. Application - complete laravel-stack.
- **standalone (unrecognized).** NOT «dump of everything»: auto-fallback puts the core (general+oss-dev). «All» —
  only consciously through `--profile standalone`.

## Scenario cases (text tests)

The behavior of skills for typical tasks is checked **eval-harnes** (`skiller eval <bucket>/<name>`):
`evals/evals.json` (typical tasks + deterministic assertions), `pressure.json` (temptations
skip skill), `triggers.json` (response accuracy `description`). This «mental run»
typical tasks in addition to structural validation - backwater `evals/` priority skills of the archetype
(`skiller eval <skill> --scaffold`). Canon - [evals.md](./evals.md).
