# Runtimes, context, extensions and integrations

[ADR 0016](../adr/0016-integrations-vs-runtimes.md) separates client integrations from
agent runtimes. Exact runtime signatures are the Protocols in
[`modules/runtimes/ports.py`](../../src/skm/modules/runtimes/ports.py). Context, extensions
and integrations ports are each module's `ports.py`.

## Responsibility boundaries

| Module | Owns | Separate concern |
|---|---|---|
| `runtimes` | Start/stream/cancel/result, detection, capabilities and usage | Does not decide task acceptance or resume policy |
| `context` | Two-phase manifests, selection, provenance, budgets and research | Does not grant permissions |
| `extensions` | Versioned resource data, packs, compatibility and quarantine | Does not execute arbitrary pack code |
| `integrations` | Interactive client projections, ownership, drift and doctor | Separate from unattended runtime sessions |

## Runtime contracts

`AgentRuntime` declares `capabilities`, `detect`, `self_loaded_context`, `start`,
`events`, `cancel` and `result`. See [`AgentRuntime`](../../src/skm/modules/runtimes/ports.py).
The core is synchronous; adapters own stream threads and bounded process cancellation.
Native terminal success is required: exit 0 without it yields
`RUNTIME_STREAM_INCOMPLETE`, with partial usage emitted before failure.
Only execution decides resume/fresh; runtime admission filters that choice.

Capabilities carry `native/adapted/unsupported/unknown`, tested version, evidence,
limitations and verification date. Unverified newer installations become unknown.
Catalogs include allowed-plugin metadata without importing plugin code (E32).
Routing records requested/resolved bindings; provider-reported model is a nullable
observation, not authority (E54). Missing telemetry remains unavailable.

Isolation profiles `none`, `worktree`, `landlock`, `container` and namespaced
plugin profiles are distinct from policy profiles. Unavailable isolation fails
closed; unconfined execution requires explicit policy permission. Unattended
sessions never load untrusted client settings from the checkout (E30).
Fresh-token budget counts input + output + cache write, excluding cache reads.

## Context pipeline

Control-plane `assemble_draft` selects pinned blocks and requests host inputs.
The host safely reads those inputs, budgets and renders. `finalize_manifest`
rechecks digests, budgets and current ownership/fencing in the same UoW through
context-owned `ContextOwnerGuard`; the adapter delegates to execution's public
ownership check, avoiding a reverse context-to-execution dependency (E21).

| Priority | Block | Requirement |
|---|---|---|
| 1 | `system_constraints` | Mandatory; never trimmed |
| 2 | `role_contract` | Mandatory |
| 3 | `task_contract` | Mandatory |
| 4 | `requirements` | Linked requirements mandatory |
| 5 | `decisions` | Linked decisions/answers mandatory |
| 6 | `review_feedback` / `previous_attempt` | Mandatory for rework |
| 7 | `steering` | Selected by scope |
| 8 | `skills` | Selected index/body/references tiers |
| 9 | `materials` | Required inputs mandatory |
| 10 | `repo_instructions` | Policy-selected, explicitly untrusted |
| 11 | `history` | Optional and bounded |

The pipeline discovers, validates, selects, checks compatibility, snapshots,
budgets, renders and persists. Every included/excluded block records source,
version, digest, trust, estimate and reason. Optional blocks are excluded from
lowest priority upward; an oversized mandatory block gives `CONTEXT_OVER_BUDGET`.
Host content stays private unless storage is explicitly enabled.

## Resource registry

| Kind | Format / content |
|---|---|
| `skill` | `SKILL.md`, manifest, references and provenance |
| `steering` | Scoped Markdown instructions |
| `agent_profile` | Role, prompt blocks, policy profile, routing and capability requirements |
| `workflow` | Versioned declarative stages |
| `plan_template` | Manifest and draft templates |
| `prompt_block` | Simple variable substitution in Markdown |
| `integration_bundle` | Instructions, hooks, MCP and client pack data |
| `runtime_catalog` | Runtime/model/pricing data with verification dates |
| `model_guideline` | Structured model guideline profile (`model-guidelines/<key>.toml`) |

Packs pin immutable versions and digests. Runs resolve all resources within pinned
pack versions. Operator overlays may override resources by priority; only
builtin/operator packs contribute configuration. Skills and profiles only narrow
permissions. Incompatible resources enter quarantine with reasons. Upstream
updates preserve provenance and require an explicit diff/apply decision.
Personal overlays live outside neutral core data.

