# Changelog — node-frontend pack

Format - [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); versions - per-PACK (semver).

## [0.5.2] - 2026-07-12

### Changed

- **Diet `description` all agents of the pack** (P4.1, plan CONTEXT-ECONOMY): frontmatter
  `description:` each `agents/*.md` shortened to cap 600B — 1 indicative `<example>`
  instead of 2-3, the anti-trigger is reduced to one phrase in prose. Affected install-files
  `.claude/agents/{PACK_PREFIX}-*.md` (all agents of the pack).

## [0.4.1] - 2026-07-02

### Added

- **Axis `generated-core-edited` (HIGH) in `agents/reviewer.md`** — diff touching file
  with header `swissknifeman:generated`, is reported as HIGH: move edit to override,
  core restore by render. Affected install-file `.claude/agents/{PACK_PREFIX}-reviewer.md`.
- **Overlay-scaffold `rules/reviewer-overrides.md`** (user_owned, `role:override`) →
  `.claude/rules/{PACK_PREFIX}-reviewer-overrides.md`: legal zone of project axes review;
  reviewer reads it as a final block «Project overrides» OVER the common axes.
- **HARD_GATES in `workflows/dev-loop.js`**: generated `.claude/agents|workflows|hooks`
  do not edit - overrides in `.claude/rules/*-overrides.md`.
- Provenance-headers in rendered-files are added by ENGINE agent-packs (harness), not templates
  pack. Context: SKM-MASTER-002 phase E.

## [0.4.0] - 2026-07-02

### Changed

- **dev-loop: `agent({schema})` throw (schema-noncompliance) no longer drops the run
  (azguard overnight-incident 2026-07-02).** Affected install-file
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`: all calls `agent()` wrapped in
  `safeAgent()` — if subagent terminated without calling StructuredOutput (throw
  `subagent completed without calling StructuredOutput`), exception is suppressed in `null`
  instead of floating to the top; further standard degradation `if (!result)` (infra-failed →
  fail-fast → Verify/report), as already happened for terminal API-errors. Previously throw
  dropped EVERYTHING workflow (loss of progress, manual resume).

## [0.3.0] - 2026-07-01

### Changed

- **dev-loop resilience (rate-limit incident 2026-07-01).** Affected install-file
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`: status `infra-failed` in enum schemas
  (infra-failure is not disguised as `deferred`); fail-fast to terminal
  `agent()===null` (STOP run); batch 3 default → 2; heartbeat `log()` on each
  step; text marker `===SLICE-RESULT=== status=…` as an alternate return path.
- In-script `withDeadline` **do not add** (sandbox does not provide `Date.now()`/`setTimeout`/
  cancel); lingering hang catches external supervisor — see pack `_common` and
  `docs/skiller/workflows/background-agents.md` → «Resilience».

## [0.2.0] - 2026-06-29

### Changed

- **AI-guide moved from public `docs/` in `.claude/guidelines/`.** `DOCS_DIR` by
  default now `.claude/guidelines` (was `docs/05_AI/guidelines`):
  `subagents-and-workflows.md` — internal artifact for agents, not public
  project documentation. Affected install-file `{DOCS_DIR}/subagents-and-workflows.md`.

> **Migration (upgrade):** new guide in `.claude/guidelines/`; old file in
> `docs/05_AI/guidelines/` is not removed automatically - remove it manually.

## [0.1.0] - 2026-06-24

### Added

- Initial frontend-pack for Vue/Vite (SPA/Inertia/Nuxt):
  - `agents/component-builder.md` (atomic SFC), `agents/slice-builder.md` (slice
    pages/features), `agents/test-writer.md` (Vitest+test-utils), `agents/reviewer.md`
    (tsc/eslint/types/a11y), `agents/spec-writer.md` (opt.) — canonical `description`
    with `<example>`, `color`, `model: {{MODEL_*}}` (default `inherit`).
  - `workflows/dev-loop.js` — slice→impl→test→review on one branch (hardcap, circuit-breaker).
  - `hooks/review-gate.sh` (verbatim, general) + `hooks/review-gate.env.ini` (template,
    user_owned) — SubagentStop-gate.
  - `hooks/validate-frontend.sh` (verbatim) — PostToolUse tsc/eslint → additionalContext,
    does NOT block.
  - `settings/settings.fragment.json` — SubagentStop + PostToolUse (merge append-if-absent).
  - `rules/{components,state,tests}.md`, `docs/subagents-and-workflows.md`.
- Skills - from the bucket `frontend` (vue/vite/pinia/inertia-vue/vitest-vue/tailwind…); new
  we do not introduce skills.

### Migration notes (agent-facing)

- First version - no upgrade; install = interview → render → lock with `base_sha256`.
- Recommended profile preset for shooting ranges: reviewer/spec=opus, component/slice/test=sonnet
  (sets `profiles/node-frontend.json:model_tiers`).
- Orchestrator - separate package `_common` (put with the same `PACK_PREFIX`).
