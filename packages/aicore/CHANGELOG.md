# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- **`aicore schema compat` soundness:** a new `patternProperties` entry is graded breaking unless the old object was closed,
  had no patterns and no kept property can meet the pattern; properties covered by a pattern are compared with the pattern's
  schema; a `$ref` target used again with different sibling keywords is compared again; keywords next to a `$ref` are
  merged with the target as a validator applies them, and a changed overlap that cannot be merged is the breaking rule
  `ref-sibling-conflict`.
- **Config maps:** a map pattern that can consume a `.` (an escaped dot, a class with a dot, `\S`, a conditional) is refused,
  because such an entry name cannot be reached through dotted keys; a `propertyNames` schema must have `type` `string`.
- **Managed skill copies:** normalize a final `..` before checking containment, reject replacing the destination
  root, and fail closed on symlink loops. Rejected copies preserve sibling skills and files outside the root.

### Added
- **Events:** `aicore.ext.events` (`Event`, `build_event`, `emit`, `read_events`; `data` is limited to 65536 bytes of canonical
  JSON, a `Secret` in `data` is refused without printing it; `emit` raises only for a wrong call and otherwise warns and
  returns `None` unless `strict=True`) over `aicore.ext.journal`, the only writer of the append-only project journal
  (one `os.write` per event under an `flock`, `fsync`, a torn tail becomes a broken line of its own, readers see only
  complete lines of a size snapshot). After journaling, `emit` starts delivery in the mode of the call or of
  `events.delivery`: `background` (default), `sync` or `off`; a failing configuration or deliverer start is a warning.
- **Event delivery:** `aicore.ext.delivery` (`deliver`, `replay`, `delivery_status`, `spawn_background`,
  `resolve_subscriptions`). Subscriptions come from `unit.json` (`<module>:<id>`) and from `[aicore.subscriptions]` (a
  config entry may switch off or retime a module subscription, never replace its command; `projects` limits one to
  given roots). One deliverer per journal (`flock` on `ext/deliver.lock`, the automatic one gives way at once, the
  command waits up to 30 s) that re-checks the journal size after releasing the lock, so no wake-up is lost; per
  subscription a cursor in `ext/cursors.json` (atomic replace under the lock, at-least-once: subscribers are idempotent by
  event `id`), journal order, one attempt per event and pass, a failure stops the subscription until the next run, after
  `events.max_attempts` failures the event goes to `ext/dead-letter.jsonl` and the cursor moves on. Every attempt is a
  line of `ext/deliveries.jsonl`. A new subscription starts at the triggering event (else at the end of the journal); a
  cursor that no longer fits a journal changed by hand starts again with a `JOURNAL_RESET` record. Subscriber commands
  run through `run_json` in the cleaned environment with `SKM_PROJECT_ROOT`, `SKM_EVENT_JOURNAL`, `SKM_EVENT_SUBSCRIPTION`
  and `SKM_EVENT_ATTEMPT`; success is exit 0 with an empty stdout or `{"status": "ok"|"skipped"}`. Plugin subscribers
  report `PLUGIN_UNAVAILABLE` for now. Locks need `flock` (POSIX); network file systems without it are not supported.
- **`aicore.ext.settings`** (the `[aicore]` config section: delivery, subscriptions, plugins, overlays with the layer of each
  file) and **`aicore.ext.units`** (events, subscriptions, overlay slots and extension points declared in `unit.json`).
- **`aicore events emit|list`** (`--json`, `--project`, `--strict-type`): emulate and read events.
- **`aicore events deliver|replay|status`**: run a deliverer (exit 1 when a delivery failed), deliver again (`--from-start`,
  `--from-event ID`, `--event ID` for a dead letter) and show lag, pending attempts and dead letters per subscription.
