# ADR 0038: Skill descriptor: the Agent Skills standard plus digest and provenance

## Status

Accepted

## Context

A skill is a directory with `SKILL.md`, but no code could say what a skill is in one document: identity, content
version, licence, requirements and where it came from were spread over frontmatter, `skills.json`, `skills-lock.json`
and `upstream.json`. The Agent Skills standard defines `name`, `description`, `license`, `compatibility`, `metadata`
and `allowed-tools`. A run that wants to say which skills took part, and an evaluation that wants to compare two
results, both need one stable description.

## Decision

- **A read-only descriptor.** `aicore.content.skill.describe_skill(skill_dir, *, skill_id)` returns a frozen
  `SkillDescriptor`; `to_json()` yields `skill-descriptor/v1`
  (`packages/aicore/schemas/skill-descriptor/v1/skill-descriptor.schema.json`, closed profile). The descriptor only
  reads; it never rewrites a value, and `build_registry` does not call it, so `skills.json` stays byte for byte.
- **Fields.** `schema`, `id` (`<bucket>/<name>` in the skill library, `<module>/<name>` elsewhere), `name` and
  `description` (required; a missing one is `SKILL_DESCRIPTOR_INVALID`), `version`, `digest`, `license`,
  `compatibility`, `allowed_tools`, `adapters`, `requires`, `risk`, `metadata`, `provenance`.
- **Digest.** `digest` is `sha256:` plus `skill_content_hash`, the same algorithm as `content_sha256` in `skills.json`;
  it ignores `upstream.json`, `evals/` and caches, so a skill's digest changes only when what the agent reads changes.
- **Standard fields as the standard defines them.** `compatibility` is free text of 1 to 500 characters and is not
  executed; `allowed-tools` is a space-separated list that only pre-approves tools in Claude Code and is neither a
  requirement nor a security boundary; `license` falls back to the one in `upstream.json`, and frontmatter wins.
- **Provenance** comes from `upstream.json` beside the skill (`source`, `repo`, `strategy`, `license`, the files with
  their hashes, the audit verdict); without it the skill is `{"source": "local"}`. Only these keys are taken.
- **Not done.** Input and output schemas for instruction skills are rejected: a skill is text for an agent, not a
  function. The receipt of which skill digests took part in a run belongs to the orchestration contracts. The
  materialised manifest and `skills-lock.json` already record digests of delivered copies and keep their formats.

## Alternatives considered

- Extend `skills.json` rows: rejected, it changes bytes that other tools hash.
- A new frontmatter schema that skills must satisfy: rejected, the content of skills is out of scope and 200 existing
  skills already carry their own fields (`adapters`, `requires`, `risk`).

## Consequences

- Any module can describe a skill without the skill library; the descriptor validates with `aicore.util.schema`.
- Evaluation context ([ADR 0039](0039-eval-result-context.md)) reuses `skill_digest`.
- The contract is at stability `development` until a second consumer reads it.

## Supersedes

None.
