# Review P10.3 (grok-4.7, effort high)

Reviewer session: grok `01a125a4-f48f-7203-9813-68c397170b96` (headless, read-only launch from the orch bridge `launch`).
Route proof from the session record: `current_model_id` grok-4.7, `reasoning_effort` high; the session record carries no
`contextWindowTokens` (the grok configuration of the machine sets `context_window = 500000` for `grok-4.7`).

## Reviewer report

## Findings

### 1. `packages/planner/lib/planner/plan/bridges.py:89`

`scan()` loads every `bridge.json` in later roots before the first-root-wins check, so an invalid manifest that repeats an earlier name raises `BRIDGE_INVALID` and the valid earlier bridge is dropped.

REPRODUCTION: a project whose `bridges.roots` are `first` then `second`, with a valid `alpha` in `first` and an `alpha` in `second` whose entrypoint file is missing:

```text
roots: ['/tmp/skm-shadow-9y2r2hmv/proj/first', '/tmp/skm-shadow-9y2r2hmv/proj/second']
BRIDGE_INVALID: BRIDGE_INVALID: /tmp/skm-shadow-9y2r2hmv/proj/second/alpha/bridge.json: entrypoint 'go' is not a file inside the bridge: missing.py
```

`bridges.scan()` raises. There is no `BRIDGE_SHADOWED` line and the bridge from `first` is not returned.

### 2. `scripts/ecosystem-units.py:697`

`module_imports` records only `import` and `from` statements, so `bridges/orch-skiller/tests/test_review_prompt.py:26` loads `orch.adhoc` and `orch.render` through `importlib.import_module` and `ecosystem-units.py check` reports no bridge boundary violation.

REPRODUCTION:

```text
python3 scripts/ecosystem-units.py check --json
```

```text
bridge violations 0
errors [] ok True
```

```text
module_imports: ['__future__', 'importlib', 'json', 'pathlib', 'sys', 'unittest', 'partners']
static module_imports: ['orch', 'orch']
orch is a module name: True
```

The same scanner yields `orch` for `import orch` / `from orch.render import load_role`, and `orch` is a package module name, so that static import would be counted.

Checked and green: `bash scripts/test-bridges.sh` (`bridges: OK (3)`, 1 + 11 + 97 tests, none skipped), `python3 scripts/ecosystem-units.py check`, `render --check`, `python3 scripts/public-hygiene.py` (0 violations), `python3 scripts/test-ecosystem-units.py` (145 tests), `unittest discover -s packages/planner/tests/engine -p test_bridges.py` (20 tests), `standalone` of the three bridges (`n/a`, exit 0). From the repo root, `plan.py bridge list` returns `planner-orch` at `bridges/planner-orch`. Relative roots, `~/…`, and duplicate roots resolve and dedupe. With `AICORE_ROOT` unset, the hub `packages/aicore` fallback is used. With `AICORE_ROOT` set to a missing directory, lookup returns `None` and does not fall through. With `SKM_ORCH_ROOT` unset and no `orch` on `PATH`, `plan.py bridge planner-orch launch` exits 3 with `BRIDGE_PARTNER_UNAVAILABLE`.

VERDICT: FINDINGS

## Executor decision (own runs)

1. `bridges.scan()` validated shadowed manifests: CONFIRMED by the executor (reproduced), FIXED: a directory whose name is
   already taken by an earlier root is reported as `BRIDGE_SHADOWED` and not read; test `test_a_shadowed_manifest_is_not_validated`.
2. Dynamic import in `orch-skiller/tests/test_review_prompt.py` is invisible to the static boundary scan: REJECTED as a defect,
   it is the recorded design limit (the engine of a partner is reached by name at run time, no static import and no
   neighbour path; logged as a deviation). The scan checks imports and paths, it does not claim to detect `importlib`.
