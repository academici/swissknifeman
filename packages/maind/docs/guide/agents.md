# Agents

Register of running node agents - in `~/.maind/agents.json` (atomic record). Status
agent **not stored**, and is derived when reading from the age of the last The heartbeat and liveliness
pid — file stores only facts.

## Life cycle

```bash
maind agents register vault-architect --project brain --pid 12345 --kind worker
maind agents heartbeat vault-architect      # update last_heartbeat
maind agents list [--all] [--json]          # without --all hides dead
maind agents kill vault-architect [--force] # SIGTERM (or SIGKILL) + remove from the registry
```

## States

| Status | Condition |
|:--|:--|
| `alive` | fresh heartbeat, pid is alive (or not specified) |
| `stale` | age heartbeat > `heartbeat_interval_ms × 3` |
| `dead` | pid is specified, but the process does not exist |

`heartbeat_interval_ms` is taken from `agents.heartbeat_interval_ms` config (default 30000).
`reap()` deletes `dead`/`stale` agents.

## API (`agents.py`)

```python
register(env, "id", pid=..., project=..., kind=...)   # upsert, registered_at once
heartbeat(env, "id")
listing(env, config)                                  # each agent with a field state
kill(env, "id", force=False)
reap(env, config)                                     # will return the number of deleted
```

## Communication with the graph

Agent from `projects[].agents` materializes in the graph as `agent:<id>` with edge
`belongs_to` to the project - see. [Graph](./graph).

Next: [Projects →](./projects)
