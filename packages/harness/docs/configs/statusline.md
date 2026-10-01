# Statusline: context and notifications

Status line Claude Code, which shows **actual context percentage**, and
OS notification when percentage crosses threshold. Installed with hooks
(`harness hooks --global`), turns on **by project** — with one command.

```
Opus 5 · swissknifeman · [########--] 81%
```

## Why exactly? statusline

Actual context percentage (`context_window.used_percentage`) gets **only**
statusline-script: context fields do not receive any of hook-events, including
`PreCompact`/`PostCompact`. The model itself does not see this percentage either - that is, the rule
«the agent will offer `/compact` at 80%» is not feasible by construction, and a window into a number can
give only a person to himself.

Mechanism price — **are not tokens**: «The status line runs locally and does not consume API
tokens». The price is measured in milliseconds: the script is launched at the start of the session and then
each new assistant message, after `/compact`, when changing permission-mode and vim-mode.

## Enable

```bash
harness hooks --global                            # files to the machine (once)
harness hooks --target . --statusline context     # include in the project
harness hooks --target . --statusline off         # turn off
```

- Key `statusLine` is written in **`.claude/settings.local.json`** — machine-local
  terminal preference (like `outputStyle`), not a team convention (like
  `plansDirectory`), therefore rummaged `settings.json` is not touched.
- Merge-only respecting someone else's choice: the key is occupied by ANOTHER value → skip + warn;
  `off` removes the key only if it is equal to ours.
- Global kill-switch — `disableAllHooks`: suppresses hooks **and any custom status line**.

## Settings (`~/.claude/statusline/env.ini`)

| Key | Default | What it does |
|---|---|---|
| `THRESHOLDS` | `80,90` | threshold bars in percentage, ascending |
| `COOLDOWN_MIN` | `15` | minutes between notifications (`0` — no cooldown) |
| `BAR_WIDTH` | `10` | bar width in characters |
| `DEBUG` | `false` | diagnostics in `$XDG_RUNTIME_DIR/claude-statusline/debug.log` |
| `NOTIFY_CMD` | `../hooks/notify/notify.sh` | notification delivery |

The file is installed once and **does not overwrite** code update - how `env.ini` hooks.

## How the notification works

- The notification comes to **crossing the lane up**, and not on every render above
  threshold, otherwise an alert would appear on every message from the assistant.
- Cooldown suppresses frequent transitions, but **does not lose** them: the suppressed band is not
  is written to the state, and the alert will go away as the first render after the cooldown.
- Percentage drop (after `/compact`) resets the bar down - a new acceleration will notify again.
- `used_percentage` happens `null` (beginning of the session and after `/compact`, hasn't passed yet
  next call API): bar is not drawn, threshold decision **not accepted**. `null` — not `0%`.
- Delivery (`hooks/notify/notify.sh`) is reused rather than rewritten: Linux
  `notify-send`, macOS `osascript`/`terminal-notifier`, WSL/Windows toast; no backend - quiet.

## Engineering Framework

Runtime **cancels statusline-script in the middle**, if a new update has arrived (updates
debounce for 300 ms). Hence the two hard frames that are visible in the code:

- notification is called **disconnected** (`setsid … &`) — otherwise the alert would be lost along with
  canceled script;
- session state is written **atomically** (`tmp` + `mv`) in
  `${XDG_RUNTIME_DIR:-/tmp}/claude-statusline/<session_id>.state` — partially recorded
  state does not exist.

Plus the rule of cheapness: **exactly one external call per render** (`jq`), none
`git`/`curl`/`python3`/network in hot path, no additional line segments (git-branch,
price, rate-limits) — each segment is the latency that the user sees as
interface slowdown. Any error → minimum string and `exit 0`: has no statusline
right to drop UI, a `stderr` is still not shown to the user (that's why `DEBUG` writes to file).
