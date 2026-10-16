# ADR 0083: GUI local API: loopback, session secret, desktop transport adapter

## Status

Accepted

## Context

The webview (desktop) and a browser (browser mode) both reach the Python control plane. A local HTTP API is exposed
to every process and web page of the machine: DNS rebinding, cross-site WebSocket hijacking and token theft from
frontend JavaScript are real threats. The `Origin` a webview sends differs by platform and WebKit version, so it cannot
authenticate the desktop client.

## Decision

- **One API.** HTTP `/v1/` and WebSocket `/v1/events` on loopback only (127.0.0.1/::1); no remote bind in production.
- **Session secret.** Every request carries the per-session secret; Host and Origin are checked; no CORS wildcard.
- **Desktop.** The webview does not call loopback directly: a bounded Rust adapter forwards requests (invoke) and
  subscriptions (`tauri::ipc::Channel`) to the fixed sidecar endpoint. The secret lives only in Rust and the sidecar.
  The adapter is not a general proxy: fixed host and port, an allowlist of methods and of the `/v1/` prefix, headers set
  by Rust, a body limit, subscriptions cancelled when the webview closes.
- **Browser mode.** A one-time URL with a token is exchanged for an HttpOnly SameSite=Strict session cookie; the same
  frontend build talks to the same API.

## Alternatives considered

- The webview calls loopback with a bearer token in the frontend: rejected, the token sits in JavaScript and `Origin`
  is not reliable across platforms.
- The whole API over Tauri IPC without HTTP: rejected, no browser mode, against one frontend build.

## Consequences

- The frontend Transport has two implementations (HTTP, Tauri); the UI code does not know which one runs. The
  handshake and the stream are contracts `bootstrap/v1` and `stream/v1` of the `gui` module.
- Tauri capabilities do not restrict Rust network code: the adapter does its own checks and has its own tests.
- Sources: https://v2.tauri.app/develop/calling-frontend/ ; https://v2.tauri.app/security/lifecycle/

## Supersedes

None.
