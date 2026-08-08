## §2. Читаемый факт → источник → команда (закрытый список источников)

**Закрытый список источников.** S1–S3 — готовые машинные читатели (межпакетная граница —
ПРОЦЕСС, а не импорт: `import task.*` и склейка `sys.path` к `packages/task/lib` запрещены,
D29). S4–S5 — собственный разбор драйвера, каждый с обоснованием в §3.

| ID | Источник | Команда |
|:--|:--|:--|
| S1 | модель плана целиком | `python3 packages/task/scripts/plan-lint.py <plan-dir> --json` |
| S2 | маршрут item'а из `## 3. Routing` | `PYTHONPATH=packages/task/lib python3 -m task.task_contract build --plan-dir <plan-dir> --item <Pn.m>` |
| S3 | запись события в журнал | `PYTHONPATH=packages/task/lib python3 -m task.journal append …` |
| S4 | собственный разбор ячейки `Exec` строки `## 3. Routing` | — (§3.1) |
| S5 | собственный разбор ТОКЕНА формы в первой непустой строке поля `**Next:**` | — (§3.2) |

| Читаемый факт | Источник | Где именно лежит |
|:--|:--|:--|
| Meta плана (`Plan ID`, `Version`, `Status`, `Closure Protocol`, …) | S1 | `plans.<ID>.meta.<Поле>` |
| Статус ФАЗЫ и счётчик `Items 🟢/всего` | S1 | `plans.<ID>.status_board[]` (строки таблицы §4) |
| Очередь фазы — порядок и состав строк `## Phase Status` | S1 | `plans.<ID>.phases.<Pn>.status_table[]` |
| Статус item'а | S1 | `plans.<ID>.phases.<Pn>.items.<Pn.m>.fields.Status` |
| Любое из 16 полей item'а (`Pending Work`, `Known Deviations`, `Escalation Needed`, `Completion Notes`, `Files`, …) | S1 | `plans.<ID>.phases.<Pn>.items.<Pn.m>.fields.<Поле>` |
| Блок `## Phase Handoff` фазы | S1 | `plans.<ID>.phases.<Pn>.phase_handoff` |
| Адресат последнего шага (`after Pn` / `after Pn.m`) | S1 | `plans.<ID>.handoff.title_ref` |
| Сырой текст поля `**Next:**` и остальных полей handoff | S1 | `plans.<ID>.handoff.fields.<Поле>` |
| Схемная легальность плана (ERROR/WARNING) и счёт НОВЫХ ошибок от git-ref | S1 | stderr + строка счёта; `--baseline <SHA> --gate new` |
| Маршрут item'а `model_class`/`effort` | S2 | `route.required.{model_class,effort}` |
| Коды границ Task Contract (`pre_mutation`/`pre_final`) | S2 | `task_contract check --contract <файл>` |
| Дозапись события волны в `journal.jsonl` | S3 | `append --plan-dir … --plan … --item … --command … --result … --run-id …` |
| Значение ячейки `Exec` строки §3, покрывающей item | **S4** | §3.1 |
| Какая из 11 форм `Next` объявлена | **S5** | §3.2 |

**Проверено прогоном 2026-08-01 на `06fefc87`** (каждая команда завершается кодом, который
контракт называет):

```bash
python3 packages/task/scripts/plan-lint.py plans/2026.07.31-SKM-LEAN --json          # exit 0
PYTHONPATH=packages/task/lib python3 -m task.task_contract build \
  --plan-dir plans/2026.07.31-SKM-LEAN --item P3.1                                   # exit 0
PYTHONPATH=packages/task/lib python3 -m task.journal append --help                   # exit 0
```

**Отказ источника — fail-loud, а не ноль.** Пакет `task` недоступен, ненулевой код, неразбор
JSON → драйвер объявляет шаг НЕДОСТУПНЫМ и отказывает в вождении с названной причиной; пустая
очередь как «нечего делать» в этом случае запрещена (RAG:— (repo-grounded: `plan.md` §5 D29 —
«отсутствие пакета → fail-loud «шаг недоступен», не тихая деградация»)).

**Коды возврата S1** (`plan_lint.py:2338–2404`): `1` — путь не найден; при `--gate all`
(дефолт) `0`/`1` по всем диагностикам; при `--gate new` — `0`/`1` по числу НОВЫХ от
`--baseline`. **Деградация:** baseline недоступен (не git-репозиторий / ref не найден /
`git archive` не удался) → линтер печатает WARNING «baseline «<ref>» недоступен: … — счёт новых
ошибок не вычислен», `new_count` остаётся `None`, и `--gate new` падает обратно к оценке по ВСЕМ
диагностикам (`plan_lint.py:2287–2333`, `:2379–2386`, `:2402–2404`). Драйвер обязан распознать
этот класс и пометить его в вердикте (§7).

**Закрытые enum'ы журнала (S3)**, читаются и передаются дословно, свои значения не
изобретаются (`journal.py:39–50`):

