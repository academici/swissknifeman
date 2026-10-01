# Changelog — _common

Format - [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); versions - per-PACK (semver).

## [0.5.0] - 2026-07-30

### Added

- **Delegation contract in grammar PLAN**: new
  return format field `; output: <return format>` in line `Task N -> @<role> : <target>` and
  section «Job Contract» with five required subagent task elements
  (`objective`/`output`/`tools`/`sources`/`boundaries`, first-party Anthropic) and the rule
  «job without return format is not issued». Additive - existing grammar fields
  (`deps:`/`files:`/`risk:`/`skills:`/`gate:`) have not been renamed or deleted. Affected
  install-file `.claude/agents/{PACK_PREFIX}-orchestrator.md` and provider-neutral canon
  `configs/common/agent-packs/roles.json::_common.orchestrator.content`.

## [0.4.1] - 2026-07-12

### Changed

- **Diet `description` all agents of the pack** (P4.1, plan CONTEXT-ECONOMY): frontmatter
  `description:` each `agents/*.md` shortened to cap 600B — 1 indicative `<example>`
  instead of 2-3, the anti-trigger is reduced to one phrase in prose. Affected install-files
  `.claude/agents/{PACK_PREFIX}-*.md` (all agents of the pack).

## [0.4.0] - 2026-07-02

### Added

- **`rules/generated-assets.md` — edit-policy generated-assets** (install-file
  `.claude/rules/generated-assets.md`, paths: `.claude/{agents,workflows,hooks}/**`).
  File with block `swissknifeman:generated` — pack property: do not edit,
  expand only through Extension-points/`.claude/rules/*-overrides.md`; needs editing
  core — stop and report (person does upgrade pack or edit template).
  Context: SKM-MASTER-002 phase E (provenance-headers + drift-detection in the engine harness).

## [0.3.0] - 2026-07-01

### Added

- **Footer `VERIFICATION` + RAG-plan rule in `orchestrator.md`** (field-feedback: agents
  are reluctant to press RAG when forming a plan). Orchestrator now: (1) verifies external facts
  plan BEFORE finalization - first `perplexity-web` (flat-rate, token-cheap), `context7` for API;
  (2) does not produce edits for the sake of edits; (3) add a block to the end of the plan `VERIFICATION` (RAG-engines ·
  **unverified → REPEAT PASS** when the engine fails · workarounds-`[POSSIBLE-DEFECT]`). Affected
  install-file `.claude/agents/{PACK_PREFIX}-orchestrator.md`. Format - canon skill `verify-claims`.

## [0.2.0] - 2026-07-01

### Added

- **Directive liveness-supervision in `orchestrator.md`** (rate-limit incident
  2026-07-01). For background `dev-loop` orchestrator add block `SUPERVISION` —
  main session contract: status report every ~30 min (`Monitor`/`ScheduleWakeup`
  on `git log <base>..HEAD`), `PushNotification` for stagnation/`<failures>`, `TaskStop`
  if necessary. Affected install-file `.claude/agents/{PACK_PREFIX}-orchestrator.md`.
  Motivation: runtime `agent()` auto-retrait rate-limit to high burl → lingering
  hang is not visible from inside the script; reliable fuse - only external supervisor.

## [0.1.0] - 2026-06-24

### Added

- Stack-agnostic subagent `orchestrator` (`agents/orchestrator.md`): delegate-only
  tech-lead, role exploration via `.claude/agents/{PACK_PREFIX}-*.md`, machine readable
  plan `Task N → @<prefix>-<role>` with modes Sequential / Parallel-max2 / Gated.
- Interview: `PACK_PREFIX`, `MODEL_ORCHESTRATOR` (default `inherit`).

### Migration notes (agent-facing)

- First version - no upgrade.
- Install with stack pack; `PACK_PREFIX` must match its prefix,
  otherwise `@<prefix>-<role>` do not resolve as a stack pack.
- Recommended shooting range: `MODEL_ORCHESTRATOR=opus` (planning benefits from a strong model).