- **`aicore.ext.process.run_json`**: runs a one-shot child with one JSON object on stdin and exactly one on stdout. A
  new session per child, one read/write deadline shared by all pipes (no `communicate()`), SIGTERM, a grace period and
  SIGKILL to the whole process group on timeout, a final SIGKILL to the group after the child exits, a 1 MiB stdout
  limit, a 2 KiB stderr tail and redaction of declared secrets in the tail (also JSON-escaped and percent-encoded
  spellings) and in the document. Every outcome is a
  `ProcessResult` with a `code` (`PROCESS_SPAWN`, `PROCESS_TIMEOUT`, `PROCESS_EXIT`, `PROTOCOL_STDOUT`,
  `PROTOCOL_STDOUT_TOO_LARGE`); only invalid arguments raise. A descendant that calls `setsid()` leaves the group and is
  not reached.
- **`aicore.ext.environment`**: `clean_environment` passes an allowlist (plus `LC_*`) and the `SKM_EXT_PROTOCOL` /
  `SKM_EXT_TRUSTED` markers; `permissions.env` and `env://` secrets from `permissions.secrets` only for trusted
  plugins (other schemes: `PLUGIN_SECRET_UNSUPPORTED`); `ignored_requests` lists what an untrusted plugin did not get;
  `effective_profile` reports `trusted-local` as not enforced and refuses `read-only` (`PLUGIN_PROFILE_UNAVAILABLE`).
- **Contracts of the extension layer**, all `development`: `event/v1` (a CloudEvents 1.0 subset; readers ignore unknown
  scalar extension attributes; no `project` field), `artifact-ref/v1`, `permissions/v1` (filesystem areas, network,
  secrets, shell, environment pass-through, sandbox profile), `extension/v1` (plugin manifest) and the plugin
  protocol `plugin-request/v1`, `plugin-response/v1`, `plugin-describe/v1`. Each ships valid and invalid examples;
  `common/v1` is now listed in `provides.contracts` too.
- **`unit/v1` additions** (minor): `subscribes` (default event subscriptions of a module, `<module>:<id>`),
  anchored patterns for `provides.events` (`<module>.<subject>.<verb>`), `overlay_slots` and `extension_points[].id`,
  and `permissions` as a `$ref` to `permissions/v1` (adds optional `env` and `profile`; `secrets` items must be
  `<scheme>://<name>`). `aicore schema compat --base HEAD` lists these as warnings and notes; every
  `packages/*/unit.json` stays valid.
- **`aicore.state.blobs`** (`put_bytes`, `put_json`, `read_bytes`, `blob_path`): a content-addressed store for the
  data an `artifact-ref/v1` points at, under the project state folder or the machine state folder; atomic writes, mode
  `0600`, digest and size checked on read (`BLOB_CORRUPT`).
- **Dictionary tables in module configuration.** A config schema may declare a *map*: an object with one anchored
  `patternProperties` key (no dots in names) whose entries are a single leaf or a table of leaves. Entries are
  created in config files (`[mod.map.name]`), merge by key across layers, take the leaf defaults when they appear,
  obey `x-skm-layers` per leaf, and work with `_unset` (a whole entry or one leaf), `_append`, flags,
  `aicore config set|unset`, `explain` and `config.example.toml` (a commented sample entry). Environment
  variables cannot address entries (one `CONFIG_ENV_UNKNOWN` warning). Schemas without maps behave as before.
- **`[aicore]` configuration section** (`configs/config.schema.json`, `provides.config`): `events.*` (delivery
  mode, subscriber deadline, attempts) and the maps `subscriptions`, `plugins` and `overlays`. What a machine
  runs (`run`, `plugin`, `on`, `projects`, manifests, `trusted`, timeouts) can be set only in the machine
  config, the invocation file and flags, never in a project file; a project may switch an entry off with
  `enabled = false` and add overlays. `config.example.toml` is generated from the schema.
