# ADR 0066: maind reaches harness through JSON commands; the MCP projection moves to aicore

## Status

Accepted

## Context

`maind deploy`, `sync` and `workspace` imported `harness` modules and named its folders to render MCP configuration,
instructions and Codex lifecycle hooks.

## Decision

- **Projection.** The pure MCP projection (`McpServer`, `McpProjection`, `parse_mcp_catalog`, `plan_mcp_projection`,
  `plan_mcp_artifact`, `render_mcp_projection`) is `aicore.provider.mcp`. It takes parsed documents and the artifact
  sources from the caller, so no harness path enters the foundation.
- **Data and services.** harness answers with JSON: `harness mcp catalog --json` (`mcp-catalog/v1`),
  `harness profiles resolve --json` (`profile-resolution/v1`), `harness hooks codex-lifecycle fragment|validate --json`
  (`codex-lifecycle/v1`), `harness instructions scopes --json` (`instruction-scopes/v1`) and the existing
  `harness instructions plan|check|apply --json`. maind calls them through `aicore.util.partners`.
- **Degradation.** Without harness the provider steps are skipped with `PARTNER_UNAVAILABLE`; the hub servers still deploy.
- **Equality.** Tests compare the bytes of provider files and the records of the artifact lock before and after the move.
- **Renderers.** The profile renderers of Cursor, Grok and the provider files stay in harness: one consumer, and they
  hold policy.

## Alternatives considered

- Moving all renderers to `aicore`: rejected, `aicore` grows only with a real second consumer.
- Keeping the import with an exception in the boundary check: rejected, it blocks `maind` from being standalone.

## Consequences

- maind passes the standalone check.
- A harness release can change its internals without touching maind while the contracts hold.

## Supersedes

None.
