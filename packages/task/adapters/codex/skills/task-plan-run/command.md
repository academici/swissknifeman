<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:cc0aa54db2b972e103596bca3abe31d161a5d3916dd3eb2ff81e1794a52581a4
Adapter: task.codex-command/1.0.2
-->
Это ИСПОЛНЕНИЕ item'а мастер-плана под моделью сессии (D18) — третий режим `plan-exec`,
БЕЗ пина `model`/`effort`: они наследуются из настроек текущей сессии владельца.
Ввод пользователя: «$ARGUMENTS».

Прочти `packages/task/commands/plan-exec.md` ЦЕЛИКОМ и исполни его пункты 1–8 ДОСЛОВНО,
с ДВУМЯ отличиями:

- Модельsession effort setting НЕ запинены: действуют настройки сессии владельца.
- Routing-гейт п.2 инвертирован: сверяется ФАКТИЧЕСКАЯ модельsession effort setting сессии с §3 Routing
  item'а (тир-порядок — plan-protocol §9). Недобор (модель или effort НИЖЕ предписанного)
  → СТОП «ROUTING-BLOCKED: Pn.m — предписано <modelsession effort setting>, сессия <фактическое>»,
  статус item'а НЕ меняется. Перебор → исполнять, запись в Known Deviations (§6
  `plan-exec.md`). Exec = plan-design → СТОП, ре-дизайн.
  **Журнал (D21, P1.1):** при `ROUTING-BLOCKED`/`ROUTING-INCONSISTENT` append ОДНУ запись
  `python3 -m task.journal append --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m>
  --command plan-run --actor <фактические model>/<фактический effort> --result blocked
  --friction routing-blocked --note "<предписано vs фактическое>"` — работа не начиналась,
  старт-запись плана-exec.md (п. 3) не пишется.

**Граница честности.** Самоатрибуция моделиsession effort setting агентом машинно НЕ проверяема (класс
B2 аудита REGHUB). Фактическая модельsession effort setting ОБЯЗАНЫ быть напечатаны в отчёте (строка
`Session: <model>/<effort>`) и записаны в Update Log / Completion Notes наравне с прочими
фактами. Жёсткий машинный гейт остаётся за `plan-exec` (его пин делает недобор структурно
невозможным) — `plan-run` этот гейт НЕ заменяет, только снимает ритуал ручного
переключения моделиsession effort setting перед серией manual-item'ов под одной моделью.

Всё остальное (эскалация, validation, топология закрытия, status-rule, якорь дерева,
launch-block) — БЕЗ ИЗМЕНЕНИЙ из `plan-exec.md`; повторно здесь не транскрибируется
(правило двух SSOT).
