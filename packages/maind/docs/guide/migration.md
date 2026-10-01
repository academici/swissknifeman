# Migration

## From brain (projects)

```bash
maind migrate from-brain ~/Vaults/Brain/.projects.json [--force]
```

Collects `config.json` (in root monorepo; legacy-name `.maind.json` is still being picked up)
from brain-project cache (real diagram brain is mapped to the format maind), prescribes
`integrations.brain` and **materializes the graph** (projects as nodes). Refused
overwrite existing `config.json` without `--force`.

## From agent-memory (daemon config)

```bash
maind migrate from-agentmemory ~/Vaults/Brain/.agentmemory [--force]
# alias: maind migrate from-skm ...
```

Transfers `iii-config.yaml` in `config/memory/iii-config.yaml` node, putting down
`service_name: maind`. **Source does not change** — transfer is non-destructive.

## Memory transfer Brain in maind (recommended script)

maind becomes the canonical memory house; Brain — client. Safe and reversible:

1. **Config**: `maind migrate from-agentmemory ~/Vaults/Brain/.agentmemory`.
2. **Data** (do not lose existing memory): copy (do not transfer!)
   `~/Vaults/Brain/data/state_store.db` and `stream_store/` in `maind/data/`.
3. **Ports**: maind holds the same `4111/4112` — clients Brain (him `.mcp.json`) continue
   work against the demon maind transparent. If you need to drive both demons for a while, set
   maind yours `AGENTMEMORY_PORT` in `.env`.
4. **Registration**: add `maind` in MCP-map Brain (`.mcp.json` / `CLAUDE.md`).

::: tip Reversibility
`.agentmemory/` in Brain remains in place (is marked as superseded), data is copied and
are not migrated - rollback is trivial. maind never kills someone else (not mine) demon.
:::
