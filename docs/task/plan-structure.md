# Структура плана — канон папок 2.0

Канонический корень `plans/<PLAN-ID>/` по plan-protocol 2.0 (SSOT — скилл
`general/plan-protocol` §2–3). Обязательны только `plan.md` / `phases/` / `handoff.md`;
остальное опционально, по потребности плана.

```text
plans/<PLAN-ID>/
├── plan.md            # мастер-план: Meta, Context, Rules, Routing, Status Board, логи
├── phases/Pn.md       # по файлу на фазу: контекст, items (16 полей), phase handoff
├── handoff.md         # rolling-указатель «где мы» (перезаписывается, история — в git)
├── findings/          # RAG-выжимки и recon-отчёты (компактный синтез, не сырьё)
├── 20_research/       # research-артефакты плана
├── artifacts/         # рабочий материал фаз — судьба: архив вместе с планом
├── root/              # долгоживущий материал — судьба: документация проекта
└── open-questions.md  # спорное/нерешённое со статусами (не блокирует план)
```

Рядом с каталогами планов живёт `plans/ACTIVE.md` — 4-строчный указатель активного плана
(парсится `plan-lint`); плоские `.md` прямо в `plans/` — черновики plan mode,
разворачиваются `/task:plan-design from-draft <файл>`.

## root/ против artifacts/ — смысловое различие

Два каталога артефактов различаются судьбой, не форматом: `root/` — timeless-материал,
который переживёт план и станет docs проекта; `artifacts/` — рабочий материал фаз,
уезжающий в `plans/archive/<ID>` вместе с планом. Набор файлов `root/` — по потребности
плана, не все обязательны.

## Таблица миграции root/ → docs

При архивации плана (`/task:plan-close archive <ID>`) содержимое `root/` мигрирует в
документацию проекта по Diátaxis-типам:

| Файл в `root/` | Diátaxis-тип | Куда в docs проекта |
|:--|:--|:--|
| `architecture.md` | explanation | архитектурный раздел docs |
| `philosophy.md` | explanation | «почему так» — рядом с архитектурой |
| `data-model.md` | reference | справочник модели данных |
| `contracts/` | reference | справочник контрактов/API |
| гайды фаз | how-to | практические руководства |

Чек-лист миграции (что перенесено в docs, что осталось в архиве) — обязательная часть
финального `handoff.md` архивированного плана.

## Routing (§3 плана) — колонка Exec

Таблица `## 3. Routing` в `plan.md` несёт колонку **Exec** (enum `plan-exec` | `manual` |
`plan-design`) поверх model/effort per-item. Пустая ячейка — деривация по тир-порядку
(`haiku < sonnet < opus ≈ fable`, `low < medium < high < xhigh < max`): `model ≤ sonnet` И
`effort ≤ medium` → `plan-exec`; иначе → `manual`. `plan-exec` (команда пинит sonnet/medium)
отклоняет item с `Exec = manual`/`plan-design` на предусловии — запуск только вручную под
предписанной моделью/effort.

## Contracts (§7/§11 плана) — cross-plan notification

Секция `## 7. Contracts` в `plan.md` фиксирует публичный контракт плана: `### Exported`
(версия SemVer, что заморожено, дата уведомления потребителей) и `### Consumed` (какие
контракты других планов использует, что замечено на их обновлении, реакция). Item, бампающий
Exported-контракт, обязан в том же bookkeeping-коммите обновить строку `Exported` донора и
строку `Consumed` каждого плана-потребителя **в том же корне `plans/`**; кросс-репо push —
задача шины mAInd, не plan-протокола (в `open-questions.md` донора остаётся запись).

## Форма `Next` и порядок закрытия item'а

`handoff.md` несёт `Next` ПЕРВОЙ СТРОКОЙ в одном из канонических видов: голая команда
`/task:plan-exec <ID> Pn.m`, форма «ЗАПУСК ВРУЧНУЮ: <model/effort>» (`Exec = manual`) или
`/task:plan-design|plan-close <ID> Pn`. Закрытие item'а — фиксированный порядок: дифф Scope →
`validate.sh` пакета → bookkeeping плана (статусы, Completion Notes, Update Log) → перезапись
`handoff.md` → `plan-lint --baseline HEAD` **после** handoff → счёт публикуется с атрибуцией
(«новых от диффа item'а: K») → bookkeeping-коммит. Прогон `plan-lint` до перезаписи `handoff.md`
запрещён — закрывающий item сам меняет handoff, и счёт «до» не описывает итоговое дерево.

## Open Questions — протокол

Спорный пункт НЕ блокирует план, если вынесен в `open-questions.md` с одним из статусов:
`Exploration` · `Decision pending (нужен владелец)` · `Resolved → D#`. Вопрос, «висящий»
в теле фазы без выноса, — находка аудита; закрытие плана с pending-вопросами — только
`🟠 Done with deviations`. Re-design поверх закрытых фаз — новый D# со ссылкой «supersedes
D#-старый», старый D# не редактируется.

## Два дома плана

Где живёт SSOT — определяется стадией (скилл §12): до старта exec — Brain; на старте exec
план переезжает в репо проекта (Meta `Home: repo:<путь>`), Brain-копия становится зеркалом
(`brain sync`); после завершения — синк обратно → архив → миграция `root/` в docs. Полный
цикл — [Методология](/task/methodology).
