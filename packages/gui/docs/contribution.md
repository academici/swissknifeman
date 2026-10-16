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

## Resolver rules

The resolver accepts or rejects a whole contribution; a rejected file is listed with its code and adds nothing.

| Code | Rule |
| --- | --- |
| `CONTRIB_INVALID` | the document fails `contribution/v1` (issues in the details) |
| `CONTRIB_UNREADABLE` | the file cannot be read or parsed, or exceeds a limit below |
| `CONTRIB_OWNER_MISMATCH` | `owner` differs from the id of the unit or extension that declares the file |
| `CONTRIB_ID_PREFIX` | a local id does not start with `<owner>.` |
| `CONTRIB_CONFLICT` | two contributions use the same local id or route path; every participant is rejected |
| `CONTRIB_INCOMPATIBLE` | `gui_protocol` excludes the host protocol, `min > max`, or a required contract is unsupported |
| `CONTRIB_HANDLER_MISSING` | a query or an `invoke` command exists without `handler`, or the handler lacks the point |
| `CONTRIB_PATH_ESCAPE` | `argv[0]`, `handler.extension` or a docs path leaves the owner root (`..`, absolute, symlink) |
| `CONTRIB_REF_UNKNOWN` | a route, widget, action, configuration section or `dry_run` names an undeclared query, command, form, docs tree or field; a route parameter is not a query parameter; `enum` without type `enum` |
| `CONTRIB_INPUT_UNKNOWN` | an argv `{input}` names an undeclared field, or a field with a flag |
| `CONTRIB_CAPABILITY_RESERVED` | the effect `terminal`, or `stream`/`cancel` with an `invoke` exec, or `dry-run` without `dry_run` (and the reverse) |

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
