# ADR 0022: Plugins through entry points with a stable `skm.plugin_api`

Status: proposed
Date: 2026-10-25

## Context
New runtimes, check systems, sandboxes, storage backends and integration targets must be addable without changing the core.

## Decision
Plugins are trusted distributions registering `PluginManifest` objects under the entry point group `skm.plugins`. They
provide components of closed kinds (runtime, integration_target, check_runner, stage_handler, isolation, secret_resolver,
blob_backend, token_estimator, event_sink, exporter, knowledge_source). Loading follows a fixed lifecycle (discover →
allowlist → import → compat → schemas → settings → construct → register → health → required). Plugins import only
`skm.plugin_api` (versioned by `API_VERSION`). Built-in components use the same component interface. Plugins cannot add
tables, bus commands, routes, CLI groups or permissions in v2.

## Alternatives considered
- Out-of-process plugins: deferred (trigger: untrusted third-party plugins).
- Free-form hooks into internals: rejected.

## Consequences
A stable API package must be maintained with SemVer.

## Compatibility
Legacy plugin protocol (ADR 0042) is not ported.

## Verification
Plugin contract tests, including [`tests/unit/bootstrap/test_plugins.py`](../../tests/unit/bootstrap/test_plugins.py), run for built-ins and plugins.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

ADR 0024 adds research_source before API v1 release. E32 exposes allowed runtime metadata through CapabilityCatalog without plugin import. E50 rejects duplicate components before factories.
