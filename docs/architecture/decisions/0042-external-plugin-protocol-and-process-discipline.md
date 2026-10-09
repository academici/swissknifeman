# ADR 0042: External plugin protocol 1, describe before use, process discipline and trust

## Status

Accepted

## Context

ADR 0016 fixed the levels, the manifest before launch and the handshake. P6 needed the exact protocol and the limits
that can honestly be promised without a sandbox.

## Decision

- **Manifest `extension/v1`** (kinds `command` and `subscriber`) is read and checked before launch: schema, entrypoint
  inside its folder, protocol range, required contracts, permission profile.
- **Protocol `1`, stdio JSON:** one request on stdin (`op` is `describe`, `invoke` or `event`), exactly one JSON object
  on stdout, logs on stderr. `describe` runs before every use, with no cache; a mismatch of `id`, `version`, `kind`,
  `protocol` or `capabilities_digest` (digest of `provides`) refuses the call before `invoke`.
- **Process:** new session, one deadline for all pipes, SIGTERM to the group, 2 s, SIGKILL to the group, and a last
  SIGKILL after the child exits; stdout at most 1 MiB; stderr tail 2 KiB with passed secrets replaced by `***`.
- **Environment:** an allowlist. Only a plugin marked `trusted` in the machine config receives declared environment
  names and `env://` secrets. `permissions/v1` is one vocabulary for `unit.json`, `extension.json` and the later run
  policy. The profile `trusted-local` is shown as `enforced: false`; `read-only` is unavailable.
- **Limit:** a descendant that calls `setsid()` leaves the group and is not contained. `aicore ext conformance` finds it
  with `PR_SET_CHILD_SUBREAPER`. Enforcement (cgroup v2 `cgroup.kill`, Landlock) waits for third-party plugins.

## Alternatives considered

- A long-lived JSON-RPC process: rejected for now, plugins have no state and no hot path.
- Cache the handshake: rejected, a stale answer defeats its purpose; revisit when a call is on a hot path.
- Claim a sandbox without one: rejected, an unenforced promise is worse than a stated limit.

## Consequences

- Own plugins run safely enough today and the limits are visible in `aicore ext status`.
- Third-party plugins need enforcement first. A `secret-resolver` kind waits for its first consumer.

## Supersedes

Refines ADR 0016.
