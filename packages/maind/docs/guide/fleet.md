# Fleet — cross-project layer (optimizer)

`maind fleet` — agent entry point **cross-project optimization**: across ~N similar projects
(common core packages) find duplicate code/schemes and put the general into the kernel. The signal is collected from
**three sources** (single «merged» there is no code graph and it is not necessary):

1. **topology** (`manifest`) → *where to look* — who shares which packets;
2. **duplicates** (`duplicates`, engine jscpd) → *what exactly* repeats;
3. **shared memory** (`features`/`log`) → *what has changed recently* — correlation of similar features.

Gives spot editing [code graph (Serena)](./code-graph) in the desired project. Ready script -
skill `cross-project-optimizer`.

## manifest — fleet map

```bash
maind fleet manifest        # JSON: projects (paths/scopes/code) + shared_packages
```

`shared_packages` — first-party packages that require ≥2 project, with consumers and provider:

```json
{ "package": "package:axioma-studio/azguard-core", "name": "azguard-core",
  "provider": "azguard", "consumers": ["azguard", "corex", "flexcrm"], "consumer_count": 3 }
```

These are ready **optimization groups**: improvement in the overall package affects all its consumers.

## duplicates — cross-project duplicates (jscpd)

```bash
maind fleet duplicates --group azguard-core --min-tokens 60 [--json]   # by package consumers
maind fleet duplicates --projects flexcrm,shop,crm [--json]            # by explicit list
```

Wrapper over [jscpd](https://github.com/kucherenko/jscpd) (via `npx`, language-agnostic).
Cross-project clones (`cross_project: true`) — first. Needed Node.js/`npx` (first launch
installs the package).

**Default ignores:** `**/vendor/**, **/node_modules/**, **/packages/**` — are focused on
**application projects** (source in `app/`/`src/`, a `packages/` for the consumer - these are symlinks to
other projects, no need to scan them). For **monorepo package** (source in `packages/*`)
override ignore: `--ignore "**/vendor/**,**/node_modules/**"`. Threshold — `--min-tokens` (less →
more noise), pattern - `--pattern` (default `**/*.php`).

::: tip Doubles are candidates, not a verdict
Similar code can be justified (different subject areas). The decision to remove it is within the meaning (via
Serena), and not just by jscpd.
:::

## similar — semantically similar code (embeddings)

```bash
maind fleet similar --group azguard-core --threshold 0.85 [--json]
```

On top of literal duplicates jscpd: extracts functions/classes by grouped paths, embeds them
**external** backend and looks for cross-project pairs «similar in meaning, not verbatim». Backend -
pluggable via `code_graph.embed.command` in the `[maind]` config (external tool `text→vector`,
placeholders `{input}`/`{output}`):

```jsonc
"code_graph": { "embed": { "command": ["my-embedder", "--in", "{input}", "--out", "{output}"] } }
```

Backend not configured → intelligible `die` (is only available `duplicates`). Retrieving chunks and
cosine comparison - on stdlib; embedding - external (like jscpd). MVP, is developing.

## features / log — feature correlation via shared memory


## What already exists and what is new

| Brick | From |
|:--|:--|
| list projects + paths | registry `registry.json` |
| access to all repositories | workspace-hub trust ([workspace](./workspace)) |
| groups by common packages | maind-topology graph ([federation](./federation)) |
| feature correlation | shared memory + namespaces |
| **duplicate detector (jscpd)** | **new** — `maind fleet duplicates` |

Next: [code graph →](./code-graph) · [Memory →](./memory)
