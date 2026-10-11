# Package architecture

analyst — deterministic (stdlib-only, on-demand) data layer/pipeline. Below are the modules,
invariants and data layout.

## Modules (`lib/analyst/`)

| Module | Responsibility |
|:--|:--|
| `cli.py` | command manager (`COMMANDS` → `cmd_*(env, argv)`) |
| `common.py` | `Env(BaseEnv)` (path-property: `state_dir` = `<state>/analyst`, see README Configuration); no re-export, modules import from `aicore` |
| `lessons.py` | file store: lesson outline, state-directories, atomic write, append-only `audit`/`events`, Jaccard/similar, mem0-taxonomy |
| `digest.py` | run-report → candidates for high-precision signals; **clean extractors** + IO in `cmd_` |
| `scan.py` | cross-project aggregator (P2): clusters → patterns in ≥N projects (namespace-isolated) + reconcile |
| `workflow_scan.py` | bounded read-only inventory plan workflow files: digest mirrors, static signatures and Rule-of-Three template coverage |
| `suggest.py` | pattern → **draft** `SKILL.ru.md` (P4): pure generators + edit-safe writer |
| `confidence.py` | **clean** arithmetic (Beta × volume × decay) + shooting ranges |
| `recompute.py` | recalculation confidence from `events.ndjson` → numeric state-machine (P3) |
| `review.py` | lessons on state + structured diff (read-only) |
| `promote.py` | pipeline + **man-gate** curated + surfacing to memory mAInd (subprocess, graceful) |
| `trace.py` | **Unified Agent Trace v1** — sole owner of the schema `TraceRecord`: assembly/record validation (provenance + sha256), fail-closed on any raw key potentially carrying chain-of-thought/tool-payload/secret, `quality.completeness` for six groups of fields with a reason for each missing one, dedup resume/fork by natural key |
| `metrics.py` | paired reliability metrics over committed ones `TraceRecord` and frozen bank: `numerator/denominator/exclusions/completeness/source-trace-IDs/baseline-proof-class` in each entry; absent candidate - `deferred`, and not a silent zero; baseline class `pinned-not-recomputable`/`unknown` cannot justify comparison (fail closed) |
| `doctor.py` | environment diagnostics |

The table names the carrier modules; complete package map (including `capture`/`events`/`readers`/
`runs`/`ingest`/`proposals`/`sessions`/`status`/`token_report`) — in `packages/analyst/CLAUDE.md`.

Provider capture readers live in `lib/analyst/readers/`. The registry keys `(provider_id, schema)`:
Claude Code run-report schema 2, Codex/Cursor/Grok hook-context schema 1. Grok reuses the Codex
envelope (`GrokCaptureReader`) and stamps `provider_id=grok`.

Public package-API package - `0.2.0`: minor bump paid for Contribution gate contract
Unified Agent Trace v1 for exactly two new public modules above (`trace`, `metrics`).
Version `.claude-plugin/plugin.json` from `package.json` **not** is displayed - this is a separate
publication surface.

## Invariants (we don't marry them)

- **Auto-recording to skills is prohibited** — analyst offers, promotes a person.
- **Privacy:** raw — LOCAL-only; out - abstracted only `trigger→action`; secrets at the link.
- **stdlib-only** — none pip-dependencies in runtime (without daemon/networks).
- **`Env` is passed explicitly** (frozen dataclass), without modular globals - testable in tmpdir.
- **Atomic JSON** (`core.atomic_write_json`); `audit`/`events` — overwrite only, never overwrite.
- **Extractors/generators - pure functions** (input → exit, without I/O/hours); IO — only in `cmd_*`/writers.
- **Determinism + namespace-insulation** are inherited throughout cross-project layer.

## Data Layout

```
<project>/.swissknifeman/analyst/                 # per-project, LOCAL (raw remains here)
  lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
  audit.ndjson · events.ndjson

<state>/analyst/                           # cross-project layer (state_dir: the machine state directory)
  index/by_pattern/<id>.json               # scan: abstracted patterns
  suggestions/<id>.md                      # scan: human readable draft-MD
  drafts/<pattern_id>/                      # suggest (P4): skill draft
    SKILL.ru.md · draft.meta.json
```

## Ecosystem Connections

- **[mAInd](/maind/)** — `curated`-lessons pop up in the shared memory (`maind memory`, subprocess,
  graceful: the demon lay down → lesson on disk, will repeat later). Namespace-insulation scan is inherited from here.
- **[skiller](/skiller/)** — endpoint `suggest`: draft → person → registered skill.
- **[harness](/harness/)** — hook `run-report` captures the run (input for `digest`).
- **core** — general stdlib-foundation (`Env`/`io`/`text`/`term`), connects via PYTHONPATH.

## Development

```bash
bash scripts/test.sh          # unittest (without network/demons)
bash scripts/validate.sh      # py_compile + bash -n + JSON + required files + frontmatter + tests
```

Commits - Conventional Commits, in Russian. Before PR: `scripts/validate.sh` green.
