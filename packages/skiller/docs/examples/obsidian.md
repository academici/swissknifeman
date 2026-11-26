# Obsidian vault

Script: AI-agent for working with the knowledge base - notes, technical specifications, documentation,
analysis of ideas.

## Installation

```bash
cd ~/vaults/brain && skiller vendor
```

Autodetect sees `.obsidian/` → profile `obsidian-vault` → bucket-s
**architect, pm, founder, operator, roles, imported**:

- `pm` — BRD, PRD, roadmap, monetization: full cycle of development of technical specifications;
- `founder` — ideas, competitor analysis, pitches;
- `architect` — when a note develops into architecture;
- `imported` — research- and knowledge-super-skills;
- `roles` — persons to change optics (startup-cto, tech-lead).

## Permissions

For vault-but enough `base` — there are no code stacks here:

```bash
harness permissions --target ~/vaults/brain
```

Autodetect will not find stack markers and will only apply `base`: git, file
operations, curl — without prompts; secrets are prohibited.

## Link to the registry

Separate registry mirroring in vault no longer exists: vault — normal
consumer project. Skills are installed once every `skiller vendor`,
and then updated with the command:

```bash
cd ~/vaults/brain && skiller update
```

This way the knowledge base always sees the current catalog of skills - useful when
notes refer to skills or agent in vault-does not match the skill to the task.

## Typical workflow

1. The idea is recorded with a note → skill `founder/idea-analysis` unfolds it
   by structure;
2. the idea is maturing → `pm/brd`, then `pm/prd-from-brd` turn it into TK;
3. Technical specification ready → `architect/*` designs the solution;
4. project starts → [Laravel-script](./laravel) expands
   working environment.
