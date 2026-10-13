# Healthcheck — connection between the project and the hub

If memory is not raised in the project + maind MCP, development in progress «past» column/memory → spaces.
`maind health` diagnoses this. Check **does not block** work - always prints the status and
tips.

## Diagnostics

```bash
maind health --cwd                 # from the project directory (match by local_path)
maind health --project flexcrm     # by id
maind health --project flexcrm --json
maind health --cwd --plan-repair   # show the repair steps (read-only)
maind health --cwd --apply-repair  # increase memory + add MCP-servers
maind health --project flexcrm --strict   # exit 1, if not connected (for CI)
```

Three axes are checked: is the memory daemon responding? agentmemory MCP in the project? maind MCP in the project?

| Status | Meaning |
|:--|:--|
| `connected` | memory available And both MCP-servers configured |
| `partial` | there is one thing (for example, MCP without daemon) |
| `standalone` | neither demon nor MCP — project works autonomously |

Example output:

```
⚠ mAInd health — project:flexcrm (scope project:flexcrm)
  [ok  ] memory daemon (http://127.0.0.1:4111)
  [FAIL] agentmemory MCP in the project
  [ok  ] maind MCP in the project
  status: partial
    → no agentmemory MCP in the project → maind sync --only mcp --project flexcrm
```

`--plan-repair` prints the steps (`--json`: `{"project", "actions": [{"kind", "target", "detail"}]}`) and changes nothing.
`--apply-repair` increases memory (if lying) and executes `sync --only mcp` for the project, then repeats the report.
`--fix` is a deprecated alias of `--apply-repair` (warning `MAIND_HEALTH_FIX_DEPRECATED`).

## Delivery «priority №1» to projects

So that the project itself reminds about the connection with the hub, two providers (are called from `maind sync`,
source of truth - `templates/health/*`):

- **health-doc** — managed block (marker `maind:healthcheck`) in `<project>/CLAUDE.md`;
  idempotent by content-hash, someone else's file text is saved.
- **health-hook** — opt-in SessionStart-hook (`observability.session_start_health_hook=true`).
  Default sync unregisters and `.claude/maind-health.sh`; run full scan
  manually via `maind health --deep` after installation, environmental changes, or symptoms.

```bash
maind sync --project flexcrm --only health-doc,health-hook
maind sync --all --only health-doc,health-hook --mode update   # update outdated blocks
```

## Troubleshooting

- `memory daemon not running The project does not have` → `maind start --only memory`.
- `no … MCP in the project` → `maind sync --only mcp --project <id>` (or `maind health --apply-repair`).
- `missing-path` →  `local_path` or the path does not exist - correct `config.json`.

Next: [Sync →](./sync)
