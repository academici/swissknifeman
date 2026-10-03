# Roadmap

Directions only; order within a block is rough priority. Work starts on measured need, not in anticipation of it.

## Near term

- **Session efficiency.** Accumulated tool results, not the resident skill set, dominate Codex session growth; duplicate skill names exist in the umbrella and in Vaulter. Next: safe pilots that trim tool-result carry-over and remove the duplicates.
- **Task: structural headings are English, localized names never block.** Task 0.26.2 rejected a plan whose names were Russian: Routing `Почему` (≠ `Why`), Meta `Поле | Значение`, `Title` prefix `План №1`, decision bodies `## Решение/Почему/Последствия` (≠ `## Solution/Why`), Phase Handoff tables. Task 0.24.3 had accepted them, so P10 ran and P05 then stopped before any write (`BATCH_AMBIGUOUS` → routing → `PLAN_DESIGN_GATE_BLOCKED`). Worse, the one-cell fix changes the design fingerprint, so a plan with `Design Audit: required` also needs a repeated whole-plan audit. Rule: templates, scaffolds and `plan-design` always emit English headings (content stays in the plan language). Next: parse headings through an alias map (`Почему`→`Why`, …) or warn-and-normalize in `plan-lint`/`task_contract`/`plan_decisions`, keep localized headings out of the design fingerprint (or normalize before hashing), and never make an alias mismatch a stop reason. A `plan-lint --fix-headings` migration should cover existing plans. Also: `plan-work.py` needs an absolute `--plan-dir` (a relative `.` gives an empty plan name), and the cached `task/<ver>` copy lacks sibling `core/` (`ModuleNotFoundError: core.provider`).
- **Provider parity.** Plugin/skill reconcile plus Cursor/Grok field residue after the provider-aware `budget`/`doctor` work. Grok is a managed provider (Codex-shaped hooks/MCP TOML, Cursor-shaped skill discovery); fleet health still requires only Claude/Codex/Cursor.
- **Own skills migration.** Analyze local projects listed in `.skills-scanner.json`, move the universal part into the registry (via the [scanner](/skiller/guide/scanner) or by hand), connect it back with `skiller connect` / `skiller vendor`, delete local copies.
- **Vendor skills in packages.** Apply the [publication mechanism](/skiller/guide/vendor-skills) in own open-source packages: `resources/skills/` + ServiceProvider publication + a full-cycle test (`composer install → vendor:publish → agent sees the skill`).
- **`configs/` content.** Preconfigured subagents (`.claude/agents/`), hooks (auto-format, pre-commit validation), other IDE configs — see the [configs overview](/harness/configs/). Verified `.mcp.json` presets already ship (`context7` + a curated subset), see [Integrations](/harness/integrations/).

## Strategic

- **Cross-project optimizer** — the read-only overview ships as `system/cross-project-coordinator` plus the `code-coordinator` agent. Next: turn findings into action (auto-extraction to a shared package, PRs to target projects) and write cross-project facts to shared memory.
- **Skills Marketplace UI** — web UI over the registry: tag search, snippet preview, "Install to project". Minimum: VitePress + GitHub API.
- **Skill Composition** — `extends: laravel` in frontmatter: the agent loads the parent context first.
- **Versioned Snapshots** — SemVer tags on the repository and a version pin in `skiller vendor` (`swissknifeman@1.2.0`); sha256 in the registry already exists.
- **Skill Chains** — the `requires` / `produces_for` graph already exists in frontmatter; visualize it as a DAG and run a chain in one call.

## Technical

- **Snippet auto-scoring** — GitHub Action runs phpcs/phpstan/hadolint on new snippets and writes a score to `index.json`; candidates below threshold are blocked.
- **Obsidian plugin** — `skills.json` in the sidebar, open SKILL.md, insert a snippet with `/skill`.
- **MCP server for skills** — `get_skill(name)`, `list_skills(bucket)`, `search_snippets(query)` instead of file reads.
- **Quality badges** — generated per-skill badges: `snippets: 5`, `used_in: 3 projects`, `last_tested: <date>`.

## Experimental

- **LLM gap analysis** — a monthly agent reads PRs/issues of working projects, finds patterns no skill covers, drafts new SKILL.md files.
- **Snippet leaderboard** — track which snippets are copied into projects and how stable they stay.
- **Skill health monitor** — scheduled Action checks that snippets compile/lint on current PHP, Node and Docker versions.
