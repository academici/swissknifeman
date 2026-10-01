# Hub like AI Skills Index + fix «skills are not visible»

> Status: ✅ implemented (`scripts/generate-hub.sh`) — all three Phase 1 supplements (agent-routing
> slice, name matching `skills:`, freshness-stamp) on the tree.

## What is hub

`skiller` generates **hub** — project skill index (buckets + descriptions + rules
source priority). This is it «AI Skills Index» from audits - **already exists**,
no need to build from scratch.

- Boost-project → hub is written in `.ai/guidelines/swissknifeman-hub.md` (markers
  `<!-- swissknifeman:hub:start/end -->`); in CLAUDE.md/AGENTS.md transfers
  `php artisan boost:update`. **Generated CLAUDE.md/AGENTS.md do not touch with hands.**
- Non-Boost → managed block in `CLAUDE.md`.

## Regression «skills are not visible»

Sources of invisibility:
1. Native field `skills:` from an agent on unknown/disabled name **is skipped with
   entry in debug-log** (first-party `https://code.claude.com/docs/en/sub-agents`,
   verified 2026-07-29) — no visible error → agent thinks that the skill is loaded, but it is not.
2. Hub is deprecated (registry has changed, hub not regenerated) → new skills are not in the index.
3. Agents are not indexed at all in hub → the role and its skills are not visible to the orchestrator.

## Fix (implemented) — three additives in `generate-hub.sh`

1. **agent-routing slice** — table from `.claude/agents/*.md` (`name`/`description`/`skills:`):
   «role → when to call → preloaded skills». Source of truth - agent files; hub indexes.
2. **Name matching `skills:`** — each name from `skills:` agents are checked against `skills.json`;
   unknown → `⚠ unknown skill` in hub + find in `skiller doctor`. Kills silent no-op.
3. **freshness-stamp** — in the header hub hash/registry counter + date; `skiller doctor` flagit
   drift «registry has changed, hub not regenerated».

List-aware pars `skills:` (inline `[..]` or block list) implemented locally in
`generate-hub.sh:parse_agent_frontmatter` — `lib/skiller/common.py:parse_frontmatter`
still only reads the scalars of the first block, but hub does not use it for this purpose.

## Connection with skills and rules

Three levels, no duplication:
- **hub** — index (what is there, when to ship).
- **path-scoped rule** (`.claude/rules/`) — thin trigger on paths «load skill here X».
- **skill** — depth. Rule REFERENCES to a skill, does not rewrite its text.
