# Writing an integration target

An integration target projects neutral configuration into an interactive
client's bound checkout and translates its native hook protocol. The host
`IntegrationTarget` contract supplies a target ID and renderer version,
`capabilities()`, deterministic `render(inputs)`, hook payload normalization
and decision rendering, client-layer inspection, instruction paths, and
optional session summaries. Return `None` when no summary can be established.
[Target port](../../src/skm/modules/integrations/ports.py) ·
[Integration guide](integrations.md)

## Projection and hooks

- Declare each surface in the target's `capabilities.toml`, with client version
  and verification date. Skip unsupported surfaces and record their diagnostic.
- Return checkout-relative paths with explicit file, block or key ownership.
  Use the projection host operations for preview, apply, drift, adoption and
  removal. They handle journaled writes, pre-images and ownership checks.
  Preserve foreign content and keep credentials as references.
- Translate native events to normalized hook events and decisions back to the
  client wire format. Enforcement must fail closed when authority cannot be
  established. Inspect user settings through the read-only ports.

Check fixture rendering, ownership and drift behavior, repeat apply, and
native input/output on the exact client version. The target manifest records
projection and hook support. Unattended launch capability requires separate
runtime proof bound to a `VerificationContext`.
[Built-in declarations and hook codecs](../reference/integration-capabilities.md) ·
[Hook checks](../measurements/hook-startup.md)

For executable plugin packaging, declare the host-side `integration_target`
component in `PluginManifest` and run `skm plugins lint <distribution-or-source-directory>`.
This baseline's supported target registry contains the built-ins, and the
target port and DTOs are internal. An externally packaged target needs the
public contract and host wiring before it can be used through the shipped
CLI and hook entry points. [Plugin manifest](../../src/skm/plugin_api/manifest.py) ·
[Public plugin imports](../../src/skm/plugin_api/__init__.py) ·
[Host target registry](../../src/skm/bootstrap/hook.py)