- **`aicore schema compat`**: mechanical backward-compatibility check of the contract schemas
  (`aicore.util.schemacompat`: `compare`, `Change`, `RULES`). It compares the contracts of the working tree with the
  same contracts at a git reference (`--base`, default `HEAD`) inside one major version and reports 21 kinds of
  change; a change whose compatibility is not provable (`pattern`, `oneOf`) counts as breaking. A breaking change
  is an error (exit 1) for contracts that are `beta`, `rc`, `stable` or `deprecated` in `unit.json`, and a warning
  for `development` and `alpha`. `--json` prints one document; a missing git or a bad reference exits with 2.
- **Validator profile: `patternProperties` and `propertyNames`.** A dictionary keyed by identifiers is now a
  schema (`patternProperties` with anchored patterns and `additionalProperties: false`): a property is covered
  when it is listed or matches a pattern, and its value meets every schema that applies. `propertyNames`
  (`type`, `pattern`, `minLength`, `enum`, `description`) checks key names only (new issue code `property_name`)
  and does not make a key allowed. `load_contract` also loads the contracts that `$ref` names
  (`urn:swissknifeman:aicore:<contract>:v<N>`) from the neighbouring directories; existing contracts and module
  config schemas are unchanged.
- **`common/v1` contract**: shared `$defs` for other contracts to reference — `semver`, `module_id`, `relpath`,
  `argv`, `stability`, `extensions` (namespaced `<owner>.<name>` keys), `media_type`, `rfc3339_utc`.
- **`aicore.ext`** package (first piece: `ExtError(code, message)`, printed as `<code>: <message>`) and its layer
  in the architecture test: `ext` may use `util`, `state` and `config`; nothing below imports it.
- **`aicore <group>` dispatcher** (`aicore.cli`): `python3 -m aicore` picks the command group and imports it on
  demand; `aicore.config.cli.main` takes the arguments after `config`. Output and exit codes of
  `aicore config …` are unchanged.
- **`aicore.content.skill`**: the skill model moved in from the skill library — the files that never travel with a
  skill (`SKILL_IGNORE`), frontmatter reading (`read_frontmatter`, `read_frontmatter_fields`, `split_frontmatter`),
  the content hash (`skill_content_hash`, new `skill_digest`) and the transitive `requires` resolution
  (`resolve_requires_bfs`, `aggregate_dependency_diagnostics`). Bodies are unchanged, so every `content_sha256`
  stays the same.
- **`aicore.content.budget`**: the context-budget math moved in from the skill library — the token estimate
  (`estimate_tokens`, one formula for every consumer), skill and set budgets, the listing budget per provider, the
  typed measurement rows (`make_measurement`, `aggregate_measurements`), the first-turn source meters (agents,
  instructions, hooks, MCP) with the verdict and the text reports. `measure_mcp(target, *, host_servers=None)` takes
  the host-owned server data from the caller, so the foundation reads no host configuration. Numbers, thresholds
  and report text are unchanged.
- **`aicore.content.publication`**: the publication mechanics moved in from the skill library — the package
  prefix (`package_rel`), manifest serialisation (`manifest_bytes`, insertion order unless `sort_keys=True`), the
  cached distribution catalog and the publication capability gate, one whole-file artifact (`render_whole_file`,
  `capability_requirements`), the Codex `plugin.json` and marketplace entry, the publication lock record and the
  runtime-file walk of a skill tree with its containment check (`skill_runtime_files`, `contained`). Artifact ids,
  adapter identities and provenance parameters stay with the caller, so generated bytes and hashes are unchanged.
- **`aicore.content.commands`**: the part of the command projection that every provider runtime shares —
  strict frontmatter (`strict_frontmatter_fields`), the description line (`frontmatter_description`, error prefix
  as a parameter), the fence split of a canonical command (`split_command`) and the generated-runtime header
  (`runtime_provenance`). Error texts are unchanged. The command catalog, routing and wrapper texts stay with the
  projecting module.
