# Journal same-plan invariant — audit-r3 F1 remediation verification

**Дата:** 2026-07-20  
**Вход:** `design-audit-2026-07-19-r3.md` F1  
**Режим:** точечная remediation design audit, не execution

## Verdict

Audit-r3 F1 закрыт на implementation/test seam без изменения published contract: event и
exception `plan_id` теперь обязаны совпадать с canonical ID текущего plan directory
(`Path(plan_dir).name`) в writer; linter выдаёт отдельный non-exemptable ERROR для event
mismatch и не позволяет foreign sidecar сделать строку допустимой. D51, sealed event schema,
plan-protocol 2.10.0 и task plugin 0.2.0 не менялись.

RAG:— (repo-grounded: `packages/task/lib/task/{journal.py,plan_lint.py}` и F1 audit-r3).

## Negative matrix

| Carrier/path | Probe | Expected |
|:--|:--|:--|
| writer event | `entry.plan_id != plan_dir.name` | reject before append; journal bytes не создаются |
| writer target event | target event foreign, sidecar canonical | reject target provenance |
| writer sidecar | event+sidecar foreign и совпадают друг с другом | reject sidecar against directory ID |
| writer exact fields | target invalid по `command` + `friction`, sidecar перечисляет только `friction` | reject; exact set = `['command', 'friction']` |
| linter event | otherwise-valid foreign event | non-exemptable plan-ID ERROR |
| linter event+sidecar | foreign event + matching foreign sidecar | sidecar ERROR + event mismatch ERROR + raw schema ERROR |
| linter exact fields | target invalid по двум полям, sidecar перечисляет одно | sidecar ERROR; raw event остаётся ERROR |

## Verification

Commands:

```bash
PYTHONPATH=packages/task/lib:packages/task/tests python3 -m unittest \
  packages.task.tests.test_journal \
  test_plan_lint.TestJournalIndexLayer
PYTHONPATH=packages/task/lib:packages/task/tests python3 -m unittest \
  test_plan_lint.TestJournalIndexLayer.test_foreign_event_and_sidecar_plan_ids_cannot_exempt_mismatch
python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER
bash packages/task/scripts/validate.sh
bash packages/skiller/scripts/check-translations.sh
git diff --check
```

- Targeted writer/linter slice: **39/39 OK**.
- Full task suite: **193/193 OK**.
- `bash packages/task/scripts/validate.sh`: exit `0`; suite **193/193 OK**; root scan
  `0 ERROR / 75 WARN`, все warnings pre-existing/out-of-scope legacy plans.
- Strict translation gate: `160` local skills, `0` stale/missing EN markers,
  `0` lost literals.
- `git diff --check`: exit `0`.
- Current scoped lint:
  `python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER` →
  **0 ERROR / 0 WARN**, exit `0`.
- Independent wrong-plan probe: **3 ERROR / 0 WARN**, exit `1`: foreign sidecar,
  non-exemptable event mismatch и исходная `friction` schema error.
- Historical row 11 SHA-256 remains
  `94307a3c3bfaf4c5d5d67ea32d8eacb09410a396b0a217ab2eb094b518693184`;
  D51 sidecar still names only `invalid_fields:["friction"]`.

## Anchors

- `HEAD`: `9844f499797faf063aede49b79703c71f7ef666e`.
- Toolchain snapshot (`journal.py`, `plan_lint.py`, two targeted test files):
  `sha256:e13065b37148713474ed41f5dad1baa99e4528675a5880cef469d9c467b3e703`.
- Final plan lint-input snapshot, excluding only this verification carrier:
  `sha256:ee59893fff14992e52990364a5f8bfabc89d63f30577c4eaa68da6e68a41a012`.
- P0.1–P7.4 remain `⬜ Not started`; no execution item was run.
- `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, fleet, instruction remediation P5.6→P7
  and unrelated user changes were not modified by this remediation.

## Contract impact

Нет: research 14 и D51 уже требовали target event того же плана. Remediation реализует
это существующее обещание; поэтому lifecycle canon/research/D# и SemVer остаются без правок.
Следующий шаг — независимый design audit r4; P0.1 до literal GREEN закрыт.
