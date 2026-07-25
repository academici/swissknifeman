# Design audit — 2026.07.19-DUAL-PROVIDER — заход 4

**Дата:** 2026-07-20  
**Режим:** повторный adversarial design audit r4 после точечной remediation audit-r3 F1  
**Вердикт: GREEN**

## Anchor и plan-lint

- `HEAD`: `9844f499797faf063aede49b79703c71f7ef666e`.
- Audit-input plan snapshot до разрешённых audit writes:
  `sha256:e6821a456e8dff234e23993d331dcc6affe14531a54f6570953a3169b297e69f`.
  Команда: `find plans/2026.07.19-DUAL-PROVIDER -type f -print0 |
  LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum`.
- Remediation verification snapshot, исключающий только его self-referential carrier,
  воспроизведён точно:
  `sha256:ee59893fff14992e52990364a5f8bfabc89d63f30577c4eaa68da6e68a41a012`.
- Current F1 toolchain snapshot (`journal.py`, `plan_lint.py`, два targeted test-файла)
  воспроизведён точно:
  `sha256:e13065b37148713474ed41f5dad1baa99e4528675a5880cef469d9c467b3e703`.
- Canon/version carrier snapshot (`task` plugin, `plan-design`, EN/RU plan-protocol,
  journal template):
  `sha256:b4217753e58230e64a1b695b198d948cefc80826be471a1eed7094a2d1f67200`.
- Post-terminal-journal lint-input snapshot, исключающий только этот audit-report carrier:
  `sha256:0a784cc2ae63b6cf8256b1d45c7e709a0ece2ec34b3c7ed51c834a8443192388`.
- `journal.jsonl:11` без newline:
  `sha256:94307a3c3bfaf4c5d5d67ea32d8eacb09410a396b0a217ab2eb094b518693184`;
  sidecar по-прежнему несёт `target_line:11`, тот же hash,
  `invalid_fields:["friction"]` и `owner_decision:"D51"`.
- `python3 packages/task/scripts/plan-lint.py
  plans/2026.07.19-DUAL-PROVIDER` до terminal append: **0 ERROR / 0 WARN**, exit `0`.

## Findings

Находок нет. Audit-r3 F1 закрыт; новых fail-open или регрессий в заявленном scope не
воспроизведено.

## F1 — проверено без находок

### Canonical plan-directory binding

- Writer event: `packages/task/lib/task/journal.py:283-298` валидирует schema, затем
  требует `entry.plan_id == Path(plan_dir).name` до открытия `journal.jsonl`. Независимый
  probe с foreign event получил `JournalValidationError`; файл не был создан.
- Writer sidecar/target: `journal.py:187-229` отдельно требует canonical directory ID у
  sidecar и target event до exact-field waiver. Независимые probes
  `foreign-target/canonical-sidecar` и `foreign-target/foreign-sidecar` оба отклонены.
- Linter: `packages/task/lib/task/plan_lint.py:758-846` валидирует sidecar через тот же
  writer SSOT, а event mismatch репортит отдельным ERROR до schema-waiver. `lint_plan()`
  задаёт canonical ID как `plan_dir.name` (`plan_lint.py:1158-1162`).

### Non-exemptable mismatch и exact field-set

- Wrong-plan temp-root probe: foreign event + matching foreign sidecar + invalid friction
  дал **3 ERROR / 0 WARN**, synthetic exit `1`: foreign sidecar, отдельный event mismatch
  и исходная schema error. Sidecar не подавил ни mismatch, ни raw schema defect.
- Exact-set temp-root probe: target с invalid `command` + `friction`, sidecar только с
  `invalid_fields:["friction"]`, дал **2 ERROR / 0 WARN**, synthetic exit `1`:
  sidecar exact-set ERROR + raw event schema ERROR.
- Writer exact-set probe отклонён с фактическим множеством
  `['command', 'friction']`. Равенство множеств гейтится в `journal.py:223-229`, а
  duplicate values/неразрешённые поля — в `journal.py:130-164`.
