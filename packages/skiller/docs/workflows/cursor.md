# Cursor / VS Code — implementation according to technical specifications

> Role in work flow: **implementation**. Receives the final detailed specification and writes the code.
> At this stage, speed and cheapness are important - less powerful models are used.

## Operating principle

- The final technical specification is transmitted entirely as a system context (`.cursorrules` /
  `AGENTS.md` / system promt).
- Tasks are broken down into small, atomic steps.
- The model does not make architectural decisions - it only implements what is described.
- For complex questions, return to Claude.

## Recommended models

| Task | Model |
|--------|--------|
| Routine implementation | Claude Haiku / GPT-4o mini / Gemini Flash |
| Non-trivial areas | Claude Sonnet (dotted) |
| Refactoring complex code | Claude Fable 5 (dotted) |

## Typical duty cycle

```
1. Open repository in Cursor
2. Add final technical specification to .cursorrules or AGENTS.md
3. Set point tasks: "Implement the class PermissionRegistry according to the technical specifications"
4. Check the result, commit when ready
5. For complex questions, return to Claude for clarification
```

## Structure `.cursorrules`

Recommended file format:

```
# Project Spec

## Purpose
[Brief description of the task]

## Architecture
[Insert directory structure from detailed specification]

## Classes and interfaces
[List with description]

## Patterns
[What patterns are used]

## Rules
- Do not make architectural changes without approval
- Follow the naming from the technical specifications
- Commit atomically across components
```

> In this project, utilitarian skills (how exactly to write tests, service provider,
> package migration) are connected as **skills** — via
> [`skiller vendor`](../guide/cli) for Cursor. TK describes *what* build,
> skills - *like* do this in this IDE.

## Point connection Claude

Claude connects **dotted** when:

- Solving non-trivial architectural issues.
- Refactoring complex areas.
- Analysis of non-obvious behavior of the framework.

Important: Claude at this stage does not rewrite the technical specifications - only answers a specific question.

## What we get at the output

- Implemented package / component.
- Commits organized by component.
- List of questions for code review.

Next: the code is sent for review → [Claude](./claude) (section «Code review»).
