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

- `PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_plan_blocking packages.task.tests.test_journal packages.task.tests.test_plan_item_state` — `65` tests (`на 623b6395`), `OK`;
- `python3 -m json.tool packages/task/configs/block-candidate-v1.schema.json` — exit `0`;
- adversarial external-enum/`external=false` reproducer — `gather-rag`, `terminal_allowed=false`, `EXTERNAL_RAG_REQUIRED`, `rag-pending`;
- `git diff --check` — exit `0`.

Routing deviation: execution used `frontier/high`; Routing requires `implementation/high`.

## P4.2

Commit map:

- canonical product: `1ea10e74`;
- provider projections: `3f73c26d`;
- release-visible out-of-`Files` change: `dd9c098c`;
- umbrella docs projection: `f4916db8`;
- original bookkeeping: `52bf8e64`.

Validation on detached committed tree `f4916db8`:

- `python3 packages/task/scripts/render-provider-commands.py --root . --check` — `OK (no-op)`;
- `bash scripts/docs-sync.sh --check` — `docs/task` fresh;
- `PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_plan_blocking packages.task.tests.test_plan_command_routing packages.task.tests.test_canon_literals packages.task.tests.test_claude_command_adapter packages.task.tests.test_codex_command_adapter packages.task.tests.test_provider_command_parity` — `78` tests (`на f4916db8`), `OK`;
- `rg -l 'block-confirmation|task\.plan_blocking\.evaluate|rag-pending' packages/task/commands/plan-{design,exec,run,audit,close}.md` — all five command files;
- `bash packages/task/scripts/validate.sh` — `861` tests (`на f4916db8`), `OK (skipped=1)`, plan-lint `0` errors;
- `git diff --check` — exit `0`.

Status-rule: `dd9c098c` changes `CHANGELOG.md`, which is outside P4.2 `Files`; this is a
material deviation, so the terminal status is `🟠 Done with deviations`.
