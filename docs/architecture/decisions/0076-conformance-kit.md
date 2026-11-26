# ADR 0076: Conformance kit for plugins and engines

## Status

Accepted

## Context

The plugin conformance of `aicore ext` lacked the case of a plugin that crashes while handling an event, and the engine
conformance of `orch` left three native scenarios declared without a test. Neither was reachable from one command.

## Decision

- **Crash scenario.** `aicore ext conformance` gets `crash`: the plugin should answer an error instead of exiting; a
  process that dies is classified by exit code or signal. The host-side guarantee (the cursor does not advance, the event
  is delivered again) is tested in the delivery tests.
- **Foreign plugins.** The manifest may be given as `--manifest PATH` anywhere on disk, besides the positional form.
- **Native engine.** The scenarios `child-process-cleanup`, `stdout-stderr-framing` and `workspace-permissions` are covered
  by tests on a fake argv. `cao` and `claude-only` stay `declared` with a reason until the parity trigger of orch.
- **Routes.** `swissknifeman conformance plugin <extension.json>` and `swissknifeman conformance engine [--binding B]` are
  routes of an alias in `configs/umbrella.json`.

## Alternatives considered

- Proving workspace permissions by OS confinement (Landlock): not now, its test is skipped where the kernel lacks support
  and a skip would count as a pass.
- Declaring the native scenarios forever: rejected, a declared scenario is a gap.

## Consequences

- A third-party plugin is judged by the same ten scenarios as ours.
- The workspace-permissions scenario proves scope detection, not confinement.

## Supersedes

None. Extends [ADR 0062](0062-engine-conformance-and-non-goals.md).
