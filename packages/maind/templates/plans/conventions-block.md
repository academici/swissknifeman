## Plans

Master plans live in `plans/<PLAN-ID>/` with `plan.json`, `brief.json`, JSON phase/item contracts
and `log.jsonl`. Use the installed planner plugin (`skills/plan-protocol`) and `scripts/plan.py`
for authoring and execution. Read JSON context through `plan.py context … --stdout`.
Human Markdown is generated under `views/` and excluded from indexing and agent input.
Archived plans are historical evidence; new plans always use the current JSON schema.
