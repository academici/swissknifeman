# Adapter: Cursor

Full cycle of integration with Cursor like **third managed-provider** (Codex-sibling):
skills through `.agents/skills`, environment via `.cursor/*`, without dual-write in
`.cursor/skills` and without rewriting Codex-owned `AGENTS.md`.

## Projection and discovery

| Surface | Channel | Note |
|:--|:--|:--|
| Skills | `.agents/skills/` | Cursor reads natively; skiller **not** writes `.cursor/skills` |
| Connect/vendor | — | Channels are declared in `configs/provider-distribution.json` (`discovery` only); without `if cursor` in Python |
| Instructions (extension) | `.cursor/rules/swissknifeman-*.mdc` | only self-host umbrella; trigger-scoped |
| MCP | `.cursor/mcp.json` | merge-only; writes `maind sync` when the provider is enabled |
| CLI permissions | `.cursor/cli.json` | only `permissions`; `deny` is worried `--force` |
| IDE allowlists | `.cursor/permissions.json` | merge-only; repo only **expands** user-level |

General repository contract Cursor is already picking up from `AGENTS.md`; in `.mdc` — only
`root.cursor.*` extension and the line precedence for `root.codex.*`.

## Installation (project)

### 1. Enable provider

B `.swissknife.json` project:

```json
{
  "providers": {
    "selection": {
      "cursor": { "enabled": true }
    }
  }
}
```

Everyday fleet-path - `workspace-contained`. `trusted-full-access` only for self-host
under the gate `self-host-apply` / `repo:<name>` (see [Harness setup: Cursor](/harness/setup/cursor)).

### 2. Skills (vendor/sync)

```bash
cd ~/projects/my-app

# Recommended path: managed sync in .agents/skills (Cursor reads natively)
skiller sync

# Legacy-compatibility
skiller vendor --agent cursor   # deprecated: copies to .cursor/skills — avoid dual-write
```

`render_cursor_publication` — ownership assertion: one writer on the skill tree, without
parallel write to `.agents` and `.cursor`.

### 3. MCP and memory (onboard/sync)

```bash
maind onboard --cwd ~/projects/my-app    # first connection: memory + MCP + health
maind sync --project my-app              # dokatka MCP in .cursor/mcp.json
maind health --cwd                       # round-trip + provider:cursor trust
```

Hub-servers (`plugin-core-maind`, `plugin-core-serena`) fall into `.cursor/mcp.json`
via provider deploy, not via legacy `harness mcp` (he only writes `.mcp.json` Claude).

### 4. Permissions (everyday and trusted)

Everyday (`workspace-contained`) — scoped allowlists in `.cursor/permissions.json` and
`.cursor/cli.json` without Run Everything to the fleet.

Trusted self-host (`trusted-full-access`) — wide allowlists **only** with explicit
`operation_id=self-host-apply` and `target_identity=repo:swissknifeman`. Inheritance
prohibited by the fleet (`HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN`).

Operator contract (shapes and audit):

```bash
harness doctor --settings --provider cursor --target .
```

Publication managed shapes for the project - via onboard/sync with enabled `cursor` in
`.swissknife.json`; details - [Harness setup: Cursor](/harness/setup/cursor).

## Autonomy: two tracks

| Track | Files | Launch / Run Mode |
|:--|:--|:--|
| Everyday onboard | `workspace-contained` shapes | Auto-review / allowlist; without `--force` to the fleet |
| Self-host trusted | `trusted-full-access` shapes | CLI: `--force --sandbox disabled --trust --approve-mcps`; IDE: **Run Everything** |

**Critical:** `approvalMode` and sandbox **not** project-scoped (E14.1). Mode - only
launch flags + UI Run Mode; harness writes allowlist/deny half. `deny` in `.cursor/cli.json`
— the only one project-scoped floor under `--force`.

Semantics launch: instruction `root.cursor.launch-and-autonomy` (agent-requested rule
`swissknifeman-launch.mdc` on self-host).

## Launch-block (cold-start)

Table Model class / Effort / Context — provider-neutral (plan-protocol §8). For Cursor
after the table - **Native Cursor command**:

```bash
agent --workspace <repo-cwd> \
      --model <model-selector> \
      --force --sandbox disabled --trust --approve-mcps \
      'task:<command> <arguments>'
```

- `--workspace`, not `-C` (freeze E3).
- Model pin: `composer-2.5-fast` / `composer-2.5` / `claude-opus-5-thinking-high` — see
  [Provider model roles](/task/reference/provider-model-roles).
- `auto` **not** replaces fixed frontier/implementation pin.

IDE checklist (trusted): workspace root → Run Everything → MCP health → pinned model.

## Models and Auto

Hand-verified inventory in `packages/task/configs/command-routing.json` →
`mappings.cursor.model_inventory`. Full guide (pins + inventory + Auto policy):
[Provider model roles](/task/reference/provider-model-roles).

## Delta-skill files

Specifics Cursor — in `adapters/cursor.md` inside the skill (overrides for `.cursor/rules`).
Main `SKILL.md` remains provider-neutral. Format - in
[adapter delta specifications](../guide/adapter-deltas).

## Diagnostics

```bash
skiller budget --provider cursor --target .
maind health --cwd
harness doctor --settings --provider cursor --target .
python3 packages/task/scripts/render-provider-commands.py --check --root .
```

## See also

- [Harness setup: Cursor](/harness/setup/cursor) — permissions, MCP, profiles
- [Provider model roles](/task/reference/provider-model-roles) — design/exec/audit/economy
- [Provider commands](/task/reference/provider-commands) — generated command projections