- **`aicore.content.eval`**: skill evaluation moved in from the skill library — the deterministic grader, the
  evals/pressure/triggers validators, the benchmark builders, the `claude -p` runner, the system-bank adapter, the
  report viewers and the scaffold. The `skiller eval` command and the registry lookup stay in the skill library.
- **`eval-context/v1` contract** with `eval_context`, `skill_eval_context`, `runner_context` and
  `compare_eval_context`: a result states the skill digest, the fixtures digest and version, the grader version
  and the runner (CLI version from `--version`, models from `modelUsage`); values not observed are null or `[]`.
  Two results are comparable when `compare_eval_context` returns no paths. Skill benchmarks are now
  `skill-benchmark/v3` and the system bank `system-bank-benchmark/v2`; both add `context`, every other key is
  unchanged, and the report prints a `Context:` line.
- **`skill-descriptor/v1` contract** with `SkillDescriptor` and `describe_skill`: identity, content digest, the
  optional fields of the Agent Skills standard (`license`, `compatibility`, `allowed-tools`, `metadata`),
  `adapters`, `requires`, `risk` and provenance from `upstream.json`; read-only, an absent value is null or empty.
- **Subpackages `aicore.content`, `aicore.delivery`, `aicore.release`** with their layering rule in
  `tests/test_architecture.py`: content imports util, provider, artifacts and config; release imports util and content;
  delivery imports everything below it; the older subpackages import none of the three.
- **`aicore config` command line** (`bin/aicore`, `python3 -m aicore`): `show`, `explain` (text and the
  `config-explain/v1` JSON), `set`, `unset`, `init`, `example` and `paths`. Writes go through the comment-keeping
  editor with a backup and an atomic replace; `init` and `example --write` never touch an existing hand-made file
  without `--force`. Exit codes: 0 success, 1 configuration error or refusal, 2 usage error.
- **Module discovery and example generation** (`aicore.config.units`, `aicore.config.example`): modules with
  `provides.config` are found through `SKM_UNITS_PATH` or the folder holding the foundation, and a deterministic
  `config.example.toml` is rendered from each schema.
- **Locator fragment** `scripts/aicore-locator.sh`: the one canonical way for a wrapper or test runner to find
  `aicore` (`AICORE_ROOT`, `_vendor/aicore`, sibling), with `AICORE_NOT_FOUND` and exit code 2 on a miss.
- **README** with the layout, subsystems, locator, compatibility shim, contracts and tests, and a section on
  configuration and state: places and `SKM_HOME`, layers, merging, environment, secrets, the command line, the
  vendored `tomli` and the TOML 1.0 rule.
- **Shared code moved in from the root `core/` package** (history preserved): `aicore.util` (block, cli, env, http,
  io, paths, proc, project, repo, term, text), `aicore.provider` (the provider model and its catalogs),
  `aicore.artifacts` (artifact rendering, locking and reconciliation) and `aicore.usage`. There is no flat facade;
  import the subpackages directly. The root `core/` package stays as a transitional alias layer.
- **Provider data ships with the package**: `configs/provider-{capabilities,distribution,projection}.json`, found
  from the package file (`aicore.provider.data.config_path`); `aicore.provider.manifest.default_manifest_path()`
  replaces hard-coded repository paths in consumers.
- **`scripts/test.sh` and `scripts/validate.sh`**: the module tests and the fast structural checks run on their own,
  without any other module.
- **`digest/v1` contract and `aicore.util.digest`**: canonical JSON bytes and the tagged SHA-256 digest with
  language-neutral test vectors (`schemas/digest/v1/vectors.json`). `aicore.artifacts.artifact`,
  `provider.control_plane` and `provider.health` use it instead of their own copies; the digests they produce are
  unchanged for the values they hash. Floats and non-string object keys are now rejected everywhere.
