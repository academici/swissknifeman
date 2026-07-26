# Структура плана — канон папок 2.0

Канонический корень `plans/<PLAN-ID>/` по plan-protocol 2.0 (SSOT — скилл
`general/plan-protocol` §2–3). Обязательны только `plan.md` / `phases/` / `handoff.md`;
остальное опционально, по потребности плана.

```text
plans/<PLAN-ID>/
├── plan.md            # мастер-план: Meta, Context, Rules, Routing, Status Board, логи
├── phases/Pn.md       # по файлу на фазу: контекст, items (16 полей), phase handoff
├── handoff.md         # rolling-указатель «где мы» (перезаписывается, история — в git)
├── journal.jsonl      # append-only execution history
├── journal-exceptions.jsonl # optional D51 exact historical-schema exception sidecar
├── findings/          # RAG-выжимки и recon-отчёты (компактный синтез, не сырьё)
├── 20_research/       # research-артефакты плана
├── artifacts/         # рабочий материал фаз — судьба: архив вместе с планом
├── root/              # долгоживущий материал — судьба: документация проекта
└── open-questions.md  # спорное/нерешённое со статусами (не блокирует план)
```

Рядом с каталогами планов живёт `plans/ACTIVE.md` — 4-строчный указатель активного плана
(парсится `plan-lint`); плоские `.md` прямо в `plans/` — черновики plan mode,
разворачиваются `/task:plan-design from-draft <файл>`.

## Historical journal exception (D51)

`journal-exceptions.jsonl` optional and append-only: it never carries an event, status, or Next.
It may waive only an exact historical `friction` schema failure when the target physical line, raw
SHA-256, plan ID, exact field set, and an existing Owner D# all match. Any duplicate, malformed or
valid target, foreign plan, hash mismatch, or additional invalid field fails closed. Create it only
with `task.journal exception`; do not rewrite or compensate the historical journal event.

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

## Портируемость: два тира и требования к бандлу

План/задача несут **тир портируемости** — какой объём материала обязан ехать вместе с
заданием, чтобы холодная сессия исполнила его без чата. Enum тиров, оба кода отказа
(`PORTABILITY_INPUT_MISSING`, `PORTABILITY_EXTERNAL_INPUT`), блок `privacy` и пара
`semantic_carrier`/`provider_renderers` принадлежат Task Contract v1; **правило
классификации** — Plan Portability v1 (оба контракта — план `2026.07.24-AGENT-RELIABILITY`,
`root/contracts/`).

```text
tier(work) := committed-bundle   если work.sessions == "multi"
                                 ИЛИ work.risk == "high"
                                 ИЛИ work.handoff
                                 ИЛИ work.audit
              brief-acceptance   иначе
```

Тир назначает **корневой супервизор**, компилирующий Task Contract, ДО диспатча — не
исполнитель item'а и не субагент: субагент получает уже разрешённый тир, а не задачу
классификации. Пере-назначение — только при смене одного из четырёх признаков, записью с
прежним хешем в `supersedes`. Компилятор проверяется машинно: `plan_lint`
(`_lint_tiered_portability_22`, порог `PORTABILITY_TIER_CANON_DATE`) отклоняет, в этом
порядке: (1) тир, который правило не выдаёт для объявленной работы; (2) `committed-bundle`
с пустым `execution_inputs`; (3) путь, присутствующий и в `execution_inputs`, и в
`provenance_only`; (4) абсолютный / `~`-корневой / выходящий за корень / URL-образный вход;
(5) `produced-by-predecessor`-вход без названного производителя.

**Провенанс против execution input — по РОЛИ, не по написанию.** Путь — execution input,
если item его реально ЧИТАЕТ (он назван в `Inputs`/`Required Reads`/`Validation`); путь —
провенанс, если он лишь объясняет происхождение и ни одно поле item'а его не читает.
Подстрочный тест на `tmp/` неверен в обе стороны: закоммиченный читаемый путь с `tmp` в
имени — вход, а черновик, который исполнитель посмотрел, но ни одно поле не назвало, —
провенанс, где бы он ни лежал. Хост, чат, mAInd и чужие репозитории — провенанс по
построению.

**Что обязан нести `committed-bundle`** (не «всё, что было под рукой»):

| Требование | Смысл |
|:--|:--|
| Минимизация | только то, ради чего вход реально читается; `privacy.minimized = true`, а `privacy.excluded_classes` называет исключённое — сырые тела, chain-of-thought, tool-payload'ы, секреты |
| Детерминированный манифест **и** верификатор | целостность пересчитывается, а не заверяется: хеши считаются заново, не берутся на веру, верификатор коммитится вместе с бандлом |
| Полное замыкание зависимостей | вход, ссылающийся на другой артефакт, тянет его с собой — иначе холодная сессия падает на втором файле |
| Один нейтральный семантический carrier + provider-рендереры | отрендеренный Claude- или Codex-вызов — **проекция**, а не источник истины; `context` едет нейтральным литералом, русские строки командных файлов — его проекции |
| Класс доказательства | ни один публичный приёмочный предикат не стоит на `pinned-not-recomputable`/`unknown`; такой материал едет только как размеченный контекст |

**Классы доказательства** (закрытый enum, Source Evidence Verification v1): `recomputed`
(выведено заново из закоммиченных байт своим алгоритмом) · `cross-checked` (два и более
закоммиченных документа сверены друг с другом, ни один не считается истиной сам по себе) ·
`pinned-not-recomputable` (закоммиченная константа как размеченный контекст) · `unknown`
(база вывода ещё не установлена). Переход из двух последних классов в два первых —
только правкой списка утверждений контракта и алгоритма верификатора, **никогда прозой**.

## Форма `Next` и порядок закрытия item'а

`handoff.md` несёт `Next` ПЕРВОЙ СТРОКОЙ в одном из канонических видов: голая команда
`/task:plan-exec <ID> Pn.m`, форма «ЗАПУСК ВРУЧНУЮ: <model/effort>» (`Exec = manual`) или
`/task:plan-design|plan-close <ID> Pn`. Закрытый item обязан НАПЕЧАТАТЬ в `Completion Notes`
коды обеих границ — `pre_mutation:` и `pre_final:`, оба со значением `allow` (`n/a` зелёным
не считается). С 2026-07-27 это не только проза чеклиста аудита: `plan_lint`
(`_lint_write_site_codes_44`, порог `WRITE_SITE_CODES_CANON_DATE`) даёт ERROR на `🟢`/`🟠`
item'е, чья дата в колонке `Updated` таблицы `## Phase Status` не меньше порога, а кода нет
или он отличен от `allow`. Скоуп forward-only по дате **item'а**: закрытое до порога не
диагностируется вовсе — новый гейт не перекрашивает чужие живые планы задним числом.
Закрытие item'а — фиксированный порядок: дифф Scope →
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
