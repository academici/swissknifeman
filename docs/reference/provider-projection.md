# Provider projection policies

Cross-package SSOT for **how each provider projects shared semantics** (instructions
and command invocation). Packages read this catalog through
`core.provider.projection`; they must not hardcode provider-specific `if/elif` dispatch.

## Location

- Catalog: [`packages/aicore/configs/provider-projection.json`](../../packages/aicore/configs/provider-projection.json)
- Loader: `packages/aicore/lib/aicore/provider/projection.py`
- Consumers:
  - `packages/harness/lib/harness/instructions.py` — `project_common_instructions`
  - `packages/planner/lib/planner/command_render.py` — invocation style dispatch

## Shape

| Provider | Project common instructions | Invocation style |
|:--|:--|:--|
| `claude-code` | yes | `slash` |
| `codex` | no (on-demand via packages/skills/commands) | `dollar` |
| `cursor` | no (Codex-sibling) | `semantic` |
| `grok` | no | `slash` |

Grok is already in [`packages/aicore/configs/provider-projection.json`](../../packages/aicore/configs/provider-projection.json).
A further provider still means extending that catalog and registering its
invocation renderer, not scattering conditionals across packages.

Grok skills stay on `.agents/skills`. planner does not write a fourth skill tree:
`plan_grok_command_render` publishes only
`packages/planner/adapters/grok/publication-lock.json` (`writer: none`). The live
slash menu comes from the installed `planner` plugin `commands/` directory.
Grok advertises a plugin command as `/<plugin>:<name>` when that bare name also
exists on another skill. `packages/planner/adapters/grok/prefix-hold` reserves the
ten planner names, so `grok inspect` reports every planner command as
`/planner:design`, `/planner:dev`, `/planner:fix`, `/planner:research`, `/planner:review`,
`/planner:make-workflow`, `/planner:plan-design`, `/planner:plan-run`, `/planner:plan-close`,
and `/planner:plan-audit`. The hold skills are `/prefix-hold:<name>` and are not
the workflow. Cursor stays on semantic invocation (`planner:plan-design`) with
Cursor model pins; copying those skill wrappers into Grok would pin the wrong
models and forbid slash syntax.

## Related root configs

| File | Role |
|:--|:--|
| `packages/aicore/configs/provider-capabilities.json` | 36-capability matrix |
| `packages/aicore/configs/provider-distribution.json` | Skill connect/vendor/discovery channels |
| `packages/aicore/configs/provider-projection.json` | Instruction/command projection policies |
| `packages/planner/configs/command-routing.json` | planner command routing SSOT |
| `packages/harness/configs/common/profile-catalog.json` | Harness profile catalog SSOT |

Package-local trees under `packages/*/configs/` remain **provider render bindings**
(harness MCP/hooks, task schemas). Shared contracts that multiple packages must agree
on live under repository-root `configs/`.
