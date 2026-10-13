# Engine conformance

`packages/orch/conformance/scenarios.json` (`orch-conformance/v1`) lists the scenarios every engine binding is
measured against. `orch.py conformance [--binding B] [--json]` runs them.

## Catalogue

Each scenario has an `id`, a `title`, a `kit` (`agent`: how an engine runs a stage; `runtime`: how run state behaves),
a proof (`how`: `trace` or `test`, with a `ref`) and one status per binding:

| Status | Meaning |
| --- | --- |
| `covered` | a trace file or an existing orch test proves it; the command runs it |
| `declared` | no proof for this binding yet (an external engine, or work that waits for orch parity); listed with its `reason`, never fails the command |
| `n/a` | does not apply to the binding; listed with its `reason`, never fails the command |

`declared` and `n/a` always carry a `reason`; `covered` needs a `ref` that exists. A test checks the catalogue itself:
every scenario of the required list is present, covered refs resolve, every binding is named.

A trace (`conformance/traces/*.jsonl`, or a golden trace under `fixtures/traces/`) is a run-event stream. The runner folds
it through `RunState` and compares with `expect`:

| Key | Meaning |
| --- | --- |
| `stages` | `{stage_id: status}` after the fold (the stream is closed unless an event is refused) |
| `error` | the port error code the stream must raise (for example `STALE_EPOCH`); the fold stops there |
| `foreign` | number of events of another contract version kept and not applied |
| `effect` | `unknown_receipt`: `effects.check` must not let the effect run again |
| `inputs`, `decision` | the stage inputs for `retry.decide` (`stage_writes`, `worktree_dirty`, `receipt_unresolved`) and the action it must return |

A test reference is a dotted unittest name; it runs once however many bindings are reported. The process scenarios of the
native binding (`child-process-cleanup`, `stdout-stderr-framing`, `workspace-permissions`) are proven by
`tests/test_native_conformance.py` on fake argv (a `python -c` role, never a live provider); the same scenarios stay
`declared` for `cao` and `claude-only` until orch parity is triggered (ADR 0062).

## Command

`orch.py conformance` prints one line per scenario and binding: `PASS`, `FAIL`, `DECLARED` or `N/A`, the binding,
the scenario and the reason. `--binding` limits the report to one binding, `--json` prints the rows. Exit code 1 means a
covered scenario failed or the catalogue is invalid; declared and `n/a` rows never change it. The command reads the
package and writes nothing.

## Write confinement and the bus rule

`tests/test_write_confinement.py` snapshots a temporary home and project, runs `prepare --dry-run`, `policy test`,
`conformance` and `explain`, and fails when anything outside the output directory or `<state>/orch/runs/` changes, or when a
provider directory (`.claude`, `.codex`, `.grok`) appears. `tests/test_boundaries.py::test_no_mcp_imports` fails when orch or
the aicore extension layer imports a module whose name contains `mcp`: MCP is a tool surface, not the event bus, not the
source of truth about a run.
