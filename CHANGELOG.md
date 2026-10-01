# Changelog

## [Unreleased]

### Fixed

- **maind memory digest:** the SessionStart digest sorted by a `timestamp` field that agentmemory 0.9.x
  never returns (records carry `updatedAt`/`createdAt`), so it kept dump order and injected the oldest
  facts instead of the freshest. It now sorts by `updatedAt`/`createdAt` and skips superseded
  (`isLatest=false`) records. `maind` 0.4.10.

## [0.26.0] - 2026-10-01

### Fixed

- **maind memory host address:** the LAN IP of the memory host machine is no longer a hand-edit in the
  tracked `config/memory/iii-config.yaml`. The tracked file stays a portable loopback template; the node sets
  `memory.bind_host` (`config.json`) or `AGENTMEMORY_BIND_HOST` (`auto` = this machine's LAN IPv4), and maind
  renders a gitignored `data/iii-config.runtime.yaml` for the daemon. Non-loopback bind needs
  `memory.role=host`; `0.0.0.0`/`::` stay forbidden. The docs example uses `<HOST_LAN_IP>`, and two skills
  no longer hardcode `/home/<user>/` paths.

### Changed

- **English-only repository:** tracked product files — scripts, CLI diagnostics, docs, workflows,
  skills, Task commands and prompts, adapters, agent-pack projections (`.claude/agents`,
  `.codex/agents` re-rendered from the English packs; the Codex role lock
  `.codex/agent-roles.lock.json` is now tracked) — are translated to English. Kept verbatim by design:
  the immutable `docs/audits/*.raw.md` archive and the generated
  `calibration-probe-log-v2.json`. All ten agent packs are bumped one patch (e.g. `role-maintainer`
  0.2.3) so project upgrades pick up the English content by version, not only by hash. The release umbrella and `task` move to 0.26.0; package and
  skill-unit versions were already above the last tag.
- **Productization cleanup:** `task:plan-run` is the only emitted execution command;
  tracked product files no longer reference working-plan IDs or paths, and
  `plans/`, `roadmap/`, `tasks/`, and `.cursor/plans/` are local ignored workspaces.
  Product instructions, diagnostics, docs, fixtures, and changelog entries are English-only.
  `skiller doctor` reports plan-dependent `capability-reference-coverage` and
  `trace-quality` as `unknown` when no cited finding exists. `docs/task` is fully
  synchronized from the Task package.
- **Public hygiene gate:** rejects tracked working-document paths, concrete plan IDs,
  short-ID citations, links into removed working-document trees, and machine-specific paths.
- **No machine paths in the repository:** the owner's home-directory paths were removed from tracked
  product files (fixtures use `/home/user/…`, docs use `<REPO_ROOT>`/`~`); `scripts/public-hygiene.py` now
  also scans file content for real-environment absolute paths (sealed working documents under `plans/`,
  `roadmap/`, `tasks/` and one hash-pinned fixture are explicitly exempt). Token-estimate calibration records
  neutral `corpus/<name>` labels instead of plan paths (lookup is by content sha256); `plan_weight` resolves
  repo-relative `source_path` from the repository root.

### Removed

- Locale overlays and command-locale machinery, the Artifex business-trial subsystem,
  and three unconsumed Task contract schemas.

### Added

- **Version guard:** `scripts/version-guard.py status [--installed]` lists units whose content
  changed since the last `releases/v*.json` snapshot without a version bump (exit 1) and installed
  plugin caches that lag behind the repo; `bump <unit>` updates `package.json`, lock and plugin
  manifest (or the skill-unit entry in `publication-versions.json`) without reformatting.
  Provider caches are keyed by plugin version, so unbumped changes were never re-fetched
  (a stale `task` kept serving old commands). `release-discipline` and `CONTRIBUTING.md` document
  the procedure; `task` follows the umbrella version (`skiller release`).
- **Next plan number:** `packages/task/scripts/plan-id.py --codename <NAME>` scans live and archived
  plans and returns the next day ordinal `№N`, the next repository-wide `PLAN<N>` Short ID, the ready
  `plan_id` and `title_prefix`. plan-protocol, work-references, plan-template and `plan-design` tell
  agents to use it instead of guessing `№1`/`PLAN1`.
- **Service-file gitignore map:** `configs/gitignore-policy.json` classifies every generated service
  file (`ignore` / `commit` / `portable-or-ignore` / `project`, owner, reason; calibrated on the 24-project
  fleet). Committed: `CLAUDE.md`/`AGENTS.md`, all skills, agent-pack artifacts, hook scripts, examples,
  skiller config. Ignored: logs, runtime state, backups, local settings; `*.env.ini`/configs only when
  they hold machine paths (`/home/…`) or secrets and `maind doctor --gitignore-drift [--project ID] [--block] [--json]` reports per-project drift
  (tracked-but-must-be-ignored, unignored runtime/backups, machine-specific content, mixed groups); the
  default `maind doctor` prints a one-line summary. `core.gitignore_policy` is the shared checker.

### Changed

- **Task lean execution:** execution is gated per phase (target phase/item detailed); a
  whole-plan design finish and GREEN design audit are opt-in via `**Design Audit:** required`.
  A stronger model/effort than declared is recorded as `over`, never a stop. Models resolve
  through one provider pool (`model_inventory`: overlapping roles, `aliases`/`patterns`,
  `status: retired`, highest class wins); an unlisted model is nonterminal
  `ROUTE_MODEL_UNKNOWN` that fails closed (no cli-config fallback for an explicit Cursor `--model`). An unstarted workset remainder no longer forbids a final
  (`TASK_WORKSET_REMAINING`); an open run still does. Canon: review is plan shape (read-only
  `Review Pn` item, Review defaults to `none`), broad suites run once per phase, bulk output
  stays in files. `task-development-philosophy` 0.3.0.
- **Task evidence freshness:** a validation receipt stays current across an ordinary commit
  (`head` is provenance; the product `tree` decides) and across sessions/providers (the
  environment identity is interpreter family, major.minor and OS family, no patch/kernel/path).
- **Task continuity:** an owner-requested new session or pause saves its checkpoint and prompt
  without a route/batch/capability attestation of the current executor (recorded as
  `transfer:manual-unattested`); an ordinary continuation still fails closed.

### Added

- **Task owner design-audit waiver:** a selected accepted owner decision can
  admit its exact finished design fingerprint without a repeated whole-plan
  audit. Provenance, scope and stale-design checks remain strict; item acceptance
  and recorded current non-GREEN audit gates are preserved. No audit GREEN is
  fabricated.

### Fixed

- **Task phase fingerprints:** nested brace alternatives in declared `Files`
  resolve to their tracked members, retaining expansion limits and path guards.
- **Task Validation bullets:** compile each top-level bullet as its own evidence
  carrier so an external bookkeeping command does not hide repository acceptance.
  Public checks still require current successful validation receipts.
- **Task immutable phase design:** a fresh generated layout-v2 phase closure
  supplies terminal handoff evidence without editing the audited phase context;
  missing or stale closure evidence still fails the gate.
- **Task waiting delivery:** an escalated or blocked item may resume itself after
  its explicit waiting gate; completed GREEN items still reject replay recommendations.
- **Task evidence parsing:** leading PHP namespace segments such as `\\Internal\\`
  in prose deliverables no longer prevent plan execution; standalone file declarations
  continue to reject backslashes.

## [0.25.2] - 2026-09-28

### Fixed

- **Task completed repeat projection:** later plan authoring no longer prevents
  status/finish views from reading an already completed repeat. Historical reads
  authenticate the original pre-start finish/GREEN and consumed owner grant;
  new execution and unfinished resumes still require current design admission.

## [0.25.1] - 2026-09-28

### Fixed

- **Task independent repeat status:** phase boards preserve authenticated historical
  phase outcomes while item tables expose the current repeat attempt. Revoked
  grants fail closed; no design carrier rewrite or lint exception is needed.
- **Task legacy journal lint:** keep the owning D22 missing-journal severity;
  execution recovery still rejects unavailable authoritative positions.

## [0.25.0] - 2026-09-28

### Added

- **Task independent repeats:** owner-bound `repeat-admission/v1` admits a new solo
  run for a terminal item, preserves historical outcomes, and retains current
  design/route/authority/input gates. Repeat delivery validates its grant and
  siblings without reclosing the historical phase. Ungranted, stale, foreign,
  revoked and consumed grants fail closed.

## [0.24.11] - 2026-09-28

### Fixed

- **Task plugin cache revision:** task publication version tracks the umbrella release
  again; Codex/Claude cache keys advance with attested bytes so deleting
  `~/.codex/plugins/cache/swissknifeman/task/*` no longer recreates a misleading
  frozen `0.24.4` slot after post-release task changes.

### Fixed

- **Task file annotations:** PHP namespace prefixes in parenthetical `Files` explanations
  remain prose while paths inside the explanation are still validated; malformed
  standalone declarations still fail admission.
- **Task evidence parsing:** quoted PHP namespaces in prose `Deliverables` are
  treated as identifiers instead of invalid repository paths; `Files` path
  validation remains strict.
- **Task plan validation:** generated blocked-item escalation is read from its state
  carrier; typed waiting continuations use the same continuity validation as delivery,
  including rejection of mismatched handoff metadata.
- **Task batch handoff:** explicit item lists retain their full membership during
  lint validation, using the same request grammar as batch admission.

## [0.24.10] - 2026-09-27

### Fixed

- **Fleet delivery:** prune stale Claude/Codex plugin cache versions after attested release.

## [0.24.9] - 2026-09-26

### Fixed

- **Claude legacy cache:** closed obsolete cleanup cache-copies after delivery; current release tree can now be validated without a saved legacy states.

## [0.24.8] - 2026-09-26

### Fixed

- **mAInd dry-run receipt:** successful planning delegated provisioner no longer
  is marked as an applied change; post-apply `sync --dry-run --json` honestly
  passes fleet idempotence gate.

## [0.24.7] - 2026-09-25

### Added

- **Provider-aware context doctor:** `skiller doctor --context --provider codex` and
  `budget --first-turn --provider codex` now read actual native prompt
  inventory, show managed/observed difference, duplicate names and included outside
  project policy plugins, as well as desired plugins not included in effective state.

### Fixed

- **Codex first-turn receipt:** metering uses `AGENTS.md`, does not assign Codex
  Claude-only agents and SessionStart hooks and returns `INCOMPLETE`, if native
  inventory cannot be verified.
- **Task 0.24.3:** repair digest-bound batch receipts, clarifications plan gates/work and
  journal migration; rebuilt provider projections and publication locks.

### Changed

- **skiller 0.17.14:** provider-aware `--context` diagnostics and Codex-native inventory in
  `budget`/`doctor` unchanged Claude default JSON contract.

## [0.24.6] - 2026-09-23

### Fixed

- **mAInd ownership:** `maind sync` keeps thin root-bootstrap projections
  `ecosystem-mcp` and `ecosystem-setup`, owned by `skiller registry`; doctor not
  reports these files as template drift maind.

## [0.24.5] - 2026-09-23

### Changed

- **Start route:** a short tutorial takes you from installation to the first task and shows you how to
  when direct editing is enough, and when to include it explicitly Task. README and the site leads to this
  route instead of a long runbook Claude Code; intro README now reflects support
  three clients and optional Task.
- **Limits of evidence:** `docs/status.md` links the main risks to inspections and directly
  marks the limits of local lock, Task receipt, release delivery and file name scanning.
- **Delivery:** `CONTRIBUTING.md` distinguishes Git-tag, attestation, local delivery and separately
  published GitHub Release.

### Fixed

- **Provider documentation:** generator escapes angle brackets in fields evidence, to
  paths like `<session>` did not break the assembly VitePress.
- **Providers Contract:** approved hashes and number capabilities in tests are synchronized
  with checked manifest from current HEAD; CI checks all 37 possibilities again.
- **Local provider lock:** inter-process test checks the expectation of a competing writer and
  release `flock` after `SIGKILL` holder-process.

## [0.24.4] - 2026-09-23

### Fixed

- **mAInd fleet readback:** `maind sync --json` keeps provisioner and subprocess diagnostics
  on stderr, leaving stdout as one parseable JSON document for release-fleet idempotence checks.

## [0.24.3] - 2026-09-23

### Changed

- **mAInd memory economy and isolation:** project recall is private by default; graph and memory
  namespaces are separate; onboarding defaults to explicit `MODE=manual`; SessionStart health,
  digest and SessionEnd feature logging are opt-in; normal health is read-only with `--deep` for
  round-trip verification. Durable `active-handoff` writes replace their previous slot, while
  checkpoint-style journal keys are rejected. Code graph can now be limited per provider.
- **Task design gate:** a plan must finish all detailed phases and pass one current GREEN design
  audit before execution. Local design returns its own diagnostics while summarizing foreign
  errors; `Next` does not materialize successor bundles. A design dossier remains optional, but a
  started dossier must be complete and is bound into the audit fingerprint.
- **Skiller protocol and memory guidance:** the `general` plan protocol and `system` shared-memory
  skill now document the design gate, semantic batch routing, manual memory mode and explicit
  shared-scope permission.

### Fixed

- **Task routing and provider projections:** final design validates one provider-neutral
  execution-sheet row per batch, admission applies the batch's maximum semantic route, and Cursor
  route evidence recognizes the `grok-4.6` `effort` alias.

## [0.24.2] - 2026-09-22

### Fixed

- **Codex fleet delivery:** registered local `swissknifeman` marketplace is reused only
  after its Git origin and checked-out commit match the tagged release. This lets every
  registered project update from the current attested checkout without replacing an
  unrelated source.

- **Codex consumer acceptance:** the native gate verifies marketplace inventory, enabled
  installation, exact version and byte-exact isolated cache surfaces through supported
  CLI contracts instead of the internal `debug prompt-input` rendering.

## [0.24.1] - 2026-09-22

### Added

- **release-fleet workflow:** single local command validates tag and attestation,
  delivers release to all active projects, deletes only confirmed ones
  unreferenced provider caches and checks again dry-run for idempotency.

### Fixed

- **Task productivity audit:** normal plan execution reuses recovery admission without a
  second prepare or snapshot; no generated carrier is mutated before admission; terminal
  reconciliation is incremental; review and plan-run carriers are shorter; missing Phase
  Assurance uses the isolated/reversible default; `risk_tags` remain extensible; final
  rendering is exact only when required; and the PR Python matrix covers the oldest,
  midpoint and newest supported runtimes. Deferred disputed continuations are tracked outside the repository.
- **release version integrity:** attestation now checks independently expected unit
  version with package/plugin/publication/provider surfaces and includes Claude-only
  units; circular snapshot consistency no longer hides the outdated version.
- **Task/maind/analyst publication versions:** Task aligned to `0.24.0`, maind on
  `0.4.4`, analyst on `0.2.3`, and modified skiller released as `0.17.11`;
  lock-files and generated provider projections
  regenerated from owning sources.
- **fleet migration:** three-provider contract applies to all active
  projects; cleanup detects legacy Claude manifest even after the shift provider
  path, a doctor no longer skips managed drift and selected plugins.
- **maind sync exit status:** JSON-mode returns an error when non-green lines,
  therefore automation cannot accept partially applied fleet sync for success.

## [0.24.0] - 2026-09-22

### Fixed

- **Task 0.21.0 / harness 0.5.6: explicit opt-in and economical workflow.** Removed
  SessionStart STOP-GATE and keyword-routing Task; Codex skills disable implicit
  call, Claude commands use `disable-model-invocation`, Cursor router became
  manual. Root projections remain compact after regeneration.
  Design respects the owner's budget, does not require a new session upon completion;
  `plan-work.py` combines compact context retrieval and service completion.
  Local finite grants are explicitly separated as `owner-session` from `provider-proof`;
  absence strict provider capability is diagnosed before repeated owner prompts.
  

- **task public recovery reasons.** Task Contract JSON preserves the exact internal
  diagnostics and adds stable `reason_codes` with eight recovery-categories;
  existing `pre_mutation`/`pre_final` and exit-status remain compatible.
- **task bundle privacy/portability boundary.** `BundleInputPolicy/v1` now
  prohibits caller-owned weakening minimization/sensitive classes; bundle members
  pass platform-neutral lexical classification, no-follow containment and
  regular-file checks, and external/invalid execution inputs are saved until
  typed portability verdict instead of silent discarding.
- **task journal/projection durability.** Terminal journal writes now
  serialized, refuse corrupt history and terminal-before-start,
  a typed historical exceptions are bound to accepted/current D#; timestamps,
  metrics and decision dates are strictly validated, projection writes added
  no-follow, process lock and `fsync(file) → replace → fsync(directory)`.
- **task owner-authority boundary.** Local Codex/Claude transcript carriers now
  honestly remain `workflow-guard` and do not activate protected owner-gate; exact
  `provider-attestation/v1` requires provider-owned verifier/nonce channel. Enforced
  authority uses durable process-safe replay/commitment store and fail-closed
  requires approval, no real yet analyzer for observed-action facts.
- **task:** added owner-gated migration legacy `journal.jsonl` to the current schema without
  rewriting history; Codex route evidence accepts semantically identical strings
  `task:…` and `$ task:…`; before one-time use owner-response now first
  is validated continuation, is therefore erroneous fallback does not consume the response.
- **Cursor lifecycle fail-closed verdict.** Generated `lifecycle.py` always writes
  JSON `permission=allow|deny` for `beforeShellExecution` and `preToolUse`: allow-path,
  empty/broken stdin and incomplete payload no longer blocks Shell/Write due to empty
  stdout, a policy deny is returned structured verdict with exit 0.

## [0.23.0] - 2026-09-21

### Added

- **Telemetry codegraph:** run-report (Claude + Cursor + Codex) writes block `codegraph`;
  `preToolUse` sidecar on Cursor/Codex; Codex parses `transcript_path` via run-report
  `_lib.py`; `harness hooks --provider codex|cursor` rolls out observability-surfaces;
  `maind doctor --audit mcp` — `[fleet] codegraph-usage`.
- **maind:** `mcp_runtime` — host-audit of duplicates Serena and heavy LSP (>500 MB) in
  `maind doctor --audit mcp`.
- **maind:** `mcp_parity` — discrepancy audit MCP between `.mcp.json`, `.cursor/mcp.json`,
  `.codex/config.toml` and duplicates in `.claude/settings*.json`; `maind sync --only mcp`
  cleans settings-duplicates and when `auto` escalates to repair; `extra_servers` are saved
  in `mark_deployed`.

### Changed

- **task:** cut out transitional legacy layout v1→v2 (migration admission hold, phase-citation alias, §3 `Model/effort` back-compat, dual freshness in item-state); dead links to runbook migration to docs.
- **Root skill hub:** `generate-hub` / `skiller connect --hub` by default writes to `CLAUDE.md` and `AGENTS.md` only comment-stub (without priorities and index); full block - `--full-index`, former short form - `--hub-legacy-short`.
- **Codex root instructions:** `project_common: false` — `root.*` common does not map to root `AGENTS.md` (on-demand through packages, skills and task-commands).
- **Root instructions (rationalization P5):** `CLAUDE.md` does not hold full `root.*` dump; first-turn `claude_md` budget on umbrella checkout decreases (~2653→~757 tokens by `skiller budget --first-turn`).
- **Fleet codegraph:** Laravel-projects translated to `laravel-boost` (php artisan boost:mcp)
  instead Serena/Intelephense; `code: false` on umbrella/agentools/perplexity-web-mcp;
  `pre_index: false` default; `.serena/project.yml` narrowed ignores/workspace on
  heavy PHP/monorepo.

### Fixed

- **task:** Codex route evidence recognizes `gpt-6-astra` like frontier when explicitly selected;
  default route remains `gpt-5.6-sol`.

- **task:** Codex route-evidence bootstrap now adds general `core/` in `PYTHONPATH`,
  therefore plan-commands do not crash with `ModuleNotFoundError` outside the monorepository swissknifeman.
- **maind:** `perplexity-web` now renders the configured `start.sh` as direct
  MCP-command: Codex no longer attempts to execute literal shell-substitution
  `${PERPLEXITY_WEB_MCP_BIN:-…}`.
- **sibintek-insiders:** `figma`, `laravel-boost` and `perplexity` are declared in hub
  `extra_servers` / `perplexity_web` — all aligned provider-targets.

## [0.22.2] - 2026-09-18

### Fixed

- **harness:** removed official Perplexity API MCP (`@perplexity-ai/mcp-server`,
  `PERPLEXITY_API_KEY`) from the catalog and bindings — research only through hub-managed
  `perplexity-web-mcp` (maind deploy).
- **maind:** `provider_deploy` inserts correctly `mcp_servers` in bootstrap
  `.codex/config.toml` (single trailing `\n` no longer breaks P2 round-trip);
  `sync` limits umbrella-instructions consumer-projects; audit takes into account
  `core@` marketplace and list-format `skills-lock.json`.
- **skiller:** `prune_orphan_managed_lock` / `retire_orphan_codex_physical_skills`;
  `connect --cleanup-codex-physical` for legacy `.agents/skills`; channel hygiene in
  status/update.

### Changed

- **Ecosystem:** fleet `providers.defaults` includes `cursor` (along with claude-code and
  codex); `maind sync` rolls out `.cursor/mcp.json` for all projects.

## [0.22.1] - 2026-09-18

### Fixed

- **skiller (0.17.7): channel hygiene for legacy raw vendor.** `status` no longer
  marks maind-managed `ecosystem-mcp`/`ecosystem-setup` like `name_duplicates`
  (they are updated via `maind sync`, not `skiller update`). `connect
  --cleanup-vendored` now removes raw symlinks/copies to `.claude/skills`, whose
  names overlap active ones marketplace-buckets (migration connect+vendor, repo fact
  insiders/flexcrm). `doctor --downstream` warns about broken symlinks in
  `.cursor/skills`.

## [0.22.0] - 2026-09-18

### Fixed

- **Cursor lifecycle hooks.** `harness hooks --provider cursor --safe-dirs` now
  renders correctly `.cursor/hooks.json` (`version: 1`, flat entries) and
  publishes `.cursor/hooks/lifecycle.py` via provider-artifact lock with saving
  user entries and deterministic iterative render.
- **Cursor safe-dirs handler contract.** The generated handler no longer requires
  `session_id` for `beforeShellExecution`, uses `conversation_id` + event fields
  and takes `cwd` via fallback (`payload.cwd` → `CURSOR_PROJECT_DIR` → `workspace_roots[0]`).
- **P0 conformance evidence.** Added fixture real Cursor wire payload and tests
  `packages/harness/tests/test_cursor_hook_render.py` (for `afterShellExecution` and
  `beforeShellExecution`); updated evidence-entry `security.safe-dirs` for `cursor`
  in `configs/provider-capabilities.json`.
- **Release attestation blockers.** Closed `RELEASE_IMMUTABLE_TUPLE` for `harness`
  (`packages/harness/package.json` 0.5.3), `core` (`publication-versions` 0.19.3),
  `package.analyst` (`packages/analyst/package.json` 0.2.3) and `package.skiller`
  (`packages/skiller/package.json` 0.17.6), and `CMD_SOURCE_DRIFT` for `task`
  (canon-forward `0.20.3` + regeneration provider-commands via
  `render-provider-commands.py --write --repair-owned`).
- **Cursor rules and command projections under `--check`.** `cursor_render` reads bodies
  `root.cursor.*` directly from the instructions directory, generator added
  `packages/harness/scripts/render-cursor-rules.py` and the verification step in
  `packages/harness/scripts/validate.sh`; `packages/task/scripts/validate.sh`
  now includes `render-provider-commands.py --check`.
- **Cursor doctor P1 (single-writer + dedup).** `harness doctor --settings --provider cursor`
  checks for intersections semantic surfaces between `.cursor/hooks.json` and Claude-compat
  hooks, catches repeated identical registrations (including D6) and marks compat-path
  as unmanaged binding, depending on user-toggle third-party configs.
- **Cursor lifecycle P2 (cheap adapted surfaces).** For Cursor raised
  `agent-packs.lifecycle`, `agents.catalog`, `command.workflow-carrier`,
  `context.observer`, `lifecycle.router`: roles go as consumer-mapping on
  `.claude/agents/*.md` (`projection_owner=claude-code`, without `.cursor/agents`), observer/router
  are published static `.mdc` (`alwaysApply: true`) without depending on
  `sessionStart.additional_context`, `task:make-workflow` is included in Cursor command projection, a
  `unsupported`-lines now have an explicit taxonomy of causes (`not implemented` / `API-capped` /
  `not applicable`) in generated provider docs.
- **Cursor lifecycle P3 (observability + analytics).** `lifecycle.command-log` and
  `lifecycle.run-report` translated to hook-native for Cursor:
  `afterShellExecution` writes only digest/class/duration/sandbox/outcome
  (without `payload.output`), `sessionEnd` saves the original `reason` with neutral
  `outcome` and correlation by `conversation_id`; in `packages/analyst` added
  `CursorCaptureReader` (`("cursor", 1)`) and e2e-path `envelope -> neutral_run_report`.
- **fix(harness): Cursor lifecycle P4 policy cores + adapters.** General issued
  core-contract (`id/pattern/reason/tier` + clean `verdict` with ladder
  `off|warn|strict`) in `lifecycle_policy_core.py`, added policy cores for
  `daemon-safety`, `git-guardrails`, `changelog-gate`, `pack-guard`; Codex/Cursor
  adapters in `hooks.py` translated to core verdict, a Cursor bindings/capabilities
  updated to `hook-native` / `adapted`.
- **test(harness): discrepancy detector core ↔ Claude lifecycle hooks.** Added
  `test_lifecycle_policy_core_alignment.py` (without rewriting bash-hooks Claude),
  plus Cursor/Codex regression tests for mode ladder, fail-closed behavior, kill-switch
  and false-positive pinning for all four policies P4.
- **Cursor lifecycle P5 review-gate.** `lifecycle.review-gate` for Cursor translated to
  `hook-native` on `subagentStop`: is enabled only after `.cursor/review-gate.env.ini`,
  takes into account `loop_count` from payload (without its own counter), returns
  `followup_message` only when `status=completed`, does not repeat the same followup
  twice in a row and skips continuation when found Claude-compat registration
  (single-writer dedup P1).
- **Cursor lifecycle P5 terminal-admission.** `lifecycle.terminal-admission` for Cursor
  translated to `hook-native` on `stop`: reuses `task.terminal_admission`
  (`validate_contracts` + `pre_final_open_runs`) and contract
  `terminal-admission-lease-v1.schema.json`, remains `off` by default, uses
  `loop_count` from payload and stops continuation with constant repeat followup.
- **Cursor lifecycle P5 memory.** `lifecycle.memory` for Cursor raised via `sessionStart`
  with env-activation from `.cursor/memory.env.ini` (`MODE`/`BRAIN`) without token transfer;
  in matrix Cursor reached `8 native / 23 adapted / 5 unsupported`.

## [0.21.5] - 2026-09-17

### Fixed

- **task codex plugin.** `packages/task/.codex-plugin/plugin.json` → `div0.20.2` (skipped when v0.21.4).
- **Cursor MCP runtime.** `.cursor/mcp.json` in `.gitignore` (as root `.mcp.json`); template - `.cursor/mcp.json.example`.

## [0.21.4] - 2026-09-17

### Fixed

- **Deliver readback.** `command-routing.json` and `profile-catalog.json` — regular files
  (not symlink) in package paths; root `configs/` remains SSOT via `shared_config_path`.

## [0.21.3] - 2026-09-17

### Added

- **Provider projection SSOT.** `configs/provider-projection.json` +
  `core.provider.projection` — instruction/route/command dispatch without provider `if/elif`
  in harness/task. Doc: `docs/reference/provider-projection.md`.
- **Shared root configs.** `configs/command-routing.json`, `configs/profile-catalog.json`
  + `core.config_paths.shared_config_path`; legacy package paths — symlinks.

### Fixed

- **D104 bootstrap.** Saves non-`SessionStart` hooks when compose (dterema/brain etc.).

### Changed

- **Provider dispatch refactor.** `instructions.py`, `route_evidence.py`, `command_render.py`
  read projection catalog instead hardcoded cursor/codex/claude branches.

## [0.21.2] - 2026-09-17

### Added

- **Provider distribution SSOT.** `configs/provider-distribution.json` +
  `core.provider.distribution` — connect/vendor/discovery channels without `if cursor` in
  `publication.py`. Doc: `docs/reference/provider-distribution.md`.

### Changed

- **maind fleet:** project `sova` in `config.json`; MCP/instructions adopt on cursor-consumer
  (flexcrm, cms, insiders, sova); D104 lifecycle handler for dterema/brain.

## [0.21.1] - 2026-09-17

### Fixed

- **skiller distribution (Cursor).** `build_connect_distribution_plan()` and
  `build_vendor_distribution_plan()` skip `cursor` — no marketplace/vendor
  channel; without it `skiller update`/`deliver` fell on cursor-enabled projects.
  Package `skiller` 0.17.1 → 0.17.2.

## [0.21.0] - 2026-09-17

### Fixed

- **skiller connect (Cursor).** `build_connect_distribution_plan()` skips `cursor` — no
  marketplace-channel; without it `skiller update`/`deliver` fell on cursor-enabled projects.
  Package `skiller` 0.17.0 → 0.17.1.

## [0.20.0] - 2026-09-17

### Added

- **Cursor third provider.** Release v0.20.0: validate, attest, fleet `maind sync` +
  `skiller deliver`; explicit enable Cursor on self-host and projects with `.cursor/mcp.json`.

- **Cursor third provider.** Documentation: adapter Cursor (install, trusted profile, MCP,
  permissions); generated [Provider model roles](packages/task/docs/reference/provider-model-roles.md)
  (pins design/exec/audit/economy + inventory and ban Auto on fixed frontier); harness
  [setup/cursor](packages/harness/docs/setup/cursor.md); launch-block with table class→selector,
  `agent --workspace` and IDE Run Mode checklist; instruction `root.cursor.launch-and-autonomy` in catalog.

- **Cursor third provider.** Task: `mappings.cursor` + `model_inventory` for all three
  providers; `command_render` (launch via `agent --workspace`, not `-C`); `route_evidence_cursor`
  and generated `packages/task/adapters/cursor/`; parity/reference into three columns. mAInd:
  `provider_deploy` for `.cursor/mcp.json`, `REQUIRED_PROVIDERS` includes `cursor`, health
  `provider:cursor trust` via harness profile resolution. Harness instructions engine:
  `PROVIDERS` + `root.cursor.*`, 21 projection (`.cursor-instructions.mdc` / `.mdc` rules),
  catalog `1.3.0` and compatibility fixture for 87 records.

- **Cursor third provider (P0–P2, cold-start S2).** `ProviderId.CURSOR` and full
  36-lowercase capability matrix (`8 native` / `7 adapted` / `21 unsupported`);
  harness-adapter `packages/harness/configs/cursor/` (profile bindings, MCP,
  permissions/cli render, lifecycle hooks, `.cursor/rules/*.mdc`); conformance
  tests by design-freeze §3.6; skiller `render_cursor_publication` and listing budget
  for `cursor` without dual-write `.agents` + `.cursor`.

## [0.19.0] - 2026-09-16

### Added

- **Task: preparation and terminal reconciliation.** Selected bundle/state is restored to
  five-carrier snapshot; one idempotent operation reduces terminal journal, generated views,
  next frontier bundle and delivery receipt.

### Fixed

- **Task/Harness: continuous workset.** Recommended batch allows current ready frontier with
  empty prefix, a Stop guard sees the balance that has not yet been started receipt. Updated Codex dispatcher
  is delivered via versioned owning adapter and calls `check-open` without special payload.
- **Task: design-time bundle validation.** All nonterminal admission-ready declarations pass
  dry render without mass materialization; unresolvable selected bundle gives the exact typed repair.
- **mAInd: provenance run-report.** Alien project/session/provider report is excluded from verdict and
  becomes `ATTENTION`, not false RED.
- **CoreX plan checker:** execution bookkeeping and generated decision views no longer invalidate
  design seal, and new ones design decisions and changes item contracts still require reseal.

### Changed

- **Task instructions:** required context is divided into common/design/execution/review layers;
  full plan protocol remains on-demand canonical reference.
- **Delivery versions:** Task `0.19.0`, Core `0.18.0`, general `0.14.1`, Skiller API `0.16.1`,
  Harness API `0.4.4` and mAInd API `0.3.3`.

## [0.18.0] - 2026-09-15

### Fixed

- **Task: field errors and execution costs.** Decision template passes native parser,
  terminal append rejects invalid decisions in advance; semicolon reads/Files are recognized,
  empty product anchor does not confirm closure. `only_item` measures only the selected item
  with saving producer admission; history takes everything into account affected `items` solutions.
- **Task/Harness: early final open run.** Enabled Stop-adapters are checked durable
  state of the current session even without Task payload/lease. Verified repository dispatcher both
  providers; field transport acceptance remains a separate step. Conformance-test
  dry-run isolated from version hook in the developer's work environment. Version Harness API `0.4.3`.

### Changed

- **Task: short links without collisions.** Constants Short ID `PLAN<N>`/`TASK<N>` for
  new file plans and tasks; external links qualify decisions and points
  (`PLAN<N>.D35`, `PLAN<N>.P2.3`). Checking duplicate plans takes into account the archive; old ID are saved.
  Skiller no longer generates ambiguous provenance `P1.2, D31` in bootstrap.
  Versions: Skiller API `0.16.0`, Task `0.18.0`, general `0.14.0`.

## [0.17.5] - 2026-09-14

### Fixed

- **Skiller: fail-closed Python 3.10 TOML fallback.** Unsupported tables and
  inline plugin maps now reject native selection before any consumer mutation.

## [0.17.4] - 2026-09-14

### Fixed

- **Skiller: Python 3.10 Codex selection.** Native Codex selection and legacy
  link cleanup use a bounded stdlib TOML reader when `tomllib` is unavailable,
  preserving explicit plugin selection and disabled local skills.

## [0.17.3] - 2026-09-14

### Fixed

- **Release hygiene.** Runtime validation logs are no longer included in the published
  tree; proof of release remains in structured JSON and Markdown
  artifacts.

## [0.17.2] - 2026-09-14

### Fixed

- **Skiller delivery: Codex native cache.** Readback still checks everything
  attested bytes and symlink safety, but no longer counts standard ones package files and
  provider-generated cache state unknown drift.

## [0.17.1] - 2026-09-14

### Fixed

- **Skiller delivery: secrets consumer settings.** Dry-run no longer prints values
  from `env` and sensitive fields of the existing `.claude/settings*.json`; project entry
  continues to use the original bytes without modification.

## [0.17.0] - 2026-09-14

### Added

- **Skiller: explicit native Codex selection.** `skiller connect --native-codex` writes
  accurate project-level selection Swissknifeman plugins, without changing permissions, third-party TOML-fields
  or global defaults; with `--hub` AGENTS is built on this set.

### Fixed

- **Skiller: start context Codex.** Brief AGENTS hub takes into account the real Codex
  discovery and does not return Claude-only extras. CORE reduced to four general skills,
  66 profile descriptions shortened;
  VueUse-directory moved to reference. Managed duplicates and explicitly disabled links
  are archived with verification ownership and equivalence; strangers backups are saved.
- **Task: result and continuation.** General resolver accepts `plan-run` with saving
  owner route; renderer distinguishes the completion of the ordered scope in chat and explicitly requested
  new session. Removed clean-tree and repeated interview gates; Task runtime contains
  all templates and references. Native Codex no longer spawns three migrated command duplicates.
- **Skills: proportionate rules.** TDD, review, package contribution and PHP architecture
  take into account the authorization and accepted contracts of the project; universal advice does not become
  additional blockers. mAInd setup/MCP descriptions are shortened without changing the instructions.
- **Publication: deleted artifacts.** Registry removes unmodified retired files by
  previous publication lock; release attestation correctly takes into account working-tree deletions.
- **Task: continuous performance and precise Next.** `continue-root` continues compatible ready
  batch in the current root without final, owner question or fresh session; native launch-block remains
  only for valid cold-start/wait boundaries. Automatic handoff fails
  repeated `plan-design`, when the existing phase is already detailed and ready for `plan-exec`.
- **Skiller / core: local repair without unnecessary design or restart.** `anti-drift`
  uses checkpoint and changing tactics when correction is delayed; the number of files itself
  does not itself require a plan. `plan-protocol` consistent with continuous execution Task;
  native handoff is stored for a confirmed context boundary, capability or waiting.
- **Skiller connect:** dry-run replacements Codex-set checks post-prune snapshot instead
  old lock; are checked before deletion digests all the previous ones owned artifacts. Changed
  preimages rejected before recording, strangers owner records are saved.

- **Task: unresolved execution binding.** An item containing an explicit
  `[NEEDS CLARIFICATION: …]` marker can no longer compile as routine authority;
  it must first receive a finite owner gate and binding.
- **Task: Unicode cross-plan inputs.** Bundle/read-path parsing now recognises
  declared paths whose plan IDs contain `№` and does not mistake `D16` in a
  filename for a local decision reference; a valid cross-plan decision can no
  longer disappear as an unresolvable entry before bundle generation.
- **Task: completion batch does not erase the next plan item.** Delivery fails
  `Context: terminal` and `Next: none/terminal`, while there is an unfinished phase; rule
  also applies to recommendation-only receipt. The protocol stores the actual
  successor out of complete batch and native command when a new session is requested.

## [0.16.1] - 2026-09-13

### Fixed

- **Field delivery readback:** separate source-bound `codex-native` surface checks complete native cache, a project bundles — only declared skills. Attestation excludes ignored/untracked telemetry; extension proof coverage is checked against the previous one Git source tag, does not require false bump unchanged units. Orphaned v1 vendor markers are archived only if all declared directories are missing; real remaining vendor-copies remain blocked. Before update is also saved lock preimage.
- **Claude skm cache:** publication version aligned with updated Codex unit, to old same-version cache was not presented as current runtime.

## [0.16.0] - 2026-09-13

### Added

- **Release-to-runtime:** `skiller attest` forms deterministic version/tree/file digests for both providers and package runtimes; tag gate rejects modified bytes under the previous one unit version. `version --json` shows umbrella and independent units. `skiller deliver --release ... --all` explicitly updates projects/native caches, restores ownership known only preimages and saves durable per-target receipt with digest readback and `restart-required`.

### Fixed

- **Task opt-in:** current owner intent defines a route; dev/fix work directly without a mandatory plan, audit/close/handoff lifecycle. Old embedded instructions do not override the new owner selection.
- **Task recovery:** successor to terminal predecessor gets `OUT_OF_ORDER_REQUEST` with active item and start/resume; start fixed durable to product write, resume saves run identity, terminal producer only materializes the next one ready bundle.
- **Task authority/calendar:** explicit finite Authority gate passes lint/compiler/bundle; grant materializes from the current provider-attested owner invocation. The review is checked again before start/resume; `waiting-external` saves observation checkpoint, date/predicate and continuation without new owner questionnaire.
- **Ownership and cache:** general lock atomically replaces only records of his owner; alternating/concurrent writers save other people's records and refuse when collision. Installed verification only accepts exact known Codex migration bytes and rejects mutation, unknown extras and symlinks. Fixed baseline snapshots already published terminal-admission capability.

### Documentation

- **Release-to-runtime roadmap.** Confirmed reasons recorded version/cache/fleet drift: reuse unit versions for new bytes, loss ownership in multi-writer lock, gap native cache/project/session and absence durable partial-delivery receipt; described as safe reconciliation and the remediation steps being verified.

## [0.15.4] - 2026-09-12

### Fixed

- **Codex plugins `task` and `core`:** versions are aligned with umbrella-release
  0.15.4; buggy intermediate target 0.14.0 is no longer published or
  is set for new sessions.

## [0.15.3] - 2026-09-12

### Changed

- **Codex plugins `task` and `core`:** released line 0.14.0 from
  current provider-projections; settings 0.13.x are no longer valid
  target for new sessions.

## [0.15.2] - 2026-09-11

### Fixed

- **Task: completion without unnecessary stuff audit.** Green phase closes direct-close regardless legacy `Audit Intent` and numbers items; additional phase audit requires a residual question and targeted consent tied to candidate/run. New audit runs check consent through existing decisions/journal. RED and incomplete acceptance remain owning repair.
- **Task: completion-first and saving checks.** Delivery rejects handoff to restart/close current item and requires a valid phase closure to be completed in the same session. Commands, canon and templates have been agreed upon: review by risk, current validation is reused, bookkeeping itself does not run a product check again.

## [0.15.1] - 2026-09-10

### Changed

- **Task lifecycle:** usual cross-module development according to a brief without a mandatory plan; read-only audit returns the product defect to the performer via journal/lint/delivery, keeping the phase open. Audit budget no longer prohibits repairs; product delta and the number of files themselves do not require design. New recommended batches allow ready subset, historical mandatory groups preserve the contract.
- **Checks and instructions:** one scoped commit by default, scoped plan validation separate from fleet; targeted context and research without mandatory restarts. Added read-only preparation snapshot and diagnostics of the selected installed Task/core-projections; terminal delivery checks freshness state, regeneration does not overwrite unchanged files. Analyst help shows workflow-scan.
- **`skiller`:** explicitly called `general/implement` no longer forces a full run or an additional code review; validation and review are selected according to the risk specified scope or PR-process.

## [0.15.0] - 2026-09-10

- **`skiller`: lifecycle-aware Laravel parallel isolation.** `test-isolation-guard` now keeps
  canonical serial DB protection at app boot and requires the framework callback’s exact worker
  DB/token before migration; writable parallel disks are local, contained per-process roots and
  fail closed with `FRAMEWORK_LIFECYCLE_CONFLICT` on unavailable lifecycle evidence.

- **`analyst`: workflow fleet evidence.** New read-only `workflow-scan` limited declared
  plan roots enabled-projects, digest-deduplicates mirrors, statically extracts features without
  execution JavaScript and publishes a reproducible `workflow-fleet-report/v1`; changes Task
  remain only report-backed and require Rule of Three according to different plan identities.

- **`skiller`: description-trigger debt queue.** `bucket-audit --description-debt` now emits the
  additive `description-trigger-priority/v1` contract with exact ratchet membership, tier-0 listing
  share, direct-call/resident/unobserved evidence, deterministic ordering, and fail-closed ledger
  diagnostics; it never rewrites canonical skills or turns missing telemetry into a usage verdict.

- **`harness` / `task`: opt-in terminal-admission Stop adapters.** Codex and Claude Code
  lifecycle bindings now delegate applicable, trusted Stop attempts to the P4.1 Task reducer;
  inactive hooks and absent leases remain no-ops, while provider limits stay explicit.

- **`task`: lease-bound terminal admission.** New provider-neutral reducer and worktree-local CLI
  bind terminal response to run/session identity, P1.3 typed continuity, fresh delivery
  receipt and accurate machine-authored fragment. Leases monotonic and expiring; append-only events
  retain only hashes and stable recovery diagnostics. Provider Stop payload translation remains P4.2.

- Fixed: `task:plan-audit` no longer forces a compatible continuation to a new session; context chooses one evidence-based reducer.

- **`task`: evidence anchors prevent self-invalidating plan closure.** New derived
  `evidence-graph/v1` detects intersection declared `Files` and digest inputs to journal/product
  mutation, shares product/closure anchor only in case of real collision, saves
  byte-identity product paths and excludes registry-owned volatile bookkeeping from material
  candidate without explicit Deliverable. `audit-finalization/v1` commits rebuilt candidate and exact
  close admission before GREEN audit.

- **`task`: single executable Routing compiler.** `Task Contract`, batch admission,
  phase audit/close and lint now consume one exact six-column Routing table; adjacent
  provider mapping-tables do not change Review coverage, a duplicate executable table or item
  refuse until mutation.

- **`task`: proportional phase assurance.** New `Phase Assurance | v1` and single
  `plan_assurance` reducer separated semantic phase risk from Routing Review and numbers items;
  phase audit subject is canonicalized, and post-GREEN diff gets field-level
  `audit-impact/v1` continuation instead bare stale/full fallback.

- **`task`: compact normal-path lifecycle.** Canonical plan-commands now delegate
  admission, risk-based validation, selective projection, continuity and delivery general
  runtime owners; normal low-risk item selects focused check, one commit and one semantic Next,
  a hard-risk boundaries are deterministically expanded validation/review.

- **`task`: explicit readiness producer.** Closed `producer-readiness/v1`,
  `phase-reentry-justification/v1` and `fix-branch/v1` now pass alone correction reducer:
  accepted-empty and digest-bound downstream are checked end-to-end, priority fix linked
  to declared target, a lint/delivery prohibit unreasonable re-entry terminal phase.
  Terminal close also requires green rerun exact original carrier after qualified repair.

- **`task`: repo-local archive does not depend on Brain.** Archive no longer searches or calls
  Brain; synchronization Brain remains separate opt-in docs-operation.

- **`task`: repairable carrier drift stays in the active execution batch.** `plan-exec` now
  permits a smallest scope-preserving carrier/reference repair and reruns the original check;
  `plan-run` inherits that one classifier, reserving redesign for actual frozen, public or
  authority-boundary changes.

- **`task`: single continue-first repair reducer.** Closed `repair-decision/v1` links
  original carrier, clean baseline/candidate delta, path attribution, bounded diff, material surface
  and pre/post validation; qualified repair cannot false terminalize or spawn redesign,
  a block confirmation consumes digest this evidence without reclassification.

- **`task`: continuation decisions keep compatible work in the current root session.** A small
  provider-neutral reducer now consumes versioned route/capability, context-health, remaining-batch,
  loaded-input and lifecycle evidence; cold starts require one canonical hard boundary and durable
  checkpoint. Renderer, DecisionRequest recovery, handoff delivery and live plan lint validate the
  same typed decision while preserving owner-wait, same-root resume and isolated-review outcomes.

- **`task`: Routing Batch is now pre-mutation authority.** One compiler derives batch membership,
  maximum route/review and digest-bound suffix receipts from `plan.md`; partial, ambiguous and stale
  executions are refused before journal or status mutation.

- **`task`: content-addressed five-carrier executor context.** Plan execution now captures immutable
  v2 inputs before analysis, proves byte-cursor completion with terminal markers, and refuses
  truncation or source drift before journal mutation; the generated history pointer now includes
  its required `--plan-dir` argument. Rootless v2 plans consume the frozen Task read-budget
  contract, while legacy plan-local contracts remain fail-closed.

- **`skiller`: Codex consumer acceptance supports skill-root aliases.** The live publication gate
  resolves current `rN/path` references through the emitted Skill roots table before checking
  cache and repository provenance.

## [0.14.0] - 2026-08-17

- **`task`: owner-gated terminal blocked phase close.** An explicit, phase-scoped accepted D# can
  record a terminal phase as `🟠 Done with deviations` while preserving its blocked item history,
  RED audits, and release disposition; without that carrier phase close remains fail-closed.

- **Documentation of operations provider/locale and release-candidate.** Added compact borders
  check-first/apply-with-authority/rollback, independent surfaces locale and exact provenance
  RFC 5646, IANA Registry and HashiCorp. Current P7 candidate explicit non-releasable: D88 blockers
  are not masked and do not provide rights to tag/push/publish.

- **`core` / `skiller` / `harness` / `maind`: added provider-health v1.**
  Clean exact-set evaluator does not allow green provider/project hide missing, stale,
  unsupported or unresolved peer; Skiller publishes dependency closure and typed
  provider-qualified measurements, Harness — independent settings audit Claude Code/Codex, a
  `maind projects health` collects redacted evidence only through public package CLI without repair.

- **`core` / `harness` / `maind`: compacted internal source prose for field testing.**
  The P4.5 working cut translates 139 implementation files without changing provider settings,
  consumer files, credentials, or runtime contracts.

- **`core` / `skiller`: added evidence-admitted locale corpus gate.**
  Single JSON ledger and stdlib-only validator check English source ownership, independent
  EN/RU reviews, immutable tokens, preimages, rollback and bounded checkpoints; new
  `check-locale-corpus.py` and `check-translations.sh --strict` refuse generated, foreign,
  stale and ambiguous lines before recording. Canonical Skill template now EN-only and generates
  byte-stable distribution copy.

- **`core`: added general stdlib-only runtime localization.**
  Pinned IANA registry allows independent `response`/`plan`/`diagnostics` contexts,
  fail-closed BCP 47 canonicalization and sparse Russian overlay with protection machine literals;
  Harness and Task get one semantic context, saving provider-owned rendering.

- **`task`: phase-close accepts legacy subject audit-phases.**
  Gate normalizes `P1 — phase mode` via general `review_policy.phase_audit_subject`, therefore
  matching GREEN audit with the same candidate fingerprint is no longer incorrectly reported as missing.

- **`task`: launch-teams became provider-native and safe to copy.**
  Metadata-table no longer contains the command: Claude Code and Codex output only native-form
  active adapter separately fenced-block. Codex additionally prohibits completion handoff without
  commands if there is an executable Next; long shell-commands use explicit `\`.

- **`task` / `skiller`: internal development philosophy has become mandatory plan-authoring context.**
  New root-bootstrap skill `task-development-philosophy` fixes the proportional
  decomposition, evidence reuse, one full audit on material baseline, delta/gate-rebind for
  repeat passes and prohibit endless audit/repair loops; it is available to both provider roots and
  fires when creating plans and changing Task workflow policy.

- **`roadmap`: measured the cost of repeated full-audits and an economical mode is designed.**
  Field P0 reached the third full audit and repeated at least 2,557 package tests; new spec
  enters digest-bound Validation receipts, modes `full|delta|gate-rebind`, strict grounds for
  second full and owner gate for the third one.

- **`task`: audit-repair rebinds terminal evidence to the current technical specification.**
  Append-only history remains the same terminal-entries, but `plan-lint` checks digest
  current spec only with the last one execution event; `plan-audit` and `plan-close` pass
  the same fail-closed terminal policy, what `plan-exec` and `plan-run`.

- **`task`: active/archive mirror of one Plan ID is no longer considered new wave.**
  `plan-lint` does not require `supersedes` for temporary postarchive-copies of the same plan, keeping
  check for duplicates ordinal and matching codenames for truly different plans.

- **`task` / `plan-protocol`: terminal outcome now follows a single acceptance/reducer contract.**
  Red mandatory Validation leaves item in progress; `closed-deviations` requires green
  carriers and `repair_exhausted`, a `blocked`/phase RED are only allowed after authority/safety
  reducer evidence. Scope-aware block gate does not accept wide in-scope inventory abroad.

- **`task`: `plan-run` received provider-neutral route provenance and durable run receipt.**
  Claude Code session JSONL and Codex adapter are projected into one record; unknown is separated from
  real undershoot. Receipt links route with run/session and checked again pre-final.
  Installed canonical command resolves package-relative, a delivery receipt certifies version,
  command digest and exact terminal subject.

- **`task`: local Validation prerequisites repair-forward to terminal close.**
  `validation-admission/v1` recognizes proven missing literal Make target like
  nonterminal local repair; material-only phase fingerprint excludes audit-owned bookkeeping,
  saving stale on the modified terminal evidence.

- **`roadmap`: completed Task-specs have been removed from the active queue.**
  Sources and disposition-map saved in archive plan artifacts
  ; partial records left with exact remainder only.

## [0.13.2] - 2026-08-13

- **`task`: terminal delivery ignores only historical malformed terminal if there is a fresh valid one.**
  Receipt still fail-closed returns `TERMINAL_RUN_ID_MISSING`, if none terminal-entry
  subject does not carry `run_id`, but no longer blocks the corrected one append-only lifecycle with the old line.

## [0.13.1] - 2026-08-13

- **`task`: phase candidate fingerprint only takes into account Git-tracked Files.**
  Exact-files, directories, recursive globs and bounded brace-sets are resolved via
  `git ls-files`; tracked edits/deletions invalidate candidate, a ignored/untracked
  runtime-bytes no longer affect audit freshness.

## [0.13.0] - 2026-08-13

- **`task`: Codex plan runtime transmits one current-thread route record in contract gates.**
  Deprecated `provider-doctor`/`self-attested` recipe no longer remains below the correct value
  provider binding in `plan-exec` and `plan-close`; this eliminates the false `ROUTE_UNDERSHOOT`
  after a new start, `/clear` and direct `$ task:…` call.

- **`task`: all Codex plan-commands check effective route according to current thread state.**
  Generated projections run adapter-owned capture to the first journal-mutations and
  fail-closed prohibit substitution provider-written `turn_context` output `codex doctor`,
  config-file or self-attestation; regression test covers all five plan-commands.
  At the same time lifted return-fingerprint contract accepts all closed journal friction/result enum,
  therefore `local-repair` and other standard observations no longer break return-loop lint.

- **`harness`: test fixtures follow Layout v2 carrier contract.**
  Run-gate, plan-reader, CLI and citation scenarios are building state/status/bundle via canonical
  Task v2 fixture API; separate legacy-rejection cases saved.

- **`task` / `plan-protocol`: lint checks bundle next run item.**
  Plan with missing or outdated fourth execution-slot now rejects to dispatch;
  future predecessor-dependent bundles remain deferred until their input artifact appears.

- **`task` / `plan-protocol`: phase audit became one-root audit-fixer.**
  Fresh independent audit root fixes itself safe in-scope deviations, repeats acceptance
  and binds the final verdict to rebuilt candidate. Proven acceptance/authority/
  safety/public-frozen boundary remains fail-closed, and one candidate allows at most one
  isolated reviewer return; routine `audit → repair-run → second audit` is no longer created.
  Unauthorized `DecisionRequest` remains a non-terminal observation `decision-pending` and not
  replaces live execution position state `blocked`.

- **`task`: owner override phase no longer depends on the number decision.**
  Audit-cap remediation is only allowed for accepted carrier with full exact item-set
  phases and required literals; incomplete scope gets a separate fail-closed refusal.

- **`task` / `plan-protocol`: terminal block passes alone isolated confirmer.**
  Design, exec, run, audit and close now use one closed sequence:
  immutable capsule, distinct fresh-context reviewer and deterministic reducer. External block
  remains nonterminal to verified digest-qualified Perplexity evidence; Codex projections,
  Claude golden fixtures and operator reference rebuilt from canonical sources.

- **`task` / `plan-protocol`: workflow lint now distinguishes between an explicit prohibition and a requirement.**
  Only positive declaration in `Phase Context` requires canonical workflow asset; negation the same
  line does not mask separate `scriptPath` or multi-agent declaration. Codex and Claude
  projections reassembled from the general canon.

- **`task`: external item references are plan-qualified, and provider projections stay synced.**
  Canonical authoring guidance, Codex artifacts, Claude golden surface and the operator reference
  now carry the same `<PLAN-ID> Pn.m` rule; audit-cap recovery grants remain limited to their
  explicitly named Validation items.

- **`task` / `plan-protocol`: executable Layout v1 retired after fleet cutover.**
  Runtime readers, migrator, policy schema and compatibility commands are removed; missing/v1
  plans fail with `PLAN_LAYOUT_V1_RETIRED`. Canonical fixtures and provider projections are v2-only,
  while terminal bundles remain schema-checked historical evidence without live source re-resolution.
  Phase-audit receipts bind the latest persisted audit launch block instead of a stale handoff, and
  canonical Batch-first launch tables are accepted by the same lint gate that publishes them.

- **`task`: fleet v1→v2 migration received frozen admission policy and controlled apply.**
  Closed defect classes, full-tree preimage digests, byte-exact source archive, current-state/
  decision/Routing projection and migration-pending read-budget admission give 15/15 previews without
  plan-lint ERROR; staged apply checks preview and restores preimage when post-write failed.

- **`task`: phase candidate fingerprint takes into account plan-relative product files.**
  Declared `Files` save compatible first repo-relative resolution, are then resolved from
  plan directory; bytes acceptance/RAG carriers are now disabled stale phase audit.

- **`task`: phase handoff and close received a single risk-adaptive audit gate.**
  Low-risk phases are no longer guaranteed to be idle `plan-close`: audit is selected in advance
  by Review, material risk, terminal status and multi-item volume.

- **`task`: Codex `plan-run` checks the current route and then `/clear`.**
  Thread-bound adapter reads model/effort, cwd, Task prompt and safety state from current
  `turn_context`; exact native argv saved as fallback. Changing the model in open CLI-sessions
  no longer requires a restart, and Claude Code projection remains byte-compatible.

- **`task`: downstream gate does not terminal missing future validator item.**
  Unicode-paths numbered plans are read from executable argv; dependency-not-ready now
  gives `unknown`, not false RED producer verdict.

- **`task` / `plan-protocol`: batch/solo is now a required part of the new plan and handoff.**
  Six-column Routing covers every item; scheduler groups connected adjacent items
  single phase while saving reading/setup/validation, a `solo` requires a specific boundary. Linter
  rejects new layout-v2 plan without `Batch`/`Review` and execution handoff, lost Batch.

- **`task` / `plan-protocol`: design no longer triggers execution automatically.**
  Terminal `plan-design` returns only the routed recommendation to the owner; successor
  gets a separate `cold-start-root: design-root-terminal`, a design-root does not call the command and
  will not spawn an artist even for a ready one item.

## [0.12.0] - 2026-08-12

- **`task` / `plan-protocol`: execution has become continue-first.** Route rejection, pending
  decision, local repair and block candidate are now nonterminal journal observations and not
  are consumed attempt. Terminal `Blocked` is only allowed after isolated `JUSTIFIED`; for each
  external candidate is required verified RAG, and small reversible defects are corrected in the current run.

- **`task`: terminal final and handoff linked machine receipt.** New `plan-delivery.py`
  fails on non-terminal/stale state, links journal run ID with digest'ami plan/handoff/state/
  closure and transfers the exact saved next step recommendation into the final response.

- **`task` / `plan-protocol`: new plans have received day numbering.** Canon
  `YYYY.MM.DD-№N-CODE` checks for positive unique ordinal and agreed upon Title `Plan №N`;
  external comments and review findings refer to item like `<PLAN-ID> Pn.m`, old IDs are read.

- **`task`: packaged plan-protocol projection makes standalone `--conflicts` fail closed.**
  Generator-owned runtime carries canonical SHA-256 provenance; a missing or drifted projection
  is rejected instead of searching arbitrary sibling or cache paths.

- **`task`: phase close supports narrow owner-authorized direct-green-validation path.**
  Only accepted, phase-scoped and superseding decision with literal
  `phase-close: direct-green-validation` can bypass audit gate; default audit path and that's it
  mismatches remain fail-closed.

- **`task`: Codex `plan-run` uses verifiable native launch provenance.**
  Fresh launch with `-m` and `model_reasoning_effort` sets the route manual item without unavailable
  provider probe; provenance honestly does not pass off as runtime telemetry. `plan-exec` saves
  strict provider-attested gate. Bundle v2 deduplicates the same path/decision input in one ordinal.

- **`task`/`plan-protocol`: terminal audit is separated from the next run.**
  Ended `plan-audit` is now required to pass successor fresh root with explicitly
  stammered route; selector is no longer allowed to be passed off as self-attested
  actual-route evidence in the absence provider attestation.

- **`task` / `harness`: layout-v2 execution checked with owner-carriers.**
  Task now fail-closed checks phase citations and write-site, a generated command/docs
  surfaces are reproduced in clean checkout; Harness reads semantic `Next`
  only from `handoff.md`, without expanding schema-pure item-state; owner status now shows
  mixture terminal and not-started children like `🟡 In progress`.

- **`task`: phase-audit recovery limited to one additional repair-approach.**
  First non-GREEN audit leads directly to owning item under the unchanged terms of reference; second audit final,
  after it Task Contract blocks the third repair/audit. RED is no longer routed to
  `plan-design` only because terminal status or validation/evidence mismatch.

- **`task`: plan-design evaluates the impact of the conflict before stopping.**
  Local reversible issue being fixed in current item; re-design or owner gate require
  confirmed boundary package/contract/authority/acceptance/safety.

- **`task`: plan-commands received evidence-first runtime-transitions and correlated lifecycle.**
  Routing preflight no longer writes product failure, terminal journal close is idempotent,
  a phase candidate passes fresh audit to close; canonical documentation Task now
  is collected separately and in an aggregated site.

- **`harness`: new SessionEnd run-report's are saved in the root Git-repository.**
  Nested launch cwd remains in the field `cwd`, and outside Git kept the same fallback; historical
  reports are not migrated.

- **`task`: v1→v2 plan migration now saves the full original plan tree.**
  Generator adds `artifacts/migration-source-v1/` with exact bytes of all legacy
  files and SHA-256 manifest; historical audit-sections and free prose are no longer
  may disappear when split into v2 carriers.

## [0.11.1] - 2026-08-10

- **`task`: runtime plan-protocol is no longer dependent on a specific archive plan.**
  Frozen schemas and calibration inputs belong to `packages/task/configs/`; inplace
  v1→v2 migration is permanently decommissioned. Plan checking utilities
  moved from `plans/` in `packages/task/scripts/` with configuration in
  `packages/task/configs/`; provider-projections, hooks and documentation use new paths.

## [0.11.0] - 2026-08-10

- **`task`: downstream-gate only executes explicit commands Validation.**
  Explanatory Markdown without inline-code payload no longer becomes shell-command and not
  fabricates RED; saved legacy bare command prefixes. Fixture terminal-phase input translated
  for fresh closure digest, a P2.10 downstream evidence rechecked green.

- **`task`: freshness item-state isolated by item journal scope.**
  Append events of one item no longer invalidates state views others: digest and `through`
  follow declared `item_id`, and two-item regression saves D148 execution semantics.

- **`task`: exact five-slot acceptance v1.1.1 ended arm-A fail.**
  Repair-pinned measurement saved raw evidence, detected 30/30 ready failures and by
  frozen reducer stopped arm B/session canary; P6.9 and unpausing ARTIFEX are prohibited.

- **`task`: acceptance protocol received repair-pinned v1.1.1 identity.**
  Successor saves threshold/scope/reducer/arms/canary v1.1.0, kicks exact five-slot
  implementation `c0ee730c` and stores v1.0.0 RED along with v1.1.0 NOT-RUN.

- **`task`: `plan-weight` measures declared executor path for both layouts.**
  Layout v1 saves legacy `plan → handoff → phase → Required Reads`; layout v2
  fail-closed checks for fresh bundle/state, believes digest-qualified selections and
  measures five carrier slots without `handoff.md`.

- **`task`: downstream consumer validation protected from recursive self-poisoning.**
  Nested `plan-lint` no longer rereads append-only downstream RED during verification,
  which should supersede; direct lint saves fail-closed behavior.

- **`task`: `acceptance-protocol` re-frozen as stage-aware v1.1.0.**
  After saved RED v1.0.0 reducer distinguishes `ready`, evidence-only
  `historical-pre-v2` and deferred `pending-producer`; threshold, scope traversal, arms and
  session canary remained unchanged.

- **`task`: two-handed technique stopped at fair RED hand A.**
  Migrated exceeded D2(a) (`101744 > 100000`) and saved four
  unresolved input; threshold and frozen protocol have not changed, arm B/session canary are not issued as
  completed, and unpausing ARTIFEX prohibited.

- **`task`: acceptance protocol v1.0.0 frozen until first measurement.**
  `acceptance-protocol` v1.0.0 machine fixes scope, two unmixed hands,
  thresholds, anti-bias, failure policy, roles, confounds and four exact branches
  `session_canary`; post-run edits require visible rheopen.

- **`skiller`/`task`: added rolling inventory and safe runbook layout migrations.**
  For `skiller update --all` fixed adoption inventory, which separates the relevance of the canon
  `plan-protocol` from instance delivery `authority-frame`; inaccessible or outdated declarations
  remain explicitly marked as `unknown`, and are not presented as relevant. Owners also received
  fail-closed procedure dry-run migrations v1→v2.

- **`skiller`/`task`: plan-protocol translated to EN-only compact canon and layout-v2 authoring.**
  Deleted 230 `SKILL.ru.md`, translation gate and RU→EN prompt; canonical `SKILL.md` became
  router on reader-specific reference, received two design-forms Next and three v2 context
  values. New two-threshold D93 weight-gate reduced carrier from 36,651 to 4,575 estimated
  tokens and fail-closed matches seven classes canon↔implementation.

- **`task`: four hard gate plan-protocol are turned on forward-only.** The shared registry stores
  date and append-only journal boundary activation; per-item status projection no longer
  replaces history with a global date. Downstream, return qualification, return owner gate and
  terminal decision join are applied to the new cohort without retroactive redness.

- **`task`: model judgement and received clarifications fail-closed command seams.** Five plan-commands
  create `DecisionRequest` instead of free prose and perform closed outcomes authority resolver;
  separate section `return-judgement@1.0.0`, provider-qualified calibration registry and reducer
  turn an unknown pair either order-sensitive swap in abstinence. Codex confirmed on
  discovery-bank, Claude remains `pending-provider`.

- **`task`: closing commands plan-protocol are now producing v2-traces.** They're recording
  session provenance, regenerate projections, commit downstream-gate record and save
  fail-closed escalation qualification; Codex confirmed, Claude awaits provider-owned replay

## [0.10.0] - 2026-08-09

- **`task`: five protocol commands is now selected declared read path by `Layout`.** Plans without
  fields are saved literal v1-branch; `Layout: v2` reads smoothly plan core, phase context, item spec,
  digest-qualified bundle and fresh item state, without mandatory `handoff.md`. Codex-projection
  regenerated and verified; Claude remains `pending-provider` with explicit replay.

- **`task`: decision queue P5.4 now forces frozen contract fail-closed.** Semantic outcome
  holds uniformly authorization auto-answer in owner/join pending, frozen bounds believe
  substantive options separate from mandatory, a exact retry restores journal and that's it views without
  duplication queue events or durable continuation (–D146).

- **`task`: return-loop owner gate now creates a reference DecisionRequest.** Frozen
  P4 packet is not copied to the queue, affected subject is parked at the address, and policy auto-answer
  only clears its local pause.

- **`task`: P5.5 now proves queue semantics executable producer acceptance.** Twelve
  fresh-copy scenarios cover terminal policy auto-answer without repeating owner ingress,
  the only one allowed `pending-authorization` owner-flow, owner `continue`/`park`/`reject`,
  boundaries 2/5 substantive options, mandatory-only reject and exact retry after request/resolve
  projection failure with byte-replay generated results/report.

- **`task`: added durable plan decision queue.** Append-only requests, lease-claim,
  subject address pause, exact root continuation, owner-gate projection and disabled
  join-gate are implemented without adding a queue to the required read path.

- **`task`: added fail-closed plan permission resolver.** Single point
  `authorize()` returns a closed structured verdict, kicks the active
  authority-frame, aggregates decisions within item, secure auto-reply only
  provenance-confirmed clarifications and supports shadow-observation.

- **`task`: frozen deny-by-default authority frame `authority-frame` v1.**
  The machine contract and the actual owner instance define a single delegated class
  `constructive`, three reserved boundaries, monotonic narrowing and item-scoped aggregation against
  splitting solutions (–D61, D143).

- **`task`: history return events now contains plan-local `return_event_id`.** It is equal to
  physical address `journal.jsonl:<line>` and links judgement carrier with specific return event,
  without changing frozen fingerprint tuple, digest, namespace or `same_return_max`.

- **`task`: return-judgement v1 is now consumed deterministically return-loop.** Reducer
  selects the first schema-valid independent entry for precise return event, collects complete
  event-scoped owner packet, does not allow `blocks=true` along with continuation and plays
  acceptance from item tree.

- **`task`: added return-loop v1 for returns plan-protocol.** `returns --gate`
  applies lifted limit, prints hard-stop owner packet over durable history and gives
  disabled by default opt-in lint-proficiency testing/owner authorization
  via existing item-scoped finding (–D139).

- Added deterministic return fingerprint calculator and durable-counter for plans.

- **`task`: added downstream-gate v1 for producer→consumer smoke-checks.**
  The tool mechanically removes consumers from the paths of the plan, executes only the applicable
  subset of them `Validation`, saves `green`/`red`/`unknown` with key «SHA-256 TK
  consumer × item-producer commit» and provides disabled by default opt-in
  check `plan-lint`.

- **`task`: continuity maintained `plan-lint` when layout v2.** Registry
  dispositions with introspection check covers everything `_lint_*`-checks;
  RAG/Consequences decisions and limit Update Log read v2-media `decisions/`
  and `journal.jsonl`, saving the branch v1.

- **`task`: `plan-lint` now checks frozen read-path v1.** Order is checked
  volatility, exception history from executor path and ban active item’read item-spec
  terminal phase; checks are based on registry/spec/resolver.

- **`task`: layout-v2 Bundle v1 now fail-closed is checked for ready item'ov.**
  `plan-lint` distinguishes declaration drift, missing/extraneous entries, changed input
  bytes and unresolved declaration, does not rebuild artifact and byte-checks decision,
  status and item-state projections (–D135).

- **`task`: layout-v2 plans now hard-fail are checked against the required reading budget D2.**
  New shared `plan_gates` uses the only weight owners and admission, names the item,
  numerical threshold, qualified calibration and a separate unreadable file; v1-plans are silent
  without opt-in.

- **`task`: deterministic schema-valid Bundle v1 for inputs item’a
  .** Single `plan-views.py bundle`
  builds and byte-checks committed manifests, hashes raw/selected bytes and
  estimates weight by frozen calibration; unresolvable declaration atomically fails
  before recording, and P3.4 displays it separately `unresolvable_entry`.

- **`task`: stage-aware admission reading budget and bounded `plan-lint` carriers
  .** `plan-weight` distinguishes
  `historical-pre-v2`/`pending-producer`/`ready`, validates fail-closed producer edges and
  applies immutable D2(a)+D2(b) only to `ready`. Monolithic lint implementation/tests
  are mechanically divided into bounded modules with saved public imports and byte-parity
  diagnostics v1/v2 fleet.

- feat(task): add deterministic on-demand historical view of the item layout v2.

- feat(task): add deterministic generated state-point projections layout v2.

- feat(task): add generated owner status view for plan layout v2.

- feat(task): add parsing of fine phase indices v2 and separate technical specification files/item states.

- feat(task): add immutable v2 decision records and deterministic generated views.

- feat(task): add the versioned executable-plan layout resolver and frozen carrier contracts.

### Fixed

- **`task`: journal-backed Update Log no longer creates an unclosable lint-conflict.**
  New `note` longer than 300 characters are rejected before being written, and layout-v2 status deterministic
  projects historical long note short pointer to the original line without modification
  append-only journal.
- **`skiller`: validation snapshots are consistent with current additive carriers.** Public config
  snapshot includes `plugins`, a publication guards record the actual Codex marketplace
  locator and full set Claude artifacts.
- **`task`: dry-run migration legacy-plans no longer reject absence
  optional `## Discussion`.** Inventory records the absence of media without
  fictitious file, and blocked journal-state is projected into the mandatory v2-three
  escalation.
- **`task`: fixed single name desync v2 phase-closure carrier.** Registry and
  read-path specification are now addressed equally `phases/<Pn>/<Pn>.closed.md`, like D34/D77 and
  project consumers; before the implementation of the generator did not exist
  runtime consumer obsolete `.closure.md`.
- **Codex plan handoff now pins the full launch route.** Generated runtime projections
  `task:plan-*` requires a separate native launch-block with `-C`, `-m`,
  `model_reasoning_effort`, `-a never` and `-s danger-full-access`; `$ task:…` remains
  intrasession only invocation. For `plan-run` route is derived from Routing
  next item'but not inherited from the previous session.
- **`plan-weight.py sweep` no longer drops an entire fleet gauge with one inaccessible root.**
  (–D112.) U `sweep` accounting unit appeared «root
  login» — top-level `roots[]` with closed status `resolved`/`unreadable`/`missing` on
  each directory passed; inaccessible root (`PermissionError`) is intercepted and not
  takes away the rest, and the readable root without plans no longer disappears from the output without a trace.
  `errors[]` now only carries the outcome of the PLAN (`plan_dir`), is not a root.
- **`maind_memory_recall` no longer sinks in general namespace.** `_recall_union` (mid-session
  recall) inherits the principle D10 from SessionStart-digest: private scope project is being polled
  without cap (`RECALL_LIMIT=200`), a shared-scope's (`ns:*`/`global`) when `project:<id>`-expansion —
  under new `RECALL_SHARED_LIMIT=40`. Measurement:
  on 6 projects the total pool gave 84–96% response when the project's private memory is low (e.g. Agelto
  2 entries vs ns:axioma 47).
- **`task` no longer assigns all plans to alien D50 authority grant.** Task Contract
  outputs routine authority from checked item-carrier current plan; protected transition
  is only allowed exact, scope-matching and unrevoked entry `[OWNER-GRANT:<gate-id>]`
  in Decision Log, otherwise remains `block:AUTHORITY_BOUNDARY`.
- **`task` fail-closed parses protected owner grants.** The entry must now be accurately
  bind gate, branch and finite scope with separate explicit repository-owner message in Layer-0
  `brief/` and his provenance; copied `Approval Owner`, synthetic D#, prefix-matches and
  arbitrary owner-prose cannot be returned `allow`.
- **`task` and core-templates are no longer searched Python runtime inside the connected project.**
  Schedule commands Codex resolve the only one included `task@swissknifeman` via native
  list of plugins and run it `lib/`; Claude Code uses `${CLAUDE_PLUGIN_ROOT}`.
  Renderer and provenance-lock allow such deterministic upgrade only when changing version
  adapter and an exact match of the previous controlled output; manual drift remains fail-closed.
- **`harness doctor --settings` recognizes current settings Claude Code 2.1.220** and not
  requires executable-bit for a script launched through an interpreter. `skiller update` deletes
  only recognized legacy symlinks `packages/task` from already connected projects.
- **Harness validation is playable again on committed tree.** Provider-instruction lock
  is regenerated by standard owner surface, run-reader test no longer depends on the root archive,
  generated provider reference is checked fully package validate, a P4 provenance/G2 assurance
  require exact Git/journal/anchor evidence and pass the built-in tamper probes.

### Added

- **`task`: provider-qualified token valuation calibration v2
  (–D122).** Appeared stdlib-only
  neutral contract `task.token_probe` and isolated adapter `codex exec --json`;
  active artifact now kicks provider/model/protocol, fail-closed rejects v1 and
  mismatched classifier, a `dense_ascii` became fifth grade with a single SSOT.
  Limited run uses 8 provenance-qualified real samples (≤128 KiB) and
  bracket-controls (≤12 provider calls); historical Claude v1 artifact/probe-log
  are saved separately.

- **`task`: machine measurement of the weight of the mandatory reading of the plan item
  (–D109).** `task.plan_weight` + launcher
  `scripts/plan-weight.py` (subcommands `item`/`plan`/`sweep`, `--json`) play
  required executor read path from `commands/plan-exec.md` §1 literally
  (`plan.md` + `handoff.md` + `phases/Pn.md` + `Required Reads`), count his weight
  assessment TOP on top of frozen calibration P0.1 and check each file
  CONJUNCTION OF both gates of the measured reading limit P0.2 (`size_bytes` AND `tokens`,
  D108) indicating the broken gate. What is not resolved is classified as closed
  taxonomy (`unreadable_root`/`unresolved_entry`/`missing_file`/`oversized_file`),
  and the sum is NEVER printed without a list of spaces. For each file it is considered
  `dense_ascii_share` — froze without threshold. Mode `--exact` checks the estimate against
  the truth of differential learning P0.1 and remains manual, out CI; `count_tokens`
  is not called in any mode.

### Added

- **`task`: deterministic converter executable plan v1→v2 and self-host migration
  .** New `plan-migrate.py` only translates
  allowed self-host plan inplace or any plan to safety read-only dry-run
  projection with explicit output; migration inventory and before/after read-weight save
  lossless evidence. Owner status now correctly counts phases from terminal
  deviations completed.

- **`task`: deterministic estimate of the read weight of the TOP plan, calibrated against
  real tokenizer.**
  `task.token_estimate` (stdlib-only) counts tokens based on a closed set of character classes
  (`ascii_word`/`ascii_other`/`cyrillic`/`other`) and frozen calibration artifact -
  without network and keys, never understating. The artifact was obtained by DIFFERENTIAL Harness
  (`calibrate-token-estimate.py`, D92: channel `POST /v1/messages/count_tokens` unreachable
  without key Console) for three runs `claude -p` to the body file (empty wrapper / file /
  drift control), 14 real fleet plan files, `bound.violations: 0`, looseness
  p95 1.17 (gate ≤1.6).

- **Artifex business-provider projections now run against current Codex and Claude Code CLI surfaces.**
  The bounded adapters use a shared Draft-07 output schema, retain only normalized observations,
  and cover current Claude structured-result metadata without persisting provider text.

- **`dart`: connected via `connect` set for Dart-packages and SDK.** New
  `dart-package-development` covers public API, null safety, async-compatibility,
  conformance fixtures, checks and release boundaries; Flutter-layout remains in `mobile`.
- **(plan summary record): meter first-turn, resident diet,
  native skill scope, exec-wave, hygiene and layout `core/`
  (`).** P1.1 added to `skiller budget --first-turn`
  plugin component, and P1.3 raised the threshold to 16K/23K; P1.4 fixed CWD-dependent
  counting and distinguishing `broken`/`unparsed`. P2.1 fixed a measurable root limit
  canon, P2.4 did `.mcp.json.example` default-on only in green provider-branch,
  P2.5 removed duplication of the native listing from the hub block. P3.2 did not roll out
  dominated `paths:`, but reissued the listing model; P3.4 issued four procedural
  skill in `context: fork`, P3.5 added `when_to_use` and joint recording gate.
  P4.6 gave `swissknifeman env run <PLAN-ID> Pn` for serial exec-waves.
  For P5.1, P5.10 and P5.11 see individual entries above; P5.4 pinned provenance
  performer route, P5.6 captured Playwright MCP with `--output-dir`, P5.8
  added the command line launch-block, P5.9 — `plan-lint --conflicts`. P6.1 moved
  provider-cluster `core` to a batch layout without changing the public façade.

- **The vendor class trust policy is now executable: block `audit` in `upstream.json` +
  gate «no verdict / the verdict is rotten».** Human Verdict
  according to the bundle moved from the table inside the plan to the additive block next to the skill (`verdict`
  ∈ `clean`/`attention`/`risk`, `at`, `by` — address of the reader, `upstream_sha` — anchor, `note` —
  is required when `attention`/`risk`); checks the block shape `validate.sh`. `--check` received
  two findings in existing exit code `11`: **`AUDIT_MISSING`** (unread bundle
  there is no human verdict - «not checked» and «clean» are no longer indistinguishable) and
  **`AUDIT_STALE`** (verdict against other bytes). The anchor is stored SEPARATELY from
  `files[].sha256` and is not updated either `--apply`, neither `--resolve`, therefore mark «rotten»
  is experiencing the use of upstream - the previous derivative mechanism died from one line and
  remains only for bundles without a block `audit`. Backfill **56** blocks according to the audit table P5.1;
  bundle that does not vendor anything has been announced `kind: "reference-only"` (it doesn't have an anchor
  designs). Border «what comes to the agent as rules of conduct is repaired; certificate and
  user artifact - accepted class» is written verbatim in
  `skiller/guide/vendored-skills`.
- **`frontend/web-design-guidelines`: removed dependence on the rules network channel, bundle
  translated to `strategy: fork`.** Skill earlier on every call
  pulled `raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` and
  applied the received AS RULES of behavior (audit finding `PRM_REMOTE_INSTRUCTIONS`,
  the only one of the six `attention`-finds P5.1, where the removed content is instructions, not
  help/user artifact). Payload pinned commit `4e799d45c17aec1498c269287a83b9dba22b966b`
  (6 939 b, sha256 verified) vendor pristine-copy to `references/web-interface-guidelines.md`;
  `SKILL.md`/`SKILL.ru.md` rewritten into navigators without a single network instruction;
  `upstream.json` carries `strategy: fork`, `body_path` and `notes` with manual procedure
  re-pins. Freshness is deliberately traded for integrity - upstream `main` did not move since
  2026-04-06, price at measurement is zero. Pinning procedure/re-pins - new section
  `skiller/guide/vendored-skills`.
- **Supply-chain vendor skills: one-time human audit of 56 bundles + triage stage in
  `update-upstreams.sh --check`.** First meaningful audit
  external skills in the entire history of the registry - before it ONLY byte integrity was checked.
  Name verdicts 56 bundles (**50 clean / 6 attention / 0 risk**), solid machine
  coverage 100 % bytes (599 files, 3,070,592 b) for four threat classes, full reading of all
  56 `SKILL.md` and all 27 files with executable content, named coverage boundaries -
  . Triage stage subordinate to audit:
  13 stdlib-rules (+ `BIN_UNREADABLE`), derived FROM audit findings, **new exit code `11`**
  (is intentionally not merged with `10` — «upstream has changed» and «suspicious pattern» miscellaneous events),
  keys `triage`/`stale_verdicts`/`triage_disclaimer` in `--json`, verbatim disclaimer
  **«no findings ≠ safe»** in both channels. Byte drift relative `audited_at` marks
  human verdict on the rotten. Procedure and its boundaries - new doc page
  `skiller/guide/vendored-skills`. External scanner is NOT connected by dependency - patterns
  rewritten by their own (`root.engineering-invariants`), provenance in `docs/reference.md`.
- **`update-upstreams.sh`: all failure fixed `--check` on provenance records without a mirror.**
  Record `files[]` with empty `path` (link to external spec, no local mirror -
  `skills/voice-ai/voice-ai`) resolved to the skill catalog ITSELF, and `read_bytes()` dropped the whole
  run `IsADirectoryError`-om: Registry integrity check was completely inoperable.
  Now such a record is printed with the tag `[ref]` and is skipped without verification sha. Found by audit
  P5.1, closed by regression test.

- **Provider parity Claude Code/Codex by root instructions, capability and declarative
  execution policy (phases P1–P4).** Four phases, terminal
  🟠 Done with deviations: canon of root instructions checked against the tree (matrix «rule →
  house», assertions directory `1.0.1→1.1.1`, literal coverage gate 105/105), started
  adoption-mode `harness instructions <plan|check|adopt|apply|repair>` and live transaction on
  twelve targets with drift gate; 17 `unsupported`-capabilities of the second provider
  triaged (closed/adapter/`Claude-only` with an honest reason), dispatcher Codex-handlers and
  group of observers/class gates B brought to a conformance artifact with a drift gate in
  `hygiene.yml`; framework canon and decision registry brought to measured reality, loop
  audit is closed by a machine gate for the freshness of package versions in `validate.sh`, detection budget
  received skills provider-aware model (Codex/Claude Code) with WARN-search gate;
  sealed declarative execution policy contract (`execution-policy.json` +
  `execpolicy.py`, gate `[10/10]` in `validate.sh`), delegation contract landed in grammar
  orchestrator PLAN and translated `pending → enforced`. Details, D-log and artifacts -
  /`.
- **Schedule commands `plan-*.md`: delegation cap, `confidence` in audit finding, item DoR
  «external fact classes» (P2.3).** Same rule A/B/C and the same card FORMAT,
  what do you have P2.2, applied to five `packages/task/commands/plan-{design,exec,run,close,audit}.md`.
  **Class A is empty again** (singular grep-match - rerun of deterministic linter,
  class B2; status update forests 0): delegation cap added `plan-design.md` — the only one
  from the five, where the intelligence subagent is assumed by the text (guide Opus 5 §6), axis
  `confidence ∈ {high,med,low}` — to find format and Expected output `plan-audit.md` (guide
  Sonnet 5, «Code review harnesses»; `review.md` received his half in P2.2). Machine media
  gates (`Pre-mutation`/`Pre-final` Task Contract, Validation, DoR-checklist) saved as class B —
  their demolition «as self-test scaffolding» prohibited D86/D93. Separately, by D81, in `plan-design.md` contributed
  item DoR «external phase fact classes are listed, each with a source» LITERALLY according to the spec
  `research/14-P6.3-dor-delta-spec.md` §1.2 (byte matching). Decision Map -
  ; `model`/`effort`-pins and
  `description` are untouched.
- **Intent commands: delegation caps + `confidence` in find review format (P2.2,
  ).** Revision of six intent commands `packages/task/commands/` and twelve
  files agent-packs according to the rule A/B/C (`research/01` §1, expanded D19) under the guides Claude 5.
  **Class A (meaningfully empty self-test rituals and forests of status updates) — empty**, work
  went to «add missing»: delegation cap in `design.md`/`research.md`/`review.md`
  (guide Opus 5 §6: «give explicit guidance on which scenarios warrant delegation, or set
  deterministic caps») + axis `confidence` next to `severity` in find format `review.md`
  (guide Sonnet 5, «Code review harnesses»). Adversarial-verify other people's finds and RAG-verification
  external facts are clearly derived from the cap - the guide addresses self-checking of its own conclusion.
  Fifteen files are closed as «no changes» with parsed candidates; decision map -
  . `model`/`effort`-pins and
  `description` are untouched.
- **`general/verify-claims`: anti-overconfidence — coverage-step + perplexity as a separate class
  + summary delegation (P6.3).** Three deltas based on two dated field
  cases of the same plan (D20 — silent frame narrowing «Opus 5» instead «Claude 5 family»; D53 —
  summary WebSearch-only delegate taken to be an exhaustive list hook-events): (1)
  coverage-step - before committing the plan/phases/verdict list external fact classes, including those
  the answer to which seems to be known; (2) `perplexity-web` reformulated from fallback to miss
  docks into a separate knowledge class (field practice), called EVEN when first-party hit; (3)
  section «Delegation: don't drop a step» extended with «check the fact» on «summary/list».
  Hard class boundary A/B is met - no added line prescribes
  self-check its own output. Additive paragraph at root `CLAUDE.md` § «Methodology
  solutions». Three new pressure-script (`evals/pressure.json` id 3–5, by D20/D53/time-pressure);
  run `skiller eval general/verify-claims` — 6/7 green (pre-existing case id:2 remains
  red, out Scope this item'a —).
  **Fair Boundary:** 7 text cases - smoke-formulation test, not measurement
  overconfidence-behavior. Third amplifier D20 (item DoR) — anchored speck for P2.3
  (`research/14-P6.3-dor-delta-spec.md`, D81), file under cross-plan is not controlled by a gate here.
  RU-source → regenerated EN-canon → `check-translations.sh --stamp` → `skiller registry`;
  `description` untouched.
- **harness: statusline context-notify — window to actual context percentage (P6.1,
  ).** New surface `configs/claude-code/statusline/`: script
  `context-notify.sh` prints the line `model · directory · bar · N%` and at the CROSSING lane
  threshold (default `80,90`, cooldown 15 min) disconnected (`setsid`) pulls existing
  `hooks/notify/notify.sh` — we do not create a second notifier. The status for the session is written
  atomically in `${XDG_RUNTIME_DIR:-/tmp}/claude-statusline/`, because runtime cancels
  statusline-script in the middle with a new update; `used_percentage: null` (session start,
  after `/compact`) is not considered zero - the bar is not drawn and the decision on the threshold is not made.
  Enable opt-in per-project: `harness hooks --target . --statusline context|off` (key
  `statusLine` in `.claude/settings.local.json` — machine-local preference, like
  `outputStyle`; someone else's meaning is respected skip+warn), files are put by the branch `--global`.
  Measurements: delta `skiller budget --first-turn` = 0 current (statusline does not spend context tokens
  by construction), render median 5.4 ms with a maximum of 6.9 ms on 50 runs (acceptance threshold
  50/150 ms) — numbers and band table in.
- **`general/context-economy` + `general/compact-responses`: compact-discipline (P6.2,
  ).** `context-economy` §3 received three deltas: session boundary at the seam
  tasks (completed unit of work/phase change/repeated `/compact`), and not by percentage -
  the model does not see the actual percentage; What does compaction lose? (rejected alternatives,
  «why NOT selected») and that decisions are recorded in a file, not only in chat; first party
  lever `# Compact instructions` in CLAUDE.md + address `/compact <focus>`. `compact-responses`
  received delta `answer-first` (action before justification). Candidate D8 `no
  preamble/closers` closed as already covered (lines presented, not rewritten). RU-source →
  regenerated EN-canon → `check-translations.sh --stamp` → `skiller registry`;
  `description` both skills are not touched.
- **`scripts/bootstrap-machine.sh`: role-conscious stage 5 + rollout-documentation of the second machine
  (P4.3,, ADR-0001).** Stage `maind service install` reads `memory.role`
  from local `config.json` BEFORE branch `--dry-run` — on `role=client` prints informative
  `SKIP` and does NOT raise the local daemon (second writer), behavior `standalone`/`host` not
  is changing. `docs/deploy.md` received section «Second car: cross-machine memory (host/client)»
  (host/client checklists, including mandatory `memory.url` host on LAN-address after LAN-bind
  `iii-config.yaml`); `packages/maind/docs/guide/systemd.md` calls `loginctl enable-linger`
  role condition `host`, is not an option. Three of six receiving gates rollout'a (client-specific)
  not driven - there is no second physical machine in the executing session; `Linger=yes` on host
  confirmed; gate attempt «backuprestore» opened the find - built-in mesh-discovery engine
  mounts any local process `agentmemory` to the general group REGARDLESS of directory
  data/port (threat to invariant «one writer» when testing locally) — incident
  fixed without data loss (254/254 records), root cause (`config.json` without `memory.url` on
  LAN-address after LAN-bind) is documented and fixed on this machine. Full protocol -.
- **`maind`: cross-machine memory mode - `memory.role` (standalone/host/client) +
  bearer-authentication (P4.2,, ADR-0001).** New field
  `memory.role` (default `standalone`, back-compat — existing nodes do not change behavior);
  `role=client` prohibits CODE from raising the local daemon (`maind memory start|run`,
  `maind service install` refuse), so as not to have a second writer. Additive
  extension `core.http` (`http_get_json`/`http_post_json`/`ping` + optional
  `headers`) carries `Authorization: Bearer` from `memory.secret_file`/`AGENTMEMORY_SECRET`;
  new `core.http.HTTPUnauthorizedError` (subclass `RuntimeError`) distinguishes 401 from others
  network failures - `maind doctor`/`maind health`/MCP-memory inaccessibility branch is no longer
  confused «unauthorized» with «not available» (`/agentmemory/health` is ALWAYS public in the engine,
  so it was indistinguishable before). Custom waiting budget
  (`MEMORY_LIGHT_TIMEOUT_S`/`MEMORY_HEAVY_TIMEOUT_S`/`MEMORY_RETRIES`) with retrays ONLY on
  read-paths (`export`, not `store`/`forget` — contract without operation-id, risk of double).
  LAN-stage: `config/memory/iii-config.yaml` bindend `iii-http` to a specific
  LAN-host address (not `0.0.0.0`) — managed engine config, convertible in one line when
  trigger `tailscale serve`. Channel metering -
  `findings/P4.2-remote-link-measure.md` (fair border: a real second car yet
  no, P4.3 will remeasure).
- **`skiller budget --first-turn`: skill listing resident is calculated according to the budget model
  Claude Code, not the sum of descriptions (P3.4).** `_measure_skills` now
  drips every listing entry for 1,536 characters (`description`+`when_to_use`, first-party default)
  and keeps the amount under the ceiling `context_window × listing_fraction` (default 1M × 1% = 10 000 current;
  both parameters, not constants) — previously ALL descriptions of the active set were summarized, the same
  reaccounting class that was `/context` to v2.1.196. Report shows both numbers (`raw_tokens` —
  sum of dropped records, `tokens` — after the ceiling), when they separate. Recalibration
  `CHARS_PER_TOKEN_*`/`FIRST_TURN_TARGET_MAX`/`FIRST_TURN_WARN` via `count_tokens` on
  `claude-opus-5` — **failed** (no network with credentials/SDK in the execution sandbox),
  Pending Work next call (`findings/P3.4-tokenizer-calibration.md` §3).
- **`docs/guide/upstream-sync.md`: criterion for transferring a live skill `notify` → `fork` +
  price recognition (P3.6).** New sections «When to transfer a skill to
  `fork`» (two required axes - mechanical re-applicability of dressing × observed value
  of the last sincs, plus the cutting axis of the diff surface; numerical operating thresholds
  criteria are prohibited) and «Price `fork`» (permanent merge tax · drift · security backports +
  our specifics: `review_pending` blocks the release of the entire repo). Classification of all 56
  passports `upstream.json` by criterion: translations - 0
  (legal and expected outcome, no passport has observed manual sync debt since
  import). Fixed discrepancy between dock and code: root `CLAUDE.md` § «References and
  provenance» listed `strategy = notify | fork | merge`, skipping `replace` — added.
- **`skiller status`: two new channel hygiene deltas - vendor without manifest + duplicate names with
  registry (P3.5).** `detect_raw_vendor_path` sees the vendor channel,
  delivered NOT via `skiller sync` (symlinks/copies from the side, without
  `.swissknifeman-manifest.json`) — previously such a channel was invisible and `channel_overlap` on it
  was silent (repo fact `flexcrm`: 58 records without manifest). `name_duplicates` catches a double
  frontmatter `name` between a local entry and ANY registry bucket (not only enabled) —
  second physical copy of the skill, not updated `skiller update`. `dead_local_entries`
  diagnoses broken symlinks/directories without `SKILL.md` number and list. Live run on
  `flexcrm`: 9 duplicate names, 41 dead entries; control on the project without vendor-channel - silence.
- **`packages/skiller/tests/test_profile_listing_budget.py`: listing budget invariant
  supplied profiles (P3.5).** Real budget 1M-models - 30,000
  characters (not 10,000, budget unit - tokens, not context percentages directly in symbols,
  diagnosis P3.1); with corrected number 9 out of 10 supplied profiles are ALREADY installed - none
  `profiles/*.json` did not need to be edited. `standalone` — named exception
  (`buckets: ["*"]`, narrow - lose the meaning of the profile The), test documents and captures the boundary.
- **`docs/guide/profiles.md` § «Listing Budget» + `docs/guide/bucket-audit-2026-07.md` §
  «P3.5 postscript» (P3.5).** Profile table vs. corrected budget
  (30 000/6 000 char) + recommendation card (`skillOverrides: "name-only"`,
  `skillListingBudgetFraction`) for other people's configs; updated consolidation proposal
  buckets (46→48, D83) with mandatory listing calculation BEFORE/AFTER for actual subscribers -
  consolidation NOT executed (**OQ-10 closed by option (b)**, sell as budget win
  prohibited - granularity saves, merging takes away).

- **`review-gate`: third enforcement point of the quote gate - `checks/plan-citations.sh` (P11.7,
  ).** Changes affected `plans/<ID>/` → run `packages/task/scripts/verify-plan-citations.py
  plans/<ID> --strict` for each affected plan on top of the dispatcher P9.1 (`run-checks.sh`);
  string `{"name":"plan-citations","mode":"warn"}` in `config.json` — mode based on cleanliness
  (`--strict` red on a living tree: 16 pre-existing finds P11.5,
  Open risk (25) — `strict` will give an unexplained noise, upgrade is conditional on their addressing); graceful
  skip, if `packages/task/scripts/verify-plan-citations.py` is missing from the tree. Two real live-run
  subagent (Agent-tul): broken quote in `handoff.md` is caught `[WARN] plan-citations: …`,
  genetically pure plan (0 finds) remains silent on this
  same run (target replacement B — on «clean» no condition today, same
  confound P11.6). Rolled onto the owner's car (`~/.claude/hooks/review-gate/`), sha256
  repo↔machine verified; `harness doctor` — third state not degraded (`plan-citations`
  added as declared, no shortcode - fallback to the raw name, `doctor.py` untouched).

- **`plan-protocol` §8 «Closing order item'a» + `plan-close.md`: mandatory gate run
  quotes when closing (P11.6).** Near step 4 (plan-lint, after
  rewrite handoff'ah, on the resulting tree) — `python3 packages/task/scripts/verify-plan-citations.py plans/<ID>
  --strict`; step 5 carries the second line of the invoice with attribution: «quotes: N finds - new from diff
  item'a: K» (K>0 is being repaired BEFORE bookkeeping-commit, N−K>0 — Pending Work + Open risks). Same
  box - in `commands/plan-close.md` (mode `Pn.m` step 6 and mode `Pn` step 7). The rule is entered
  AFTER P11.5 (the gate on live planes is already clear - K=0 by construction for the first one to be closed
  item'a). Existing canon steps are NOT renumbered (F4-relapse: score without attribution).

- **`packages/task/configs/verify-citations-known-exceptions.json`: baseline-list + residual triage
  quote gate housings (P11.5).** Running the gate on live planes after
  P11.1–P11.4 yielded 105 hits (52 unique quotes) — according to four mechanical rules
  R1–R4 (`packages/task/docs/reference/plan-tooling.md` § «Known exceptions»): 18 quotes
  fixed to full path (the short form has been restored unambiguously, `git ls-files`), 19
  are listed as exceptions with targeted reason (external files - Claude Code CLI
  bundle/Serena, ambiguous paths - multiple candidates `validate.sh`, quotes in closed
  item'oh and in other people's plans). `python3 packages/task/scripts/verify-plan-citations.py --strict` — 0 finds on all
  live plans (was 52); gate ready for strict-class.

- **`plan_lint.py`: cross-document check `handoff.md` ↔ «## 4. Phase Index & Status Board»
  (P11.3,, D129).** Each occurrence of the pattern `Pn a/b` in `handoff.md`
  is checked against the column value `Items 🟢/total` lines `Pn` boards - discrepancy is diagnosed
  with BOTH sides, the phase missing from the board is «dangling link» (class protects against discovery F8
  audit P9: handoff lied `P9 4/4`, board carried `2/4`). Forward-only by header date handoff'a
  (`HANDOFF_BOARD_CANON_DATE = "2026-07-28"`); severity — like launch-block-gate (dated
  `plan_id` from `2026.07.16` → ERROR, legacy → WARNING). On a living tree ECO-OPT gate immediately
  found a real discrepancy (`handoff.md:44` — `P3 1/6` vs board `P3 0/6`), unrepaired before
  P11.8 (Scope Excluded this item'a). House is a structural linter, not `verify-citations.py`.

- **`packages/task/scripts/verify-plan-citations.py`: quote class `` `file.json::a.b.c` `` via `json.load`
  with greedy-bypass (P11.2,, `research/27-P11-citation-gate-target-design.md`
  §2.3).** Previously, such a quote was resolved by an old thread `::symbol` — waypoint worked
  as a regexp metacharacter, the check was false green. Now: the file is parsed as JSON →
  path is resolved by keys/indexes, at each level the LONGEST subsidized
  remainder prefix, which is the key (regression - keys with dots in proper names,
  e.g. `owners.P2.2`); JSON is not parsed → find «JSON is not parsed», is not a silent pass.
  Border: «key exists», value is not verified.

- **`packages/task/scripts/verify-plan-citations.py`: two-step path resolver + seven surface patterns
  scan (P11.1,, D128).** Quote resolution - for TWO databases in a fixed
  ok (repo root → source plan directory); internal short link
  (`` `phases/P1.md:80` ``) resolves to second base instead of a false find - on live planes
  removes 79% false background (114/144). Scan surface expanded with `plan.md`+`phases/*.md`
  up to seven templates (`+handoff.md`, `roadmap.md`, `findings/**`, `research/**`, `brief/**`,
  recursively) — there were 120 blind knowledge layer files. Naked path-mention without suffix
  is deliberately NOT checked (class rejected by measured noise 16%, D128).

- **Review role registry as data (P9.2,, D126).** Extension-table
  `packages/harness/configs/common/agent-packs/review-roles.json` (key `(pack_id, role_id)`,
  next to canon `roles.json`) indexes five reviewer-roles: projection/overrides,
  actual headings of the four required sections, measurements from a closed dictionary.
  `role-bindings.json`/`agentpacks.py` untouched (frozen provider-contract). Validator
  `harness.reviewroles` (stdlib, eight checks, each for a specific failure mode
  policy-as-data) — step `[8/8]` `packages/harness/scripts/validate.sh`, single point
  coercion. Actual drift of five packs (different headers, different set `skills`) —
  , addressed to track 1 OQ-4.

- **docs-impact gate in CI (P8.4,, D119–D123).** New
  `scripts/docs-impact.py` + `.github/workflows/hygiene.yml` stops change-set,
  which enters/removes/renames the package surface file or edits its interface
  (`bin`/`commands`/`configs`/`install.sh`), without editing the docks of the SAME package in the same
  range - measured rule C, not «any surface editing» (sinter mold painted
  12/12 PR and would have filmed on the first controversial evening). Bypass - commit trailer
  `Docs-Not-Needed: <reason>` (reason is printed). Measured trigger frequency:
  8/12 PR, 11/41 commit on tree `cd93dbc8`; coverage boundary (does not catch body edits
  `lib/**` without new file/interface) is named in the docstring and `docs/develop.md` §11.

- **Capability Matrix `docs/status.md` (P8.5).** Table
  «Package | Opportunity | Maturity | Evidence / boundary» for five packages + `core` + root
  router, maturity - dictionary `plan-protocol` § Statuses; each line carries a reproducible
  command or named boundary. Checked `scripts/status-check.py` (step `status-check` in
  CI-job `hygiene`); honestly names the boundary: «visible CLI-group does not prove that its runtime
  enabled», check of completeness against the list of real possibilities is postponed (candidate D2).

- **CI-tree hygiene: prohibited paths + tag = version (P8.6).**
  `scripts/public-hygiene.py` — fail-closed by `git ls-files` for prohibited suffixes/names/
  directories (`.sqlite`/`.log`/`.pem`/`.key`/archives, `.env` except `*.example`, `__pycache__`/
  `.venv`/`node_modules`); `scripts/verify-tag.py <tag>` — tag `vX.Y.Z` must be top
  released header `## [X.Y.Z] - YYYY-MM-DD` in root CHANGELOG.md. Step
  `public-hygiene` in job `hygiene` and new job `release-tag` (`on: push: tags: ['v*']`) in
  `.github/workflows/hygiene.yml`; section in `docs/develop.md`.

- **`core.io.assert_safe_replace_target` (P8.7).** Goal invariant
  atomic write: before `os.replace` `atomic_write_text`/`atomic_write_json` fail if
  existing target - symlink, non-regular file or hard link (`st_nlink != 1`); failure
  names the path and reason. A non-existent target and a regular file - the byte-by-byte behavior is the same;
  new parameter `check_target=False` — point legal exit. Dedup: doxstring calls
  manual copies of the same invariant in `packages/maind/lib/maind/provider_deploy.py` (translation to
  helper - roadmap-candidate, outside the scope of this item'a).

- **`validate.sh`: body sections CORE-nines, anti-duplication projection, completeness pressure
  (P8.8).** Three deterministic delta gates: (1) resident
  `core-policy.json::skills` (9 pcs.) are required to carry the activation section (`##When…`/
  `##Activate…`, ERROR with Ratchet `scripts/skill-sections-burndown.txt`, 3 starting
  entries) and links section (`##Links`/`References`/`Related skills`/`Related`, ERROR without
  exceptions - zero debt); (2) thin projections `.claude|.agents/skills/*/SKILL.md` not
  duplicate canon - pairs from `adapters/repository-bootstrap/publication-lock.json`: body
  ≤15 non-empty lines, there is a link to canon, none `##`-canon title not played
  (fail-closed: there are projections, no location ⇒ ERROR; neither ⇒ pass); (3) skill with
  `evals/evals.json` must have `evals/pressure.json` with ≥1 script (ERROR), a
  `triggers.json`'s `should_trigger` without cover pressure-script (new field
  `triggers[]`) — WARNING. `eval.py::validate_pressure` validates the form `triggers[]`.

- **`skiller eval`: determinism `benchmark.json` (P8.9).**
  Metrics (`pass_rate`/`duration_*`/`tokens_*`/`delta.*`) — exact arithmetic
  `fractions.Fraction` inside (√ for stddev — integer, `math.isqrt`), string
  fixed precision at record boundary - none `float` in the report.
  Injected clock (`clock_ns`/`now_iso` in `run_case`/`run_suite`/`cmd_eval`,
  default - real time, CLI does not change) give byte-byte reproducibility when
  identical clocks. Honest block `provenance` (`llm`/`network`/`clock`/`baseline` —
  actual, not constants). `schema_version: "skill-benchmark/v2"` (spaced
  — does not conflict with its neighbor P3.3-contract `system-bank-benchmark/v1` in the same
  module). No-op on the offline branch, exactly `benchmark.json`(+`.html` when `--static`)
  on online — 6 new tests via `SKM_CLAUDE_BIN`-fake.

### Changed

- **Root `AGENTS.md`: router-table + untrusted-import invariant + repair by addresses
  breakdowns Codex-dogfood (P7.2,, D62/D143).** New section `## Operation
  router` (table `Operation | Canonical procedure`, reception A2) sends to canon
  `general/plan-protocol` §8 for plan-item'ov and enters the rule «work inside the package -
  restart `codex -C packages/<name>`» (D62(3), closes owner-a question of fate per-package
  `AGENTS.md` without actually rendering them); untrusted-import string (reception F1) — imported
  content is data, not instructions. Four breakdowns of the living dogfood-run P7.1
  (`findings/P7.1-switch-test.md` §6) repaired at: headless-form `codex exec` without
  of a non-existent flag `-a`; preflight no longer prescribes `codex doctor --json` for
  confirmation model/effort (is structurally incompetent `-m`) — the source of truth is now running itself
  command; launch-block for `plan-protocol`-work announced MANDATORY neutral table
  (with `Capabilities`) over native, not optional «may accompany»; form of semantic
  media `Next` is no longer rewritten here - line router-table sends to canon
  `general/plan-protocol` §8. Glue size
  `AGENTS.md` — 7 252 b against the ceiling 32,768 b (≈22%, stock ≈4,5× — 32 768 / 7 252). Specka -
  /research/21-P7.2-instruction-slice-spec.md`.

- **Reopene remediation P7 (P7.4,, D144).** Audit P7 (RED) found false
  base in the edit above: root `AGENTS.md` stated that `codex doctor --json` not
  accepts `-c` — accepts, rejects only `-m`; preflight-bulletin reduced to fact.
  Launch-bulletin required `-a never` from headless `codex exec`, which does not have such a flag -
  form is divided into TUI-path (`-a never`) and headless-path (`-c 'approval_policy="never"'`).

- **Cell shape `Items` in `## 3. Routing` — closed set + diagnostic failure
  (P8.10,, D124/D125).** Canon `plan-protocol` §9 declares the value
  cells with a closed set of two forms - one item (`Pn.m`) or single phase range
  (`Pn.a–Pn.b`); comma separated list (`P8.5, P8.6`) and merging a range with a list
  (`P4.1–P4.2, P4.4`) are illegal - the group of subphases is carried by the column `Batch`. Disclaimer Back-compat
  got a fair border: legacy easing §3 works for a person, but not for a cell
  `Items` — the machine reads it too. `task_contract._find_routing_row` on such a cell gives
  diagnostic failure (names a cell, its row number in `plan.md` and both legal forms)
  instead of voiceless `no §3 Routing row found for this item`; failure remains failure - route
  is not taken from the matched token. A cell without a comma and without a match gives the same text
  byte-to-byte. Measurement that generated the edit: 7 alive items no fleet was built Task Contract.

- **`SERENA_SCHEMA_FIELDS` narrowed down to the fact of upstream (P5.6,, D117).**
  The constant carried 12 keys under the name `FIELDS_WITHOUT_DEFAULTS` pinned Serena
  (`026b007b…`, `1.6.2.dev0`), where is the upstream on this SHA holds two - `project_name`,
  `language_servers`; the remaining eleven are in default (`data.setdefault`). Comment
  indicates the address of the fact (file+upstream string, reconciliation date); docstring `render_project_yaml`
  fixed on the same issue («lack of ANY → KeyError» — incorrect, deleted). Behavior
  renderer has not changed - we print the full set of keys using our own solution, not on demand
  upstream. Gate `check_schema_connectivity` still catches the real discrepancy
  (`language_servers`), but no longer colors leaving the optional key (`encoding`) false
  discrepancy.

- **`code-review-graph` — verdict `skip`, question closed by number (P5.2,, D112/D113).**
  External code graph as retrieval-layer under review **does not connect**: `Ops` the candidate has excellent
  (build 1.66 s on 405 files, increment 0.24 s), but precision blast-radius vs co-change ground
  truth `P_impact` = **0.039** at threshold `≥ 0.40`, announced BEFORE measurement. The threshold was not moved -
  instead, the metering was STRENGTHENED by the owner's decision: k-fold (each changed commit file seed'ohm
  in turn, 24 fold'and on three real commits Laravel-project, the protocol is declared separate
  commit before run). Gain shifted the numbers in favor of the tool (medium ×2.1, large ×1.45) —
  threshold still not reached, threshold crossed 1 fold from 24. Failure due to NOISE, not due to blindness: recall
  0.40–0.43 with 110 predicted files per one seed (true - at positions 77 and 102, that is
  truncation top-K makes things worse). Code graph canon remains **Serena** (LSP). Recorded in the body of the skill
  `general/mcp-advisor` (new server map line + block «Graphretrieval MCP: measured
  verdict» with rule «do not connect via README — only after your co-change-measurements» and three
  reopening triggers) and in `docs/reference.md` (`reference → pilot` → `skip` with numbers).

### Fixed

- **Codex: basic plugins `core` and `task` are now installed out of the box.**
  Umbrella `install.sh` adds local marketplace `swissknifeman` and calls
  native installation of both plugins, so `$ task:*` is available in a new session without
  manual `codex plugin add`/symlink inside the project. The list is taken from a single
  `core-policy.json`; profile plugins are not globally bloated. By car without Codex
  step is honestly skipped, opt-out — `--no-codex-plugins`.

- **Codex: native bucket-plugins are exposed again skills after installation.**
  Generator `.codex-plugin/plugin.json` lists each directory skill explicitly instead
  root `./`, which Codex 0.146.0 accepted, but did not disclose prompt. Live
  consumer-acceptance now checks `blender` in isolated `CODEX_HOME`.

- **harness: starting cleaning statusline removes orphaned `*.tmp` (P6.4,
  ).** The only one `find` in the new session thread now removes
  obsolete `*.state` and `*.tmp` with the same threshold `-mtime +1`; regression test saves
  fresh files of both types.

- **Pin Serena restored to the root cause - `SERENA_SRC`/`config.json`/`.mcp.json` fleet (P5.3,, D109/D110).**
  Policy `code_graph.args`/`index_args` root `config.json` interrupted the pinned default
  `SERENA_SRC` (`packages/maind/lib/maind/constants.py`) unpinned
  `git+https://github.com/oraios/serena` — the entire living fleet resolved the floating HEAD.
  First attempt to return a tag `v1.6.1` failed fatally (`KeyError: 'languages'`): upstream
  renamed `languages` → `language_servers` AFTER RELEASE `v1.6.1`, and our provider switched to
  new key yet 2026-07-23 (`ccd4505b`) — any tag today turns out to be downgrade, breaking
  loading `.serena/project.yml` on each registered project. The owner expanded the form
  pin: immutable link = tag OR full commit-SHA; value -
  `@026b007bb889366283c925527e9a3bab317f66c1` (`main` HEAD, `Serena 1.6.2.dev0`) — contributed by the same
  seam in `constants.py`, `config.json` (`args`+`index_args`) and `serena.args` ten living
  `.mcp.json` (`agelto`/`flexcrm`/`vaulter`/`swissknifeman`/`corex`/`memster`/`cms`/`edufy`/
  `chatom`/`perplexity-web-mcp`). Smoke on two types of projects (python-monorepo `swissknifeman`,
  php/laravel `flexcrm`) confirmed full JSON-RPC loop (`initialize` → `get_symbols_overview`)
  without fatality. Repeated `maind sync --only mcp --dry-run` confirms that `unmanaged-target`
 remains a separate defect that has not disappeared - delivery `.mcp.json` to the fleet
  is still manual.

- **Pin Serena moved to versionable layer + connectivity gate in `maind doctor` (P5.5,, D115/D116).**
  P5.3 three surfaces are pinned, but `config.json` — **gitignored**; only versionable
  bearer of the same policy, `config.example.json`, remained unpinned, and
  `packages/maind/install.sh` copies it to live `config.json` on any new node - fresh
  installation reproduced the defect D65 with its own installer. Pin
  `@026b007bb889366283c925527e9a3bab317f66c1` added to `config.example.json`
  (`code_graph.args`+`index_args`), `.mcp.json.example` (`serena.args`) and example in
  `packages/maind/docs/guide/code-graph.md`. Double guarded: offline test
  `test_tracked_templates_pin_serena_same_as_source` (`test_constants.py`) compares templates
  byte byte with `constants.SERENA_SRC`, and `maind doctor` now calls
  `codegraph.check_schema_connectivity` on the REAL node config - the discrepancy is printed,
  is not repairable.

- **`core.provider_lock._classify`: `unmanaged-target` can now be taken under explicit control `--repair` (P10.4,, D92/D106).**
  Thread `record is None` returned `OWNERSHIP_CONFLICT`/`REFUSE` EARLIER than in the thread
  accounting appeared `repair_requested` — unmanaged existing target could not be adopted
  never, even with explicit `--repair` (found D65, hypothesis D82). Two-digit rule specified
  BEFORE implementation: **Tier 1** — target exists, no entry, `repair_requested` set AND
  contents match the render byte byte ⇒ is taken under control (is written provenance,
  disk does not change - `STALE_SOURCE`/`UPDATE`, not `NOOP`, otherwise `apply_plan` would have missed the entry
  loka); **tier 2** (content divergent) ⇒ still `REFUSE`, but the diagnostics names the path
  targets, discrepancy class and command («diff … --repair»), not naked `unmanaged-target`. Four
  test combinations (there is a target/no × repair yes/no) + separate test for Tier 2. **Empirics on
  live fleet (15 verified `record is None`-targets):** 15/15 — tier 2, tier 1 not found
  once - systemic discrepancy (renderer today gives `codegraph`/`perplexity` + literal
  `"maind"`, and rolled out `.mcp.json` carry `serena`/`perplexity-web` + `${MAIND_BIN:-maind}`),
  non-design drift; fixing the renderer convention is a separate defect, `--adopt` for tier 2
  deliberately NOT implemented (owner-solution, D106). Delivery `.mcp.json` for the fleet remains manual
  in fact.

- **`plan_lint.py`: gate printed boundary codes (`_lint_write_site_codes_44`) was wrong
  in BOTH directions due to `re.search` throughout the field `Completion Notes`.** Fail-open: item,
  quoting ALIEN codes in prose item'a (parsing, example form), went through the gate like
  closed with his own. False ERROR: item with their `allow`/`allow`, quoted above
  by text `block:*`/`n/a` alien item'oh, blushing - `search` took the FIRST occurrence. Both
  prices are real with gate activation (`WRITE_SITE_CODES_CANON_DATE = 2026-07-27`). Repair -
  canonical carrier string `write-site: pre_mutation: <code> · pre_final: <code>`
: gate matches ONLY it, line by line; codes on other lines (quotes, explanations)
  no longer count. Literal `write-site:` registered in `CANON_LITERALS` +
  `i18n-keep`; instruction to print line added to `plan-exec.md`/`plan-close.md`.
  Five new discrimination tests (two of them are on the code BEFORE editing, red) + two
  existing test `TestWriteSiteCodesGate`, encoding the old free form,
  translated to canonical string (fixture, not subject to test).

- **skiller sync --repair now restores managed-skill REMOVED from the project.**
  A missing skill is classified as managed-drift (`not dst.is_dir()`), but pre-images
  it does not have by definition - the repair branch required `SKILL.md` for backup and crash
  `SPUB_OWNERSHIP_CONFLICT: … has no recoverable pre-image`, because of which the ONLY way
  recovery was unreachable: normal `sync` refused (drift), `--repair` was dying.
  Observed on a live project (`plan-protocol` missing from `.claude/skills`). Now when
  missing local bytes, the backup is simply not created (nothing to save), copy
  is restored, evidence carries `observed: sha256:<missing>`; behavior when alive
  local edits have not changed - backup `SKILL.md.provider-artifact.bak` still
  is required. Regression test -
  `test_repair_restores_managed_skill_deleted_from_project`.

- **Plan path resolution after archiving: `core.resolve_plan_dir` (P10.3).**
  `scripts/provider-docs.py` hard read the living path /…` and fell
  `FileNotFoundError` after archiving that plan (the file is actually located in `plans/archive/…`), a
  `packages/skiller/lib/skiller/doctor.py` the same two diagnostics (`capability-reference-coverage`,
  `trace-quality`) silently degraded into `unknown` with unsolvable `next_command: cat …` —
  tree carried TWO conventions per fact («plan `<ID>` — this `plans/<ID>` OR
  `plans/archive/<ID>`»), and the next archiving broke the next reader. New helper
  `core.repo.resolve_plan_dir(repo_root, plan_id)` — single resolver (live directory, otherwise
  archived, otherwise `FileNotFoundError` with BOTH paths checked); translated four
  functional reader: `scripts/provider-docs.py`, `scripts/test-provider-docs.py`,
  `packages/harness/lib/harness/instructions.py`, `packages/skiller/lib/skiller/doctor.py`.
  `python3 scripts/provider-docs.py --check` — green.

### Added

- **`maind.codegraph.check_schema_connectivity`: offline connectivity gate «pin Serena ↔ diagram `.serena/project.yml`» (P5.4,, D111).**
  Version Serena lives in the repo in two independent places (`constants.SERENA_SRC` and template
  `render_project_yaml`) — they already dispersed silently and fell fatally only at the living
  server. New function checks pin (`SERENA_SRC` + `code_graph.args`/`index_args` config)
  with required schema keys (`constants.SERENA_SCHEMA_FIELDS`, offline copy of the fact,
  without network) versus what the renderer actually prints - not the pin value, just the connectivity.
  Connected to `packages/maind/scripts/test.sh` via `tests/test_codegraph.py`.
- **`packages/task/scripts/verify-plan-citations.py`: gate «proof link resolves to symbol»
  (P10.2).** Moves a verification class into the repository, in which there is a hole
  called someone else's closed plan his duty (`verify_claim_verdicts.py` only checked
  existence of FILE from `ref` to `::`, character after `::` was not validated - via this
  passed the hole mis-cite H06). New stdlib-script checks four forms of links
  (`path:line`, `path:line-line`, `path:line,line`, `path::symbol`) in all living planes,
  closing at the same time the second class - rotten linear anchors on files rewritten by another
  plan. `--strict` for CI/pre-start discipline, the report is always printed;
  `--selftest` — embedded unittest. First run at: 154 quotes,
  39 finds (are documented in Completion Notes P10.2 — are not adjusted to zero).
- **maind MCP: tool-result trimming + PARTIAL-receipt (P3.2).**
  Single funnel `_content()` (`packages/maind/lib/maind/mcp.py`) aims lower
  warning-threshold Claude Code (10 000 tokens): (1) above the threshold is first removed
  `indent=2` (pure savings without data loss); (2) if compact JSON not
  fits - the largest top-level list is trimmed by binary descent with fair
  receipt (`truncated`/`returned_count`/`total_count`/`hint`), without branching by name
  tool. A response that falls within the threshold does not change byte-to-byte. Live frozen
  11 tools showed: removal `indent=2`
  is enough for all current fleet node responses (largest - `maind_projects_list`,
  ~8,3K evaluation tokens after unindenting against ~10,6K with them) — design path
  «(2) ceiling+receipt» code is covered and tested with synthetic fixtures, but
  on a live node does not work yet.
- **`review-gate`: gate with content instead of silent no-op (P9.1).**
  The content of checks has moved to `hooks/review-gate/checks/` (dispatcher `run-checks.sh` +
  `generated-assets`/`plan-lint` strict + `tests-touched` warn); `config.json` announces
  SET ONLY per-check mode, `check_command` — one stable call line
  dispatcher. Global `MODE=warn` lowers strict-class, not vice versa; loop protection -
  dispatcher counter (session, agent, check), third in a row strict-failure downgrades to
  `warn` with `systemMessage`. `apply-permissions.sh --global` puts `checks/` always and
  migrates `config.json` ONLY if it's a byte-for-byte old stub (otherwise - local
  selection, skip + exact command). `harness doctor` prints one of three states
  (`unconfigured (no-op)` / `configured: …` / `disabled (MODE=off)`) instead of silence.
  Live-running the subagent confirmed the semantics `exit 2` (forces you to continue, not
  interrupts) and removed `[UNVERIFIED]` about `stop_hook_active` (the field actually exists in runtime) —.

- **`CHECKPOINTED`: failure item'a must carry the exact resume command (P8.3,
  ).** Item with status `🔴 Blocked` could be closed by a report «not
  was able» no turning back. Media - string `Resume: <exact command>` in the field
  `Pending Work` item'a (NOT the seventh status and NOT the seventeenth field - both options are broken
  would be a contract `plan_lint.STATUSES`/`TERMINAL_STATUSES` and interplane gate
  `packages/task/scripts/cross-plan-files.py` on all living planes). Gate `plan_lint.py` — opt-in ONE
  TIMES (`Closure Protocol | v1`): `🔴 Blocked` without a non-empty command (form `Resume:
  — (external blocker: …)` is legal for a blocker without a local step) → ERROR with id item'a;
  `⛔ Skipped by decision` without EXACTLY `Resume: -` and links `D<number>` → ERROR.
  Delimited with form `waiting:`/`WAITING:` (this one is about the plan step, this one is about item). Canon -
  `plan-protocol` §6; literal `Resume:` in `CANON_LITERALS` + `i18n-keep`;
  instructions - `plan-exec.md` (escalation), `plan-close.md` (reconciliation) (skill
  `2.18.0 → 2.19.0`, units `core`/`general` + skiller package API `0.11.0 → 0.12.0`).

- **`**Consequences:**` in D-entries + capability maturity dictionary (P8.2,
  ).** D-log recorded the decision and reason, but not the price: canceling/
  replacing D-entry (`supersedes D#`/«cancels D#»/participle) now carries inline
  subfield `**Consequences:**` inside the cell `Solution` (fifth column rejected - header
  D-log canon-literal). Gate `plan_lint.py` — opt-in TWICE (`Closure Protocol | v1` +
  `Date` D-entries ≥ `2026-07-28`, forward-only — on a living tree measured predicate
  catches the only existing cancellation without `Consequences`, and backfill is prohibited for her);
  cancellation predicate/replacements - measured (`supersedes D`/«cancels D»/participle with
  negative lookbehind `(?<!not )`), and not specka verbatim (it caught zero records on
  plan for the sake of which the gate is introduced - the Russian participle declines). Second move -
  maturity dictionary OPPORTUNITIES (not item'a): EXACTLY five values - `available` /
  `experimental` / `behind-gate` / `disabled` / `superseded`, canon - `plan-protocol` §6,
  next to six statuses item'a (different axes: «item closed» ≠ «feature works»).
  Canon - `plan-protocol` §4 (D-log), §6 (dictionary); literal `**Consequences:**` in
  `CANON_LITERALS` + `i18n-keep`, cancellation system - in `HEURISTIC_LITERALS` (skill
  `2.17.0 → 2.18.0`, units `core`/`general` + skiller package API `0.10.0 → 0.11.0`).

- **Phase closing report `plans/<ID>/closure/<Pn>.json` (diagram v1) with certificate class
  (P8.1).** `## Phase Handoff` — prose plus git-hash: class
  evidence was not recorded anywhere, and synthetics were read as a result. Now the phase
  also comes with a machine-readable report: `evidence_class` — enum EXACTLY out of three (`real` /
  `synthetic` / `baseline_pending`), «no number» is expressed by a RECORD with a reason, not
  missing key. Turns on **opt-in** field `## 0. Meta` → `Closure Protocol | v1`
  (other value = ERROR); plan without a field is not affected by any diagnostics
  (additivity test). Writer - `plan-close <ID> Pn` (collects mechanically from the fields
  items); consumers are named and both are executed: `plan_lint.py` (diagram · `items[]` ↔
  `## Phase Status` · `phase_status` ↔ Status Board · `real` with empty proof ·
  terminal phase without file - ERROR with the expected path) and `plan-audit <ID> Pn` (first
  stage 1 input: rerun commands from `evidence` on `git.head_sha`, technical specification editing detection
  phases after closing `inputs_sha256`). Our `evidence_class` DIVERTED on one line
  canon with a closed list of proof classes `recomputed`/`cross-checked`/
  `pinned-not-recomputable`/`unknown` (`source-evidence-verification-v1.md`) — different axes,
  both dictionaries are valid. Canon - `plan-protocol` §8 + `snippets/closure-template.md`
  (skill `2.16.0 → 2.17.0`, units `core`/`general` + skiller package API `0.9.0 → 0.10.0`).

- **docs/plan — canonical docs synchronised and the measured-scope Owner decision
  packet assembled (P4.3).** Terminal item of the plan.
  Docs now state the three source layers explicitly — canonical (hand-written), generated
  (`skiller registry` / `render-provider-commands.py`, never hand-edited, drift repaired by
  regeneration) and effective (what the runtime actually resolves, read via
  `skiller doctor --effective-source`) — and print measured quality rather than rounding it
  to `ok` (`docs/control-surface.md`). `docs/task/plan-structure.md` gains the compiled
  portability tiers (`brief-acceptance` / `committed-bundle`), the classification rule and
  who applies it, the five lint rejections, the provenance-vs-execution-input test **by role
  rather than by spelling**, the five `committed-bundle` requirements (minimisation with
  named excluded classes; a deterministic manifest AND a committed verifier whose hashes are
  recomputed rather than trusted; complete dependency closure; one neutral semantic carrier
  whose Claude/Codex renderings are projections, never the source of truth; the proof-class
  rule) and the closed proof-class enum — plus the P4.4 machine gate on printed
  `pre_mutation:`/`pre_final:` codes. `docs/task/methodology.md` separates an audit verdict
  from plan acceptance, so a clean record can no longer be read as a met floor.
  `docs/reference.md` records the external `core`/provider architecture audit as adjudicated
  (3 accept → future proposals, 11 reject, 2 unknown) and `docs/rejected-optimizations.md`
  carries its three load-bearing rejections with the code that refutes them.
  `packages/analyst/docs/architecture.md` documents the two public modules the Contribution
  gate was paid for (`analyst.trace`, `analyst.metrics`) and why `plugin.json` does not
  follow `package.json`. Publication closure is proven by command, not by prose: task render
  `--check` and `skiller registry --check` both no-op, the diff-scope guard over adapters /
  bootstrap trees / both marketplaces exits clean, and the private
  `repository-bootstrap@0.2.0` unit is recounted from its own lock — 27 thin root
  projections (26 class-A + class-B `workflow-craft`), one combined lock, **zero** ordinary
  marketplace entries. The packet
   states in
  its first sentence that acceptance is formally NOT met, prints what is unproven as numbers
  (`F1 = 0.96`, `F10 = unknown`, declared subset 5/31, F6 on a denominator of 1, Codex side
  never attempted), lists every residual debt with a named carrier, records the rehearsed
  rollback and its measured cost (2/5 → 5/5 first-pass success would be destroyed), and asks
  exactly one owner decision (G1 go/hold) with a **hold** recommendation and falsifiable
  criteria that would change it. One honest gap is recorded rather than repaired:
  `scripts/provider-docs.py` — the generator/checker behind `docs/provider-support.md` —
  still reads /...` after that plan was archived, so it fails
  closed with `FileNotFoundError` and is wired into no `validate.sh`; that page is therefore
  **not** claimed proven closed, and the repair belongs to the script's owner.
- **skiller — read-only composed effective-source doctor
  (P4.2).** `skiller doctor --effective-source [--json]`
  composes five read-only diagnostics — active semantic owner/provenance/collisions
  (reused verbatim from the P1.4 gate, `run_effective_runtime_gate`, never re-derived),
  cache (a structural `n/a`: identity detection is repo-derived/cold, D44 — no provider
  cache/profile is read), reference/capability coverage (cites the committed P1.1
  capability-gaps finding), hook ownership (registration source × `.swissknifeman/
  provider-artifacts.lock.json` managed owner × handler locality, per
  `semantic-identity-ownership-v1.md` § Hook identities) and trace-quality (cites the
  committed P3.11 measured scope — declared subset 5/31, `F1=0.96`, `F10=unknown` —
  printed measured, never rounded to `ok`). Each diagnostic carries owner/source/status/
  evidence/quality/`next_command`; `build_effective_source_report` fails closed on a
  missing key or an out-of-vocabulary status. No new public subcommand or write path
  (Scope Excluded, D92): an extension of the existing `skiller doctor` facade only,
  proven no-write by `git status --porcelain=v1` before/after in Validation.
- **analyst/harness — Contribution gate minor bumps paid (P4.5,
  , `analyst@0.2.0`, `harness@0.4.0`).**
  Package-API minor bumps owed by `unified-agent-trace-v1.md` § Contribution gate —
  `analyst 0.1.0 → 0.2.0`, `harness 0.3.0 → 0.4.0` — were recorded as debt in P3.1
  Pending Work / P3.2 Completion Notes (the contract's own consumer-surveyed SemVer/ADR
  result) but left unpaid because `package.json` sat outside those items' declared
  `Files`. This item pays exactly that debt: `analyst`'s bump reflects the new public
  module `analyst.trace` (P3.1's normalized `TraceRecord` schema owner) plus
  `analyst.metrics` (P3.2's paired reliability digest layer); `harness`'s bump reflects
  the new public module `harness.provider_trace` (P3.1's thin Claude/Codex readers).
  Neither package's `.claude-plugin/plugin.json` moves — that is a separate publication
  surface not derivable from `package.json` (measured: `harness` package `0.3.0` sat
  against plugin `0.2.0` before this bump) — and no generated artifact drifts
  (`skiller registry --check` and diff-scope guard both confirm a no-op).
- **task/general — machine gate for printed pre_mutation/pre_final boundary codes
  (P4.4,, `plan-protocol@2.15.0`, `skiller@0.8.0`).**
  `plan_lint.py` gains a new rule: a `🟢`/`🟠` item whose `Updated` cell (Phase Status
  table) is ISO-dated `≥ 2026-07-27` must print BOTH `pre_mutation:`/`pre_final:` codes
  in its Completion Notes, and both must read `allow` (D76: `n/a` is not green) — a
  missing code, or a code other than `allow` on either boundary, is now an ERROR
  instead of a prose checklist item (`plan-audit.md`) an auditor has to remember to
  recompute by hand. Repairs `findings/P3.11-terminal-audit-2.md` § F2 (reopen of F3,
  event 2 of 2): five consecutive items (P3.6-P3.10) closed `🟢`/`🟠` after the
  write-site canon already existed without ever printing the codes — the gate itself
  held (the audit's own recomputation of the predicate on all five returned
  `allow`/`allow`) but the RECORD was silently absent, and a real `block:*` under a
  `🟢` would have stayed invisible until the next audit, which this phase no longer
  has. The scope anchor is the ITEM's own `Updated` date, not the plan's — a
  plan-dated cutoff would miss this very plan's own future `P4.*` items; items
  closed before the cutoff are never diagnosed at all (forward-only, no existing
  fleet plan is repainted retroactively). `plan-protocol` §8 canon gains one line
  (both languages) naming the machine check; `pre_mutation:`/`pre_final:` are
  registered in `CANON_LITERALS` with matching `i18n-keep` directives (test T2).
- **skiller — system-bank adapter for the P0.3 reliability bank (P3.3,
  ).** `skiller.quality.eval` gains a second,
  distinct deterministic grading vocabulary alongside its existing per-skill
  `ASSERTION_TYPES` (which grade one free-text string): eight structured
  transcript/outcome operators (`event_present/absent/order/count_max/
  count_min`, `outcome_field_equals/list_contains/list_excludes`) matching
  `reliability-acceptance-v1.md` § Graders exactly — no LLM judge anywhere in
  this path. `apply_system_operator`/`grade_system_case` grade a case
  against a structured transcript+outcome record; `validate_system_graders`/
  `validate_system_cases` structurally validate ANY `reliability-bank/v1`-
  shaped document, not only the frozen P0.3 one; `compute_system_metrics`
  reimplements (independently of, never importing) the frozen bank's own
  `run_bank.py::compute_metrics` — so this regression surface survives the
  plan's own eventual archival — and is verified **byte-identical** against
  `bank-manifest.json::layer1_metrics` (zero mismatches across ten metrics
  plus `same_finding_loop_depth`) when run against the real 31-case bank.
  `seeded_system_sample` reproduces the same `sha256(seed|case_id)`-ascending,
  baseline-passing selection rule the frozen bank uses — confirmed to
  reproduce `bank-manifest.json::sample.selected` exactly (the same five
  control cases). `provider_capability_matrix` is a deliberately narrow
  presence-only Claude/Codex probe (native only on resolved binary — an
  unconfirmed capability must fail closed, D46, never claim more). `classify_
  portability_tier` cites `task.task_contract.classify_tier` via an optional
  import (mirrors `analyst.doctor`'s existing `task.route_evidence` pattern;
  returns `(None, reason)` rather than guessing when `task` isn't importable).
  `pair_system_metric` mirrors `analyst.metrics.pair_metric`'s discipline
  (candidate `None` → `deferred`, a `pinned-not-recomputable` baseline can
  never ground a comparison) as its own small local implementation, per that
  module's own stated cross-package-boundary rule. `build_system_benchmark`
  orchestrates all of the above into the P3.3 benchmark artifact
  (+
  `benchmark-manifest.json`, generated against the real frozen bank,
  candidate-less/`deferred` — no live paired (layer-2) transcript-capturing
  harness exists yet for the bank's multi-round, typed-event cases; that gap
  is named as Pending Work, not fabricated). Two new local test fixtures
  (`packages/skiller/tests/fixtures_data/system-reliability-{bank,graders}-
  v1.json`) exercise all eight operators and every `compute_system_metrics`
  path without touching the frozen plan-owned bank.
- **analyst — reliability metric arithmetic and paired digest (P3.2,
  ).** `analyst.metrics` derives paired reliability
  metrics only from committed `analyst.trace.TraceRecord`s and the frozen P0.3
  reliability bank, never by re-parsing provider logs a second way. `build_metric_record`
  emits the numerator/denominator/exclusions/completeness/source-trace-IDs/baseline-proof-
  class shape every metric must carry; `pair_metric` pairs a baseline against a candidate
  (or `None` when the P3.3 live paired run has not produced it yet — reported `deferred`,
  never a silent zero) and fails closed (`METRIC_PINNED_BASELINE_FORBIDDEN`) if the
  baseline's proof class is `pinned-not-recomputable`/`unknown`, so a historical pinned
  quantity (e.g. `journals.classified_lifecycle_events`) can never be silently promoted to
  a recomputed comparator. `slice_by` groups by project/plan/item over a caller-side
  `{project_id, trace}` wrapper — the frozen `TraceRecord` carries no `project_id` field of
  its own, so slicing does not widen that closed schema. `build_digest`/`digest_to_json`
  produce the one compact, byte-stable JSON shape Code Guidance asks for (no dashboard, no
  ranking). `findings/P3.2-metric-reconciliation.md` reconciles this against the committed
  P0 bank: the four already-recomputed layer-1 floors it can re-express today (F1/F7/F13/
  F14) all resolve to `deferred` pairs (no layer-2 candidate exists yet), and F6
  (`trace_completeness`) gets its record shape with `value=None` rather than a fabricated
  pass — no new central `analyst <cmd>` is wired (`cli.py` is outside this item's declared
  `Files`); `doctor.py`/`test_provider_readers.py`/`test_cli.py` were declared in scope but
  left untouched for lack of a concrete requirement against any of them.
- **analyst/harness/task — Unified Agent Trace v1 (P3.1).**
  New versioned, stdlib-only trace schema

  links a requirement to its contract identity, route, dispatch state, findings and
  public outcome in one closed-field record, distinct from the unrelated D90
  normalized analytics envelope (`analyst.events`/`runs`/`readers`). `analyst.trace`
  is the sole schema owner: `build_trace_record` validates provenance/sha256, fails
  closed on any raw key plausibly carrying chain-of-thought/tool-payload/secret
  content (`TRACE_PRIVACY_VIOLATION`), scores `quality.completeness` over six nullable
  field groups with an explicit `reasons` entry for every missing one, and
  `dedup_records` collapses resumed/forked duplicates by a natural-key `trace_id`
  (provider/project/session identity/turn), keeping the higher-completeness record.
  `harness.provider_trace` supplies thin Claude/Codex readers that map already-
  captured provider structures into the RAW payload the schema owner consumes — no
  Codex hook in this repository captures a comparable structure yet, so every
  Codex-sourced field degrades to `null` + `codex-hook-not-integrated` rather than a
  guessed value. `task.journal` gains one additive optional `trace_ref`/`--trace-ref`
  linkage (outside `REQUIRED_FIELDS`; a call that omits it writes a byte-identical
  entry to before this field existed) so a journal line can point at a trace identity
  without duplicating its metrics. `analyst`/`harness` package-API minor bumps
  (`0.1.0`→`0.2.0`, `0.3.0`→`0.4.0`) are owed but deferred to the next item touching
  those manifests — `package.json` is outside this item's declared `Files`.
- **task/general — pre-final boundary closes fail-closed on both closing paths
  (P2.11 reopen-remediation,, `task@0.9.0`,
  `plan-protocol@2.14.0`, `skiller@0.7.0`).** `task:plan-close`'s pre-final
  checkpoint (step 4) no longer greenlights `n/a`: the gate is now the binary
  `pre_mutation == "allow" and pre_final == "allow"`, with `n/a` reported by
  its own code→action table row spelling out the contract-SSOT semantics
  ("a blocked session has nothing to declare done") — before this fix the
  literal `in ("allow", "n/a")` predicate greenlit every real item, because
  the actual route substituted was the closing command's own pin
  (`implementation/low`), below every item's required route, so
  `pre_mutation` always failed and `pre_final` always reported `n/a` (M1,
  `findings/14`). The `actual_route` on pre-final is now resolved as the
  item's EXECUTOR route via a fail-closed ladder — Completion Notes
  routing-adherence line, cross-checked against the item's terminal
  `journal.jsonl` entry — instead of the closing command's pin; an
  unresolvable or mismatched route stops with a named PASS rather than
  guessing. `task:plan-exec`'s own step 7 (routine self-close — the path most
  items actually take) gains the SAME executable pre-final call: before this
  fix the boundary was never crossed there at all (M5) — `plan-exec` closes
  the item itself and `plan-close Pn.m` is never invoked on that path.
  `plan-run.md` and `plan-audit.md` are synced to the same binary gate and
  dual-boundary reporting requirement. Both checkpoints now name what
  `pre_final` actually asserts: a property of the item spec's FORM —
  whether at least one publicly checkable acceptance entry rests on a
  deterministic proof class — never that the item was executed well. §13 of
  `plan-protocol` (both languages) is rewritten to state all of this
  truthfully, and the literal test in `test_canon_literals.py` gains a new
  class asserting the DIFFERENTIATING predicate rather than mere
  identifier presence — every new assertion was verified red against the
  pre-fix command bodies before being added (M6: the pre-existing literal
  test passed green through the `n/a` and missing-step-7-call defects both).
- **task — compiler reads all §3 Routing forms and never crashes
  (P2.10 reopen-remediation,, `task@0.8.0`).**
  `task_contract._find_routing_row` now recognizes a closed literal set of
  route-column headers — the canon `Model class/effort` plus the two legacy
  spellings `Model/effort`/`Model/Effort` `plan-protocol` §9 Back-compat already
  declares valid — instead of the single hardcoded canon header (D78:
  `findings/14` M4/M4.1 measured 11 of 14 root `plans/` failing this call, 9 of
  them with an unhandled `ValueError`). A provider model name in the cell (the
  FOREMAN §3 form, e.g. `opus/high`) is resolved to its frozen class ONLY
  through the committed `command-routing.json::mappings.*.class_selectors`
  carrier (`command_catalog.load_routing_metadata`) — never a second name
  table. Every unparseable/unrecognized/ambiguous form now raises
  `TaskContractBuildError` naming the item, field and offending cell instead of
  fabricating an empty `required` route or crashing; `pre_mutation`'s own
  `_rank` lookup is guarded on both axes and both sides of the route (closing
  D74's `.index(None)` root cause defensively, for any contract reaching `check`
  regardless of producer) and returns the frozen `ROUTE_UNDERSHOOT` code rather
  than raising. New committed probe

  reproduces the walk over all 14 root plans and exits 1 on any unhandled
  exception (none observed after the fix — 9 `ok`, 5 typed refusals, 0 `EXC`).
- **task/general — Task Contract write-site and truthful canon
  (P2.7 reopen-remediation,, `task@0.7.0`,
  `plan-protocol@2.13.0`, `skiller@0.6.0`).** `task:plan-exec`'s pre-mutation
  checkpoint and `task:plan-close`'s pre-final checkpoint now CALL the P2.6
  compiler — an executable step (build a live Task Contract v1 payload via
  `task_contract.build(..., actual_route=…)`, evaluate it, fail closed on any
  non-`allow` code with a named code→action table) — replacing the F1 prose-only
  cross-reference and the always-false "when a Task Contract JSON happens to be
  mounted" condition. `task:plan-run` substitutes the session's observed route;
  `task:plan-audit` gains a checklist bullet requiring the printed
  `pre_mutation`/`pre_final` result in a closed item's Completion Notes. §13 of
  `plan-protocol` (both languages) is rewritten to state this truthfully and is
  now protected by a literal test in `test_canon_literals.py` that fails if the
  wording diverges from the command bodies. New
  `snippets/source-evidence-template.md` delivers the evidence-bundle Files
  entry P2.2 left undelivered — manifest structure, required fields,
  verification command via `task_contract.bundle_lint`, and the
  explicit forbidden-content-class list — cited from, not duplicating,
  `plan-portability-v1.md` §Bundle requirements (also newly cited by the
  canon). Discovered along the way: the CLI form `task_contract build` (no
  `--actual-route` flag) always leaves `route.actual` unresolved by design
  (cross-process determinism) — feeding that straight into `check` crashes
  `pre_mutation`'s `ROUTE_UNDERSHOOT` check with an uncaught `ValueError`
  (`.index(None)`), so the write-site calls the compiler's documented Python
  API (`build`/`evaluate`) instead of a literal `build | check` shell pipe.
- **task — compiler producer, bundle predicate, cross-session cap, actor repair
  (P2.6 reopen-remediation,, `task@0.6.0`).**
  `packages/task/lib/task/task_contract.py` gains `build(plan_dir, item_id, …)`
  — the Task Contract v1 PRODUCER a transaction can actually call before
  `pre_mutation`/`pre_final` existed only as predicates over a hand-authored
  JSON: compiles `phases/Pn.md` + `plan.md` §3 fields into the exact 15-key
  schema, deterministic across repeat calls on the same committed tree, and
  fails closed with a typed `TaskContractBuildError` on an empty item field
  rather than fabricating a placeholder. Full field mapping:.
  `bundle_lint(bundle_dir, …)` computes minimization and content-class evidence
  (secrets/chain-of-thought/tool-payloads/raw-transcript-bodies, by signature
  scan over actual bundle bytes) instead of trusting a self-declared
  `portability.privacy` block, two new reason codes
  `BUNDLE_ARTIFACT_MISSING`/`BUNDLE_PRIVACY_MISMATCH`.
  `packages/task/lib/task/review_policy.py`'s `LoopBudget` gains
  `from_committed(plan_dir, phase_id, finding)` — reconstructs one finding's
  cross-session occurrence count from `journal.jsonl` + `## Audit Pn` blocks
  instead of always starting a fresh in-process counter at zero (the exact
  defect that let three independent `plan-audit` rounds each see
  `occurrences() == 0` for the same recurring finding). `canonical_actor`
  (`route_evidence.py`) is a breaking signature change: it now carries the
  concrete provider MODEL (`sonnet/high`), never the route-evidence class —
  `model_class` stays a separate `route.actual` axis; `capture_actual` gains
  an optional `model` evidence field; `journal.py --route-evidence` repaired
  to match (a historical evidence blob lacking `model` renders `unknown/…`,
  never crashes).
- **task — route/budget evidence (P2.4).** New
  `packages/task/lib/task/route_evidence.py`: normalized `required`/`actual` route
  capture with a named source (`self-attested`/`provider-doctor`/`cli-flag`) and
  timestamp — never inferred from static config, an actor string or the requested
  model. `classify` gives the four-way `exact/over/under/unknown` label (one axis
  never compensates the other — an unresolved model class outweighs a generous
  effort); `dispatch_guard` is the fail-closed boundary strictly upstream of
  `task_contract.pre_mutation` — it reuses the two frozen P0.2 `route` deny
  codes verbatim (`ROUTE_UNDERSHOOT` also for an `unknown` axis, `CAPABILITY_UNSUPPORTED`)
  and is what prevents that predicate's `.index()` lookup from ever seeing a `None`.
  `build_task_contract_route` assembles the exact `task-contract-v1.schema.json`
  `$defs/route` shape once the guard already allowed. Also: `capture_budget`
  (token/duration/tool-call evidence only, no pricing — axis names match
  `analyst.readers` `usage.totals`), `route_change_boundary`, and
  `canonical_actor` — the one `<model_class>/<effort>` journal actor spelling
  (`findings/02-telemetry-2026-07-20-24.md` — 34 observed spellings). `task.journal
  append` gains `--route-evidence PATH` (mutually exclusive with `--actor`) to derive
  the actor from a captured evidence file instead of hand-typing it. `harness doctor`
  and `analyst doctor` each gain one informational/optional line naming where route
  evidence can come from (`analyst doctor`'s is the existing `task.route_evidence`
  importability pattern already used for `maind`).
- **task — typed finding/review enforcement and loop breaker (P2.3,
  ).** New `packages/task/lib/task/review_policy.py`
  implements `risk-review-loop-budget-v1.md` as executable policy: seam-derived
  `finding_id` (file/rule-locus/defect-class, split-ban — cosmetic re-wording never
  resets the loop-budget cap), the `reopens_product` predicate (product-typed, security
  blocker, or evidence invalidating acceptance), and `same_finding_max = 2` — the third
  occurrence of one stable identity becomes an `INCIDENT` with no inline repair, its cap
  subject parameterized by authority profile (`owner-gated` → owner, `self-host` → agent,
  never hardcoded). `task_contract.py` gains one lazy-imported hook,
  `evaluate_finding`, so the independently-green compiler's own tests never need the new
  module importable. Task plugin/routing bumps `0.4.0` → `0.5.0`; full adapter/lock/golden
  regeneration proven no-op on the second check.
- **task — Task Contract v1 compiler and tiered-portability lint (P2.2,
  ).** New `packages/task/lib/task/task_contract.py`: the
  single checked seam owning content-hash recomputation, the precedence/conflict-resolution
  ladder, the twelve pre-mutation and three pre-final reason codes of
  `task-contract-v1.md`, plus the portability tier classification/lint layer of
  `plan-portability-v1.md` (`PORTABILITY_TIER_MISCLASSIFIED`). Canonical plan commands
  (`plan-design`/`plan-exec`/`plan-close`/`plan-audit`) now cite this compiler at their
  pre-mutation/pre-final checkpoints instead of restating the predicate in prose.
  `plan_lint.py` gained a tiered-portability check (role-based — never a `tmp/` substring
  match, D47) that rejects a committed-bundle-tier plan without a committed execution input
  or with an external (host/chat/mAInd/tmp/foreign) one; severity is ERROR only for plans
  dated `2026.07.27` or later (back-compat, existing fleet plans stay WARNING). Versions:
  `plan-protocol@2.12.0`, skiller package API + `general`/`core` publication units to
  `0.5.0`, task plugin/routing to `0.4.0`.
- **skiller — effective-runtime conformance gate.** New
  `skiller doctor --effective-runtime`: cold per-provider install/discover of the declared
  positive fixture (every repository-marketplace unit minus exactly the three donor buckets
  `general`/`research`/`oss-dev`) into a `tempfile.TemporaryDirectory`, proving catalog-wide
  identity uniqueness (216 Codex / 204 Claude identities, 0 collisions, 0 undeclared root
  directories) rather than checking a named ID list. A companion negative fixture proves the
  nine `core`↔donor D42 pairs and the class-B `workflow-craft` precondition still fail
  closed when their donor bucket is enabled. `--fixture-out`/`--carrier-out` persist the
  declared fixture (`fixture-unit-set.json`) and the measured identity→carriers map
  (`effective-carrier-set.json`), the latter reconciling every one of the 29 frozen
  collision records from P1.1's `remediation-map.json` as `resolved` or `still-measured`
  (0 `unowned-or-unexplained`).
- **skiller — root-bootstrap class-B publication and collision closure.**
  Four duplicate `architect` root identities (`architecture`, `codebase-design`,
  `domain-modeling`, `package-contribution-protocol`) removed from `.agents/skills/` after
  per-identity ownership proof against the installed `architect` bucket unit. `workflow-craft`
  (public-bucket canon whose unit is not enabled) gets a generated thin Codex-only root
  projection with provenance/hash under a new class-B extension to the root-bootstrap
  renderer — declared asymmetry, no copied body, no Claude projection. `repository-bootstrap`
  publication unit bumps `0.1.0` → `0.2.0` (`skiller` package API `0.4.1` → `0.4.2`); the 13
  class-A canonical sources, their 26 projections and lock bytes stay byte-identical (a new
  D38-frozen `class_a_content_version` decouples the class-A embedded stamp from the umbrella
  unit version). The generator and `skiller registry --check` now assert each provider's root
  skills directory equals exactly the declared target set (undeclared directory → hard
  failure). `skiller doctor --provider-distribution` gains a read-only D42 diagnostic naming
  every identity the curated `core` unit shares with a donor bucket (`general`/`research`/
  `oss-dev`) under the worst-case declared set — never a live-profile read, never a repair.
- **plan — agent reliability and SSOT recovery.** Added executable plan
  : field root-cause model for four projects,
  single task contract, runtime-dedup skills/hooks, bounded review loop,
  unified traces, behavioral evals and self-host canary to fleet-gate.
- **harness/core — dual-provider environment and instruction projections.** Provider-neutral
  profile, security, hook, MCP, agent and instruction catalogs now render independent native
  Claude/Codex artifacts. Artifact contract v1.1.0 preserves generic semantic metadata in the
  authoritative lock while exact v1.0.0 callers and records remain supported.
- **task — dual-provider command surface.** Immutable semantic command catalog,
  generated Codex adapters, byte-compatible Claude projection, fail-closed neutral
  routing and exhaustive parity/operator reference for the full task inventory.
- **skiller — `plan-protocol` 2.11.0.** Semantic `Next`, model class/effort/capability
  gates and provider-rendered Claude/Codex invocations are now provider-neutral.
- **skiller:** provider-aware Claude/Codex distribution preflight, provider-qualified
  vendor locks and explicit `skiller codex-install`; normal connect/update/doctor and
  dry-runs never invoke the native user-global installer.
- **task/harness — root task-adapter dedup.** `task` publication bumps to
  `0.3.1`: regenerated Codex adapter tree (24 artifacts), `provider-artifacts.lock.json` and
  `publication-lock.json` via a new stdlib CLI front
  (`packages/task/scripts/render-provider-commands.py --write --repair-owned` /
  `--check`) wrapping the existing `command_render.py` planning/apply API — no new
  translation logic. Six duplicate root task identities
  (`task-design`, `task-plan-{audit,close,design,exec,run}`) removed from `.agents/skills/`
  after proving the generated `task@0.3.1` bundle covers them. `harness` package bumps to
  `0.3.0` (plugin `0.2.0`) alongside. `AGENTS.md` now describes `.agents/skills/*` as
  generator-owned bootstrap-only projections for identities not served by an authoritative
  installed bundle, sourced from the private `repository-bootstrap` bucket.
- **skiller — root-bootstrap class-A publication.** 13 private/source-only
  bilingual canonical skills (`skills/repository-bootstrap/<id>/{SKILL.ru.md,SKILL.md}`)
  replace the 13 hand-maintained duplicate root copies with 26 thin generated
  `.claude/skills/<id>/`+`.agents/skills/<id>/` projections (trigger metadata + canonical
  path/hash, no copied body) plus one combined `publication-lock.json`. `registry.py` →
  `publication.py` is the sole producer; `build_publication_catalog` excludes the private
  bucket from every ordinary Claude/Codex/marketplace unit and `skillset.py` rejects it from
  vendor/connect selection outright. `configs/publication-versions.json` now separates
  the skiller package API SemVer from finite per-unit manifest versions — `core`/`skm` bump to
  `0.4.1` alongside the package API, every other unit stays byte-identical at the frozen
  `0.4.0` baseline. Six duplicate root `core` identities
  (`anti-drift`/`context-economy`/`plan-protocol`/`query-craft`/`session-handoff`/`verify-claims`)
  removed from `.agents/skills/` after proving the generated `core@0.4.1` bundle covers them.

### Fixed

- **harness/maind — self-host Codex hook lifecycle: unmanaged target and missing
  handler.** `.codex/hooks.json` carried only handwritten memory-hook outside artifact lock
  (`harness hooks --provider codex --observer` refuted as `ownership-conflict`), a
  observer `context.observer` was not registered at all - `harness doctor`
  reported `missing → create`. Composition through an existing D104
  bootstrap-transfer (`maind.provider_deploy.plan_d104_bootstrap_transfer`) saved
  memory-hook byte-by-byte and added an observer second `SessionStart`-hook +
  `.codex/hooks/lifecycle.py`; `.swissknifeman/provider-artifacts.lock.json`
  now owns both. `run-report/_lib.py` in `~/.claude/hooks/` synchronized
  repeated `harness hooks --global` (went bad after the last update).
- **harness — protracted stale path after archiving.**
  `instructions.py:contract_path()` and one test fixture carried the way to
  plan archiving (`5b79f926`), because of what `test_provider_instructions.py`,
  `test_instruction_compatibility.py` and `packages/harness/scripts/validate.sh`
  crashed completely regardless of the current task. Path synchronized to
  /...`.
- **harness — `agent-packs upgrade` checks the fact of the files, and not just the version of the pack.**
  The upgrade plan is built from hashes (source and drive against `base_sha256` loka), therefore
  forgotten bump `pack.json:version` no longer gives silent «is already relevant» (change
  arrives + warn to the author of the pack), and the missing one target is restored even if the version is equal.
  The matching state is printed as «nothing to do»; local edits still fail
  are overwritten (`conflict` → `*.pack-new`). `agent-packs doctor` additionally warns
  o targets, claimed by 2+ installed packs (root of silent file loss when
  `remove` neighbor), and gives them to `--json` field `shared_targets`.
- **skiller — single Codex carrier when update.** If the external project is already receiving
  self-contained Codex marketplace under `.agents/plugins/`, `skiller update`
  updates independent Claude vendor-channel, but no longer duplicates the same
  skills and lock-entries in `.agents/skills/`.
- **skiller — idempotent vendor sync.** Unchanged skill manifest saves
  original `installed_at`, therefore repeated dual-provider `sync` no longer changes
  snapshot when transitioning between seconds.
- **maind — current schema Serena.** Generator `.serena/project.yml` uses
  canonical key `language_servers`; multilingual and empty configurations more
  are not created legacy `languages`, which Serena migrated upon activation.
- **skiller — external Codex connect bundle.** Repo-contained bundles selected
  plugins now include runtime-skill files with consumer exclusions; native
  install/cache/enable remain a separate explicit action.
- **core/harness/maind — clean-runner compatibility.** D108 tests now use a committed sealed
  MCP preimage instead of a gitignored local file; harness agent-pack and maind provider-config
  projections import on Python 3.9, and the provider rollback/deploy paths pass the Ruff gate.
- **core/harness/maind — provider project sync.** Managed provider-artifact locks now
  retain records owned by other packages; Codex observer deployment, agent templates and
  provider MCP projection preserve independent managed surfaces during check/apply/repair.
- **task/skiller — Codex plugin activation.** The native marketplace now publishes
  package-owned Codex siblings with a Codex-compatible local source shape; `task` 0.3.0
  includes its generated `task-plan-*` skills, versioned provenance and cold-session coverage.
- **skiller:** dual-provider `sync` now rejects an unmanaged selected-provider target
  before any provider skill copy, lock write or project registration; `--force` remains
  the explicit overwrite path.

### Added

- **task — historical journal exception v1.** Owner-gated append-only sidecar for one exact
  historical `friction` schema error; strict writer/linter validation and negative tests.
- **skiller — `plan-protocol` 2.9.0 → 2.10.0.** Documents the sealed D51 exception lifecycle.

### Added

- **skiller — `plan-protocol` 2.8.0 → 2.9.0.** Scope-payload launch-block'and for `RED`/`ATTENTION`
  audits (`MODE:`/`ENTRANCE:`/`SCORE:`/`DO NOT TOUCH:`), literal `Verdict:`; log
  `journal.jsonl` and optional `index.md` in plan layout; snippets
  `journal-template.md`, `index-template.md`.
- **skiller — `check-translations.sh`.** Two-way gate `i18n-keep`: literal must be
  used in the body `SKILL.ru.md`, not only in the directive.
- **task — `plan_lint.py` + `plan-audit.md`.** Gates scope-payload in blocks `## Audit Pn`,
  validation `journal.jsonl` (ERROR from 07/2026/18) and `index.md` (WARNING); unittest's.
- **docs — `reference.md`.** Cards gstack, last30days-skill, llm-council, codex-plugin-cc;
  roadmap `codex-subagent-offload.md`, `plan-design-vs-exec-status-check.md`.

### Added

- **task — skill `plan-protocol` 2.4.0 → 2.7.0.** Cluster summary (F7/m7/m8/A5/B1, escalation REGHUB):
  **2.4.0** — routing-gate (§9 column `Exec`: `plan-exec`/`manual`/`plan-design`, derivation by
  shooting range model/effort), status-rule §6 (material vs process-deviations, 6th trigger -
  extraneous diff in item-commit), enum forms `Next` + closing order §8 (diff → validate →
  bookkeeping → handoff → `plan-lint` → attributed account → commit), section Contracts §7/§11
  (Exported/Consumed, cross-plan notification), fork carrier `## Discussion` §3. **2.5.0** —
  gate for untranslatable literals (`CANON_LITERALS`) + mandatory tree anchor for numbers in
  Completion Notes/Validation/Update Log. **2.6.0** — command canon-text `plan-{exec,close,audit,
  design,run}` (§13). **2.7.0** (rheopen wave) — predicate «Phase Handoff rotten» is checked against
  FIRST line + negation (not substring), the only bearer of phase status is Status Board
  (not Phase Handoff), linter gates are executable on their artifacts + extended root picker,
  numbers from ALIENS roots `plans/` — only by the delta of a paired run in one image, form `Next`
  first line + phase existence `after Pn.m` in handoff. **2.8.0** — «soft item
  Validation» (soft-TK mark, removing the red point without escalation) explicitly prohibited: red
  item Validation ALWAYS material (§6) or escalation to new owner D# (§10); OQ-1 plan
  closed D58.
- **task — `plan_lint.py`.** Synchronized with skill: enum forms `Next`, `--baseline`/`--gate`,
  section matching Contracts, regression on 30 live plans in 10 roots `plans/` — 0 new ERROR.
- **skiller — default change auto-approve `strict` → `bypass`** in bundles `recommended`/`full`
  (owner's decision, `365079c`).

## [0.9.0] - 2026-07-12

### Added

- **maind — digest-budget project-only + byte-cap.** `select_digest_items`: byte budget for
  memory digest + `shared_max=0` default (D10 supersede D5) — cross-project (`ns:*`) facts in
  digest is not received without an explicit request; `--shared-max`/config-flags for point enablement.
- **maind — quiet health-hook + digest-template v2.** `session-start-hook.sh` no longer prints
  nothing at OK (only `--strict` gives rc-gate); `memory-digest-hook.sh` — compact template v2.
- **maind — cross-project memory guideline.** `ecosystem-mcp` + docks `guide/{memory,namespaces}.md`:
  cross-project task → `graph` → `recall --scope ns:<name>` → `remember --scope ns:<name>`, digest -
  only project-only.
- **harness — agent-router policy v2.** Policy-config compressed to ter-EN ≤400 current (was RU ≈600–900
  current every session), semantics (6 routing invariants) saved completely.
- **skiller — diet of skill descriptions + desc-gate.** 24 the longest descriptions have been shortened;
  new hard gate `validate.sh` (`DESC_WARN_MAX=300`/`DESC_ERROR_MAX=450`) + burn-down-ratchet
  (`scripts/desc-burndown.txt`, one-way, rotten recording - warn) for the remaining skills.
- **harness — diet agent-packs.** Descriptions of subagents of all 10 packs are compressed (1 example instead
  2–3 + one anti-trigger phrase), regression cap-test on a real registry + `.bak`-warn in `agent-packs
  doctor`.
- **skiller — `budget --first-turn`.** Metering always-on footprint of the first move project: skills
  tier-0, agents, CLAUDE.md/rules without paths, alive fail-soft run SessionStart-hooks, MCP tool-defs;
  verdict OK/ELEVATED/WARN (thresholds 7K/10K), `--json`/`--strict`.
- **maind — `doctor --context`.** Fleet aggregation `_fleet_context`: subprocess `skiller budget
  --first-turn --json` for all `_enabled_projects`, fail-soft `n/a` when unavailable.
- **analyst — session token analytics.** `core/usage.py` — `first_turn_overhead` (first
  assistant-entry, main transcript); run-report `usage.first_turn_overhead`/`usage.turns`; new
  command `analyst sessions [--project ID] [--weeks N] [--json]` — weekly ISO-medians from living
  transcript-jsonl with trend-warn (week-over-week >20%, only calendar adjacent weeks).
- **root — bootstrap-machine.sh.** Idempotent script for deploying a new machine/commands
  (`swissknifeman setup --machine`): install → hooks/permissions --global → MCP soft-skip → maind
  service install → doctor, plus manifest-step `--projects FILE` (clones only missing ones
  projects, does not affect existing ones); `docs/deploy.md` + `docs/machine-manifest.example.json`.
- **root — doctrine budget-gate.** root CLAUDE.md «Frames»: any new always-on injection (hook
  additionalContext/description skill-agent-team/CLAUDE.md-block/MCP-server) passes before rolling
  `skiller budget --first-turn` and fits into budget (target 3–7K, warn 10K); compact entry in
  memory mAInd (`ns:axioma`).
- **Local skills/docks are synchronized with the release.** `package-architecture`/
  `project-tooling-runbook`/template `ecosystem-setup` (maind) + CLI-docks `analyst`/`maind`/`skiller`
  added new commands (`budget --first-turn`, `doctor --context`, `analyst sessions`,
  bootstrap-machine); outdated wording «digest top 8» (without `project-only`-disclaimers) in
  `docs/develop.md` fixed.

### Changed

- **P5.4 (OTEL-preset) — ⛔ Skipped by decision.** Without a working external collector - dead
  code; speck saved in a roadmap note. New catalog `docs/rejected-optimizations.md` —
  consciously rejected ideas (not «deferred», like `roadmap/`).


### Added (maind — fleet-measurement settings)

- **`maind doctor --audit settings|all`**: measurement `settings` in fleet-audit - subprocess to
  `harness doctor --settings --target <path> --json` for each registered project
  (D10, maind does not import harness). Fail-soft like `--channel-drift`: harness not available/fell/
  gave not-JSON → `settings·n/a`, audit return code does not change. Print: `settings✓` (zero
  error/warn) · `settings⚠(err:N warn:M)` · `settings·n/a`. `--json` puts `{"error","warn","info"}`
  or string `"unavailable"` to the project line.

### Implemented (settings-doctor — SKM-ROADMAP-005 P1 closed)

- Settings conflict-linter Claude Code (a roadmap note) is fully implemented:
  taxonomy 13 checks, 2 policy-profile, CLI `harness doctor --settings` + facade
  `skiller doctor --settings` + fleet `maind doctor --audit settings`. Field case 2026-07-10
  is caught entirely (integration test P1.5); real fleet run (21 project) confirmed.

### Added (harness — settings-doctor CLI + facade skiller)

- **`harness doctor --settings [--target P] [--json] [--profile NAME]`**: engine output
  settings-doctor in CLI. Branch separate from environment diagnostics (early return): reads
  settings layers Claude Code of the target project, reports the taxonomy of checks in a human-readable way
  report or single JSON-document. exit-code `0` (clean/only info) / `1` (warn) / `2`
  (error); `--json` does not change the code and prints EXACTLY one document per stdout (contract for
  fleet-scan). Audit read-only — does not write anything to disk.
- **`skiller doctor --settings [--target P]`**: facade of the same audit from the skill registry -
  delegates to `harness doctor --settings` via subprocess (without check logic), throws
  return code; harness not installed → warn and graceful skip (rc 0).

### Added (skiller — ecosystem-reuse-gate + bucket axioma)

- **`architect/ecosystem-reuse-gate`**: gate against reinventing functionality - before
  designing a new project/features must be verified with the ecosystem registry and run
  vendor-vs-build rules (default - reuse). `tech-stack-selection` and `founder/new-project`
  received `requires: [ecosystem-reuse-gate]` and gate calling step in the algorithm (Step 1 / Step 0
  Idea-gate).
- **Bucket `axioma`**: `axioma-doctrine` (five pillars-imperatives of the ecosystem Axioma) +
  `axioma-stack` (binding reuse-gate to live `Ecosystem_Tech_Radar.md`) — read when
  designing any new project/package Axioma to architectural decisions.

### Fixed (maind — `derive`/`probe` fell on list-format `skills-lock.json`)

- `derive.derive_skills`/`probe.probe_project` assumed `skills-lock.json::skills` only
  like `dict {name: entry}` (format `skiller sync`) and fell `AttributeError` on the alternative
  format - list (e.g. own lock-generator Brain-valta). Caught during first onboarding
  project with this lock-file in mAInd (`maind onboard`/`maind sync --only graph` collapsed,
  `maind health --project <id>` too). Normalize a list in dict before iteration; test for both
  format in `test_derive.py`.

### Added (maind@0.x — provider Laravel PAO + fleet-gate)

- **`maind pao`**: new provider (`lib/maind/pao.py`, detection based on file facts + `php -v`),
  connected step `pao` in onboarding PHP/Laravel-projects (`provision/onboard.py`). Interactive
  suggests `composer require laravel/pao --dev`; on `--yes`/non-interactive - loud warn, not
  silent installation; opt-out `project.pao_opt_out`. `onboarding-decision-tree.md` received
  section «PHP-tools: PAO».
- **`maind doctor --audit pao|all`**: new dimension fleet-audit, reuses `pao.status()`
  (detection logic is not duplicated). Prints `pao⚠(missing: composer require laravel/pao --dev)`
  for php/laravel-project without PAO, `pao✓`/`pao·<state>` for installed/n-a/opt-out/php-too-old.
  Closes the contract hole «skill delivery ≠ install dependency»: onboarding Agelto passed
  GREEN without actually installed `laravel/pao`.

### Fixed (harness — perplexity-web no longer prompts permission)

- **`settings.global.json`**: two independent classes of permission prompts eliminated with one change
  — allow `mcp__plugin_core_perplexity-web` (plugin `core` duplicate `perplexity-web` under another
  named) + top-level `enabledMcpjsonServers: ["perplexity-web"]` (project-scoped `.mcp.json`-server
  forever `Pending approval`). Semantics verified context7. `apply-permissions.sh` received
  union-merge for `enabledMcpjsonServers` + test. Repro on 4 projects (botkit/flexcrm/agelto/
  dterema-app): `⏸ Pending` → `✓ Connected`.

### Fixed (skiller — SKILL_MANAGED_MARKER byte round-trip, registry idempotence)

- **`SKILL_MANAGED_MARKER`/`_mark_skill_managed`/`strip_skill_managed_marker`** are implemented in
  `lib/skiller/common.py` (byte mode, BOM-safe, idempotent) — import crashed (`ImportError`),
  `skiller registry` was not idempotent (`git status` remained dirty after rerun).
- **PAO skill**: package typo in text (`nunomaduro/pao` → `laravel/pao`, externally verified)
  in `SKILL.ru.md`/`SKILL.md`, `skills.json` regenerated.

### Fixed (analyst — Laravel-runners and guard-patterns in the signal A)

- `_RUNNER_EXEC` (`lib/analyst/digest.py`) learned to resolve `php artisan test`/`sail test`
  (Sail-shortcut); removed blanket refusal `||` + thread added `xargs` — reconnaissance teams
  without actually running the test/lints no longer count as «signal A».

### Fixed (maind — `norm_path` resolves symlinks when deduping projects)

- `provision/workspace.py`: `norm_path` translated to `os.path.realpath` — re-onboarding
  project via symlink no longer created a duplicate entry in `projects.json`.

### Changed (docs — package `task` in root CLAUDE.md, CORE_SKILLS 8→9)

- Root `CLAUDE.md`: string `task` in the table «Packages» + layout + explanation in CLI-block,
  why `task` does not route via `swissknifeman` (plugin-only, without `bin/`); new
  `packages/task/CLAUDE.md`. `install.sh` — comment explaining the exception `task` from the installation.
- `packages/skiller/CLAUDE.md`: `plan-protocol` ninth in `CORE_SKILLS` (resident 705/750 current,
  within `RESIDENT_BUDGET_TARGET`); obsolete phrase «resident exceeds target» corrected.

### Changed (harness@0.5.0 — Lean-tiering agent-packs + whole-server MCP allow)

- **agent-packs `python-backend`/`node-frontend`/`dart-flutter` → Lean-tiered (0.4.1 → 0.5.0).**
  `workflows/dev-loop.js` of these three packs were inherited by the model and burned `effort:'high'` on EVERY
  `agent()`; is now parity with `backend-laravel`/`laravel-package`: helper-lanes `implLane`
  (impl `LOW→haiku` otherwise `sonnet`) and `reviewLane` (`LOW→sonnet/medium · MED→opus/high ·
  HIGH→opus/xhigh`), setup/type-check/verify → `sonnet`; `SLICE_RESULT_SCHEMA` enriched
  `risk_level`/`risk_markers`/`workarounds`/`tool_failures` (risk-adaptive review-gate by
  evaluation test-writer); durable-light handover past slices. `pack.json` MODEL_* defaults
  `inherit` → tiered (reviewer/ffi-reviewer `opus`, builder/test/spec `sonnet`).
  Motive (RAG-confirmed): per-stage model tiering — cheap ones execute, expensive designs/
  arbitrates (Anthropic orchestrator-worker + advisor pattern). Inheriting parent
  fan-out models = entire fleet on top model (incident Flex: 93% weekly quota per day).
- **`settings.global.json`: whole-server auto-approve `mcp__perplexity-web` + `mcp__playwright`.**
  Bare-server form covers all current+future tools (incl. `perplexity-web login`,
  missing playwright-tools). Rolling out `harness permissions --global` in `~/.claude/
  settings.json` → stops asking again in ALL projects (earlier - scattering per-tool records,
  prompt for each new tool). Grammar confirmed by docs Claude Code.

### Added (harness@0.5.0 / skiller — multi-agent token economy doctrines workflow)

- Runbooks packs `docs/subagents-and-workflows.md` (all 5) + skill `general/context-economy`
  §8: **no-polling** (do not flood background agents - the notification comes automatically, `ScheduleWakeup`/
  polling cycles burn cache), **resume-stability** (deterministic prompts + model/effort-
  override as a separate parameter → `resumeFromRunId` gives stages from cache), **budget-log**
  (`budget.remaining()` after the wave in big fan-outs). Three doctrines were missing verbatim;
  RAG-are valid (Anthropic context-engineering: progressive disclosure/compaction).

### Added (harness@0.x — safe-dirs: path-scoped resolution rm/rmdir in auto-approve)

- **safe-dirs**: `rm`/`rmdir` with targets strictly inside trusted directories pass by
  `deny_hard` auto-approve-hook (before - unconditional deny). Allowlist **machine-owned**,
  lives **at the root of the monorepo** — `safe-dirs.json` (gitignored; template `safe-dirs.example.json` —
  pattern `config.json` node maind), search ladder with hook: `$SKM_SAFE_DIRS_CONFIG`
  (exclusive override) → monorepo root (realpath PATH-launcher swissknifeman/skiller/
  harness/maind, marker `.claude-plugin/marketplace.json`) → legacy `~/.swissknifeman/
  safe-dirs.json` (`init` migrates it to the repo, home remains in memory/registry). Format:
  `dirs[]` + auto-inclusion of onboarded projects from `projects.json` + `exclude[]`;
  project-override `.claude/auto-approve.config.json` on allowlist has no effect (hostile
  the repository cannot resolve itself rm). Verdict -
  new `hooks/auto-approve/lib/safedirs.py` (stdlib-only, fail-closed): argv via shlex
  (not regex by line), realpath vs symlink-escape and `..`, containment by components,
  cd-tracking for relative paths, globs by static prefix (`allow_globs`),
  protection `.git` (`protect_git`) and the root itself safe-dir; `$VAR`/`$( )`/backticks/`xargs rm`/
  unknown flags/multi-line → deny as before. Handler CENTRAL: one file
  in `~/.claude/hooks/auto-approve/` (puts `harness hooks --global`), projects are only referenced.
- **CLI `harness safe-dirs`** (`lib/harness/safedirs.py` + slash `/harness:safe-dirs`):
  `init` (creates a monorepo at the root; legacy from home migrates automatically, old file →
  `*.migrated`) / `list` (effective allowlist through the eyes of a hook - importlib of the same kernel, without
  second implementation) / `add|remove [--exclude]` (guards: `/`, `$HOME`, ancestors `$HOME` — failure) /
  `prune-ask [--global] [--target P] [--all-projects]` — removing static ask-rules rm
  from settings of already applied projects (merge-only will not delete them itself). New helper
  `settings.remove_permission_rules` (exact matches, «take off yours»).
- Tests: +34 (`test_safedirs.py` — kernel unit: symlink escape, `..`, globs, `--`, `.git`,
  exclude, cd-branches; scenario through real `auto-approve.sh` with tmp-$HOME, including
  immunity to hostile project-override; `test_safedirs_cli.py` — CLI+prune-ask).

### Changed (harness@0.x — presets: rm is controlled by a hook, not ask-rules)

- From `settings.base.json`/`settings.global.json` removed `ask: Bash(rm -r *)`, `Bash(rm -rf *)`:
  hook-`allow` does NOT break through static ask (official semantics permissions — deny > ask >
  allow between layers), i.e. with them rm in safe-dirs would have prompted anyway. Outside safe-dirs rm
  still hard blocks deny_hard — protection has not weakened. At the same time the dead were removed
  `allow: Bash(rmdir *)` from global (always blocked it deny_hard). For already applied
  project rules will not go away on their own (merge-only) — remove: `harness safe-dirs prune-ask
  --global --all-projects`.

### Added (skiller@0.x — profile platform-service · skill voice-ai · presets polyglot · guide polyglot-monorepo)

- **Profile `platform-service`** (`packages/skiller/profiles/platform-service.json`): externalized
  runtime platform, polyglot monorepo (`services/` + `packages/js|php|flutter/` + `apps/` + `infra/`) —
  10 buckets (architect/ai/oss-dev/general/php/php-packages/frontend/frontend-vue/frontend-backend/devops),
  `harness_presets:[base]`, `mcp:[context7]`. `agent_pack`/`model_tiers` deliberately not specified (no
  suitable generic-pack; analogues don’t ask them either).
- **New skill `voice-ai`** (`skills/voice-ai/voice-ai/`, bucket `voice-ai`): voice-agents
  (WebRTC media + WebSocket control, 3-layered turn-detection VAD+semantics+LLM, barge-in <500ms,
  latency <800ms — 1200ms is explicitly marked LEGACY/IVR, session state-machine, RU-stack Yandex
  SpeechKit/SaluteSpeech/YandexGPT/GigaChat + offline-alternativy, remark 152-FZ). Bilingual
  (`SKILL.ru.md` source → `SKILL.md` EN-canon), `upstream.json` strategy=notify (reference
  spec/patterns, without code vendoring). The registry has been regenerated: **208 skills**, 53 plugin.
- **4 polyglot-preset** (`packages/skiller/presets/polyglot-{node-php-flutter,node-php,node-go,
  python-node}.json`) — only from existing buckets (buckets.json), without links to
  non-existent node/go/flutter-buckets.
- **Guide `docs/guide/polyglot-monorepo.md`** (skiller docs): monorepo vs separate repo,
  structure `services/+packages/js|php|flutter/+apps/+infra/`, dependency direction, contracts-as-SSOT
  + codegen, per-package vs unified semver, separate lockfiles, CI multi-lang.

### Changed (skiller@0.x — presets[] in `.swissknife.json` will now resolve to connect-channel, WAS no-op)

- **Contract Behavioral Change `.swissknife.json`:** key `presets[]` used to be
  is reserved, but **was ignored** (`_RESERVED`, no-op). Now connect-channel expands
  presets to buckets according to the formula `buckets = (resolve_presets(presets) ∪ buckets) − exclude` —
  is symmetrical to how `presets` have already worked in vendor-channel (`skillset.resolve_presets`,
  extends/cycle-detection reused, not duplicated). **Projects that have
  `.swissknife.json` was already lying `presets[]` (was previously silently ignored), at the next `skiller
  connect` will receive the corresponding buckets** — before use it is worth checking with the current set
  project buckets. Precedence saved: explicit CLI-flags > `.swissknife.json` (buckets/presets) >
  autodetect by profile. Unknown preset → warn+skip (not die); skill-only preset in
  bucket-channel → warn+no-op (presets work at the level of buckets, not individual skills). 13 new
  tests (`tests/test_presets.py`).

### Changed (schema — `memory_brain` now accepts an object with `sync{direction,patterns}`)

- **`memory_brain` in `.swissknife.json`** expanded from a clean line (path) to `oneOf[string,
  {path, sync?{direction:push|pull|bidirectional, patterns?, on_integrate?}}]` — string-configs
  old projects remain valid without changes. New module `lib/skiller/brain_sync.py`
  (stdlib-only): config normalization, `sync_pull` (copies by glob-patterns from BRAIN, saving
  relative paths, soft-skip in the absence BRAIN — does not break offline work), generation
  `.claude/sync-brain.sh` (atomic record, `chmod 755`). `integrate` calls `sync_pull`
  only for object config with `direction: pull|bidirectional`; string config left
  under the old one memory-hook without behavior changes. Three drift-gate (`test_schema`, `doctor`,
  `test_registry_state`) are trained to treat multi-type fields (`(str, dict)`) like `oneOf`, not
  weakening the check. New `tests/test_brain_sync.py`.

### Added (maind@0.x — cache BRAIN-docks in memory namespace)

- **`packages/maind/scripts/cache-brain-docs.sh`** — bash-helper that caches docks from Brain-valta
  to memory namespace via real-life flags `maind memory remember --scope
  project:<ns> --type docs:<key> "<contents>"` (appeared in the previous audit
  non-existent `--key`/`--file` — checked by code `memory.py`, actual flags used).
  Section «Cache BRAIN-docks in memory» added to `packages/maind/docs/guide/namespaces.md`
  (table of recommended `--type`-keys: `docs:brd`/`docs:architecture`/`docs:api`/`docs:glossary`,
  example `recall`). Not integrated into `onboard.py` — remains manual/script step.

### Changed (layout refactoring + core-dedup)

- **core-dedup:** three cross-packet takes are combined into one `core`. `core.repo.sibling_bin`
  (unified neighbor launcher resolver `env→PATH→<monorepo>/packages/<pkg>/bin`) replaced three
  out of print (`skiller.harness_bin`, `analyst._resolve_maind_bin`); `core.io.backup_file`
  (merge-only `*.bak`, parameterizable suffix) replaced `maind.common.backup_file` + inlines in
  `harness.settings`; managed markdown-block and urllib-HTTP-client moved to `core.block`/
  `core.http` (`maind.blocks`/`maind.http` — thin re-export-shim's, back-compat imports).
  +12 core-tests.
- **Grouping flat-lib by domain** (beyond the threshold flat-lib smell): `maind/lib/maind` —
  loosely coupled outskirts into subpackets `provision/` (deploy·sync·onboard·orchestrate·migrate·
  service·start·workspace·skilldoc) and `analysis/` (fleet·analyze·audit); densely connected kernel
  (memory/graph/federation/namespaces/derive + cli/common/config/mcp/health) remains at the root.
  `skiller/lib/skiller` — analysis in `quality/` (eval·audit·analyze). Imports: `maind.provision.*`/
  `maind.analysis.*`/`skiller.quality.*`. `cli/common/__main__` — at the top level (launchers
  untouched). `harness`/`analyst` left flat (below threshold). validate all 4 green
  (core 151 · maind 380 · analyst 175), CLI-smoke approx.

### Changed (integration contract `perplexity-web-mcp` — version drift removed)

- **`research/query-craft`, `general/mcp-advisor`, `docs/reference.md`:** bridge integration instruction
  `perplexity-web` was inconsistent with the actual package code (docks stuck on «demon v1.3.0», code gone
  forward). Reconciled **by code** `perplexity-web-mcp` (`src/{config,resilience,dispatcher}.ts`, 2026-07-03),
  version binding removed, undocumented behavior added: **client-side resilience** (auto-retry
  with backoff 3× on transient `BROWSER_BUSY`/`TIMEOUT`/`INTERNAL`; desktop `notify-send` and structural
  JSONL error-log `$XDG_STATE_HOME/…/errors.jsonl` on final failure; kill-switch'and `PERPLEXITY_WEB_MCP_*`),
  error code `INTERNAL`, **login grace-window** (the demon itself opens the login window ~3 min + cooldown, parallel
  requests fail-fast with `LOGIN_REQUIRED`), default timeouts (`search` 60s / `deep` 600s) and auto-fallback in legacy.
  Tip «manual retry on BROWSER_BUSY/TIMEOUT» reformulated - bridge retrain **himself**. The registry has been regenerated.

### Added (documentation - Diátaxis-frame + closing holes)

- **User Guidelines:** new landing-directory (`docs/index.md` — card 4 packages
  «what is this + when to take»), end-to-end **`docs/getting-started.md`** (installation → onboarding →
  first task) and **`docs/tasks.md`** — guide «what `/task:*` in which case» + **plan-protocol**
  (master plans `plans/<ID>/`, 4 commands, 6 statuses, handoff, escalation, `plansDirectory`),
  which was not previously on the site at all.
- **Sections `task` and `core`** on the website (`packages/{task,core}/docs/index.md` + docs-sync);
  reference telemetry run-report (SCHEMA=2, `core/usage.py`) — in core-section.
- **Holes closed:** `develop.md` synchronized (per-project `plans/`, `/task:plan-*`);
  `analyst/docs/guide/cli.md` received `token-report`/`ingest`/`proposals`; `plansDirectory`
  operator-docks in `maind/sync.md` and `skiller/integration-checklist.md`; `bucket-audit` in sidebar.
  Frame Diátaxis entered by navigation (nav/sidebar), without mass rewrite 100+ pages.
  Provenance Diátaxis — `docs/reference.md`. Assembly VitePress green (without dead links).

### Added (SKM-MASTER-003 — plan-system per-project · tails reviews)

- **Plan-system per-project (P1, design A–F):** plans plan-protocols live IN THE PROJECT.
  Key `plansDirectory: "plans"` is rolled out in three layers - `harness hooks --plans-dir`
  (new `block_plans_dir` via `set_setting_key` in `.claude/settings.json`; foreign value
  key is not overwritten), providers `maind sync --only plans-dir,plans-doc`
  (retroactive, opt-out `project.plans_dir="off"`; `plans-doc` — hashed-convention block
  `maind:plan-conventions` in CLAUDE.md), `skiller integrate` (new onboardings). Active
  plan - `plans/ACTIVE.md` (lead `plan-design`/`plan-close`, validates `plan-lint`
  root-mode: non-existent plan → ERROR, stale drafts → WARNING with hint).
  Built-in bridge plan mode → protocol: mode **`/task:plan-design from-draft <file>`**
  (flat draft in `plans/` → `plans/<ID>/` by templates, provenance in Decision Log,
  draft is deleted). Owner loop «phase → handoff → /clear» is pinned to
  Expected output `plan-exec`/`plan-close`, §6 skill and CLAUDE.md-block. Skill
  `plan-protocol` entered ninth in CORE_SKILLS (resident 705/750 current). Pilot end-to-end
  on azguard — 7/7 steps green (artifacts in azguard not committed - owner's decision);
  effect `plansDirectory` live plan mode headless not checked - first live
  owner planning. Fan out on ~17 projects - `maind sync` after running in.
- **Tails of reviews of waves 1–4 (P2, 9 items):** `skiller budget` takes into account `references/`
  like ⌥ on-demand (symmetrical `snippets/`); `bucket-audit` got the channel **`resident`**
  (CORE_SKILLS ∪ active sets of registered projects; dead → keep, honest
  mark «resident» — 9/9 CORE is no longer falsedead; perimeter wider CORE: flip
  122 skills, take into account before P7.4); 8 RU-monoliths (architect/legal/marketing/operator/
  pm/research/security/sales) compressed to RU-navigators (full translations - git-history);
  upstream `quality/tdd-discipline` clean - deleted in upstream file removed from `files[]`
  (0 failed); BC-string Verify in dev-loop `laravel-package` under `pack:if/ifnot
  BC_CHECK_CMD` (pack 0.1.1); `analyst token-report` — invariant «ERROR:» ⇔ exit≠0
  is fixed by test; dock pack-guard in `agent-packs.md` (+58 lines); roadmap-docks
  are in sync with the implementation (analyst-suggest/self-learning-memory/README —
  «implemented», remainder - event-stream capture).
- **Dogfooding and fixing the protocol field-feedback pilot:** the wave plan itself -
  a master plan (transcribed by the first agent, closed entirely 19/19,
  `plan-lint plans/` 0/0, ACTIVE → «—»). According to the pilot's findings: legalized bootstrap-header
  handoff `after P0.0` (plan-design), `plan-close` when closing the plan completely updates
  `Meta.Status` and writes `Next: plan closed`, `plan_lint` allows «plan closed» only
  with a completely terminal plan (+2 test). Deferred: honest `changed` y `plans-dir`
, per-skill signal in SCHEMA=2-trend (Known Deviations P2.2).

### Added (SKM-MASTER-002, wave 4 — pack-guard · live protocol loop · metrics BEFORE)

- **pack-guard (P5.6, layer 2 mutation-protection, optional):** PreToolUse-hook
  `hooks/pack-guard/` (off | warn | strict; is NOT set by default) — catches the edit
  generated-pack file BEFORE it happened (solution for `.claude/agent-pack.lock.json`,
  user_owned-files are skipped; strict → block with Russian explanation, any error/no lock →
  silent pass, exit 0). Connection: `harness hooks --target . --pack-guard MODE`;
  physical delivery - in `apply-permissions.sh --global`. 16 tests. Recommended for
  overnight/unattended dev-loop.
- **Live protocol loop (P1.8/P1.10 — phase A closed 10/10):** real item's P5.6 and P8.1
  executed sonnet-operators with cold context strictly according to `/task:plan-exec`, audited
  opus by `/task:plan-audit`. The main risk was not confirmed: sonnet not «finishes drawing» plan -
  performer P8.1 caught the real drift myself (rotten global hook) and honestly refused
  pin baseline on an empty window; cold-start confirmed (work only from files plans/).
  By findings audit protocol has been tightened: plan-close — gate of unscheduled files in the tree
  closing phase + «🟢 requires a commit» + reconciliation of obsolete deviations; plan-audit —
  explicit reconciliation committed vs working-tree; plan-design — rule «time gate Deliverable —
  separate item» (applied to the plan itself: highlighted P8.5 «pin baseline pilots»).
- **Metrics BEFORE:** global hook run-report updated to SCHEMA=2 (stood rotten
  SCHEMA=1 from the rollout on July 1 - a real drift caught by the performer; `harness doctor`
  clean); telemetry enabled on pilots azguard and chatom (ENABLED=on + SessionEnd);
  SCHEMA=2-mechanics tested on a real transcript in isolation scratch-cwd (pilot
  baseline are not clogged with synthetics). Pin baseline — time gate P8.5 (≥1 week window).

### Fixed (wave 4)

- Recovered from HEAD uncommitted reversion `docs/routing.md` (layer lost analyst,
  «three-pack umbrella») and `docs/reference.md` (−24 provenance card lines) —
  HIGH-find adversarial-audit P5; in `plan-close` added a gate that catches this class
  contamination during phase closure.

### Added (SKM-MASTER-002, wave 3 — analyst learning loop · bucket optimization)

- **Analyst learning loop (phase D):** command **`analyst token-report`**
  (`[--sessions N] [--by model|role] [--vs-baseline] [--all-projects] [--json]`) — slices
  usage-trend, rolling-baseline (median+p90 last 20 sessions), regression-flag
  (>1.3×median or >p90), pinned-snapshot `--baseline set --note …` → `.claude/analyze/baseline.json`
  (format is compatible with those already reading it `maind analyze`; 21 test). **Agent Analyst**
  `packages/analyst/agents/analyst.md` (opus, read-only) + command **`/analyst:deep`** —
  digest-first: scripts are collected JSON-extracts (`maind analyze` / `token-report` / `review`)
  in `.claude/analyst/deep/`, paths are sent to the agent; raw-transcripts prohibited promptly; exit -
  findings under contract **`analyst ingest --file F`** (validation entirely up to the first record;
  ONLY ephemeral-lessons, detector=agent-finding — enforced code; promot behind the person;
  10 tests). **`analyst proposals`** — draft system improvements
  (stack-pack | project-override | docs) in `~/.swissknifeman/analyst/proposals/<type>/<id>/`
  (deterministic slug-id, edit-safe writer like suggest.py), statuses draft|accepted|rejected
  via append-only audit, print handoff-sequences; test-invariant «zero records out
  ~/.swissknifeman/analyst/» (27 tests). Plugin analyst now also distributes agents
  (`"agents"` in plugin.json, marketplace regenerated - 52 plugins).
- **Bucket optimization (phase G):** command **`skiller bucket-audit`** (`lib/skiller/audit.py`) —
  size (review budget) · overlap (Jaccard≥0.4 by description, 5-gram shingle ≥0.3 by body) ·
  usage (fan-out by projects.json, `--since N`, honest mark «was not used in the window») →
  verdicts keep/thin/retrieval-only/merge/dead (structural facts take precedence usage-signal;
  20+ tests). **Solution document** `docs/guide/bucket-audit-2026-07.md`: 206 skills / 45
  buckets / 21 project, verdicts with numbers (dead=180 · keep=13 · thin=8 · merge=3 ·
  retrieval-only=2), topology sketch 45→~34 (sketch only), section «what we DO NOT do».
  **10 monoliths → thin-navigator**: bodies 55–102KB moved byte-to-byte into
  `references/full.md`, SKILL.md — compact EN-navigator with anchor map; additive field
  **`body_path`** in upstream-diagram + gates in validate.sh/update-upstreams.sh (sha/drift - by
  body, not by navigator). Summary budget: **on-trigger tier 512 608 → 279 802 current
  (−232 806, ~45%)**, resident ⊕-tier has not grown. **Alias-bucket merge mechanism** (D14,
  code without application): `alias_of`+`skills[]` in buckets.json → marketplace-record by use case
  core-plugin, migration tips in `skiller update`/`status` (15 tests; live registry
  does not declare aliases - the generic diff is empty). Criteria **always-on vs retrieval-only** recorded
  in `docs/guide/methodology.md` (3 conditions + reversible rule exclude for 2 windows).

### Fixed (wave 3 - incidental finds)

- **`bin/analyst`**: hard whitelist launcher did not know the registered commands
  `status`/`compact` (and new `token-report`) — commands were unreachable through the installed
  CLI; whitelist and usage are synchronized.
- **`bin/skiller`**: same disease - `analyze-run` and new `bucket-audit` were missing from
  whitelist launcher; added.
- **`skiller registry`**: provenance-entry external-skilla now prefers
  `body_path`-file (`references/full.md`) entries `SKILL.md` — otherwise provenance thin-navigator
  skills depended on the order `files[]`.

### Known gaps (honestly, wave 3)

- `analyst token-report --by phase` not possible on current schema run-report: `workflows[]` not
  carries tokens per-workflow — CLI accepts the flag and explains politely; selection of hook format -
  separate wave (harness).
- `budget.py` does not take into account `references/` in any tier - savings −232K partially «leaving
  accounting», and not honest-reclassification to on-demand; model solution for tier-2 accounting
  references/ — follow-up.
- usage-source bucket-audit — transcript scan by explicit Skill-calls (not SCHEMA=2-trend):
  structural blind spot on auto-trigger/CORE-skills (8/8 CORE show «dead» when
  deliberate distribution) — verdicts dead read with this amendment; integration with trend - follow-up.

### Added (SKM-MASTER-002, wave 2 - catalog of pathologies · stack pack laravel-package + pilots)

- **Pathology catalog (phase C):** `core/pathology.py` — pure security detector workflow-pathologies
  (`detect(run_report) → findings {code, severity: info|attention, metric, threshold, evidence}`),
  10 detectors: file-reread, tool-error-loop, no-op-run, no-verify (+`no-verify-devloop`),
  cache-miss, overthinking, retrieval-stuffing, protected-write, static-context, fanout; thresholds -
  constants with fair marking «heuristics, not calibrated» (36 tests). Strict routing
  Detect ≠ Gate: `maind analyze` — `pathology_slice` (attention → reasons/ATTENTION, info → section
  «Efficiency»; RED from pathologies is impossible, invariant in docstrings); `analyst digest` —
  extractor `extract_pathologies` with relapse rule (window 5 latest run-report'ov, lesson
  only when ≥2 code hits; one-time pathology - signal analyze, not a lesson), only go to lessons
  4 code with ready-made remediation. Catalog-doc `packages/analyst/docs/guide/pathologies.md`
  (all classes, formulas/thresholds = code constants, remediation, honest column «detectable/additional»).
- **Stack pack `laravel-package` 0.1.0 (phase F):** separate pack for Laravel-PACKAGES
  (composer library / package monorepo) — reviewer with center «public contract» (Public API/
  BC-SemVer + roave/bc-check, register-vs-boot, publishables, `env()` out config → HIGH,
  composer-constraints, Testbench, multi-version matrix), slice-builder («package feature»,
  @internal/final), test-writer (Testbench + version_compare-branches), new recon `api-surface`,
  4 rules, dev-loop-fork (risk-adaptive saved, +public-api marker, preflight
  `composer validate --strict`). Anti-double with two layers: slider **`src_pack`** in files[]
  (review-gate.sh/env.ini/settings.fragment — byte-to-byte from backend-laravel without copies) +
  **parity-test shared-blocks** `test_agentpacks_shared.py` (6 blocks of prose reviewer'and marked
  `<!-- shared:X -->` in both packs, drift = red test). New command **`harness agent-packs
  remove`** (clean files are deleted, modified/user_owned/merge remain with warn, lock atomically).
  `backend-laravel` 0.11.2 — shared-markup + fix `app/Repositories` → `{{ACCESS_ROOT}}/…`.
  Profile `php-package` received `agent_pack: ["laravel-package", "_common"]`; roadmap
  `php-package-stack-pack.md` → «implemented»; docks harness + docs/reference.md (roave — adopt;
  spec-kit/beads/planning-with-files — reference).
- **Pilots (phase F, rendered in working trees azguard/chatom, don't commit there):** azguard —
  remove backend-laravel → render laravel-package clean + 4 domain axes in
  `.claude/rules/azguard-reviewer-overrides.md` (panel_id isolation, epoch-invalidation,
  wildcard semantics, extension API idempotency) + path-scoped `azguard-domain.md`; chatom
  (monorepo `packages/*/src`) — same migration with `HAS_MIGRATIONS=true`/Pest. Acceptance-greps
  app-canon on both - 0 hits; `doctor --drift` clean. Non-pilot regression (F-8):
  upgrade-channel 0.11.0→0.11.1 (worktree-emulation «to headers») — 0 conflict; dry-run live
  app-project - conflict's only from real manual edits generated-core (exactly the pattern
  which now catches the axis `generated-core-edited`).

### Fixed (field findings of wave 2 pilots - engine agent-packs)

- **`_probe_allowed` cut detection samples according to `;` without understanding the quotes** — sample
  `PACKAGE_NAMESPACE` (php -r) quiet skip'arrived `shell_policy=safe` and variable
  remained empty; sample rewritten by one PHP-expression without `;` (terminator `?>`),
  plus fallback on `packages/*/composer.json` with shortest psr-4 (monorepo case).
- **`categorize_file_change`: pack file in lock, but not on disk**, when upgrade
  gave useless `conflict`/`*.pack-new` instead of simple installation → now `new`/
  `new-optional` (missing + base-unchanged remains `nochange`). +2 test.
- **`do_render` did not rewrite lock when `changed=False`**, even if the file has real
  flag changed `local_modified` (external file reconciliation to the package database) — `doctor`
  always showed rotten `modified: true` → lock is written when a new record is different
  from the saved one. +1 test.

### Added (SKM-MASTER-002, wave 1 — plan-protocol · token-telemetry SCHEMA=2 · protection generated-assets)

Master Plan a master plan (operating system plans): strong model designs,
cheap execution, telemetry makes token leaks visible, generated-assets are protected.

- **Plan-protocol (phase A):** skill `general/plan-protocol` (SSOT: schemas `plans/<ID>/{plan.md,
  phases/Pn.md,handoff.md}`, 6 canonical statuses, rolling handoff, routing-matrix
  model/effort, escalation with greppable-artifacts) + snippets-templates; 4 teams
  `/task:plan-{design,exec,close,audit}` with pins (opus/high · sonnet/medium · sonnet/low ·
  opus/xhigh); deterministic `plan-lint` (`packages/task/lib/task/plan_lint.py` + thin
  `scripts/plan-lint.py`, 45 tests) and the first `validate.sh` package task; the master plan itself
  transcribed in a master plan (dogfooding, lint green).
- **Token telemetry end-to-end (phase B):** `core/usage.py` — single self-sufficient
  transcript parser usage (is vendored byte-for-byte in a hook like `_usage.py`; `sync-usage.sh` +
  cmp-gate in validate.sh harness — copy drift fails validation); run-report **SCHEMA=2**
  (only-additive: `usage` per-agent including sidecar-subagents, `reads`, `error_loops`,
  `retrieval`, `protected_writes`); trend `.claude/analyze/usage-trend.ndjson` (~200 bytes/session,
  retention 4000→2000); `skiller analyze-run` translated to `core.usage` (amounts are identical,
  regression fixture); `maind analyze` — block tokens (session vs median K=20/p90 trend + pinned
  `baseline.json`), token regression → ATTENTION (RED from tokens is not possible); `harness doctor`
  detects a rotten installed hook. USD we deliberately do not count - raw tokens model-keyed.
- **Protection generated-assets (phase E):** deterministic provenance-header
  `swissknifeman:generated` (Pack@version/Template/Edit-policy/Extension-points, WITHOUT timestamp —
  hash along with header, matrix `_decide`/`categorize_file_change` untouched) in all rendered
  pack files; `user_owned` in lock (schema 1, additive); `harness agent-packs doctor --drift
  [--strict]` + self-sufficient `pack_drift` in `maind analyze` → ATTENTION when editing locally
  generated-file; overlay-extension model (`.claude/rules/<prefix>-reviewer-overrides.md`,
  user_owned, `role:override`) in all stack packs + rule `_common/rules/generated-assets.md`
  + axis `generated-core-edited` (HIGH) in reviewer'ah + HARD_GATES in dev-loop. Bump packs:
  `_common` 0.4.0, `backend-laravel` 0.11.1, `node-frontend`/`python-backend`/`dart-flutter`
  0.4.1, role-packs +0.0.1.

### Added (output-style=lean + skills-catalog — automatic distribution to all projects)

- **`skiller integrate` puts `output-style lean` in ALL bundles** (`minimal`/`recommended`/
  `full`/`custom`, default `True`) — new block `_block_output_style` delegates `harness hooks
  --output-style lean` (according to the example `_block_autoapprove`/`_block_memory`). Formerly terse-voice
  agent was a purely manual operation (`harness hooks --output-style lean`), none of the points
  login (`maind onboard`, `skiller integrate`) did not call it - capability `env:hooks` in
  `orchestrate.py` had no callers. Token savings needed «for all projects»
  regardless of the scope of the rest of the automation of the bundle - the only item included in
  `minimal`.
- **`maind sync` — two new providers** for already onboarded projects (close
  the same gap retroactively, without complete re-onboard): `output-style` (the same `env:hooks
  --output-style lean`, opt-out per-project `project.output_style: "off"` — otherwise regular
  `maind sync --all` would overwrite the locally selected style) and `skills-catalog` (`skiller update`
  — re-resolve buckets/exclude from disk, so a new skill of an already selected bucket, for example
  `php/pao`, reaches long-onboarded PHP-projects without manual `skiller update`/`connect`/
  `vendor`). Both are in the default set `--all`.
- **`skm:update` added to `orchestrate.DRY_CAPABLE`** — `skiller update` knows how to be honest
  `--dry-run`, now `maind sync --dry-run` gives a real preview for `skills-catalog`, and not
  fake print+rc0 (the same trap that `DRY_CAPABLE` already repaired for `agent-pack`).
- Context: `php/pao` (agent-optimized output PHPUnit/Pest/PHPStan for PHP-projects) already
  was included in the default profile `php-package`/`laravel-project` and reached new onboardings;
  real `composer require laravel/pao --dev` **deliberately not automated** nowhere (mutation
  `composer.json`/`composer.lock` without human confirmation) — agent executes it itself
  skill instructions when it really starts running tests («skill-on-demand»).

### Fixed (package `skiller` — audit registry/budget/vendor/connect: duplication, false green gates, reliability)

Based on the results `research/Deep package audit skiller (registry-budget-vendor-connect).md` (22 finds,
all closed - fixed code or documented conscious refusal of the fix if it broke the existing one
invariant).

- **R-1 [CRITICAL] — token-saving `connect` confirmed, not suspected.** Comment in
  `registry.py` stated «confirmed by doc Claude Code v2.1.x» without actual testing. RAG
  (perplexity-web + direct quote `code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries`):
  for marketplace-records whose `source` resolves to the root marketplace, explicit `skills[]`
  **replaces** default scan, and does not complement it - the risk of resident loading of all 219 SKILL.md
  there is no repository. The comment has been rewritten with the exact quote and date of review.
- **V-2/V-3 [HIGH] — false green install/lock (`vendor.py`, `skillset.py`).** `safe_copy_skill`
  could return `False` (containment-stop/TOCTOU-race) — the pass was quietly swallowed, `sync`/`vendor`
  reported the plan as a fact. Now we count and print FACT (`plan['installed']`/`skip_copy`).
  Structurally broken `skills-lock.json` (not to be confused with legitimately empty after manual cleaning - test
  `test_manual_lock_cleanup_*` remained green) restores managed-set from manifest, not
  resets it.
- **V-1 [HIGH] — duplicate resolve `requires`.** `skillset._pull_requires`/`vendor.resolve_requires`
  were independent, already separated BFS (RU/EN texts warn) — reduced to general
  `common.resolve_requires_bfs` with host source adapter (FS-tuple / registry-entry).
- **V-4/V-5 [MEDIUM] — duplicates writer'and manifest and collect buckets.** Single
  `common.write_skill_manifest` (there were two independent writers with different schemes: date-only without
  `version` y vendor, `now_iso`+`version` y skillset). Collecting buckets (FS-rglob vs registry) abandoned
  architecturally separate (deliberately - a forced merge would introduce a hard dependency `vendor`
  from driven away `skiller registry`), but added golden-parity test (`test_channel_parity.py`),
  catching future channel drift.
- **B-1/B-2 [MEDIUM] — token-score calibration + shortage in `--check-core`.** Constants
  `CHARS_PER_TOKEN_CYR/LAT` (2.2/4.0) are calibrated to RAG (perplexity, 3 source: ~2.9 for
  Cyrillic, ~3.4 compromise EN-prose/code) — old ones underestimated RU-tokens and inflated code-heavy bodies.
  `budget --check-core --strict` now fails and is on LACK CORE-skills (moved/sealed
  path used to silently DECREASE resident, gate «turned green» instead of error). Conversion using calibrated
  constants revealed a real fact: resident CORE (8 skills) — 696 current that honestly exceeds the old one
  target 600. `resident_budget_target` raised to 750v `configs/core-policy.json` (conscious
  solution, not calibration rollback).
- **R-2 [MEDIUM] — drift-did not see the gate `graph.md`/`budget.md`.** `scripts/generate-graph.sh` (bash+
  heredoc) ported to `registry.render_graph`/`write_graph` (in-process, without subprocess) — now
  `registry.check_drift` compares both artifacts, not just `skills.json`/`_index.md`/manifests.
  Old shell-script left in tree with deprecation-with a header (`rm` blocked by environment policy
  sessions - safe to delete manually: `git rm packages/skiller/scripts/generate-graph.sh`).
- **V-6 [MEDIUM] — diagnosability of a partial copy in case of crash.** Conflict with sha256, matching
  registry (looks like interrupted sync), now receives a separate message with an explicit hint
  «`--force` safe» instead of scary «busy with someone else's skill». Auto-adoption is NOT enabled -
  would break the invariant being tested «manual cleaning lock requires `--force`».
- **C-1/C-3 [MEDIUM/LOW] — `connect.py`.** Skip CORE-plugin when undeclared marketplace
  (`--no-core` not specified) is now explicit `warn`, not silence. `DEFAULT_COMMAND_PLUGINS` covered in dough.
- **U-1 [MEDIUM] — `update --all` does not crash on a broken manifest.** Unwrapped `json.loads` dropped
  unhandled exception the entire batch on the first project with a broken `.swissknifeman-manifest.json`
  (not caught `except SystemExit`). The same class of defect was found and fixed in `vendor.load_manifest`
  (regression came up through a test for `update --all`).
- **Doc-1/Doc-2 [MEDIUM/LOW] — `doctor.py` did not diagnose harness.** Added check
  `harness_bin` + light `harness --help`-probing: absence - not FAIL (optional dependency),
  breakdown - FAIL. Schema-check in doctor previously only checked key names (`⇄ keys`), now also types
  (`⇄ types`) — parity with `test_schema.py`.
- **T-2 [MEDIUM] — obsolete figure CORE («7 ≈ 480 current») everywhere.** Synced (`connect.py`,
  `config.py`, `CLAUDE.md`, `docs/guide/{archetypes,skills-architecture}.md`) to a current fact
  (8 skills) without the hardcode of the new snapshot - indicates `skiller budget --check-core` as source
  truth, so as not to go rotten again.
- **V-8/V-9 [LOW] — reliability.** Broken `boost.json` in `lock._boost_skills` now warn, not quiet
  `[]`. Change `skills_path` in the config no longer leaves an orphaned copy at the old path (new
  pass prune by `installed_path` from lock).
- **B-3/B-4/R-3/R-4 [LOW] — dotted.** Cyrillic detector expanded to Cyrillic Supplement
  (U+0500–052F). `_split_frontmatter`/duplicate«dead» name branch in `registry.py` — are documented
  as conscious, not merged/not deleted (there was no real benefit from the merger, there was a risk).
- **Tests:** +18 unit-tests (233 total, there would be more nominally - some of the finds are covered
  extension of existing assertions), including new `test_channel_parity.py`. `validate.sh` green
  (`skiller registry` regenerated, `registry --check` clean).

### Changed (discipline: RAG-delegation + plan detail/handoff)

- **RAG-step is not delegated to a tool-poor subagent** (canon `general/verify-claims` — new
  subsection «Delegation: don't drop a step»; pointer to root-skill `decision-verification`;
  clause in `CLAUDE.md` «Decision Methodology»). Root cause: verification of an external fact was
  delegated to subagent `claude-code-guide` (toolset without `perplexity-web`) → stairs silently
  sank to `WebSearch`. Rule: RAG-stage is executed where the priority engine is available;
  you delegate - the delegate is obliged to bear `perplexity-web`/`context7`, otherwise keep the check mostly
  context (you CAN delegate, you cannot drop a step silently). **Regression guarantor** — new
  pressure-case in `verify-claims/evals/pressure.json` (catches temptation through `skiller eval`).
- **Contract `task`-package: the plan is as detailed as possible, the handoff is short** (`task/design.md`,
  `task/dev.md`). Plan - self-sufficient (everything for execution IN FILE, survives session crash),
  not «briefly by phase»; controversial → separate block `## Discussion` in terms of (pros/cons + explicit
  recommendation), and not popup; handoff on `/task:dev` — short link to the plan, not a 2-page brief;
  `AskUserQuestion` — extreme case and always with the recommended option.

### Added (package `analyst` — P4: cross-project pattern → DRAFT skill)

- **`analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]`**
  — deterministic (stdlib, on-demand) bridge `scan` → reused skill: reads **only**
  abstracted index `index/by_pattern/<id>.json` and generates staged-DRAFT
  `~/.swissknifeman/analyst/drafts/<pattern_id>/` = `SKILL.ru.md` (RU-source-stuff with
  frontmatter-skeleton + inert provenance stamp) + `draft.meta.json` (passport + `seed_sha256`).
  **Invariant retained:** does NOT write to `skills/`, DOES NOT generate EN-canon, DOES NOT log, DOES NOT expand
  raw/secrets (privacy STRUCTURAL - index already abstracted). Promot in the bucket - person; conclusion
  prints **exact** repo-grounded sequence skiller (mkdir → `claude-canon-from-ru.md` →
  `check-translations.sh --stamp` → `validate.sh` → `skiller registry`).
- **Edit-safety (idempotency):** re-suggest does not overwrite manual edits - `seed_sha256`-detect
  (body == last generated → regenerate; straightened by hand → we do not touch the body, we only refresh
  provenance meta; `--force` overwrites). Orphaned drafts (pattern disappeared) — **WARN, not
  delete** (≠ scan-prune: draft human-editable).
- **Gates:** `name`-candidate for official skill rules (≤64, `[a-z0-9-]`, without leading/tail
  hyphens and reserved `claude`/`anthropic`; Cyrillic does not form name → Latin token/`skill`,
  finalizes man); `--min-weight` (index does not carry confidence → `--min-tier` postponed, D7).
  Pure generators (`build_skill_ru`/`build_meta`/`_slug_name`) + writer with I/O in `cmd_suggest`;
  +13 offline-tests. Design: a roadmap note.
  At the same time, outdated pointers have been fixed «promoter = `skiller integrate`» in `scan.py`/CHANGELOG
  (integrate sews skills into the project, does not register a new one).
- **Package documentation `analyst`** — added `packages/analyst/docs/` (VitePress: index + guide
  cli/lifecycle/suggest + architecture + roadmap) and linking to the umbrella site (`scripts/docs-sync.sh`,
  root `docs/.vitepress/config.mts` nav+sidebar+Packages, `docs/routing.md` layer «Training»,
  `.gitignore`). Standalone and aggregate build green. Previously analyst was the only package without
  their docks.

### Added (package `analyst` — P1 MVP + P2 scan: continuous learning, layer-1)

New fourth monorepo package **`analyst`** (CLI `analyst`, plugin-only-commands) — deterministic
(stdlib-only, **on-demand, without daemon**) capture layer «hard-won lessons» from runs Claude Code with
**man in the gate** (auto-recording to skills is prohibited). Implements P1 contour continuous learning:

- **`analyst digest`** — deterministically extracts CANDIDATE lessons from fresh `run-report` run by
  high-precision signals (resolved-failure «worked after N attempts»; explicit dev-loop workarounds) →
  `.claude/analyst/lessons/ephemeral/` (LOCAL). Not «guesses insights» — conscious boundary MVP.
- **`analyst review`** — lessons on states (ephemeral/candidate/curated/deprecated) + structured diff
  against active (Jaccard, stdlib). Read-only.
- **`analyst promote <id>` / `deprecate <id>`** — pipeline `ephemeral→candidate→curated` with **man-gate**
  (transition to curated — only explicit consent: confirm on tty or `--yes`); curated comes to mind
  mAInd (`maind memory remember`, graceful — the demon lay down → lesson on disk, will repeat later). Soft-deprikate.
- **Provenance:** each lesson carries `source`/`session_id`/`scope`/`evidence`; each transition is a record in
  append-only `.claude/analyst/audit.ndjson`.
- **`analyst scan`** — cross-project aggregator: the package itself bypasses the registry `config.json:projects[]`,
  reads per-project lessons, greedy-Jaccard-clusters and detects patterns that repeat in **≥N
  projects** (default 3) → draft-**suggestions** (not skills!) in `~/.swissknifeman/analyst/suggestions/`
  + index `index/by_pattern/`. **Namespace-insulation** (inherits from maind): lessons are clustered
  only among projects sharing namespace — pattern from `ns:axioma` does not flow into someone else's. Determinism
  (sort by id). Draft skill from the proposal - `analyst suggest`; promotion to the bucket - a person.
- **Harness:** root-router `swissknifeman analyst …` + `doctor` fan-out; umbrella `install.sh`;
  marketplace-entry (auto-pickup `skiller registry`). `Env(BaseEnv)`, atomic JSON, tests offline (37).
- **Reconciliation `analyst scan` (P2-debt closed)** — after recording artifacts deterministic prune
  orphaned `index/by_pattern/<id>.json` + `suggestions/<id>.md` (pattern disappeared: project disabled/deleted,
  lesson deprecated, cluster fell below threshold). Prune STRICTLY in scope run: `scanned_namespaces` =
  `{--namespace}` if specified, otherwise union namespace all enabled-projects; stranger namespace not rescanned →
  his files are not touched (classification - from FIELD `namespace` index, not from filename; broken index →
  SKIP, do not delete or drop scan). Flags: `--no-prune` (default wire ON), `--dry-run` (only
  would-prune, does not delete anything); `pruned:[…]` in `--json`, «taken by orphans: N» in human. Non-standard
  `--min-projects/--threshold` auto-prun skip (protection against churn). Clean `stale_pattern_ids` (tests
  without I/O) + `list_existing_patterns`/`prune_artifacts`; +11 offline-tests (adversarial S2).
- Postponed for P5 (by design, no debt): skill `analyst-capture` + `observe.sh` PostToolUse-stream.

### Added (package `analyst` — P3: confidence-life cycle)

Implements **P3** contour continuous learning: deterministic,
**recoverable-from-logs** lesson confidence recalculation + **numeric** state-machine, **without daemon**
(on-demand) and **without invariant violation** «`candidate→curated` — human only».

- **`events.ndjson`** (new append-only signal stream, next to `audit.ndjson`) — `digest`/`promote`
  add observation scalars (`sessions_total/success`, `tests_total/passed`). Source of Truth
  recalculation: we reproduce the snapshot only from this log.
- **`confidence.py`** — PURE arithmetic (stdlib, without I/O/hours, tested by points): Beta-average
  `p=(S+α)/(N+α+β)` × volume `(1−e^{−N/k})` × time-decay `λ^days`; application ranges
  `0.3` tentative · `0.5` moderate · `0.7` strong · `0.9` core. Constants (`α=β=1`, `k=20`, `λ=0.95`
  ≈ half-life 14 days, bucket=1 day) — **module tuning parameters** (are calibrated according to false-positive rate).
- **`analyst recompute [--now ISO] [--dry-run] [--json]`** — reads `events.ndjson` → decay by time →
  unit `S/N` (+ `S_decayed`/`N_decayed`) → `confidence` → numeric state-machine → **atomic** snapshot
  in lesson (additive fields, P1-the circuit does not break). Deterministic and recoverable (when fixed. `--now`). Gates:
  `ephemeral→candidate` — **auto** when `N≥15 && conf≥0.6 && tests_total≥1`; `candidate→curated` — **always
  person** (numbers only mark «ready», auto-transition disabled - invariant P1); drawdown `conf<0.6` →
  **soft-deprecate** (file is not deleted).
- **mem0-consolidation into human-gate** — `review`/`promote` consider taxonomy **ADD/UPDATE/NOOP/CONFLICT**
  (Jaccard by trigger/action, stdlib) against active ones. Controversy (same situation, different action) →
  **flag-and-ask** (promote is blocked until explicit `--supersedes ID` | `--force`, no auto-resolve).
  `--supersedes` — **soft-invalidate** replaced (`supersedes`/`superseded_by`+timestamp, move in
  deprecated, file saved).
- **Harness:** `recompute` in `cli.py`/`bin/analyst`/`commands/analyst.md`; tests offline (+33 = 70).
  There is no demon. Real round-trip surfacing to memory mAInd — checked back in P1.

### Docs (analytics and continuous-learning in the showcase README + runbook)

Showcase didn't mention analytics/self-learning, although the real layer already exists, and the full circuit is
is designed and roadmap. Reflected honestly (real vs roadmap):

- **README** — string «📈 Analytics and training»: real (capture `run-report` → `maind analyze`
  with memory metrics/graph; experimental `session-observer`; loop `field-feedback-loop` with
  manual promo) + cross-project **Continuous Learning** is marked as designed/roadmap
  (links to a roadmap note and design `research/analyst-package-design.md`).
- **`docs/develop.md` §9** — block «Self-learning - circuit and status»: manual loop with a person in the gate
  now; automatic cross-project loop - deferred (confidence + manual promo as guardrail).

### Added (developer-runbook + showcase README + memory observability/column)

Development process documentation was lagging and memory/graph mAInd were «black box Does» (write,
whether it reads, whether it helps - there is nothing to measure with). Parsed by reading the code + RAG-verification of external facts
(native auto-memory Claude Code and semantics `/compact` — official. docks; Serena-tools - context7).

- **`docs/develop.md`** — single operator-runbook «Development with Claude Code + swissknifeman»: phases
  plan, `/compact` vs new session (canon according to official. docks), task-plugin, roles/agent-packs, token-levers,
  **demystifying memory** (two layers: agentmemory-demon vs native memory Claude Code) and **column**
  (manual scan + pull-model), performance measurement, RAG-stairs, scripts-FAQ. Back connector -
  refers to deep docks, not a duplicate. Embedded in VitePress (nav + sidebar `/develop`).
- **README → showcase** — feature-review «which gives» (plugins+skills, roles+workflow, token-levers,
  tasks, memory+graph, environment, RAG) instead of repeat CLAUDE.md; prominent link to the running book. Does
- **Memory observability/column** (answers to «work or just eat tokens?»):
  - run-report (`_lib.py`) counts calls `maind_memory_*`/`maind_graph_*` from transcript (match by
    tail after `__` — is worried `mcp__maind__`/`mcp__plugin_core_maind__`) + facts found/neighbors →
    additive key `maind` (SCHEMA not bampan, back-compat with old `analyze`).
  - `maind analyze` shows `memory: recall×N→M · graph: query×K` and highlights **«code graph not
    used for heavy scanning»** (indirect heuristic: many Read/Grep/Glob with graph ×0).
  - `maind memory count [--project]` — how many facts are in memory by scope (by scope-token, not the entire pool).
- **graph-first nudge** — skill `ecosystem-mcp` (maind) now explicitly advises the Count/Serena
  `find_symbol`/`get_symbols_overview` before wide `grep` (with a caveat about manual scanning/deprecation);
  cross-ref from `context-economy` (lever ladder).

### Added (token-economy — base deny-rules for large artifacts; track A plan-A ROI-1)

Token Savings (audit `research/swissknifeman-token-audit.md`): large low-value files should not
get into context through random `Read`/glob. Expanded `permissions.deny` in
`configs/claude-code/settings.base.json` (was only `.env`/keys/ssh/sudo): added
`Read(**/CHANGELOG.md)`, `Read(**/skills.json)`, `Read(**/package-lock.json)`,
`Read(**/composer.lock)`, `Read(**/*.lock)` — anchors `**/` (match at any depth downstream).
- **Behavior change:** `**/*.lock` is now disabled at level base (subsumes laravel-preset take;
  merge additive and deduplicate exact matches). Stack presets unchanged.

### Added (maind analyze — post-run run analysis «did everything work?» + SessionEnd-hook run-report)

Field-feedback: after task-with-plan (e.g. on azguard) you need to check through the logs whether everything worked,
but the sources of the outcome were read separately - there was no single command. Capture mechanism verification -
entirely via `perplexity-web` (found 2 errors in the first draft: transcript - first-class artifact,
pars supported; SessionEnd-hook can write a report generic'ohm → edit `dev-loop.js`/packs are NOT needed).

- **Hook `run-report` (SessionEnd, harness)** — `configs/claude-code/hooks/run-report/`
  (`run-report.py` + `_lib.py`): lowercase (without slurp) and protectively parses the transcript → writes
  `<project>/.claude/runs/<sid>.json` (tests/lint with `ok` from `is_error`, modified files, tool-failures,
  work flow, best-effort dev-loop `tool_failures`/`deferred`/`workarounds`). Generic — any task, not
  only dev-loop. Never a barrier (error/broken stdin → exit 0). Retention `RUNS_KEEP`.
- **`harness hooks --run-report on|off`** (`block_run_report`) — env.ini (ENABLED/RUNS_KEEP) + merge-only
  registration SessionEnd. `apply-permissions.sh --global` copies `run-report/` in `~/.claude/hooks`.
- **`maind analyze [--project|--cwd] [--session] [--base] [--json] [--no-health]`** (new
  `lib/maind/analyze.py` + `cli.py` + `bin/maind` whitelist + `commands/analyze.md`): aggregates
  run-report (primary) + bash-log (forensics, WITHOUT return codes - honestly) + observer + git + health →
  verdict **GREEN/ATTENTION/RED** (+`confidence` low, if run-report no). Bow with RAG: dev-loop
  `tool_failures` → block «**Unverified → REPEAT PASS**». RED → exit 1 (gate for scripts).
- Tests: `harness/tests/test_run_report.py` (+12: parser, hook behavior, retention, block_run_report),
  `maind/tests/test_analyze.py` (+11: verdict, search run-report, forensics, assembly+JSON).
  **Fair limits:** transcript schema not frozen → pars protective; bash-log without pass/fail;
  SessionEnd = 1 entry/session; `devloop`/observer — best-effort.

### Added (intent-router — free text → optimal command; activation roadmap-hook)

Field-feedback: owner forgets to set tasks through `/task:*` (measured misrout → trigger
deferred activation a roadmap note). Capability verification - entirely through
`perplexity-web` (found 2 errors in the original plan: auto-run first class via `SlashCommand`;
SessionStart-send policy via `additionalContext`, not `systemMessage`).

- **Pair Python-hooks `agent-router`** (first Python-repo hook):
  `configs/claude-code/hooks/agent-router/` — `session-policy.py` (SessionStart injects static
  routing policy via `additionalContext`) + `router.py` (UserPromptSubmit: keyword-prescor →
  tiny idempotent-prompt when score≥THRESHOLD, otherwise silence; escape-hatch `~`). Hybrid:
  prescor — bias, final classification (question vs task) makes the model. Never a barrier.
- **`harness hooks --router propose|auto_dispatch|off`** (`block_router`) — includes a couple of hooks
  per-project (env.ini + merge-only registration UserPromptSubmit+SessionStart).
- **`harness router --generate --target P`** (new module `lib/harness/router.py` + `cli.py`) —
  generates `.claude/agent-router.config.json` from `/task:*` + `.claude/agents/*.md` + local
  `.claude/skills/*/SKILL.md` (low weight - backstop). Umbrella `swissknifeman env router` for nothing.
- **maind:** `env:router` capability + provider `router-config` in `maind sync` (opt-in: generates
  directory only for projects with the hook enabled; comes after `agent-pack`).
- **Global distribution:** `apply-permissions.sh --global` copies `agent-router/` in `~/.claude/hooks`
  (env.ini does not overwrite). `validate.sh` received py_compile-step for Python-config hooks.
- Tests: `harness/tests/test_router.py` (+10: block_router, --generate, behavioral hooks),
  `maind` `TestRouterConfigProvisioner` (+4). roadmap is marked activated + fixed outdated
  thesis about auto-activation of commands. **Fair limit:** hook does not run the command; `auto_dispatch`
  can overfire → default `propose`; marketplace-package commands - follow-up (in README).

### Added (RAG-plan formation discipline - aggressive perplexity-web + footer «Verification» + honesty)

Field-feedback: agents are reluctant to press RAG when generating a plan, although the plan is 100% should be on fresh
data; engine failure (perplexity-web locked/timeout, MCP lay down) was not submitted for a second pass; there wasn't
honesty clauses «call a crutch a crutch». Scope: CORE-skills + CLAUDE.md + docs + agent-packs (teeth).

- **CORE-skill `verify-claims` 0.2.0** (is distributed to each project): ladder - token saving
  (`perplexity-web` flat-rate → **aggressive default**; on a miss context7 fallback on perplexity-web, NOT on
  WebSearch); new **footer «Verification»** (RAG · unverified→**REPEAT PASS** · workarounds-`[POSSIBLE-DEFECT]`);
  honesty clause «not edits for the sake of edits, call a crutch a crutch». RU-source edited → EN-canon regenerated.
- **CORE-skill `query-craft`**: token-saving note (press `perplexity-web` aggressive) + how to record a failure
  engine in footer «Verification» (cross-ref on `verify-claims`).
- **Root `CLAUDE.md`**: «Decision Methodology» rewritten to be aggressive perplexity-web + footer «Verification»;
  new philosophy thesis **«RAG-delegation (token-saving)»**.
- **Root-skill `decision-verification`**: trigger «plan formation» + footer «Verification» + honesty.
- **Agent-packs (teeth): `_common` 0.3.0** — `orchestrator.md` received RAG-plan rule + output block
  `VERIFICATION`; **`backend-laravel` 0.10.0** — `dev-loop.js` `SLICE_RESULT_SCHEMA` received optional
  `tool_failures[]` (engine unavailable → repeat pass, do not mask).
- Provenance — `docs/reference.md` (industry prompt-engineering RAG-forcing/verification-footer, verif.
  `perplexity-web` 2026-07-01). **Fair limit:** interactive plan mode is not hardgated (no hook) —
  fix behavioral; teeth only in workflow-layer `dev-loop.js`.

### Added/Changed (harness — agent-pack migrator: monorepo-detect + anti-false-green)

- **Engine `agentpacks.py` — post-render path validation (`expect_globs`).** New field
  pack manifest: list single-brace-critical path globs; `render`/`upgrade` after
  renders are checked `target.glob(...)` and **print WARN for 0 matches** —
  deterministic security network vs. **false green** access-layer (when
  hardcoded paths do not match the project layout), regardless detect-sample
- **Engine - Summary conflict/.pack-new in `do_upgrade`** (`⚠ N conflict → manual
  merge: …`) — increases the visibility of unchecked edits (was only per-file warn).
- **Engine - condition `<!-- pack:ifnot KEY -->…<!-- pack:endif -->`** (mirror `pack:if`,
  «otherwise»-branch; from PR #96) — needed for dual-mode blocks (`SCAFFOLDS_SCHEMA`).
- **`backend-laravel` 0.9.0** (details - in his CHANGELOG, **supersedes PR #96**): `ACCESS_ROOT`
  auto-detection (`app`/`src`/`packages/*/src`) — supplanted `IS_LARAVEL_PACKAGE` (he couldn't
  monorepo) + layout-aware paths (drop `/Api`-segment) + `expect_globs`; **saved
  `SCAFFOLDS_SCHEMA`** from #96 (orthogonal axis: scaffold vs finished diagram, `pack:if/ifnot`).
  **Monorepo Laravel-packages are rendered correctly automatically** (pilot chatom opened the gap).
  Principle: each manual iteration of a fleet upgrade refines the base migrator.

### Added (harness — auto-allow orchestration tools `Workflow`/`Agent`/`TodoWrite`)

- **Presets `base` and `global` is now auto-enabled `Workflow`, `Agent`, `TodoWrite`.** This
  universal (off-stack) orchestration tools are therefore added to both common layers:
  `settings.base.json` (rolls into `.claude/settings.local.json` of each project) and
  `settings.global.json` (machine `~/.claude/settings.json` — applies to all projects at once).
  Root cause: startup `Workflow` spawns subagents at each phase (`Agent`) and leads the plan
  (`TodoWrite`), and without rules Claude Code asked for confirmation **after each stage** —
  multiphase work flow turned into a series of prompts. Security does not suffer: only allowed
  the tool call itself, the subagent executes its Bash/Read/Edit via the same permission-layer.
  Affected `packages/harness/configs/claude-code/settings.{base,global}.json`, docks
  `docs/configs/claude-permissions.md` and `docs/setup/claude.md`.
### Added (skiller — post-ran observability: `skiller analyze-run`)

- **`skiller analyze-run`** (`lib/skiller/analyze.py` + `cli.py`) — deterministic
  run analysis JSONL-logs Claude Code, **without running agents/spending tokens**.
  By agent: fact tokens `in/out`, **cache-hit%** (from field `usage`), model,
  wall-clock, tools, retrays, tool-errors. Skills: active set
  (`resolve_active_set`/`budget_for_set`) × actually loaded (`Skill`-calls) →
  **effective / DEAD** (in set, 0 downloads → repair triggers/remove) / out of set.
  Plus runtime failure scan (`Rate limited`/`SingletonLock`/…, heuristic).
  Flags `--last|--session|--project|--json|--store` (`--store` → JSON in
  `.claude/analyze/`, hit the cross-session trend). Closes the gap
  «budget (theory) ↔ eval (synthetic) ↔ real run». Complements quality
  skill `system/session-observer` (numbers vs «why»). +14 offline tests
  (`tests/test_analyze.py`); guide `docs/guide/analyze-run.md`. Fair limit:
  skill loading detection partial (only `Skill`-tool; native `skills:`-preload
  not visible).

### Added/Changed (harness — token-saving: downstream `deny` + agent-pack backend-laravel 0.5.0)

> Plan: `~/.claude/plans/idempotent-snacking-nest.md` (retrospective summary chatom + response Perplexity +
> token-audit; verified RAG). This P0-wave (publish-surface + workflow).

- **Downstream `permissions.deny`-presets (publish-surface, cheapest ROI).** `deny` — real
  token barrier (to built-in Read/Edit and on `cat/head/tail/sed`), `.claudeignore` is not official.
  `settings.laravel.json` += `storage/framework/**`, `bootstrap/cache/**`, `**/node_modules/**`,
  `vendor/bin/**` (NOT `vendor/**` entirely - vendor-sources are needed to verify the real API),
  `**/package-lock.json`, `**/.phpunit.cache/**`, `**/*.sqlite[3]`. `settings.base.json` += `~/.claude/logs/**`
  (hook log files). `settings.python.json` received deny-set (`__pycache__`/`.venv`/`.mypy_cache`/
  `.pytest_cache`/`.ruff_cache`/`*.egg-info`/`dist`/`build`). Entire logs are NOT denim - so as not to break
  `tail`-slice (selective-input).
- **agent-pack `backend-laravel` 0.5.0** (details - in his CHANGELOG): risk-adaptive review-gate
  (severity-enum, adversarial on HIGH, config-honesty, fresh-context), Lean-tiered model/effort-lanes,
  fairness of tests `[POSSIBLE-DEFECT]`, env-preflight in Setup, layout-agnostic globs rules + per-layer
  risk-annotations; fix false «project NOT on Pest» (chatom F2) → `{{TEST_FRAMEWORK}}`, hardcode pint →
  `{{CHECK_CMD}}`.
- **Migration: `agent-packs upgrade` now installs NEW version files** (not only safe-apply/conflict). Files,
  added in the new version of the pack (recon-agents 0.6.0), reach onboarded projects on `upgrade` (and not
  only at full `render`) — target does not exist, write is safe; obviously deleted optional (`removed_optional`)
  are not returned; local edits to existing files are still not overwritten (`conflict`→`.pack-new`). Important:
  because `maind sync` is calling exactly `upgrade`. +unit-test. The pack guide has been supplemented with a section «How tasks are set» +
  **mermaid-diagram** process dev-loop.

### Added/Changed (skiller — token-saving: plugin `task` + docker-router + context-economy/session-handoff)

- **New plugin `task`** (`packages/task/`, commands-only, auto-registration in marketplace, 51 plugin):
  intent commands `/task:design|dev|review|research|fix`. Plugin name `task` + files `commands/dev.md`
  etc. give exactly `/task:<verb>` (Claude Code names plugin commands as `<plugin>:<file>`; option
  `tasks`+`task-dev.md` would give `/tasks:task-dev` — fixed). Each one kicks `model:`+`effort:` (frontmatter) under
  profile, interrupting session settings - closes «forgot to switch model/effort/mode». dev→Opus/high
  (planning) + Lean-tiered risk subagents; fix→Sonnet/medium single-agent; review→Opus/xhigh adversarial;
  design/research→Opus/high + research-fanout.
- **`task` — default-on in EVERY project** (`skiller.config.DEFAULT_COMMAND_PLUGINS = ["task"]`): connect
  includes the plugin `task` automatically (as supervised `core`) — marketplace-guarded (on the old one
  marketplace / in the test registry is silently skipped), `--no-core` does NOT touch it, dotted opt-out —
  `enabledPlugins["task@swissknifeman"]=false`. New onboarded projects receive `/task:*` without manual
  edits. Resident tier-0 no tax (command descriptions are not injected into every request).
- **Doctor registers a pass** (`maind doctor --audit core`): dimension `core` now in addition to CORE-skills
  also checks default command plugins - `cmd⚠(no: /task:*)` on projects without `task`. Checklist
  integration (`integration-checklist.md`) added a clause about `core`/`task` in connect.
- **`devops/docker` → thin router-skill** (v0.2.0, `risk: read`): description-trigger + routing table by
  to all 6 sub-skills (docker-php/postgres/dev-prod/services/vite/makefile) + assembly order (DAG in
  requires/produces_for); deep expertise - in `snippets/docker-expert.md` on-demand (progressive disclosure).
  «Background» cluster: resident only router-description, specialists are loaded as needed.
- **`general/context-economy` v1.2.0**: §8 — recon-subagents (heavy reading in an isolated window, up only
  summary), selective-input (slice instead of whole file; `tail`/`grep`/`git diff`; nuance: `deny` blocks and
  `tail`), cost visibility (`/usage`, not `/cost`); back-ref to the plugin `tasks`.
- **`general/session-handoff`**: `outputs: []`→`[".claude/handoffs/*.md"]` + standard path
  `.claude/handoffs/YYYY-MM-DD-<topic>.md` (is indexed maind). RU→EN re-stamped, `skiller registry` driven away.
  Audit recommended `risk:draft→stable` — **rejected** by verification (`stable` not in
  `RISK_VALUES={read,draft,write,external}` → would break validate; maturity - separate field `level`, not `risk`).
- **F8 budget-governance — `skiller budget --check-core`** (+ `--strict` for CI) and constant
  `RESIDENT_BUDGET_TARGET=600` (config.py): resident gate ⊕ tier-0-budget `CORE_SKILLS` (is loaded into EVERY
  request) against target; tailed `validate.sh` (informational). Measurement opened by: resident CORE now
  **592/600 current** — near the ceiling (comment promised ~480), so the gate against the quiet growth of the kernel is objective.
- **D4 — 5 new production-readiness-skills** (from retrospective chatom; local, bilingual RU→EN, 205 skills):
  `php:transactional-outbox-relay` (persist+outbox in one tx, sole owner retry, idempotency,
  after-commit), `php:production-readiness-checklist` (atomicity/racing/config-honesty/cursor/queue-semantics -
  class of defects that green tests mask), `php:cursor-pagination-design` (keyset by non-nullable key,
  composite-tiebreak), `php:namespace-refactor-safety` (three-phase alias→use→rename, prefix traps, contract-seam),
  `laravel-architecture:config-driven-abstraction` (Registry+Builder, config:cache-safe, per-variant ≠ runtime `$table`).
  Retrospective #5 (state-machine-race) and #6 (env-driven-test) **collapsed** in production-readiness-checklist +
  dev-loop env-preflight (anti-bloat: do not duplicate existing ones `enum-state-machine`/`db-test-preflight`).
- **F2 — `skiller doctor --downstream`** (audit publish-surface onboarded projects - there is the main runtime-consumption
  tokens, not in the registry): per-project hygiene always-loaded layer - `CLAUDE.md` ≤200 lines, scoped vs unscoped
  `.claude/rules`, availability `permissions.deny`-preset. Measurement on real projects revealed over-budget CLAUDE.md
  (sova 1214, cms 813, flexcrm 738 lines, …) vs healthy (chatom 123, corex 169) — operationalizes
  audit keynote (measure the generated artifact, not templates). +unit-test (202 test).
- **A2/A3 — thin-orchestrator + skill-on-demand documented/forwarded:** `docs/guide/skill-taxonomy.md`
  received section «Router-skill» (thin background cluster orchestrator - sample docker); orchestrator-pack agent
  (`_common/orchestrator.md`) — fields `risk:`+`skills:` in PLAN (minimum set for task type + risk→model/
  effort/review depth), instead of full preload. (C — durable per-phase handover: implemented «light» version -
  compact summaries in briefs + plan-file-primary + native resume workflow; on-disk-the double is redundant, do not enter it.)

### Changed (skiller — `perplexity-web-mcp` v1.3.0: demon-competition in skills)

- **`research/query-craft`**: section «Reliability keyless-bridge» (lock/serialization, prohibition
  «do not parallel») rewritten to «Competitiveness and sustainability `perplexity-web` (demon v1.3.0)».
  Parallel allowed until `maxConcurrency` (default 3); pools (`--pool`) as config MCP; code table
  errors (`BROWSER_BUSY`/`TIMEOUT`/`LOGIN_REQUIRED`/`PROTOCOL_MISMATCH`); non-contract breaks
  (`ECONNRESET`/«connection closed» → under-inflated Chromium → `npx playwright install`); `search_deep`
  to ~10 min and does not block parallel `search`; checklist updated. Former bypass «do not parallel»
  filmed as legacy.
- **`general/mcp-advisor`**: pull note to keyless `perplexity-web` (demon v1.3.0, isolation through
  `--pool=<project>`).
- **`docs/reference.md`**: line about integration-note `perplexity-web-mcp` v1.3.0 (verdict **adopt**).
- RU→EN regenerated + `check-translations.sh --stamp`; `skiller registry` (`skills.json`, `budget.md`).
  Contract verified end-to-end live: 3 parallel `search` isolated (no cross-read), fix
  background tab anti-throttling confirmed.

### Changed (maind — rename ecosystem project DocVault → Vaulter)

- **Project `docvault` renamed to `vaulter`** (product DocVault → Vaulter). `derive.py`:
  `FIRST_PARTY_VENDORS` `docvault`→`vaulter`; `DOC_ALIASES` — new canon `vaulter`,
  plus **back-compat alias `docvault` → `vaulter`** (old doc-backlinks Brain resolve).
  Examples/comments (`namespaces.py`, `design-notes.md`, skill `cross-project-optimizer`)
  updated. Hub state (`config.json` id/scope/path, graph, `.mcp.json` scope `project:vaulter`,
  memory, agent-pack `vaulter-*`) rolled out VCS; consumer `flexcrm` and the package itself -
  separate repositories/PR.

### Added (maind — opt-in emits `.mcp.json.example` + hygiene `.gitignore`)

- **`maind deploy`/`sync` when `mcp.emit_example: true`** emit next to the real one `.mcp.json`
  portable `.mcp.json.example`: machine-specific abs. ways → placeholders (`<ABS_PATH_TO_PROJECT>`,
  `<HOME>`), direction `${MAIND_BIN:-maind}` saved. One generator → two outputs from one `data`
  (`mcpconfig.write_example`) — discrepancy real↔.example not possible by design.
- **Hygiene `.gitignore`** (`reconcile_gitignore`): real config → in `.gitignore` (append-if-absent),
  him `.example` → out (remove-if-present, for the template to be committed); idempotent; warn, if real
  file is already being tracked git. **Opt-in** (is disabled by default - we do not touch other people's repo without a flag).
  Closes the machine-specific serena path `--project <abs>`, which indirection `maind` (PR #94) not
  decided. +tests `test_mcpconfig`; status a roadmap note → implemented (opt-in).

### Fixed (skiller — false `[MOVED]` in `skiller status` on the monorepo registry)

- **`skiller status` compared source marketplace with `env.root` (package directory), and not with root
  monorepo.** In monorepo `marketplace.json` lies in the ROOT (there `connect`/`update` write
  `source` via `find_repo_root`), therefore comparison with `env.root` (`packages/skiller`) gave
  perpetual false flag `[MOVED - fix: skiller update]`, which `skiller update` physically
  is unable to extinguish (it writes the correct repo root). Now `status` resolves expected
  source also - `find_repo_root(env.root) or env.root`. Affected `lib/skiller/status.py`.

### Added (skiller — CORE-skill `research/query-craft`: discipline of formulating search queries)

- **New skill `research/query-craft`** — how to FORMULATE a query to a search engine/dock engine
  (Perplexity Web · WebSearch · context7): iron rule «never a naked library request
  without version+context» (anti-pattern «Laravel how to do X?» → «Laravel 11: … for 2025»); 5 slots
  request (verb · subject+version · context · specifics · format/limit); select engine and mode
  Perplexity (`search`/`search_advanced`/`search_deep`, `sources` web/academic/social); section
  «Reliability keyless-bridge» (lock/timeout on heavy requests → do not parallel, split, escalate
  on WebSearch/context7, system - API-key option).
- **Ends RAG-trio discipline in `CORE_SKILLS`** (is distributed to each project, on-trigger):
  `mcp-advisor` (what to connect) · `verify-claims` (when/what to verify) · `query-craft` (like
  ask). Skill physically in the bucket `research`, in CORE — at the link. `verify-claims`/`mcp-advisor`
  received back-reference on him, the roles are cut (verify-claims = «when», query-craft = «like»).
- Bilingual (RU-source → EN-canon); fact-basis - official Perplexity Prompt Guide,
  verified RAG (WebSearch+WebFetch) 2026-06-29 (see `docs/reference.md`). 200 unit-tests OK,
  `validate.sh` green (201 skill).

### Added (skiller — ecosystem locators: agent navigation to nodes Brain/swissknifeman)

- **Two locator skills** in the bucket `system` (on-trigger, NOT in CORE — resident token budget does not grow):
  `system/brain-locator` (from any project reach Brain-volta) and `system/swissknifeman-locator`
  (from external repo reach the managing monorepo). Goal - the agent no longer guesses where the ecosystem nodes are.
- **Non-hardcode path resolution.** brain-locator repeats canon `maind` (`projects.py::brain_path`):
  `integrations.brain.path` → project `id==brain` → `$MAIND_BRAIN_VAULT` → candidates from `$HOME`
  (`~/Vaults/Brain` first); swissknifeman-locator — via installed binary (`readlink` to repo) →
  `$SWISSKNIFEMAN_ROOT` → `$HOME`-candidates. Everyone has a ready `cd`-command and node sign check.
- **Communication Abstracts.** brain-locator carries a marker «skill connected → project synchronized on Brain», explains
  directory `.projects.json` / control-notes / `CLAUDE.md` / wikilinks; swissknifeman-locator — `config.json`
  as a registry of related projects (two-sidedness) and communication identification by
  `.swissknifeman/config.json` / `skills-lock.json` / `enabledPlugins`.
- **Associated with the map.** `requires: [local-topology]`; `local-topology` received them in `produces_for` +
  note about fallback-node resolution without `~/.swissknifeman/topology.json`.

### Added (maind — sync protection visibility + explicit directory ownership model)

- **`sync_from_brain` warns of a change visibility** doc-folders of an existing project
  (`_warn_visibility_changes`) — a common sign of rotten brain `.projects.json` (need it
  regenerate from frontmatter before sync). brain still «wins» (field is overwritten):
  directory source of truth/visibility — frontmatter control-notes → `.projects.json` → `config.json`.
- **Explicit model «three layers + fact owner»** in `docs/guide/config.md`: frontmatter Brain (source)
  → `.projects.json` (gitignored cache) → `config.json` (import + maind-fields). Semantics divorced
  `repo` (GitHub-slug) ≠ `local_path` (path to code) and inversion brain-schemas (`repo` = path → `local_path`
  on import). `config.example.json` — canonical `docs_folders` `{id,vault,repo,visibility}`.

### Changed (maind — binary direction in `.mcp.json` instead of absolute path)

- **`deploy.py::_maind_entry` writes `"${MAIND_BIN:-maind}"`** instead `<abs>/packages/maind/bin/maind`.
  Claude Code reveals an indication from the process environment (default `maind` by PATH — `~/.local/bin`
  from `install.sh`); the same `MAIND_BIN`, what do you have health-hooks. Portable to another machine/CI and when
  repo transfer - to `.mcp.json` no longer hard-skinned `/home/...`. Test lock on `command`
  (`test_deploy.py`), example in `docs/guide/mcp.md` updated.
- Already onboarded projects are migrated idempotently: `maind sync --only mcp --all` (non-destructive
  merge + `.bak`). Serena-path `--project <abs>` remains machine-specific - separate phase
  (a roadmap note).
- Guides are brought into line with reality: `project-tooling-runbook` §«Hygiene» (nuance
  `${VAR:-default}` — Claude Code exposes from the process environment, not from the project one `.env`; maind-path
  is indicated, the serena path remains) and a roadmap note (problem narrowed down to serena-path).

### Added

- **`laravel-architecture/eloquent-accessors`** (new skill) — canon of modern Eloquent
  accessors/mutators via `Attribute::make(get:, set:)` instead legacy `getXxxAttribute()`:
  syntax/naming/visibility/typing, class placement (after relations, before scopes),
  migration legacy, border with `casts()`. Snippet `accessor.php` (getter, getter+setter with
  normalization, multiline, migration). Promote project-local skill from the project agelto
  (anonymized, raised to the registry according to the universality rule) via `field-feedback-loop`.

### Changed

- **`project-tooling-runbook`** — new section «Hygiene machine-specific configs»: config with
  absolute local paths or secrets (`.mcp.json` any provider, `.cursor/.vscode/mcp.json`,
  `.claude/*`) do not commit as is. Two-level rule: indication through `.env` (preferably
  config remains portable) or gitignore real + **synchronous** `.example` with placeholders
  (like `.env`↔`.env.example`). Cross-link from `ecosystem-integration` (step deploy: `.mcp.json` carries
  absolute paths maind/Serena). Triggers for both skills have been expanded.

- **`harness` agent-pack `backend-laravel` 0.2.0 → 0.3.0** — deuniversalization of templates: removed
  secure environment of one project (machine-specific `php8.5`/`pgsql`/`Postgres`/`/usr/bin/php8.4` and false
  for most «phpstan not installed», «do not add migrations - the diagram is complete»). Test framework
  is now parametric (`{{TEST_FRAMEWORK}}` — previously the interview variable was ignored, hardcode
  «PHPUnit-native, NOT Pest»); identity slice-builder softened to «Laravel/REST API **or package**».
  Caught on field onboarding azguard (Pest+Testbench-package) → `field-feedback-loop` path 1 (fix
  generator, not artifact). Affected agents/rules/workflow/docs pack.

- **Doc-folders: name ↔ visibility untied (Brain doc-sync + maind + core).** Previously «publicity»
  folder was encoded with its name (hardcode `docs-public`), party names vault/repo were tough
  are symmetrical. Now - a single folder model `{id, vault, repo, visibility}`: party names may
  differ (in valt `docs-public` ↔ in the repo `docs`), status `public|private` is name independent,
  wikilink-publication gate - by `visibility`. Visibility default **by project type**
  (`core.docs_visibility_for`): package/library → `docs` public, product → private. Source
  truths - frontmatter control-notes Brain; maind caches `docs_folders` (flat normalization
  legacy-list on the fly, complete back-compat). Caught on package onboarding chatom →
  `field-feedback-loop`. Affected `core/project.py`, `maind/{config,onboard,common}`, Brain
  `lib/brain/{folders,engine,config,status,listing,syncing,watch,discovery}` + docks/tests.

- **`harness` agent-pack `backend-laravel` 0.3.0 → 0.4.0** + `python-backend`/`node-frontend`/
  `dart-flutter` 0.1.0 → 0.2.0 — **AI-guide `subagents-and-workflows.md` moved from public
  `docs/05_AI/guidelines/` in `.claude/guidelines/`** (default `DOCS_DIR`). This is an internal artifact
  for agents, not public VitePress-package documentation (otherwise leaked to the publication and to Brain-valt).
  From template backend-laravel removed erroneous Brain-frontmatter (`parent: [[05_AI]]`) and wiki link.
  Migration of installed projects: new guide to `.claude/guidelines/`, delete the old path manually.

### Roadmap

- **roadmap note** — deferred: teach `maind deploy/sync` issue it yourself
  `.mcp.json.example` (placeholders) + lead `.gitignore` (mechanism instead of agent discipline).
  Implementation criterion - repeated leakage of abs. paths/secrets or inability to raise MCP without `.example`.
  Routed via `field-feedback-loop` from field case agelto (setting playwright-MCP).

### Added (audit wave 3 — docs, ergonomics, dude)

- **`analyst status` / `analyst compact`** (S16). `status [--json]` — read-only store summary:
  counters by state, `curated-ready`, `promote_failed`, number of events, dates of last
  `digest`/`recompute`. `compact [--before ISO] [--dry-run]` — deterministically reduces old
  events `events.ndjson` into one snapshot-event for the lesson; amounts (S/N/tests) and the age of the latter
  events are saved, so `recompute` before and after gives **the same** confidence (verified e2e:
  0.7968 → 0.7968). Transaction provenance - in `audit.ndjson`. New module `analyst/status.py` (+10 tests).
- **`packages/analyst/docs/guide/tuning.md`** (S13) — a single directory of all thresholds (confidence-
  arithmetic, dashes, state-machine, Jaccard-dedup/consolidation): parameter · file · value ·
  effect↑/↓ · calibration method. Linked in sidebar (standalone + umbrella unit) and from
  `lifecycle.md`.
- **`core.paths.state_dir(home, app=None)`** (S15) — single literal source `.swissknifeman`
  for umbrella state (root `~/.swissknifeman` — skiller; subdirectory `~/.swissknifeman/analyst`).
  `maind` is intentionally NOT included (him state `~/.maind` — separate node-state, documented). +3 test.

### Changed (honesty + provenance)

- **Comment `analyst/confidence.py` — honest** (S13, D3-discipline): false removed «verified
  perplexity, tune by false-positive rate» → «curve-fitting heuristics NOT
  calibrated to FP-rate» (no real calibration was carried out - separate research-task).
- **`docs/reference.md`: card mem0** (S17, provenance F-RAG-2) — consolidation taxonomy mem0
  = ADD/UPDATE/DELETE/NOOP; `analyst` adapts as **ADD/UPDATE/NOOP/CONFLICT** (`CONFLICT`
  instead `DELETE` — auto-removal would violate the invariant «man in the gate»). Row in table
  clarified + separate card.

## [0.7.1] - 2026-06-28

### Added

- **`founder/idea-audit`** — end-to-end destructive audit of an idea / concept / finished technical specification: First-Principles
  Decomposition → market skepticism (5 vectors) → architectural pre-mortem (on AI-specific) →
  Kill-or-Build Scoring + verdict. Bridge idea→architecture between `idea-discovery` and `brd`/`architecture`.
  Bilingual (SKILL.ru.md → SKILL.md). External facts verified through RAG (Founder's Playbook — real;
  CB Insights ~42% — classic, 2026 ~43% PMF); provenance — `docs/reference.md`.
- **`provider-skills/` — SSOT skills-capability for external agents (paste-in).** Text that
  person copies to UI provider (Perplexity → My Skills), and not delivered by the registry connect/vendor;
  canon versioned here, consumers (Brain) hold provenance-linked copy. First skill -
  `perplexity/idea-architect.md` (modes Idea/Spec/Architecture). The registry counts them as `references`.
- **Internal skill `field-feedback-loop`** (`.claude/skills/`, not exported) — reverse loop
  connections from field work: tooling deviation/runbook from the one promised during implementation/synchronization
  project is routed to obvious-bug→fixed-immediately or new/questionable→proposal
  (`roadmap/`/issue + capture to memory), but not swallowed. Mechanism principle «based on actual measurement
  problems»; linked to `release-discipline`/`decision-verification`.

### Changed

- **`pm/requirement-critic`** — mode Spec Audit: Optimism Bias Detector, `[UNVERIFIED]`-labels for numbers without
  source, completeness checklist for product/startup TK (target customer, kill-criteria, metric PMF).
- **`founder/adversarial-check`** — section **stage-context** (idea→market, mvp→retention, launch→CAC/LTV).
- **`founder/idea-discovery`** — **falsification signals** (measurable threshold) to each kill-criterion.
- **`architect/architecture`** — required field **`business_rationale`** in each Options-block.
- **`founder/startup-lifecycle`** — evidence gate: **≥1 external signal** for each exit-criterion.
- **`founder/risk-assessment`** — 6-I risk category **AI/Agentic** (hallucination/drift/injection/cost
  creep/eval-gaps/single-provider); tag `agentic`.

## [0.7.0] - 2026-06-28

### Added

- **Single control-surface projects (4 layer, strictly + machine readable).** One command - complete
  project inventory/fleet by layer *skills · roles/agent-packs · MCP · memory-graph* with drift→fix
  hints; spot re-sync already gives `maind sync --only <cap>`.
  - `maind projects status` now takes inventory **role layer** (`probe_project` reads
    `.claude/agent-pack.lock.json` → field `agent_packs`) and prints **drift→fix** (`probe.drift_hints`:
    `{layer, issue, fix}` — e.g. «profile awaits pack X → `maind sync --only agent-pack`»). `--json`
    carries `agent_packs` + `fixes` for each project.
  - **`swissknifeman status [<id>|--all] [--json]`** — umbrella facade of a single 4-layer status
    (→ `maind projects status`); bare/`--target` → `skiller status` (back-compat saved).
  - **`--json`** added to `skiller status` (channels/profile/budget/overlap) and
    `harness agent-packs doctor` (pack directory + installed) — is machine readable for the agent.

### Docs

- **Root `CLAUDE.md` — section «Philosophy and framework»:** principles scattered throughout the text are summarized in
  explicit **abstracts** (umbrella≠tool, single source of truth, stdlib-only, deterministic
  delivery, faithful-first+provenance, insulation namespace, speculative→`roadmap/`) and hard
  **frames** («we don't marry them»: pip/JS-runtime, duplicate primitives, umbrella renaming/prefixes
  plugins, break paths `maind`, Proprietary-vendoring, assert external facts from memory).
- **Section «References and provenance»:** `CLAUDE.md` now points to the provenance directory
  [`docs/reference.md`](docs/reference.md) (studied external sources: verdict adopt/reference/skip
  + what is taken) and per-skill passports `upstream.json`, with rule «used an external resource - check».
- **Runnbook `project-tooling-runbook` — section «Agents/roles (agent-packs)»:** project setup
  is now explicit = skills **AND** agent-packs (roles/agents - a separate subsystem `harness agent-packs`:
  subagents + workflow + review-gate). B «Order „give everything to the project“» step added agent-packs;
  fixed auto-path (`maind onboard`/`setup` with the project type installs a pack from `profiles/<type>.json`)
  and reason for skipping manually `connect`/untyped record. Closes the gap «
  roles/code review for a large task».
- **New umbrella page [`docs/control-surface.md`](docs/control-surface.md):** table
  «layer → status command → fix/re-sync → lock» + operating cycle `status --json → fixes[] →
  maind sync --only <cap>`. Runnbook `project-tooling-runbook` added section «Control-surface»,
  explicit steps MCP/memory/graph, and «Verification» reduced to `swissknifeman status <id>`.

## [0.6.0] - 2026-06-27

**Repository audit (multi-agent, 122 confirmed findings) → remediation in 7 phases.**
Headline — **smart connection**: connect distributes a curated plugin `core` (EXACTLY 7 `CORE_SKILLS`
via links, no copies) instead of whole buckets general+oss-dev → resident ⊕ tier-0 **~1956 → ~480
current/project** for each request; budget-aware connect shows the price of the set; Cyrillic alphabet has been removed from
EN-descriptions (−643 current) + CI-gate. Plus: reliability of connection logic (TOCTOU, validation lock,
effective path drift), cross-package deducing of primitives in `core`, insulation maind (scope-markers,
recall-crowding, working graph-namespace), +18 tests and ruff on `tests/`, docs are given in
code compliance. Compatibility maintained (onboarded projects - migration hint, merge-only).

### Docs (audit 2026-06 — Phase 7: accuracy of docks and DX)

- **Docs no longer lie about CORE-policy.** `skiller/CLAUDE.md`, `docs/guide/skills-architecture.md`,
  `docs/guide/archetypes.md` and root `CLAUDE.md` updated for smart connection: connect distributes
  curated plugin `core` (and NOT buckets general+oss-dev). Plugin counter marketplace ~50.
- **Command documented `harness agent-packs`** (`list|render|upgrade|doctor` + flags) in
  `harness/CLAUDE.md` — was previously missing from the help CLI.
- **`research/README.md`** (new): index of work records with explicit marking «NOT canon» and pointer
  to sources of truth (docs/CHANGELOG/CLAUDE.md) + methodology reminder (pre-check audits).

### Added (audit 2026-06 — Phase 6: tests and CI)

- **Unit tests for new behavior:** `core.load_json_db` (missing/corrupt-backup/version-die),
  `core.is_within`/`is_within_lexical` (traversal), `core.atomic_write_*` mode=0600;
  `maind.split_scope` (strip-all tokens, unforgeable owner); `harness.categorize_file_change`
  (matrix new/user-owned/conflict/safe-apply/nochange); skiller registry issuer supervised `core`-plugin;
  connect pushes `core` (not buckets), `--no-core`, graceful-skip without core in marketplace. (+18 tests.)
- **CI ruff now lints and `tests/`** (earlier - only `lib/`, garbage was accumulating in the tests: F401/F841).
  Previous debt cleared; The bar is now the same for test code.

### Fixed (audit 2026-06 — Phase 5: correctness and isolation maind)

- **`memory.split_scope` — no longer leak marker-artifacts:** remove ALL presenters `[[s:…]]`
  (in case of nested/repeated in content), owner scope = first marker (cannot be faked).
- **`memory` RECALL_LIMIT 50 → 200 + saturation warning:** pool common to all projects
  ecosystems, a narrow window squeezed out relevant facts scope strangers (crowding). When saturated
  (daemon returned the entire pool) — `warn`, that the facts scope might not fit.
- **MCP `maind_graph_query`/`neighbors`: parameter `namespace` NOW works** — used to be
  declared in the schema but was silently ignored and the bypass federated ALL projects (alien nodes namespace
  leaked to depth>1). Now narrows union; starting node is still under `_project_blocked`.
- Tested and NOT changed (finds are overrated/are already closed): `cmd_sync` already fail-soft with non-zero
  rc and the visibility of failures (per-project `failed`); `deploy` already health-WARN'etc (cannot be blocked -
  `.mcp.json` is static and valid regardless of the daemon); absolute paths in `.mcp.json` —
  intentional (CLAUDE.md «do not break», 17 projects), env-indirection - separate additive PR.

### Changed (audit 2026-06 — Phase 4: cross-packet deduc → core)

- **`core.paths`** (new): `is_within`/`is_within_lexical` — single containment-primitive
  (was only in `skiller.common`, duplicated the pattern in connect/vendor/skillset/eval). Exported
  from `core`; `skiller.common` will re-export for back-compat.
- **`core.io.load_json_db`** (new): JSON-DB with recovery (broken → backup `.corrupt.<date>` +
  warn; version > max → die). Condensed verbatim copies `skiller.state.load_db` and
  `maind.common.load_json_db` (diverged in the backup name/text) to one source.
- **`skiller.common.safe_copy_skill`** (new): unified secure copy skill (containment +
  removal symlink/file/directory + TOCTOU-recheck + `SKILL_IGNORE`) — common for
  `vendor.copy_skill` and `skillset.sync_skillset` (used to be duplicated, diverging in safety;
  TOCTOU-fix Phase 3 now also in vendor). Legacy `vendor` re-copy became clean-replace (like skillset).
- Consciously NOT touched: `apply_permissions` (skiller→harness — is the delegation boundary across
  subprocess, not a duplicate); consolidation of 3 config validators (schema-divergent - separate
  risk/PR).

### Fixed (audit 2026-06 — Phase 3: reliability of connection logic)

- **TOCTOU in `skillset.sync_skillset`:** between deletions `dst` and `copytree` someone else's process could
  recreate the path with a symlink outward (copytree would follow it). Added re-check after
  removal: `dst` exists → race, skip (fail-closed).
- **Validation `skills-lock.json` (`load_lock`):** broken/non-structural lock is no longer interpreted
  SILENT as empty (this led to recopying all managed-skills). Now `warn` + rebuild
  from the config; Availability is checked dict `skills`.
- **`connect`: path drift marketplace — effective tip.** Directory-source with DIFFERENT path
  (repository moved → plugins are not loading) now gives `⚠` with the command `--fix-path`/`update`,
  not silent «keeping it». Other source type (github/…) is left as a conscious choice.
- **`apply_permissions`: appearance of failure.** Non-zero rc harness with EMPTY stderr was silent before
  (presets deny/allow did not go unnoticed) — now `warn` always, with a restart command.
- **Order lock→manifest documented as intentional** (lock — detection source of truth
  `plan_sync`, is written with authority; manifest — derivative): protection against «reverse repairs».

### Added (audit 2026-06 — Phase 2: smart connection, saving tokens)

- **Curated Light `core`-plugin (connect-channel).** CORE-policy `connect` now distributes to
  each project ONE lightweight plugin `core` (== `CORE_SKILLS`, 7 skills) INSTEAD of whole buckets
  `general`(19)+`oss-dev`(10). marketplace-entry `source:"./"` + explicit `skills[]` loads EXACTLY
  these 7 skills (skills physically remain in their buckets - without copies/symlinks; mechanism
  confirmed by doc Claude Code). **Residential savings ⊕ tier-0: 1956 → 476 current ≈ −1480
  current/project for EVERY request.** `--no-core` disables; `registry.py` issues a plugin, `validate.sh`
  gateitis (skills-paths exist). Migration: onboarded projects with old ones `general/oss-dev`
  `connect` prompts you to remove them (merge-only, we don’t touch it ourselves).
- **Budget-aware connect.** `connect` prints the line `Resident: ~N current ⊕ tier-0 (M skills)` —
  set price is visible BEFORE recording (source of mathematics - single `budget.skill_budget`). «Smart
  connection»: fewer plugins / `--no-core` → cheaper.
- **Cyrillic alphabet removed from 21 EN-descriptions** (resident tier-0): 20 skills + `generate-skill`
  translated into English canon (RU-source remains in `SKILL.ru.md`), activation triggers
  saved. tier-0 for all 195: 12375 → 11732 current (−643). EN cheaper RU at the tokenizer.
- **CI-description gate** (`validate.sh`): Cyrillic in `description`/`name` SKILL.md → ERROR
  (SKILL.md — EN-canon resident tier-0); `description` > 450 char → WARN (bloated tax).
  Prevents regression - savings are consolidated.

### Fixed (audit 2026-06 — Phase 1: quick wins)

- **The conflict in skill names has been resolved:** `php/naming-conventions` → frontmatter `name:
  php-naming-conventions`. Registry by-name map (`lock._registry_map`,
  `vendor.build_requires_index` via `setdefault`) silently dropped one of the two skills with the name
  `naming-conventions` (general+php). Updated link in agent `php/agents/laravel-implementer`,
  registry has been regenerated, EN-marker re-stamped.
- **Validation `project.id` (maind):** id limited `[A-Za-z0-9._-]` (`config.PROJECT_ID_RE`) —
  he goes to scope-memory token `[[s:project:<id>]]` and namespace; special characters (`]`, space,
  line feed) broke parsing scope when recall/forget and could replace someone else's scope.
- **`config.json` is written with permissions `0o600`** (node secrets): `core.atomic_write_text/json`
  received opt. `mode=` (chmod on `.tmp` BEFORE `os.replace` — without window world-readable);
  `projects.write_config` applies `0o600`.
- **eval-assertions `file_exists`/`file_absent` are protected from traversal** (`is_within`): `value`
  from `evals.json` (incl. external skills) will not escape the run directory (fail-closed).
- **MCP-error handler logs argument KEYS** tool (not values - memory/secrets)
  for diagnostics; naked `except: pass` in `probe`/`memory` are provided with explanatory comments.
- **`agentpacks.do_upgrade`:** file categorization logic has been cleaned up `categorize_file_change`
  (matrix under test new/user-owned/conflict/safe-apply/nochange).
- **Marker for manual counters** in `docs/index.md` («195/45» — check with `skiller registry`).

### Fixed (skiller — drift-path stability and root marketplace)

- **`connect`: source marketplace points to the ROOT monorepo**, and not to the package directory
  (`env.root`). `marketplace.json` is generated at the root of the repo with relative `source`-paths;
  before `connect` announced marketplace under `packages/skiller`, where Claude Code couldn't find it
  `.claude-plugin/marketplace.json` and plugins were not connected. Added flag `--fix-path` for
  updating the rotten path in existing settings.
- **`resolve_skillset`/`_match`: drift-stability after splitting buckets** — old path
  `oldbucket/skill` (e.g. `frontend/vue` → `frontend-vue/vue`) is no longer lost silently: when
  miss on full key token path is achieved by basename and caller prints
  migration-warning with old→in a new way (`update .swissknifeman/config.json`). Regression test.

### Changed (audit - finishing the deferred: super-skill + Serena-pin)

- **3 vendored super-skill demotivated in «navigators»** (`pm/product`, `architect/engineering`,
  `operator/operations-cx`) — they duplicated mature granular native skills (9/13/5) and
  intercepted the entire bucket over-broad trigger («any … work»). `description` narrowed to «review
  bucket; for a specific task → granular skill», added a block of backlinks to the body
  granular. Trigger conflict resolved, provenance (upstream `notify`) saved.
- **One-way borders Group B closed:** `research/research`→`general/verify-claims` (RAG),
  `legal/legal`→`architect/legal-compliance`, `security/security`→`architect/security-design`
  (run-time ↔ design-time). 7 super-skill-only buckets (creative/finance/legal/…) left -
  they are the only domain coverage.
- **Serena pinned to the release tag** (`constants.SERENA_SRC = git+…/oraios/serena@v1.5.3`,
  was bare-main) — breaking-change to main will not suddenly break the code graph for all projects. One
  bump-point. Version **verified via RAG** (latest release v1.5.3, 2026-05-26;
  `@agentmemory/agentmemory ^0.9.26` and jscpd-`npx --yes` checked - relevant, no action required).

## [0.5.0] - 2026-06-26

### Fixed (audit - fan-out stability, gates CI, tails)

- **maind sync — fail-soft fan-out** (`sync.run_sync`): the fall of one provider no longer brings down the whole
  rolling out - the rest are practicing, the fallen one is marked `status=failed` per-project (is visible in the output,
  return code `cmd_sync` non-zero). `_agent_pack_run`: `rc!=0` → `failed` (was `skip` — failure
  render pack was invisible); `harness not available` remains graceful `skip`.
- **validate.sh: gate of bilingual freshness** (section 14) — `check-translations.sh --strict`: edited
  `SKILL.ru.md` without regeneration `SKILL.md` (or without `ru-source-sha256`) now crashes in CI, and not silent.
- **bin/swissknifeman:** dead alias removed `validate` (skiller-there is no such command - the routing provided
  «Unknown command»).
- _Tested, NOT a bug:_ `config.example.json` `type=node-package` + `code_language=python` — intentional
  demo override mixed repo (yes `_comment_code_graph`), is not a defect.
- _Postponed (tracked):_ RAG-verification of the relevance of external pins (`@agentmemory/agentmemory ^0.9.26`,
  Serena git-pin, jscpd, ruff) — by methodology `decision-verification` is done BEFORE bump'ohm
  dependencies; bump'but not here. Audit upstream-super-skill (name=dir, backlinks) — separate
  per-skill pass.

### Added (audit - coverage of local skills + scenario recipes for archetypes)

- **New governance-skill `harness-operations`** (`.claude/skills/`) — for the package `harness` there was no
  one operational skill. Team map (`permissions`/`mcp`/`hooks`/`agent-packs`/`doctor`),
  preset catalog (`settings.*` on stacks, `mcp/<name>.json`, modes auto-approve), and undocumented
  subsystem **agent-packs** (4 glass + 4 role-pack with `pack:if`-templating). So that the agent does not guess
  for environment task Claude Code.
- **`maind-overview` expanded:** `maind verify` (proof-of-life vs `health`), registry commands/orchestration
  (`projects`/`agents`/`namespaces`/`workspace`/`run`/`fleet`/`migrate`/`deploy`), table 11 MCP-tools
  with a note about insulation scope (per-project server is limited by its project).
- **Archetype Blender** — was a space: `.blend`/`bpy`-project was detected as `standalone`. Added
  `blender` in `core.PROJECT_TYPES`/`LANGUAGE_BY_TYPE` (python) + detect (`*.blend`/`blender_manifest.toml`/
  `import bpy`, before python-backend) + `profiles/blender.json` (buckets blender/blender-modeling/python/
  quality). Tests - `core/tests/test_core.py` (+3).
- **`docs/guide/archetypes.md`** — recipes for 9 archetypes (detect → buckets/MCP/presets/agent-pack) +
  **non-obvious forks** (connect vs vendor, CORE, memory, namespace, Serena, Nuxt-vs-Vue-SPA) — to
  onboarding of a typical project did not raise any questions. B nav skiller-docs.
- **Scenario text cases (eval-harnes)** started for CORE-skill `general/compact-responses`
  (`evals/{evals,pressure,triggers}.json` — typical tasks + temptations + trigger accuracy). Coating
  `evals/` 3→4; mechanism and extension are documented in `archetypes.md`.

### Fixed (audit - summary of documentation drift after splitting buckets php/frontend)

- **862 rotten links `php/<skill>` / `frontend/<skill>` rewritten** for current buckets by
  `skills.json` (`laravel-*`/`frontend-*`/`php-packages`/`azguard`/`botkit`/`general`) — after the split
  cores `php`/`frontend` on thin buckets hundreds of cross-links in `routing.md`, `boost-compatibility.md`,
  `guide/*`, skill bodies and `snippets/`/`references/` pointed to non-existent paths. Vault name-driven
  (only known skills, word boundaries → without false substitutions), buckets are neighboring directories, so
  relative links are rewritten correctly. SKILL.ru.md were corrected synchronously with SKILL.md,
  ru-source-sha256 re-labeled (`check-translations` clean). **Regression gate** in `validate.sh` (section
  13): rotten `php/<skill>`/`frontend/<skill>` in `skills/`+`docs/` package → error.
- **Counters and hero-links corrected:** root `CLAUDE.md` «20 plugins» → «49»; `docs/index.md`
  hero `/guide/`→`/skiller/guide/` (was 404), «65+ 10 skills bucket-ah» → «195 45 skills».
- **skiller `CLAUDE.md`:** added module `skillset.py` (vendor-channel `sync`/`do_sync`), fixed
  attribution `sync` (was `update.py`/`vendor.py` — real `skillset.py`), CORE-list vendor completed
  to 7 (== `CORE_SKILLS`: added `mcp-advisor`, `verify-claims`).
- **Governance-skills (always-loaded):** `ecosystem-integration` — fixed broken canonical link to
  `onboarding-decision-tree.md` (`../../../packages/maind/docs/guide/`); `release-discipline` — `./scripts/
  validate.sh` (not at root) → per-batch `packages/<package>/scripts/validate.sh`.

### Changed (audit - registry dedup: token-efficient out CORE)

- **`general/performance` (`token-efficient`) moved `general` → `ai`** (`skills/ai/performance/`).
  This Perplexity-environment super-skill (get-zeked, `notify`), duplicate native
  `general/compact-responses` and sitting in the bucket `general` = CORE → was distributed by the plugin to EVERY
  connect-project. `general` must be minimal/cross-stack (skill-taxonomy); environment-specific
  double has no place there. Non-piecewise transfer (provenance `upstream.json` saved, relative path),
  `presets/agent-context.json` redirected to `ai/performance`, registry regenerated
  (`skills.json`/`_index.md`/`graph.md`/`budget.md`).
- _Postponed separately upstream-pass:_ 10 vendored super-skill have `name != directory`
  (`pm-super-skill` vs `pm/product` etc.) and do not link to granular native skills. Edit
  affects upstream-canon + everyone's provenance is neat per-skill pass (and possibly
  separate decision whether these composites are needed super-skill in the registry along with granular ones), and not
  quick summary. `reka-ui-cva` already `requires: [tailwind-conventions]` (audit finding is not relevant).

### Fixed (audit - logic for distributing skills: requires / update / CORE)

- **`sync` now resolves transitive `requires`** (`skillset.resolve_skillset`). Skill-granular
  `include` was silently losing dependencies (64/195 skills are announced): `include: [api-design]` copied
  api-design, but not his `requires: [data-schema]`. Added transitive bypass (parity with
  `vendor.resolve_requires`): `exclude` still beats addiction with warning. Regression -
  `test_skillset.py::{test_sync_pulls_transitive_requires,test_sync_exclude_beats_requires}`.
- **`skiller update` recognizes sync-channel** (`update.update_one`). sync and legacy-vendor write
  ONE `.swissknifeman-manifest.json`, therefore on sync-project `update` went to legacy `do_vendor`
  (bucket-granular from `.swissknife.json`/profile), ignoring skill-granular `.swissknifeman/config.json`.
  Now, if available sync-config `update` re-applies it via `do_sync` (as already doing
  `integrate`). Regression - `test_update.py::test_update_routes_sync_config_to_sync`.
- **CORE-fallback channel-independent** — `MINIMAL_BUCKETS` (set for unrecognized project type) pulled in
  bucket `system` in its entirety, including `system/{shared-memory,cross-project-coordinator}` — exactly duplicates
  hub maind, what CORE-politics drives through `DEFAULT_EXCLUDE`. Now `MINIMAL_BUCKETS == CORE_BUCKETS`
  (general+oss-dev) — fallback is not against policy.
- **Reserved keys `.swissknife.json` are honestly marked** (`config.validate_config`) — `shape`/
  `stacks`/`coordinator_ignore`/`presets` were validated but not read connect/vendor; now
  warn «reserved/has no effect» (like `skills_map`), and not silent. Deleting keys is not
  do (strict validation - would break existing configs); `memory_brain` actually consumed
  (integrate↔harness) and does not touch.

### Fixed (audit - the foundation of skills distribution: common primitives)

- **Leak `SKILL.ru.md` (Russian SSOT) in downstream-projects via `sync`** — canonical
  Claude-channel `skillset.sync_skillset` copied the skill catalog, excluding only
  `upstream.json`/`.claude-plugin`, but NOT `SKILL.*.md`/`evals/` (unlike `vendor.copy_skill`).
  Full Russian source and behavioral tests went to each of the 195 skills of the consumer
  project. ONE introduced `common.SKILL_IGNORE = (upstream.json, .claude-plugin, SKILL.*.md, evals)`
  — `vendor` and `sync` now ignore one list (used to be dubbed and separated). Regression -
  `tests/test_skillset.py::test_sync_excludes_ru_source_and_evals`.
- **Dedup containment-helper** — `connect`/`vendor`/`skillset`/`doctor` duplicated
  `str(p.resolve()).startswith(str(root.resolve()) + os.sep)`. Reduced to `common.is_within`
  (resolve symlink — for prune) and `common.is_within_lexical` (without final resolution symlink —
  for install-gate against traversal via `../` in the skill name). `vendor.copy_skill` now removes
  symlink at destination until `copytree` (otherwise I would write through it to someone else's target).
- **Atomic write JSON** — `vendor.write_manifest` wrote the manifesto raw `write_text` (crash
  left a broken file, breaking `update`/`connect`/`status`); `skillset.write_lock`/`lock.cmd_lock`/
  `topology.save_topology` manually duplicated `tmp+os.replace` without erasure `.tmp`. All translated
  on `core.io.atomic_write_json`. `harness/apply-permissions.sh` writes settings atomically (tmp+`mv -f`)
  and crashes with a Russian error (and not traceback) on the bit input JSON.

### Security (audit - 2 gaps closed: RCE and bypass namespace-memory isolation)

- **maind MCP: server isolation enforcement namespace** (`lib/maind/mcp.py`, `memory.py`). Previously
  `scope = args.get("scope") or default_scope` gave priority to CLIENT: project agent A,
  passing `{"scope":"project:B"}`, read/wrote/deleted private project memory B (and graph
  tools - topology by arbitrary `from`/`project`), although the server is rolled out stammered to
  to your project (`maind mcp --scope project:<id>`). Now the server, pinned to the project,
  limited to OWN project buckets (`recall_scopes`: private + `ns:<his group>` + `global`);
  graph tools cut access to projects that do not share namespace (`namespaces.shares`);
  `forget` confirms ownership of the fact by marker `[[s:<scope>]]` before deletion (memoryId global).
  Hub mode (`default_scope=global`) and explicit `MAIND_MCP_ALLOW_CROSS_SCOPE=1` — without restrictions
  (back-compat/admin). Regression - `tests/test_mcp.py::TestScopeIsolation` (+9).
- **harness review-gate: fixed RCE when opening someone else's repo** (`configs/claude-code/hooks/review-gate/review-gate.sh`).
  Hook on `SubagentStop` (is set globally) performed `check_command` from project-local
  `.claude/review-gate.config.json` via `bash -c` — any third-party repository received
  arbitrary code execution. Now `check_command` is taken ONLY from machine-owned
  `$HOOK_DIR/config.json`; project-local config is executed honestly only with explicit opt-in owner
  machines (`ALLOW_PROJECT_CONFIG=1` in `$HOOK_DIR/env.ini`).
- **harness auto-approve strict: interpreters and awk/sed are no longer auto-approved**
  (`configs/claude-code/hooks/auto-approve/config.json`). `_normalize` cuts out the body in quotes,
  therefore `python -c "<code>"` / `awk 'BEGIN{system(…)}'` is visible to the analyzer only by the command head -
  approve it = approve arbitrary code. `trust_inline_interpreters` → `false` default;
  `awk`/`sed` removed from `allow` (enable inline-interpreters - conscious per-project selection).
  Regression - `harness/tests/test_security_hooks.py` (+5, real hooks via subprocess).

### Added (skiller — eval-skills training + composite-upstream `merge`)

- **`skiller eval <bucket>/<name>`** (`lib/skiller/eval.py`) — behavioral skill testing,
  which was not there (validation was only structural). Format `evals/`: `evals.json` (cases +
  **deterministic** assertions `contains`/`not_contains`/`regex`/`not_regex`/`file_exists`/
  `file_absent`/`min_words`), `pressure.json` (temptation scenarios «skip skill» — TDD for
  documentation), `triggers.json` (response accuracy `description`). Run with-skill vs
  `--baseline` via `claude -p` → `benchmark.json` (pass-rate, tokens/timings mean±stddev, Δ);
  `--static` writes HTML-report; `--scaffold` creates stubs; `--triggers` — description optimization
  (≤150 symbol, editing via `SKILL.ru.md`→EN). Adapted (methodology, not code) from Anthropic
  `skill-creator` + obra/superpowers `writing-skills`. **CI offline:** no `claude` → mild degradation.
- **Gate and cover in `validate.sh`** — strict validation of the entered format `evals/*.json` + summary
  `evals coverage: X/Y` in one line (without per-skill noise). `generate-skill` and root-skill
  `skill-authoring` translated to **eval-first**. `evals/` NOT vendored (`vendor.copy_skill`) and
  excluded from `skill_content_hash`. Seeds: `general/verify-claims`, `general/anti-drift`,
  `quality/code-review`. Unit tests - `tests/test_eval.py` (offline).
- **upstream.json `strategy: merge`** — skill collected from **multiple external sources**:
  `origins[]` with roles (exactly one `base` + ≥1 `supplement`/«suggest», with hint `note`/`suggest`
  added). Sync **manual under agent control**: on the drift of any origin
  `merge.review_pending=true` blocks `validate.sh`/`registry`/release before manual re-merge
  (as gate `fork`), auto-overwrite is prohibited. Validation in `validate.sh`; DX-schemas
  `schema/{evals,upstream}.schema.json`; docks `docs/guide/evals.md` + `upstream-sync.md`.

> Context: review of three external skill-repositories (anthropics/skills, obra/superpowers,
> affaan-m/ECC) — largest registry gap closed (behavioral skill testing) and added
> provenance composite-skills from several sources with manual agent-merge.

### Added (verify-claims — RAG-verification of external facts in review and planning)

- **Skill `general/verify-claims`** (CORE, bilingual RU→EN) — epistemic gate against decisions on
  outdated knowledge. Classifies the statement: **repo/code-grounded** (reading the code - without checking) ·
  **stable general knowledge** (without checking) · **external + staleness-sensitive** (versions/API,
  «still relevant», best practice, market, possibilities of someone else's service/MCP, prices) → **verify via
  RAG**. Ladder of engines (cheap first): **context7** (library docks) → **Perplexity** (native MCP when
  `PERPLEXITY_API_KEY`, otherwise keyless `perplexity-web`) → **WebSearch/WebFetch** → escalation to `research/research`.
  Quote + confidence (high/medium/low). Special clause: when analyzing someone else's audit, external-world verdicts
  before-check **even if audit «full»**. Added to `CORE_SKILLS`.
- **`general/mcp-advisor`**: string `perplexity` in the server map + cross-reference to `verify-claims`
  (are complementary: *what to connect* ↔ *when/how to get a fact*).
- **Catalog harness**: `configs/claude-code/mcp/perplexity.json` (`@perplexity-ai/mcp-server` + env
  `PERPLEXITY_API_KEY`). Package name **verified via RAG** (current official `@perplexity-ai/mcp-server`,
  not legacy `server-perplexity-ask` — exactly the same staleness, what catches `verify-claims`).
- **Planning chains**: `verify-claims` `produces_for: [architecture, tech-stack-selection]` (edge graph) +
  house-style ban «fix external facts from memory - first `verify-claims`» in `architect/architecture`
  and `architect/tech-stack-selection`.

> Context: request - build in checking external facts via RAG (knowledge of the model has a threshold and may be incomplete/
> erroneous) in **audit reviews** and **big planning**. Repo-grounded verdicts (code reading) are safe;
> external facts - verified using a ladder engine. Discipline is fixed by skill and applied in the process.

### Added (skiller — plan review Perplexity: mcp-advisor, github-ops, layers)

- **Skill `general/mcp-advisor`** (CORE, bilingual RU-source→EN-canon) — checklist **selection
  MCP-servers for the project** during onboarding/sinke. Closes the gap: profiles/onboarding is screwed
  MCP static (almost everyone - only `context7`), without suggestions on what to connect. Menu = directory
  harness (context7/playwright/github/fetch/sequential-thinking/filesystem) + hub `maind`; for each -
  when needed/not needed and price (schema in each request + permissions + Node/uvx-dep). Rules: memory/graph
  via `maind` (not generic `memory`-MCP), routine GitHub-review via `gh` CLI (not heavy `github` MCP).
  Added to `CORE_SKILLS`; cross-reference with `context-economy` (selection ↔ cropping).
- **Preset `github-ops`** — scattered bundle GitHub-set: `roles/open-source-maintainer` +
  `oss-dev/{github-flow,gh-review,issue-triage,release-engineering,oss-governance}` + `devops/ci-cd`.
  The only real space from «Stage 3» plan (there were skills, but there was no single preset).
- **Docks**: `routing.md` — section «Architectural layers: what goes where» (4-layer rule-stop on real
  3-batch split skiller/maind/harness, links to package canon); `skiller/docs/guide/upstream-sync.md`
  — cross-link to source directory `references/README.md` (directory diskability from the docks site).

> Context: review `research/swissknifeman_final_plan.md` (external audit Perplexity). Most
> «stages» turned out to be already done (MCP-façade `maind` 11 tools, profiles/presets, upstream-catalog, quality
> code `cde47b8`) or reimagined as a 3-pack split; form-duplicates (`config.engines/packs`, `swiss.*`
> renaming MCP, manual `capability-matrix`, `docs/upstream/`) **rejected** as parallel registries.
> Only non-duplicate slices were taken (this block). Full analysis with favorites -
> `research/swissknifeman_final_plan_review.md`.

### Added (skiller — architecture audit review: init, JSON-schemes, level, doki-true)

- **`skiller init`** — new command: creates `.swissknifeman/config.json` (vendor) from
  project type autodetect + profile, **without** copying skills (does this `sync`).
  Idempotent (the existing config is not overwritten without `--force`), `--dry-run`. Logic -
  general helper `materialize_skillset_config` (removed from `do_sync`, to init and sync not
  were leaving). Registered in `cli.py` + launchers `bin/skiller`/`bin/swissknifeman`.
- **JSON-config schemes** (`schema/swissknife.schema.json`, `schema/swissknifeman-config.schema.json`)
  — DX/IntelliSense via `$schema`. Runtime validation remains manual and **stdlib-only** (without
  pip `jsonschema`); synchronous circuit↔code hold gate `tests/test_schema.py` (is chasing in `validate.sh`)
  and two checks `skiller doctor`. Config validators now pass keys to `_`/`$`.
- **Opt. frontmatter field `level`** (`core|foundation|extension`) — self-documenting layer
  hierarchy; written in `skills.json` (omit-when-empty), enum-gate in `validate.sh`, tally-consumer
  in `skiller registry`, added to preserve-list canon generator and `SKILL_TEMPLATE.md`. Opt-in:
  no skill is marked yet (null churn sha256 from consumers).
- **`content_sha256` — drift hash throughout the skill catalog** (`common.skill_content_hash`,
  is written in `skills.json` next to `sha256`). Closes the hole: incremental `sync` detectil
  drift only by `SKILL.md` and **missed** edits to `snippets/`/`references/`. Now `plan_sync`
  catches them and updates the skill. Ignores - like vendor (`upstream.json`/`SKILL.*.md`/`.claude-plugin`),
  hashed SOURCE (copy differs in ignores). Old locks without `content_sha256` degrade
  correct (drift by `SKILL.md`), field beforepopulated at the next sync **without** recopying.
  The only accepted item from the audit `research/skiller_delivery_modes_and_manifest.md`.
- **Documentation-true**: new canon `docs/guide/skills-architecture.md` («real state»,
  read first - against straw-man) + entry in navigation (standalone + umbrella VitePress).
  Truth-up local skills `package-architecture`/`project-tooling-runbook` (two configs; body
  reads skills Claude Code, not Python). Decision-record in the caps of both research-audit docks
  (were marked «Ready for implementation» — now «reviewed, NOT as is»).

### Rejected (audit review - justified refusals)

- **3-level refactoring of skills** (core/foundation/extension) — rejected: hierarchy/dependencies/
  levels already exist; «take subskills» solved skill-granular vendor; price churn (193 bilingual pairs,
  49 plugins, locks) is disproportionate. The benefit was taken cheaply by the field `level`.
- **Caching subsystem** (`SkillMemoryCache`/disk-cache/commands `cache`) — rejected: no
  caller (skill bodies reads Claude Code, not Python; `load_skill` does not exist). Prompt
  caching y Claude Code automatic. Micro-memoization of the frontmatter pars is also not implemented
  (conflict with convention «without modular globals», gain below perception threshold).

### Added (skiller — bilingual skills: compact EN-canon + full RU-source)

- **193 skills have been converted to a bilingual model.** Local (139): `SKILL.ru.md` — full Russian
  SOURCE (it is ruled by man, SSOT), `SKILL.md` — compact English canon (is generated from RU,
  loads only its agent; Russian doesn't fit into the context). External (54): EN-canon from upstream not
  touched, added `SKILL.ru.md`-help. All 139 EN-canons passed adversarial-fidelity verification
  (no rules/condition/threshold/code/path not lost, nothing added).
- **Savings ~32% tokens** on the bodies of local skills (≈268K→182K current): English at the tokenizer
  Claude is denser than the Cyrillic alphabet. `budget.py` — language-sensitive evaluation (Cyrillic ~2.2 / Latin ~4.0
  chars/tok); map `docs/guide/budget.md` shows the effect.
- Edit stream: editing `SKILL.ru.md` → regenerate `SKILL.md` (`prompts/generate/claude-canon-from-ru.md`)
  → `check-translations.sh --stamp`. Canon coherence marks `<!-- ru-source-sha256 -->`.
- `*.ru.md` are NOT vendored into projects (only goes EN-canon); generation performed by multi-agent Workflow.

### Added (skiller — implementation mattpocock/skills: engineering methodology + chaining)

- **9 imported skills** from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT),
  fold-in to existing buckets (without a new bucket), `strategy: notify`:
  `quality/diagnosing-bugs` (6-phase debugging: feedback-loop before hypotheses, tag `[DEBUG-xxxx]`),
  `quality/tdd-discipline` (red-green-refactor vertical cuts, not horizontal),
  `architect/codebase-design` (deep modules Ousterhout/Feathers: depth/seam/deletion-test;
  collapsed HTML-report from improve-codebase-architecture),
  `architect/domain-modeling` (glossary `CONTEXT.md` + ADR inline, multi-context),
  `general/implement` (chain implement→tdd→review, **user-invoked**),
  `oss-dev/to-issues` (plan→issue vertical slices + fields Affected projects/Environment, **user-invoked**),
  `oss-dev/issue-triage` (triage state machine + role `needs-device-access` for hardware, **user-invoked**),
  `oss-dev/resolving-merge-conflicts`, and central `general/grill-with-docs` (grilling + domain
  model vs external API/RFC-spec, **user-invoked**).
- **Level + activation conditions for each skill** (response to «not folders, but in a chain»): compact
  `description`-router (tier-0 always), lean-body (tier-1 on-trigger), sub-files mattpocock →
  `snippets/` (tier-2 on-demand); side effects (implement/to-issues/issue-triage/grill-with-docs) —
  `disable-model-invocation: true`; `general/git-safety` — `lifecycle: init`. NOT in CORE — opt-in.
- **Built into a chain with edges `requires/produces_for`**: grill-with-docs→{spec-interview,domain-modeling};
  to-issues→github-flow, produces_for→implement; implement→{tdd-discipline,code-review};
  diagnosing-bugs→code-review; codebase-design→{refactoring-plan,architecture};
  domain-modeling→{architecture,api-design,data-schema}; resolving-merge-conflicts→git-commit-rules.
  Plus sections «Related skills» in every body.
- **Distribution via presets** — new `presets/engineering-workflow.json` (end-to-end pipeline) +
  expanded `agent-tasks` (grill-with-docs/implement/to-issues), `code-quality` (tdd-discipline/
  diagnosing-bugs), `system-design` (codebase-design/domain-modeling).
- **Expanded `general/spec-interview`** (our grilling) — links to `grill-with-docs`/`to-issues`/`implement`.
- **git-guardrails → harness, not a skill** (audit amendment): PreToolUse-hook
  `block-dangerous-git.sh` (+`force-with-lease`/`rebase --onto`) in
  `packages/harness/configs/claude-code/hooks/git-guardrails/`, skill wrapper `general/git-safety`.
- **Agents upload new skills via `skills:`**: `issue-triager`←`issue-triage`,
  `sprint-planner`←`to-issues`, `review-gatekeeper`←`diagnosing-bugs`/`tdd-discipline`
  (harness agent-packs `role-maintainer`/`role-tech-lead` → 0.2.0).
- **Provenance**: source registered in
  [references/mattpocock-skills.md](packages/skiller/references/mattpocock-skills.md) (`imported`) +
  per-skill `upstream.json` (sha256/fetched_at, HEAD `5d78bd09`).

### Added (skiller — token budget + diagram map + promty + backlog of translations)

- **Command `skiller budget`** — three-tier context discovery model: **⊕ always**
  (`name`+`description`, resident in each request - persistent «tax»), **↻ on-trigger**
  (body `SKILL.md`), **⌥ on-demand** (snippets). Modes: `--config F.json`, `--compare a,b`,
  `--json`, `--profile/--buckets/--exclude`, `--no-core`, `--write-map`. Module
  [budget.py](packages/skiller/lib/skiller/budget.py) — **single source** token-mathematics
  (reuses `resolve_selection`/`collect_skills`/`resolve_requires`, without duplication
  samples). +9 unit-tests (`tests/test_budget.py`).
- **Token Budget Map** — generated mermaid-page
  [docs/guide/budget.md](packages/skiller/docs/guide/budget.md): node for skill (by buckets),
  heat-color by ⊕ always, edges `requires` = transitive tax, tables for buckets and tops.
  Regenerates `skiller registry` (in-process, after the graph); item in VitePress sidebar.
- **Budget line in `skiller status`** — ⊕ always/↻ bodies project set + top 3 descriptions.
- **Promt library** [prompts/](packages/skiller/prompts/) (audit/review/generate) — templates
  for registry maintenance (what `validate.sh` does not catch: intersections, water content, duplicates).
- **Backlog of translations** — `SKILL.<lang>.md` gitignored (agent only loads `SKILL.md`); checker
  coverings [check-translations.sh](packages/skiller/scripts/check-translations.sh) (`--lang`,
  `--generate-stubs`).
- *From the audit Perplexity — rejected as a duplicate:* `generate-graph.ts` (= existing
  `generate-graph.sh`) and `drift-check.ts` (= `validate.sh`); audit token model fixed
  (body ≠ «always loaded» → three-tier).

### Added (skiller — presets/skill clusters + thin buckets for config-managed per-project sync)

- **Presets layer** — `presets/<name>.json` (`{name, description, extends?, buckets?, include?}`):
  named skill clusters for vendor-samples. Revealed in `resolve_skillset`
  ([skillset.py](packages/skiller/lib/skiller/skillset.py)) BEFORE formula **`(presets ∪ buckets ∪ include) − exclude`**,
  with recursive `extends`. Project config `.swissknifeman/config.json` refers to `presets: [...]`
  (+ `include`/`exclude` overrides) → `skiller sync` → `.claude/skills/` + `skills-lock.json`. Only vendor
  (connect bucket-atomic). Validation in [validate.sh](packages/skiller/scripts/validate.sh) (refs resolve,
  acycle `extends`); +5 unit-tests (`tests/test_skillset.py::TestPresets`). `presets`-key in `SKILLSET_KEYS`/`CONFIG_KEYS`.
- **Thin buckets instead of monolithic `php`** (44→13 core): `php` became a shed core (laravel, structure,
  conventions, DI, database, repositories, patterns, static-analysis), a feature-areas are moved to separate
  bucket plugins - `laravel-testing`, `laravel-filament`, `laravel-livewire`, `laravel-data-layer`,
  `laravel-auth`, `laravel-architecture`, `laravel-extras`. Filament/Livewire more **are not pulled by default**
  (turn on pointwise). `php-packages` — development Laravel-packages (9 skills). `azguard`/`botkit` — separate
  single buckets (for future transfer of the skill inside the package itself).
- **Thin buckets instead of monolithic `frontend`** (35→3 core): core `frontend` (web-design-guidelines,
  document-writer, filepond-upload) + feature-buckets `frontend-{vue,nuxt,tailwind,naive-ui,reka,vite,linting,
  animations,figma,wayfinder,backend}`. Nuxt/Naive-UI/Figma etc. - separate plugins, not by default.
- **19 presets** (end-to-end stacks): php — `laravel-admin`/`laravel-enterprise`/`laravel-inertia`/`laravel-livewire-stack`;
  frontend — `vue-spa`/`figma-to-frontend`; + clusters `architect`/`pm`/`general`/`quality`.
- **Profiles** under line default: `laravel-project` = core + `laravel-testing`/`laravel-auth`/`laravel-data-layer`;
  `node-frontend` = core + `frontend-vue`/`frontend-vite`/`frontend-linting`/`frontend-tailwind`;
  `php-package` += `php-packages`/`laravel-testing`. Feature-buckets (Filament/Livewire/Nuxt/…) — opt-in.
- **buckets.json** +21 bucket; **docs**: new `docs/guide/presets.md`, updated `vendor-mode.md`/`profiles.md`/
  `skill-anatomy.md` + runbook `project-tooling-runbook`. Regeneration `skiller registry` (49 plugins).
- *Rejected (Perplexity, with argumentation):* skiller like PHP-application (`src/*.php`) and `.swissknife.yml`/`.lock`
  from scratch - the mechanism already exists (Python + JSON); merge `laravel-package-*` — this upstream-skills (merge breaks tracking);
  new domain skills (fintech/fiscal) — project-local.

### Added (skiller — `strategy: fork`: support of modified vendor skills)

- **New strategy `upstream.json` — `fork`** (besides `replace`/`notify`): external skill with ours
  edits, which **cannot be auto-updated**. `files[].path` indicates **pristine-mirror**
  (e.g. `references/source.md`), edits live in a thin wrapper `SKILL.md`; on upstream drift
  is set `review_pending: true`. Escalation `replace` (mirror) → `notify` (report) → `fork`
  (edits + baseline + manual transfer + hard gate).
- **`validate.sh`**: enum strategies expanded `fork`; **gate** — `review_pending: true` → ERROR
  (blocks `skiller registry`/release until drift is manually transferred). Verification bool/`last_review`.
- **`update-upstreams.sh`**: thread `fork` — `--check` reports drift (exit 10), `--apply`
  stages fresh upstream in `upstream/<name>.incoming.md` and picks up `review_pending` (mirror and
  `SKILL.md` DO NOT touch); new mode **`--resolve`** — after manual transfer promotes incoming
  in the mirror, updates `sha256`/`fetched_at`/`last_review`, clears the flag (works offline).
- **`ai/ai-agents` translated `notify` → `fork`**: monolith (2722 page in `SKILL.md`) → thin
  navigator wrapper `SKILL.md` (is loaded upon activation) + full upstream in `references/source.md`
  (loaded on demand). Closes both axes: context-economy (lazy-load) and tracking (1 file ↔ 1 url,
  trivial diff transfer). Drift Lock - **only in the registry**; to projects still
  vendor clean copy (`upstream.json` is cut). +1 test (provenance fork via path
  `references/source.md`, fallback `files[0]`); `*.incoming.md` in `.gitignore`. Docks:
  `upstream-sync.md` (section fork), `creating-skills.md`.

### Fixed (skiller — audit trivia)

- **`context-economy`**: cross-reference to skill `pao` converted to standard format
  (`` `pao` (bucket: php) `` instead of non-standard `laravel/pao`).

### Added (skiller — vendor-channel «publish skills in repo» on onboarding)

- **`integrate --skills-channel connect|vendor|skip`** + interactive channel question (TTY). Channel
  `vendor` for Claude-of the project is now routed to **modern `sync`** (`skillset.do_sync`):
  `integrate` materializes `.swissknifeman/config.json` from the project profile and applies `sync` —
  physical. copies of skills in `.claude/skills/` + `skills-lock.json` (`managed`). Closes the case
  **external developers**: project is sent to a team without access to the registry swissknifeman, skills
  go as files in the repo itself (y `connect` marketplace points to the local registry path → y
  other developer's plugins will not connect). Legacy `do_vendor` (`.ai/.cursor`) only remains
  for `--agent cursor|generic`. Channel selection concerns **only skills** — memory/graph/MCP hub not
  are affected. +6 tests (do_sync: config materialization / respect curated / dry-run;
  integrate: vendor→sync, skip, invalid channel).
- **`maind onboard --skills-channel` / `swissknifeman setup --skills-channel`** — channel forwarding to
  `skiller integrate`; `onboard` interactively asks the channel (like the memory mechanism), flag - for
  non-interactive (default `connect`).
- **Canal hygiene in `skiller status`**: warning `DOUBLE CHANNELS`, if one bucket is active
  SIMULTANEOUSLY as a plugin (connect) and vendor (vendor) — skills would be distributed twice. Check
  (`channel_overlap`) lives ONLY in skiller (skill owner) and is accessible from the umbrella via
  `swissknifeman skills status` — is not duplicated across packages. +4 test.
- **Hygiene tests `skills-lock.json`** (managed vs alien): entry added to lock manually
  (your skill / another hub, `managed!=true`), is worried `sync` and is not deleted even if it is empty
  config; manual cleaning managed-entries when the folder is live → without `--force` path is considered foreign
  (pass), with `--force` skill is purely re-adopted (one managed-record, without tails/takes).
  +3 test. Fixes an invariant «we synchronize only our (`managed: true`)».

### Security / Fixed (maind — portability of generated hooks, no path leakage)

- **Hook scripts maind no longer binds the absolute path to the launcher.** Templates
  `templates/health/*.sh` (memory-digest · session-start · feature-log) resolve `maind` in runtime
  (`env MAIND_BIN → command -v maind`), rather than substitute machine-specific
  `<…>/packages/maind/bin/maind` via `_maind_bin` (deleted). Generated artifact is now the same
  on any machine; launcher not found → quiet no-op (as with a demon who is light). Configured via
  env `MAIND_BIN` (can be found from `.claude/*.env.ini`). Back-compatible: already rolled out hooks work,
  `command -v maind` resolves the same `~/.local/bin/maind`. +3 test (no abs-paths, yes env→PATH).
- **`.claude/maind-*.sh` (+ `.maind-feature-log.last`, `scheduled_tasks.lock`) in `.gitignore`** —
  generated per-project hooks/runtimestate are not getting into the repo like `.mcp.json`. Closes the leak
  author's absolute path when `git add .claude/`.
- **Audit MCP** (no changes - already clean): presets `packages/harness/configs/claude-code/mcp/*.json`
  portable (`npx`/`uvx`/`http`, without abs-paths); `.mcp.json` (with abs-by maind) already gitignored,
  template - `.mcp.json.example` with `{{REPO_ROOT}}`, generates the real file `maind` for deployment.

### Fixed (third audit skiller — hardening silent failures)

- **`_registry_index` no longer loses skills silently**: entry in `skills.json` without `name`/`path` and double
  short names between buckets are now logged `warn` — formerly mute `continue`/`setdefault` lost skill
  from sin without a trace (by full path `bucket/rel` double is available, by short name - first). +tests.
- **subprocess in harness with timeout** (`common.apply_permissions`, `integrate._run_harness`): `timeout=30`
  + stderr in `warn` — frozen harness (NFS/network) no longer freezes `skiller sync` silently; stdout abandoned
  alive (progress harness visible). Complements returncode-check from the previous audit.
- **manifest is atomic and traceable** (`skillset._write_manifest`): entry via `core.io.atomic_write_json`
  (tmp+`os.replace` instead raw `write_text` — no half-written file on crash) + `installed_at` via
  `now_iso()` (time, not naked date) + `version` schemas. +test.
- **frontmatter reads YAML-block scalars** (`common.parse_frontmatter`): `description: |`/`>` (multiline)
  no longer get lost in silence - stdlib-parsing without `pyyaml`, with protection against values starting with `|`/`>`. +tests.
- **`skills_map` is not silent** (`config.validate_config`): reserved but unimplemented key
  is marked `warn` instead of silently ignoring.

> Rejected as false (checked against source): path-traversal in `contained()` — code already adds
> `+ os.sep`, example `/skills_extra` does not pass against `/skills/`; «cropped `parse_inline_list`» — function
> integer; «enter profiles as first-class» — 8 profiles + flag `--profile` already exists; recursive `_dir_sha256`
> — deliberately mirrors per-file registry hash (recursion will go out of sync lock with `skills.json`); `import yaml` —
> violates stdlib-only, replaced stdlib-handler.

### Fixed (second audit skiller — real bugs)

- **`integrate` no longer suppresses errors harness**: `_run_harness` checks returncode and `warn`-it when
  non-zero - previously the wizard silently reported «ready», even if the block was not applied. Graceful
  degradation saved (wizard does not crash).
- **frontmatter resistant to BOM** (`common.parse_frontmatter`): read `SKILL.md` via `utf-8-sig` —
  file with BOM is no longer silently ignored. +test.
- **`projects.json` without duplicates**: `upsert_project`/`db_records` normalize the path through `Path.resolve()`
  (used to be different repr of one directory - `./`, `..`, symlink - duplicates were generated). +test.
- **`boost.json::skills` is sorted entirely** (`sorted(existing + added)`, not only `added`) —
  deterministic order.

> Rejected as false/over-engineering for Linux-only single-user (with justification in plan): «double-nesting
> `extraKnownMarketplaces`» — is a valid schema Claude Code (confirmed by real configs);
> frontmatter «cuts into `:`» (there `split(":",1)`); TOCTOU/atomicity `copy_skill`; Windows-paths; mmap/
> read-parts of small files; rotation `.bak`; `deque` instead `pop(0)`.

### Security / Fixed (repository audit - umbrella, core, CI)

- **`.mcp.json` removed from under git** (`git rm --cached` + `.gitignore`): machine-specific file
  with absolute paths to `maind` (author path leak + broke the clone from others). Template -
  `.mcp.json.example` (placeholder `{{REPO_ROOT}}`); generates the real file `maind` (sync/deploy).
- **`core.atomic_write_text`**: on write error/`os.replace` cleans up the orphaned `.tmp`
  (`try/except → unlink`) — otherwise garbage accumulated in long-lived processes (e.g. `No space left`). +test.
- **`bin/swissknifeman doctor`**: no longer crashes on the first missing launcher
  (`need()` beat `exit 1`) — fan-out for all three packages with aggregation of the final exit-code.
- **`install.sh`**: collects failed package installations and completes `exit 1` with list - earlier
  was typing «Done» and returned 0 even if the packages were not installed.
- **`scanner-pr.yml`**: branch name is taken from the repository (`git rev-parse --abbrev-ref HEAD`), and not from
  duplicated formula `$(date +%Y%m%d)` (race at the border of the day); removed `|| true` with `git push`
  (real crash push is no longer masked in front of `gh pr create`).
- **`core/env.py`**: `BaseEnv.home` default_factory calling `Path.home()` when creating (not modular
  snapshot) — spoofed `$HOME` is picked up in tests. Global `HOME` saved (public API). +test.

### Changed (documentation and CI — audit)

- **README**: package added `harness` (table + CLI) and root router `swissknifeman`/`setup`;
  removed obsolete phrase «there is no single wrapper console».
- **`CONTRIBUTING.md`** (root) — new: layout, dev-installation (stdlib-only/without pip, IDE
  extraPaths instead pip), tests/validation, conventions, release discipline.
- **CI `test.yml`**: matrix Python extended 3.9–3.12 → 3.9–3.13.
- **`MERGE-PLAN.md`** deleted (working artifact of the merge process, no value to the user).

### Added / Tooling (follow-up audit - improved options)

- **`pyrightconfig.json`**: Pylance/pyright resolve `from core import …` and cross-batch imports
  out of the box (`extraPaths`: root `.` + `packages/*/lib`, `typeCheckingMode: off`) — IDE-DX without pip,
  stdlib-only intact. PyCharm — Sources Root (see `CONTRIBUTING.md`).
- **`swissknifeman --version` / `-V`**: monorepo version from `git describe` (fallback «dev»). At the same time
  removed dangling `version` from the router - it delegated to `skiller version`, which does not exist.
- **Linter ruff in CI** (job `lint`): `pipx run ruff==0.15.19 check` — ephemeral, ruff NOT a dependency
  repo; config `ruff.toml`, set `F,B`, `target-version=py39` (B905 does not conflict with 3.9). One-time
  cleanup: 6 unused imports, 8 empty f-lines, 9 unused loop-vars, 1 broad-except in the test.
- **Per-project `code_language(s)`** (maind/codegraph): override code-graph language (str|list) on top
  `language_by_type` — mixed repo (python-code + TS-docks at `type:node-package`) graph­is correct
  without editing general constants; swissknifeman → `python`. `render_project_yaml` renders the list as well
  (multi-language). +tests.

### Added (harness — memory mode `maind`)

- **Memory hook has received a mode `MODE=maind`** (`hooks/memory/modes/maind.sh`): delegates
  `remember`/`recall` in `maind memory` (demon :4111 + insulation according to scope on the side maind).
  brain is ignored, scope taken from the project (`CLAUDE_PROJECT_DIR` → `match_cwd`). Repairs
  split «hook writes to files `core`, MCP reads empty scope demon»: now both paths go
  in one side. Recommended for applied projects; global default for now `federation`.

### Changed (session-observer 0.3.0 — auto-enable logger)

- **`/observe on` is now a complete checklist**, which Claude performs automatically:
  installing the hook globally → preset wiring `observer` to the project → `ENABLED=true`
  → gitignore `.claude/observer/` → reminder about session restart. Previously skill
  meant only `ENABLED=true`, which is not enough to activate the logger.
  Added `/observe off`.

### Docs (multi-provider distribution - dev-plan)

- **`skiller/docs/multi-provider-distribution.md`** — dev-plan: steal the distribution
  local `.ai/` content (CLAUDE.md/AGENTS.md/Cursor) from Laravel Boost in skiller
  (Boost → only MCP). Fixes a gap (`vendor.py`/`skillset.py` resolve the registry, not
  local `.ai/`), target design and reference-pilot `sibintek-insiders`. Cross-references
  from `boost-compatibility.md` and `index.md`; item in the sidebar VitePress.

### Added (Observer capture-layer - plan agent-skill-binding, Stage D)

- **`harness` observer-hook** (PreToolUse/PostToolUse/Stop), EXPERIMENTAL,
  per-project (`.claude/observer.env.ini` → `ENABLED`, default `false`): writes
  compact project-local `.claude/observer/runtime.jsonl` + alert `LOOP`
  (3+ errors in a row), archives to `Stop`. **Never blocks** (observer,
  not a gate). Wiring - opt-in preset `settings.observer.json` (`harness hooks
  --preset observer`), not global. Analysis - skill `system/session-observer`.
- **`system/session-observer` 0.2.0** — added `runtime.jsonl`/`archive` in
  data sources + how to enable capture-layer.

### Added (deterministic binding of skills to agents)

- **Field `skills:` in frontmatter bucket agents** (`skills/<bucket>/agents/*.md`) —
  native preload Claude Code (v2.0.43+): full content of the listed skills
  is injected into the subagent at the start, without hope of model-invocation. Linked
  `php/laravel-implementer`, `laravel-reviewer`, `laravel-test-writer`. Closes
  root of failure «agent ignored skill» (6/7 missed `repositories`).
- **Validation (`scripts/validate.sh`, 10c):** each `skills:`-agent element must
  resolve to real registry skill (`bucket:name`); unnamespaced — warning.
- **`php/laravel-implementer`:** prose «FIRST STEP - load via Skill» replaced by
  declarative field `skills:`; strict rules abandoned L4-insurance.

### Added (duress gate + Observer — plan agent-skill-binding, Stage B–D)

- **`harness` review-gate** — deterministic gate architecture on `SubagentStop`
  (`off|warn|strict`, default `warn`): runs the project-configured check
  (`check_command`), `warn` → hint in `additionalContext`, `strict` → block
  subagent. Without checking - no-op. L5-line under `skills:`-preload. (Stage B)
- **`system/session-observer`** (skiller, EXPERIMENTAL, per-project toggle
  `.claude/observer.env.ini`) — post-facto session analysis JSONL-logs with
  3-axial weakness analytics: **agents** (skill-skip/drift/loops), **skills**
  (gap/thin/dead/correction-after-load), **settings** (hooks/rights). Finds →
  learnings via memory-hook, human promotion; closed cycle of self-repair.
  Snippet `analyze-session.md` (jq/grep-recipes). Read-only by code, not live. (Stage C–D)

### Changed (validation: strict frontmatter + broken links)

- **`validate.sh` tightened** (section 1a) — was previously only checked *availability*
  required fields; now:
  - `risk` ∈ {read, draft, write, external}; `adapters` ⊆ {claude, cursor, fable};
  - `version` — semver (`\d+.\d+.\d+`); frontmatter `bucket` == bucket directory (for local);
  - declared in frontmatter `snippets:` must exist on disk;
  - **intra-skill links** `snippets/…` / `references/…` in the body SKILL.md are required
    resolve (broken link → error).
- Intentionally NOT checking: equality frontmatter `snippets:` ↔ `index.json` (accepted
  convention - index.json is self-sufficient, frontmatter-list optional; 34 skills),
  and general `../`/`.agents`-links (consumer project layout upstream/imported —
  false positives). All new checks result in 0 violations on the current registry.

### Changed (core: deduplication + protected subprocess)

- **`parse_flags`/`parse_args` are summarized in `core/cli.py`** — before `parse_flags`
  was duplicated in skiller and harness byte-to-byte, `parse_args` (superset with
  positional) lived in maind. Now one source of truth, packages are re-exported from
  their `common.py` (imports `from .common import parse_flags|parse_args` untouched).
- **`core.cli.run_cmd`** — protected subprocess launch (argv-list, without shell):
  `FileNotFoundError`/`TimeoutExpired`/non-zero code → clean `die` instead
  traceback. Applied to `registry`/`hub` (calls `generate-*.sh` with `check=True`
  no longer crash with a traceback).
- **`core.io.safe_load_json`** — single graceful-reader JSON (broken/missing →
  default, opt. `on_error`). For a database with a backup of a broken file, the domain one remains
  `maind.common.load_json_db`.
- **Split `maind/common.py`**: HTTP-client (`http_get_json`/`http_post_json`/`ping`)
  → `maind/http.py`, managed markdown-block (`managed_block`/`upsert_block`/
  `content_hash`) → `maind/blocks.py`. Re-export from `common.py` — imports
  `from .common import ...` untouched (non-breaking).
- Audit subprocess-calls: the rest are already protected (`shutil.which`-guards,
  `try/except OSError`, health-poll memory daemon with early exit detection) —
  not touched (audit recommendation about `shlex.quote` turned out to be false: argv-lists
  not injectable by shell).
- **Tests:** core 12→28 (parse_flags/parse_args/run_cmd/safe_load_json), harness
  14→28 (new coating `doctor`/`settings`/`cli`-dispatcher).

### Added (naming discipline skills)

- **`general/naming-conventions`** (bucket `general` — CORE-connect, is automatically distributed to every
  project) — language-agnostic rules: name reveals intent, fighting noise words
  (`Manager`/`Helper`/`data`/`process`) and a combinatorial explosion of methods (`findByX…OrFail`/
  `…OrNull`). Snippet `naming-gallery.md` (bad → good).
- **`php/naming-conventions`** (bucket `php`) — Laravel-specifics: naming Action/Repository/
  DTO/VO/Enum/Event/Job, tables/columns, anti-pattern analysis `findByCodeOrFail`-explosion
  (→ route binding / model scopes by intent / criterion / one canonical `findByIdOrFail`).
  Snippets `naming-antipatterns.php`, `repository-method-naming.php`. Cross references in
  `repositories`, `code-style-spatie`, `named-arguments`; checklist updated `repositories`
  (the only canonical one lookup, do not produce method-on-field).
- Name `naming-conventions` intentionally lives in two buckets (`general` + `php`): legal under
  plugin-namespaces (connect), in vendor-mode flat-names are separated by the bucket prefix.

### Changed

- **Bucket `blender` is split into two plugins:** `blender` (universal bpy+MCP —
  `version-gotchas`, `mcp-blender`) and `blender-modeling` (parametric CAD under
  FDM/SLA — `parametric-config`, `threading`, `model-rules`, `config-conventions`,
  `scene-conventions`, `build-loop`). Previously, one bucket mixed a universal
  Blender, methodology CAD and private workflow project DiaBox; diabox-specific
  (layer C) was cut from the plugin. The names of parts in skills are anonymized
  (`lens/glass/rocket → part/insert/model`). `blender-modeling` depends on `blender`
  (`mcp-blender` from B does not depend); consumers of model skills connect both plugins.

### Added (agent-framework — agent-practitioner framework + continuous-audit)

- **Agent framework documentation** (`docs/skiller/agent-framework/`): review,
  `framework-overview` (current state - audit input), `decisions-ledger`
  (accepted/rejected + verified facts Claude Code), `roles`,
  `skills-index-and-hub`, `post-integration-checklist`. Stand: **data + skill,
  not a generator engine**.
- **Reused audit-promt** `docs/skiller/workflows/framework-audit.md` —
  periodic revision of the frame through Perplexity (input: overview + ledger; output:
  strict delta tables); self-anchoring loop, does not over-offer the finished one.
- **Audit archive** `docs/skiller/audits/` (raw verbatim + triage of two runs
  2026-06-23: universal-framework, agent-teams+ponytail) + ledger
  `references/framework-audits.md`. Sidebar updated (standalone + unit).

### Changed (hub — visibility of agents and skills, Phase 1)

- **`generate-hub.sh`**: a slice has been added to the hub **«Project Agents»** (table from
  `.claude/agents/*.md`: role → purpose → preloaded `skills:`) — roles and their
  skills are now visible to the orchestrator. Every name in `skills:` is checked against the registry;
  unknown is marked `⚠` (preload silently no-op) + WARNING in stderr. Added
  **freshness-stamp** `<!-- swissknifeman:registry sha=… skills=N -->` for verification
  drift «registry has changed - the hub has not been regenerated» (doctor — Phase 5). Block list parsing
  `skills:` — inline in script; general helper in common.py will come with a validator (Phase 3).

### Added (agent-packs — versionable pack-system, Phase 2)

- **Skill `system/agent-packs`** — playbook installation and version upgrade of packs in
  consumer project: stack detection → interview → render+copy → lock; upgrade by
  CHANGELOG-delta with 3-way reasoning via sha256 in lock (without diff-engine). Stand:
  agent-driven, is not a generator engine.
- **Pack `backend-laravel` v0.1.0** (`harness/configs/claude-code/agent-packs/`):
  agents slice-builder/test-writer/reviewer + workflow dev-loop + review-gate hook +
  settings-fragment + guideline; generalized by placeholders (`{{PACK_PREFIX}}`,
  `{{PHP_RUNNER}}`, `{{TEST_RUNNER_CMD}}`, `{{TEST_DB}}`, `{{CHECK_CMD}}`,
  `{{PROJECT_DIR}}`). `pack.json` (manifest) + per-pack `CHANGELOG.md` + README pack.
- **Lock-diagram** `.claude/agent-pack.lock.json` (version + interview answers + per-file
  `base_sha256` rendered) — base upgrade without diff-engine.

### Added (Phase 3 - roles, path-scoped rules, ponytail-discipline)

- **Role `spec-writer`** (opt.) in the pack `backend-laravel` — writes `docs/specs/<feature>.md`
  (tech-spec) for large features, NOT a global gate. Path-scoped `rules/{api-controllers,
  migrations,tests}.md` — native auto-loading `.claude/rules/` by paths; thin
  triggers, refer to skills (without duplicate text).
- **ponytail-discipline is imbibed in `quality/code-simplifier`** (0.2.0→0.3.0): ladder
  YAGNI to code (7 steps) + delete-list format (tags `delete:`/`stdlib:`/`native:`/
  `yagni:`/`shrink:`). External plugin ponytail DO NOT connect (conflict with boost).
  Reviewer-pack role refers to over-engineering-pass.
- **`.swissknife.json` diagram** (`CONFIG_KEYS`): `shape`/`stacks`/`skills_map` — data
  profile for versatility back/front/fullstack (not an engine).
- Name matching `skills:` is already covered for agents hub-check (Phase 1) — separate
  command `validate-agents` was not needed.

### Added (Phase 5 - doctor freshness-drift)

- **`skiller doctor`** checks the stamp `swissknifeman:registry sha=…` in everyone's hub
  registered project with current sha registry → flags outdated hubs («registry
  has changed - the hub has not been regenerated»). Projects without a stamp (old hub) are skipped.
  Closes continuous-audit drift detection loop.

### Added (Phase 6 - Agent Teams, opt.)

- **Preset `settings.agent-teams.json`** (harness) — opt-in enable experimental
  Agent Teams: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + `teammateMode` (merge-only,
  coexists with auto-approve/review-gate). Prerequisite: Claude Code ≥2.1.178; config
  forward compatible.
- **Doc `agent-framework/agent-teams`** — when to take Teams vs subagents, spawn-templates
  (full-stack feature, parallel debug), module-boundaries (path zones for roles, WITHOUT
  file-lock), opt. quality-gate hooks `TeammateIdle`/`TaskCompleted` (reused
  review-gate). Frame roles are suitable as teammates. Sidebar updated.

## [0.4.0] - 2026-06-22

> **Umbrella single version of monorepo.** Accumulated from `v0.3.0`: package allocation
> `harness` (environment Claude Code), root control layer `swissknifeman`,
> documents by package + umbrella aggregate, granular environment orchestration and
> standalone-building package docks. Tag `vX.Y.Z` — single marker for the entire repository;
> plugin versions Claude Code resolve to git SHA and do not depend on the tag, per-package
> `plugin.json` (harness 0.1.0 · maind 0.2.1 · skm 0.3.0) — are informative.

### Added (Phase 3 - granular orchestration of the environment)

- **Capability `env:mcp` / `env:hooks`** in `maind/orchestrate.py` next to `env:apply` —
  spot rolling MCP-servers / hooks via package `harness` (`maind run <project>
  env:mcp|env:hooks`, router `swissknifeman env mcp|hooks` — full passthrough in
  harness). Previously, the environment was configured only in one piece (`skiller integrate`
  or `env:apply` for permissions); now «umbrella = unified management» covers and
  MCP/hooks granularly. Whitelist `CAPABILITIES` expanded, tests orchestrate added
  (sibling=harness, subcommand, `{path}`-substitution).

### Changed (Phase 3 - standalone-building package docks)

- **Docks skiller/harness are collected and standalone, and in the unit** (as he already knows
  maind). Each package has its own `docs/.vitepress/config.mts` (base `/skiller/`,
  `/harness/`); umbrella `scripts/docs-sync.sh` still discards per-package
  `.vitepress` and assembles a single website. Internal doc links translated to
  **relative** (`./`, `../`, without `/skiller/`·`/harness/`-prefix) — one
  source is valid in both assemblies; cross-packet links skiller→harness/`/routing`
  are resolved only in the unit and in standalone are marked `ignoreDeadLinks`. `harness`
  received `package.json` (docs-scripts), skiller — `docs:standalone:*`. Checked:
  unit + both standalone-sites are assembled without dead links.

### Changed (docs: maind merged into a single site)

- **maind-docks entered the umbrella VitePress** — `scripts/docs-sync.sh` now
  aggregates and `packages/maind/docs`; in the menu «Memory and graph» leads inside the site
  (`/maind/…`), not out. Internal links maind-docks translated from absolute
  (base `/maind/`) on **relative** — the package is assembled and standalone (yours
  `.vitepress`), and in the unit (general base `/swissknifeman/`). Single site green
  (`vitepress build`, without dead links); standalone-assembly maind is also green.

### Added (root control layer `swissknifeman`)

- **`bin/swissknifeman`** — thin router + setup-facade above three packages (umbrella =
  unified management, packages = capabilities): `swissknifeman skills|env|maind …` →
  skiller/harness/maind; `swissknifeman setup <project>` → `maind onboard` (full
  onboarding: skills+environment+memory+graph); `swissknifeman doctor` → fan-out three.
  Does not implement logic - delegates it; one onboarding chain (`maind/onboard.py`).
- **Back-compat alias**: historical `swissknifeman <cmd>` (connect/vendor/integrate/
  update/sync/lock/status/list/registry/topology/validate/version) router proxies to
  `skiller` — onboarded projects and habits do not break.
- **Ownership of the alias has passed to the umbrella**: `swissknifeman`→`bin/swissknifeman` puts
  umbrella `install.sh` AFTER packages; from `packages/skiller/install.sh` installation
  alias removed (otherwise re-run skiller install would overwrite router). Standalone-skiller
  without umbrella - only `skiller` (no alias).
- **maind**: capability `env:apply` (sibling `harness`) — direct application of the environment
  (`maind run <p> env:apply`, router `swissknifeman env`); `onboard --skip-skills` now
  still configures the environment via harness (before it only went inside
  `skiller integrate`).

### Added (package `harness` — environment settings Claude Code)

- **New package `packages/harness`** (CLI `harness`): Harness settings Claude Code —
  presets permissions, modes auto-approve/bypass, MCP-servers, hooks (memory/notify/log).
  Detached from `skiller`, because it does not relate to skill management. `git mv`
  `configs/claude-code/` and `scripts/apply-permissions.sh` from skiller → harness (history
  saved). Commands: `harness permissions|mcp|hooks|doctor`. Package stateless
  (writes in `.claude/` purposes and `~/.claude/hooks/`); umbrella `install.sh` puts
  `skiller · harness · maind`.
- **skiller delegates the environment to harness via subprocess** (like maind → skiller):
  `apply_permissions` and env-blocks `integrate` (permissions/MCP/auto-approve/memory)
  name `harness …`; launcher resolution - `SKM_HARNESS_BIN` →
  `<monorepo>/packages/harness/bin/harness`. Signature `apply_permissions` has not changed -
  `connect`/`vendor` were not touched; harness not installed → graceful skip (as before with
  missing script). Selection Policy MCP (`_default_mcp`/dev-gate) remained in integrate.
- **marketplace: provenance field `package`** for each plugin entry (`skiller`/`harness`/
  `maind`) — `skiller registry` is entered automatically; harness is picked up as
  adjacent packet (plugin `harness@swissknifeman`, commands only `/harness:*`). Names
  plugins and name marketplace NOT changed (back-compat: `<plugin>@swissknifeman`).
- **PR-template** rewritten for monorepo (affected packages skiller/harness/maind/core,
  per-package validate, regenerate-marketplace, docs). Hooks share memory state with skiller
  (`~/.swissknifeman/`) — paths in installed hooks did not change.

### Changed (naming model and topology MCP)

- **Package `packages/swissknifeman` → `packages/skiller`** (CLI `skiller`). Repo/umbrella remains
  `swissknifeman` (= container-«Swiss knife»); package name is now explicitly about SKILLS management
  and does not get confused with the repository. `git mv` directory + `lib/swissknifeman`→`lib/skiller` (imports
  package relative - only changed absolute-imports into `tests/`) + `bin/swissknifeman`→
  `bin/skiller` (`python3 -m skiller`). `install.sh` puts `skiller` **and back-compat alias
  `swissknifeman`** in PATH — docks/habit/onboarded projects don't break. **NOT changed**
  (umbrella brand): name marketplace `swissknifeman`, state-directory `~/.swissknifeman/`,
  `.swissknifeman-manifest.json`, `.swissknife.json`, repo-URL; `skm`-plugin and `/skm:*`.
  `orchestrate.py` (maind): path sibling-launcher → `packages/skiller/bin/skiller`.
- **Plugin `maind` → commands only (`/maind:*`), without MCP-server.** Field cleared `mcpServers`
  from `plugin.json`, deleted `packages/maind/.mcp.json` (server `maind-hub --scope global`). Previously
  user-global pulled the plugin `maind-hub` in EVERY session on top per-project server `maind` — two
  identical `maind`-lines in `/mcp` with different scope (miss «write to global instead project»).
  Now MCP-hub tools only gives per-project server `maind` from `.mcp.json` project;
  graph/`projects_*`/`links` scope-are independent, ecosystem-fact is written explicit `scope:"global"`.
- **maind MCP: defaultscope from cwd, not deaf `global`.** When starting without `--scope`/`MAIND_SCOPE`
  server defines `project:<id>` according to the current directory (resolver shared with `health --cwd`), falling
  in `global` only outside of a known project - argless-the server writes to its project's bucket.
- **Dedup plugin inclusion in `~/.claude/settings.json`** (user-config): taken
  `maind@academici` (+ stale marketplace `academici`, indicating pre-monorepo standalone-clone);
  left single `maind@swissknifeman`.
- **Solution: maind remains united** (memory+graph connected namespace-model; memory `agentmemory`
  and graphify are already separate MCP-servers - nothing to split). Committed to CLAUDE.md.

### Added

- **Practice audit round-2 + 4 deltas of the skill registry.** Continued
  `docs/research/practices-audit-2026-06.md` — new doc `practices-audit-2026-06-r2.md`
  (map covered/partially/gap/rejected + backlog, Dart postponed as 1 project). Authorized by:
  - **NEW `php/enum-state-machine`** — domain status transition graph from a single source
    (`transitionDefinitions()` on enum) + runtime registry (`allowedFrom`/`canTransition`) +
    execution of transition to Action under `DB::transaction()` with event `ShouldDispatchAfterCommit`.
    Gap: `enum-attributes` excludes state-machine, `ticket-workflow` is project specific.
  - **EXTEND `devops/ci-cd` 0.3.0 → 0.4.0** — coverage-gate separate CI-job (GitHub Actions
    + GitLab `.php-base`/`php-coverage`); parser/config reused from `php/laravel-testing`,
    are not duplicated. Snippet `github-actions-coverage-gate.yml`.
  - **EXTEND `quality/test-strategy` 0.1.0 → 0.2.0** — composition of named test suites
    (Arch/Unit/Feature/Context) + architectural tests Pest Arch. Snippets `pest-arch-test.php`,
    `phpunit-testsuites.xml`.
  - **EXTEND `php/spatie-settings` 0.1.0 → 0.2.0** — pattern «runtime-infraconfig (websocket/
    Reverb) from the admin panel → to front public DTO», secret boundary.

### Changed

- **Node config: `.maind.json` → `config.json` at the root of the monorepo (general).** Config moved
  from the package to the root of the monorepo and renamed (template - `config.example.json`). Resolver
  `Env.default_config` looking for `config.json` up the tree (to the directory with `packages/`), with
  backwards compatible on legacy `.maind.json`. Added a lightweight wrapper `Config`
  (subclass dict: `Config.load(env)`/`.save(env)`/`.projects`/`.project(id)` — single point
  config logic; old access `cfg["projects"]` saved). `config.json` — gitignored,
  `0600`. Resolve brain in orchestration made consistent with sync (via
  `integrations.brain.path` → vault → default `~/Vaults/Brain`, normalization to directory) —
  `maind run brain:*` works without project entry brain. Documentation and messages updated.

- **Plugin maind 0.2.0 → 0.2.1.** Bump version to Claude Code recached the plugin from
  with fresh code (corrected `.mcp.json` → `maind` from PATH, `from core`); cache as before
  version was not rebuilt. `package.json` is synchronized.

### Removed

- **Removed wrapper console `bin/academici`.** Umbrella router `academici maind/skm <cmd>`
  removed - two independent ones remain CLI in PATH (`swissknifeman`, `maind`). Umbrella
  `install.sh` now only delegates installation to batches `install.sh`; CLAUDE.md/README
  describe two CLI without wrapper. (Ecosystem name «academici» as brand saved.)

### Changed

- **General core: `academici_core` → package `core`.** Word removed `academici` from paths/names.
  Catalog `core/` himself became python-package (`core/__init__.py`, `core/env.py`, …); import
  `from core import ...`. PYTHONPATH now points to the root of the monorepo (where is `core/`),
  and not on itself `core/` — updated launchers, `test.sh`, `validate.sh` of both packages and
  real-spawn test maind (`CORE_DIR` → `MONOREPO_ROOT`).

### Fixed

- **Valid format `plugin.json` to install from marketplace.** Current Claude Code
  tightened the scheme - the old format was not installed (`commands: Invalid input,
  mcpServers: Invalid input`): `commands` is now an array of paths (`["./commands"]`),
  `mcpServers` — path with `./` (`"./.mcp.json"`). Broken YAML-frontmatter commands (`description`
  with colon `academici: …` was parsed as a nested key) is wrapped in quotes. Both affected
  command plugin (maind, skm) — pass `claude plugin validate`. Test `test_plugin.py`
  catches these defects before installation.

### Changed

- **Monorepo academici: verification + bulk re-deploy consumers (stage 7).** MCP-configs
  projects have been redirected to the new hub path: `maind deploy` ran across 15 registry projects -
  14 updated (corex/azguard/edufy/memster/vintera/… → `packages/swissknifeman/packages/maind/`),
  1 missing (agelto: pre-existing broken `.cursor/mcp.json` with double JSON — do not touch).
  `swissknifeman update --all` updated consumer skills. Check `maind health` on the project:
  status `connected`. Stage 4 tails completed: test `test_plugin.py` and `validate.sh` maind
  no longer require their own marketplace.json package (it's in the root of the repo).

### Added

- **Monorepo academici: umbrella navigation (stage 6).** Root `CLAUDE.md` (map
  monorepo: packages, console, core, marketplace) and root `README.md` umbrella. README
  swissknifeman moved to `packages/swissknifeman/README.md`. `docs:*`-scripts
  swissknifeman target root `docs/` (`../../docs`). docs/ packages and two VitePress
  left in place (full site merger is a separate task).

- **Monorepo academici: single console `bin/academici` + umbrella `install.sh` (stage 5).**
  `academici` — thin bash-router: `academici maind <cmd>` / `academici skm <cmd>` →
  package sub-binary; unique commands are auto-routed without a prefix; conflicting names
  (`status`/`doctor`) give a summary of both packages, `sync` requires a domain. Sub-binaries
  `maind`/`swissknifeman` remain independent (do not break `.mcp.json` and muscle memory).
  Umbrella `install.sh` puts `academici` and delegates the installation of batch CLI them
  own `install.sh` (with batch post configuration). All three symlinks point to the monorepo.

### Changed

- **Monorepo academici: single marketplace + plugin maind under the umbrella (stage 4).** Root
  `.claude-plugin/marketplace.json` now declares 19 plugins - 18 swissknifeman
  (buckets + generate-skill + skm) and `maind` (`source: ./packages/maind`). Generator
  `registry.py` scans neighboring packets `packages/<name>/.claude-plugin/plugin.json`
  (the source of truth is their manifesto) and adds them to marketplace; `validate.sh` takes into account
  sibling-plugins in match-check. Own `packages/maind/.claude-plugin/marketplace.json`
  deleted (its role is taken by the root). Plugin maind (`commands/` + `.mcp.json` with
  `${CLAUDE_PLUGIN_ROOT}`) is transferred without changes. Cache migration Claude Code
  (`maind@maind` → `maind@swissknifeman`) — manually in the panel `/plugin`.

- **Monorepo academici: general `core/academici_core` (stage 3).** Verbatim takes,
  historically copied between swissknifeman/maind/brain byte-to-byte, placed in
  general stdlib-only package: `die/warn/now_iso/confirm` (`term`), `sanitize` (`text`),
  basic `BaseEnv` (core root/cmd/home + `__post_init__`, `env`). `Env` of each package
  now inherits `BaseEnv` and adds only its path-property. Connection - via
  PYTHONPATH (without pip): launchers, `test.sh`, `validate.sh` add `<repo>/core`
  (optional - fallback on standalone-layout). `parse_args`/`parse_flags`, atomic
  JSON, HTTP, frontmatter, managed-block remain in `common.py` packages (diverge in
  contract - not verbatim). 5 smoke-tests core; 113 (skm) + 235 (maind) green.

- **Monorepo academici: maind added to `packages/maind/` (via `git subtree`, history
  saved).** Memory hub The/count now lives under an umbrella next to the skill registry.
  `node_modules` (demon `@agentmemory/agentmemory`) reinstalled in a new location (`npm ci`);
  systemd unit `maind-memory.service` regenerated to a new path (`maind service install`),
  memory demon is alive (ports 4111/4112). `.maind.json` (node config, `0600`) has been moved to the package.
  `orchestrate.py`: path to launcher swissknifeman updated to `packages/swissknifeman/bin/...`
  (local_path remains the root of the repo). `maind doctor` and 235 green tests from a new location.
  Re-deploy `.mcp.json` consumers (≈18 projects keep the old absolute path) — stage 7.
- **Monorepo academici: moving to `packages/swissknifeman/`.** The repository becomes
  ecosystem umbrella - registry contents (`lib/`, `bin/`, `skills/`, `skm/`,
  `generate-skill/`, `scripts/`, `configs/`, `buckets.json` …) moved to
  `packages/swissknifeman/`; umbrella artifacts remain at the root (`.claude-plugin/`,
  `docs/`, `README`, `LICENSE`, `CHANGELOG`). One `marketplace.json` in the root of the repo now
  declares plugins with `source: ./packages/swissknifeman/...` (generator `registry.py`
  breeds package-root vs root-repo via search `.git`; `validate.sh` and
  `generate-graph.sh` adapted). `bin/swissknifeman` no longer requires marketplace.json
  at the root of the package. Symlink is reinstalled `install.sh` from the new path. Prepares the ground
  for package `packages/maind/` under the same umbrella.

- **External audit review: disambiguation overlap-clusters + CI security-gates.**
  By analysis `Audit.md` (verdict - `docs/research/audit-2026-06-review.md`): from
  all recommendations are real 3 (rest - already-done/duplicates/out scope/vs
  stdlib-only invariant). `frontend/vue-composition-api` (0.2.0) trimmed to delta
  (ref-first + composables), basic syntax given upstream `vue`/`vue-best-practices`
  (not removed - serves as an anchor «pattern composable» for ≈13 frontend-skills).
  `php/laravel-permissions` (0.3.1) and `frontend/vitest` (0.1.1) — sharp
  description-triggers against routing confusion (vs `azguard`/`attribute-authorization`
  and vs `vitest-vue`). `devops/ci-cd` (0.3.0) — section «Security gates» (SAST/PHPStan-taint,
  `composer`/`npm audit`+Dependabot, Trivy image scan) + snippet `github-actions-security.yml`.
- **Anti-bloat in existing skills (instead of new takes).** `anti-drift`
  (0.2.0) — section «Dependent package boundary: ask before expanding» +
  updated snippet CLAUDE.md; `code-simplifier` (0.2.0) — checklist
  speculative-generality (YAGNI) on fresh diff; `api-design` (0.1.1) —
  cross-ref on the evolution of the package contract; internal `skill-authoring` —
  skill review standard (universality, no project names/packages).
  `CLAUDE.md`/`CONTRIBUTING.md` — pointers to methodology and anti-bloat gates.

### Fixed

- **auto-approve: false `deny_hard` on `git rm` and `*-init`** — general token `rm`
  caught `git rm` (reversible, files in index/stories), a token `init` — `git init`/
  `npm init`/`composer init`/`swissknifeman topology init`. Now `analyze.sh`
  masks `git rm` before deny_hard-check (naked `rm`/`xargs rm`/`rm -rf`
  are still blocked; `git rm` goes like a mutation - prompt in strict/permissive,
  allowed in bypass), a `init` removed from the general list and replaced with a dot pattern
  rantlevel (`telinit`/`init [0-6sS]`). `git rm` added to `deny_block_approve`.
  Hook files are being updated `apply-permissions.sh --global` (for `config.json` —
  re-upload manually, because it doesn't overwrite)

### Added

- **Integrations catalog `docs/integrations/` + curated MCP-presets.** By analysis
  external audit (`CLAUDE_INTEGRATION_TASK.md`): new section VitePress «Integrations» —
  index + 11 pages (context7, playwright, filesystem, fetch, memory,
  sequential-thinking, github, task-master, spec-kit, claude-code-router), reduced to
  reality hub (remote-HTTP context7, mechanism preset→`integrate`, current packages:
  fetch — `uvx mcp-server-fetch`, github — remote `api.githubcopilot.com/mcp/`; without
  obsolete model-id and fictitious schemes). Curated subset of presets in
  `configs/claude-code/mcp/` (`playwright`/`filesystem`/`fetch`/`memory`/
  `sequential-thinking`/`github`) — **opt-in** via new flag `swissknifeman integrate
  --mcp <a,b>` (interactively - a separate question); `DEV_MCP` is not expanded by default.
  `claude-code-router` — page «there is a tool, but in doubt». **Skills from auditing
  not deliberately created** (anti-bloat): `playwright-e2e-tester` duplicate
  `quality/playwright-e2e`, `git-flow-ru` — `git-commit-rules`+`github-flow`+`writing-style`,
  a `context7-dart-flutter`/`fintech-api-context`/`pos-fiscal-assistant` violate the ban on
  names of specific products in the body of the skill and would fall into CORE-bucket `general` — their place in
  `.ai/skills/` specific projects.
- **`integrate`: MCP-servers in development environments (context7).** New wizard block
  `_block_mcp` pours in presets MCP-servers in `<project>/.mcp.json` (merge-only,
  other people's servers are intact, backup `*.bak`, `--dry-run`). Presets -
  `configs/claude-code/mcp/<name>.json`; first - `context7` (remote HTTP
  `mcp.context7.com/mcp`, up-to-date docs libraries). Gate «development environment»:
  is heard in everything except `obsidian-vault`. Bundles `recommended`/`full` include
  by default, `minimal` — no, `custom` — asks.
- **Semantics loop'ov on top of skills (without a separate registry `loops/`).** By
  audit [loops.elorm.xyz](https://loops.elorm.xyz/loops): page
  `docs/guide/loop-semantics.md` (VitePress, in the sidebar «Guide») — model loop'a
  (Goal/Run mode/Max iterations/Between-check/Exit condition + anti-gaming
  guardrails), phase mapping to existing skills and boundaries «skill gives gates,
  runner built in (`/loop`, `/schedule`)». Skill `task-brief-template` (0.4.0):
  fields `Loop verifier`/`Exit condition`/`Hard stop trigger` in the template + snippet
  `loop-kickoff.md` (starting template of an iterative task for `.claude/commands/`).
  Deliberately without duplicates: iteration/stop is already in `anti-drift`, session-split — in
  `context-economy`, shared-code gate — in `package-contribution-protocol`.
- **`swissknifeman sync` caught up `vendor`/`connect`: manifest, CORE-policy and
  skill index.** Previously `sync` just copied skills and wrote
  `skills-lock.json` — without `.swissknifeman-manifest.json` (reinstallation contract
  and source for `generate-hub.sh`), without CORE-skills and without updating
  managed-block in the project root. Now `sync`: (1) writes a manifesto in `skills_path`
  (`layout: flat`, `flat_name`/`source_path`); (2) distributes `CORE_SKILLS` by
  by default and applies `DEFAULT_EXCLUDE` (flag `--no-core` disables), like
  other channels; (3) updates the skill index (managed-block `CLAUDE.md` /
  `.ai/guidelines/swissknifeman-hub.md`), if it is already in the project or transferred
  `--hub` (`--no-hub` disables). `generate-hub.sh` additionally looks for the manifest in
  `skills_path` from the config (finds non-standard layouts like `.agents/skills`).
- **Methodology against code bloat + skill `architect/package-contribution-protocol`.**
  On auditing ecosystem development practices «project ↔ dependent package» added
  generic-gate against Speculative Generality: main question (Rule of Three +
  YAGNI), principle «stop and ask / subagent go/no-go before extension
  package», two-stage gate (proposal → ADR), table «what is NOT included in the package»,
  direction of dependencies and SemVer contracts. Snippets: `proposal-issue.md`,
  `adr-template.md`, `claude-md-priority.md` (manual «first priority» in
  CLAUDE.md consumer), `permissions-deny.md`. Skill **opt-in** (bucket
  `architect`), without specific project names/packages. Basic reflex «ask
  before extension» — in CORE-skill `anti-drift` (goes to all projects);
  deep protocol is connected selectively (hybrid distribution).
- **Permissions-preset `product-boundary`** (`configs/claude-code/settings.product-boundary.json`):
  deny to write to the dependent package (`Write/Edit(vendor/**)`); option for
  path-repo (`packages/**`) — in the skill snippet. Opt-in (not in autodetect),
  is applied via `apply-permissions.sh --preset product-boundary`.
- **Page `docs/guide/methodology.md`** (VitePress, in the sidebar «Guide») —
  anti-bloat with map «principle → skill/config» and hybrid distribution.
- **Figma MCP-skills + new bucket `mobile`.** Three skills improve work
  agent with connected Figma Dev Mode MCP: `architect/figma-mcp-core` —
  framework-agnostic discipline (real tools `get_metadata`/
  `get_variable_defs`/`get_code`/`get_code_connect_map`/`get_screenshot`/
  `search_design_system`, prohibition of extracting values from screenshots,
  selection-driven algorithm, W3C `tokens.json`, audit design-system);
  `frontend/figma-to-vue` — mapping in Vue + Tailwind v4 (`@theme`, cva, `.dark`);
  `mobile/figma-to-flutter` — mapping in Flutter (`ThemeData`, Row/Column/Expanded,
  Stack/Positioned). New bucket `mobile` (Flutter) in `buckets.json`.
- **Vendor-mode `swissknifeman sync` — physical transfer of skills one by one
  config.** `.swissknifeman/config.json` — source of truth (rules:
  `include` specific skills + `buckets` in full − `exclude`); `sync`
  expands them into a flat set according to `skills.json`, copies files to
  `skills_path` (default `.claude/skills`) and writes the derivative
  `skills-lock.json` marked `managed`. Safe prune: are deleted only
  `managed=true` records that disappeared from the config - someone else's/manual vendoring
  (legacy Boost, another hub) is not touched. The config is recognized as a marker
  project root; example - `.swissknifeman.example/config.json`; docks -
  `docs/guide/vendor-mode.md`. Read-only composer `lock` remains for
  projects without vendor-mode.
- **Management-plugin `skm@swissknifeman`** — command person CLI: directory
  `skm/` with static `plugin.json` + slash-commands (`skm`, `skills`,
  `integrate`, `status`, `doctor`). Not a skill bucket - `registry` adds
  entry in `marketplace.json` synchronously, `validate.sh` checks as usual
  plugin. Install `skm@swissknifeman` gives commands for managing project skills.
- **Implementation of the audit backlog - 14 more universal skills + 1 extension
  (batch-2).** Finished all deferred §5 candidates from
  `docs/research/practices-audit-2026-06.md`; all summarized (project - only
  evidence, the skill includes a transferable pattern + anonymized snippets).
  **Frontend (7):** `frontend/reka-ui-cva` (headless-primitives Reka UI + cva),
  `frontend/dark-mode` (composable light/dark/system, without flash, SSR-cookie),
  `frontend/naive-ui-theming` (GlobalThemeOverrides), `frontend/laravel-echo-client`
  (Echo/Reverb composable, X-Socket-ID), `frontend/filepond-upload` (vue-filepond
  + rahulhaque/laravel-filepond), `frontend/vue-dynamic-icons` (dynamic icon
  by name), `frontend/pinia-stores` (setup-stories, composition). **PHP (4):**
  `php/livewire-blade-attributes` (delta-gochizy to Boost livewire),
  `php/spatie-settings`, `php/health-checks` (spatie/laravel-health),
  `php/laravel-data` (spatie/laravel-data DTO + `#[TypeScript]`). **Quality (2):**
  `quality/playwright-e2e`, `quality/mutation-testing` (Infection). **Blender (1):**
  `blender/parametric-config` (config-dataclass → profile/check without bpy).
  **Expanded** `php/laravel-testing` (Pest-composition: traits + fake/freeze/dataset).
  `skills.json` 138 → 152; Boost-boundaries respected (complementary: `laravel-data`,
  `spatie-settings`, `livewire-blade-attributes`); `boost-compatibility.md` updated;
  `validate.sh` green (0 warnings, 76 tests).
- **Skills from constellation practices (audit + 10 skills, focus - frontend).**
  Read-only audit of all projects from `~/Vaults/Brain/.projects.json` + `unbox`,
  `art-kombinat/frontend`, `sova` (6 Explore-agents, checking candidates with live
  registry to cut off vendor copies). Parsing - in
  `docs/research/practices-audit-2026-06.md` (stack fingerprints, correction
  vendored-vs-local, authorized, deferred backlog, out of scope). **7 new
  skills:** `frontend/tailwind-conventions` (Tailwind v4: CSS-first `@theme`,
  tokens, dark theme, `cn()`, prettier-plugin-tailwindcss), `frontend/backend-type-sync`
  (`spatie/laravel-typescript-transformer` + `#[TypeScript]` → `App.Enums.*`/`App.Data.*`,
  paired with `wayfinder`), `frontend/eslint-flat-config` (ESLint 9 flat for Vue/TS:
  `@stylistic`, import boundaries, chain Prettier), `php/test-isolation-guard`
  (bootstrap-guard against combat database tests/media disk), `php/attribute-authorization`
  (`#[CheckPermission]` + reflection-middleware on top Gate), `general/writing-style`
  (tone/language of comments, commits, test descriptions - extended version, merged
  with the skill of the same name from flexcrm-extraction below), `devops/db-test-preflight`
  (pre-flight Postgres-DB before tests - analogue `node-pnpm-preflight`). **3 expanded:**
  `frontend/inertia-vue` (domain slices `features/<domain>/` + import boundaries, →0.3.0),
  `php/enum-attributes` (section `#[TypeScript]` + export types, →0.2.0),
  `php/modular-architecture` (implementation on `nwidart/laravel-modules` + Filament discovery, →0.3.0).
  Snippets are anonymized; `validate.sh` green (0 warnings).
- **Extraction of universal skills from flexcrm** (source: local, copyright):
  `quality/testing-safety-report` (security report after migrations/refactoring),
  `php/php-upgrade-checklist` (version upgrade checklist PHP — image/CI, composer,
  phpstan-baseline, rector, RFC), `general/writing-style` (live commentary language
  and commit texts, complements `git-commit-rules`). Boost-ownership (tailwind/mcp/
  pest) and those already existing in the registry were not duplicated; `fortify-development` abandoned
  local in the project by owner's decision
- **Doc warning about clean reinstallation** (`docs/guide/cli.md`): `vendor`/
  `update` remove previously vendor skills that have fallen out of the registry set, including
  **uncommitted** local copies - keep project skills in git; preview
  deleted - `--dry-run`. (An acute angle that came up during onboarding flexcrm)
- **Integration Wizard `swissknifeman integrate`** (`lib/swissknifeman/integrate.py`)
  + [checklist](docs/guide/integration-checklist.md) — single entry point: passes
  checklist «choose what you want from the maximum functionality» and applies the selection,
  reusing `do_connect`/`do_vendor` (skills), `apply-permissions.sh` (permissions),
  `generate_hub` (hub) + writes per-project hook-JSON (auto-approve on PreToolUse
  Bash/ExitPlanMode) and `.swissknife.json:memory_brain` (membership memory-brain).
  Bundles `minimal|recommended|full|custom`; safe - `--dry-run`, merge-only with
  backups `*.bak`, idempotent, prerequisites (`topology init`, `--global`) only
  with confirmation. Registered in `cli.py`/launcher; tests `tests/test_integrate.py`.
  B `CONFIG_KEYS` added `memory_brain`/`coordinator_ignore` (are valid in `.swissknife.json`)

- **Flexible «unified memory» constellations** — self-contained hook folder
  `configs/claude-code/hooks/memory/` according to the example auto-approve: switch
  `memory.sh` (remember/recall/members/status/sync), mode in `env.ini`
  (`MODE=file|federation|agentmemory|off`), groups and members in `config.json`,
  backends in `modes/`. **Membership:** general «brain» (brain) visible only to members
  from it `members` (resolve nodes/projects via topology). Modes are interchangeable
  (file/federation on markdown without daemon; agentmemory — proxy to third party
  demon on Brain, degrades when unavailable), config is overridden
  per-project (`<project>/.claude/memory.{env.ini,config.json}` + `.swissknife.json:
  memory_brain`). Fact schema is compatible with native memory Claude Code, therefore
  `federation` reads and `~/.claude/projects/<slug>/memory/` participants. Bonding agent -
  skill `system/shared-memory`; installation via `apply-permissions.sh --global`.
  `validate.sh` now `bash -n`-and all hook scripts `configs/claude-code/hooks/`
- **Cross-project code coordinator** — `system/cross-project-coordinator` (skill) +
  agent `system/agents/code-coordinator` (read-only). On top of the topology bypasses
  related projects, listing only git-monitored files (`git ls-files` —
  respects `.gitignore`/`.git/info/exclude`, secrets and vendor/does not read the generezhka),
  and searches by seven criteria: duplicates between repo, divergent implementations of one
  concept, drift from skill registry, copy-instead-of-dependency, discrepancy
  conventions/documentation/dependencies. Criteria reused `quality/`-skills
  (tech-debt-audit, refactoring-plan, code-simplifier, code-review). Outputs
  prioritized (impact×effort) report with `file:line` by projects and named
  extraction target; edits/PR doesn't. `requires: local-topology`
- **Local environment topology** — system root node. New bucket `system`
  with skill `local-topology` (distributed to all projects: added to profiles
  laravel-project/php-package/obsidian-vault), command `swissknifeman topology
  [init|show]` (`lib/swissknifeman/topology.py`) and global config
  `~/.swissknifeman/topology.json` (version 1): three hub nodes
  Brain-volt/swissknifeman/project-base (roles docs-hub/skills-hub/workspace).
  `init` — interactive collection with auto-default detection, atomic recording with
  backup `.bak`, save `created_at`; is suggested when `install.sh` (TTY).
  Skill explains the scheme and resolves nodes according to the config - any agent in any project
  sees where the nodes are and gets to the code/documentation of neighboring projects.
  Tests `tests/test_topology.py` (+10). Roadmap: cross-project optimizer agent
- **Notification-hook `configs/claude-code/hooks/notify/notify.sh`** — OS notification,
  when Claude Code waiting for a person: tool permission request, approval
  plan (ExitPlanMode) or a simple prompt longer ~60 sec. Cross platform
  (Linux `notify-send`, macOS `terminal-notifier`/`osascript`, WSL/Windows toast).
  Registered as a preset `global`, is placed via `apply-permissions.sh --global`,
  never blocks (`exit 0`)

### Added (food readiness)

- **`LICENSE` (MIT)** + field `license` in `package.json` — legal basis for
  propagation; external (imported) skills retain source licenses
  (`upstream.json`)
- **`SECURITY.md`** — procedure for disclosing vulnerabilities, trust model of imported
  skills (sha256 in `upstream.json`, strategies `notify`/`replace`), rule
  «no secrets in snippets», priority «project > source > registry»
- **`.github/workflows/test.yml`** — separate CI with matrix Python 3.9–3.12
  (previously tests were chasing only the tail `validate.sh` on one version)
- **Core coating CLI tests** (38 → 57): `registry` (`build_registry`,
  `write_plugin_manifests`, provenance external skills, die without `buckets.json`),
  `state` (CRUD `projects.json`, save `first_connected_at`, atomicity),
  `doctor`, `status`, `update` (selection replay, idempotency) — now every
  commands are a direct test; helper `write_upstream` in `tests/fixtures.py`
- **`docs/guide/troubleshooting.md`** — diagnostics (`command not found`, Claude
  Code does not see skills, conflict `settings.json`, vendor collisions, broken
  `projects.json`) and update (registry, vendor `update`/`--all`, change scheme);
  added to sidebar
- **Badges in README** (Tests / Validate / Docs / License) + sections
  «Security» and «License»

### Changed (refactoring CLI: lib/ + tests)

- **`bin/swissknifeman` → slim launcher**: all Python-logic (before - heredoc
  for 1300 lines inside bash) included in the package `lib/swissknifeman/` and unfolded
  by module (`common`, `config`, `state`, `connect`, `vendor`, `update`,
  `status`, `listing`, `registry`, `doctor`, `boost`, `hub`, `cli`). Binary
  does preflight-checks and `exec python3 -m swissknifeman <root> <cmd>`.
  Byte-to-byte behavior is the same (`registry` gives identical `skills.json` and
  manifests); installer and symlink are not affected. Modular globals
  `root`/`cmd`/`argv` replaced with explicit `Env` — functions became importable

### Added (tests CLI)

- **`tests/` (stdlib unittest, without dependencies)**: 27 unit tests
  (frontmatter, parsing flags, sanitize, autodetect, precedence
  `resolve_selection`, transitive `requires`, collisions flat-names) and
  11 integration - fake Laravel-project in tmpdir, cases `connect`/`vendor`
  (autodetect, explicit plugins, saving `false`, dry-run, bucket/flat-layout,
  pull `requires`, `--exclude`, sync `boost.json`, clean reinstall).
  Synthetic registry (`tests/fixtures.py`) — tests are content independent
  skills
- **`scripts/test.sh`** — test runner (`-v` for detailed output), is built into
  `scripts/validate.sh` (group 12: package import + suite run). Same
  script runs CI

### Added (gh-driven review and context saving)

- **`oss-dev/gh-review` (0.1.0)**: review and handoff of changes via GitHub CLI
  with context saving - `gh pr diff/view/comment/review` give point cut
  (diff, threads), `gh api .../contents` pulls one file instead of downloading the whole one.
  Clear boundary: local VCS (commit/branch/diff/log/rebase) — for `git`,
  platform (PR/issue/release/api) — for `gh`. `requires: context-economy`,
  `produces_for: github-flow`; snippet-command cheat sheet
- **`scripts/update-upstreams.sh` — channel `gh api`**: for GitHub raw-URL and when
  available `gh` file is pulled through `gh api repos/{o}/{r}/contents/{path}?ref=...`
  (auto-authentication from `gh auth`, rate-limit, one file). Silent rollback to
  `urllib`+`GITHUB_TOKEN`, if `gh` unavailable; shutdown - `UPSTREAM_NO_GH=1`.
  Applies to imported skills (`source: github`)

### Changed

- **`general/context-economy` 1.0.0 → 1.1.0**: section «Platform layer -
  via `gh`, not files» (`gh` complements `git`, does not replace; savings on
  point cut) + checklist item; link to `oss-dev/gh-review`
- **`oss-dev/github-flow` 0.1.0 → 0.2.0**: step Review refers to `gh-review`
  (`requires += gh-review`); review PR — via `gh`, not loading files
- **Documentation**: stage «dev-review via gh» in the intersystem chain
  (`docs/workflows/index.md`), channel `gh api → urllib` in
  `docs/guide/upstream-sync.md`

### Added (integration with Laravel Boost — compatible kernel)

- **`php/named-arguments` (0.1.0)**: required named argument rule
  in PHP-calls with scope and exceptions (one argument, built-in
  functions, splat). Extracted and de-agelized from the project skill;
  `source: local`. Complements, not duplicates - the registry was previously only *used*
  named arguments in examples, there was no separate rule
- **`php/pennant-development` (0.1.0)**: feature-flags Laravel Pennant
  (`define`/`active`/`for`-scope, directive `@feature`, activation/rolling).
  Retrieved from `laravel/boost` (`upstream.json` strategy=notify) — the only one
  clean static-`.md` generic-candidate without version fork; Blade-skills
  Boost (`folio`/`volt`/`mcp`) remain for Boost (needed render-context)
- **`php/laravel` → `eloquent-model.md`**: section «Accessors and mutators» added
  rules `Attribute::make()` (visibility `protected`, camelCase→snake_case,
  position in class, migration from legacy-accessors) — merged from project
  `laravel-attributes` instead of creating a duplicate

### Added (CLI and hub - installation in Boost-projects)

- **Boost-aware `vendor`/`update`**: if available `boost.json` in the target project
  CLI (1) automatically uses **flat-layout** `.ai/skills/<name>/SKILL.md`
  — Boost detects user-skills through `glob('.ai/skills/*')` one level,
  bucket-he would not have found the subfolder; (2) idempotently overwrites vendor ones
  skills in `boost.json::skills` (by frontmatter-`name`) and prompts
  `php artisan boost:update`. Skills are automatically distributed to all agents
  Boost from a single source `.ai/skills/`
- **`generate-hub.sh --root-files A,B`**: managed-hub block (between markers
  `swissknifeman:hub:start/end`) is additionally written to the specified root files
  (`AGENTS.md`, `GEMINI.md`, …) for tools outside Boost; content outside markers is not
  starts moving

### Fixed

- **Hub marker out of sync**: `bin/swissknifeman` searched
  `<!-- swissknifeman:hub:begin -->`, whereas `generate-hub.sh` writes
  `:start`/`:end`. Because of this `hub_artifacts_exist()` couldn't find it managed-block in
  `CLAUDE.md`, and `update`/repeated `connect` did not understand that the hub was already in place.
  Reduced to a single `hub:start`

### Changed (kernel concept documentation)

- **Compatible Kernel Policy** is fixed explicitly: `docs/guide/index.md`
  (principle №6 «Compatible kernel» + use case table), `README.md`,
  `references/laravel-boost.md` (extraction criterion static/versioning/generic,
  what is extracted, what is not and why), `docs/guide/installation.md` (section
  «Project with Laravel Boost»). Update flow inverted: generic-skills
  of an external source are updated first in the registry, then pulled into projects

### Added (subagents Laravel)

- **`php/agents/` — first agent definitions in the plugin**: bucket plugin is now
  carries a catalog `agents/` (Claude Code detects it in the plugin root
  automatically; registry and validator directories without SKILL.md ignored;
  available only in plugin-channel - `vendor` does not copy agents).
  Agents: `laravel-reviewer` (read-only review with fresh context:
  PHPStan/Pint/targets Pest, Laravel-criteria, structured findings without
  edits) and `laravel-test-writer` (Pest-tests using ready-made code in the style
  existing project tests; application code does not change - discrepancies
  reports)
- **`php/laravel-subagents` (0.1.0)**: subagent orchestration protocol on
  large Laravel-tasks - response threshold (≥3 layers/domains or the whole
  feature; small/medium - direct, explicit anti-trigger), research via
  Explore-agents, the architectural code is written by the orchestrator, parallel only for
  independent subtasks (otherwise worktree), `laravel-reviewer` after each
  units, `laravel-test-writer` by finished code, pipeline anti-patterns
  role agents

### Added (github-flow)

- **`oss-dev/github-flow` (0.1.0)**: process chain Issue → Branch → PR →
  Merge → Tag → Release on GitHub — naming Issue/branches/PR, labels, SemVer-oracle
  by commit type, checkpoints with mandatory agent questions;
  PHP/Packagist-gate in `references/php-package-gate.md`; snippets with templates
  PR/Issue; `requires: git-commit-rules, release-engineering` (commit format
  and changelog/pipeline are not duplicated)

### Changed (github-flow)

- **`general/git-commit-rules` 0.1.0 → 0.2.0**: expanded list of types
  (`perf`, `style`, `build`, `ci`, `revert`), section «Conventional Commits:
  scopes and breaking changes» (source scope — commitlint, footer
  `BREAKING CHANGE` / `!` after type), link to SemVer-oracle github-flow

### Added (CLI swissknifeman + internal skills)

- **CLI `bin/swissknifeman`**: single entry point - `connect` (marketplace
  Claude Code), `vendor` (vendoring), `update [--all]` (channel detection by
  disk markers, adopt unregistered projects, repair path-drift
  marketplace when moving the registry), `status`, `list [--prune]`, `registry`
  (ex `sync.sh --update-registry`), `validate`, `doctor`, `version`.
  The project root is searched upwards from CWD (`.swissknife.json` → `.claude/` →
  `.git`) — flag `--target` is no longer needed
- **Project Map `~/.swissknifeman/projects.json`** (schema v1, key
  path+channel): is replenished automatically when connect/vendor/update; explicit
  selection (`--profile`/`--plugins`/`--buckets`) is played when `update`,
  autodetect will be re-resolved from the disk; atomic write, self-healing
  adopt-om after file loss
- **Internal skills `.claude/skills/`** (are not exported): full map
  package (`package-architecture`), skill authoring procedure with verification
  intersections and mandatory upstream.json for external (`skill-authoring`),
  change completion discipline (`release-discipline`), decision on
  update docs/ after tasks (`docs-maintenance`)
- **validate.sh sections 10–11**: soft linting of internal skills
  (name+description, kebab-case == directory, warning in case of a conflict with the registry);
  `bash -n` all scripts + executability CLI
- **`docs/guide/cli.md`**: command reference CLI, diagram projects.json,
  search for project root, troubleshooting

### Changed (CLI swissknifeman)

- **`install.sh` repurposed as an installer CLI** (symlink
  `~/.local/bin/swissknifeman` → `bin/swissknifeman`, is idempotent,
  PATH-shell tooltip); **breaking**: legacy-vendoring
  `./install.sh <dir> <bucket>` deleted - `swissknifeman vendor`
- `scripts/connect-claude.sh` and `./sync.sh --update-registry` —
  deprecation-wrapper's for one release, will be redirected to CLI
- `docs/guide/installation.md` rewritten for two-step installation
  (CLI once → `connect`/`vendor` from the project); README and others
  pages docs translated to commands CLI

### Removed (CLI swissknifeman)

- **Brain-sync** (`sync_to_brain`, `BRAIN_PATH`, workflow
  `.github/workflows/sync-to-brain.yml`): mirroring to brain no more -
  brain connects as a regular project
  (`cd <brain> && swissknifeman vendor`, next `swissknifeman update`)

### Added (improvement report v2: dependency graph + methodology)

- **Dependency resolution in install.sh**: frontmatter `requires` is allowed
  transitive for custom installation (`--buckets`/`--exclude`), including
  cross-bucket; `--exclude` defeats dependency with warning; outstretched
  skills are marked in `--list`/`--dry-run` like `(dependency of <skill>)`
- **Graph validation in validate.sh** (section 9): existence of names in
  `requires`/`produces_for`, self-reference, cycles through `requires` (DFS);
  warning on non-inline lists
- **`scripts/generate-graph.sh`**: Mermaid-dependency graph →
  `docs/guide/graph.md` (subgraph per bucket, only connected nodes, isolated -
  table); is called from `sync.sh --update-registry`; in VitePress connected
  `vitepress-plugin-mermaid`
- **Registry skills.json v5**: fields `tags`, `requires`, `produces_for`
  in skill records (are optional, omitted if empty)
- **`general/anti-drift` (0.1.0)**: methodology Karpathy (think-before-coding,
  simplicity-first, surgical-changes, goal-driven) + circuit-breaker thresholds;
  snippet block for CLAUDE.md target project
- **`general/spec-interview` (0.1.0)**: grill-me-style pre-code interview -
  questions one at a time, the agent reads the codebase itself, recommended answer
  for each question; result - completed task-brief-template
- **`general/session-handoff` (0.1.0)**: context transfer protocol between
  sessions/agents; snippet handoff-template.md
- **`quality/code-simplifier` (0.1.0)**: simplification of fresh diff without change
  behavior; snippet GitHub Actions `simplify-on-push.yml`
- **`php/laravel-security-audit` (0.1.0)**: sharp-edges-audit Laravel
  (raw-requests, mass assignment, XSS in Blade, CSRF/redirect,
  serialization/authorization) with references/ for each edge; snippet
  GitHub Actions `security-audit-scheduled.yml`; requires: static-analysis
- **`docs/workflows/background-agents.md`**: background agents in CI — templates,
  requirements, cost restrictions, anti-drift rules

### Changed (improvement report v2)

- `general/task-brief-template` 0.2.0 → 0.3.0: sections «Explicit assumptions»,
  «Out of Scope», «Definition of Done» in the TK template
- `oss-dev/dependency-audit` 0.1.0 → 0.2.0: `references/composer.md` —
  composer-audit specifics (composer audit/outdated/licenses,
  roave/security-advisories, reproducible installs, composer-rake, SBOM)
- `php/filament`: `produces_for: [backend-dev, fullstack-dev]` → `[]` — such
  skills do not exist (caught by new graph validation)
- `docs/boost-compatibility.md`: link to card laravel-boost leads to
  GitHub (relative path outside docs-root broke the assembly VitePress)

### Rejected (improvement report v2, based on the results of the analysis)

- `registry.json` — already exists as `skills.json` (richer: sha256,
  provenance, upstream)
- Tier-system (0–4) in the frontmatter - duplicates the bucket axis+profiles+requires
- `caveman`-skill - covered `general/compact-responses`
- `composer-audit` as a separate skill - extension `dependency-audit`
- Background workflow in the registry itself - only templates for target projects

### Added (token optimization wave)

- **`php/pao` (1.0.0)**: skill by laravel/pao — agent-optimized output
  PHPUnit/Pest/PHPStan/Rector/Artisan (~20 tokens JSON instead of thousands);
  installation, testing, restrictions
- **`general/context-economy` (1.0.0)**: context saving Claude Code —
  CLAUDE.md ≤200 lines, path-scoped `.claude/rules/` with `paths:`, /compact vs
  /clear, Plan→Clear→Execute, audit MCP, native model routing;
  snippets: rule template, commands /prime //plan //execute, audit checklist
  CLAUDE.md
- deny-block «token-noise» in presets `configs/claude-code/settings.laravel.json`
  and `settings.node.json` (`storage/logs`, `node_modules`, `*.lock`, caches,
  bundles); `vendor/` is not deliberately blocked - there Boost-guidelines

### Changed

- **`php/filament` 0.2.0 → 1.0.0**: rewritten from v3 on Filament v5 — structure
  v5-generator (Schemas/ + Tables/), table of valid namespaces
  (`Filament\Actions\*`, `Filament\Schemas\Components\*`), CLI-reference
  `make:filament-*`, union-property types, typical errors from official
  Boost-guidelines; snippets updated under v5 + new
  `forms-tables-reference.md`; upstream.json tracks
  filamentphp/filament `boost/guidelines/core.blade.php` (strategy=notify)
- `general/compact-responses` 0.1.0 → 0.2.0: loop behavior patterns
  development (`✓ tests passed (N)`, only failed test on error) and format
  the only detailed final report
- `general/task-brief-template`: section Plan→Clear→Execute (plan and execution -
  separate sessions)

### Rejected (based on fact-check reports Perplexity)

- `.claudeignore` — does not exist in Claude Code (working mechanism -
  `permissions.deny: Read(...)`)
- `paths:` frontmatter for SKILL.md — `paths:` only works in
  `.claude/rules/`; skills are already loaded lazily
- claude-code-router — third party proxy; native `/model` is sufficient
- waaseyaa/agent-output as standard - overlapped laravel/pao
- `deny Read(vendor/**)` — breaks reading Boost-guidelines

## [0.3.0] - 2026-06-11

### Added

- **Native plugin marketplace Claude Code**: `.claude-plugin/marketplace.json`
  + `plugin.json` for each bucket (are generated `sync.sh --update-registry`,
  metadata in `buckets.json`); plugin = bucket, skills with namespace
  `<bucket>:<skill>`, plugin version = git SHA
- **`scripts/connect-claude.sh`**: connecting the project to marketplace —
  profile auto-detect, idempotent merge `extraKnownMarketplaces` +
  `enabledPlugins` in `.claude/settings.local.json`, `--dry-run`/`--list`,
  migration from old vendor (`--cleanup-vendored` deletes only
  manifest copies)
- **`buckets.json`**: description/category/tags on bucket; descriptions fall
  in plugin-manifests and skills.json (registry v4)
- **Schema-validation `.swissknife.json`** in install.sh and connect-claude.sh:
  unknown key/type → error with hint (`did you mean 'buckets'?`)
- **Manifest and collisions in bucket-mode install.sh**: `.swissknifeman-manifest.json`
  is now written in generic/cursor-mode (clean reinstall), existing
  other people's folders - collision error, overwriting only with `--force`
- validate.sh: checks buckets.json, freshness plugin-manifestos,
  uniqueness of skill names

### Changed

- `generate-skill/` restructured to layout plugin
  (`generate-skill/generate-skill/SKILL.md`)
- `--agent claude` in install.sh — deprecated (preferred marketplace);
  `.claude-plugin/` is excluded from vendoring and brain-sync
- Documentation: adapter Claude Code rewritten around marketplace,
  installation guide is divided into channels Claude Code / Cursor-generic
- Links to `references/` in `oss-dev/oss-development` corrected to
  relative to skill (`../references/...`)

### Added (docs & configs wave)

- **Documentation for VitePress** (`docs/`): guide (principles, installation, profiles,
  skill anatomy, upstream-sync, registry, scanner, CI), configs, adapters,
  examples, roadmap; deploy to GitHub Pages (`docs.yml`)
- **Presets permissions for Claude Code** (`configs/claude-code/`):
  base/laravel/php-package/node/python/docker/yolo +
  `scripts/apply-permissions.sh` (merge in settings.local.json, stack autodetect,
  dry-run, backup)
- **Vendor-skills**: universal mechanism for publishing skills from Composer-package
  to the consumer via `vendor:publish` — doc page + reworked skill
  `php/laravel-packages` (v0.3.0) with snippet `boost-skill-publisher.php`
- **Adapter Delta Specification**: format `Override:`/`Additional:`,
  pre-flight hooks, criteria «when delta is needed»
- Quality criteria for scanner snippets (threshold 60/100) in the documentation
- Roadmap: coming phases + strategic/technical/experimental ideas
  (moved from tmp-drafts master-plan v3, drafts deleted)

## [0.2.0] - 2026-06-11

### Added

- **Upstream-sync system**: per-skill `upstream.json` (source, strategy replace/notify,
  sha256, fetched_at), `scripts/update-upstreams.sh` (--check/--apply/--force, exit-codes
  for CI), weekly workflow `upstream-sync.yml` with PR-review
- `upstream.json` + baseline for all 12 `skills/imported/*` (get-zeked super-skills)
- **Contextual installation**: `install.sh` v2 — project type autodetect, `profiles/*.json`
  (obsidian-vault, laravel-project, php-package, standalone), `.swissknife.json` override,
  `--agent claude` with flat layout under `.claude/skills/` and manifest-cleanup
- **`references/`** — catalog of 15 external sources with the principle of selective selection
- `scripts/validate.sh` — single validation (frontmatter, upstream.json, profiles,
  registry, snippet-manifests) locally and in CI
- Provenance in `skills.json`: `source: local|github|http`, `upstream`, `fetched_at`
- `.swissknife.example.json`

### Fixed

- `validate.yml`: glob `skills/**` did not work in bash without globstar — CI actually
  did not validate skills
- `sync.sh`: name/description were parsed throughout the entire file, not just from frontmatter
- `skills/pm/prd-from-brd`: field was missing `version` in frontmatter

## [0.1.0] - 2026-06-11

### Added

- Skills registry v3 with 65 skills across 10 buckets
- Migration of 36 skills from `academici/brain`
- New buckets: devops, php, roles, imported
- 12 perplexity super-skills in `skills/imported/`
- PHP skills: laravel, laravel-permissions (with AzGuard patterns), laravel-testing, laravel-packages, php-patterns, botkit, filament
- DevOps skills: docker (php, vite, postgres, dev-prod), ci-cd, gitops
- Roles: startup-cto, tech-lead, open-source-maintainer, solo-founder
- `install.sh`, `sync.sh`, scanner pipeline
- CI: validate, sha256-update, sync-to-brain, scanner-pr
- Adapters: cursor, claude-code, perplexity
- `generate-skill/` meta-skill
