# Deployment: new machine / command

One idempotent script takes the ecosystem to **new computer** (OS reinstallation,
second laptop) or **new team members** — dotfiles pattern (see
[Roadmap](/roadmap)): versioned repo + one script, it is safe to run again.

## Quick start: one car

```bash
git clone <repo-addressswissknifeman> ~/projects/swissknifeman
cd ~/projects/swissknifeman
scripts/bootstrap-machine.sh
```

Script (`scripts/bootstrap-machine.sh`, route `swissknifeman setup --machine`) drives away
7 steps in order, checking each separately:

1. `install.sh` — CLI packages + symlink `swissknifeman` + basic Codex-plugins
   `core`/`task` (if Codex installed; opt-out `--no-codex-plugins`).
2. `harness hooks --global` — global hooks Claude Code (merge-only).
3. `harness permissions --global` — global preset permissions (merge-only).
4. MCP-presets - **soft-skip**: y harness/maind not available now `--global`-mechanism for MCP,
   rolling remains per-project (`harness mcp --target` / `maind deploy`).
5. `maind service install` — memory daemon as `systemd --user` (mild degradation without systemd).
   **Role-conscious** (`memory.role` in `config.json`, ADR-0001): on `role=client` stage
   prints informative `SKIP` and the local daemon does NOT rise (second writer) —
   client reaches the host via `memory.url`; on `standalone`/`host` — same behavior.
6. `swissknifeman doctor` — final diagnostics of all packages.
7. Project Manifest (`--projects <file>`) — see below.

Flags: `--dry-run` (plan without changes on disk), `--skip-projects` (skip step 7
in full), `--bin-dir DIR` (where to put symlinks CLI, default `~/.local/bin`).

## Project Manifest (`--projects`)

Baseline (himself swissknifeman) is set equally for everyone; list **dependent projects** — for everyone
user's own (per-user overrides, canon dotfiles-pattern). Manifest - JSON-file, diagram and
placeholders - [`docs/machine-manifest.example.json`](https://github.com/academici/swissknifeman/blob/main/docs/machine-manifest.example.json):

```json
{
  "version": 1,
  "projects": [
    {
      "repo": "git@github.com:example-org/example-project.git",
      "path": "~/projects/example-org/example-project",
      "profile": ""
    }
  ]
}
```

| Field | Required | Meaning |
|:--|:--|:--|
| `repo` | yes | git-repository address (ssh/https) |
| `path` | yes | local cloning path (`~` expands) |
| `profile` | no | profile flag/project type (informational; automatic profile detection during onboarding does `skiller connect` itself) |

Launch:

```bash
scripts/bootstrap-machine.sh --projects ~/.swissknifeman/machine-manifest.json
```

Step Behavior (idempotent - the second pass does not do anything unnecessary):

- Path from manifest **missing** → `git clone <repo> <path>`, then `swissknifeman setup <path>`
  (full onboarding: skills + environment + memory + graph, see [ecosystem-integration](/maind/)).
- Path **already exists** (cloned earlier) → `git pull` **not done** (don't touch someone else's
  working state - uncommitted changes, local branches); only repeated
  `swissknifeman setup <path>` (onboard-check, adds what is missing, does not overwrite anything).
- `--dry-run` prints the plan (what will be cloned / which already exists) unchanged on disk.
- `--skip-projects` skips the entire step, even if `--projects` is specified.

Store your personal manifest outside the repository (for example `~/.swissknifeman/machine-manifest.json`) —
in the repo is committed only `.example` with placeholders (hygiene `.env`↔`.env.example`).

## Second car: cross-machine memory (host/client)

Starting from `, memory (`agent-memory`) can live **on one host machine**,
and the rest of the owner's permanent machines are networked **clients** (option 1 closed
roadmap-stub; decisions and rejected options -
`packages/maind/docs/adr/ADR-0001-cross-machine-memory.md`). Node role - field
`memory.role` in local (gitignified) `config.json`: `standalone` (default, back-compat,
your daemon) · `host` (demon holds, listens LAN-address) · `client` (does NOT raise the demon, goes to
host by `memory.url`).

**On host** (next stage - LAN, not Tailscale):

1. `packages/maind/config/memory/iii-config.yaml` → `iii-http.host` = specific LAN-host address
   (not `127.0.0.1`, not `0.0.0.0` — ban D28); `AGENTMEMORY_SECRET` (or `memory.secret_file`)
   REQUIRED LAN-stage is the only fuse (segment LAN wider tailnet).
2. `config.json`: `memory.role = "host"` + **`memory.url` = `http://<LAN-address>:<http_port>`**
   (not `127.0.0.1`!). Daemon after editing (1) stops listening loopback — without `memory.url`,
   pointing to its own LAN-address, **local** host checks (`maind health`/`doctor`,
   MCP-hooks of the same machine) will start to fall `not available` the next time the daemon is restarted, although
   he is alive and responding LAN (played during performance P4.3: restart the daemon after
   `iii-config.yaml` was already carrying LAN-bind, a `config.json` — not yet, gave full local downtime
   memory before editing `memory.url`; see).
3. Autostart without login - `loginctl enable-linger $USER` (see
   [systemd.md «Autostart without login»](/maind/guide/systemd)) — role condition `host`, is not an option.
4. Firewall host - allow incoming memory port ONLY from the subnet LAN.

**On the client:**

1. `config.json`: `memory.role = "client"` + `memory.url` = host address (not loopback — gate
   config validation will fail). Token - `memory.secret_file` (0600), not env.
2. `scripts/bootstrap-machine.sh` — stage 5 itself skips the rise of the local daemon (see above);
   other steps are identical.
3. Acceptance - `maind health --strict --json` (round-trip store→recall→forget via network) and
   `maind doctor` (does not consider the absence of local Node/agentmemory error on the client -
   known space at the time P4.3, see Pending Work).

Known limitations LAN-stage (secret - single fuse, manual rotation,
segment LAN wider tailnet) and the growth path to `tailscale serve` — see ADR-0001 «Known limitations».

## Script «command»

1. Baseline — everyone puts `bootstrap-machine.sh` without `--projects` (or with a common command
   read-only manifest «required» projects, if agreed upon).
2. Each participant holds his `~/.swissknifeman/machine-manifest.json` with a list of projects,
   with whom he personally works - the list is not autodetected (Scope: written by a person).
3. Secrets/API-keys - **not in the manifest or in the script**: are started separately (env/`.env`
   in the project), bootstrap does not concern them.

## What's not included in this script

- **Intercomputer memory synchronization** — not part bootstrap'a: mode host/client
  rolls out separately (see section «Second car» above and
  `packages/maind/docs/adr/ADR-0001-cross-machine-memory.md`).
- Automatically determines which projects the user needs - the list in the manifest is written
  person.
- CI/automation bootstrap — script is designed for a one-time machine operator.

## See also

- [Development with Claude Code](/develop) — what to do after the machine is lifted.
- [Control-surface projects](/control-surface) — spot diagnostics/repairing layers
  of the connected project.
