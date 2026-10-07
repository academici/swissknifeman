# Architecture

## Boundaries

`orch` owns the `exec/v1` JSON Schemas (nine document kinds), the stdlib-only closed-profile validator,
the Engine Port (Protocol, errors, run-state reducer), the binding capability matrix and capability seeds,
role manifests and canonical role texts, and the `scripts/orch.py` CLI (`validate`, `input adhoc`,
`render-prompt`, `prepare --dry-run`, `launch`).

`orch` does not own plan data or lifecycle, model execution (nothing is started yet), or environment
installation. Partners are reached only through named bridges (`bridges/<partner>/`) or as processes
discovered by `orch.discovery`.

## Dependency rule

```text
contracts (packages/orch)  <-  partners, engines
orch code imports only the standard library and orch.*
partners read exec/v1 documents as JSON; they do not import orch
engines use partner CLI/JSON APIs only
```

- Generated copies of canonical text into another package's managed block are build-time generation,
  not a runtime dependency.
- Conformance tests live on the consumer side of the contract and run partner CLIs as subprocesses.
- `tests/test_boundaries.py` walks `lib/orch/**/*.py` and rejects non-stdlib imports, and scans the
  package outside `bridges/` for names of other packages.

## Layout

```text
packages/orch/
  README.md  docs/  scripts/{orch.py,validate.sh,test.sh}
  schemas/exec/v1/            # defs + nine document schemas
  lib/orch/                   # schema, contracts, port, discovery, catalog, render, adhoc, bindings/, cli
  roles/<role>.md|json        # canonical role texts and role manifests
  bindings/matrix.json        # binding capability matrix
  bindings/capabilities/      # <binding>--<provider>.json seeds (status declared)
  configs/                    # launch catalog
  bridges/<partner>/          # the only place that names a partner
  fixtures/  tests/
```
