# Plan read API

Use `python3 <Task package root>/scripts/plan.py` for plan data. Query documents and links through
the API; never open or edit plan source files directly. Human Markdown under `views/` is not an
agent input. Repository code and documentation remain ordinary readable files.

## Discover the API

```sh
python3 <Task package root>/scripts/plan.py schema --verbs
python3 <Task package root>/scripts/plan.py schema item
python3 <Task package root>/scripts/plan.py schema read-links
python3 <Task package root>/scripts/plan.py schema defs
```

`schema` needs no plan. With no argument, it returns the same catalog as `schema --verbs`.
`schema <kind>` returns the complete schema document, including `$id`, properties and definitions.
The kind and `--verbs` are mutually exclusive. The catalog's `schema` argument lists available kinds.

The catalog is built from the live argument parser. Each entry contains `name`, `summary`,
`mode`, `args`, `errors` and, when available, `data_kind`:

- `args` contains the actual argument names, `required`, `help`, cardinality (`nargs`), and optional
  `choices` and `aliases`. Global options precede the verb; arguments with `scope: verb` follow it.
  `exclusive_with` lists alternatives. `required_group: true` requires one of those alternatives,
  even when each individual argument has `required: false`.
- `mode` describes the default invocation. `context` writes a generated pack unless `--stdout`
  is supplied; `render` writes views unless `--check` is supplied. `unit` combines queries and
  mutations, so its mode is `write`. `brief` defaults to read-only stdout; `--out` writes a file
  outside the plan. Mode is discovery metadata, not an authorization grant.
- `data_kind` names a dedicated `plan/v1` data schema. Retrieve it with `schema <data_kind>`.
  Existing polymorphic payloads omit this field. `brief` uses the external `exec/v1 execution-input`
  contract. For `schema`, `read-catalog` describes the default/`--verbs` result; `<kind>` returns
  the schema document itself.
- `errors` lists conservative stable refusal codes registered for that verb, including shared
  CLI errors. It is not a list of errors produced on every invocation.

## Responses

The read verbs below and `schema` always return one validated JSON envelope:

```json
{"ok": true, "data": "the verb result"}
```

A refusal returns `{"ok": false, "error": {"code": "REF_UNKNOWN", "message": "..."}}`.
`error.issues` optionally carries validation details. Exit codes are 0 for success, 1 for refusal
or failed checks, and 2 for invalid command usage. Get the same envelope for any existing verb
with `plan.py --output json <verb> ...`.

Read data is complete: there is no content truncation or read quota. An explicit field, section,
filter, depth or limit narrows the requested result.

## References and queries

Pass a plan id, `PLAN<N>` or plan directory as `PLAN`. Document references are `plan`, `brief`,
`Pn`, `Pn.m`, `Pn.m/U#`, `D#`, `knowledge/<id>[#section]` and `artifact/<id>`.
Qualified references use `PLAN<N>.<ref>` or `<repo>:PLAN<N>.<ref>`.
The shared `defs.ref` grammar covers typed document references; `plan` and `brief` are query
selectors, not stored typed links. Knowledge/artifact ids and section ids use ASCII letters,
digits, dots, underscores and hyphens, with an alphanumeric first and last character.
Paths and `.json` filenames are not substitutes for a typed reference.

| Query | Result in `data` |
| --- | --- |
| `get PLAN REF [--section ID] [--fields a,b] [--repo NAME=PATH]` | `{ref,kind,doc}`; source kind is `document` for knowledge. Section selection retains the knowledge document with its selected complete section; fields are top-level keys. |
| `list PLAN KIND [--status S] [--phase Pn] [--applies-to REF]` | Rows `{ref,title,status}`, in deterministic document order. Filters combine with AND. Kinds are item, phase, decision, document and unit; plural names also work. |
| `events PLAN [--item REF] [--type T,...] [--since TS] [--limit N]` | Full journal events in log order. `since` is inclusive and needs a timezone; `limit` selects the latest matching events, retaining log order. Zero returns an empty list. |
| `artifact PLAN artifact/ID [--inline] [--repo NAME=PATH]` | `{ref,path,role,exists,sha256,content?}`. SHA-256 covers exact bytes. Inline content is complete JSON for `.json`, otherwise UTF-8 text. A missing declared file has `exists: false`, `sha256: null`, and no content. |
| `links PLAN REF [--direction out\|in\|both] [--kind K,...] [--depth N]` | `{ref,edges,nodes}`. Default direction is both and depth is 1. Depth must be an integer >=1. Incoming traversal finds dependents but retains each edge's original `from`/`to`. |
| `neighborhood PLAN ITEM` | `{ref,item,edges,nodes,decisions,documents}`: the complete local item, its depth-one graph, explicit and applicable accepted local decisions, and global/applicable/explicitly consumed local knowledge. |

