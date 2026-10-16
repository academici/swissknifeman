# Contribution contract (`contribution/v1`)

A contribution is a `gui.json` file that a hub unit (usually a bridge `bridges/gui-<module>`) or an external
extension ships to add pages, widgets, queries, commands, forms, configuration sections and docs to the GUI. It is
data only: the GUI never runs JavaScript from a contribution.

- Contract: `urn:swissknifeman:gui:contribution:v1`, file `schemas/contribution/v1/contribution.schema.json`.
- Declared by `provides.gui` (a path relative to the unit or extension root) in `unit.json` (aicore `unit/v1`) or
  `extension.json` (aicore `extension/v1`). `python3 scripts/ecosystem-units.py check` in the hub verifies that the
  file of a hub unit exists inside the unit and is valid (`ECOSYSTEM_UNIT_GUI` otherwise).
- Queries and short commands are answered by the owner's aicore extension (`handler`) on the points `gui:query` and
  `gui:command`; long commands run as an argv array through the GUI execution broker.
- Validation: `gui.contracts.validate(document, "contribution")` (closed profile of `aicore.util.schema`). The rules
  that a schema cannot express are checked by the resolver (`gui contributions`, `gui check`) with the `CONTRIB_*`
  codes listed below.

## Document

| Field | Required | Meaning |
| --- | --- | --- |
| `$schema` | yes | `urn:swissknifeman:gui:contribution:v1` |
| `owner` | yes | id of the unit or extension that ships the file (`^[a-z][a-z0-9-]*$`); equals its `unit.json` / `extension.json` id |
| `version` | yes | semver of the contribution |
| `gui_protocol` | yes | `{min, max}`: host protocol versions (positive integers as strings), `min <= max` |
| `requires_contracts` | no | `[{id, version}]`: contracts the host must support (`urn:swissknifeman:<module>:<name>`, `v<N>`) |
| `handler` | when a query or an `invoke` command exists | `{extension}`: path of the owner's `extension.json` (kind `command`, points `gui:query` and/or `gui:command`) |
| `routes`, `widgets`, `queries`, `commands`, `forms`, `config_sections`, `docs` | no | lists, at least one element when present |

### Identifiers

- A *local id* names a route, widget, query, command, form, configuration section or docs tree:
  `<owner>.<name>[.<name>...]`, segments `^[a-z][a-z0-9-]*$`. The first segment must equal `owner`.
- Field names (inputs and parameters): `^[a-z][a-z0-9_]*$`.

### `routes[]`

`{id, title, path, view, scope, query?, command?, docs?, nav?, actions?}`

- `path` is relative to `/x/<owner>/`: literal segments `^[a-z0-9-]+$` and parameters `:name`; no leading slash, no
  empty segment, no `.` or `..`. Each `:name` must be a parameter of the route query.
- `view`: `resource-list`, `resource-detail`, `schema-form`, `metric-group`, `status-table`, `timeline`, `log-stream`,
  `markdown`, `dependency-graph`, `board`, `command-form` (the data is the same kind of `view-data/v1`).
- `scope`: `fleet`, `project`, `plan`, `item`, `run` — the context the host passes.
- `query` is required for every view except `command-form` (which names `command`) and `markdown` with `docs`.
- `nav`: `{section: fleet|project|plan|settings|plugins, order 0..1000, icon}`; without `nav` the page is reached by
  links only. `actions`: command ids offered on the page.

### `widgets[]`

`{id, title, view, query, scope, size?}` — `view` is one of `metric-group`, `status-table`, `timeline`,
`resource-list`; `scope` is `fleet` or `project`; `size` `small|medium|large` (default `medium`).

### Fields (`queries[].params[]`, `commands[].input[]`)

`{name, title, description?, type, required, enum?, pattern?, minimum?, maximum?, default?, flag?}`

- `type`: `string`, `integer`, `number`, `boolean`, `enum` (values in `enum`), and the reference types checked by the
  host: `project-path` (relative, inside the project after realpath), `plan-ref` (planner plan id or `PLAN<N>`),
  `item-ref` (`P<n>.<m>`), `model-ref` (`<provider>/<model>` of the model catalog), `secret-ref`
  (`env://NAME` or `keyring://NAME`; the value is a reference, never the secret).