From the checkout root, `skm pack compile` compiles `resources/packs` in place. Use
`--path DIR` for a standalone pack or another collection of packs. Identical
asset bytes are stored once under `.pack-blobs/<sha256>` at the compile root.
`pack.lock.json` lists the logical paths that use those blobs and records the
SHA-256 of the sorted logical paths and their individual SHA-256 digests,
including each `pack.toml`. The pack readers verify referenced blob bytes and
restore them at their original logical paths before installation. Installation
continues to compute the immutable registry digest from the pack payload.

Commit the lock, referenced blobs, and source changes together. To edit a
shared asset at one path, write the new file at that logical path and recompile.
To remove a logical path stored in a blob, remove its entry from `aliases` and
recompile. Keep the compile root and its metadata together when copying a pack
that uses collection-level blobs. Archive a standalone pack with its lock and
blobs at the archive root. The hygiene workflow runs
`skm pack compile --check`, which exits nonzero for missing or stale metadata,
corrupt blobs, and duplicate copies that still need compilation. Check mode
leaves the tree untouched. See the [CLI reference](../reference/cli.md).

Built-in pack sync seeds the relational model catalog from
`resources/packs/core/runtimes/models.toml` in the pack installation transaction.
Identical model IDs share a canonical row across runtimes. Each offering keeps
its provider selector and tariff. Missing tariffs are SQL `NULL`. Guidelines
reference their immutable extensions resource version. Structured profiles use
the `model_guideline` kind and `urn:skm:runtimes:model-guideline:v1`; the core
pack ships them under `resources/packs/core/model-guidelines/`. Hosts report availability
separately, with one observation per host, runtime, model and effort. An
observation is fresh from `observed_at` up to `expires_at`, excluding expiry.

Control-plane callers can publish an operator pack version through
`extensions.public.publish_runtime_catalog_snapshot`. The function takes the
pack manifest and catalog TOML and writes through the caller's UoW. Normal pack
selection applies to new reads, while existing `PackPins` keep their recorded
versions. Planning continues to resolve catalogs through the extensions facade.

`ModelCatalogSyncJob` fetches four inventories before any unit of work:
models.dev, OpenRouter models plus endpoints, an OpenAI-compatible `/v1/models`
list, and offline fallback generalizations. The HTTP transport is injected, so
tests never open a socket. A missing tariff stays `None`. `skm runtime sync`
stages external candidates for review. An authorized control-plane caller uses
`report.approve(*candidates)` with selected rows' `candidate` values from
`report.pending`, then passes the returned report to `activate_staged_catalog`.
Activation writes the approved offerings and publishes an immutable
`synced-models` resource in the `catalog-sync` pack. When the pack is enabled,
the snapshot adds or updates model rows while keeping the base runtime selectors.

## Projections and research

Projection uses desired state, recorded applied state and actual files.

| Ownership | Guarantee |
|---|---|
| `managed_file` | User changes cause drift and a `.skm-new` alternative, not overwrite |
| `managed_block` | Only the owned block changes |
| `merged_json` / `merged_toml` | Only owned keys change; pre-images support recovery |

Host operations perform file IO and submit observations to control-plane recording
commands. Hooks use one `skm hook` entrypoint with separate enforcement,
observation and workflow classes. Default policy is `workspace-contained`.
ADR 0024 adds the host-only `research_source` component and
`ResearchSourceRegistry`, with builtins `command`, `filesystem`, `codegraph`, and `mcp_stdio`.
The host searches; control-plane commands store results and serve cache queries.

### Native CodeGraph

Install the [CodeGraph CLI](https://colbymchenry.github.io/codegraph/reference/cli/) on the host and
bind a Git checkout to the SKM project. `skm graph init` initializes and indexes the checkout locally.
`skm graph index` rebuilds it, `skm graph status` reports its state, and `skm graph doctor` checks
readiness and returns the MCP server configuration. The commands accept `--project` and `--mount`.
The default mount is `main`. Initialization and rebuild maintain the root-anchored `/.codegraph/`
rule in the shared Git `info/exclude` via the managed SKM block.

Enable the research source for the CLI in the instance settings.

```toml
[context.research.sources.codegraph]
kind = "codegraph"
tier = "codegraph"
capabilities = ["search"]
```

`skm research query SymbolName --source codegraph` returns indexed symbol locations from the
project's initialized checkouts. The research ladder tries the source after local docs and before
external search. Native results bypass the research cache because rebuilding the index can change
results for the same checkout contents.

To project the [CodeGraph MCP server](https://colbymchenry.github.io/codegraph/reference/integrations/)
to a supported client, add the `mcp` fields from `skm graph doctor --json` to
`integrations.mcp.servers.codegraph` in the project settings and run `skm integrations apply`.
The server arguments are `serve --mcp --path <bound checkout>`. The core client instructions direct
agents to use `codegraph_explore` when the checkout contains a `.codegraph/` index. These native
operations work with the `knowledge` module disabled.
