# gui architecture

A short map of the module. The decisions live in the hub decision records (`docs/architecture/decisions/` of the hub
repository); this page names them and does not repeat them.

## Parts

```text
React/TypeScript UI (unprivileged; one build)
   │ Transport: HttpTransport (browser mode) | TauriTransport (desktop)
   ▼
Python control plane `gui` (the only authority): HTTP /v1 + WebSocket /v1/events
   │ catalog resolver · ExecutionBroker · PluginHost · ConfigService · RunStore · EventHub
   ▼
bridges/gui-* (domain adapters) → module command lines · aicore plugins · project files

Tauri shell (Rust) = sidecar life cycle + OS integration + transport adapter; no domain logic
```

| Layer | Technology | Owns | Must not |
| --- | --- | --- | --- |
| Desktop shell | Tauri 2, Rust | sidecar supervision, handshake, session secret, single instance, tray, native dialogs, deep links, updater, transport adapter | SKM domain logic, a general shell or file system API for the webview, remote content |
| Frontend | React, TypeScript, Vite, TanStack Query | app shell, host view catalog, core screens, rendering of contributions | file system or shell access, writing canonical files, validation as the source of truth, arbitrary plugin JavaScript (v1) |
| Control plane | Python ≥ 3.11, Starlette + uvicorn | API, validation, orchestration, security, audit | importing modules other than aicore; Pydantic models as a second contract |
| Domain core | stdlib + aicore (`lib/gui/core`, `lib/gui/catalog`) | transport-free services: catalog, broker, runs, configuration transactions, plugins, trust | third-party dependencies (only in `lib/gui/http`) |
| Domain adapters | bridges gui-hub, gui-planner, gui-orch | `gui.json` + `extension.json` (aicore protocol) + mapping onto module command lines | writing another module's files around its command line |
| Local state | SQLite (stdlib sqlite3) + JSONL logs | index of runs, preferences, cache | being the source of truth for plans or configuration |

## Invariants

- I1. Canonical SKM files (plans, configuration, manifests) are the only source of truth; SQLite and caches are
  rebuilt from them and from the journals (`gui state rebuild`).
- I2. The UI writes no files and builds no commands: only typed API requests; the backend builds the argv from a
  registered descriptor.
- I3. Every domain mutation goes through the command line or library of the domain owner (`plan.py`,
  `aicore.config`), never through a direct write of another module's JSON or TOML file from gui.
- I4. A catalog command runs as an argv array without a shell; each argv element is a descriptor literal or exactly
  one value of a typed input; an input value is never joined with other text and cannot start with `-` unless the
  field is declared as a flag value.
- I5. The command cwd is the root of a trusted project or a subfolder of it after `realpath` and `is_within`; the
  environment is `aicore.ext.environment.clean_environment` plus the explicit allowlist of the descriptor.
- I6. Redaction (`aicore.util.redact`) happens before writing to disk and before sending to the WebSocket; secrets are
  never returned by a read API; secret configuration fields are edited as references (`env://`, `keyring://`).
- I7. Life cycle fields of a plan (`status`, `result`, `updated_at`, timestamps) change only through planner life cycle
  commands; a generic form never writes them.
- I8. A configuration write is preview → validate → diff → confirm → lock → revision CAS → temp + fsync + atomic
  replace → re-read and validate; a silent last write wins is forbidden.
- I9. The backend listens on loopback only (127.0.0.1/::1); every request is authenticated with the session secret;
  Host and Origin are checked; CORS has no wildcard; there is no remote bind in production.
- I10. A plugin or adapter runs as a separate process; its failure neither stops the backend nor damages canonical
  files.
- I11. A run state is stored before its event is published; runs left unfinished by a crash become `lost`; a PID is
  never adopted.
- I12. Permissions show three statuses: declared, enforced, advisory; the UI never shows enforced when the platform
  does not apply the restriction.
- I13. Trust is not transitive; a grant is plugin + capability + project + optional expiry + manifest digest; a digest
  change with new permissions needs a new approval.
- I14. gui contracts are versioned like aicore contracts: a breaking change is a new `v<N+1>/` next to the old one; an
  additive change stays in the same version and passes `aicore schema compat`.

## Decision records

| ADR | Decision |
| --- | --- |
| 0080 | Tauri 2 shell, React/TypeScript frontend, Python control plane as a sidecar; Starlette + uvicorn; PyInstaller onedir |
| 0081 | Domains are reached only through bridges `gui-<module>` and the aicore plugin protocol |
| 0082 | Contributions are declarative; UI annotations stay outside canonical schemas; own form renderer |
| 0083 | Local API: loopback, session secret, desktop transport adapter, browser mode by one-time token |
| 0084 | State: canonical files are the source of truth; SQLite is a rebuildable index |

## Module boundary

`lib/gui` imports only the standard library, `gui` and `aicore`; third-party packages appear only in `lib/gui/http`
and the API tests. Contracts are listed in [schemas/README.md](../schemas/README.md).
