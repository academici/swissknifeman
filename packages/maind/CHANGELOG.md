# Changelog

Format - [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
versioning - [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

### Added
- **Installer declared in unit.json:** `provides.install` is `["install.sh"]`, so `swissknifeman install` runs it with `--bin-dir` and `--force` (no prompt with `--force` or without a TTY).
- **Hub modules on aicore:** maind imports only itself and `aicore` and reaches `harness`, `analyst`, `skiller` and `brain` through partner commands found by `aicore.util.partners` (`PARTNER_UNAVAILABLE` and degradation without a partner). Settings are the `[maind]` table, the fleet registry is `<state>/maind/registry.json`, the machine map is `maind topology`; documentation in `docs/ecosystem.md`, `docs/guide/{cli,config,health,mcp}.md` and the README.
- **Doctor as check-result/v1:** `maind doctor --json` prints check-result documents (`maind.environment`, `.config`, `.registry`, `.memory`, `.mcp`, `.health`); the text form adds `<status> <check_id>: <observed>` lines. The doctor no longer creates the state directory, and the Python floor is `aicore.MIN_PYTHON`. `maind health --plan-repair` shows the repair steps (read-only), `--apply-repair` performs them; `--fix` is a deprecated alias (`MAIND_HEALTH_FIX_DEPRECATED`).
- **maind:** the MCP server negotiates the protocol version: `initialize` returns the requested version when it is in `SUPPORTED_PROTOCOL_VERSIONS` (`2025-06-18`, `2024-11-05`), otherwise the newest supported one (it used to echo the client's version). `maind mcp tools [--json]` prints the tool list and its `tools_digest` (contract `mcp-tools/v1`). An optional conformance test runs the server against the official MCP Python SDK (`packages/maind/requirements-dev.txt`, skipped without it; the runtime never imports the SDK).
- **Hook modes through harness:** the memory and agent-router modes of a project are read from `harness hooks show --json`
  (`settings.hooks.<hook>`), then from the committed `.swissknifeman/hooks.env`, then from the legacy `.claude/*.env.ini` (the last two
  are read directly when harness is missing). `maind onboard` sets the memory mode with `harness hooks --memory <mode>` and no longer
  writes `memory.env.ini`; without harness the write is skipped with `PARTNER_UNAVAILABLE` (`memory_env_skipped` in the report). `health`
  and `sync` (memory-hook, router-config) use the same readers.
- **Harness link:** `maind.harness_link` reaches harness only through its JSON commands (`mcp catalog`, `profiles resolve`,
  `hooks codex-lifecycle fragment|validate`, `instructions scopes|plan|check|apply|repair`) found by `aicore.util.partners`
  (`SKM_HARNESS_BIN`, `SKM_HARNESS_ROOT`, PATH; `MAIND_HARNESS_BIN` still works with one `MAIND_HARNESS_BIN_DEPRECATED` warning). The MCP
  projection comes from `aicore.provider.mcp`. `maind deploy`, `sync` (instructions), `workspace` trust and the provider conformance
  report use them; without harness those steps are skipped with `PARTNER_UNAVAILABLE` (trust stays non-green) and the hub servers still
  deploy. `plan_d108_operation`, `plan_d104_bootstrap_transfer` and `generate_conformance_report` no longer take the harness
  configuration folder. The provider files and lock records are byte for byte what they were.
- **Topology:** `maind topology show|init [--json]` and `<state>/maind/topology.json` (legacy `~/.swissknifeman/topology.json` read file by file with one warning; `*.bak` copies go through `aicore.state.backup`; defaults come from the fleet registry and the known vault). `skiller topology` is an alias. Skills `local-topology`, `cross-project-coordinator`, `shared-memory` and the agent `code-coordinator` read the map through `maind topology show --json` and `skiller list --json`.
- **Contract:** `projects-list/v1` (`schemas/projects-list/v1`) describes `maind projects list --json`; the output itself is unchanged.
- **Skills and agent:** the plugin `maind` 0.5.0 ships the skills `local-topology`, `swissknifeman-locator`, `cross-project-coordinator` and `shared-memory` and the agent `code-coordinator` (moved from the `system` bucket of skiller), and a Codex plugin manifest.

### Changed
- **Config split:** settings are the `[maind]` table of the layered config (`configs/config.schema.json`, `config.example.toml`), the
  fleet registry is `<state>/maind/registry.json` (single writer `projects.write_registry`, previous file kept under the state
  `backups/`); `Config.load` returns the same dictionary as before. The legacy node file (`config.json`, `.maind.json`) is read until
  `swissknifeman upgrade` with one `MAIND_LEGACY_CONFIG` warning (settings: an extra layer while no `[maind]` table is set; registry:
  while there is no `registry.json`, and then written back to that file). `Config.source` is `config`, `legacy:<file>`,
  `linked-worktree-config`, `brain-fallback` or `empty`. `maind migrate from-brain` writes `registry.json` and the node settings into
  the machine config.
- **Places:** `Env.state_dir` is `<state>/maind` and `Env.data_dir` `<data>/maind` (`aicore.state`; `~/.maind` and `<module>/data` are used
  with one warning while the new places do not exist); `Env.projects_db` is removed (it was unused); `default_config` is now
  `legacy_node_config`; `install.sh` no longer creates `~/.maind`.
- **Graph links:** `derive` reads `[maind.graph.links.<project>]` (`type`, `plane`, `note`) from the project's `.swissknifeman/config.toml`;
  `<repo>/.maind.graph.json` is read with `MAIND_LEGACY_GRAPH_LINKS` while the project config has no `[maind.graph]` table.
- **Provider selection of a project:** read from `[aicore.providers]` of `.swissknifeman/config.toml`, else the legacy
  `.swissknife.json#/providers` (warning `MAIND_LEGACY_PROVIDERS`); the one-off D108 deployment writes to the active carrier (a legacy
  file keeps its bytes, a new project gets the TOML table).
- **Backups:** files maind replaces are copied to `<project>/.swissknifeman/backups/<stamp>/` (rotated) instead of `*.bak` next to them.
- **Template:** `config.example.json` moved to `configs/registry.example.json` (registry keys only).
- **aicore:** maind imports `aicore` directly; `maind.blocks` and `maind.http` are removed, `maind.common` re-exports nothing but its own
  `Env` and `load_json_db`; `bin/maind` and `scripts/test.sh` no longer add the monorepo root.
- **Neighbors:** skiller and harness are found through `aicore.util.partners` instead of `constants.SIBLINGS` (old `MAIND_SKM_BIN`,
  `MAIND_HARNESS_BIN`, `MAIND_BRAIN_BIN` still work first and warn once); a missing neighbor gives `PARTNER_UNAVAILABLE` and the same skip
  as before. Agent-pack profiles are read from `skiller profiles --json`.
- **Vault:** `projects.brain_path` takes `integrations.brain.path`, the `brain` project's `vault_path`, then `brain vault --json`, and returns
  `None` when none is known (`maind projects sync` and `brain:*` steps then stop or skip with a message). `MAIND_BRAIN_VAULT` and
  `~/Vaults/Brain` are no longer read by maind; brain reads them.
- **skilldoc:** a root-bootstrap projection of skiller is recognised by `bucket: repository-bootstrap` and its "generated by `skiller registry`" line.
- **analyze:** `maind analyze` and the codegraph usage scan read run reports, codegraph summaries and analytics events through
  `analyst runs show|codegraph --json`; without analyst the source is reported `unavailable` (`PARTNER_UNAVAILABLE`,
  `PARTNER_FAILED` or `PARTNER_BAD_OUTPUT`) and the command still finishes. `maind.common` no longer re-exports `find_run_report*`.
- **Follow the task → planner rename:** the default command plugin of the audit is `planner`, and the plan convention block names the planner plugin.

### Removed
- **`scripts/cache-brain-docs.sh`** moved to the brain module (`scripts/cache-brain-docs.sh`); it finds `maind` through `$MAIND_BIN` or `PATH`.

### Fixed
- **`validate_config` — section `memory` didn't know about `digest`.** Key `memory.digest` (P1.1: `budget_chars`/`item_max_chars`/`shared_max`) existed in runtime since 0.3.0, but the validator scheme considered it unknown and warned on every `maind health`/CLI-call. Added to valid section keys.

## [0.3.0] — 2026-07-12

### Added

- **`select_digest_items` — digest-budget project-only + byte-cap.** Byte budget for digest
  memory + `shared_max=0` default (D10, supersede D5): cross-project (`ns:*`) facts in the digest are not
  are reached without an explicit request; config/CLI-flags `--shared-max` for point switching.
- **`session-start-hook.sh`/`memory-digest-hook.sh` — quiet health + template v2.** Health hook
  session no longer prints anything when OK (only `--strict` gives rc-gate); digest hook - compact
  template v2.
- **`doctor --context` — footprint fleet.** Fleet aggregation `_fleet_context`: subprocess `skiller
  budget --first-turn --json` for each `_enabled_projects` (without cross-imports), fail-soft
  `context: "n/a"` when unavailable.

### Added
- **`maind sync` — providers `plans-dir` and `plans-doc` (per-project plan-system).**
  Retroactive rolling plan-protocol for onboarded projects: `plans-dir` calling
  `harness hooks --plans-dir plans` (writes `plansDirectory` in `.claude/settings.json`
  project; key occupied by another value harness respects - skip), `plans-doc` inserts
  hashed-block `maind:plan-conventions` in CLAUDE.md project (`health.apply_plans_doc`
  according to the example `apply_health_doc`, template `templates/plans/conventions-block.md`,
  idempotent: repeat → `fresh/skip`). Opt-out one for both: `project.plans_dir="off"`
  (convention without rolled out plansDirectory is meaningless). Both are in the default set
  `--all`. Pilot end-to-end on azguard — 7/7 steps green. Known seam: JSON-result
  `plans-dir` on an idempotent repeat gives `changed=true` (the provider sees only rc
  subprocess'a harness) — honest `changed` requires rolling stdout from
  `run_capability`, deferred. Context: SKM-MASTER-003 P1.2/P1.3 (design A/C).
- **`analyze` — section «Efficiency» (run pathologies, Detect ≠ Gate).** New source
  `pathology_slice(run_report)` on top `core/pathology.py` (10 detectors: file-reread,
  tool-error-loop, no-op-run, no-verify, cache-miss, overthinking, retrieval-stuffing,
  protected-write, static-context, fanout): attention-finds go to `reasons` → verdict
  ATTENTION (the same mechanics as `pack_drift`), info-finds - in machine-readable
  `rep['efficiency']` and a human-readable section «Efficiency» before «RESULT». Invariant
  is captured in docstrings: RED never comes from pathologies. SCHEMA=1-reports - block
  silently lowers himself. +8 tests (`PathologyCase`). Context: SKM-MASTER-002 phase C.
- **`maind sync` — providers `skills-catalog` and `output-style`.** Retroactive distribution for already
  onboarded projects: `skills-catalog` (`skm:update` — re-resolving the skills catalog from disk,
  the new skill of the already selected bucket is rolled out without manual re-onboard) and `output-style`
  (`env:hooks --output-style lean`, opt-out `project.output_style: "off"`). Both are in default
  set `--all`, both use existing capability `skm:update`/`env:hooks` from
  `orchestrate.py` (none had a caller in `PROVISIONERS` before this). At the same time `skm:update`
  added to `DRY_CAPABLE` — honest `--dry-run` instead fake print+rc0.
- **Memory observability/graph in `analyze` + `maind memory count`.** Answers field question
  «memory/the graph is written - are they readable and helpful, or are they just eating tokens?». `analyze.py` reads new
  additive key `run_report.maind` (metrics MCP-memory calls/graph, they are counted by the paired parser
  run-report in harness): string «memory: recall×N→M · graph: query×K» + heuristic ATTENTION **«code graph
  was not used for heavy scanning»** (Read/Grep/Glob ≥30 with graph ×0) and «recall empty/not by
  address». New subcommand `maind memory count [--project|--scope] [--json]` — number of facts by scope
  (by scope-token, not the entire global pool). Skill `ecosystem-mcp` enhanced graph-first-hint
  (graph/Serena before wide `grep`, with a caveat about manual scanning). Tests: `test_analyze.py`/
  `test_memory.py` (+3). Back-compat: old `analyze` ignores the key `maind`, the new one does not crash without it.
- **`perplexity-web` — hub-managed MCP-server (rolling out from the config, not manually).** Keyless-bridge
  `perplexity-web` (separate Node-package) is distributed to projects by the same `deploy`/`sync`, what `maind`
  and Serena, — a single source of truth instead of manual hardcode entries in each `.mcp.json`
  (as it was with `swissknifeman`/`edufy`/`botkit`). Politics - section `mcp.perplexity_web` config:
  `enabled` (global fan-out; per-project override `perplexity_web: true|false`), `pool`
  (browser pooling model: generic literal like `default` — reuses the current login;
  `per-project` — pool=id; `per-namespace` — pool=`ns-<namespace>`; per-project override
  `perplexity_web_pool`), `bin` (fallback-path to `start.sh`, turns into an indirection
  `${PERPLEXITY_WEB_MCP_BIN:-<bin>}` — portable, no hard-skin `/home/...`). New resolver
  `pplxweb.py` (mirror `codegraph.py`), `PERPLEXITY_WEB_DEFAULTS` (disabled-by-default), entry in
  `deploy_project`/`mark_deployed` (`proj.mcp.perplexity_web`), fallback defaults in `merge_defaults`
  (only if section is specified). Repairs it at the same time «broken» `--pool=swissknifeman` (pool without login) →
  canonical `--pool=default` at the next deployment. Tests: `test_deploy.py` (+7, pool models and
  override). Caught onboarding via `field-feedback-loop`.

### Fixed
- **MCP-provisioning is resistant to broken sibling-channel.** Previously `load_mcp` on bit JSON one
  channel (e.g. `.cursor/mcp.json`) called `die()` and left **all** `maind sync`/`deploy` (although
  `.mcp.json` was valid). Now `load_mcp` raises `MCPConfigError`, a `deploy_project` catches
  him **per channel**: do not touch the broken file, print it warn and skip only this channel -
  other channels and fan-out projects are being worked on (`result["skipped"]`, visible in the output sync/deploy).
  Non-destructive merge of other people's servers (`merge_server` saves e.g. `playwright`/`laravel-boost`)
  as it was - added regression tests (`test_preserves_foreign_server_in_mcp_json`,
  `test_broken_channel_skipped_others_continue`, `test_broken_json_raises`). Caught in the field
  onboarding agelto via `field-feedback-loop`.

### Changed
- **Kernel quality by audit review (Perplexity)** — behaviorally neutral edits `lib/maind/`
  with checking each item by code (part of the audit observations was rejected as factually incorrect or
  contradictory `stdlib-only`; see `research/swissknifeman_audit.md`):
  - `sync.py`: single builder `_result(...)` — all providers return ONE result form
    (`provisioner/id/status/changed/state/detail`, all keys are always there), 9 inline-dictionaries consolidated
    to it; CLI no longer depends on `.get()`-defaults. Above `PROVISIONERS` — provider signature.
  - `health.py`: 3 almost identical hook-provider (`health`/`feature-log`/`memory`) reduced to
    to the general skeleton `_apply_script_hook(...)`; `json.loads(json.dumps())` → `copy.deepcopy()` (intent
    explicit, faster); `ok = lambda` → modular `def _status(...)` (E731).
  - `config.py`: `merge_defaults` — `copy.deepcopy` login (does not share nested objects with either input or
    with `CODE_GRAPH_DEFAULTS`); `Config.save()` validates the schema before writing (do not write spoiled
    state); `import difflib` raised to module level.
  - `constants.py`/`orchestrate.py`/`sync.py`: `SIBLINGS` moved to neutral `constants.py` —
    `sync._skiller_profiles_dir` doesn't do it anymore lazy-import `orchestrate` (fixed coupling-smell).
  - `fleet.py`: `extract_chunks` reads/joins the file once (and not per match); added
    warning when `>2000` chunks before O(N²)-comparison; comment clarified `_DECL_RE` (languages).

### Fixed
- **`fleet duplicates`/`similar`**: `jscpd` and external embedder are checked by `returncode` — real
  reason (no `npx`/network, backend error) gets into the message instead «no report file».
- **`load_json_db`**: when the file is broken in `warn` is now the full path to the backup `.corrupt.<date>`, and not
  name only (you can see where to look in `~/.maind/`).

### Tests
- Direct unit tests of previously indirectly covered pure utilities (refutation of clause 5.1 of the audit - there are tests,
  is the addition of spaces): `fleet._cosine` (identical/orthogonal/null vectors), `health._act`
  (matrix mode×state), `health._file_state` (absent/fresh/stale), `health._merge_session_hook`
  (idempotency, update by marker, login isolation via copy). +17 tests (267 → 284).

### Added
- **`onboard --skills-channel connect|vendor`** — selecting a channel for publishing skills on onboarding
  (applies to skills ONLY; memory/graph/MCP — as usual). `onboard` asks the channel interactively
  (as a memory mechanism), flag - for non-interactive (default `connect`); forwarding to `skiller integrate
  --skills-channel`. `vendor` → physical. copies of skills in `.claude/skills/` (for projects submitted
  to external developers without registry access swissknifeman). `swissknifeman setup` forwards the flag.
- **Subagent role packs (option A+C)**: 4 cross-stack person-pack in harness
  (`role-tech-lead`/`role-cto`/`role-founder`/`role-maintainer`, `shape:role`, without
  `stack.project_type`/`detect`). Delivery: `project.roles` in `config.json` → map `role_packs`
  (new TOP_KEY) mappit role → pack; `_resolve_agent_pack` (sync.py) adds role packs
  additive to the profile stack pack. Role-skills skiller received `role_agent_pack` in
  frontmatter; subtle selection of one role - through vendor.
- **Project setup decision tree** — canonical doc `docs/guide/onboarding-decision-tree.md`
  (10 layers with conditional branches: type → memory → namespaces → skill channel → buckets → environment →
  graph → agent-packs → brain → operation). Principle «optimal, not maximum; not obvious - ask».
- **Distributed-skill `ecosystem-setup`** — is rolled out into projects (like `ecosystem-mcp`) via new
  provider `setup-skill` (`skilldoc.apply_setup_skill`, in `sync` ORDER and in `onboard`). Delivers
  tooling decision tree, incl. to EXTERNAL repos, where governance-skills maind outside the scope. Substitution
  `{{TYPE}}` added.
- `onboard` no longer transmits `--profile standalone/unknown` in skiller — unrecognized type goes away
  in autodetect-fallback (minimum + warn), and not «puts everything».
- **Delivery of subagents by project type (hub → project)**: profile skiller calls
  `agent_pack` (string or list - composition), a `maind onboard`/`maind sync` deterministic
  roll out the pack(and) in `.claude/agents/` via `harness agent-packs render --auto` — WITHOUT agent in
  loop. New Provisioner `agent-pack` (10-th in `sync` ORDER), capability `env:agent-pack`/
  `env:agent-pack-upgrade` in orchestrate, step in onboard. `profile.model_tiers` pre-fill
  model agent shooting ranges.
- **Single project type detector in `core.project`**: `maind._infer_type` (×2) and
  `skiller.autodetect` reduced to one taxonomy (`core.detect_project_type`); `language_by_type`
  reaches out from `core.LANGUAGE_BY_TYPE`. Eliminated 3 divergent copies of the detector.
- `maind onboard` transmits `--profile <type>` in `skiller integrate` — selection of skills/presets/MCP
  goes by the type profile, and not just by bundle defaults.
- **Auto-load memory at the start of the session** (`maind memory digest` + SessionStart-hook):
  when `MODE=maind` onboarding puts `.claude/maind-memory.sh`, which injects the digest
  project memory into context Claude Code (`additionalContext`), and **disables native
  auto-memory** (`autoMemoryEnabled:false`). So the demon becomes a single source
  context - closes the hole «the daemon does not have auto-loading, the agent must remember about recall».
  Digest is deterministic (list+filter by scope-token, private scope first, fresh
  above), hook-safe (the demon lay down → quiet no-op). Rollback to native — `revert_memory_hook`.
- **Flexible choice of memory mechanism**: `maind onboard --memory maind|native|off` (default
  `maind`; online - checklist question). `native` returns auto-memory Claude Code.
  `maind health` checks consistency: `MODE=maind ⇒ native off + digest-injection in place`.
- **Provisioner `memory-hook` in `maind sync`** — memory auto-loading now rolls to
  already connected projects with one command (`maind sync --all --only memory-hook`), without driving
  full `onboard`. The intent is taken from `.claude/memory.env.ini` (`MODE=maind` → puts
  digest-injection + native off; `off` → revert on native; no config → pass). Included in
  default set `sync`, idempotent (drift by content-hash). Closes the gap: template
  hook already referenced this command, but the provider in `sync` was not there.

### Changed
- **Project memory is expanded only by the server `maind`** — raw MCP-server `agentmemory`
  is no longer deployed and is actively REMOVED from `.mcp.json` when `deploy`/`sync` (he wrote by
  scope-marker → entries are invisible to scoped-recall, footgun isolation). Legacy-return —
  `maind deploy --with-agentmemory`. Project status (`probe`/`health`) is now defined
  presence of a server `maind`, and not `agentmemory`. `mcpconfig.remove_server` — new helper.

### Docs
- **`guide/memory.md` rewritten to match the truth**: insulation - on the side maind (demon -
  single pool, `namespace`/`sessionId` ignores, `type` overrides; scope-marker in
  content), single path hook+MCP via `MODE=maind`, contract `forget {memoryId}`, check
  round-trip + troubleshooting, name collision removed `federation` (memory-files vs graph).
  `guide/federation.md` received a sidebar «not to be confused with memory». Skill `system/shared-memory`
  → 0.2.0 (canon `MODE=maind`, multi-namespace, membership by namespaces).

### Added
- **Onboarding auto-sweeps memory**: `maind onboard` brings up the memory wiring for already
  of the connected project - sets `namespaces` (default «general `axioma` + yours `<id>`»,
  `--namespace a,b` for several; clients - an explicit list without `axioma`) and writes
  `<project>/.claude/memory.env.ini` `MODE=maind`. Step `memwire` in the report.
- **`maind health` — round-trip memory**: sample write→recall→forget by temp-fact in
  private scope + checking that the hook is in mode `MODE=maind`. Catches the split (hook does not write
  in that side), broken forget and loss of insulation. `--strict` crashes on failure round-trip.
- **`maind memory remember|recall|forget` (scope-aware CLI)**: single recording path/read
  memory for man AND hook. scope is calculated from the project config via `namespaces.py`
  (`--project`/cwd/`--scope`): `remember` writes in private `project:<id>` (+ `--share`
  to general `ns:<tag>`); `recall` merges private + groups + `global` with grandfather.
- **ON-SIDE Memory Isolation maind**: agentmemory 0.9.x — single global pool, field
  `namespace` it ignores, `type` overrides (verified alive `curl`). Therefore maind
  embeds scope-marker `[[s:<scope>]]` into the content when writing and filters the results by
  him when reading (see `store`/`recall`, `mark_scope`/`split_scope`). Privacy and
  «general-by-tag» now actually work; `maind_memory_recall` (MCP) expands
  `project:<id>` to the full set recall-scope'ov.

### Fixed
- **`maind memory forget`**: payload now `{memoryId}` instead `{namespace, id}` —
  the previous version gave `HTTP 400` from agentmemory 0.9.x (verified alive `curl`), deletion
  didn't work. `FakeMemoryServer` in tests received `/agentmemory/forget` (by `memoryId`),
  test `test_memory_forget_deletes_by_id` proves round-trip store→recall→forget→gone.

## [0.2.0] — 2026-06-15

### Added
- **Count Federation**: graph **for the project** (`data/graphs/<id>.db`) + thin regenerable
  `_index.db` instead of a single `graph.db`. Cross-border request - federate-on-read (union stores).
  `graph_store: local` puts the store in the project repo itself.
- **Derive-engine**: graph is constructed from **sources of truth** (`composer.json`/`package.json`,
  Brain frontmatter, `<repo>/.maind.graph.json`, `skills-lock.json`) with plan mark (`via`),
  and not from a manual take. Teams `graph derive` / `graph rebuild` / `graph --project` / `graph --cross`.
- **Namespaces**: isolation of inter-project relationships by groups (`projects[].namespaces`) — inside
  groups common, isolated between groups; `["*"]` — general infrastructure. Applies to
  column (edge creation point), and to **memory** (buckets `ns:<name>`).
- **Namespace-memory parity**: scope-tier `ns:<name>` next to `project:<id>`/`global`; seed
  writes cross-ref about connections to group buckets; `maind_memory_links` gives away memory from all
  relevant buckets (`project:<id>` + `ns:<groups>` + `global`).
- **Healthcheck** (`maind health [--cwd|--project] [--fix] [--strict]`): status
  `connected|partial|standalone` + hints; delivery providers «priority №1» to projects
  (SessionStart-hook + managed block in `CLAUDE.md`).
- **Unified provisioning** `maind sync`: fan-out of managed artifacts to projects via the registry
  providers (`mcp` · `graph` · `memory` · `health-hook` · `health-doc`), modes
  `install|update|auto` with honest `changed` by content-hash; `deploy` = `sync --only mcp`.
- **Workspace trust** (`maind workspace sync|status`): trust Claude to ecosystem projects
  via `.claude/settings.local.json` (separate from allow/deny).
- **MCP harden+extend**: crash-resistant cycle (tool error → `isError`, server is alive),
  echo `protocolVersion`, stderr-logs, conformance-test for real spawn. **11 tools**
  (+`graph_path`, `graph_project`, `memory_forget`, `memory_links`, `projects_status`).
- **graphify** as a peer agent-memory link mechanism (graph **code** project),
  is rolled out separately MCP-server (`deploy --with-graphify`).
- Local skill `.claude/skills/maind-overview` + root `CLAUDE.md` (code map/convention).
- Guides: federation, namespaces, graphify, health, sync (ru-RU, with examples).

### Changed
- **The only graph layout is federation**: legacy-path `seed_*` (single `graph.db` from
  config) deleted; everything is built through `derive`. `graph.adapter` canonical
  `federation`/`disabled`; obsolete `memory`/`graphify`/`networkx` are accepted with
  warning and normalized to `federation`.
- Reading the graph - through a single façade `federation.graph_reader`.
- Documentation and `.maind.example.json` are adjusted to the current model; dead field removed
  `graph_node`; command `graph migrate-federation` has been removed.

### Performance
- Federation caches in-memory union within instance (read-only) — query/neighbors/path/
  stats are not rebuilt union for each call.

### Tests
- Coating `cli`/`doctor`/`constants` (26/26 modules), namespace-memory isolation,
  graphify-deployment, honest `changed` in sync. 166 → 189 tests.

## [0.1.0] — 2026-06-14

### Added
- Core on Python + bash (slim launcher `bin/maind` → `python3 -m maind`), stdlib-only.
- **Memory**: orchestration Node-demon `@agentmemory/agentmemory` (`memory start/stop/status`)
  + HTTP-wrapper with scope'ami (`store/recall/forget/export`), verified with real API
  agentmemory 0.9.x (`/agentmemory/remember` · `/agentmemory/search` · `/agentmemory/health`).
  Ports - from env/config, without hardcode.
- **Graph**: stdlib property-graph (`node/edge/neighbors/path/subgraph/stats`) with persistent
  in node-link JSON; `networkx`/`graphify` as optional adapters via `graph.adapter`.
  Auto-seeding of projects/connections from the config (`depends_on`/`uses`/`belongs_to`).
- **Agent Registry**: `register/heartbeat/list/kill/reap` (`~/.maind/agents.json`),
  state derivation `alive/stale/dead` from heartbeat + liveliness pid.
- **Project Registry**: `.maind.json` (superset brain `.projects.json`) + fallback on
  legacy with warning; `projects sync --from brain` (mapping of the real circuit brain).
- **MCP-server**: `maind mcp` — stdio JSON-RPC, 6 tools (memory/graph/agents/projects).
- **Migration**: `migrate from-brain` (config + graph), `migrate from-agentmemory` (iii-config).
- **CLI**: `start`, `status`, `doctor`, summary node status.
- `install.sh`, `.maind.example.json`, `.env.example`, `config/memory/iii-config.yaml`
  (service_name: maind), `scripts/test.sh`, `scripts/validate.sh`.
- Documentation (VitePress, ru-RU), 65 unit-tests (without a living demon - `FakeMemoryServer`).

[Unreleased]: https://github.com/academici/maind/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/academici/maind/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/academici/maind/releases/tag/v0.1.0
