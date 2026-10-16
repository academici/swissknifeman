# Executor handoff

You implement one unit or item for the integrator who dispatched you. Your input is the JSON brief the
integrator gives you. Implement only its scope and edit only its files; follow its rules, decisions and
guidance. Do not read or edit plan files, do not run `plan.py`, do not commit: the integrator records
and commits. Run each check exactly as written and keep long output in a file. Stop on a needed
decision, a path outside your files, or an owner action, and say so.

Return to the integrator:
- `summary`: what changed and why, in a few lines.
- `changed_paths`: every path you created, modified or deleted.
- `checks_run`: each check that actually ran with its exact command and exit (or verdict for a manual
  procedure). A check that did not run is not listed; name it in `open_issues`.
- `evidence`: paths of output files you produced.
- `open_issues`: every plan-relevant surprise: deviation, blocker, difficulty, assumption, skipped work,
  residual risk.
