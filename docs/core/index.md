# core — removed

**What is this.** The root `core/` package used to hold the shared stdlib-only primitives of the monorepo. They moved
into the foundation module `packages/aicore` (see its `README.md`), and the folder `core/` is gone: there is
no import shim and no `AICORE_ROOT` fallback for the name `core`
([ADR 0071](../architecture/decisions/0071-core-and-artifex-removal-and-strict-boundaries.md)).

**When to touch.** Never. New and old code import `aicore`; code outside the repository that imports `core` must switch to
the names below.

## Where the code went

| Old name | New home |
|:--|:--|
| `core.{block,cli,env,http,io,paths,proc,project,repo,term,text}` | `aicore.util.*` |
| `core.provider` and `core.provider.*` | `aicore.provider.*` |
| `core.provider.{artifact,lock,reconcile}` | `aicore.artifacts.*` |
| `core.usage` | `aicore.usage` |
| `core.gitignore_policy` | `aicore.state.gitignore` |
| `core.runs`, `core.pathology`, `core.codegraph_telemetry` | `analyst.run_reports`, `analyst.pathology`, `analyst.codegraph`; read by other modules through `analyst runs show\|codegraph --json` |
| `aicore.util.paths.state_dir` | `aicore.state.state_dir` |

## Reference: run telemetry (SCHEMA=2)

`packages/aicore/lib/aicore/usage.py` is the single accumulator of tokens on which all telemetry is based. The run is
captured by the SessionEnd hook of harness (`hooks/run-report/`), which parses the transcript line by line and writes
`<project>/.claude/runs/<sid>.json` (**SCHEMA=2**: tests, lint, files, tool failures, dev-loop signal and the
usage partition in/out by model). This run report is read by:

- **`maind analyze`** — the post-run verdict GREEN/ATTENTION/RED (did the agent use its memory and graph);
- **`analyst token-report`** — usage trend and rolling baseline (`.claude/analyze/baseline.json`);
- **`analyst.pathology.detect`** — the detector of recurrent pathologies (rule ≥2/5 on the run-report history).

The operational layer of this is [Development §9](/develop#_9-performance-measurement★).

## Development

```bash
bash packages/aicore/scripts/test.sh                       # aicore tests
```
