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

Fixed commands and launch-blocks pin **one** default selector per class. The model pool below is the admission list: any entry whose roles cover the required class is admitted (roles overlap, the highest class wins, a stronger model is never a stop). Entries match by id, `aliases` or regex `patterns`; `status: retired` leaves the pool. A model outside the pool is `ROUTE_MODEL_UNKNOWN`: extend the pool, never the plan. `auto` never substitutes a pin.

## Class pins

| Provider | economy | implementation | frontier |
|:--|:--|:--|:--|
| `claude-code` | `haiku` | `sonnet` | `opus` |
| `codex` | `gpt-5.6-luna` | `gpt-6-sol` | `gpt-6-astra` |
| `cursor` | `composer-2.5-fast` | `composer-2.5` | `claude-opus-5-thinking-high` |

## Model inventory

### `claude-code`

- `verified_at`: `2026-09-17`
- `source`: claude --help @ 2.1.266
- `verification`: cli-help-and-frozen-mapping; no machine-readable catalogue exists; 2026-10-01 pool extended by owner (fable, overlapping roles, family patterns)

| Model id | Roles | Notes |
|:--|:--|:--|
| `fable` | frontier, implementation, review, design, audit | patterns=`.*fable.*` |
| `opus` | frontier, implementation, review, design, audit | patterns=`.*opus.*` |
| `sonnet` | implementation, review | patterns=`.*sonnet.*` |
| `haiku` | economy, explore | status=confirmed; patterns=`.*haiku.*` |

### `codex`

- `verified_at`: `2026-09-23`
- `source`: docs/provider-support.md and Codex provider thread state
- `verification`: frozen mapping; gpt-6-sol observed in provider thread state; no machine-readable catalogue exists; 2026-10-01 pool extended by owner (gpt-6.1-sol frontier, overlapping roles)

| Model id | Roles | Notes |
|:--|:--|:--|
| `gpt-5.6-luna` | economy, explore | — |
| `gpt-5.6-terra` | implementation, review | — |
| `gpt-5.6-sol` | frontier, implementation, review, design, audit | — |
| `gpt-6-astra` | frontier, implementation, review, design, audit | patterns=`gpt-6(\.\d+)*-astra` |
| `gpt-6-sol` | implementation, review | — |
| `gpt-6.1-sol` | frontier, implementation, review, design, audit | patterns=`gpt-6\.[1-9]\d*-sol` |

### `cursor`

- `verified_at`: `2026-09-17`
- `source`: agent --list-models @ 2026.09.15-d2fe57e
- `verification`: 2026-10-01 pool extended by owner (overlapping roles, family patterns); ids not re-listed from the CLI

| Model id | Roles | Notes |
|:--|:--|:--|
| `composer-2.5-fast` | economy, explore | — |
| `composer-2.5` | implementation, review | — |
| `claude-opus-5-thinking-high` | frontier, implementation, review, design, audit | patterns=`claude-(opus|fable)-.*` |
| `grok-4.7` | frontier, implementation, review | patterns=`grok-4\.\d+`; live cli-config selectedModel; reasoning_effort=high maps through effort_selectors |
| `grok-4.6` | frontier, implementation, review | live cli-config selectedModel; effort=high is the Grok 4.6 alias of reasoning_effort |
| `gpt-5.6-sol-medium` | frontier, implementation, review, alternate | — |
| `auto` | routing-assist | policy=never-substitute-fixed-frontier |

**Auto policy** (`auto` routing-assist only):

- `allowed_for`: `economy`, `adhoc-explore`
- `forbidden_for`: `fixed-frontier-commands`, `plan-design`, `plan-audit`

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
