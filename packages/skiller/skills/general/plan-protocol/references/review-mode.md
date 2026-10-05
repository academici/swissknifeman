# Review mode

Applies to `task:plan-audit` and to a review item added by `--review`.

1. Runs only on explicit owner request: one reviewer, one pass over the whole target, no subagents
   unless the owner asked.
2. Read-only over product code and plan JSON. Inputs: `plan.py show`, `plan.py check`, the item
   context packs, the product diff, recorded check results.
3. Judge against the item contracts: scope, acceptance checks, deliverables, decisions.
4. Each finding: severity by demonstrated impact, evidence (`path:line` or command output), owning
   item. Uncertainty is a question, not a defect.
5. Output: a verdict file (`GREEN`, `ATTENTION` or `RED`) under `@plan/artifacts/audit/` and one
   `plan.py log <Pn> --type note` event naming it.
6. Fixes are execution work of the owning item (`plan.py reopen` by the owner when it is closed);
   the reviewer does not fix and does not start a second pass without a new question.
