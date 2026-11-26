# Installation

## Full bootstrap (recommended)

With one command: CLI + memory daemon + autorun under systemd.

```bash
git clone <repo> maind && cd maind
./install.sh --with-memory --with-service
```

- `--with-memory` — `npm install` at the root (demon `@agentmemory/agentmemory`).
- `--with-service` — registers the daemon as systemd --user service (`maind service install`):
  autostart upon login + auto-restart. See [Memory Daemon (systemd)](./systemd).

For the demon to rise **when loading OS** (and not just after login) — enable linger (one-time):

```bash
loginctl enable-linger $USER       # check: loginctl show-user $USER -p Linger → yes
```

After - connect projects: `maind onboard <path>` (see skill `ecosystem-integration`).

## Only CLI

```bash
./install.sh
```

Creates a symlink `~/.local/bin/maind → bin/maind`; a fresh machine also gets `registry.json` from
`configs/registry.example.json` in the state directory (nothing is created when a registry or the legacy
node file already exists). Options: `--bin-dir DIR`, `--force`. Check: `maind doctor`.

## Manual memory (without systemd)

Memory Daemon - Node-package `@agentmemory/agentmemory`:

```bash
npm install                  # puts the daemon in node_modules
cp .env.example .env         # host ports (default 4111/4112)
maind start --only memory
maind memory status
```

::: tip Port conflict
If on 4111/4112 another node is already spinning (for example Brain), set in `.env` theirs
`AGENTMEMORY_PORT` / `AGENTMEMORY_STREAM_PORT` — maind will take them instead of defaults.
:::

## Documentation

```bash
npm run docs:dev        # local server VitePress
npm run docs:build      # building a static site
```

## Requirements

- **Python 3.8+** and **bash** — for kernel CLI (required).
- **Node.js** — for memory daemon and documentation build only.
- **uvx** (from [uv](https://docs.astral.sh/uv/)) — for the code graph in the project (engine Serena, see
  [code graph](./code-graph)); is included in the project by the field `code:true`.

Next: [Config config.json →](./config) (lives in the root of the monorepo, not in the package maind)
