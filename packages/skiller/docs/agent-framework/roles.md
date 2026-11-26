# Universal role agents

> Status: ✅ implemented (`configs/claude-code/agent-packs/role-bindings.json`,
> `binding_version 1.0.0`). Here is the model; seed-agents are rendered from `_common` and
> stack packs (`backend-laravel`, `node-frontend`, `python-backend`, `dart-flutter`,
> `laravel-package`) via role binding.

Key idea of versatility: **roles are the same for any project, only the
stack - via profile.** Reviewer on Laravel and on Nuxt — one role; the set varies
preloaded skills and path-scoped rules selected by the profile.

## Role set

| Role | Responsibility | tools |
|---|---|---|
| `implementer` (slice-builder) | implements one slice according to the canon, commits, does not write tests | Read/Grep/Glob/Edit/Write/Bash |
| `test-writer` | tests on the finished code, until green; the code doesn't change | Read/Grep/Glob/Edit/Write/Bash |
| `reviewer` | read-only review + over-engineering-pass (ponytail) | Read/Grep/Glob/Bash |
| `explore` | read-only research, collects context | read-only |
| `plan` | architectural plan | read-only |
| `spec-writer` (opt.) | `tech-spec.md` for major features (not global. gate) | Read/Grep/Glob/Write |

## How a role becomes stack-specific

- `skills:` preload from profile (`skills_map`) + self-load fallback in promt - on
  unknown/disabled name preload is skipped with entry to debug-log, not quiet
  no-op without a trace (first-party `https://code.claude.com/docs/en/sub-agents`, verified
  2026-07-29). **Disclaimer (teammate):** this preload does not apply when role is running
  like teammate agent-commands - there skills/mcpServers are taken from the design/user settings
  session, not from the agent definition (first-party `https://code.claude.com/docs/en/agent-teams`,
  verified 2026-07-29). Along this path self-load fallback in industrial media is the ONLY carrier,
  not a safety net (see [agent-teams](./agent-teams)).
- Stack gates (php8.4 vs node, PHPUnit vs Pest, access-layer on/off) — from answers
  interview pack, not hardcode in the role.
- path-scoped rules by stack paths (`app/**` vs `resources/js/**`).

## Inheritance - on build-time pack, NOT runtime

Claude Code **does not support** `extends:`/`@include` for agents (verified, official.
docks). Therefore «common role database» is implemented like this: the pack stores generalized templates →
when installed renders them in `.claude/agents/<prefix>-*.md` under the project profile.
No runtime inclusion that would not silently work.

## Anti-patterns (from audits, rejected)

- File numbering `01_`,`02_` for priority - on `/agents` has no effect.
- Frontmatter `triggers/role/version/project_type` — are not native, do not use.
- file-lock (`touch {file}.lock`) against parallel edits - replaced one-branch/worktree
  and module-boundaries.
