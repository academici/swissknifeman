---
name: context-economy
bucket: general
version: 1.1.0
description: "Claude Code context economy in a project: CLAUDE.md ≤200 lines, path-scoped .claude/rules/, /compact vs /clear, Plan→Clear→Execute, MCP audit, model routing. Officially-supported mechanisms only — no myths like .claudeignore."
risk: draft
persona: oss-dev
tags: [tokens, context, claude-code, workflow, conventions]
requires: []
produces_for: [gh-review]
outputs: [".claude/rules/*.md", ".claude/commands/*.md", "CLAUDE.md (trim)"]
snippets:
  - rules-example.md
  - command-prime.md
  - command-plan.md
  - command-execute.md
  - claude-md-checklist.md
adapters: [claude, cursor, fable]
sha256: ""
---

# Context Economy — token-spend discipline

Reference: https://code.claude.com/docs/en/memory. Do NOT exist / do NOT work: `.claudeignore` (not a thing in Claude Code); `@import` in CLAUDE.md = organization not economy (imports load fully at start).

## 1. CLAUDE.md — ≤200 lines (Anthropic official target)

- Keep: non-standard build/test commands, architecture decisions against framework defaults, prohibitions, paths to skills/rules.
- Remove: what the model knows from training (standard Laravel/TS), aspirational rules ("write clean code"), contacts, schedules.
- Per-line test: "would this rule surprise an experienced dev new to the repo?" No → remove.
- Human notes → HTML comments `<!-- ... -->`: stripped before context injection (preserved inside code blocks).
- Audit checklist: snippets/claude-md-checklist.md.

## 2. Path-scoped rules — `.claude/rules/*.md`

Rules with `paths:` frontmatter load only when Claude reads matching files; without `paths:` → every session like CLAUDE.md:

```markdown
---
paths:
  - "app/Filament/**"
---
# Filament rules — load only when working with Filament files
```

Template: snippets/rules-example.md. Not skills: SKILL.md already loads lazily (only name+description live in session context); `paths:` for skills is unneeded and does not exist.

## 3. Sessions: /compact, /clear, Plan→Clear→Execute

- `/compact` — after finishing a feature (summarizes history, keeps decisions).
- `/clear` — on topic switch (full reset).
- Large tasks → separate sessions: plan to file (`/plan` → `.claude/plans/<task>.md`) → `/clear` → execute loading only the plan (`/execute`). Intermediate planning attempts don't carry into execution context. Command templates: snippets/command-{prime,plan,execute}.md → copy into project `.claude/commands/`.

## 4. Tool output

PHP projects → skill `pao` (bucket: php): tests/static-analysis compressed to ~20 tokens JSON.

## 5. MCP & model audit

- MCP server unused 7 days → disable (its schema loads in every request). CLI instead of MCP where possible.
- Selection (what to connect, not what to trim) at onboarding/sync — skill `mcp-advisor` (the reverse axis of this audit).
- Model — natively via `/model`: routine/recon → Haiku, architecture/debug → senior model. Don't use third-party proxy routers (claude-code-router): extra risk layer without native guarantees.

## 6. Platform layer — via `gh`, not files

GitHub ops (PRs, review threads, others' code, releases) → **GitHub CLI**, not whole-file reads, not web UI. NOT a `git` replacement: local VCS (commit, branch, working-tree diff, log, rebase) stays with `git`, `gh` can't do it. Split: local → `git`; platform → `gh`. `gh` returns minimal slice: `gh pr diff <N>` — diff only; `gh pr view <N> --comments` — threads only; `gh api .../contents/{path}` — one file (not a repo clone). Full algorithm/commands → skill `oss-dev/gh-review`.

## 7. Hard noise block — permissions.deny

`permissions.deny: Read(...)` in `.claude/settings.json` — hardware read block (`storage/logs/**`, `node_modules/**`, `*.lock`). Presets: `configs/claude-code/` + `scripts/apply-permissions.sh`. In Laravel+Boost projects do NOT block `vendor/**` — guidelines live in `vendor/laravel/boost/.ai/`.

## Quality checklist

- [ ] CLAUDE.md ≤200 lines, each line passes "would it surprise an experienced dev"
- [ ] Topic/local rules moved to `.claude/rules/` with `paths:`
- [ ] deny noise preset applied; `vendor/**` not blocked in Boost projects
- [ ] prime/plan/execute commands copied into `.claude/commands/`
- [ ] MCP servers checked within last 30 days
- [ ] Platform ops (PR/review/others' code) go via `gh`, not whole-file loading

## References

- snippets/rules-example.md, snippets/claude-md-checklist.md
- snippets/command-prime.md, snippets/command-plan.md, snippets/command-execute.md
- https://code.claude.com/docs/en/memory — CLAUDE.md, rules, auto memory
- Skill `pao` (php) — compress PHP tool output
- Skill `oss-dev/gh-review` — gh-driven review/handoff (section 6, full algorithm)
- Skill `compact-responses` (general) — terse model output (different economy axis: the answer, not the context)
- Skill `task-brief-template` (general) — Plan→Clear→Execute pattern and `/plan`, `/execute` command templates
- Skill `session-handoff` (general) — compress session into a handoff before `/clear`
- Skill `mcp-advisor` (general) — pick MCP for a project at onboarding (the reverse side of the audit: what to connect)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 699a674f99a471a04cb378e7f6c1581150fa056a2d7dc78dd794d8f347fa1ae6 -->
