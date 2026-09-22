# Provider model roles

Hand-verified model inventories and fixed class pins for the three managed providers.
Neutral routing in `packages/task/configs/command-routing.json` uses `model_class` (`economy` < `implementation` < `frontier`) plus `effort`; each provider block below maps those classes to native selectors.

Generated from the validated command-routing mappings. Do not edit the tables manually.

## Semantic roles

| Work kind | Neutral class | Typical commands |
|:--|:--|:--|
| Economy / ad-hoc explore | `economy` | low-risk fixes, scans |
| Implementation / execution | `implementation` | `task:dev`, `task:plan-exec`, `task:plan-close` |
| Design / audit / review | `frontier` | `task:design`, `task:plan-design`, `task:plan-audit`, `task:review` |

Fixed commands and launch-blocks pin **one** selector per class. Inventory-only models never substitute a missing pin (fail-closed, same as an unknown spelling in plan-protocol).

## Class pins

| Provider | economy | implementation | frontier |
|:--|:--|:--|:--|
| `claude-code` | `haiku` | `sonnet` | `opus` |
| `codex` | `gpt-5.6-luna` | `gpt-5.6-terra` | `gpt-5.6-sol` |
| `cursor` | `composer-2.5-fast` | `composer-2.5` | `claude-opus-5-thinking-high` |

## Model inventory

### `claude-code`

- `verified_at`: `2026-09-17`
- `source`: claude --help @ 2.1.266 + command-routing.json D84
- `verification`: cli-help-and-frozen-mapping; no machine-readable catalogue exists

| Model id | Roles | Notes |
|:--|:--|:--|
| `opus` | frontier, design, audit | — |
| `sonnet` | implementation | — |
| `haiku` | economy | status=confirmed |

### `codex`

- `verified_at`: `2026-09-17`
- `source`: plans/2026.07.19-DUAL-PROVIDER/plan.md#D84
- `verification`: frozen D84 mapping; no machine-readable catalogue exists

| Model id | Roles | Notes |
|:--|:--|:--|
| `gpt-5.6-luna` | economy | — |
| `gpt-5.6-terra` | implementation | — |
| `gpt-5.6-sol` | frontier, design, audit | — |
| `gpt-6-astra` | frontier, design, audit | — |

### `cursor`

- `verified_at`: `2026-09-17`
- `source`: agent --list-models @ 2026.09.15-d2fe57e

| Model id | Roles | Notes |
|:--|:--|:--|
| `composer-2.5-fast` | economy, explore | — |
| `composer-2.5` | implementation | — |
| `claude-opus-5-thinking-high` | frontier, design, audit | — |
| `grok-4.7` | frontier | live cli-config selectedModel; reasoning_effort=high maps through effort_selectors |
| `gpt-5.6-sol-medium` | alternate | — |
| `auto` | routing-assist | policy=never-substitute-fixed-frontier |

**Auto policy** (`auto` routing-assist only):

- `allowed_for`: `economy`, `adhoc-explore`
- `forbidden_for`: `fixed-frontier-commands`, `plan-design`, `plan-audit`, `task:review`

`auto` never substitutes a fixed `frontier` or `implementation` pin in a launch-block or fixed command.

## Cursor launch contract (trusted self-host)

Approval mode and IDE Run Mode are **not** project-configurable (see freeze E14.1). Autonomy comes from launch flags plus a documented IDE checklist; the `deny` floor in `.cursor/cli.json` survives `--force`.

| Parameter | Value |
|:--|:--|
| Workspace (`cwd`) | repository root — `agent --workspace <repo-cwd>` (not `-C`) |
| Model | class pin from table above |
| Effort | from plan Routing / command frontmatter |
| CLI autonomy | `--force --sandbox disabled --trust --approve-mcps` |
| IDE Run Mode | **Run Everything** (trusted self-host only; UI-owned, not a repo file) |

**Native Cursor command** (copy after the metadata table in a launch-block):

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:<command> <arguments>'
```

IDE checklist before an autonomous session:

1. Open the intended repository root as the workspace.
2. Set Run Mode to **Run Everything** (Settings → Run Mode).
3. Confirm `.cursor/mcp.json` contains hub servers (`maind health --cwd`).
4. Pin the routed model; do not substitute `auto` for fixed frontier/implementation pins.
5. For CLI launches, pass the full flag set above; partial flags are not a trusted launch.

Full install and profile shapes: [Cursor adapter](/skiller/adapters/cursor) and [Harness setup: Cursor](/harness/setup/cursor).
