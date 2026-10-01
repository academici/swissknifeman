# Workflow: AI-assisted development

> Methodology for organizing development using AI-tools on each
> stage of the project life cycle.

## Skills vs. work flow

It is important to distinguish between two layers of the registry:

- **Skills** (`skills/`) — are utilitarian. One skill = one skill working
  **inside a specific IDE/agent** (Claude Code, Cursor). Skill does not describe
  joint behavior of different systems - only how to do a specific thing
  where it is running.
- **Workflow** (this section) — **intersystem layer**. Describes how
  tools transfer work to each other: study → design →
  implementation → review. It's a methodology, not an executable skill.

Skill «how to write package tests» lives in `skills/php-packages/laravel-package-testing`.
Methodology «Perplexity collects technical specifications → Claude designs → Cursor implements»
lives here.

## Toolchain

```
Perplexity (research + primary technical specification)
    ↓
Claude (detailed technical specification + architectural solutions)
    ↓
Cursor / VS Code + cheap model (implementation)
    ↓
Claude / Perplexity (code review)
    ↓
dev-review via gh (PR-review and handoff with context saving)
```

Key Idea - **separation of responsibilities between tools**:
research and analytics, detailed design, implementation and control
qualities are different tasks that require different models.

## Tool Summary Table

| Stage | Tool | Task | Model |
|------|-----------|--------|--------|
| Research | **Perplexity** | Analytics, references, primary technical specifications | Pro Search |
| Design | **Claude** | Detailed technical specifications, architecture, patterns | Fable 5 / Sonnet |
| Implementation | **Cursor / VS Code** | Writing code according to technical specifications | Haiku / GPT-4o mini |
| Spot help | **Claude** | Complex issues in the implementation process | Sonnet |
| Code review | **Claude + Perplexity** | Quality analysis, relevance | Fable 5 |
| dev-review / handoff | **gh CLI** | PR-review and transfer of work point by point (`gh pr diff/view/comment`), without downloading entire files | any |
| Python / 3D | **Claude + Vilis** | Scripts, algorithms, visuals | Fable 5 / Claude Code |

## Sections

| Page | Contents |
|----------|------------|
| [Perplexity](./perplexity) | Settings, templates, resource block |
| [Claude](./claude) | Prompts for detailed technical specifications, architecture, code review |
| [Claude Fable 5](./fable-5) | Promting specifics Fable 5 (XML, effort) |
| [Cursor / VS Code](./cursor) | Implementation work cycle according to technical specifications |
| [Python / 3D](./python-3d) | Tools for Python and 3D-tasks |

## Rules of thumb

### Transfer between stages

- TK from Perplexity transfer to Claude **in full**, without summarizing.
- Links from the block «Resources» — include in the promt for Claude.
- Detailed technical specifications for Cursor save to repository (`.cursorrules`,
  `AGENTS.md`, `docs/spec.md`).
- **Platform handoff - via `gh`, not a dump.** Transferring work to
  review/merge, refer to PR/issue (`gh pr view <N> --json url`), instead of pasting
  body diff. The next agent will pull up the required cut himself (`gh pr diff <N>`,
  `gh pr view <N> --comments`) — this saves context vs moving everything
  artifact between sessions. Local VCS remains for `git`. Rules - skill
  `oss-dev/gh-review`, token discipline - `general/context-economy`.

### Quality control

- After each stage - a short audit: does the result meet expectations.
- Code review is not the final step, but **regular practice** throughout
  development.
- Perplexity-relevance review - once per sprint for long-term projects.

---

*Source of methodology - personal vault `40-AI/Workflow`. Update by
as new tools become available.*
