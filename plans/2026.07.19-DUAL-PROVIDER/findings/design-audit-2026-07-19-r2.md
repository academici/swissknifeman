# Design audit — 2026.07.19-DUAL-PROVIDER — заход 2

**Дата:** 2026-07-19  
**Режим:** повторный adversarial design audit после remediation audit-red  
**Вердикт: RED**

## Anchor и plan-lint

- `HEAD`: `9844f499797faf063aede49b79703c71f7ef666e`.
- Audit-input worktree snapshot: `sha256:55aef78fdbdbc056f6703d40677507b50c356239506b529e17d371259f84e85e`.
  Это SHA-256 отсортированного manifest всех файлов plan directory до разрешённых audit writes;
  воспроизводящая команда:
  `find plans/2026.07.19-DUAL-PROVIDER -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum`.
- Post-journal lint-input snapshot: `sha256:caba5c2e64e16c2fcc9680e56e05eb222cb67958aabd50cad426d7405c8f55e8`.
  Он включает terminal audit row этого захода и исключает только сам audit-report carrier,
  поэтому остаётся воспроизводимым после публикации отчёта; команда:
  `find plans/2026.07.19-DUAL-PROVIDER -type f ! -path 'plans/2026.07.19-DUAL-PROVIDER/findings/design-audit-2026-07-19-r2.md' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum`.
- Current command:
  `python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER`.
- Exact result на обоих указанных lint-input snapshots: **1 ERROR / 0 WARN**; exit code `1`.
- Единственная диагностика: `journal.jsonl:11` — `friction` содержит значения вне закрытого
  enum P1.1.

## Findings

### F1 — append-only correction не принимается current plan-lint

- **Severity:** Blocker
- **Label:** issue
- **Item:** design / journal lifecycle
- **Evidence:** `journal.jsonl:11`; compensating rows `journal.jsonl:22` и
  `journal.jsonl:25`; `plan.md:168` (D49); `packages/task/lib/task/journal.py:36-38,93-95`;
  `packages/task/lib/task/plan_lint.py:781-792`.
- **Failure scenario:** историческая строка 11 остаётся schema-invalid; текущий lint валидирует
  каждую строку независимо и не определяет ссылочную correction/supersession semantics. Валидные
  append-only rows 22/25 не могут погасить ошибку строки 11. Поэтому pre-exec gate `plan-lint
  green` недостижим одновременно с запретом переписывать историю; запуск P0.1 нарушил бы явный
  execution gate плана.
- **Требуемая remediation:** owner-approved, непротиворечивый и нециклический contract для
  исторически invalid rows: либо каноническая correction-record semantics, понимаемая writer,
  schema и linter, либо явно разрешённое provenance-preserving исключение. После фактического
  применения — current anchored `0 ERROR / 0 WARN` и повторный design audit. Audit не выбирает
  вариант и не исправляет package code/items.

## Проверено без находок

- Owner refinement имеет executable carriers: P5.6 замораживает common instruction contract,
  P5.7 реализует explicit catalog/fragments/render/lock/conformance.
- Producer order согласован: P5.6 → P5.7 → P6.2 → P6.5 → NEW SESSION P6.6 → P7;
  P7 не проектирует release-critical instruction mechanism впервые.
- Target exact-set — root + пять packages (`skiller`, `harness`, `maind`, `analyst`, `task`);
  common/provider-extension blocks, user-owned bytes вне markers, full contract/catalog/fragment
  source SHA-256, rendered SHA-256, parity/drift/repair и Claude back-compat имеют contract,
  implementation и independent validation carriers.
- Restart traceability ведёт на P6.5 disk+mAInd checkpoint и P6.6 cold-session proof, включая
  instruction source/render hashes и root/five-package semantic IDs.
- Structural sweep: **39/39 items**, у каждого ровно 16 обязательных полей; Required Reads конечны
  и ordered, future paths имеют более ранний producer; Validation и Deliverables заполнены.
- Routing exact-set: **39/39**, из них `11 plan-exec` и `28 manual`; roadmap exact-set **39/39**,
  без duplicate item rows; solo/restart/owner-gate обоснования согласованы с dependencies.
- Historical design starts 1–10 получили append-only terminal backfills 12–21; original audit
  row 11 сохранена. Остаточный defect — только отсутствие исполнимой correction semantics F1.
- `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, fleet, package code/tests/items и unrelated
  user changes не изменялись и не исполнялись.

## Что запускать

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high |
| Context | NEW SESSION — шаг-не-item |
| Суть | Спроектировать нециклическую remediation journal/linter contract и вернуть current plan-lint к нулю до нового audit |

```
$ task:plan-design 2026.07.19-DUAL-PROVIDER finish

РЕЖИМ: remediation повторного design audit, НЕ execution
ВХОД: plans/2026.07.19-DUAL-PROVIDER/findings/design-audit-2026-07-19-r2.md → F1; прочитать ПЕРВЫМ
СКОУП: 1) owner-gated устранить противоречие append-only history и strict per-line schema 2) задать исполнимый нециклический carrier correction/supersession semantics либо явного provenance-preserving исключения 3) синхронизировать journal writer/schema/linter/plan lifecycle и получить current anchored 0 ERROR / 0 WARN 4) подготовить повторный design audit без запуска P0.1
НЕ ТРОГАТЬ: P0.1–P7.4 package implementation/items; plans/2026.07.18-FOREMAN/**; plans/ACTIVE.md; fleet; instruction remediation P5.6→P7, кроме ссылок, необходимых для journal gate; unrelated user changes
```
