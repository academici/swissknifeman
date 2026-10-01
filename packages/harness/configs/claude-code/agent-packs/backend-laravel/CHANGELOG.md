# Changelog — backend-laravel pack

Versions per-PACK (one version - one changelog). Format Keep a Changelog. Each
entry marks affected install-file for the upgrade agent to match
change with a specific project file.

## [0.12.3] - 2026-10-01

### Changed

- **English-only pack content:** agent prompts, templates, docs and the manifest are translated to
  English. Affected install-files: every file the pack installs (`.claude/agents/{PACK_PREFIX}-*.md`
  and the other `files[]` targets); upgrade with `harness agent-packs upgrade --pack backend-laravel`.

## [0.12.2] - 2026-07-12

### Changed

- **Diet `description` all agents of the pack** (P4.1, plan CONTEXT-ECONOMY): frontmatter
  `description:` each `agents/*.md` shortened to cap 600B — 1 indicative `<example>`
  instead of 2-3, the anti-trigger is reduced to one phrase in prose. Affected install-files
  `.claude/agents/{PACK_PREFIX}-*.md` (all agents of the pack).

## [0.11.2] - 2026-07-02

### Changed

- **Shared-prose markup for parity-test.** 6 common blocks `agents/reviewer.md`
  (risk-adaptive, config-honesty, test-honesty, over-engineering, generated-assets,
  report-format) wrapped in markers `<!-- shared:X --> … <!-- /shared:X -->` without
  content changes; blocks of the same name `laravel-package` are compared
  byte-to-byte test `test_agentpacks_shared.py` (general text drift = red test).
- **Fix `app/Repositories` → `{{ACCESS_ROOT}}/Repositories`** in `agents/reviewer.md`
  and `agents/slice-builder.md` — last paths past `ACCESS_ROOT` (tail 0.9.0);
  when `ACCESS_ROOT=app` render byte is equivalent to the previous meaning (verified
  regression F-8 master plan SKM-MASTER-002). Affected install-files
  `.claude/agents/{PACK_PREFIX}-reviewer.md`, `.claude/agents/{PACK_PREFIX}-slice-builder.md`.

## [0.11.1] - 2026-07-02

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

## [0.11.0] - 2026-07-02

### Changed

