# ADR 0051: Skill metadata in the index and `skiller describe`

## Status

Accepted

## Context

The Agent Skills standard names `license`, `compatibility` and `allowed-tools`. `aicore.content.skill` reads them
into `skill-descriptor/v1` ([ADR 0038](0038-skill-descriptor-agent-skills-standard.md)), but `skills.json` carried no
license and there was no way to see a descriptor from the command line. Editing every `SKILL.md` is outside this
change.

## Decision

- **Index fields.** The registry writes `license` for every skill (frontmatter, then `upstream.json`, then the
  package license) and `compatibility` and `allowed_tools` when the skill declares them. All three come from
  `describe_skill`, the one reader of metadata.
- **Command.** `skiller describe SKILL [--json]` prints the descriptor of a library or host-module skill.
- **Checks.** `validate` builds the descriptor, requires a license for upstream skills and keeps `compatibility` within
  1–500 characters and `allowed-tools` a string.

## Alternatives considered

- Writing `license` and `compatibility` into the frontmatter of all skills: rejected, it edits skill content.

## Consequences

- The change is additive; older readers ignore the new fields.
- A strict frontmatter projection for external validators and copying upstream license texts wait for a trigger; the
  receipt of skill digests in a run belongs to the orchestration stage.

## Supersedes

None.
