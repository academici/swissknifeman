# Codex request lifecycle

Rollout messages alone cannot explain a client/provider delivery gap. The stdio observer reads
actual native app-server requests and notifications at the client boundary. It stores request,
thread, turn and process identity plus observed lifecycle transitions; it does not store prompts,
tool arguments, reasoning or answer content, and does not impose an execution deadline.

Configure an app-server client to launch this command in place of `codex app-server`:

```bash
python3 <skm-root>/packages/harness/scripts/codex-request-observer.py \
  --output-dir <project>/.harness/codex-requests/<connection-id> -- codex app-server
```

The script forwards stdin/stdout unchanged and inherits server stderr. Use a distinct directory
per connection. `events.jsonl` retains submitted/streaming/waiting-tool/completed/interrupted/
failed observations; `status.json` is a compact current view. An interrupt request is not a
terminal outcome: only `turn/completed` proves completion/interruption/failure. Connection loss
without terminal evidence records unknown.

```bash
python3 <skm-root>/packages/harness/scripts/codex-request-observer.py \
  --output-dir <project>/.harness/codex-requests/<connection-id> --status
```

A view older than 60 seconds retains its last observed phase but reports `current_state=unknown`
and `observation_stale=true`. Tool activity stays waiting-tool until the matching tool completes.
Absence of events proves neither inference activity nor zero token expenditure. The observer
uses the installed native protocol; it does not create a planner workflow or recover hidden events.

This launcher is available for app-server clients that expose their launch command. Hosted
clients and ordinary Codex CLI sessions are not automatically intercepted by repository code.
Enable capture at the owning client integration before attempting to diagnose another silent
interval. The original 2026-10-05 incident remains unexplained without its missing client/server
request events.
