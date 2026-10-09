# aicore

The shared foundation of the swissknifeman modules. Every module depends on `aicore` and on nothing else
(see `requires` in its `unit.json`); `aicore` depends on no module and on nothing but the Python standard library
(Python 3.9 or later).

## Layout

```text
packages/aicore/
  unit.json  README.md  CHANGELOG.md
  bin/aicore                           # command line: `aicore config|events|ext|schema ...`
  configs/       provider-{capabilities,distribution,projection,errors}.json  model-catalog.json  gitignore-policy.json
                 config.schema.json  telemetry-conventions.json
  lib/aicore/    util/  provider/  artifacts/  state/  config/  content/  delivery/  release/  ext/  usage.py  cli.py  _vendor/tomli/
  schemas/       <contract>/v1/  and README.md
  scripts/       test.sh  validate.sh  aicore-locator.sh
  tests/         util, io, text, usage, contracts, architecture, vendor; provider/, artifacts/, state/, config/, content/, delivery/, release/ and ext/
```

`lib/aicore/__init__.py` carries only the version; there is no flat facade. Import the subpackages directly.

## Subsystems

| Subsystem | Holds | Used by |
| --- | --- | --- |
| `aicore.util` | atomic write, paths, text, terminal, CLI and processes, HTTP, repository root, managed blocks, project type, `digest` (canonical JSON and tagged SHA-256), `schema` (closed-profile JSON Schema validator) | all modules |
| `aicore.provider` | provider capability manifests, configuration layers, control plane, health, adapter registry, request lifecycle, `errors` (failure classes and classification by data), `models` (model catalog); data in `configs/` found from the package file (`provider.data.config_path`, `manifest.default_manifest_path()`) | harness, maind, planner, orch, skiller |
| `aicore.artifacts` | plan, apply and lock of artifacts in projects, reconcile | skiller, harness, maind |
| `aicore.state` | standard machine and project places (`SKM_HOME`, XDG, `.swissknifeman/`), legacy lookup, timestamped backups with rotation, the gitignore policy | `aicore.config`, all modules |
| `aicore.config` | module settings from layers (`resolve`): schema defaults, machine file, project file, extra layers, environment, `--config` file, flags; `explain` (origin of every value), secret references (`Secret`, `register_secret_resolver`), `edit_layer_file` (comment-preserving write with backup); module discovery and `config.example.toml` generation; the `aicore config` CLI; the one TOML entry (`toml`, `toml_edit`) | all modules |
| `aicore.content` | what a skill or command is and what it costs: `skill` (frontmatter, content hash and `skill_digest`, `describe_skill` for `skill-descriptor/v1`, transitive `requires`), `budget` (the one token estimate, skill, set and listing budgets, first-turn meters and verdict), `publication` (manifest bytes, whole-file artifacts, Codex plugin manifest and marketplace entry, publication lock, runtime-file walk), `commands` (the shared part of command projection), `eval` (grader, validators, benchmarks, `claude -p` runner, `eval-context/v1`) | skiller, harness, planner |
| `aicore.delivery` | how skills and plugins reach a project: `codex` (explicit plugin selection in `.codex/config.toml`), `claude` (enabled marketplace plugins and their price, settings merge), `distribution` (vendor and marketplace plans per provider, Codex bundle, native install), `materialize` (managed skill copies, marker, manifest, `skills-lock.json`, `sync_skillset`) | skiller, hub |
| `aicore.release` | `attestation` (tagged digests, release-unit policy, `build`, `check`, `check_transition`), `version` (last tag, semver bump, next free version, version files), `changelog` (the Unreleased section, `release_changelog`, `parse_released`) | skiller, hub scripts |
| `aicore.ext` | events and their journal, delivery to subscribers, external plugins, instruction overlays, plugin conformance (see [Extensions](#extensions-aicoreext)); `aicore.util.schemacompat` and `aicore.util.telemetry` belong to `util` | planner, orch, brain, analyst, harness |
| `aicore.usage` | one accumulator of tokens parsed from provider logs; self-sufficient, so it can be vendored byte for byte | analyst, harness, skiller |

### Layers inside aicore

Managed skill copies require a destination strictly below the skills root. The path gate normalizes a final
`..`, permits replacing a leaf symlink without following it, and refuses parent symlink escapes and resolution
errors. It also refuses replacing the root itself, which would delete other installed skills.

`ext` imports `util`, `state` and `config`, and no older subpackage imports `ext`; `content` imports `util`, `provider`, `artifacts` and `config`; `release` imports `util` and `content`; `delivery`
imports everything below it; the older subpackages import none of the three (`tests/test_architecture.py`). The three
take their data from the caller as explicit parameters (the package that owns the publication versions, the identities
in generated provenance, the host-owned MCP servers), so the foundation names no library and reads no host
configuration.

## Configuration and state

Settings of a module come from layers and are read only through `aicore.config.resolve(module, ...)`; a module never
parses `config.toml` itself. Places come from `aicore.state`.

### Places

| What | Default | With `SKM_HOME=<dir>` |
| --- | --- | --- |
| machine config file | `$XDG_CONFIG_HOME/swissknifeman/config.toml` (`~/.config/...`) | `<dir>/config/config.toml` |
| state (registries, machine backups) | `$XDG_STATE_HOME/swissknifeman` (`~/.local/state/...`) | `<dir>/state` |
| data | `$XDG_DATA_HOME/swissknifeman` (`~/.local/share/...`) | `<dir>/data` |
| cache | `$XDG_CACHE_HOME/swissknifeman` (`~/.cache/...`) | `<dir>/cache` |
| project config (in git) | `<project>/.swissknifeman/config.toml` | same |
| project state, backups (ignored) | `<project>/.swissknifeman/{state,backups}/` | same |

`SKM_HOME` isolates a sandbox or a test: all four machine places move under it and no legacy location is read. It
must be an absolute path; a relative `XDG_*` value is ignored. A file that exists only at an old location
(for example `~/.swissknifeman/analyst`) is still read, with one warning per process; nothing is copied or removed
until `swissknifeman upgrade`. Before a write the old file is copied to `.swissknifeman/backups/<UTC stamp>/` (machine
files: to the state directory), and the newest ten copies are kept. `aicore config paths` prints the resolved places.

### Layers and merging

From low to high: schema `default`, machine file, project file, a module's own extra layers, environment,
`--config FILE`, flags. Each file starts with `schema_version = 1` and holds one `[<module>]` table:

```toml
schema_version = 1

[analyst.recompute]
candidate_min_n = 25
```

Tables merge key by key; arrays and scalars of a higher layer replace the lower value. In a file layer
`_unset = ["recompute.candidate_min_n"]` returns a key to its default (or removes it), and
`_append = {"some.list" = ["x"]}` extends an array instead of replacing it. A key cannot be both set and appended in
one layer. A schema may restrict a key to some layers (`x-skm-layers`), for example to keep machine paths out of a
project that is committed. Unknown keys, wrong types, ranges, a missing or newer `schema_version` and forbidden layers
are errors that name the layer, file, line and key.

Environment variables are `SKM_<MODULE>_<PATH>`: upper-case module id, `-` as `_`, path segments joined by `__`, for
example `SKM_ANALYST_RECOMPUTE__CANDIDATE_MIN_N=30`. The text is parsed by the type of the key (booleans:
`true|false|1|0|yes|no`; arrays: a JSON array). An unknown path under a known module warns once.

Config files are TOML 1.0. `tomllib` of Python 3.15 or later also accepts TOML 1.1, which Python 3.9 to 3.14 cannot
read, so do not use 1.1 syntax in a shared file.

### Secrets

A key marked `x-skm-secret` in the schema holds a reference, never the secret: `env://NAME` reads the environment
variable `NAME`. Other schemes are registered with `register_secret_resolver`. A plain value in such a key is an error
whose text does not repeat it. `ResolvedConfig.secret(key).reveal()` looks the value up at the call; the value is not
shown by `show`, `explain`, `repr`, error messages or tracebacks.

### Command line

```text
aicore config show <module>                          resolved values and their layers
aicore config explain <module> [key] [--json]        origin of each value; --json is config-explain/v1
aicore config set <module>.<key> <value> --machine|--project
aicore config unset <module>.<key> --machine|--project
aicore config init --machine|--project [--module ID ...] [--force]
aicore config example <unit-dir> [--write|--check]   config.example.toml of a module
aicore config paths [--json]
```

`swissknifeman config ...` is the same command. `--root DIR` names the project, `--config FILE` adds the invocation
layer. `set` and `unset` change one line with the comment-keeping editor, check the result against the schema and
back up the file first; dotted keys, inline tables and multi-line values are refused with a hint to edit by hand.

Example run in a sandbox (`scripts/dev-sandbox.sh`), with the machine file setting 20 and the project file 25:

```text
$ aicore config set analyst.recompute.candidate_min_n 25 --project
$ aicore config explain analyst recompute.candidate_min_n
recompute.candidate_min_n = 25
  from project <project>/.swissknifeman/config.toml:4
  overrides machine <home>/config/config.toml:4 = 20; defaults = 15
$ aicore config set analyst.recompute.candidate_min_n 0 --project
aicore config set: <project>/.swissknifeman/config.toml:4: project: recompute.candidate_min_n: 0 is less than the minimum 1 [CONFIG_TYPE]
```

Every module with a `provides.config` entry in `unit.json` ships `configs/config.schema.json` and a generated
`config.example.toml`; `scripts/ecosystem-units.py check` fails when the example drifts.

### Vendored tomli

Before Python 3.11 the files are read by `aicore/_vendor/tomli` (tomli 2.3.1, MIT, copied byte for byte from the
pure wheel; hashes in `VENDORED.json`, checked by `tests/test_vendor.py`). 2.3.x implements TOML 1.0 like `tomllib`
of Python 3.11 to 3.14, so a file reads the same on 3.9 to 3.14. Never edit the vendored files; to update, take the
new wheel, check its hash and write a new `VENDORED.json`. Decisions: ADR 0034 to 0036 in `docs/architecture`.

## Finding aicore

Wrappers and test runners of the modules find `aicore` with one canonical fragment,
`scripts/aicore-locator.sh`, copied verbatim between the markers `# --- aicore locator ---` and
`# --- end aicore locator ---`. The order is:

1. `$AICORE_ROOT`; when it is set and is not an `aicore` checkout, the fragment fails and does not look further;
2. `<module>/_vendor/aicore`;
3. the sibling `<module>/../aicore` (inside the hub repository only).

A candidate qualifies when its `unit.json` has `"id": "aicore"`. The fragment exports `AICORE_ROOT` and
`AICORE_LIB=$AICORE_ROOT/lib`, which the wrapper puts on `PYTHONPATH`. When nothing is found it prints
`AICORE_NOT_FOUND` with the hint to set `AICORE_ROOT` and exits with code 2.

## Compatibility shim

The root `core/` package is a transitional alias layer. Its `__init__.py` makes `aicore` importable (using
`AICORE_ROOT`, otherwise the sibling `packages/aicore/lib`) and registers every moved module under its old name as
the same module object (`core.io` is `aicore.util.io`, `core.provider.lock` is `aicore.artifacts.lock`), and keeps
the old flat `core.__all__`. The window lasts until `core/` is removed, when the hub modules move onto `aicore`.
New code imports `aicore`, never `core`. A test checks that every alias is the same object and that the facade is
unchanged.

## Contracts

All contracts are JSON Schema draft 2020-12 in the closed profile, with valid and invalid examples; the schema is the
source of truth and the code implements it. The layout rules and the full table are in `schemas/README.md`.

| Contract | Implementation |
| --- | --- |
| `unit/v1` | manifest of a module (`packages/<id>/unit.json`); checked by `scripts/ecosystem-units.py` |
| `check-result/v1` | result of one diagnostic check |
| `digest/v1` | `aicore.util.digest`; test vectors in `schemas/digest/v1/vectors.json` |
| `error/v1` | `aicore.provider.errors`; rules in `configs/provider-errors.json` |
| `capability-support/v1` | `SupportLevel`, `SupportSource`, `AvailabilityDimension` in `aicore.provider.values` |
| `model-catalog/v1` | `aicore.provider.models`; data in `configs/model-catalog.json` |
| `config-explain/v1` | `aicore.config.ResolvedConfig.explain_json` |
| `skill-descriptor/v1` | `aicore.content.skill.describe_skill`; fields of the Agent Skills standard plus digest and provenance |
| `eval-context/v1` | `aicore.content.eval.eval_context`; skill digest, fixtures, grader and runner, compared with `compare_eval_context` |
| `common/v1` | shared `$defs` (`semver`, `module_id`, `relpath`, `argv`, `stability`, `extensions`, `media_type`, `rfc3339_utc`) that other contracts reference |
| `event/v1` | `aicore.ext.events`; a CloudEvents 1.0 subset |
| `artifact-ref/v1` | pointer to data too large for an event; the store is `aicore.state.blobs` |
| `permissions/v1` | one vocabulary of declared permissions for `unit.json` and `extension.json` |
| `extension/v1` | manifest of an external plugin (`extension.json`) |
| `plugin-request/v1`, `plugin-response/v1`, `plugin-describe/v1` | the plugin protocol, version `1` |
| `telemetry-conventions/v1` | `aicore.util.telemetry`; data in `configs/telemetry-conventions.json` |

## Extensions (`aicore.ext`)

Extensions let a module react to another one without importing it ([ADR 0006](../../docs/architecture/decisions/0006-extensibility-events-subscriptions-overlays.md),
[ADR 0016](../../docs/architecture/decisions/0016-extension-model-levels-and-trust.md)). Everything here is out of
process: a subscriber or a plugin is a command that gets one JSON object on stdin and answers with one on stdout.

### Events and the journal

`aicore.ext.emit(type, data=..., ...)` builds an `event/v1` (CloudEvents 1.0 subset: `specversion`, `id`, `source`,
`type` as `<module>.<subject>.<verb>`, `time`, optional `subject`, `data`, and the extension attributes `traceparent`,
`causationid`, `correlationid`) and appends it to `<project>/.swissknifeman/state/events.jsonl`. `data` is at most 65536
bytes of canonical JSON (larger data goes to `aicore.state.blobs` and is referenced by `artifact-ref/v1`); a `Secret` in
`data` is refused. The journal has one writer (`aicore.ext.journal`): one `os.write` per event under an `flock`, then
`fsync`; readers see only complete lines. `emit` raises only for a wrong call (type, `data`, size, `Secret`); a failed
journal write is a warning and `None`, a failing configuration or delivery start still returns the stored event with a
warning (`strict=True` raises both). `aicore events emit|list` emulates and reads events.

### Delivery and its guarantees

After journaling, `emit` starts delivery in the mode `events.delivery`: `background` (default; a one-shot deliverer in
its own session), `sync` or `off`. Guarantees:

- Delivery is from the journal only; each subscription has a cursor in `ext/cursors.json` (offset and last event `id`).
- At-least-once: a subscriber must be idempotent by event `id`.
- Journal order per subscription, one attempt per event and pass; a failure stops that subscription until the next run.
- After `events.max_attempts` (default 3) failures the event goes to `ext/dead-letter.jsonl` and the cursor moves on; every
  attempt is a line of `ext/deliveries.jsonl`.
- One deliverer per journal (`flock` on `ext/deliver.lock`); the journal size is re-checked after releasing the lock, so
  no wake-up is lost.
- A subscriber failure never breaks the source.

```text
aicore events emit --source MODULE --type TYPE [--subject TEXT] [--data JSON | --data-file FILE] [--delivery MODE] [--strict-type] [--json]
aicore events list [--type PATTERN] [--since ID] [--limit N] [--json]
aicore events deliver | replay SUBSCRIPTION (--from-start | --from-event ID | --event ID) | status
```

### Subscriptions

A subscription is `on` (a list of event type patterns, shell-style wildcards) and `run` (an argv) or `plugin` (a registered plugin id). It comes from the
`subscribes` field of a `unit.json` (id `<module>:<name>`) or from `[aicore.subscriptions.<id>]` in the machine
config. Configuration may switch a module subscription off (`enabled = false`) or retime it, never replace its command.
The command runs in the cleaned environment with `SKM_PROJECT_ROOT`, `SKM_EVENT_JOURNAL`, `SKM_EVENT_SUBSCRIPTION` and
`SKM_EVENT_ATTEMPT`; success is exit 0 with an empty stdout or `{"status": "ok"|"skipped"}`.

### External plugins and the protocol

A plugin is a folder with an `extension.json` (`extension/v1`; kinds `command` and `subscriber`), registered in the machine
config under `[aicore.plugins.<id>]`. `aicore.ext.plugins.load_manifest` checks the manifest before anything runs
(schema, entrypoint inside the folder, protocol range against the host's `1`, required contracts, permission profile).
Then the plugin is started with a `plugin-request/v1` of `op` `describe` (the host adds `protocol`, `request_id`, `deadline_ms` and `context`).
Its `id`, `version`, `kind` and `capabilities_digest` (digest of `provides`) must equal the manifest and its `protocol`
must lie in the range shared by the manifest and the host; only then `invoke` (a point a module declared in
`extension_points`, through `invoke_point`) or `event` is sent. There is no cache: every use describes again. Protocol
`1` is stdio JSON: one request in, exactly one JSON object out, logs on stderr only. Answers are validated as
`plugin-response/v1`. Failures carry a code such as `PLUGIN_UNAVAILABLE`, `PROTOCOL_UNSUPPORTED`, `PROCESS_TIMEOUT` or
`PROTOCOL_STDOUT`.

```text
aicore ext plugins list | describe ID | invoke POINT [--input JSON | --input-file FILE]
aicore ext status [--json] [--project DIR]        # always exits 0; the doctor probe of aicore.ext
```

### Trust and limits

`aicore.ext.process.run_json` runs a child in a new session with one deadline for all pipes, SIGTERM to the group, a 2 s
grace, SIGKILL to the group, and a final SIGKILL to the group after the child exits; stdout is limited to 1 MiB, the
stderr tail to 2 KiB, with declared secrets replaced by `***`. The environment is cleaned to an allowlist. A plugin the
machine config marks `trusted` receives the environment names and `env://` secrets its manifest declares; an untrusted
one receives neither, and `aicore ext status` lists what it did not get. Only the machine config, the `--config` invocation file and flags can define what
runs (`run`, `plugin`, `manifest`, `trusted`, `on`, `projects`, timeouts); a project file in git may only switch an entry off and
add overlays.

Known limits, each with the trigger that ends it:

| Limit | Trigger to lift it |
| --- | --- |
| A descendant that calls `setsid()` leaves the process group and is not contained (conformance detects it); no cgroup or Landlock yet | third-party plugins |
| The profile `trusted-local` is reported with `enforced: false`; the profile `read-only` is unavailable (`PLUGIN_PROFILE_UNAVAILABLE`) | third-party plugins |
| `flock` is required: network file systems without it are not supported | a user on such a file system |
| `events.jsonl` has no rotation | a journal above 50 MB or a complaint about its size |
| No describe cache | a plugin call on a hot path |
| No `secret-resolver` plugin kind (`register_secret_resolver` is open) | the first external secret store |
| No retry by timer: a failed delivery is retried at the next deliverer run | delivery needed without a next `emit` or a manual `deliver` |
| No long-lived JSON-RPC, magic cookie or framing | a plugin with state or on a hot path |
| In-process (entry points) and remote extensions | pip packaging of modules; distributed execution |

### Overlays

A module declares a slot `<module>:<name>` in `provides.overlay_slots`. Files for the slot are listed under
`[aicore.overlays."<module>:<name>"]` and read in layer order (a layer replaces the array, `_append` extends it;
relative paths are taken from the file of the layer). `resolve_overlays` returns the texts; `render_overlays` returns one
block between `<!-- overlays: SLOT -->` and `<!-- end overlays: SLOT -->` that a command appends to its text. Texts are
limited to 32768 bytes (`OVERLAY_TOO_LARGE`); an unknown slot is `OVERLAY_SLOT_UNKNOWN`; a missing file is skipped with
`OVERLAY_MISSING`, an unreadable or non-UTF-8 one (or, from the project layer, one outside the project) with
`OVERLAY_INVALID`. Overlays are resolved at run time ([ADR 0044](../../docs/architecture/decisions/0044-instruction-overlays-runtime-resolution.md)):
a command calls `aicore ext overlays SLOT [--project DIR] [--json] [--strict]`; static embedding is allowed only into
projections generated into a project or onto a machine, never into shared plugin projections or repository files.

### Conformance

`aicore ext conformance MANIFEST [--input-file FILE] [--json]` starts any plugin through nine scenarios and prints
`check-result/v1` documents `ext.conformance.<scenario>`: `manifest`, `describe`, `protocol-unsupported`, `invoke`,
`redelivery`, `stdout-discipline`, `deadline`, `no-descendants` (Linux only, otherwise `skip`) and `secrets`. Exit
code 1 when a scenario fails. Contract tests for the journal are in `tests/ext/test_event_contract.py`.

## `[aicore]` configuration

The section is validated by `configs/config.schema.json` (`provides.config`); `config.example.toml` is generated from it.

| Key | Meaning |
| --- | --- |
| `events.delivery` | `background` (default), `sync` or `off` |
| `events.timeout_seconds` | subscriber deadline |
| `events.max_attempts` | failures before dead-letter (default 3) |
| `subscriptions.<id>` | `on`, `run`, `plugin`, `projects`, `timeout_seconds`, `enabled` |
| `plugins.<id>` | `manifest`, `trusted`, `timeout_seconds`, `enabled` |
| `overlays."<module>:<slot>"` | array of file paths |

`subscriptions`, `plugins` and `overlays` are *maps*: a schema object with one anchored `patternProperties` key (names
without dots). Entries merge by key across layers, take the leaf defaults, work with `_unset` (a whole entry or one leaf)
and `_append`, and show in `explain`; environment variables cannot address entries. Executable definitions are machine
only (`x-skm-layers`); see [ADR 0040](../../docs/architecture/decisions/0040-extension-configuration-map-tables.md).

## Schema compatibility

`aicore schema compat [--base REF] [--json]` compares the contract schemas of the working tree with the same contracts at
a git reference (default `HEAD`), within one major version, by rules of backward compatibility (a removed property of a
closed object, a new `required`, a narrowed `enum`, a changed `type` or `const`, a tightened bound, a closed
`additionalProperties`, and so on; what cannot be proven, such as `pattern` or `oneOf`, counts as breaking). A breaking
change is an error (exit 1) for contracts that are `beta` or above in `unit.json` and a warning below; a bad reference
or no git exits 2. The validator profile also knows `patternProperties` and `propertyNames`
([ADR 0043](../../docs/architecture/decisions/0043-validator-profile-and-schema-compatibility.md)).

## Telemetry conventions

`configs/telemetry-conventions.json` (contract `telemetry-conventions/v1`) fixes the names, not an exporter: attributes
live in the `skm.*` namespace with `low` or `high` cardinality; spans nest as `skm.run` with the children `skm.plan.compile` and
`skm.stage` > `skm.agent.execute` > (`skm.tool.execute` and `skm.effect.apply`), plus the roots `skm.event.deliver` and
`skm.plugin.invoke`. Only low-cardinality attributes (and the allowed `gen_ai.*` ones) may label a metric;
`aicore.util.telemetry` offers `load_conventions`, `span_name` and `metric_label_problems`. OpenTelemetry export is not
implemented ([ADR 0045](../../docs/architecture/decisions/0045-telemetry-naming-conventions.md)).

## Tests

```bash
bash packages/aicore/scripts/test.sh        # all aicore tests, in a throwaway HOME, without any other module
bash packages/aicore/scripts/validate.sh    # fast structural checks
python3 scripts/ecosystem-units.py check   # manifests and boundaries of all modules, from the repository root
```

The tests need nothing but `aicore` itself, so the folder can be tested as a standalone repository.
