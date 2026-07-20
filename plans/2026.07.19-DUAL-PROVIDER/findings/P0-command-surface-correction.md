# P0 command-surface correction

## Anchor

- Tree: `d8ac22c04fc4d4219dc95244ee9d181e92553a74` (`git rev-parse HEAD`).
- Worktree (`git status --short`):

```text
 M .mcp.json.example
 M docs/reference.md
 M packages/skiller/skills/general/plan-protocol/SKILL.md
 M packages/skiller/skills/general/plan-protocol/SKILL.ru.md
 M packages/skiller/skills/general/plan-protocol/snippets/journal-template.md
 M packages/task/.claude-plugin/plugin.json
 M packages/task/commands/plan-design.md
 M packages/task/lib/task/journal.py
 M packages/task/lib/task/plan_lint.py
 M packages/task/tests/test_journal.py
 M packages/task/tests/test_plan_lint.py
 M plans/2026.07.18-FOREMAN/handoff.md
 M plans/2026.07.18-FOREMAN/plan.md
 M plans/2026.07.19-DUAL-PROVIDER/brief/01-refinements.md
 M plans/2026.07.19-DUAL-PROVIDER/handoff.md
 M plans/2026.07.19-DUAL-PROVIDER/index.md
 M plans/2026.07.19-DUAL-PROVIDER/journal.jsonl
 M plans/2026.07.19-DUAL-PROVIDER/phases/P0.md
 M plans/2026.07.19-DUAL-PROVIDER/plan.md
 M plans/2026.07.19-DUAL-PROVIDER/roadmap.md
?? .agents/
?? .serena/
?? AGENTS.md
?? plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py
?? plans/2026.07.19-DUAL-PROVIDER/findings/P0-command-surface-correction.md
?? plans/2026.07.19-DUAL-PROVIDER/research/04-provider-domain-scenarios.md
?? plans/2026.07.19-DUAL-PROVIDER/research/15-command-surface-prerequisite-remediation.md
?? plans/2026.07.19-DUAL-PROVIDER/root/CONTEXT.md
```

This is an anchored observation of the current tree, not a frozen contract invariant.

## Corrected metric

**Command Surface** is the union of direct Markdown command definitions in the five explicit
first-party package roots below. At this anchor it is **32** files:
**11 + 5 + 6 + 8 + 2 = 32** (task + skiller + harness + maind + analyst).

**Task Command** is the narrower semantic workflow subset
`packages/task/commands/*.md`, which contains **11** files at this anchor.
Package commands in the other four roots remain owned by their respective bounded contexts.

## Root sets

| Package surface | Explicit non-recursive root | Count |
|:--|:--|--:|
| task | `packages/task/commands/*.md` | 11 |
| skiller | `packages/skiller/skm/commands/*.md` | 5 |
| harness | `packages/harness/commands/*.md` | 6 |
| maind | `packages/maind/commands/*.md` | 8 |
| analyst | `packages/analyst/commands/*.md` | 2 |
| **Total Command Surface** | union of the five roots | **32** |

Only direct `*.md` files are collected: no recursive glob is used. In particular,
`packages/harness/configs/**/commands/*.md` is agent-pack content and is outside this
top-level package command surface.

## Raw sorted paths

### task — `packages/task/commands/*.md` (11)

```text
packages/task/commands/design.md
packages/task/commands/dev.md
packages/task/commands/fix.md
packages/task/commands/make-workflow.md
packages/task/commands/plan-audit.md
packages/task/commands/plan-close.md
packages/task/commands/plan-design.md
packages/task/commands/plan-exec.md
packages/task/commands/plan-run.md
packages/task/commands/research.md
packages/task/commands/review.md
```

### skiller — `packages/skiller/skm/commands/*.md` (5)

```text
packages/skiller/skm/commands/doctor.md
packages/skiller/skm/commands/integrate.md
packages/skiller/skm/commands/skills.md
packages/skiller/skm/commands/skm.md
packages/skiller/skm/commands/status.md
```

### harness — `packages/harness/commands/*.md` (6)

```text
packages/harness/commands/doctor.md
packages/harness/commands/harness.md
packages/harness/commands/hooks.md
packages/harness/commands/mcp.md
packages/harness/commands/permissions.md
packages/harness/commands/safe-dirs.md
```

### maind — `packages/maind/commands/*.md` (8)

```text
packages/maind/commands/analyze.md
packages/maind/commands/doctor.md
packages/maind/commands/health.md
packages/maind/commands/maind.md
packages/maind/commands/onboard.md
packages/maind/commands/plugins.md
packages/maind/commands/status.md
packages/maind/commands/sync.md
```

### analyst — `packages/analyst/commands/*.md` (2)

```text
packages/analyst/commands/analyst.md
packages/analyst/commands/deep.md
```

## Supersession

This P0.5 finding supersedes **only the command-surface interpretation** of the historical
P0.1 finding: its `32 task commands` label is corrected to an umbrella Command Surface
of 32 and a Task Command subset of 11. P0.1 helper, finding, status, Completion
Notes, and journal remain historical evidence and are not rewritten.

The truth chain is: P0.1 historical Task Command subset → P0.5 umbrella Command Surface
correction → P0.2 owner vocabulary freeze. P0.5 does not approve vocabulary or P0.2.

## Reproduction

```bash
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py --write
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py --check
```

The scanner is stdlib-only and reads the repository except when `--write` updates this
P0.5 finding. `--check` compares the generated evidence byte-for-byte and returns nonzero
when the anchored tree, worktree, root set, or content has drifted.
