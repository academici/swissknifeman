# Configuration engine

Algorithms live in [`platform/config/`](../../src/skm/platform/config/) and
[`modules/settings/`](../../src/skm/modules/settings/).
[ADR 0010](../adr/0010-one-config-engine.md) records the single-engine decision.
Section schemas are the catalog under `src/skm/schemas/settings/`.

## Components

| Component | Location / boundary | Responsibility |
|---|---|---|
| Section schemas | `src/skm/schemas/settings/` | Types, defaults and `x-skm` metadata |
| Registry | `platform/config/registry.py` | Build and validate `KeySpec` inventory |
| Resolver and merge | `platform/config/{resolver,merge}.py` | Pure layers-to-values resolution with provenance |
| Effective config | `platform/config/effective.py` | Typed section views, digest and generation |
| Sources | `platform/config/sources/` | Read defaults, packs, bootstrap, env and invocation overrides |
| Store | `ConfigStore` port, PostgreSQL adapter | Read scope entries inside the current UoW |
| Administration | `modules/settings/` | Authorized writes, history, locks, import/export |
| Surfaces | CLI, API, web Settings | Render the same registry and provenance |

## Scope chains

| Chain | Far to near | Storage |
|---|---|---|
| Work | `default → pack → instance → workspace → project → plan → run → invocation` | Schema defaults, resource packs, DB scopes, invocation |
| Host | `default → pack → instance → host → invocation` | Same mechanism with host-scoped DB entries |

Each key belongs to exactly one chain. Capacity versus project parallelism is a
module-level decision, not a mixed scope chain. Bootstrap locates the instance,
database, credentials and machine paths before DB configuration is available.
Portable exports omit those paths; secrets remain `SecretRef` values.
Set `logging.level` and `logging.format` at instance or host scope through the settings catalog.

## Metadata and merge

| Metadata | Contract |
|---|---|
| `chain`, `levels` | Exactly one chain and permitted storage levels |
| `merge` | `replace`, `deep_merge`, `append`, `append_unique`, `union`, `narrow` |
| `reload` | `live`, `run_frozen`, `restart` |
| `override` | Whether invocation/env/CLI can contribute |
| `sensitivity`, `portable` | Redaction and export policy |
| `lockable`, `nullable` | Lock policy; absence without a default, not JSON null |
| `write_permission`, `validators` | Extra rights and cross-key validation |
| `deprecated`, `ui` | Migration diagnostics and schema-driven form hints |

| Strategy | Rule |
|---|---|
| `replace` | Nearest contribution wins; explicit append is allowed for replace arrays |
| `append` / `append_unique` | Ordered accumulation; unique keeps first occurrence |
| `union` | Include every contribution and schema default; nearer layers cannot delete members |
| `deep_merge` | Merge fields recursively; validate partial contributions and then the complete result |
| `narrow` | Intersection or configured restrictive numeric/boolean/enum ordering |

Removing an entry reveals the farther contribution. Explicit `unset` resets to
the schema default; it cannot hide that default and is invalid for monotonic
`narrow`/`union`. Locks prevent nearer overrides. Invalid effective values fail
closed. Project/plan/run contributions without farther explicit values can only
narrow the default/pack baseline (E30). Only trusted builtin/operator packs
provide configuration; pack data cannot raise security ceilings.

## Resolution and writes

```python
def resolve(registry: SettingsRegistry, chain: ScopeChain, layers: Sequence[Layer], *,
            keys: Iterable[str] | None = None, generation: int, pack_generation: int,
            expand: Callable[[str], str] | None = None) -> EffectiveConfig: ...
```

The pure resolver receives already loaded layers of one scope chain (`keys` defaults
to every key of that chain); `expand` rewrites `~` and `${state_dir}` in path keys. `EffectiveConfig` carries values,
provenance, diagnostics, generation and a canonical digest. Modules read typed
sections through `ctx.config.section(SectionType)`. Each write records history,
an event and a generation increment in the same transaction. Cache keys include
scope-chain IDs and generation. Unknown keys and forbidden levels are errors.

Run bundles pin `run_frozen` values; live revocations are checked again immediately.
E55 permits only a fixed server allowlist of operational overrides at a drained,
CAS-protected checkpoint. Workflow/check/acceptance structure changes require a
new published resource/revision and run. Existing receipts, reservations, spent
amounts, counters and deadline origins are preserved.
