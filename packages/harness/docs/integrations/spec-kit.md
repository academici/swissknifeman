# GitHub Spec Kit

## What is this

GitHub Spec Kit — toolkit for **spec-driven development**: forces AI-agent write
specification before code. This is not MCP-server, and CLI `specify` + set of templates and slash-commands,
which are built into the agent (supports Claude Code, Copilot, Cursor, Gemini CLI etc.).

- Repository: <https://github.com/github/spec-kit>
- Documentation: <https://github.github.com/spec-kit/>

## Duty cycle

Four phases, each - markdown-file that the following reads:

```
Specify → Plan → Tasks → Implement
```

After `specify init` agent receives slash-commands (`/specify`, `/plan`, `/tasks`,
`/implement` etc.) — from requirements description to task generation and implementation.

## Installation

Via `uvx` (Python/uv), integration under Claude Code:

```bash
uvx --from git+https://github.com/github/spec-kit.git specify init my-project \
  --integration claude
```

## Connection with hub practices

::: tip There are already overlapping practices
B swissknifeman discipline «spec/solution before code» is closed by skills:
`general/spec-interview` (interview and technical specifications before the code), `general/task-brief-template`
(target/boundaries/invariants/DoD), `architect/architecture` and
`architect/package-contribution-protocol` (ADR-template, border «project ↔ package»).
Spec Kit — this is external *tuning* the same approach with their slash-commands; take it if
need a ready-made frame spec→plan→tasks→implement, and not as a replacement for these skills.
:::

Specification Spec Kit fits well PRD for [Task Master](./task-master).

## Limitations

- Value is in adherence to process, not technology: without discipline, templates just lie there.
- Requires `uv` (Python).
- Basic materials - in English; for the Russian-speaking team, adapt the wording.
