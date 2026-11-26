# Layers and modules

This page is the layer and module contract. The product lives at the repository root.
[ADR 0002](../adr/0002-layers-and-import-rules.md) and [ADR 0003](../adr/0003-module-graph.md)
record the import rules and the graph. The [codebase map](CODEBASE-MAP.md) keeps the
machine-readable dependency copy.

## Layers

All package paths below start at `src/skm/`.

| Layer | Path | Responsibility and allowed direction |
|---|---|---|
| Kernel | `kernel/` | Pure shared IDs, errors, outcomes, clocks, versions and envelopes; stdlib only |
| Platform | `platform/` | Config, schema, JSON, logging, filesystem and process infrastructure; kernel and allowed libraries |
| Domain | `modules/<m>/domain/` | Pure entities, values, transitions and rules; kernel and own domain |
| Ports | `modules/<m>/ports.py` | Typed repository/gateway Protocols; owner domain and kernel |
| Application | `modules/<m>/application/` | Transactional handlers; own domain/ports, permitted platform API and dependency facades |
| Public | `modules/<m>/public.py` | Explicit facade exports for other modules |
| Host | `modules/<m>/host/` | Host operations through host gateways and client; no UoW or repositories |
| Adapters | `adapters/<tech>/<m>/` | Implement owner ports using IO; never imported by domain/application |
| Entrypoints | `entrypoints/<surface>/`, `sdk/` | Parse, invoke client/host operation, render; adapters assembled by bootstrap |
| Background | `background/` | Bounded service ticks through application boundaries |
| Bootstrap | `bootstrap/` | Composition root; may assemble every layer |

The detailed import matrix and explicit annotation exceptions remain in the
[contract inventory](contracts.md) and `tests/architecture/`. `TYPE_CHECKING` does not grant
arbitrary cross-module access. Providers belong in adapters/bootstrap; configuration
sources belong in `platform/config/sources/` and bootstrap, with the entrypoint-main
exception specified by the tooling rules. Domain code has no IO, environment or
ambient clock. Modules call foreign facades only for direct `depends_on` entries.
Host gateway imports follow the explicit gateway contract rather than granting
host access to repository/control-plane APIs.

## Module graph

| Module | Owns | Direct `depends_on` | Optional | Database schema |
|---|---|---|---|---|
| `access` | Principals, identities, tokens, memberships and permissions | — | No | `skm_access` |
| `settings` | Configuration entries, history, locks and administration | — | No | `skm_config` |
| `workspace` | Workspaces, projects, repositories, hosts, checkouts and workers | `access` | No | `skm_workspace` |
| `artifacts` | Staged blobs, files, immutable versions and grants | `access`, `workspace` | No | `skm_artifacts` |
| `policy` | Permission narrowing, intents, approvals and decision audit | `access`, `workspace` | No | `skm_policy` |
| `extensions` | Packs, resource versions and provenance | `access`, `workspace`, `policy` | No | `skm_extensions` |
| `runtimes` | Runtime/model catalogs, sessions, capabilities and usage | `access`, `workspace`, `extensions` | No | `skm_runtimes` |
| `planning` | Plans, drafts, immutable revisions and typed specifications | `access`, `workspace`, `artifacts`, `extensions` | No | `skm_planning` |
| `context` | Two-phase manifests, block selection, budgets and research | `access`, `workspace`, `planning`, `extensions`, `artifacts` | No | `skm_context` |
| `execution` | Runs, tasks, attempts, stages, checks, reviews and acceptance | `access`, `workspace`, `artifacts`, `extensions`, `policy`, `runtimes`, `planning`, `context` | No | `skm_execution` |
| `integrations` | Client projections, ownership, drift and doctor | `workspace`, `artifacts`, `extensions`, `policy`, `runtimes` | No | `skm_integrations` |
| `knowledge` | Ephemeral memory, durable lessons and code graph | `access`, `workspace` | Yes | `skm_knowledge` |
| `learning` | Activity, lesson candidates, confidence and human promotion | `access`, `workspace`, `runtimes`, `execution`, `knowledge` | Yes | `skm_learning` |
| `exports` | Derived Markdown and vault notes | `workspace`, `planning`, `execution` | Yes | `skm_exports` |

The column lists each module's actual `MODULE.depends_on`, checked by the architecture tests
(the [codebase map](CODEBASE-MAP.md) keeps the machine-readable copy).
Growing the graph requires a change to the owning module and those tests.
FKs follow this DAG or point into `skm_core`; reverse relationships belong in
consumer tables or events. `settings` references the core scope registry.
The platform manifest is infrastructure, not a fifteenth bounded context.
Disabling an optional module removes its registrations and subscribers, while
its database migrations still apply.

## Repository boundaries

| Root path | Meaning |
|---|---|
| `src/skm/` | Product Python code |
| `src/skm/schemas/` | Sole writable source of JSON Schema contracts |
| `resources/` | Data packs; packaged as `skm/_resources` |
| `tests/` | Default-collected regression, contract and architecture tests |
| `tools/` | Development tools |
| `docs/` | Living English documentation |

`generated/` files are emitted by `make gen`, never handwritten. The
[codebase map](CODEBASE-MAP.md) and [contract inventory](contracts.md) name modules,
ports and registration points; a listed file is not proof that its scenario works.
Kernel additions must be stable shared primitives used by at least two modules and
owned by neither.
