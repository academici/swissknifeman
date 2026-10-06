# Agent Framework

Opinionated agent-practitioner framework Claude Code ecosystems academici: subagents,
skills, work flow, hooks - versioned and portable between projects.

> **Rack: data + skill, NOT engine-generator.** Templates are real `.md`/`.js`
> files in versioned packages; installation, adaptation and upgrade is executed by the agent
> clear metadata (manifest + CHANGELOG + lock), and not Python/Mustache-compiler.
> This is a conscious decision (see [decisions-ledger](./decisions-ledger)).

## Map

| Document | What's it about? |
|---|---|
| [framework-overview](./framework-overview) | Current state of the framework - what is already there (audit input) |
| [decisions-ledger](./decisions-ledger) | What is accepted / rejected and why (audit input) |
| [roles](./roles) | Universal role agents (reviewer/implementer/…); general, stack - from profile |
| [skills-index-and-hub](./skills-index-and-hub) | Hub like AI Skills Index; fix regression «skills are not visible» |
| [post-integration-checklist](./post-integration-checklist) | Integrity check after implementation/upgrade pack |
| `agent-packs` (skill) | Installation/upgrade versioned packs - `skills/system/agent-packs/SKILL.md` |

## Continuous audit

The framework is developed through periodic audits Perplexity. Promt and loop:

- Promt: [workflows/framework-audit](../workflows/framework-audit) — paste into
  Perplexity, for entry you give `framework-overview` + `decisions-ledger`.
- Archive of runs: [audits/](../audits/) (raw + triage for each).
- Ledger sources: `references/framework-audits.md`.

The loop is self-anchoring: each audit starts from a post-previous state, so
does not re-offer something that is already ready or rejected.

## Components (packages)

- **harness** — versioned packs (`configs/claude-code/agent-packs/`), hooks,
  settings, MCP. Distributes files to `.claude/` project (merge-only).
- **skiller** — skills + hub (AI Skills Index) + playbook-skill `agent-packs`.
- **maind** — memory and graph (opt. persistent task-graph - deferred).