- **dev-loop: `agent({schema})` throw (schema-noncompliance) no longer drops the run
  (azguard overnight-incident 2026-07-02).** Affected install-file
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`: all calls `agent()` wrapped in
  `safeAgent()` — if subagent terminated without calling StructuredOutput (throw
  `subagent completed without calling StructuredOutput`), exception is suppressed in `null`
  instead of floating to the top; further standard degradation `if (!result)` (infra-failed →
  fail-fast → Verify/report), as already happened for terminal API-errors. Previously throw
  dropped EVERYTHING workflow (loss of progress, manual resume).

## [0.10.0] - 2026-07-01

### Added

- **`tool_failures[]` in `SLICE_RESULT_SCHEMA` (`dev-loop.js`)** (field-feedback: RAG-plan facts
  must be honestly marked when the engine fails). The slice can now honestly report that the verification engine
  external fact was not available (`perplexity-web` locked/`TIMEOUT`, `context7` empty, MCP lay down) →
  fact unverified, needed **REPEAT PASS** (DO NOT guess, DO NOT mask). Optional field
  (backwards compatible with old calls); test-writer-promt received honesty string; final
  report aggregates counter `tool_failures`. Affected install-file `.claude/workflows/{PACK_PREFIX}-dev-loop.js`.

## [0.9.0] - 2026-07-01

Combining two project axes into one package (**supersedes PR #96**): `ACCESS_ROOT` (layout-path,
including monorepo) supplanted `IS_LARAVEL_PACKAGE` (app-vs-src, monorepo couldn't);
`SCAFFOLDS_SCHEMA` from #96 saved (orthogonal axis).

### Changed

- **Layout-aware access-layer paths (monorepo support).** Auto-detection
  interview variable `ACCESS_ROOT` (`app` | `src` | `packages/*/src`, sample
  `test -d app/Http … ; ls -d packages/*/src/Http …`). Hardskinned `app/`-paths
  replaced with `{{ACCESS_ROOT}}/…` in install-files: `.claude/workflows/{PACK_PREFIX}-dev-loop.js`
  (Verify-grep), `.claude/agents/{PACK_PREFIX}-reviewer.md`, `.claude/agents/{PACK_PREFIX}-slice-builder.md`.
  Reason: monorepo Laravel-packages (code in `packages/*/src/Http`) was paddling around
  non-existent path → false green access-layer (class F-incident).
- **Drop `/Api`-segment** in grep/prose: `{{ACCESS_ROOT}}/Http/Controllers` (recursive
  grep covers `Api/`-subfolder app and flat package controllers/monorepo; chatom
  holds controllers in `packages/*/src/Http/Controllers` without `Api/`).
- **`expect_globs: ["{ACCESS_ROOT}/Http/Controllers"]`** — enables post-rendering
  engine validation: path matches 0 files → `render`/`upgrade` print WARN
  (safety net against false green, regardless detect).

### Added (from #96, orthogonal ACCESS_ROOT)

- **`SCAFFOLDS_SCHEMA`** (bool, detect `test -d app/Models && echo false || echo true`,
  default true) — agents start migrations/models (greenfield/package) vs written over
  finished diagram (established-app). Divorced `pack:if/pack:ifnot`-blocks in install-files:
  `slice-builder.md`, `reviewer.md`, `dev-loop.js` (HARD_GATES). Axis independent of `ACCESS_ROOT`.

## [0.7.0] - 2026-07-01

### Changed

- **dev-loop resilience (rate-limit incident 2026-07-01).** Affected install-file
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`:
  - Slice status `infra-failed` in enum circuits - infra failure (rate-limit/timeout/
    `agent()`=null) is no longer disguised as `deferred` (honest telemetry).
  - Fail-fast: terminal `agent()===null` → `infra-failed` + STOP run
    (throttling itself will not pass from the transition to the next slice).
  - Batch default `DEFAULT_MAX` 3 → 2 — less retry-surfaces under throttling.
  - Heartbeat `log()` at each slice step (liveliness signal for supervisor/person).
  - Bullet text `===SLICE-RESULT=== status=…` as return path (bypass
    StructuredOutput retry-cap runtime on long/complex returns).
  - Final `log()` shows the number `infra-failed`.

### Not added (deliberately)

- In-script wall-clock / `withDeadline` — sandbox Workflow does not work `Date.now()`/
  reliable `setTimeout`, `agent()` is not cancelled. Lingering hang catches **external
  supervisor** (orchestrator report ~30 min + `PushNotification`; see pack `_common`
  and `docs/skiller/workflows/background-agents.md` → «Resilience»).

## [0.6.0] - 2026-06-30

### Added

- **Read-only recon-subagents** (isolated reconnaissance → main-the context does not swell, only a summary goes to the top;
  subagent reads are not counted to the orchestrator window): `{prefix}-route-mapper` (routes→controllers→Action),
  `{prefix}-db-impact` (affected models/migrations/communications/indexes), `{prefix}-blade-review` (escaping/N+1
  in views), `{prefix}-test-verifier` (running tests → COMPRESSED summary, verbose-output remains in the subagent),
  `{prefix}-security-review` (auth/policy/injection/secrets/IDOR). All `optional`, model `{{MODEL_RECON}}`
  (default `haiku`). Operationalizes «heavy reading - to subagent» (skill `context-economy` §8). New
  install-files `.claude/agents/{prefix}-{route-mapper,db-impact,blade-review,test-verifier,security-review}.md`.
- **Guide `subagents-and-workflows.md` updated**: section «How tasks are set» (`/task:*` + `args.slices`),
  **mermaid-process diagram dev-loop** (Setup→Build[impl→test→risk-review]→Verify + recon-delegation),
  recon-agents and risk-adaptive reviewer in the agents table; hardcode `pint`/phpstan → `{{CHECK_CMD}}`.

## [0.5.0] - 2026-06-30

### Added

