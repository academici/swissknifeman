# Namespaces — connection isolation

Namespace — this **group of projects**. Within a communication group (graph) and memory are shared; between groups -
isolated. One mechanism for hub binding systems: **maind-graph** (topology between projects)
and **memory** (`agent-memory`).

## Announcement

The project declares membership as a field `namespaces` in `config.json` (maind-only, like `tags`):

```jsonc
{ "id": "flexcrm",  "namespaces": ["axioma"] }
{ "id": "azguard",  "namespaces": ["axioma", "*"] }   // also general infrastructure
{ "id": "diabox",   "namespaces": ["diabox"] }
{ "id": "legacyapp" }                                  // no field → group default
```

| Meaning | Meaning |
|:--|:--|
| no field / `[]` | implicit `default` → old behavior (everything is connected inside default) |
| `["axioma"]` | connection only with projects that also have `axioma` |
| `["*"]` (wildcard) | general infrastructure: contacts ALL groups |

Optional registry `namespaces: { axioma: { name, description } }` in `config.json` gives
metadata and typo hints; membership is specified in the projects themselves.

## Graph: isolation at edge creation point

Cross-project edge A↔B is under construction, **only if A and B share at least one namespace**
(`namespaces.link_allowed`, applies to `derive.*`). Therefore, stores do not physically contain
inter-namespace bridges, and lower and lower (union, index, query) isolates itself; `rebuild_index`
duplicates the gate as defense-in-depth.

## Memory: buckets by namespace

Memory follows the same model via scope-buckets:

| bucket | who sees |
|:--|:--|
| `project:<id>` | the project itself (private) |
| `ns:<name>` | all projects of the group `<name>` |
| `global` | entire ecosystem (wildcard-infrastructure + ecosystem-wide) |

`namespaces` manages graph connections. Memory uses separate opt-in
`memory_namespaces`; seed and normal recall remain in `project:<id>`. General `ns:<group>`
is only raised explicitly recall with scope — more details → [Memory](./memory).

## Commands and example

```bash
maind namespaces                          # groups and their member projects
maind projects list --namespace axioma    # group projects
maind graph --cross --namespace axioma    # cross-project layer of one group
maind sync --namespace axioma --only graph,memory   # group fan out
```

Example: `flexcrm` and `azguard` in `axioma` — are connected in a graph and divide `ns:axioma` memory; `diabox`
doesn't see them in his group. `azguard` with `["axioma","*"]` — bridge: visible in `axioma`, and how general
infrastructure to everyone.

## Cache BRAIN-docks in memory

Project documents (BRD, architecture, API-contracts, etc.) can be cached in memory maind,
so that the agent picks them up through `recall` instead of re-reading files with each request - savings
context on repeated runs. **Commands `maind memory store`/flags `--key`/`--file` not
exists** — real writing to memory goes through `maind memory remember`, which only has
flags `--project`|`--scope`, `--share`, `--type`, `--json` (see `lib/maind/memory.py:_cmd_remember`).
«Key» document topics (`docs:brd`, `docs:architecture`, …) is transmitted via `--type`:

```bash
# write the document as a fact with a key type docs:brd
content="$(cat docs-private/dev/BRD.md)"
maind memory remember --scope project:loqum --type docs:brd "$content"

# remember later (query - based on the meaning of the text, not an exact match of the key)
maind memory recall --scope project:loqum "docs:brd"
```

Wrapper over several documents at once - `scripts/cache-brain-docs.sh` of the brain module (maind is taken from `$MAIND_BIN` or `PATH`):

```bash
scripts/cache-brain-docs.sh --scope project:loqum \
  docs:brd=docs-private/dev/BRD.md \
  docs:architecture=docs-private/dev/Architecture_Loqum.md
```

Recommended keys (`--type`) for projects with BRAIN-documentation:

| key (`--type`) | what is cached |
|:--|:--|
| `docs:brd` | requirements and goals (BRD) |
| `docs:architecture` | architecture (C4, components) |
| `docs:api` | API-contracts |
| `docs:glossary` | glossary of terms |

This is manual/script step (not part `maind onboard`/`sync`) — if you need auto-caching
on onboarding, this is a separate modification `provision/onboard.py`, not described here.

Next: [Code graph (Serena) →](./code-graph)
