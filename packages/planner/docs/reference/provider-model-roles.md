# Provider model roles

Hand-verified model inventories and fixed class pins for the managed providers.
Neutral routing in `packages/planner/configs/command-routing.json` uses `model_class` (`economy` < `implementation` < `frontier`) plus `effort`; each provider block below maps those classes to native selectors.

Generated from the validated command-routing mappings. Do not edit the tables manually.

## Semantic roles

| Work kind | Neutral class | Typical commands |
|:--|:--|:--|
| Economy / ad-hoc explore | `economy` | low-risk fixes, scans |
| Implementation / execution | `implementation` | `planner:dev`, `planner:plan-run`, `planner:plan-close` |
| Design / audit / review | `frontier` | `planner:design`, `planner:plan-design`, `planner:plan-audit`, `planner:review` |

Fixed commands and launch-blocks pin **one** default selector per class. The model pool below is the admission list: any entry whose roles cover the required class is admitted (roles overlap, the highest class wins, a stronger model is never a stop). Entries match by id, `aliases` or regex `patterns`; `status: retired` leaves the pool. A model outside the pool is `ROUTE_MODEL_UNKNOWN`: extend the pool, never the plan. `auto` never substitutes a pin.

## Class pins

| Provider | economy | implementation | frontier |
|:--|:--|:--|:--|
| `claude-code` | `haiku` | `sonnet` | `opus` |
| `codex` | `gpt-6-luna` | `gpt-6-sol` | `gpt-6-astra` |
| `cursor` | `composer-2.5-fast` | `composer-2.5` | `claude-opus-5-thinking-high` |
| `grok` | `grok-4.5` | `grok-4.6` | `grok-4.7` |

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

- `verified_at`: `2026-10-22`
- `source`: https://developers.openai.com/api/docs/models/gpt-6-luna and the local Codex model cache on 2026-10-22; earlier docs/provider-support.md and Codex provider thread state
- `verification`: gpt-6-luna confirmed on the official OpenAI model page and in the local Codex model cache on 2026-10-22 as economy/explore. No launch of the model was run for this record. Earlier frozen mapping remains: gpt-6-sol observed in provider thread state; 2026-10-01 pool extended by owner (gpt-6.1-sol frontier, overlapping roles). 2026-10-30 owner extended the pool with the exact gpt-6.1-terra implementation/review selector for AgenTools PLAN2; admission only, without a live model launch or a capability comparison. The pre-integration main working tree also admitted frontier/design/audit for this exact Terra selector; those local roles are retained without a new capability or live-launch claim.

| Model id | Roles | Notes |
|:--|:--|:--|
| `gpt-6-luna` | economy, explore | status=confirmed; Preferred Codex economy selector, including ordinary context-scout. Explicit executor, reviewer and owner model routes are unchanged. Not a comparative benchmark. |
| `gpt-5.6-luna` | economy, explore | Previous economy pin. Kept in the inventory; not the preferred selector. |
| `gpt-5.6-terra` | implementation, review | — |
| `gpt-5.6-sol` | frontier, implementation, review, design, audit | — |
| `gpt-6-astra` | frontier, implementation, review, design, audit | patterns=`gpt-6(\.\d+)*-astra` |
| `gpt-6-sol` | implementation, review | — |
| `gpt-6.1-terra` | frontier, implementation, review, design, audit | status=owner-authorized; Exact owner-selected route admitted on 2026-10-30 for AgenTools PLAN2. No family pattern or default class pin change. Existing main working-tree admission for frontier/design/audit retained during integration on 2026-11-01. |
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

### `grok`

- `verified_at`: `2026-10-03`
- `source`: grok --help / grok models and ~/.grok/config.toml [models].default
- `verification`: CLI --model plus config.toml default; live session GROK_SESSION_ID; agent is the same grok binary

| Model id | Roles | Notes |
|:--|:--|:--|
| `grok-4.5` | economy, explore | patterns=`grok-4\.5.*` |
| `grok-4.6` | implementation, review | patterns=`grok-4\.6.*` |
| `grok-4.7` | frontier, implementation, review, design, audit | patterns=`grok-4\.7.*` |

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
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'planner:<command> <arguments>'
```

IDE checklist before an autonomous session:

1. Open the intended repository root as the workspace.
2. Set Run Mode to **Run Everything** (Settings → Run Mode).
3. Confirm `.cursor/mcp.json` contains hub servers.
4. Pin the routed model; do not substitute `auto` for fixed frontier/implementation pins.
5. For CLI launches, pass the full flag set above; partial flags are not a trusted launch.

Full install and profile shapes: see your environment's Cursor adapter setup.

## Grok launch contract (trusted self-host)

Grok Build CLI (`grok`, PATH alias `agent`) is a managed provider. Skills are discovered from `.agents/skills` (no `.grok/skills` writer). Project `.grok/config.toml` carries `[permission] deny` and MCP only; `[ui] permission_mode` is user-level in `~/.grok/config.toml` and is not read from the project file. `--always-approve` is a trusted-session launch flag. The deny floor still applies. Cursor's `agent --workspace` is a different binary (`cursor-agent`); identity is `GROK_SESSION_ID`.

| Parameter | Value |
|:--|:--|
| Workspace (`cwd`) | repository root — `grok --cwd <repo-cwd>` |
| Model | class pin from table above (`grok-4.5` / `grok-4.6` / `grok-4.7`) |
| Effort | from plan Routing / command frontmatter; fallback `[models].default_reasoning_effort` |
| CLI autonomy | `--permission-mode default|acceptEdits`, or `--always-approve` on trusted self-host |
| Binary | `grok` or Grok `agent`; never Cursor `cursor-agent` |

**Native Grok command** (copy after the metadata table in a launch-block):

```bash
grok --cwd <repo-cwd> --model <model-selector> --always-approve '/planner:<command> <arguments>'
```

1. Open the intended repository root (`--cwd`).
2. Confirm `.grok/config.toml` and hub MCP.
3. Pin the routed model; do not substitute Cursor-inventory grok-4.x ids for provider grok.
4. Pass `--always-approve` only on a trusted self-host; the deny floor remains.