- `flag` (`--name`): a boolean adds only the flag when true; another value adds the flag and then the value as its own
  element; a field without a flag is positional and appears in `argv` as `{input: name}`.

### `queries[]`

`{id, title, description?, scope, params?, returns, timeout_s?, cache_s?}` — always executed through `gui:query` of
the handler with the input `{id, context, params}`; the answer is a `view-data/v1` document of the kind `returns`.
`timeout_s` 1..120 (default 30), `cache_s` 0..3600 (default 0).

### `commands[]`

`{id, title, description?, scope, input?, effects, risk, confirmation, supports?, timeout_s, concurrency_key?, exec,
dry_run?}`

- `effects` (at least one): `read`, `project.write`, `plan.write`, `config.write`, `process.spawn`, `network`,
  `secrets.read`, `terminal` (reserved; refused in v1). The host authorizes each effect.
- `risk` `low|medium|high`; `confirmation` `none|risk-based|always`; `timeout_s` 1..86400.
- `supports`: `dry-run` (needs `dry_run`), `cancel` and `stream` (need an argv `exec`).
- `concurrency_key`: runs with the same key do not overlap; placeholders `{project_id}`, `{plan_id}`, `{item_id}`.
- `exec`:
  - `{kind: "invoke"}` — through `gui:command` of the handler;
  - `{kind: "argv", argv, cwd, env?}` — an argv array without a shell. `argv[0]` is a literal path inside the owner
    root; every element is a literal string or `{input: <field>}`, the whole value of one field. A value is never
    joined with other text: the schema has no way to say so. `cwd` is `project` (the trusted project root) or `owner`
    (the owner root); `env` names variables passed on top of the clean environment.
- `dry_run`: `{argv_append: [literals]}` or `{input: <boolean field>}`.

Example: `argv: ["bin/plan-adapter", "run-item", {"input": "plan"}, {"input": "item"}]` with the field
`{name: "dry", type: "boolean", flag: "--dry-run"}` and the input `plan=PLAN5, item=P2.1, dry=true` runs
`["<owner root>/bin/plan-adapter", "run-item", "PLAN5", "P2.1", "--dry-run"]`.

### `forms[]`

`{id, schema, groups?, fields}` — UI annotations of a canonical schema (`schema`: its URN, optionally with a pointer).
`fields[]`: `{pointer, group?, order?, widget?, readonly?, hidden?, confirm?}`; `widget` is one of `text`, `textarea`,
`number`, `toggle`, `select`, `model-picker`, `path-picker`, `secret-ref`, `list`, `map`, `json`. Annotations live
only here: canonical schemas never carry UI keywords. `readonly` is UX only; the owner refuses the write.

### `config_sections[]` and `docs[]`

- `config_sections[]`: `{id, module, title, form?}` — a module configuration shown in the settings screen.
- `docs[]`: `{id, title, root, index}` — a documentation tree inside the owner root; `index` is relative to `root`.

## Resolver

`gui.catalog` finds and accepts contributions (stdlib + aicore; it does not know the hub layout):

