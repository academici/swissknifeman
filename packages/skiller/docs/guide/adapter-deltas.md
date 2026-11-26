# Adapter deltas

`SKILL.md` — the only source of truth, provider-neutral. Anything specific
for a specific agent is entered in **delta files** `adapters/<agent>.md`
inside the skill folder:

```
SKILL.md  ←── the only one source of truth
    │
    ├── adapters/claude.md   (only delta: overrides, add. instructions)
    ├── adapters/cursor.md   (only delta: .cursor/rules specific)
    └── adapters/<agent>.md  (any other agent on the same principle)
```

**Delta is NOT duplicate SKILL.md** — it contains only differences.

## When delta is needed

| Condition | Need a delta? |
|---|---|
| Agent uses a different output format | ✅ yes |
| Agent has specific tools (MCP, tools) | ✅ yes |
| Agent requires special prompt syntax / rules | ✅ yes |
| The skill works the same everywhere | ❌ no - the file is not created |

Lack of delta is the norm: most skills provider-neutral in its entirety.

## Delta format

Delta - markdown from sections of two types:

- `## Override: <what>` — replaces the corresponding part SKILL.md;
- `## Additional: <what>` — adds instructions without canceling the main ones.

```markdown
## Override: output_format
Instead markdown use JSON with fields: ...

## Additional: pre_flight
Before executing, check the presence of the file composer.json
```

## Typical sections

### Pre-flight hook

Checking preconditions before starting a skill:

````markdown
## Additional: pre_flight
```bash
# perform before starting the skill
ls composer.json || echo "WARNING: not Laravel-project"
```
````

### Output override

Redirecting results under agent or project conventions:

```markdown
## Override: output_paths
Write files to `infra/docker/` instead `docker/`
```

### Example: delta for Cursor

```markdown
## Cursor Delta: docker-php

### Additional: rules
Add to .cursor/rules:
"When creating Dockerfile always use non-root user and multi-stage build"

### Override: file_creation
Create files via Cursor Edit, not via terminal write
```

### Example: delta for Claude Code

```markdown
## Claude Delta: docker-php

### Additional: pre_flight
Check `docker compose version` — skill is designed for Compose v2.

### Additional: permissions
Skill needs permissions from preset `docker` —
see configs/claude-code/settings.docker.json
```

## Field adapters in frontmatter

Frontmatter skill lists the agents in which the skill is tested:

```yaml
adapters: [claude, cursor, fable]
```

This **compatibility declaration**, and not a list of delta files: the skill can be
tested in three agents and does not have a single delta.

## How skiller vendor works with deltas

When installing with The installer places `--agent <name>` next to `SKILL.md`
only the delta of this agent (if it exists) — deltas of foreign agents in the target
project are not included.

## Checklist when creating a delta

- [ ] There is no duplicate text in the delta SKILL.md
- [ ] Each section - `Override:` or `Additional:` with a clear subject
- [ ] Pre-flight hooks are idempotent and safe (checks only, no recording)
- [ ] The delta of the mentioned agent is in `adapters:` frontmatter-a
