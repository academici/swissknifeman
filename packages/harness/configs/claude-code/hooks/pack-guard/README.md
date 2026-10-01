# pack-guard — layer 2 mutation-protection generated-assets (optional)

Optional **Python-hook** Claude Code (`PreToolUse`), which catches the edit generated-file
agent-pack'a **to** how it will happen - unlike layer 1 (`lock_drift()` /
[`harness agent-packs doctor --drift`](../../../lib/harness/agentpacks.py) / `pack_drift()` in
`maind analyze`), which catches the edit **after the fact**. Default **NOT installed**:
is included explicitly per-project, recommendation - overnight/unattended dev-loop.

## Modes

| Mode | Behavior |
|:--|:--|
| `off` (default) | hook is not registered in the project |
| `warn` | stderr-warning when editing generated-file, **does not block** |
| `strict` | **blocks** Edit/Write/MultiEdit/NotebookEdit by generated-file (exit 2) |

`user_owned`-files (overlays - extension point base+overlay, D11) guard'ohm does NOT touch: them
can and should be edited.

## Solution - by lock-project file

Hook reads `<project>/.claude/agent-pack.lock.json`, collects `packs[].files[].target` WITHOUT
`user_owned` — this is it managed-set. Same analysis as `_protected_sets()` in
[`../run-report/_lib.py`](../run-report/_lib.py) (conscious small take - autonomy
hook, PYTHONPATH monorepo in `~/.claude/hooks` not available). No lock'a / he's broken / file not under
pack control → pass (exit 0), never blocks «just in case».

## Files

| File | Role |
|:--|:--|
| `pack-guard.py` | PreToolUse-hook: stdin → solution for lock → exit 0/2 (+ stderr-message) |
| `env.ini` | `MODE` (off/warn/strict). Per-project override in `.claude/pack-guard.env.ini` |

## Installation / enable

```bash
harness hooks --global                              # copies the hook to ~/.claude/hooks/pack-guard/
harness hooks --target . --pack-guard strict         # include in the project (env.ini + registration PreToolUse)
harness hooks --target . --pack-guard off            # turn off (kill-switch, hook remains registered but inactive)
```

## I/O-contract (for debugging)

Hook reads JSON payload PreToolUse on stdin (`cwd`/`tool_name`/`tool_input`), solution - by
lock-file `<cwd>/.claude/agent-pack.lock.json`. Doesn't write anything to disk.

```bash
echo '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/.claude/agents/x.md"}}' \
  | python3 pack-guard.py   # strict + managed-file → exit 2, reason is stderr
echo 'not json{' | python3 pack-guard.py   # → exit 0 (never drops the session)
```

## Fair limits (we will not overpromise)

- **Double parsing lock'and with `run-report/_lib.py`** — conscious (both hooks are autonomous in
  `~/.claude/hooks`, PYTHONPATH monorepo not available there); there is no one to catch the drift between copies
  automatically (see D8 for a similar case `_usage.py` — here sync-no script,
  parsing is simple ~15 lines).
- **Message to stderr — best-effort**, does not contain the exact path to the specific overlay
  file (it carries `Extension-points:` in the provenance-header) — only the name of the pack.