```text
COMMANDS        = plan-exec · plan-run · plan-close · plan-audit · plan-design
RESULT_VALUES   = in-progress · closed-green · closed-deviations · blocked ·
                  escalated · no-op · audit-green · audit-red
FRICTION_VALUES = escalation · routing-blocked · red-audit · deviation · retry · no-op
REQUIRED_FIELDS = ts · plan_id · item_id · command · session_id · run_id · attempt ·
                  actor · friction · result · cost_usd · num_turns · duration_ms · note
```

`run_id` — штатное поле схемы и ЕДИНСТВЕННЫЙ дискриминатор строк драйвера (у строк воркера
`null`: `packages/task/commands/plan-exec.md` шаги 3 и 7 его не передают). Правило «кто пишет
строку» — предмет P4.5 (D32), здесь фиксируется только сам факт наличия дискриминатора и
закрытость enum'ов.


### §3.2. S5 — токен формы в первой непустой строке поля `**Next:**`

**Обоснование (пятый источник, правило Implementation Rules (2) item'а P4.1).** S1 отдаёт
поле `**Next:**` СЫРЫМ текстом (`plans.<ID>.handoff.fields.Next`); РАЗРЕШЁННУЮ форму
`lint_plan` резолвит внутри себя и в модель `--json` не кладёт (проверено прогоном: ключи
`handoff` = `path` · `title_ref` · `fields`). Ни S1, ни S2, ни S3 не отвечают на вопрос
«КАКАЯ из 11 форм объявлена», поэтому разбор заводится драйвером — и сведён к минимуму:

```text
форма объявляется ПЕРВОЙ непустой строкой поля (канон §8, D40) — ниже неё резолвер не смотрит;
читается ТОЛЬКО префиксный токен до двоеточия, по закрытому набору plan_lint.SEMANTIC_NEXT_RE
(plan_lint.py:127–129):
  exec-items · run-items · audit-design · design-phase · design-item ·
  audit-phase · close · archive · terminal · manual · waiting
исторические входы совместимости (plan_lint.py:107, :115–126, :140–141):
  /task:… формы · «ЗАПУСК ВРУЧНУЮ» · «ОЖИДАНИЕ:»
```

**Границы разбора, названные явно.**

- ЛЕГАЛЬНОСТЬ формы драйвер не решает — её гейтит S1: форма вне enum есть ERROR линтера
  (`plan_lint.py:2166`, текст `NEXT_FORMS_HELP` `:142–150`). Собственный разбор отвечает
  только на «какая именно», и при неудаче классификации даёт отказ `NEXT-FORM-UNSUPPORTED`
  (fail-safe: догадка запрещена).
- **Условие формы `waiting:` драйвер НЕ вычисляет.** Канон §8 требует, чтобы условие было
  СТРУКТУРНЫМ (дата, гейт, счётчик), но его истинность — суждение владельца; драйвер читает
  форму и останавливается, а не «ждёт до».
- Полезная нагрузка launch-block (таблица параметров, code-block, строки
  `РЕЖИМ:`/`ВХОД:`/`СКОУП:`/`НЕ ТРОГАТЬ:`) драйвером не разбирается — потребителя нет.


## §8. Правило breaking-детекта

**Несовместимая смена схемы канона БЕЗ синхронного бампа этого контракта = breaking.**
Единственное действие — **остановить волну и эскалировать владельцу**. Варианта «продолжить на
устаревшей схеме» в контракте нет.

Закрытый перечень якорей (иных оснований объявить breaking у драйвера нет):

| # | Якорь | Что ломается | Где зафиксирован |
|:--|:--|:--|:--|
| 1 | новый статус вне ШЕСТИ канонических | сверка статусов слепнет | §4.1 |
| 2 | смена формы заголовка `handoff.md` | адресат шага не резолвится | §4.4 |
| 3 | новая ОБЯЗАТЕЛЬНАЯ форма `Next` вне enum из ОДИННАДЦАТИ | шаг не классифицируется | §4.2, §3.2 |
| 4 | смена шапки/колонок Status Board (`## 4.`, колонка `Items 🟢/всего`) | прогресс фазы не читается | §4.3 |
| 5 | смена полей JSON-конверта (`type`/`is_error`/`result` переименованы или удалены) | исход прогона не судится | §6.2 |
| 6 | смена формы ячеек `## 3. Routing` (закрытый набор форм `Items`, имя/enum колонки `Exec`, набор заголовков колонки маршрута) | право вождения не определяется | §3.1 |

**Как детектируется.** Перед волной: версия скилла из frontmatter против строки `pinned` (§1),
`git rev-parse HEAD` против пинованного коммита, `claude --version` против `client_pinned`.
Расхождение любой из трёх строк — не автоматический breaking, а ТРЕБОВАНИЕ сверить якоря 1–6 и
бампнуть контракт; невозможность сверить = стоп и эскалация.

**Приоритет носителей.** При расхождении «контракт vs скилл» прав СКИЛЛ: правится контракт
(бамп версии документа + новая строка `pinned` + дата сверки), а не парсер под удобную
трактовку и не канон под драйвер. Правка чужого пакета (`plan_lint.py`, `task_contract.py`,
`journal.py`, `command-routing.json`) драйвером запрещена — они ВЫЗЫВАЮТСЯ; замеченный в них
дефект уходит владельцу пакета через `package-contribution-protocol`, а не в дифф драйвера.