1. **Sources.** Unit folders come from `SKM_UNITS_PATH` when it is set, else from the hub registry
   `swissknifeman units list --json` (the executable from `SKM_UMBRELLA` or `PATH`; relative unit roots resolve
   against its `hub_root`). External extensions are the enabled, loadable entries of `[aicore.plugins]` (for
   `--project DIR`, with that project's configuration). A unit or extension counts when its manifest has
   `provides.gui`. A source that cannot be read is a `CATALOG_SOURCE_UNAVAILABLE` entry; the other sources still count.
2. **Rules.** Every contribution goes through the rules in this order; the first failing rule names the rejection
   code and the rest of the file adds nothing:

| Rule | Code | Fails when |
| --- | --- | --- |
| path | `CONTRIB_PATH_ESCAPE` | `provides.gui` is absolute or its realpath leaves the owner root (`..`, a symlink, a symlink loop) |
| read | `CONTRIB_UNREADABLE` | the file is missing, larger than 256 KiB or not UTF-8 JSON |
| schema | `CONTRIB_INVALID` | the document fails `contribution/v1` (issues with pointers) |
| limits | `CONTRIB_INVALID` | a limit below is exceeded or a field `pattern` does not compile |
| owner | `CONTRIB_OWNER_MISMATCH` | `owner` differs from the id of the unit or extension that declares the file |
| ids | `CONTRIB_ID_PREFIX`, `CONTRIB_CONFLICT` | a local id does not start with `<owner>.`; a local id (per list), route path or field name is declared twice in the file |
| protocol | `CONTRIB_INCOMPATIBLE` | `min > max`, the range excludes the host protocol, or a required contract is not provided by gui or aicore |
| handler | `CONTRIB_HANDLER_MISSING`, `CONTRIB_PATH_ESCAPE` | a query or an `invoke` command exists without `handler`; the handler file is missing, not a usable command `extension.json` (aicore `load_manifest`) or lacks `gui:query` / `gui:command`; its path leaves the owner root |
| refs | `CONTRIB_REF_UNKNOWN`, `CONTRIB_PATH_ESCAPE` | a route, widget, action, configuration section or `dry_run` names an undeclared query, command, form, docs tree or boolean field; a route or widget view differs from what its query returns; a route needs a query (or a command for `command-form`, docs or a query for `markdown`); a route parameter is not a query parameter; `enum` values without type `enum` or the reverse; an unknown `concurrency_key` placeholder; a docs index is missing (`REF_UNKNOWN`) or leaves the owner root (`PATH_ESCAPE`) |
| argv | `CONTRIB_PATH_ESCAPE`, `CONTRIB_REF_UNKNOWN`, `CONTRIB_INPUT_UNKNOWN` | `argv[0]` is not a literal or leaves the owner root; it is not an executable file; an `{input}` is undeclared or has a flag |
| capabilities | `CONTRIB_CAPABILITY_RESERVED` | the effect `terminal`; `stream` or `cancel` with an `invoke` exec; `supports: dry-run` without `dry_run` or the reverse |

3. **Conflicts.** Accepted contributions are compared with each other: two that claim the same owner, local id or
   route path (`/x/<owner>/<path>`) are all rejected with `CONTRIB_CONFLICT`. The order of the sources never decides
   a winner.

## Catalog (`catalog/v1`)

`{$schema, host {gui_protocol}, contributions [{owner, source, file, digest, document}], rejected [{owner, file, code,
message, issues?}], digest}` — contributions sorted by owner, source and file; rejected entries by owner, file and code;
no timestamps. `file` is the realpath of the gui.json (or the name of an unavailable source); each `digest` is the
digest of its document; the catalog `digest` covers the host and the `(owner, source, digest)` of every accepted
contribution, not the paths, so the same contributions give the same digest on every machine.

## Command line

```text
gui contributions [--json] [--project DIR]   the catalog: a table (owner, source, routes, queries, commands, file),
                                             the rejected entries and the digest; --json prints catalog/v1; exit 0
gui check PATH [--json]                      one contribution (a gui.json, or a unit or extension folder): one
                                             check-result/v1 per rule (gui.contribution.<rule>), then the aicore
                                             conformance of its handler (starts the handler); exit 1 on a fail
```

Exit 2 is a usage error.

## Limits

Limits the schema cannot express; the resolver enforces them (`CONTRIB_UNREADABLE` for the file size, `CONTRIB_INVALID`
otherwise):

| What | Limit |
| --- | --- |
| `gui.json` size | 256 KiB |
| `title`, `label` and other single-line text | 200 characters |
| `description` | 2000 characters |
| routes, widgets, queries, commands, forms, configuration sections, docs | 200 each |
| fields of a query or a command | 64 |
| argv elements; `argv_append` elements | 64 |
| one argv literal | 4096 characters |
| `enum` values of a field | 200 |
| form field annotations | 500 |

## Examples

- `schemas/contribution/v1/examples/valid/minimal.json`: identity only.
- `schemas/contribution/v1/examples/valid/full.json`: a planner-like bridge with routes, a widget, queries, an argv
  command with inputs, flags and a dry run, an invoke command, a form, a configuration section and docs.
- `schemas/contribution/v1/examples/invalid/*.json`: one rejected case per file, named `<case>.<issue code>.json`.

The data contract of queries is `view-data/v1` (`schemas/view-data/v1/`): one kind per `view`, chosen by the const
field `view`; `gui.contracts.validate` reports the issues of the named kind.