- **Risk-adaptive review-gate.** `SLICE_RESULT_SCHEMA` (`workflows/dev-loop.js`) expanded:
  `risk_level` (LOW|MED|HIGH, required), `risk_markers` (concurrency/transactions/data-integrity/
  queue-semantics/connectors), `workarounds`, `test_coverage_pct`. Review depth scales to
  RISK, not size: LOW→spot-check, MED→contracts/auth, HIGH→adversarial (list failure-modes →
  build a crash script) + fresh-context. **Detect ≠ gating**: report of ALL finds from severity-enum
  {LOW,MED,HIGH,CRITICAL} + `failure_scenario`, filtering/merge — by packet gates. Affected
  install-files `.claude/workflows/<prefix>-dev-loop.js`, `.claude/agents/<prefix>-reviewer.md`,
  `.claude/agents/<prefix>-test-writer.md`. (Source: retrospective chatom — 78% major masked
  green tests.)
- **Lean-tiered model/effort-lanes.** Per-slice model/effort at risk of shearing (Haiku trivial / Sonnet
  impl / Opus+xhigh on HIGH-review), interrupt the environment through `agent()`. Defaults `MODEL_*` (pack.json):
  slice-builder=sonnet, test-writer=sonnet, reviewer=opus, spec-writer=opus (was `inherit`).
- **Fairness of tests.** test-writer marks walkthroughs/force configs like `[POSSIBLE-DEFECT]` and uncovered
  queue-semantics ShouldQueue (`handle()` directly); `.claude/rules/tests.md` duplicates the rule.
- **Env-preflight** in Setup-phase dev-loop: version PHP + `PDO::getAvailableDrivers()` + dry run
  BEFORE distributing slices; environment blocker stops the run (chatom F3: php without worker pdo_sqlite).

### Fixed

- **False instruction «project NOT on Pest»** removed from `agents/reviewer.md` (chatom F2) →
  `{{TEST_FRAMEWORK}}`. Hardcode `vendor/bin/pint --test` + «phpstan not installed» →
  parameterized `{{CHECK_CMD}}`.
- **Layout-agnostic globs rules** (chatom F4): `app/Http/Controllers/**`→`**/Http/Controllers/**`,
  `database/migrations/**`→`**/database/migrations/**`, `tests/**`→`**/tests/**` (+`**/database/factories/**`) —
  matchat package-layout `packages/*/src/...`. Affected `.claude/rules/{api-controllers,migrations,tests}.md`
  (+ per-layer risk-annotations for conditional-reviewer checklists).

## [0.4.0] - 2026-06-29

### Changed

- **AI-guide moved from public `docs/` in `.claude/guidelines/`.** `DOCS_DIR` by
  default now `.claude/guidelines` (was `docs/05_AI/guidelines`). Guide
  `subagents-and-workflows.md` — internal artifact for agents, not public
  VitePress-package documentation: in open-source PHP-package `docs/` is published, and
  machine guide has no place there (a doc-sync pulled him into Brain-valt). Affected
  install-file `{DOCS_DIR}/subagents-and-workflows.md`.
- **Removed erroneous Brain-frontmatter from template** `docs/subagents-and-workflows.md`
  (`parent: [[05_AI]]`, tags, created) and wiki link `[[agent-system-references]]` —
  Obsidian-wiki links would be broken wikilink-gate, make the guide public `docs/`.

> **Migration (upgrade installed projects):** new guide will appear in
> `.claude/guidelines/`; **old file in `docs/05_AI/guidelines/` is not deleted
> automatically** (engine does not clean when changing target) — remove it manually.

## [0.3.0] - 2026-06-28

### Changed

- **Templates have been deuniversalized - the secure environment of one project has been removed** (agents/slice-builder,
  agents/test-writer, rules/tests, workflows/dev-loop, docs/subagents-and-workflows). Test framework
  is now parametric via `{{TEST_FRAMEWORK}}` (was previously ignored - hardcode «PHPUnit-native, NOT
  Pest»). Deleted machine-specific statements (`php8.5`/`pgsql`/`Postgres raised`/`/usr/bin/php8.4`)
  and false for most projects («phpstan not installed - do not call», «do not add migrations -
  complete diagram»). Identity slice-builder softened to «Laravel/REST API or package on top of models
  project» (before - «on top of a ready-made 8-domain model layer»). Static check now
  refers to `{{CHECK_CMD}}`. Affected install-files: `.claude/agents/{prefix}-slice-builder.md`,
  `{prefix}-test-writer.md`, `.claude/rules/tests.md`, `.claude/workflows/{prefix}-dev-loop.js`,
  `docs/.../subagents-and-workflows.md` — upgrade will re-render them.

