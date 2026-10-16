# Conformance kit

Two checks answer "does this follow the protocol" for code that is not ours
([ADR 0076](../architecture/decisions/0076-conformance-kit.md)). Both run through the umbrella:

```bash
swissknifeman conformance plugin path/to/extension.json [--json]
swissknifeman conformance engine [--binding cao|claude-only|native] [--json]
```

Any other word is a usage error (exit 2).

## Plugin

`conformance plugin` runs `aicore ext conformance`. The manifest may be anywhere on disk, for example a third-party plugin
in a temporary folder; it is given as a path or as `--manifest PATH` (not both). The plugin is started like the host
would start it, with a cleaned environment. Each scenario prints a `check-result/v1` document with
`check_id` `ext.conformance.<scenario>`:

| Scenario | Proves |
| --- | --- |
| `manifest` | the manifest satisfies `extension/v1` |
| `describe` | the handshake answers with the declared id, version and protocol |
| `protocol-unsupported` | a protocol outside `min`..`max` is refused |
| `invoke` | a request gets a valid `plugin-response/v1` |
| `redelivery` | the same event delivered twice is handled idempotently (`skip` for a command plugin) |
| `crash` | the plugin answers `status: error` instead of exiting while it handles an event; a process that dies is reported as failed (exit code or signal), and the host then keeps the cursor and delivers the event again |
| `stdout-discipline` | stdout carries only the protocol document |
| `deadline` | the plugin stops at the deadline |
| `no-descendants` | no process outlives the call |
| `secrets` | a secret value never reaches stdout |

[`examples/extension.json`](examples/extension.json) is a manifest of kind `command` to start from. Every scenario is reported as `ok`, `fail` or
`skip` (it does not apply or cannot run); a failing one carries a remediation line.

The host-side guarantee of `crash` (the cursor does not move) is tested in the delivery tests of `aicore`; the scenario
judges the plugin's own process.

## Engine

`conformance engine` runs `orch.py conformance` for one binding of an orchestration engine and prints one line per
scenario: `pass`, `declared` (not tested, with a reason) or `n/a`.

| Binding | Result |
| --- | --- |
| `native` | scenarios are covered by a test or a recorded trace; none is merely declared without a reason |
| `cao`, `claude-only` | some scenarios stay `declared` with a reason until the parity trigger of orch |

The workspace-permissions scenario of `native` proves the scope check (what a role wrote outside its write set) on a fake
process, not OS-level confinement.

## Applying it to someone else's code

1. Write an `extension.json` for the plugin (start from the example) and keep the entrypoint relative to the manifest.
2. Run `swissknifeman conformance plugin extension.json --json` and read the failing `check_id`s.
3. Fix the plugin until the run is green; then it may be listed in a project's extensions.
