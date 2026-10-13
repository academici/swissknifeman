# ADR 0070: The maind MCP server negotiates the protocol version

## Status

Accepted

## Context

The server answered `initialize` with the version the client sent, so it claimed support for revisions it never
checked.

## Decision

- **Versions.** `SUPPORTED_PROTOCOL_VERSIONS` lists the supported revisions, newest first: `2025-06-18`, `2024-11-05`.
  A revision is added only after its changelog is checked for required behavior of a stdio server that offers tools only.
- **Negotiation.** `initialize` returns the requested version when it is supported and otherwise the newest supported one.
- **Digest.** `tools_digest` is the `aicore` digest of the tool list. `maind mcp tools [--json]` prints the list and the digest
  (contract `mcp-tools/v1`); `maind doctor` reports it in `maind.mcp`.
- **Conformance.** A test runs the server against the official MCP Python SDK. The SDK is a development dependency pinned in
  `packages/maind/requirements-dev.txt`; the test is skipped without it and the runtime never imports it.
- **Own server.** The server stays hand-written and stdlib-only; replacing it by the SDK stays rejected.

## Alternatives considered

- Echoing the client version: rejected, it hides unsupported behavior.
- Using the SDK at run time: rejected, it needs a newer Python and a dependency.

## Consequences

- A conformance run needs an environment with the SDK; the hub CI step installs it.

## Supersedes

None.
