# Memory daemon as systemd-service

Shared Memory Daemon (`agent-memory`) — this Node-process on node mAInd, through which they go
`recall`/`store` all projects. So that it rises automatically (upon login / loading OS) and
restarted itself during a crash, it is registered as **custom** systemd-unit
(`systemctl --user`, without root). Control - by command `maind service`.

## Quick start

```bash
maind service install     # create a unit, daemon-reload, enable --now (raise immediately)
maind service status      # unit state
maind service logs        # journalctl -u maind-memory (last 100 lines + follow)
```

After `install` memory rises immediately and starts with each login. Checking project connectivity:

```bash
maind health --cwd        # status connected, demon responds to :4111
```

## Commands

| Command | What it does |
|:--|:--|
| `maind service install` | write `~/.config/systemd/user/maind-memory.service`, `daemon-reload`, `enable --now` |
| `maind service uninstall` | `disable --now` + delete unit |
| `maind service start` / `stop` / `restart` | running unit control |
| `maind service status` | `systemctl --user status maind-memory` |
| `maind service enable` / `disable` | autostart at login on/off |
| `maind service logs [args]` | `journalctl --user -u maind-memory` (add. arguments are thrown out) |

## How the unit works

`ExecStart` starts the daemon in **foreground** — `maind memory run` does `exec node …`,
replacing the process, so systemd tracks itself Node-demon like `MAINPID` and rules it correctly
(restart, stop). Unit (generated from absolute installation paths):

```ini
[Unit]
Description=mAInd — ecosystem shared memory daemon (agent-memory)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=<root maind>
ExecStart=<root maind>/bin/maind memory run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`maind memory run` — foreground-launch for systemd; for manual background start still
yes `maind start --only memory` / `maind memory start` (detail + pidfile).

## Autostart without login (server by SSH)

User units live as long as there is a user session. So that the daemon starts at boot
OS and kept without logging in - enable **linger** (one-time step). For role `memory.role =
"host"` (cross-machine memory, ADR-0001) linger — **role condition, not an option**: without it the daemon cannot
will survive a host reboot without interactive login, and all clients will lose memory at the same time
(see [umbrella deploy.md «Second car»](https://github.com/academici/swissknifeman/blob/main/docs/deploy.md)):

```bash
loginctl enable-linger $USER
loginctl show-user $USER -p Linger    # check → Linger=yes
```

Without linger the daemon will rise only after the first login into the session. C linger — immediately upon loading.

## Ports and config

The demon listens `:4111` (HTTP) and `:4112` (stream) — are overridden via `.env` at the root maind
(`AGENTMEMORY_PORT` / `AGENTMEMORY_STREAM_PORT`); worker config - `config/memory/iii-config.yaml`.
See [Memory (agent-memory)](./memory).

## If not systemd

On systems without `systemctl` (or naked SSH without user-sessions) `maind service` will tell you
alternative - raise memory manually: `maind start --only memory`.
