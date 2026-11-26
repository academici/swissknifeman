# SKM Web Operator Guide

## Sign in

The web client follows the API process `web_auth` mode.

- **`none`.** On a loopback server the client calls `GET /api/v1/auth/session`.
  A successful `mode: none` response opens the app as the local owner. Requests
  use `credentials: include` and do not send `Authorization`. **Выйти** returns
  to `/login` until **Продолжить локальный сеанс** is chosen again.
- **`admin_login`.** **Пароль администратора** loads `GET /api/v1/auth/csrf`,
  then `POST /api/v1/auth/login` with `X-SKM-CSRF` and the session cookie.
  Mutations repeat that header. **Обновить сеанс** calls
  `POST /api/v1/auth/session/reload`. **Выйти** calls `POST /api/v1/auth/logout`.
  HTTP 403 refreshes the CSRF token and stays on the page. HTTP 401 clears the
  session.
- **`token`.** Open the SKM URL with the `#token=<secret>` fragment supplied for
  your session. On startup, the browser stores the token in
  `sessionStorage["skm.token"]` and removes the fragment with
  `history.replaceState`, preserving the path and query. API requests and event
  subscriptions send the token as `Authorization: Bearer <token>` and omit
  cookies, so a leftover session cannot be combined with the bearer token.

You can also open `/login`, paste the token into **Токен доступа**, and select
**Войти**. The page checks the token against `GET /api/v1/me` before saving it.
If an API request or event subscription for the current session receives HTTP
401, the app closes open event and live streams, clears the token, saved scope,
and query cache, then takes you to `/login`. Sign in again with a valid token.

**Принципалы** (`/admin/principals`) lists, creates, and disables principals and
assigns roles. Project and workspace views manage members on the same membership
API.

## Live updates and reconnect

The client reads workspace server-sent events (SSE) with `fetch` and a
`ReadableStream` so it can send the bearer token and `Last-Event-ID` headers.
After a dropped connection it retries with backoff from 1 to 30 seconds and
resumes from the last cursor. Duplicate event IDs are ignored.

- **SURF-06.** The client reads the view with `GET`, then starts its workspace
  subscription with `after` set from the response's `SKM-Events-Cursor` header.
  This lets the stream replay events written between the read and subscription.
  If an existing stream has already advanced past the response cursor, the
  client reads the view again.
- A subscription with neither `after` nor `Last-Event-ID` starts at the current
  workspace head. An `event: cursor` frame advances the cursor without invalidating
  cached data. A `snapshot-required` frame triggers a full query-cache
  invalidation and refresh of active views. The v2.0 server does not emit this frame.
- **SURF-14.** Instance resources such as extension packs, resources, hosts, and
  runtimes refresh on window focus and poll at `ui.stale_after_seconds`. The same
  setting controls freshness indicators. Worker state updates use the workspace
  stream, and health has its own 15-second poll.

Event-to-query invalidation is implemented in [`web/src/api/invalidation.ts`](../../web/src/api/invalidation.ts).

## Choose a scope and check permissions

Select a workspace and project in the top bar. `ScopeProvider` uses the scope in
the URL when present and falls back to `sessionStorage["skm.scope"]`. Changing
scope closes the previous workspace subscription and drops cached queries for
the previous scope.

`GET /api/v1/me` supplies `modules` for optional navigation and
`permissions_by_scope` for actions on the selected resource. The UI hides
actions when the corresponding permission is missing. The API checks the
permission again for each request. If an action is missing, check the selected
workspace, project, and role first. For a 403 response, use the error code and
request ID shown in the error panel when contacting the operator.

## Manual review and Inbox

On a waiting run, read the blocking reason and follow the link to **Входящие**
(`/inbox`). Filter by scope, kind, and state to find the open request. Check its
run and task references, required role, and deadline when shown.
For review evidence, open the attempt from the task and look under **Ревью**
for the recorded verdict and findings.

| Kind | Operator action |
|---|---|
| `question` | Read the question, blocking reason, and displayed authority. Select an offered answer or enter a response as the form allows, then submit. |
| `manual_check` | Verify the referenced check using the instructions on the card. Add a comment if needed and choose **Пройдена** (`pass`) or **Не пройдена** (`fail`). Return to the run to see the server's updated status. |
| `approval` | Review the `ApprovalCard` fields bound to the server intent. Check `subject_ref`, `effect_id`, the exact target and other values in `normalized_args`, `args_digest`, risk, expiry, and the single-use flag. Approve or deny in the confirmation dialog. Under SURFACE-04 the card displays these fields outside user Markdown, so a title or link in the description cannot disguise the destination. If the request changed, reload it and inspect the new details before confirming. |
| `deviation` | Select the applicable criterion, finding, attention verdict, or coverage. Check the target identifier when required and give the reason for accepting the deviation. |
| `escalation` | Read the stop code and choose among the responses offered for the request. Run-control and deviation actions require their own permissions. A `NOT_ACCEPTABLE` escalation can also offer the deviation form. |

The Inbox shows actions for open requests when the required role and permissions
allow them. After submitting a decision, use the updated Inbox and run status
to see whether anything else is blocking the run. The Inbox shows the server
error code and request ID when a decision fails.

## Review analytics

Open **Аналитика** in a project and select a run. The report counts completed
agent and human reviews and uses the latest state of each finding key within
its task. Cost and capture time are sums over finished reviewer steps with
the corresponding measurements. The coverage counts show how many steps
contributed to each total, including any failed or cancelled steps with data.

The CLI exposes the same report with `skm analytics review-roi RUN` and accepts
`--json`. The report requires `run.read` and is read-only. Estimating review
impact and informing router weights requires a labeled comparison sample.
