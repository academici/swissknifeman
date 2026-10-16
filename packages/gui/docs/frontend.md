# Frontend

`packages/gui/frontend` is the one frontend build of the GUI: the browser mode serves it from `gui serve`, the desktop
shell will load the same files. React, TypeScript, Vite, TanStack Query and react-router (library mode); exact
versions are pinned by `package-lock.json` (`npm ci` reproduces the install; Node 22.22 or newer).

## Scripts

| Script | Does |
| --- | --- |
| `npm run dev` | Vite dev server; `/v1` and the WebSocket are proxied to `GUI_BACKEND` (default `http://127.0.0.1:8765`, a running `gui serve --port 8765`) |
| `npm run build` | type check, then `dist/` (served by the backend; not in git) |
| `npm run gen:types` | regenerate `src/contracts/generated/*.ts` from the contracts |
| `npm run check` | generated types up to date (golden), `tsc`, `eslint`, `vitest run` |

From the hub root: `npm --prefix packages/gui/frontend ci && npm --prefix packages/gui/frontend run build`.

## Contract types

`scripts/gen-types.mjs` runs `bin/gui schemas bundle --out <tmp>`: each contract of `unit.json` as one JSON Schema
whose references (to this contract, other gui contracts and the foundation) are all local `#/$defs/<key>`
(`gui.contracts.bundle`). json-schema-to-typescript turns them into `src/contracts/generated/<contract>.ts`, kept in
git; `--check` fails when they differ from what the contracts give. `src/contracts/index.ts` names the types the app
uses. The frontend never sees a path of another module.

## Transport

`src/transport/Transport.ts` is the only way the UI reaches the backend: `request(method, path, body)` (the path
starts with `/v1/`) and `subscribe(filter, handlers)`. `HttpTransport` (browser mode) uses same-origin `fetch` with
the session cookie and JSON bodies; a failed request throws `ApiError` (`code`, `message`, `retryable`,
`correlationId`, `details`, `issues` of `api-error/v1`). All subscriptions share one WebSocket `/v1/events`; after a
drop it reconnects with a backoff of 0.5 → 8 s and subscribes again from the last applied `seq` of each
subscription with the backend `epoch` (set by the bootstrap gate). A frame with a `seq` already applied is dropped;
`snapshot_required` resets the cursor and calls `onSnapshotRequired`, where the page reloads its data. The desktop
shell will bring a second implementation with the same interface.

The UI sends only typed bodies of the contracts (`context`, `params`, `input`, `dry_run`, `confirm`): it never builds
an argv and knows no path of a program or an owner (I2).

## Shell and pages

The bootstrap gate reads `/v1/bootstrap`; a backend whose `gui_protocol` excludes protocol 1 or that lacks a contract
the frontend reads shows `PROTOCOL_INCOMPATIBLE` instead of the UI. The navigation lists the contribution routes of
the sections `fleet`, `plan`, `settings`, `plugins` (by `nav.order`); project routes are tabs of a project page.

| Path | Page |
| --- | --- |
| `/` | fleet widgets of the catalog, sized by `size` |
| `/projects`, `/projects/:id` | trusted projects (add one with a confirmation); project widgets and routes |
| `/x/:owner/<path>[?project=<id>]` | a contribution route: its query with context and path parameters, its actions |
| `/runs`, `/runs/:id` | runs (live by `gui.run` frames); a run with its log and Cancel |
| `/catalog` | accepted and rejected contributions with their codes |
| `/settings/config`, `/settings/config/:module[?layer=&project=&mode=]` | the configuration editor (below) |

## Host views

`src/views/ViewDataView.tsx` picks the view by `view`: `resource-list`, `status-table` (with repair buttons that open
the command form of the action), `metric-group`, `timeline`, `markdown` (react-markdown with `skipHtml`; links only
relative or http(s)), `log-stream` (stored pages, then live `log` frames, merged by chunk number), `command-form`
(typed fields from `/v1/commands`, Run and Dry run, the confirmation dialog of `428`, then the run page).
`resource-detail`, `dependency-graph`, `board` and `schema-form` show a placeholder until a later version.

