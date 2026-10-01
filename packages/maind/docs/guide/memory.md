# Memory (agent-memory)

Long-term memory - external **Node-demon** `@agentmemory/agentmemory` (on `iii-sdk`).
maind him **orchestrates** (does not rewrite to Python) and speaks HTTP, collecting requests
for the project.

## Life cycle

```bash
maind memory start     # launch in a separate session, pidfile in data/, health-poll
maind memory run       # foreground (exec node) — for systemd Type=simple
maind memory status    # running / url / pid / ports / workers
maind memory stop      # SIGTERM→SIGKILL; alien demon (without pidfile) does not touch
```

`maind start` without `--only` raises both memory and graph. For autostart upon login/loading -
register the daemon as systemd-service: [`maind service install`](./systemd).

## Ports - from env/config

`memory.resolve_ports` takes values by priority: **env** (`AGENTMEMORY_PORT` /
`AGENTMEMORY_STREAM_PORT` / `AGENTMEMORY_URL`) → **`.maind.json`** (`memory.http_port` /
`stream_port` / `url`) → **default** `4111/4112`. No hardcodes - two nodes on one
to the machine are routed to ports via `.env`.

## Cross-machine mode: `memory.role` (ADR-0001)

The default node is `standalone` (today's regime, its demon on loopback; back-compat —
existing nodes do not change behavior). For multiple persistent machines
(`docs/adr/ADR-0001-cross-machine-memory.md`) — the only living demon on
**host**-car, the rest - **client**:

```json
"memory": {
  "role": "host",                          // | "standalone" (default) | "client"
  "url": "http://<HOST_LAN_IP>:4111",       // REQUIRED for role=client, NOT loopback
  "bind_host": "auto",                      // only role=host: LAN-address of THIS machine (or explicit IP)
  "secret_file": "memory.secret"            // path (relative to the node root), 0600
}
```

- **`role=client` prohibits raising the local daemon with CODE** (not only documentation):
  `maind memory start`/`maind memory run`/`maind service install` will fail with non-zero
  code - the second writer breaks the uniqueness of the store (LWW/overwrite whole scope when
  conflict, `findings/P4-cross-machine-facts.md` §4). Specify the host via `memory.url`.
- **`secret_file`** — bearer-token for `AGENTMEMORY_SECRET` on host; resolution order:
  env `AGENTMEMORY_SECRET` → `memory.secret_file` → without token (anonymous, like today).
  The secret is NOT stored inline in the config (diffs/copies of the config light it would have been leaked) and not
  is printed in the logs/error messages.
- **LAN-stage (closest, D80).** Transport - LAN: daemon bindend not on `127.0.0.1`, and on
  **specific LAN-host address**. The machine address is NOT stored in the repository: tracked
  `config/memory/iii-config.yaml` remains a portable template (`host: 127.0.0.1`), and the address
  specifies the node - `memory.bind_host` in `config.json` (gitignored) or env `AGENTMEMORY_BIND_HOST`;
  `auto` takes LAN-IPv4 of the current machine. At start maind renders a runtime copy from the template
  `data/iii-config.runtime.yaml` (gitignored) with substituted `workers[iii-http].host` and gives it away
  to the demon (`AGENTMEMORY_III_CONFIG`), therefore `npm install`/engine upgrade the address will not be reset, but
  transfer to another computer = `bind_host: "auto"` (or other IP) + `memory.url` from clients, without editing
  repo. Not-loopback `bind_host` is only valid when `memory.role=host`. Bind
  `0.0.0.0` PROHIBITED (entire attack surface LAN + key expiry ceases to be
  fuse); `iii-stream` (stream port) NOT bind to LAN — cross-machine
  store/recall/forget/export go only through `iii-http` REST.
  When trigger fires **`tailscale serve`** (third permanent machine OR work outside
  LAN) — edit is REVERSIBLE in one line: `host` returns to `127.0.0.1`, publication
  is done from the outside (`tailscale serve --http=4111 127.0.0.1:4111`), `AGENTMEMORY_SECRET`
  remains enabled (ADR-0001).
- **Discrimination «not available» from «unauthorized» (401).** `GET /agentmemory/health` ALWAYS
  is public on the engine (even with a given secret) — «daemon responds» ≠ «our calls
  authorized». `maind doctor`/`maind health` distinguish this with an explicit protected call
  (`memory.check_auth`), rather than relying on `ping`.
