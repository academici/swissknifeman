# Architecture

## Boundaries

`orch` owns the `exec/v1` JSON Schemas (nine document kinds), the `exec/v1` document semantics on top of the closed-profile validator of aicore (`orch.schema` re-exports it),
the Engine Port (Protocol, errors, run-state reducer), the binding capability matrix and capability seeds,
role manifests and canonical role texts, and the `scripts/orch.py` CLI (`validate`, `input adhoc`,
`render-prompt`, `prepare --dry-run`, `explain`, `launch`, `policy`), the `[orch]` configuration schema and the shipped run-policy packs.

`orch` does not own plan data or lifecycle, model execution (nothing is started yet), or environment
installation. Partners are reached only through bridges (units of the hub, `bridges/<id>/`, outside this
package) or as processes discovered by `orch.discovery`.

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
  package for names of other packages.

## Work source and bridges

`orch` takes work through the extension point `orch:work-source` (contract `work-source/v1`, see [work-source.md](work-source.md)),
served by the plugin that `[orch] work_source` names. The plugin that ships is the bridge `planner-orch` of the hub; the core
never names it. The other bridges (role-to-skills resolution and the agent-pack role conformance) are units of the hub in `bridges/<id>/` and find their
partners by an environment variable or a command on `PATH`, never by a neighbouring folder.

## Non-goals

`orch` prepares runs, drives a work source and describes engines through a port. It does not provide:

- durable timers;
- signals;
- workflow replay;
- compensation;
- multi-day execution.

These belong to specialised runtimes; an engine may adapt one, `orch` does not become one. Starting engine processes is not
implemented yet: `run`, a live `watch`, `cancel`, `resume` and `results` of a binding return `NOT_IMPLEMENTED`.

**MCP is a tool surface, not the event bus, not the source of truth about runs.** The journal of a run and the events of
`aicore` are that source; `tests/test_boundaries.py::test_no_mcp_imports` rejects MCP imports in `orch` and in the `aicore`
extension layer ([conformance.md](conformance.md)).

## Layout

```text
packages/orch/
  README.md  docs/  scripts/{orch.py,ro-run.py,validate.sh,test.sh}
  schemas/exec/v1/            # defs + nine document schemas
  lib/orch/                   # schema (aicore validator), contracts, port, discovery, catalog, render, adhoc, settings, policies, resume, bindings/, cli
  roles/<role>.md|json        # canonical role texts and role manifests
  bindings/matrix.json        # binding capability matrix
  bindings/capabilities/      # <binding>--<provider>.json seeds (status declared)
  configs/                    # launch catalog, config.schema.json, run-policies/<id>/{policy.json,cases/}
  config.example.toml         # generated from configs/config.schema.json
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
