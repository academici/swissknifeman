# statusline context-notify — window to actual context percentage

Status line Claude Code (`model · directory · bar · N%`) **plus** OS notification when
crossing the threshold strip. Needed because the actual percentage of context
(`context_window.used_percentage`) gets **only** statusline: none of hook-events
does not receive context fields as input - including `PreCompact`/`PostCompact`.

Statusline **does not spend context tokens** («The status line runs locally and does not consume
API tokens»), therefore its price is measured in milliseconds: the script runs on each message
assistant in the path with a debounce of 300 ms.

## Layout

```
statusline/context-notify.sh   string renderer + lane crossing detector
statusline/env.ini             thresholds, cooldown, bar width, DEBUG (NOT overwritten)
hooks/notify/notify.sh         delivery (is reused, not duplicated):
                               Linux notify-send · macOS osascript/terminal-notifier ·
                               WSL/Windows toast; no backend → quiet
```

Status - **per session**: `${XDG_RUNTIME_DIR:-/tmp}/claude-statusline/<session_id>.state`,
record atomic (`tmp` + `mv`), cleaning older than a day - only at the start of the session.

## Enable (opt-in, per-project)

```bash
harness hooks --global                                  # files to the machine (once)
harness hooks --target . --statusline context           # key statusLine in the project
harness hooks --target . --statusline off               # remove (only your key)
```

The key is written in **`.claude/settings.local.json`** — this is a machine-local preference
terminal (like `outputStyle`), not a team convention (like `plansDirectory`), therefore
sharable `settings.json` is not touched. The key is occupied by ANOTHER value → the team respects him
(skip + warn), does not overwrite.

## Trigger rule

- Strip = how many thresholds from `THRESHOLDS` passed (`80,90` → 0 / 1 / 2).
- Notice - on **growth** stripes and not more often `COOLDOWN_MIN`. Transition suppressed by cooldown
  is not lost: the status bar does not increase, and the alert will go away as the first render after the cooldown.
- Percentage drop (after `/compact`) resets the bar down - a new acceleration will notify again.
- `used_percentage` happens `null` (session start, after `/compact`) — then the bar is not drawn and
  threshold decision **not accepted**. `null` — this is not `0%`.

## Boundaries

- Script **never falls out**: any error → minimum string and `exit 0`.
- Exactly **one** external render call (`jq`); `git`/`curl`/`python3`/network in hot path
  are prohibited - every extra call is visible to the user as a slowdown UI.
- Notification delivery **disconnected** (`setsid … &`): runtime cancels statusline-script on
  in the middle of a new update, the synchronous side effect would be lost along with it.
- Segments beyond context (git-branch, price, rate-limits) intentionally not added: every
  segment - latency in the hot path.
- Kill-switch — `disableAllHooks` in settings: suppresses hooks **and any custom status line**.
