# Post-Integration Checklist — post-implementation check

Skill `system/agent-packs` RUN this checklist after each install/upgrade pack;
`skiller doctor` — upon request. The goal is to guarantee the integrity and **absence
conflicts**. On any find install/upgrade is considered incomplete.

## Pack integrity

- [ ] `.claude/agent-pack.lock.json` yes, valid (JSON is parsed), `version` matches `pack.json`.
- [ ] All files from `lock.files[].target` exist; no orphans (in lock yes, not on disk).
- [ ] There are no path collisions between multiple installed packages.

## Settings and hooks (main thing about conflicts)

- [ ] `.claude/settings.json` is parsed as JSON.
- [ ] The hooks that were BEFORE installation are in place: `diff` vs `.claude/settings.json.bak`
      does not show deleted entries (added only).
- [ ] `review-gate.sh` executable (`test -x`), `bash -n` without errors.
- [ ] review-gate registered on `SubagentStop` exactly ONE time (no duplicates).
- [ ] (Agent Teams) `TeammateIdle`/`TaskCompleted` registered once; don't conflict
      with `PreToolUse`(auto-approve)/`SubagentStop`(review-gate) — events are different.

## Agents and skills (fix «skills are not visible»)

- [ ] Each agent `.claude/agents/*.md`: valid frontmatter (`name`, `description`).
- [ ] ALL names in `skills:` agents exist in `skills.json` — zero silent no-op
      (otherwise `⚠` in hub + find `skiller doctor`).
- [ ] No duplicates `name` among `.claude/agents/*` and agents of enabled plugins.
- [ ] `tools:`-scope meaningful (read-only roles without Edit/Write).

## Workflow and rules

- [ ] Everyone `.claude/workflows/*.js`: `node --check` no errors (on the rendered).
- [ ] Everyone `.claude/rules/*.md` (if available): valid `paths:` frontmatter; rule
      does not duplicate skill text (refers to it) — no «rules in three places».

## Hub and Boost

- [ ] Hub regenerated (`generate-hub.sh`): yes agent-routing slice; `⚠`-inconsistencies zero; freshness fresh.
- [ ] B Boost-project: block in `.ai/guidelines/swissknifeman-hub.md` updated; NOT touched
      generated CLAUDE.md/AGENTS.md; reminder `php artisan boost:update` issued.

## Project behavior

- [ ] Project tests are green (for retrofit/upgrade — behavior-preserving).

## Output Format

Compact report: `PASS` or a list of finds by section. When found -
specific repair step, install/upgrade does not close.
