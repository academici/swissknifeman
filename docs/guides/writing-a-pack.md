# Writing a pack

A pack distributes versioned data such as skills, steering rules, profiles,
workflows, plan templates, prompt blocks, integration bundles, model
catalogs or model guideline profiles. Use a directory with `pack.toml` at its root. Declare the
`urn:skm:extensions:pack:v1` schema, slug, version, title, description,
publisher, trust, SPDX license and `requires_skm` version constraint. Place
resources in the layout for their kind. Use
`[[overrides]]` to name each overridden kind and key and give a reason.
[Example manifest](../../resources/packs/core/pack.toml) ·
[Pack and resource contracts](../architecture/runtimes-context-extensions.md#resource-registry)

## Install and inspect

Use a new version when resource bytes change. Preview the schema, trust and
resource checks with a dry run:

```sh
skm ext install "$pack_dir" --trust third_party --dry-run
skm ext install "$pack_dir" --trust third_party
skm config set extensions.packs.enabled '["example-pack"]' --scope "workspace:$workspace_id"
skm ext list --resources
```

Use the manifest slug and the workspace UUID in the example. Inspect resources
with `skm ext show` or `skm ext resolve`. Pack trust and declared overrides
govern which resources may shadow an existing resource. Installed versions
are immutable and runs pin the resolved pack versions. Keep scripts projected
by an integration bundle as data. The application does not execute them.

Only built-in and operator packs can carry a `[config]` fragment. Pack
selection, security ceilings, isolation and secret keys are excluded where
the settings catalog disallows pack contributions. Profiles and skills
remain subject to permission ceilings. [Operator overlays](../extensions/overlays.md) ·
[Configuration](configuration.md)

Use `ext install --dry-run` for data-only packs. If the distribution also has
a separate executable plugin, run `skm plugins lint` on that plugin. Runtime
`capabilities.toml` and `VerificationContext` evidence belong to the adapter
path. A pack can supply the model catalog. [Runtime adapter guide](writing-a-runtime-adapter.md)