`get` and `artifact` can load qualified sources; map another repository with repeatable
`--repo NAME=PATH` or `SKM_PLAN_REPOS` (a JSON object of repository names to paths).
`links` and `neighborhood` never load another plan. Foreign graph nodes retain their qualified
reference with null title/status. `neighborhood` requires a local item; self-qualified references
are accepted. The link table can also emit `brief/B#` requirement nodes.

Edges come from the single typed link table, including computed incoming traversal. They are
unique, retain optional `relation`/`note`, and are sorted by kind, from, to, relation and note.
Nodes include the root and every returned edge endpoint, sorted by reference. Cycles terminate.
Supported edge kinds are `depends_on`, `related`, `decision`, `applies_to`, `unit_depends_on`,
`parent`, `consumes`, `produces` and `supersedes`.

Malformed references return `REF_INVALID`; unknown local documents return `REF_UNKNOWN`.
Unknown sections/fields return `SECTION_UNKNOWN`/`FIELD_UNKNOWN`. Graph options can return
`DEPTH_INVALID`, `DIRECTION_INVALID` or `KIND_UNKNOWN`. Artifact path escape, plan human views and
invalid inline content return `PATH_INVALID`, `HUMAN_VIEW` and `CONTENT_INVALID` respectively.
Use the catalog for the complete per-verb refusal sets.

These read queries take no plan lock and write no files. `show PLAN REF` remains a document-only
compatibility view, while `show` without a reference remains the overview. Existing `context`
continues to provide the full execution pack. State changes use authoring/lifecycle verbs;
do not convert a query result into a direct plan-file edit.

## Declare plan links and artifacts

Use the following mutations to change links. They take a plan lock, validate the changed
document and complete proposed graph before publication, and leave source documents and the
event log unchanged on refusal. They do not change lifecycle fields (`status`, `result`).
Use `--output json` before the verb for the success/error envelope.

| Mutation | Arguments after `PLAN` |
| --- | --- |
| `link` | `SOURCE TARGET --kind KIND [--relation R] [--note TEXT]` |
| `unlink` | `SOURCE TARGET --kind KIND [--relation R]` |
| `add-artifact` | `ITEM --path PATH --role input\|output [--id ID]` |

`link` and `unlink` accept only bare local references, including their source. Qualified
references are refused with `REF_QUALIFIED`; use `set`/`apply` for schema-supported qualified
links. `set`, `push` and `apply` refuse (`PLAN_INVALID`) an edit that introduces a new unresolved link
in any link field; errors the plan already had do not block an unrelated edit. The writable kinds map to these fields:

| Kind | Source → target | Owning field |
| --- | --- | --- |
| `depends_on` | phase → phase, item → item | `depends_on[]` |
| `related` | item → typed document reference | `related[]` (`ref`, `relation`, optional `note`) |
| `decision` | item → decision | `decisions[]` |
| `applies_to` | decision or knowledge document → phase or item | `applies_to[]` |
| `unit_depends_on` | unit → unit in the same item | `depends_on[]`, stored as bare `U#` |

`related` requires `--relation informs|consumes|conflicts|follows_up|supersedes`.
`--relation` and `--note` belong only to related links. Repeating an existing link is a no-op;
supplying a different nonempty note for the same related target/relation updates the note.
`unlink` also needs the relation for related links; a missing link is a no-op. It can remove
a dangling target without resolving that target, provided the remaining graph passes `check`.

`add-artifact` declares metadata; it does not create the artifact file. `PATH` is repository-relative
or starts with `@plan/`. An output's optional id is unique across the plan and can be queried as
`artifact/ID`. An input with an id cites the matching output declaration and path. Omitting ids
preserves existing path-based artifact declarations. Repeating the same `(path, role, id)` is a
no-op; adding an id to a declaration without one is allowed, but changing an existing id is refused.
The responses report `changed: false` for a no-op.

Optional `reads[].ref` names local plan data, including `knowledge/<id>#section`; exactly one of
`ref` or `path` is required, with the existing `why` and `required` fields. Repository code/docs
remain path-based reads. `context` resolves plan reads into complete sections and `brief` projects
them to the existing path-based `exec/v1` read contract. Required missing sections refuse
`start`/`brief` with `READ_MISSING`; graph validation also checks section references.
Use either the `#section` fragment or the separate `section` key, never both. Qualified read
refs are refused by `check`; qualified queries remain available through `get`/`artifact`.

`check` derives all links from one table (`edges.LINK_FIELDS`), checks target kinds and existence,
dependencies, cycles, artifact declarations and decision supersession backlinks. Reverse edges
are computed rather than persisted. The other graph kinds (`parent`, `consumes`, `produces`,
`supersedes`) remain visible through `links`; their owning authoring/lifecycle verbs change them.
Invalid source/target combinations return `LINK_INVALID`; schema and proposed-graph failures
return `SCHEMA_INVALID` and `PLAN_INVALID`. See `schema --verbs` for the full error sets.
