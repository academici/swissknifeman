# Provider projection policies

Cross-package SSOT for **how each provider projects shared semantics** (instructions,
route evidence, command invocation). Packages read this catalog through
`core.provider.projection`; they must not hardcode provider-specific `if/elif` dispatch.

## Location

- Catalog: [`configs/provider-projection.json`](../../configs/provider-projection.json)
- Loader: `core/provider/projection.py`
- Consumers:
  - `packages/harness/lib/harness/instructions.py` — `project_common_instructions`
  - `packages/task/lib/task/route_evidence.py` — route adapter + semantic prefix
  - `packages/task/lib/task/command_render.py` — invocation style dispatch

## Shape

| Provider | Project common instructions | Route prefix | Invocation style |
|:--|:--|:--|:--|
| `claude-code` | yes | `/` | `slash` |
| `codex` | no (on-demand via packages/skills/commands) | `$ ` | `dollar` |
| `cursor` | no (Codex-sibling) | *(empty)* | `semantic` |

Adding a fourth provider means extending the JSON catalog and registering the
invocation renderer — not scattering conditionals across packages.

## Related root configs

| File | Role |
|:--|:--|
| `configs/provider-capabilities.json` | 36-capability matrix |
| `configs/provider-distribution.json` | Skill connect/vendor/discovery channels |
| `configs/provider-projection.json` | Instruction/route/command projection policies |
| `configs/command-routing.json` | Task command routing SSOT |
| `configs/profile-catalog.json` | Harness profile catalog SSOT |

Package-local trees under `packages/*/configs/` remain **provider render bindings**
(harness MCP/hooks, task schemas). Shared contracts that multiple packages must agree
on live under repository-root `configs/`.
