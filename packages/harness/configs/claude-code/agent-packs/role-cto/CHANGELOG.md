# Changelog — role-cto pack

Versions per-PACK (Keep a Changelog). Each entry is marked affected install-file,
so that the upgrade agent matches the change with a specific project file.

## [0.1.3] - 2026-10-01

### Changed

- **English-only pack content:** agent prompts, templates, docs and the manifest are translated to
  English. Affected install-files: every file the pack installs (`.claude/agents/{PACK_PREFIX}-*.md`
  and the other `files[]` targets); upgrade with `harness agent-packs upgrade --pack role-cto`.

## [0.1.2] - 2026-07-12

### Changed

- **Diet `description` all agents of the pack** (P4.1, plan CONTEXT-ECONOMY): frontmatter
  `description:` each `agents/*.md` shortened to cap 600B — 1 indicative `<example>`
  instead of 2-3, the anti-trigger is reduced to one phrase in prose. Affected install-files
  `.claude/agents/{PACK_PREFIX}-*.md` (all agents of the pack).

## [0.1.1] - 2026-07-02

### Changed

- Technical bump: rolling out provenance-headers engine agent-packs (harness) — when
  re-render/upgrade agents receive header `swissknifeman:generated` with Edit-policy.
  The contents of the pack agents have not changed. Context: SKM-MASTER-002 phase E.

## [0.1.0] - 2026-06-25

### Added

- Persona-pack `role-cto` (`shape: role`, cross-stack): subagents - architecture-decision (opus), tech-radar-curator (opus), ai-viability-assessor (opus).
  Delivery by `project.roles` → `role_packs`-hub map (option A+C). Interview -
  only `PACK_PREFIX`; model dashes by literals in `model:` (standalone-delivery not
  gets `profile.model_tiers`). Files: `agents/*.md` → `.claude/agents/{PACK_PREFIX}-*.md`.
