# core — transitional compatibility shim

**What is this.** The root `core/` package used to hold the shared stdlib-only primitives of the monorepo. They moved
into the foundation module [`packages/aicore`](../../packages/aicore/README.md). `core/` now has two parts: a shim
that keeps the old import names working, and the modules whose owners are later stages.

**When to touch.** Never for new code: import `aicore`. The shim is removed together with `core/` when the hub
modules move onto `aicore` ([ADR 0028](../architecture/decisions/0028-aicore-subsystems-and-core-shim.md)).

## Where the code went

| Old name | New home |
|:--|:--|
| `core.{block,cli,env,http,io,paths,proc,project,repo,term,text}` | `aicore.util.*` |
| `core.provider` and `core.provider.*` | `aicore.provider.*` |
| `core.provider.{artifact,lock,reconcile}` | `aicore.artifacts.*` |
| `core.usage` | `aicore.usage` |

Every old name is registered in `sys.modules` as the same module object as the new one, so `mock.patch("core.io.os.replace")`
acts on `aicore.util.io`. The flat facade `from core import …` keeps its previous `__all__`. If `aicore` is not
importable, the shim looks for it in `$AICORE_ROOT/lib`, then in `packages/aicore/lib` next to `core/`; otherwise it
raises `ImportError("aicore not found: set AICORE_ROOT or run from the monorepo")`.

## What still lives in `core/`

| Module | Stays until | Then goes to |
|:--|:--|:--|
| `config_paths`, `gitignore_policy` | configuration stage | `aicore` |
| `runs`, `pathology`, `codegraph_telemetry` | hub modules stage | `analyst` |

## Reference: run telemetry (SCHEMA=2)

`packages/aicore/lib/aicore/usage.py` is the single accumulator of tokens on which all telemetry is based. The run is
captured by the SessionEnd hook of harness (`hooks/run-report/`), which parses the transcript line by line and writes
`<project>/.claude/runs/<sid>.json` (**SCHEMA=2**: tests, lint, files, tool failures, dev-loop signal and the
usage partition in/out by model). This run report is read by:

- **`maind analyze`** — the post-run verdict GREEN/ATTENTION/RED (did the agent use its memory and graph);
- **`analyst token-report`** — usage trend and rolling baseline (`.claude/analyze/baseline.json`);
- **`core.pathology.detect`** — the detector of recurrent pathologies (rule ≥2/5 on the run-report history).

The operational layer of this is [Development §9](/develop#_9-performance-measurement★).

## Development

```bash
bash packages/aicore/scripts/test.sh                       # aicore tests
PYTHONPATH=. python3 -m unittest discover -s core/tests   # shim and the modules still in core
```
