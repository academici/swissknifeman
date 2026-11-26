# Receipt recovery correction: targeted verification

The receipt-recovery implementation and the fixture-isolation corrections were already in the working tree at the
start of this correction round. They were retained. No additional implementation changes were necessary.

The bridge fixture binds `SKM_PROJECT_ROOT` to its sandbox and provides a local `plans/` discovery boundary for
legacy fixtures. Launch and core-verb probes now run in their own temporary fixtures. Tests that need a marker-free
branch exclude ancestor markers outside their synthetic filesystem, while preserving real markers inside it.
Production project discovery is unchanged.

## Test results

Each row was run separately through `python3 -I` and unittest discovery, with explicit import paths, a throwaway
HOME and TMPDIR, local bridge partner paths, disabled event delivery, and isolated git configuration. No providers
were called. The fixture files were also run with a valid workspace-backed project marker above TMPDIR; this
reproduces the ancestor-marker contamination without writing a marker into the shared `/tmp` directory.

| Test file | Tests | Normal exit | Ancestor-marker exit |
| --- | ---: | ---: | ---: |
| bridges/planner-orch/tests/test_launch_bridge.py | 10 | 0 | 0 |
| bridges/planner-orch/tests/test_record_parity.py | 6 | 0 | 0 |
| bridges/planner-orch/tests/test_brief.py | 66 | 0 | 0 |
| packages/aicore/tests/state/test_invocation.py | 19 | 0 | 0 |
| packages/aicore/tests/state/test_locations.py | 50 | 0 | 0 |
| packages/aicore/tests/test_project_cli.py | 34 | 0 | 0 |
| Plan-source overlays (`test_overlays.py`) | 19 | 0 | 0 |
| Plan-source workspace (`engine/test_workspace.py`) | 33 | 0 | 0 |
| packages/workspace/tests/test_workspaces.py | 20 | 0 | 0 |
| Environment settings (`test_doctor_settings_cli.py`) | 18 | 0 | 0 |
| packages/orch/tests/test_resume_receipts.py | 17 | 0 | not repeated |
| packages/orch/tests/test_adhoc.py | 10 | 0 | not repeated |
| bridges/planner-orch/tests/test_commit_bridge.py | 11 | 0 | not repeated |
| bridges/planner-orch/tests/test_worksource.py | 51 | 0 | not repeated |

The normal run covers 364 tests across 14 files. The ancestor-marker run covers 275 tests across 10 files.
Each variant has one pre-existing skip in `test_record_parity.py`; the remaining tests pass.

The local driver is `/tmp/p23_correction_tests.py`; full unittest output and per-file exit records are in
`/tmp/p23-correction-results/`. These runtime files are kept outside the repository. Commands used, with
`<REPO_ROOT>` standing for this checkout, were:

```sh
python3 -I /tmp/p23_correction_tests.py <REPO_ROOT> fixtures
python3 -I /tmp/p23_correction_tests.py <REPO_ROOT> receipts
python3 -I /tmp/p23_correction_tests.py <REPO_ROOT> fixtures --hostile-parent
python3 -I /tmp/p23_correction_tests.py <REPO_ROOT> fixtures --pattern test_overlays.py
python3 -I /tmp/p23_correction_tests.py <REPO_ROOT> fixtures --pattern test_overlays.py --hostile-parent
python3 scripts/public-hygiene.py
git diff --check
```

Both initial fixture-group commands exited 1 because the local driver initially used the package root as the
unittest discovery top for planner overlays, whose tests directory is not a Python package. The driver was
corrected to use `-t tests`; the individual overlays reruns passed all 19 tests in both variants. No repository
change was needed for this invocation error. All other per-file commands exited 0 on their first run.

## Hygiene and handoff

`python3 scripts/public-hygiene.py` exited 0 and reported `public-hygiene: 0 violations`.
The previously reported validation `.log` files were already absent from both the working tree and the index;
this round did not delete or recreate them. `git diff --check` exited 0.
An explicit hygiene scan of all candidate paths, including this untracked evidence document, also found zero
violations. All 20 changed or newly added Python files parsed with the Python 3.9 grammar.

