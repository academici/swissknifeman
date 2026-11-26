# P08.09 small-task eval report

Live results are filled in manually from the sanitized evidence of an explicitly opted-in run.
`skipped` and `not_run` are not verified provider capabilities or supported deployment evidence.

| Date (UTC) | Runtime | CLI version | Admission | Capabilities | Usage / USD micros | Outcome | Reason / evidence |
|---|---|---|---|---|---|---|---|
| — | claude_code | unknown | not_run | unverified | unknown / null | not_run | No live run performed |
| — | codex | unknown | not_run | unverified | unknown / null | not_run | No live run performed |

Run with user credentials: `SKM_EVALS=1 make evals`. The target selects only these two live
cases and disables parallel execution, so they share one budget. `SKM_EVALS_MAX_USD` defaults
to `0.50`; direct pytest invocation also accepts `--evals-max-usd`. Missing CLI or credentials
produce a reasoned skip. Credential lookup uses the account HOME from `pwd`, since the root
test policy replaces the process HOME. Auth files are copied only into disposable isolated homes.

The task changes `greeting.py` in a temporary Git repository and runs an unchanged deterministic
check. Request limits are 90 seconds, four turns, 1024 output tokens, and 256 KiB of output.
These are adapter request limits, not a guarantee of provider billing or native token enforcement.
After each started eval, actual usage is accumulated in integer USD micros. Reaching the ceiling
stops the suite. Unknown usage or missing catalog pricing stops further evals as well; missing
usage remains `unknown`, missing cost remains `null`, and neither becomes a measured zero.
The current model catalog omits unverified pricing, so the USD ceiling and unknown-usage stop
policy **cannot guarantee actual provider spend**, including the first request.

Sanitized streams and `summary.json` remain under `.pytest_cache/d/live-evals/<runtime>-<id>/`
with private permissions. Summaries include date, runtime version, bounded admission, declared
capability statuses, actual usage, check outcome and budget stop reason. Declared capabilities
are not promoted to live verification by this small task. Credential values from auth files and
provider auth environment variables are masked again before export. Only stream files are copied;
client homes and raw credentials are never exported. The repository, runtime state and isolated
credentials are removed on success, failure, budget stop and interruption of the stream.

Executor validation on 2026-11-17:

- Default offline harness: **19 passed**, including unset/0 opt-in, collection marker separation,
  network ban, finite caps, budget accumulation/stop, fake-child failure/interruption, redaction and cleanup.
- `pytest --collect-only -q tests/evals`: **21 collected** (19 offline cases and two live cases).
- Ruff format/check and Pyright for all four Python files: **passed**, zero type errors.
- The requested unmodified final command chain stops at its first pytest command:
  **20 passed, 24 failed**. All 24 failures are in the existing integration harness. Its
  `tests/support/harness.py` runner disables plugin autoload, but the copied root conftest
  defines the xdist hook `pytest_configure_node`; without xdist loaded, pytest reports
  `PluginValidationError: unknown hook 'pytest_configure_node'`. No forbidden files were changed.
  The remaining collection/style/type commands were run separately and passed.
- Diagnostic run with explicit plugin loading:
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_PLUGINS=xdist.plugin uv run --frozen pytest -q tests/evals/test_harness.py tests/integration/test_test_harness.py`
  gives **44 passed**. This is supplementary evidence, not a claim that the unmodified chain passed.

Manual review: `not_requested` (independent of executor validation).
The donor orientation path `../swissknifeman/packages/orch/tests/test_characterization.py`
is absent in this worktree layout; no donor code was imported.