- **Provider contracts**: `error/v1`, `capability-support/v1` and `model-catalog/v1` with examples.
  `aicore.provider.errors` has the twelve failure classes, `ProviderError` and `classify_failure`, which classifies
  by the rules of `configs/provider-errors.json` and never copies provider text into a record;
  `aicore.provider.models` reads `configs/model-catalog.json` (`load_model_catalog`, `select_model`,
  `select_effort`, `inventory`); `SupportSource` and `AvailabilityDimension` join `provider.values`. A test keeps the
  provider layer free of waiting and retry code.
- **`aicore.util.schema`**: the closed-profile JSON Schema validator, with `load_contract` for a
  `<contract>/v<N>/` directory; `scripts/ecosystem-units.py` validates all aicore contracts with it.
- **Architecture tests**: `aicore` imports only itself and the standard library; `usage.py` stays self-sufficient.
- **`aicore.state`**: the standard places for configuration and state. `machine_locations` resolves the XDG
  config/state/data/cache directories (a relative `XDG_*` value is ignored); an absolute `SKM_HOME` moves all four
  under one directory and switches off every legacy lookup, so sandboxes and tests never read the real home.
  `project_*` helpers name `.swissknifeman/{config.toml,state,backups}` and `find_project_root` finds the project.
  `resolve_with_legacy` prefers the new place, falls back to an existing legacy path with one warning per process
  and never copies or removes anything. `backup` and `list_backups` keep timestamped copies below
  `.swissknifeman/backups` (or the machine state directory) and rotate only stamp-named directories.
- **`aicore.MIN_PYTHON = (3, 9)`**, the single minimum Python version, and a test that parses every module with the
  3.9 grammar; the architecture test also checks the layer of `state` (only `util`).
- **`aicore.config` (first part): TOML reading and editing.** `config.toml` reads with `tomllib` on Python 3.11+ and
  with the vendored `tomli` 2.3.1 (`aicore/_vendor`, byte-for-byte from the pure wheel, pinned by hash in
  `VENDORED.json`, covered by an integrity test) before that, so a file means the same on 3.9 to 3.13. A syntax error
  becomes `ConfigError("CONFIG_FILE_INVALID")` with the file and the line; `LineIndex` maps key paths to lines.
  `config.toml_edit` sets or removes one leaf value, keeps comments, indentation and every other line, refuses
  dotted keys, inline tables, arrays of tables and multi-line values with a hint to edit by hand, and parses its
  own result and compares it with the expected document before returning it. Architecture tests keep the TOML
  import in `config/toml.py` only and the `config` layer on `util` and `state`.
- **`aicore.config`: layered module settings.** `resolve(module, ...)` applies defaults (the `default` of the module's
  `configs/config.schema.json`), the machine file, the project file `.swissknifeman/config.toml`, module-specific extra
  layers, `SKM_<MODULE>_<PATH>` environment variables (`__` between path segments, parsed by the key's type; unknown
  paths warn once), a `--config FILE` layer and flags, in that order. Files carry `schema_version = 1` and a `[module]`
  table; a layer may reset keys with `_unset = ["a.b"]` and extend arrays with `_append = {"a.b" = [...]}`, tables
  merge, arrays and scalars replace, and `x-skm-layers` forbids a key in other layers. Unknown keys, wrong types and
  ranges, a missing, newer or invalid version and forbidden layers are errors (`ConfigError` with a code, layer, file
  and line). `ResolvedConfig` gives `get`, `as_dict`, `secret` and `explain` (layer, file, line, source and the
  overridden values of each key; text and the `config-explain/v1` JSON). `edit_layer_file` changes one key of a
  layer file: it checks the result against the schema, backs the old file up and writes atomically, leaving the file
  untouched on any error.
- **Secret references.** A key marked `x-skm-secret` holds only a reference (`env://NAME` is built in;
  `register_secret_resolver` adds schemes). `Secret` shows `***`, cannot be pickled and looks the value up on
  `reveal()` without keeping it; errors on a secret key never contain the value, and a failed lookup is reported as
  `SECRET_UNRESOLVED` with no chained cause. A test checks `explain` output, `repr`, error text and full
  tracebacks for a marker value.
