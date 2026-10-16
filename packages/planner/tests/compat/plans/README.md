# Frozen plans of earlier engines

Each directory under `plans/` is a plan directory exactly as an earlier version of the plan engine wrote
it, kept as a regression fixture: the engine must keep reading it without migration.

- `engine-0.28.3` — the demo plan of engine 0.28.3 (plan, brief, phases, items, decisions, knowledge document
  and event log).

Frozen output of the plan engine 0.28.3; never regenerate and never edit. `test_old_plans.py` copies a fixture
into a temporary directory before it runs anything, so the files here stay untouched.
