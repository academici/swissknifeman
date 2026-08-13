---
date: 2026-08-13
phase: P4
source: Audit P4 repair-forward
---

# P4 committed-tree evidence

## P4.1

Commit map:

- product: `aefd1450`;
- write-site product repair: `cc7a0523`;
- audit product repair: `623b6395`;
- original bookkeeping: `0c70c57c`.

Validation on detached committed tree `623b6395`:

- `PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_plan_blocking packages.task.tests.test_journal packages.task.tests.test_plan_item_state` — `65` tests, `OK`;
- `python3 -m json.tool packages/task/configs/block-candidate-v1.schema.json` — exit `0`;
- adversarial external-enum/`external=false` reproducer — `gather-rag`, `terminal_allowed=false`, `EXTERNAL_RAG_REQUIRED`, `rag-pending`;
- `git diff --check` — exit `0`.

Routing deviation: execution used `frontier/high`; Routing requires `implementation/high`.
