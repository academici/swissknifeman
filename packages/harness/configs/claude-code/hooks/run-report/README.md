# run-report — archived run outcome capture (SessionEnd)

One **Python-hook** Claude Code (`SessionEnd`), who at the end of the session reads the transcript and
writes structured **run-report** in `<git-root>/.claude/runs/<session_id>.json`. From here
[`maind analyze`](../../../../../maind/) collects post-run report «did everything work as it should?».

Capture **universal** (generic): the outcome is removed from the transcript for ANY task - not only
dev-loop-work flow. Therefore `dev-loop.js`/no need to touch the packs (verified perplexity-web by
official. docks: SessionEnd gets `transcript_path`+`session_id`+`cwd` and can write to disk).

## What it retrieves (protective, degraded by presence)

| Slice | Source in transcript |
|:--|:--|
| `tools.by_name` / `.total` | all `tool_use`-blocks (Bash/Edit/Write/Workflow/Task/…) |
| `codegraph` | calls symbol-tools Serena/codegraph/laravel-boost (`find_symbol`, `get_symbols_overview`, …) |
| `bash.tests` / `.lints` | Bash-commands by pattern (pytest/phpunit/pest/ruff/pint/validate.sh…) + `ok` from `is_error` |
| `bash.failed` | Bash-commands whose `tool_result.is_error=true` |
| `tool_failures` | any `tool_result.is_error=true` (tool + output slice) |
| `files_changed` | `file_path`/`notebook_path` from Edit/Write/MultiEdit/NotebookEdit + `toolUseResult.filePath` |
| `workflows` | `toolUseResult` work flow (`workflowName`/`status`/`summary`) |
| `devloop` | best-effort: JSON with `tool_failures`/`workarounds`/`deferred`/`open_questions`/`results` as a result of work flow/agent |

## Files

| File | Role |
|:--|:--|
| `run-report.py` | SessionEnd-hook: stdin → transcript → `<git-root>/.claude/runs/<sid>.json` (atomic, retention) |
| `_lib.py` | protective **lowercase** transcript parser (without slurp) — tested separately |
| `env.ini` | `ENABLED` (kill-switch) + `RUNS_KEEP` (retention). Per-project override: `[harness.hooks.run_report] enabled / runs_keep` in `.swissknifeman/config.toml` (carrier `.swissknifeman/hooks.env`; the legacy `.claude/run-report.env.ini` is still read) |

## Installation / enable

```bash
harness hooks --global                      # copies the hook to ~/.claude/hooks/run-report/
harness hooks --target . --run-report on     # include in the project (config + hooks.env + registration SessionEnd)
maind analyze --project <id>                 # analysis of accumulated run-report'ov
```

## I/O-contract (for debugging)

Hook reads JSON payload on stdin (`transcript_path`/`session_id`/`cwd`/`reason`), writes a file
`<git-root>/.claude/runs/<session_id>.json` and nothing in stdout (SessionEnd stdout is not visible to the model).
The root is determined `git rev-parse --show-toplevel` from observable `cwd`; out Git hook
keeps the same path `<cwd>/.claude/runs/`. Field `cwd` in JSON always saves the actual
launch directory.
Catalog `runs/` **self-ignored** (`.gitignore` = `*`): run-report'are ephemeral/machine-local,
do not clog `git status` (and do not break the check «pure tree» in `maind analyze`).

```bash
echo '{"transcript_path":"/path/to/session.jsonl","cwd":"/proj","session_id":"s1"}' \
  | python3 run-report.py          # → /proj/.claude/runs/s1.json
echo 'not json{' | python3 run-report.py   # → exit 0, does not write anything
```

## Fair limits (we will not overpromise)

- **Transcript schema not frozen** official (verified perplexity-web: is stable to
  additive changes, but not a contract) → pars **protective**, the hook is silent on the error (exit 0),
  a `maind analyze` degrades to forensics (bash-log + git-diff).
- **`SessionEnd` = one entry per session** — several tasks in one session will merge into one
  run-report. Needed per-turn — will be required `Stop`-option (follow-up).
- **`bash.tests`/`.lints` — heuristics based on command patterns**; `ok` is taken from `is_error`
  tool_result (reliable), but classification «this is a test/lint» may miss on atypical commands.
- **`devloop` — best-effort**: depends on whether the workflow has produced a structural result in
  transcript; no - let's be content `workflows[].summary`.
