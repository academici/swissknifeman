# Configuration

Each key declares a chain, allowed levels, merge strategy, reload mode,
invocation override policy and sensitivity. The work chain follows instance →
workspace → project → plan → run. The host chain follows instance → host.
The CLI defaults to the selected project, then workspace, then instance. Use
`--scope instance` or an explicit selector such as `project:<uuid>` to choose a
scope. [Key catalog](../reference/config.md)

## Resolution and writes

Resolution applies schema defaults, enabled pack fragments in ascending
priority, then stored entries from outer to inner scope. For keys that
permit invocation overrides, environment values, `--config` and `--set` are
applied last, in that order.

- `replace` takes the last applicable value. For array keys using `replace`,
  `config set --append` is available when the key allows that operation.
- `narrow` allows nearer scopes to tighten a ceiling using the key's declared
  order, bound or set intersection. An explicit shared-scope value can
  establish the ceiling. Without one, project, plan and run contributions
  must respect the applicable pack or schema baseline.
- `append` concatenates arrays in layer order. `append_unique` keeps the first
  occurrence of each value. Use ordinary `set` for these merge strategies.

An instance or workspace lock fixes the effective value at that point and
blocks later contributions, including invocation overrides. `config unset`
stores an explicit reset where the key permits it. `config remove` removes
that scope's contribution and reveals inheritance. When `x-skm.confirm`
(the `confirm` field in `x-skm` metadata) is true, `config set` prompts for
confirmation in an interactive session. Pass `--yes` to confirm
non-interactively. The actor still needs write permission.
[Settings rules](../architecture/config-engine.md#resolution-and-writes)

## Diagnostics and secrets

```sh
skm config explain runtimes.allowed --scope instance --detail full
skm config doctor
```

`explain` shows effective values and their provenance, including shadowed or
rejected contributions. `doctor` checks the registry, stored entries across
scopes, locks and restart-pending status for the responding process. It
requires instance-level `config.read`. Use `config import FILE --dry-run` to
inspect a proposed import before writing.

Use `secret://` references such as `secret://env/NAME` or
`secret://file//absolute/path` wherever a key expects a secret. The consuming
process resolves the reference when needed. `config explain` and config
exports show the reference only. Restart-required changes take effect on
restart. Run-frozen settings are captured in the run's bundle, while live
settings are read at their operational boundary. [CLI configuration reference](../reference/cli.md#cli-configuration-operations)
