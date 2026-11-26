# Changelog — laravel-package pack

Versions per-PACK (one version - one changelog). Format Keep a Changelog. Each
entry marks affected install-file for the upgrade agent to match
change with a specific project file.

## [0.2.3] - 2026-10-01

### Changed

- **English-only pack content:** agent prompts, templates, docs and the manifest are translated to
  English. Affected install-files: every file the pack installs (`.claude/agents/{PACK_PREFIX}-*.md`
  and the other `files[]` targets); upgrade with `harness agent-packs upgrade --pack laravel-package`.

## [0.2.2] - 2026-07-12

### Changed

- **Diet `description` all agents of the pack** (P4.1, plan CONTEXT-ECONOMY): frontmatter
  `description:` each `agents/*.md` shortened to cap 600B — 1 indicative `<example>`
  instead of 2-3, the anti-trigger is reduced to one phrase in prose. Affected install-files
  `.claude/agents/{PACK_PREFIX}-*.md` (all agents of the pack).

## [0.1.1] - 2026-07-02

### Fixed

- **BC-string Verify in `workflows/dev-loop.js`** (T6ah, SKM-MASTER-003 P2.5) — point 6
  list Verify wrapped in `<!-- pack:if BC_CHECK_CMD -->…<!-- pack:endif -->` /
  `<!-- pack:ifnot BC_CHECK_CMD --> … <!-- pack:endif -->`: when unspecified `{{BC_CHECK_CMD}}`
  render no longer carries a raw placeholder with double space («if specified, run
  her…») — explicit text instead «command not specified - mark «BC-checker is not installed,
  pass»» (step does not disappear silently, the semantics are the same). Affected install-file
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`. Not shared-block (pack-unique string,
  no duplicate in other packs) — `test_agentpacks_shared.py` is not affected.

## [0.1.0] - 2026-07-02

First release. Separate pack for **Laravel-PACKAGES** (composer library / monorepo
packages), not applications - have reviewer'and is replaced ~60% body relative
`backend-laravel`, unit identity slice-builder other («package feature»).
Context: Master Plan SKM-MASTER-002, phase F; roadmap `php-package-stack-pack.md` →
«implemented». Bool-mode (`IS_LARAVEL_PACKAGE`) tried and cut into
backend-laravel@0.9.0 — does not return here.

### Added

- **`agents/reviewer.md`** — center «package public contract»: axes Public API/BC-SemVer
  (Contracts-diff, `getFacadeAccessor`, removed public method without MAJOR → CRITICAL,
  `{{BC_CHECK_CMD}}` vs latest tag if available roave/backward-compatibility-check),
  ServiceProvider register-vs-boot (I/O in register → HIGH), publishables
  (`pack:if HAS_MIGRATIONS`), `env()` out config → HIGH, composer-constraints
  (dev-tools in require → CRITICAL; laravel/framework instead illuminate/* → MED),
  Testbench (`use App\` in tests → HIGH), multi-version matrix.
  Install-file `.claude/agents/{PACK_PREFIX}-reviewer.md`.
- **`agents/slice-builder.md`** — unit = «package feature» (contract → implementation →
  registration in provider → publishables → facade); minimum public canon
  surfaces (`@internal`/`final`). Install-file `.claude/agents/{PACK_PREFIX}-slice-builder.md`.
- **`agents/test-writer.md`** — Testbench (batch TestCase/getPackageProviders,
  in-memory sqlite `{{TEST_DB}}`), matrix-sensitive `version_compare`-branches.
- **`agents/api-surface.md`** — new recon-agent ({{MODEL_RECON}}): diff map
  public surface (added/changed/removed + SemVer-hint). route-mapper/blade-review
  app-packs are missing in this pack.
- **`agents/{spec-writer,test-verifier,security-review}.md`** — forks with batch prose
  (security-review: + secrets in publishable config, md5/sha1 for tokens; app-axes
  policy/IDOR/middleware removed).
- **`rules/{public-api,service-provider,package-migrations}.md`** (verbatim) +
  **`rules/tests.md`** (template) — path-scoped batch canon rules.
- **`rules/reviewer-overrides.md`** (user_owned, `role:override`) →
  `.claude/rules/{PACK_PREFIX}-reviewer-overrides.md` — legal zone of project axes.
- **`workflows/dev-loop.js`** — fork backend-laravel: lanes/risk-adaptive no changes,
  `+'public-api'` in risk_markers, HARD_GATES under the package, preflight
  `composer validate --strict` + PDO sqlite, Verify + grep `env(` + `{{BC_CHECK_CMD}}`.
- **`src_pack`-review**: `hooks/review-gate.sh`, `settings/review-gate.env.ini`,
  `settings/settings.fragment.json` are taken from `backend-laravel` byte-to-byte
  (engine link `src_pack`, there are no copies in the pack directory).
- **Interview/detect** (safe-samples): `PACKAGE_SRC_ROOT` (src | packages/*/src),
  `PACKAGE_NAMESPACE` (psr-4 from composer.json c fallback on `packages/*/composer.json`,
  shortest prefix - monorepo case), `TEST_FRAMEWORK`/`TEST_RUNNER_CMD`/`CHECK_CMD`/
  `HAS_MIGRATIONS`/`BC_CHECK_CMD` (empty = axis in prose). app-project (artisan) →
  use `backend-laravel`.

### Known limitations

- `stack.detect.none_of` — informational (engine agent-packs detect-does not read matching).
- ~~When empty `BC_CHECK_CMD` in Verify-prompt dev-loop remains a double space
  (no `pack:if`-wrappers) — cosmetics, follow-up.~~ Fixed in 0.1.1.