Acceptance commands and the full suites they start were not run; the coordinator runs them after this report.
Schema compatibility and phase-wide validation therefore remain coordinator checks. No golden files were changed.
The architecture and conductor durability documentation already matches the implementation; this correction only
affects fixture isolation, so additional product documentation is not needed.

## Executor.3 follow-up

The two reported failures were reproduced separately before this correction: the boundary test rejected the three
partner-module paths formerly listed above, and the native-selection test searched an ancestor repository for its
marketplace. The table now identifies those tests by purpose and filename. The synthetic native marketplace now
owns a local repository boundary. Its malformed-config regression also creates an ancestor repository explicitly
and verifies the preflight diagnostic names the malformed config, with all project bytes unchanged.

Only this evidence document and the distribution unit's `tests/test_provider_distribution.py` changed in this
round. Production discovery and receipt recovery were retained. Additional product documentation is not needed
for this fixture correction.

The isolated runner was `python3 -I /tmp/p23-executor3-validation/run_targeted.py`. It ran individual test files
through unittest with temporary HOME and TMPDIR and explicit module import paths. `--hostile-parent` creates a
repository marker above TMPDIR without modifying the shared temporary-directory root.

| Procedure | Tests | Exit | Output |
| --- | ---: | ---: | --- |
| Boundary regression before correction | 1 | 1 | `/tmp/p23-executor3-validation/boundaries-before.log` |
| Native-selection regression before correction, ancestor repository | 1 | 1 | `/tmp/p23-executor3-validation/provider-before.log` |
| `test_boundaries.py` after correction | 6 | 0 | `/tmp/p23-executor3-validation/boundaries-after.log` |
| `test_provider_distribution.py` after correction | 46 | 0 | `/tmp/p23-executor3-validation/provider-after.log` |
| `test_provider_distribution.py` after correction, ancestor repository | 46 | 0 | `/tmp/p23-executor3-validation/provider-hostile-after.log` |

All three complete test-file runs passed without skips. After this evidence update, the boundary regression passed
again (`boundaries-final.log` in the same output folder). `git diff --check` and Python 3.9 grammar parsing also
passed. The coordinator's acceptance commands and full suites were not run in this correction round. No golden
files changed.

### Revalidation of the supplied correction

Both executor.3 fixes were already present when the supplied correction was checked again: the evidence table
uses neutral names for partner tests, and the synthetic native marketplace owns its repository boundary. No
further implementation or fixture changes were needed. The same isolated runner was invoked again:

| Test file | Environment | Tests | Exit | Runtime output filename |
| --- | --- | ---: | ---: | --- |
| `test_boundaries.py` | Normal | 6 | 0 | `boundaries-reverified.log` |
| `test_provider_distribution.py` | Normal | 46 | 0 | `provider-reverified.log` |
| `test_provider_distribution.py` | Ancestor repository | 46 | 0 | `provider-hostile-reverified.log` |

All three commands exited 0 without skips. Full output is retained outside the repository in the same runtime
folder. The first boundary rerun after updating this document failed because two recorded commands named a
partner module (`boundaries-reverified-final.log`). The commands were removed from this module-local evidence;
the concluding boundary check passed all 6 tests (`boundaries-reverified-after-evidence.log`). Python 3.9 grammar
parsing of the distribution fixture and `git diff --check` also passed.
The acceptance commands and full suites were left for the coordinator. Additional product documentation is
not needed: this correction changes only evidence wording and test fixture isolation.

### Current correction verification (2026-10-20)

The supplied red results were checked against the current candidate. Both corrections above were already
present and were retained; this round only updates this evidence. The same isolated runner executed each
affected test file with event delivery disabled:

| Test file | Environment | Tests | Exit | Runtime output filename |
| --- | --- | ---: | ---: | --- |
| `test_boundaries.py` | Normal | 6 | 0 | `boundaries-current.log` |
| `test_provider_distribution.py` | Normal | 46 | 0 | `provider-current.log` |
| `test_provider_distribution.py` | Ancestor repository | 46 | 0 | `provider-hostile-current.log` |

These runs passed without skips. Output is in the same runtime folder outside the repository. Full acceptance
commands were not run; these targeted results do not establish V10 or V60 exits. No additional product
documentation or golden changes are needed for this correction.