- **Known limitations LAN-stage** (completely - `root/adr/ADR-0001-cross-machine-memory.md`):
  secret - the only fuse (no auto-recall key expiry, like Tailscale);
  secret rotation is a manual operation; segment LAN wider tailnet (who is in the same segment and
  received a secret - reads/writes the memory of ALL projects); offline machine (no network to host)
  works WITHOUT memory - local cache/deferred write queue NO (conscious refusal,
  versioning/idempotency of the contract record `store` no).

## Scopes (memory buckets) and where the insulation lives

| scope | purpose |
|:--|:--|
| `project:<id>` | private project memory (his own facts) |
| `ns:<name>` | **general bucket namespace-groups** — facts visible to all her projects |
| `global` | entire ecosystem: wildcard-infrastructure (`["*"]`) + ecosystem-wide facts |

> ⚠️ **Insulation - on the side maind, not an engine.** agentmemory 0.9.x — **single
> global pool**: field `namespace` in `remember`/`search`/`memories` he
> **ignores**, `sessionId` too, and the one sent `type` **overrides** to your
> classifier (verified alive `curl`). Only saved verbatim `content`.
> Therefore scope-provides insulation **himself maind**: embeds a marker when writing
> `[[s:<scope>]]` to the beginning of the content, when reading - filters the results of the global
> search for this marker and remove it (`memory.mark_scope`/`split_scope`).
> Without this layer the project would see «private» memory of other people's projects. Don't write to
> daemon bypass maind (`maind memory` / `maind_memory_*` MCP) — records without marker
> will be invisible to scoped-recall.

Scope model: seed writes one updated fact about connections only in private
`project:<id>`. Graph namespaces (`namespaces`) and allowed shared memory areas
(`memory_namespaces`) are separated. Regular recall reads only `project:<id>`; `ns:<name>`
is read or written only when explicitly passed `scope`. Automatic publication seed
not included in the general bucket. Derivation of buckets - `namespaces.py`, seed — `seed.py`. Groups -
[Namespaces](./namespaces).

## Single write path/read: hook + MCP via maind

To «remembered» (memory hook) and «remembered» (MCP/CLI) went to ONE isolated side:

- **Manual mode `MODE=manual`** — recommended: memory accessible via MCP/CLI, but not
  is loaded in every session; native auto-memory is also disabled.
- **Legacy auto-mode `MODE=maind`** (`~/.claude/hooks/memory/modes/maind.sh`) delegates
  `remember`/`recall` in `maind memory`; scope taken from the project (`CLAUDE_PROJECT_DIR` →
  `match_cwd`), brain is ignored. `maind onboard` writes himself `<project>/.claude/memory.env.ini`
  `MODE=maind`.
- **MCP** `maind_memory_store|recall|forget` go through the same `memory.py`-wrappers;
  `maind_memory_recall(project:<id>)` remains private scope. General `ns:*` is specified explicitly.
- **CLI** for humans: `maind memory remember|recall|forget [--project ID|--scope S] [--share]`.

## Auto-load context at session start (digest) and native-memory

For native memory Claude Code (`~/.claude/projects/<proj>/memory/MEMORY.md`) is a property,
which the demon does not have «out of the box»: she **auto-injected** into the context of each session. To
the demon didn't lose in this (otherwise the agent MUST REMEMBER to do `recall` — non-deterministic):

- `MODE=maind` puts SessionStart-hook `<project>/.claude/maind-memory.sh`, who calls
  **`maind memory digest`** (deterministic project memory digest: list+filter by
  scope-token, private scope first, freshest on top; byte budget + per-item trim; hook-
  safe - the demon is down → no-op) and injects it through `additionalContext` (Claude Code ≥ 2.1.59).
- Placed at the same time **`autoMemoryEnabled:false`** — native auto-memory is turned off to
  there was no duplication. The demon becomes a single source of both memory and starting context.
- **Digest — project-only default.** `shared_max=0` (default): in `additionalContext` is coming
  Project private memory ONLY (`project:<id>`); `ns:<group>`/`global` is not included in the digest
  fall at all, even if the facts are there. This is a conscious narrowing (context-economy: general
  namespace without reservation inflated the start of each session and pulled someone else's group context -
  «negative» only had digest, not at recall/column). When `shared_max=0`, digest prints
  one-line tooltip `(cross-project: maind memory recall --scope ns:<name> — digest
  project-only)`. Enable shared in the digest explicitly - `--shared-max N` (CLI) or
  `memory.digest.shared_max` in the project config; then added N the latest shared-facts
  after private. See «Cross-project task» below - how to raise the general context without changing
  digest default.

**Flexible (per-project):** `maind onboard <id> --memory manual|maind|native|off` (default
`manual`). `maind` clearly includes the old one SessionStart digest; `native` returns auto-memory.
Consistency check - in `maind health`.

