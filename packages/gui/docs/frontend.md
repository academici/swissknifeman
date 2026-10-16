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

## Host views

`src/views/ViewDataView.tsx` picks the view by `view`: `resource-list`, `status-table` (with repair buttons that open
the command form of the action), `metric-group`, `timeline`, `markdown` (react-markdown with `skipHtml`; links only
relative or http(s)), `log-stream` (stored pages, then live `log` frames, merged by chunk number), `command-form`
(typed fields from `/v1/commands`, Run and Dry run, the confirmation dialog of `428`, then the run page).
`resource-detail`, `dependency-graph`, `board` and `schema-form` show a placeholder until a later version.

To add a host view: implement `src/views/<Name>View.tsx` for the view-data kind, add its `case` to `ViewDataView`,
and the test of `views.test.tsx` renders every valid example of `schemas/view-data/v1/examples/valid` through it.

## Security rules

Data from the API is text: `dangerouslySetInnerHTML` and `innerHTML` are refused by eslint, markdown skips raw HTML.
The build has no inline script or style and no eval-like code (`tests/test_frontend_build.py`), so it runs under the
backend CSP (`script-src 'self'`, `style-src 'self'`, no `unsafe-eval`); there is no Ajv and no runtime schema
compiler in the frontend.