- Targeted regression carriers присутствуют: writer foreign event
  (`test_journal.py:127-134`), writer foreign target/sidecar и exact set
  (`test_journal.py:210-228`), linter non-exemptable event, foreign event+sidecar и
  exact set (`test_plan_lint.py:162-238`).

## Независимая verification matrix

| Gate | Фактический результат |
|:--|:--|
| Targeted writer/linter slice | `39/39 OK`, exit `0` |
| Full `packages/task` unittest | `193/193 OK`, exit `0` |
| `bash packages/task/scripts/validate.sh` | exit `0`; `193/193 OK`; root scan `0 ERROR / 75 WARN`, warnings только вне этого плана |
| Scoped plan-lint до terminal append | `0 ERROR / 0 WARN`, exit `0` |
| Wrong-plan probe | `3 ERROR / 0 WARN`, exit `1` |
| Exact-set probe | `2 ERROR / 0 WARN`, exit `1` |
| Translation gate | `160` local skills; `0` stale/missing EN markers; `0` lost literals |
| `git diff --check` | exit `0` |

## Contract/canon/D51 и r3 non-F1 regression check

- Published contract не менялся: sealed
  `plans/2026.07.18-FOREMAN/root/contracts/plan-journal-schema.md` имеет нулевой git diff.
  R3 уже цитировал same-plan promise; current EN/RU canon сохраняет его в
  `plan-protocol/SKILL.md:73-83` / `SKILL.ru.md:73-83`. Remediation реализует существующее
  обещание и не расширяет contract.
- Версии остаются `task 0.2.0` и `plan-protocol 2.10.0`; RU source hash
  `ed305ad41de0e2b37bd5d363da8c7f01f436e8d2d649be52e2bca6003f4e9c47`
  совпадает с EN `ru-source-sha256`; strict translation gate зелёный.
- D51 остаётся единственной D5x-записью (`plan.md:170`), D52 не создана;
  `research/14-journal-schema-exception-remediation.md` по-прежнему требует same-plan
  target и exact fields. Event schema сохраняет 14 полей, закрытые enum counts
  `command=5`, `friction=6`, `result=8`; sidecar — ровно 8 полей, v1 exemptable field
  только `friction`.
- Все **39/39** execution items имеют ровно 16 canonical fields в точном порядке и
  `⬜ Not started` и в item field, и в Phase Status. Routing покрывает **39/39** unique:
  `11 plan-exec`, `28 manual`; execution-map roadmap — **39/39 unique**, без дублей.
- Instruction producer/consumer boundary не регрессировал: P5.6→P5.7 остаётся
  contract→implementation (`phases/P5.md:161-193`); P6.2/P6.5/P6.6 несут
  deploy/repair и split restart evidence (`phases/P6.md:81-95,139-172`); P7 явно
  запрещает новый mechanism design и остаётся consumer/verification-only
  (`phases/P7.md:13-14,29,48,144`).
- P0.1 остаётся закрыт: Phase Status и item field — `⬜ Not started`
  (`phases/P0.md:34,41`), journal не содержит ни одной строки execution item
  `P0.1`–`P7.4`, а roadmap разрешает P0.1 только после literal GREEN design audit
  (`roadmap.md:94-105`). Этот r4 GREEN является первым разрешающим verdict; сам audit
  P0.1 не запускал.
- `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, fleet, package files,
  instruction remediation P5.6→P7 и unrelated user changes этим audit не изменялись.

## Что запускать

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | Пересчитать inventory/provider-coupling baseline без package mutation |

```
$ task:plan-exec 2026.07.19-DUAL-PROVIDER P0.1 — cold-start reads: plans/2026.07.19-DUAL-PROVIDER/{plan.md,roadmap.md,phases/P0.md,research/03-p0-design-and-premortem.md,findings/repository-baseline-2026-07-19.md,brief/00-brief.md}; gate: design audit r4 GREEN
```
