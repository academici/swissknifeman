<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:835d6e3abe3d784d05b236a53c0d1c7bdf50676403d98ea7dff7b4cc0f06668f
Adapter: task.codex-command/1.0.4
-->
Это ИСПОЛНЕНИЕ item'а мастер-плана под моделью сессии (D18) — третий режим `plan-exec`,
БЕЗ пина `model`/`effort`: они наследуются из настроек текущей сессии владельца.
Ввод пользователя: «$ARGUMENTS».

Прочти `packages/task/commands/plan-exec.md` ЦЕЛИКОМ и исполни его пункты 1–8 ДОСЛОВНО,
с ТРЕМЯ отличиями:

- Модель/effort НЕ запинены: действуют настройки сессии владельца.
- **Pre-mutation/Pre-final write-site (P2.7/P2.11).** Литерал `"implementation", "medium",
  model="implementation"` встречается ДВАЖДЫ в `plan-exec.md` — Pre-mutation (шаг 2) И Pre-final (шаг 7,
  штатный путь закрытия, М5) — и ОТДЕЛЬНО `"implementation", "low", model="implementation"` в
  `plan-close.md`'s Pre-final шаг 4: пин ТЕХ команд, не этой. Подставляй ФАКТИЧЕСКИЕ
  `model_class`/`effort`/`model` ЭТОЙ сессии (те же значения, что уже прошли Routing-гейт ниже) в
  КАЖДЫЙ из трёх вызовов `route_evidence.capture_actual(...)`. Шаг остаётся ОБЯЗАТЕЛЬНЫМ в обеих
  точках `plan-exec.md` — замена лишь литералов, не условия. **Основание (D75, лестница
  разрешения маршрута исполнителя):** `plan-run` исполняет и закрывает item в ОДНОЙ сессии,
  поэтому её «фактический маршрут сессии» И ЕСТЬ маршрут исполнителя — на pre-final замена
  литерала остаётся верной той же логикой, что и на pre-mutation, без отдельной лестницы
  Completion Notes↔journal (та лестница нужна только реконсилирующему `plan-close`, который
  закрывает item, которого сам не исполнял).
- Routing-гейт п.2 инвертирован: сверяется ФАКТИЧЕСКАЯ модель/effort сессии с §3 Routing
  item'а (тир-порядок — plan-protocol §9). Недобор (модель или effort НИЖЕ предписанного)
  → СТОП «ROUTING-BLOCKED: Pn.m — предписано <model/effort>, сессия <фактическое>»,
  статус item'а НЕ меняется. Перебор → исполнять, запись в Known Deviations (§6
  `plan-exec.md`). Exec = plan-design → СТОП, ре-дизайн.
  **Журнал (D21, P1.1):** при `ROUTING-BLOCKED`/`ROUTING-INCONSISTENT` append ОДНУ запись
  `python3 -m task.journal append --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m>
  --command plan-run --actor <фактические model>/<фактический effort> --result blocked
  --friction routing-blocked --note "<предписано vs фактическое>"` — работа не начиналась,
  старт-запись плана-exec.md (п. 3) не пишется.

**Граница честности.** Самоатрибуция модели/effort агентом машинно НЕ проверяема (класс
B2 аудита REGHUB). Фактическая модель/effort ОБЯЗАНЫ быть напечатаны в отчёте (строка
`Session: <model>/<effort>`) и записаны в Update Log / Completion Notes наравне с прочими
фактами. Жёсткий машинный гейт остаётся за `plan-exec` (его пин делает недобор структурно
невозможным) — `plan-run` этот гейт НЕ заменяет, только снимает ритуал ручного
переключения модели/effort перед серией manual-item'ов под одной моделью.

Всё остальное (эскалация, validation, топология закрытия, status-rule, якорь дерева,
launch-block) — БЕЗ ИЗМЕНЕНИЙ из `plan-exec.md`; повторно здесь не транскрибируется
(правило двух SSOT).