To add a host view: implement `src/views/<Name>View.tsx` for the view-data kind, add its `case` to `ViewDataView`,
and the test of `views.test.tsx` renders every valid example of `schemas/view-data/v1/examples/valid` through it.

## Configuration editor

`/settings/config` lists the modules of `GET /v1/config`; `/settings/config/:module` edits one module. Search
parameters: `layer` (`machine` or `project`), `project` (a project id from `GET /v1/projects`), `mode`
(`form`, `diff`, `raw`, `explain`). The view is `GET /v1/config/{module}/effective[?project_id=]`
(`config-view/v1`, read again on window focus). The UI only reads those endpoints and sends `POST .../preview` and
`PATCH .../layers/{layer}` through the Transport (I2); it writes no file and builds no path.

Code: `src/forms/` (reusable by the plan forms of P4) and `src/pages/ConfigModules.tsx`, `ConfigEditor.tsx`.

- `profile.ts` reads the closed profile of aicore into leaves, tables and maps. Keywords it knows: `type`, `title`,
  `description`, `default`, `enum`, `minimum`, `maximum`, `minLength`, `pattern`, `items`, `properties`,
  `additionalProperties`, `patternProperties`, `x-skm-secret`, `x-skm-layers`. A node with any other keyword is shown
  read-only with the note `unsupported: <keyword>`; it never throws.
- `draft.ts`: the draft is an ordered map of operations (`set`/`unset`) with the layer, the revision and the layer values
  of the view it started on (the base). `toPatch` gives the `patch` of `config-mutation/v1` in the order of editing.
  There is no schema validation in the browser (D6): input is parsed by type only (an integer field that is not an integer
  shows an error and makes no operation); `minimum`, `pattern`, `enum` are hints and the backend preview decides.
- `SchemaForm.tsx` and `fields/`: String, Integer/Number, Boolean, Enum, ScalarList, SecretRef and Map. A secret key takes
  and shows only a reference `env://NAME` or `keyring://NAME`. A field is disabled when `allowed_layers` does not contain the
  layer being edited; `env`, `invocation` and `flags` are read-only and shown in the provenance only. Emptying a field
  removes the key (`unset`); a value equal to the one in the file takes the operation back.
- `ProvenanceBadge.tsx`: the layer, the value and `file:line` (or the variable) of the effective value, `default`, and a list of the
  values it overrides.
- `PreviewDialog.tsx`: `POST preview` with the draft revision, the diff table (layer value and effective value with
  layers), issues and `confirm_reasons`. Apply is disabled while there are issues; it sends
  `{preview_id, expected_revision, confirmed: confirm_required}`. `PREVIEW_STALE` makes a new preview; `CONFIG_LOCKED`
  (423) shows a message and Apply can be repeated.
- `ConflictView.tsx`: `CONFIG_REVISION_CONFLICT` (409, from the preview or the commit) reads the view again and compares by
  key: base (the file when the draft started), current (the file now), mine (the draft). Status `same` (applies cleanly),
  `theirs` (only the file changed) or `conflict` (both changed differently). Reload drops the draft; Reapply keeps its
  operations that still change something and makes a new preview on the current revision.
- Modes: Form; Diff (the draft against the file, in the browser); Raw (`layers[].raw`, redacted by the backend, in a `<pre>`);
  Explain (every key with its effective value and the overridden chain).

Tests: `profile.test.ts`, `draft.test.ts`, `SchemaForm.golden.test.tsx` (golden markup in `src/forms/__golden__/*.html`,
kept in git; `npm run check` compares them and never updates them — to change one on purpose run
`npx vitest run -u src/forms` and read the diff), `src/pages/ConfigEditor.test.tsx` (request bodies, confirmation, conflict,
lock) and the E2E `e2e/config.spec.ts` (edit, preview, apply, an outside change, Reapply) on the `demo` fixture unit, which
provides `configs/config.schema.json`.

## Security rules

Data from the API is text: `dangerouslySetInnerHTML` and `innerHTML` are refused by eslint, markdown skips raw HTML.
The build has no inline script or style and no eval-like code (`tests/test_frontend_build.py`), so it runs under the
backend CSP (`script-src 'self'`, `style-src 'self'`, no `unsafe-eval`); there is no Ajv and no runtime schema
compiler in the frontend.
