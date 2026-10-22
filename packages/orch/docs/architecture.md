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

These belong to specialised runtimes; an engine may adapt one, `orch` does not become one. The Engine Port bindings
currently prepare launch plans; their `run`, live `watch`, `cancel`, `resume` and `results` operations return
`NOT_IMPLEMENTED`. The conductor starts role processes itself.

The conductor provides durable item execution on one host: local leases own the run and checkout, started records
precede each step, work-source receipts record closing effects, and resume reconciles interrupted work. Successful
receipts close only the matching attempt; a split commit also needs a completed workspace part. Missing or unsuccessful
receipts repeat the source's idempotent operation. This local durability does not add the specialised runtime features
listed above, or recovery across machines, to the Engine Port.

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
fills `{model}`, `{effort}`, `{cwd}` and `{orch}` (this package root) and starts nothing. The Grok `executor`,
`bounded-implementer`, `reviewer`, `triager`, `researcher`, `advisor` and `report-fixer` all run headless through
`scripts/ro-run.py` with jsonl transport:
`--prompt-file /dev/stdin`, `--model`, `--effort`, `--permission-mode bypassPermissions` and
`--output-format streaming-messages-json`. The sanitized real stream fixture pins text, error and usage parsing.
The Grok scout uses the same wrapper with text transport (`--output-format plain`) and disables web search.
The complete role/provider matrix and explicit catalog refusals (`LAUNCH_REFUSED`) are documented in
[conductor.md](conductor.md); an unlisted pair retains `LAUNCH_UNKNOWN`.

An entry may also carry `resume_argv` (catalog 1.6.0, optional; the required keys `model_class`, `effort`, `transport`,
`argv`, `timeout_s`, `model_set` are unchanged and a catalog without it is valid): the whole command line that continues a
provider session, a list of strings with `@part` items like `argv`, the same placeholders and the required `{session}`
(filled by the conductor with the session it resumes; `launch.build_resume_argv` fills the others and leaves it). The
Codex `executor` has one (`codex -a never exec resume {session} --json -c sandbox_mode="{write_sandbox}" --model … -`):
`codex exec resume` takes no `--sandbox`, so the sandbox mode is a `-c` override. A route carries `resume_argv` when its
entry has one, and the conductor continues the executor session of that provider with it.

The wrapper applies Linux Landlock before `exec` (no root or user namespaces); every child inherits it. Writers
grant `--rw {cwd}`. The reviewer and triager use `--protect {cwd} --rw {cwd}/vendor` for test caches; the scout,
researcher, advisor and report-fixer use `--protect {cwd}` without a checkout grant. Protected roles disallow editing, subagent creation, scheduled writes, workflows
and image/video generation; the report-fixer also disallows shell commands. The filesystem stays readable, with
default writes to `/tmp`, `/var/tmp`, `/dev` and `~/.grok`.

`--protect` requires Landlock ABI >= 3 (including TRUNCATE) and fails closed with exit 3 for a protected checkout
inside a default writable root (`RO_RUN_PROTECT_OVERLAP`), a symlink or escaping in-checkout `--rw` grant
(`RO_RUN_RW_ESCAPE`), or an older ABI (`LANDLOCK_ABI_TOO_OLD`). A checkout in `/tmp` therefore cannot serve these
protected roles. Without `--protect`, the existing writable rules are preserved. Conductor preflight checks both
the wrapper command and the provider after `--`, caching command availability for its process.