## Cross-project task - how to explicitly raise shared-context

The digest at the start of the session carries only its project (see above). When the task is real
cross-project («analyze the project A and B and improve the commonality between them») — raise shared-
context in three explicit steps (without changing digest default):

1. **Connections** — what projects are generally connected and how: `maind graph --project <id>` (CLI, short
   form `view`) or MCP `maind_graph_path`/`maind_graph_neighbors` — path/neighbors in the graph.
2. **Group context** — raise shared memory namespace explicit (it's not in the digest):
   `maind memory recall --scope ns:<name> "<request>"` (CLI) or `maind_memory_recall` c with this
   `scope` (MCP).
3. **Write output** — cross-project fact is written in scope groups, not private `project:<id>`,
   otherwise other projects in the group will not see it: `maind memory remember --scope ns:<name> "<fact>"`
   (CLI) or `maind_memory_store` with `scope: "ns:<name>"` (MCP).

The skill guide with the same guideline was rolled out to each connected project - `ecosystem-mcp`
(source - `packages/maind/templates/skills/ecosystem-mcp/SKILL.md`). Cross-project optimization
code (duplicates/common packages) — separate local skill `cross-project-optimizer`
(`maind fleet manifest|duplicates|features`).

## Where to write a fact - routing rule (do not create duplicates)

The two layers are complementary, **do not duplicate the same fact in both**:

- **maind** (`maind memory` / `maind_memory_*`) — explicit long-term memory: private
  `project:<id>` default, general scope by direct request only. For continuity use
  key `active-handoff`: new entry replaces old one. Keys `progress`, `checkpoint`,
  `session-log` rejected - This log belongs to the repository.
- **native MEMORY.md** — is disabled when `MODE=maind`. If consciously `--memory native`: only
  small curated set of invariants «always at hand», without copies maind-facts.
- **file-federation (`MODE=file/federation`, brain `core`)** — legacy, for infranodes only
  (brain/swissknifeman). For app-projects should not be used.

## HTTP-demon contract

| Operation | Request (agentmemory 0.9.x, checked with living demon) |
|:--|:--|
| health | `GET /agentmemory/health` |
| store | `POST /agentmemory/remember {namespace, content, type}` — `content` carries a marker `[[s:<scope>]]` |
| recall | `POST /agentmemory/search {query, namespace, limit}` → `{results:[{observation, score}]}` (filter by marker - in maind) |
| forget | `POST /agentmemory/forget {memoryId}` — **exactly `memoryId`** (not `{namespace,id}` → HTTP 400) |

Wrapper in `memory.py`: `store`/`recall` (marker + filter + normalization in `[{score, text, id}]`),
`forget`/`export`. Worker config - `config/memory/iii-config.yaml` (7 workers `iii-*`).

When configured `memory.secret_file`/`AGENTMEMORY_SECRET` all protected calls carry
`Authorization: Bearer <secret>` (`core.http` — additive parameter `headers`, default not
changes nothing); `GET /agentmemory/health` — exception, it is always public. Expectation budget
(timeouts/retrays) — `MEMORY_LIGHT_TIMEOUT_S`/`MEMORY_HEAVY_TIMEOUT_S`/`MEMORY_RETRIES` in
`constants.py`, measured in;
retract only read-calls (`export`), not mutations (`store`/`forget` — risk of double without
operation-id in the contract).

## Verification «does it really work?» and troubleshooting

`maind health [--project ID]` executes read-only check. Mutating **round-trip**
write→recall→forget starts only with `--deep`; `--strict --deep` falls if it fails.
Common cases:

- **remember and recall diverge** (wrote down - can't remember): hook not in `MODE=maind` (writes in
  file `core`-brain past the demon) → `maind onboard <id>` or put `.claude/memory.env.ini`
  `MODE=maind` + restart the session.
- **`forget` gives HTTP 400**: old payload `{namespace,id}` — needed `{memoryId}` (fixed).
- **recall sees «private» facts of someone else's project**: recording was bypassed maind (without marker) —
  write only through `maind memory` / `maind_memory_*`.
- **project graph is empty**: derive was not run → `maind graph derive --project <id>` (onboarding
  does it himself; empty at fresh app-project without intra-ecosystem dependencies - the norm).

> **Name collision «federation».** In memory hook `MODE=federation` — is a file backend
> (`~/.swissknifeman/memory/<brain>/*.md`), it is NOT associated with graph-federation maind (graph by
> projects + index). For applied projects canon - `MODE=manual` (daemon on request), file
> `federation`/`core` is left for infra-nodes.

Next: [Graph →](./graph)
