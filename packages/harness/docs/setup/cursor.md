# Setting up the environment Cursor

How to connect a project to swissknifeman like **to the third managed-to the provider**: permissions
(allowlist half), MCP hub, autonomy and trusted self-host — without rewriting `AGENTS.md`.

## Problem

U Cursor two independent axes:

1. **Allowlist half** (project-scoped) — `.cursor/cli.json` + `.cursor/permissions.json`.
2. **Approval mode / Run Mode** (not project-scoped) — global CLI config or UI IDE.

Harness publishes only (1). Autonomy in trusted-session requires launch flags **and** explicit
installations Run Mode in IDE (freeze D2).

## Profiles (semantic)

Source: `packages/harness/configs/common/profile-catalog.json` +
`packages/harness/configs/cursor/config/profile-bindings.json`.

| Profile | Fleet | `.cursor/cli.json` | `.cursor/permissions.json` | Launch-only mode |
|:--|:--|:--|:--|:--|
| `observe` | yes | read-biased allow | empty allowlists + block_instructions | plan / allowlist |
| `workspace-contained` | **everyday default** | scoped workspace allow | scoped MCP/terminal | auto-review |
| `trusted-full-access` | **only self-host-apply** | broad allow + deny floor | `*:*` wildcards | unrestricted + Run Everything |

Shared **deny floor** (all three profiles, D4): secrets (`.env*`, `*.pem`, `*.key`) — failure
even under `--force`.

## Installation: everyday (fleet)

### 1. Enable provider in project

```json
// .swissknife.json
{
  "providers": {
    "selection": {
      "cursor": { "enabled": true }
    }
  }
}
```

### 2. Onboard + sync

```bash
cd ~/projects/my-app
maind onboard --cwd              # memory, health hooks, MCP-channels
maind sync --project <id>        # .cursor/mcp.json ← hub servers (merge-only)
maind health --cwd               # provider:cursor trust
```

Skills: `skiller sync` → `.agents/skills/` (Cursor discovery, without `.cursor/skills` writer).

### 3. Permissions (workspace-contained)

Managed shapes are rendered harness profile engine in:

- `.cursor/cli.json` — `permissions.allow/deny` (CLI)
- `.cursor/permissions.json` — `mcpAllowlist`, `terminalAllowlist`, `autoRun`

Operator audit without recording:

```bash
harness doctor --settings --provider cursor --target .
```

::: warning Merge-only widening
Per-user and per-repo arrays **are concatenated** (E14.2). Repo-file does not narrow broad
user-level allowlist — only expands. Observe/workspace-contained do not guarantee
narrowing if the car is already wide user profile.
:::

## Trusted self-host (only umbrella)

`trusted-full-access` for `repo:swissknifeman` — explicit operation, not fleet default:

- `origin=operation`
- `operation_id=self-host-apply`
- `target_identity=repo:swissknifeman`

Any other target → `HARNESS_CURSOR_TRUSTED_NON_SELF_HOST_REFUSED`.

Artifacts (when applied): broad allowlists, `.cursor/rules/swissknifeman-{core,launch,packages}.mdc`.

### Launch (CLI)

```bash
cd /path/to/swissknifeman
agent --workspace "$(pwd)" \
      --model composer-2.5 \
      --force --sandbox disabled --trust --approve-mcps \
      'task:plan-run <PLAN-ID> <Pn.m>'
```

### IDE checklist (required for trusted)

1. Workspace = repository root (is not a subfolder without intent).
2. **Run Mode → Run Everything** (Settings; is not committed to the repo).
3. `maind health --cwd` — connected, `provider:cursor trust` green.
4. Model = pin from Routing (not `auto` for fixed frontier/implementation).
5. `.cursor/cli.json` deny floor on site - no secret refusal transient error.

## MCP

| Command | Where does it write? | When |
|:--|:--|:--|
| `maind sync` / `maind deploy` | `.cursor/mcp.json` | `providers.selection.cursor.enabled` |
| `harness mcp --target .` | `.mcp.json` | only Claude Code (legacy) |

Catalog presets: `packages/harness/configs/cursor/mcp/bindings.json` → secret refs only.

## Hooks

First ship: `security.safe-dirs` (`beforeShellExecution`, `failClosed: true`) in
`.cursor/hooks/`. Others lifecycle hooks — deferred (honest `unsupported` in matrix).

## Contact skiller and maind

- `skiller integrate` / `maind onboard` — cross-package onboarding once.
- `skiller sync` — managed skills in `.agents/skills`.
- `maind sync` — MCP + memory hooks; cursor channel when enabled provider.
- Budget listing: `skiller budget --provider cursor`.

## See also

- [Adapter Cursor](/skiller/adapters/cursor) — full integration cycle
- [Provider model roles](/task/reference/provider-model-roles) — pins and inventory
- [Permissions Claude Code](./claude) — sibling-provider (others surfaces)
