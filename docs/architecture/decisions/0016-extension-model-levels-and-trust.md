# ADR 0016: Extension model: levels, manifest before launch, handshake, trust

## Status

Accepted

## Context

Without a shared model every module would invent its own extension registry.

## Decision

Levels: (1) out-of-process (external plugin commands and bridges over JSON on stdin and stdout) is the only level
now; (2) in-process through Python entry points waits for pip packaging; (3) remote waits for distributed
execution. Every extension has a manifest readable before launch (id, kind, version, protocol range, required
contract ranges, provided capabilities with stability, declared permissions for filesystem, network, secrets and
shell, entrypoint). Before use, a `describe` call performs a handshake (protocol, id, version, capabilities digest,
transport); an incompatible extension is rejected before it runs. An external plugin runs with a cleaned
environment, receives secrets only through declared references and is marked trusted or untrusted. Enforced
sandboxing is added when third-party plugins appear. CLIs and checks of modules are discovered from `unit.json`
(`provides.cli`, `provides.doctor`), not from a hard-coded list.

## Alternatives considered

- In-process plugins first: rejected, modules are not pip packages.

## Consequences

- Permissions are declared in the manifest schema now and enforced later.
- The hub finds module CLIs and checks from manifests.

## Supersedes

None.