- **`config-explain/v1` contract** with valid and invalid examples.
- **`aicore.util.schema`** accepts `minimum` and `maximum` (issue codes `minimum`, `maximum`) and the annotations
  `x-skm-secret` and `x-skm-layers` (ignored by validation); every other `x-*` keyword still fails the profile.
  `load_schema_file` loads one schema file under the profile.
- **`aicore.delivery`**: how skills and plugins reach Codex, Claude Code and a project. `MARKETPLACE` names the
  ecosystem marketplace. `codex` plans and applies the explicit Codex plugin selection in a project
  `.codex/config.toml` (comments, foreign tables and line endings stay byte for byte) and reads what the installed
  Codex discovers; `claude` lists the enabled marketplace plugins with their always-on price, redacts a settings
  preview (`redacted_settings_preview`) and merges the marketplace source and the plugin switches into a settings
  mapping (`enable_marketplace_plugins`, a pure function that returns the notes to print); `distribution` plans the
  vendor path and the marketplace channel of each provider, including the self-contained Codex bundle checked
  against the artifact lock, and runs the explicit native Codex install. The caller selects the providers and
  passes the identities that appear in generated provenance (`DistributionIdentity`), so artifact ids, adapter
  identities and bytes do not change.
- **`aicore.delivery.materialize`**: the managed skill copies a project receives, moved in from the skill library —
  the managed marker after a skill's frontmatter (`mark_skill_managed`, `strip_skill_managed_marker`), the
  contained copy of a skill directory (`safe_copy_skill`: refuses a path outside the destination, never follows a
  symlink, rechecks after removal), the manifest writer (`write_skill_manifest`), the `skills-lock.json` reader,
  validator and writer (`load_lock`, `lock_problem`, `write_lock`) and `sync_skillset`, which applies a computed plan
  (add, update, remove, keep, conflicts, drift repair) and writes the lock, the manifest and the optional
  `.gitignore` of the managed copies. Choosing the skills and planning stay with the caller: `sync_skillset` takes
  the plan, or a `planner` that makes it. Formats, marker and report counts are unchanged.
- **`aicore.release`**: release identity and rules moved in from the skill library — the attestation of a release
  (`attestation`: tagged digests, the release-unit policy, `build`, `check`, `check_transition`, `version_errors`),
  the version rules (`version`: last tag, commits since it, the semver bump with no MAJOR, the next free version,
  the version files of a host) and the changelog format (`changelog`: the Unreleased section, its move under a
  version, `parse_released` with the heading grammar). The location of the package that owns the publication-version
  map is the `package_root` parameter of `build` and `check` (none means no prefix), so the foundation names no
  package. Digests and attested bytes are unchanged.
- **Documentation:** the README describes `content`, `delivery` and `release` and the two new contracts; the
  architecture documents carry ADR 0037 to 0039.

### Changed
- **The gitignore policy moved into `aicore.state.gitignore`** (history preserved) and its data to
  `configs/gitignore-policy.json` of this package, found from the package file. The policy gains `project-config`
  (`.swissknifeman/config.toml`, committed) and `swissknifeman-state` (`.swissknifeman/state/`, ignored).
  `core.gitignore_policy` stays as an alias of the same module object.
- **Codex plugin selection reads the full TOML on every Python.** On Python before 3.11 it used a reduced parser that
  refused any table other than the plugin and skill tables; it now uses `aicore.config.toml.loads` like Python 3.11+
  and a project `.codex/config.toml` with other tables is accepted. A syntax error is a `ValueError` (`ConfigError`)
  that names the file.
- `scripts/test.sh` unsets `SKM_HOME`, `XDG_*_HOME` and `SKM_UNITS_PATH` before running the tests.
- `aicore.util.paths.state_dir` is documented as a legacy location (new code uses `aicore.state`).

### Removed
- `core.config_paths` and `shared_config_path` (the gitignore policy was the only user).
