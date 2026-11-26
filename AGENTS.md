# Agent rules for the SKM repository

Work in the repository root. Product code is under `src/skm`; schemas under `src/skm/schemas`.
Use the [codebase map](docs/architecture/CODEBASE-MAP.md) for module boundaries, reusable test fixtures,
registrations and fast checks. When `.codegraph/` exists, query CodeGraph in the current worktree before
searching or reading code; then read only missing slices.

1. Start with the owning module, its schemas and its tests.
2. Use [layers and modules](docs/architecture/layers-and-modules.md) for names and boundaries.
3. Keep changes within the task scope. Preserve other changes and user deletions.
4. The donor at `../swissknifeman/` is read-only. Never modify it or import its packages.
5. P00 builds the complete 14-module contract skeleton before logic and ports. Unfinished handlers are not registered.
6. Domain code has no IO, clock or environment. Modules use public facades by `depends_on`; host code uses gateways.
7. Install with `uv sync --frozen`; Makefile tools use `uv run --frozen`. Run the relevant tests and inspect the diff.
8. `make check` runs `fmt-check lint typecheck test arch docs-check schema-check`; PostgreSQL/e2e are separate. `make check-touched` is a local diff preflight, followed by affected behavioral tests. A `skip:` message is an unavailable check, never success. New regression tests belong in the default-collected root `tests/` tree within the task write set; tests under `src/skm/modules/**/tests` are omitted.
9. In manual work, read the relevant contracts, implement the change, validate it and record the manual review status separately.
10. Executor validation and manual review are independent. Recommendations do not automatically launch another agent.
11. Follow owner instructions for commits, reports and publishing; manual work requires no commit or JSON report per leaf.
12. Generated code comes from its owning generator. Product checks, reviews, leases and security contracts remain normative.
13. Attribute provider-created or provider-implemented commits using the actual execution evidence. Add Git trailers `Plan`, `Plan-Ref`, `Plan-Role`, `Plan-Actor`, `Executed-By`, and `Executor-Session`, following the existing SKM convention. `Plan-Actor` records the assigned route; `Executed-By` records the actual provider/model/effort, and `Executor-Session` the actual provider session ID. Include the campaign and checkpoint identifiers when applicable. For a commit integrating several contributors, identify each actual contribution and session in the commit body or repeated trailers. Never infer or fabricate unavailable values: omit them and preserve the available evidence. The coordinator is responsible for preserving attribution when integrating an executor's work.
