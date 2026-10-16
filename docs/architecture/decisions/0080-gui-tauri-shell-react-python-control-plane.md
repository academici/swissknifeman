# ADR 0080: GUI is a Tauri 2 shell, a React/TypeScript frontend and a Python control plane

## Status

Accepted

## Context

One local control plane (fleet, configuration, plans, plugins, commands) must run as a desktop application and in a
browser, keep a thin privileged boundary and leave Python, on a 3.9 hub, the owner of the domain. Current Starlette,
uvicorn, FastAPI and Pydantic dropped Python 3.9; current Starlette requires 3.11.

## Decision

- **Shell.** Tauri 2; Rust does only the sidecar life cycle, OS integration and the transport adapter (ADR 0083).
- **Frontend.** React, TypeScript, Vite; one build for desktop and browser mode (a localhost web UI is that mode, not
  a separate application); no direct Tauri API, only a Transport.
- **Control plane.** The module `gui` (`kind: capability`, `destination: own-repo`) is the only authority: Starlette
  + a minimal uvicorn; canonical JSON Schema validation through `aicore.util.schema`; no FastAPI, no Pydantic.
- **Python floor.** `gui` requires Python ≥ 3.11 (`MIN_PYTHON`, `PYTHON_TOO_OLD`); the hub stays on 3.9, so `gui` is a
  tool module (`standalone.tools`) with its own `dev.test`. Third-party packages only in `lib/gui/http` and API tests.
- **Packaging.** The backend ships as a PyInstaller onedir sidecar `gui-backend-<target-triple>`; Linux AppImage/deb and
  macOS; updater artifacts are signed with minisign on the owner's machine (`tauri signer sign`), not in CI.

## Alternatives considered

- Electron: rejected, a bigger runtime and Node in the main process raise the cost of an XSS. PySide6/Qt: rejected,
  no browser mode and runtime contributions are hard.
- FastAPI + Pydantic: rejected, Pydantic models would be a second contract next to JSON Schema.
- PyInstaller onefile or PyTauri: rejected, per-start extraction and partial signing; PyTauri breaks process isolation.

## Consequences

- The desktop build needs a Rust toolchain and an updater key on the owner's machine; API contracts are documented
  by hand (`docs/api.md` of the module), not generated as OpenAPI.
- Sources: https://v2.tauri.app/develop/sidecar/ ; https://starlette.dev/release-notes/

## Supersedes

None.
