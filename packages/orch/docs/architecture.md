# Architecture

## Boundaries

`orch` owns the `exec/v1` JSON Schemas (nine document kinds), the `exec/v1` document semantics on top of the closed-profile validator of aicore (`orch.schema` re-exports it),
the Engine Port (Protocol, errors, run-state reducer), the binding capability matrix and capability seeds,
role manifests and canonical role texts, and the `scripts/orch.py` CLI (`validate`, `input adhoc`,
`render-prompt`, `prepare --dry-run`, `launch`).

`orch` does not own plan data or lifecycle, model execution (nothing is started yet), or environment
installation. Partners are reached only through named bridges (`bridges/<partner>/`) or as processes
discovered by `orch.discovery`.

## Dependency rule

```text
contracts (packages/orch)  <-  partners, engines
orch code imports only the standard library, orch.* and aicore.* (validator, digest, model catalog)
partners read exec/v1 documents as JSON; they do not import orch
engines use partner CLI/JSON APIs only
```

- Generated copies of canonical text into another package's managed block are build-time generation,
  not a runtime dependency.
- Conformance tests live on the consumer side of the contract and run partner CLIs as subprocesses.
- aicore is located by `scripts/orch.py` (Python) and by `scripts/test.sh` and `scripts/validate.sh` (bash) the same way
  as in every module: `AICORE_ROOT`, then `_vendor/aicore`, then the sibling `aicore`.
- Models come from the aicore model catalog (`orch.catalog`, `--model-catalog`); orch keeps no model names.
- `tests/test_boundaries.py` walks `lib/orch/**/*.py` and rejects imports outside the standard library, `orch` and `aicore`, and scans the
  package outside `bridges/` for names of other packages.

## Layout

```text
packages/orch/
  README.md  docs/  scripts/{orch.py,ro-run.py,validate.sh,test.sh}
  schemas/exec/v1/            # defs + nine document schemas
  lib/orch/                   # schema (aicore validator), contracts, port, discovery, catalog, render, adhoc, bindings/, cli
  roles/<role>.md|json        # canonical role texts and role manifests
  bindings/matrix.json        # binding capability matrix
  bindings/capabilities/      # <binding>--<provider>.json seeds (status declared)
  configs/                    # launch catalog
  bridges/<partner>/          # the only place that names a partner
  fixtures/  tests/
```

## Launch catalog

`configs/launch-catalog.json` states how each role starts on each provider CLI by model class; `orch.py launch argv`
fills `{model}`, `{effort}`, `{cwd}` and `{orch}` (this package root) and starts nothing. The grok `reviewer` is a
headless read-only run: `scripts/ro-run.py` applies a Linux Landlock ruleset before `exec` (no root, no user
namespaces, so it works where Ubuntu refuses unprivileged bubblewrap), the whole filesystem stays readable and
writes go only to temp directories, `~/.grok` and `{cwd}/vendor`; grok reads the brief from stdin
(`--prompt-file /dev/stdin`), runs under `bypassPermissions` with its edit tools disallowed and streams
`streaming-messages-json`. Every child inherits the ruleset, so tests and shell commands of the reviewer run but
cannot change the repository.