## [0.2.0] - 2026-06-24

### Added

- Canonical `description` of all agents in auto-delegation format Claude Code
  («Use this agent when…» + 2–3 `<example>` Context/user/assistant/`<commentary>`,
  placeholder-safe) — `agents/{reviewer,slice-builder,test-writer,spec-writer}.md`.
- Field `color` to each agent (reviewer=yellow, slice-builder=green, test-writer=cyan,
  spec-writer=magenta) and a stack-agnostic orchestrator (pack `_common`, blue).
- Model shooting ranges via placeholders: `model: {{MODEL_REVIEWER|MODEL_SLICE_BUILDER|`
  `MODEL_TEST_WRITER|MODEL_SPEC_WRITER}}` (everyone's default - `inherit`, behavior is not
  changes; project type profile pre-fills dashes via `model_tiers`).
- Quantized gates in `agents/reviewer.md`: `{{GATE_MAX_CRITICAL}}`/
  `{{GATE_COVERAGE_MIN}}`/`{{GATE_MAX_COMPLEXITY}}` — verdict on thresholds, not «by eye».
- `stack.project_type: "laravel-project"` — canonical detection by reference to
  `core.project` (legacy `detect.all_of` saved for agentdriven skill).

### Changed

- `hooks/review-gate.sh` — generalized missing-tool guard (path → executability,
  bare-command → PATH), now verbatim-can be reused with any stack pack.

### Migration notes (agent-facing)

- WATCH on 4 agent files: if frontmatter edited locally (changed `model`/added
  skills) — upgrade will mark `conflict`, new render will be nearby `*.pack-new`, original not
  is overwritten; fry manually.
- New interview fields `MODEL_*` (default `inherit`) and `GATE_*` (80/0/10) — on upgrade
  autos from defaults are interrogated; recommended profile preset: reviewer/spec=opus,
  slice/test=sonnet (sets it `profiles/laravel-project.json:model_tiers`).
- `review-gate.sh` (verbatim) — safe-apply, if not edited locally.

## [0.1.0] - 2026-06-23

### Added

- Initial pack, summarized from overnight-artifacts memster:
  - `agents/slice-builder.md`, `agents/test-writer.md`, `agents/reviewer.md` —
    roles with `skills:` preload + self-load fallback; stack-specific via placeholders.
  - `workflows/dev-loop.js` — slice→impl→test→review on one branch; defense lessons:
    one branch/run, hard cap `DEFAULT_MAX` literal (is worried resume),
    circuit-breaker.
  - `hooks/review-gate.sh` (verbatim) + `hooks/review-gate.env.ini` (template,
    user_owned) — SubagentStop-gate off|warn|strict.
  - `settings/settings.fragment.json` — registration SubagentStop (merge append-if-absent).
  - `docs/subagents-and-workflows.md` — guideline.
  - `agents/spec-writer.md` (opt.) — writes `docs/specs/<feature>.md` for large features.
  - `rules/{api-controllers,migrations,tests}.md` — path-scoped rules (`.claude/rules/`,
    native auto-loading by paths); thin triggers → refer to skills.
- Placeholders: `{{PACK_PREFIX}}`, `{{PROJECT_DIR}}`, `{{PHP_RUNNER}}`,
  `{{TEST_RUNNER_CMD}}`, `{{TEST_DB}}`, `{{CHECK_CMD}}`.

### Migration notes (agent-facing)

- First version - no upgrade. On install: interview (see `pack.json:interview`),
  placeholder render, lock with `base_sha256` rendered.
- SAFE-APPLY-semantics will appear with the second version: SAFE-APPLY (base has changed,
  file is not edited locally) / WATCH (edited locally - show delta, not
  overwrite) / OPTIONAL (new, optional).
