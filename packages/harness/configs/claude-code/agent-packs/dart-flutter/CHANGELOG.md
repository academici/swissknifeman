# Changelog — dart-flutter pack

Format - [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); versions - per-PACK (semver).

## [0.5.3] - 2026-10-01

### Changed

- **English-only pack content:** agent prompts, templates, docs and the manifest are translated to
  English. Affected install-files: every file the pack installs (`.claude/agents/{PACK_PREFIX}-*.md`
  and the other `files[]` targets); upgrade with `harness agent-packs upgrade --pack dart-flutter`.

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

- Starter pack for Flutter/Dart (mobile / POS / embedded):
  - `agents/slice-builder.md`, `agents/test-writer.md`, `agents/reviewer.md`
    (POS/embedded-aware), `agents/ffi-reviewer.md` (opt., under FFI), `agents/spec-writer.md`
    (opt.) — canonical `description` with `<example>`, `color`, `model: {{MODEL_*}}`
    (default `inherit`).
  - `workflows/dev-loop.js`, `hooks/review-gate.sh` (verbatim) +
    `hooks/review-gate.env.ini` (template, user_owned), `hooks/validate-flutter.sh`
    (PostToolUse `dart analyze` → additionalContext, does not block).
  - `settings/settings.fragment.json` (SubagentStop+PostToolUse),
    `rules/{widgets,state,ffi,tests}.md`, `docs/subagents-and-workflows.md`.
- Interview: `STATE_MGMT`, `HAS_FFI`, `TARGET_KIND` (mobile/pos-embedded/desktop),
  `FLUTTER_BIN`/`DART_BIN`/`ANALYZE_CMD`/`FORMAT_CMD`. FFI-blocks under `pack:if HAS_FFI`.

### Migration notes (agent-facing)

- First version - no upgrade.
- Bucket `mobile` thin (1 skill): architecture/state/FFI/POS — in agent prompts and
  `rules/`, without new ported skills (anti-bloat). Future Candidate (according to real
  reuse): `mobile/flutter-testing`.
- Recommended profile preset for shooting ranges: reviewer/spec=opus, slice/test=sonnet.
- Orchestrator - separate package `_common`.
