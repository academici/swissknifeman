# P10.2 review verdicts (grok/grok-4.7, effort high, headless read-only via orch bridge launch)

## review-grok-4.7
session: 01a1256e-a93e-7872-9fb2-d9780f2287e6 (model grok-4.7 from session record ~/.grok/sessions/.../01a1256e-a93e-7872-9fb2-d9780f2287e6/summary.json current_model_id)

Three confirmed findings. The default sibling discovery, absolute `AICORE_ROOT`, fixture verdicts, digests, and the golden `orch-validate-*` outputs match HEAD.

1. `packages/orch/scripts/test.sh:25` and `packages/orch/scripts/validate.sh:25`. Both runners `cd` to the module after the locator and then keep a relative `AICORE_ROOT` on `PYTHONPATH` and in the environment, so a path that was valid in the caller's directory no longer points at aicore. `test.sh` then fails imports. `validate.sh` also starts `scripts/orch.py` in the new directory, and that locator rejects the same relative root.
   Reproduction: from the repository root,
   ```bash
   AICORE_ROOT=packages/aicore bash packages/orch/scripts/test.sh -k test_profile_is_the_aicore_profile
   ```
   exits 1 with `ModuleNotFoundError: No module named 'aicore'` (14 import errors). The same variable with `bash packages/orch/scripts/validate.sh` exits 1: `FAIL: schema registry` (`ModuleNotFoundError: No module named 'aicore'`), then `AICORE_NOT_FOUND: AICORE_ROOT=packages/aicore is not an aicore checkout` on every fixture. An absolute `AICORE_ROOT` passes.

2. `packages/orch/README.md:37`. The README still says the validator is an adapted copy of the plan store's validator and that the plan bridge tests keyword parity, while `packages/orch/lib/orch/schema.py:8` only re-exports `aicore.util.schema` and no keyword-parity test exists under `packages/orch`.
   Reproduction:
   ```text
   README 37: is an adapted copy of the plan store's closed-profile validator (decision D4 of the orchestration-prep plan);
   README 38: the plan bridge tests keyword parity.
   schema.py:8: from aicore.util.schema import (
   ```
   A search for `parity` under `packages/orch` hits only that README sentence.

3. `packages/orch/docs/index.md:4`. The docs index still says the package uses only the Python standard library.
   Reproduction: `index.md:4: Status: **internal, not published**. The package uses only the Python standard library.` The runtime import is `packages/orch/lib/orch/schema.py:8` (`from aicore.util.schema import`).

Checked and holding: locator blocks match the canonical copies (`scripts/test-aicore-locator.py`, 18 tests); all 51 `exec/v1` fixtures have the same schema verdicts `(path, code, message)` as the HEAD validator and the same bare sha256 digests as the old `json.dumps` form; golden `orch-validate-valid`, `orch-validate-invalid`, `orch-launch-list`, and `orch-help` match without recapture; `prepare -h` shows `--model-catalog` and has no `--routing`; no routing-discovery leftovers under `packages/orch` outside `bridges/` and `docs/research/`; `bash packages/orch/scripts/test.sh` (173 tests), `bash packages/orch/scripts/validate.sh`, and `python3 scripts/ecosystem-units.py standalone orch` pass.

RED

## rereview-grok-4.7
session: 01a12581-7660-7053-9a97-bcd7c6847779 (model grok-4.7 from session record ~/.grok/sessions/.../01a12581-7660-7053-9a97-bcd7c6847779/summary.json current_model_id)

No findings. The three fixes hold, the locator closure matches the canonical blocks, and the requested runs passed.

The runner fix is outside the locator block, which stays byte-identical to `packages/aicore/scripts/aicore-locator.sh` in `packages/orch/scripts/test.sh` and `packages/orch/scripts/validate.sh`. The Python block in `packages/orch/scripts/orch.py` matches `packages/aicore/scripts/aicore_locator.py`. `scripts/test-aicore-locator.py` ran 18 tests and passed. After the block, both runners resolve `AICORE_ROOT` with `cd && pwd` and export it before `cd` into the module. A relative root from the repo root and from `/tmp/orch-review-cwd` is absolute by the time Python starts (`AICORE_ROOT=/home/vostrikov/projects/packages/swissknifeman-next/packages/aicore`, `PYTHONPATH=lib:/…/packages/aicore/lib`).

`test.sh` ran 173 tests, all passing, for relative and absolute `AICORE_ROOT` from the repo root and from `/tmp/orch-review-cwd`, and with `AICORE_ROOT` unset from both directories. `validate.sh` passed the same four path variants (`validate: OK`, including the 173 tests and the bridge suites). `python3 scripts/ecosystem-units.py standalone orch` printed `standalone orch: pass`.

Invalid roots exit 2 before any test run: a missing path, `packages/does-not-exist`, and a directory whose `unit.json` is not `aicore`. With `AICORE_ROOT` unset and no sibling or `_vendor/aicore` (script copied to `/tmp/orch-nofound`), both runners exit 2 with `AICORE_NOT_FOUND: no aicore in $AICORE_ROOT, /tmp/orch-nofound/_vendor/aicore or /tmp/orch-nofound/../aicore; set AICORE_ROOT`. An empty `AICORE_ROOT` is treated as unset and finds the sibling.

`packages/orch/README.md:36` now names the aicore validator. `packages/orch/docs/index.md:4` includes `orch` and `aicore`. Under `packages/orch`, outside `bridges/` and `docs/research/`, nothing still describes an adapted plan-store validator, a standard-library-only runtime, or `--routing` / `ORCH_ROUTING`.

GREEN

## Executor handling
Round 1 RED: three findings, each reproduced by the executor (relative AICORE_ROOT in test.sh/validate.sh; stale README sentence; stale docs/index.md sentence); one owning correction, checks V1-V4 rerun. Round 2 (local re-review of the fixes and their closure): GREEN, no findings.
