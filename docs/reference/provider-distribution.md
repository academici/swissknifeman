# Provider distribution channels

Cross-package SSOT for **which skill-distribution channels each provider supports**.
Packages read this catalog through `core.provider.distribution`; they must not hardcode
provider-specific `if provider == "cursor"` skips in Python.

## Location

- Catalog: [`packages/aicore/configs/provider-distribution.json`](../../packages/aicore/configs/provider-distribution.json)
- Loader: `packages/aicore/lib/aicore/provider/distribution.py`
- Primary consumer: `packages/skiller/lib/skiller/publication.py` (`build_connect_distribution_plan`, `build_vendor_distribution_plan`)

## Shape

| Provider | Connect (marketplace) | Vendor (managed copy) | Discovery |
|:--|:--|:--|:--|
| `claude-code` | `.claude` marketplace | `.claude/skills` (via `claude_path`) | — |
| `codex` | `.agents/plugins/marketplace.json` (+ bundle) | `.agents/skills` (via `codex_path`) | — |
| `cursor` | — (none) | — (none) | `.agents/skills` native (D8) |

Adding a fourth provider or a new channel means extending the JSON catalog and the
`connect.mode` dispatch in publication — not scattering conditionals across packages.

## Related root configs

| File | Role |
|:--|:--|
| `packages/aicore/configs/provider-capabilities.json` | 37-capability matrix (native/adapted/unsupported) |
| `packages/aicore/configs/provider-distribution.json` | Skill connect/vendor/discovery channels |
| `packages/aicore/configs/provider-projection.json` | Instruction/route/command projection policies |
| `packages/planner/configs/command-routing.json` | planner command routing SSOT |
| `packages/harness/configs/common/profile-catalog.json` | Harness profile catalog SSOT |
| `config.json` (maind hub) | Fleet project registry, MCP inventory, `extra_servers` |

Package-local trees under `packages/*/configs/` remain **provider render bindings** (harness MCP/hooks/profile catalogs, task routing). Shared contracts that multiple packages must agree on live under repository-root `configs/`.
