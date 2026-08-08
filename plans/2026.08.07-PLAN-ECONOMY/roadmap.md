# Roadmap исполнения — 2026.08.07-PLAN-ECONOMY

<!-- Собран после детализации всех семи фаз (P6 — последняя). Отвечает на «какую команду
     дальше?» без анализа всего плана. Живой документ: закрытие фазы / re-design обновляет
     таблицу (+строка в Update Log). Roadmap НЕ переопределяет §3 Routing — только группирует
     запуски. -->

**Обновлён:** 2026-08-08 (D118–D126: shared-first multiprovider; adaptive review; machine-gated session canary; P0 и P1.1–P1.4 закрыты) · **Соответствует plan.md:** v0.24.0

## Как читать

Из 45 items **42 несут `Exec = manual`** (§3 Routing): их не исполняет `task:plan-exec` —
носитель либо голый промпт item'а, либо `task:plan-run <ID> Pn.m` под ПРОВЕРЕННЫМ маршрутом
сессии. Три item'а (`P0.2`, `P2.6`, `P6.9`) — `plan-exec` (`P0.4` ушёл в `manual` по D110).

**Почти всё — `solo`, и это не небрежность батчинга.** Критерий слияния требует НИЗКОЙ сцепленности
и МАЛОГО объёма подфаз; здесь же почти каждый item либо замораживает контракт (владельческая или
необратимая семантика), либо делает хирургию по живому линтеру флота с обязательным дословным
сравнением диагностик, либо несёт приёмочный замер. Два батча заведены там, где сцепленность
действительно низкая, а маршрут и глубина ревью совпадают.

**Носитель батча — колонка `Batch` в `## 3. Routing`** (`plan-protocol` §9); колонка `Batch` этой
карты её ПОВТОРЯЕТ для удобства запуска и не является вторым источником истины. Расхождение карты
с §3 Routing — дефект карты, а не разрешение: карта группирует запуски и никогда не переопределяет
маршрут.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-run (manual) | implementation/high | — | ✅ terminal — neutral core + thin Codex usage adapter; 8 real samples, ≤128 KiB/≤12 calls; Claude deferred; v1 evidence сохранён |
| P0.2 | solo | plan-exec | implementation/medium | — | ✅ terminal — эмпирический зонд среды |
| P0.3 | solo | plan-run (manual) | implementation/high | — | ✅ terminal — инструмент замера против замороженной калибровки |
| P0.4 | solo | plan-run (manual) | implementation/high | — | ✅ terminal — учёт корней `sweep` и замер флота |
| P0.5 | solo | plan-run (manual) | frontier/high | ✅ решения получены D113–D115 | ✅ terminal — read-budget 100 000, только новые layout-v2, без legacy |
| P1.1 | B1 | plan-run серия | frontier/high | — | ✅ terminal — реестр носителей |
| P1.2 | B1 | ↑ | frontier/high | — | ✅ terminal — форма слепка |
| P1.3 | B1 | ↑ | frontier/high | — | ✅ terminal — исторический вид |
| P1.4 | B1 | ↑ | frontier/high | — | ✅ terminal — read path; discovery deviation передан отдельно |
| P1.5 | solo | plan-run (manual) | frontier/high | ✅ заморозка контракта ЧИТАТЕЛЕЙ v1 | до freeze: два профиля одного auditor (`scoped-review`/`full-audit`) и `return-to-root`; затем сквозная сверка и оценка выполнимости |
| P2.1 | solo | plan-run (manual) | implementation/high | — | резолвер раскладки — адресация всего последующего; правит и два репозиторных инструмента `plans/` (D74) |
| P2.2 | solo | plan-run (manual) | implementation/high | — | каркас проекций + журнал решений: неизменяемость и свежесть задаются здесь один раз для всех видов |
| P2.3 | solo | plan-run (manual) | implementation/high | — | хирургия по живому парсеру фазы + расщепление 16 полей: ошибка ломает разбор любого плана флота |
| P2.4 | solo | plan-run (manual) | implementation/high | — | ядро `plan.md` и владельческий вид; меняет канон Meta и доски |
| P2.5 | solo | plan-run (manual) | implementation/high | — | слепок — единственное, что осталось исполнителю от состояния мира после ухода handoff с пути |
| P2.6 | solo | plan-exec | implementation/medium | — | вид не коммитится и не стоит на живом пути — цена ошибки локальна |
| P2.7 | solo | plan-run (manual) | implementation/high | — | правило живого пути, которое потом меряет гейт P3 |
| P2.8 | solo | plan-run (manual) | implementation/high | — | self-host текущего реального плана — первая вертикальная field-проверка shared carriers; provider-specific семантика запрещена |
| P3.1 | solo | plan-run (manual) | frontier/high | — | форма манифеста входов — публичный контракт для всех новых планов флота |
| P3.2 | solo | plan-run (manual) | implementation/high | — | детерминизм сборщика несёт гейт свежести; недетерминированный делает проверку вечно красной |
| P3.3 | solo | plan-run (manual) | implementation/high | — | ГОЛОВНОЙ гейт плана (D2) против замороженного порога |
| P3.4 | B2 | plan-run серия | implementation/high | — | семья проверок в `plan_gates.py`; scope сцеплен файлом, маршрут и глубина ревью совпадают с P3.5 |
| P3.5 | B2 | ↑ | implementation/high | — | вторая семья проверок в том же файле |
| P3.6 | solo | plan-run (manual) | implementation/high | — | реестр диспозиций: доказательство «ничего не пропало» интроспекцией; отдельный вердикт |
| P3.7 | solo | plan-run (manual) | frontier/high | — | контракт + ранний read-only canary: текущий layout-v2 план и временная dry-run проекция одного реального fleet-плана, без записи наружу |
| P4.1 | solo | plan-run (manual) | frontier/high | — | форма отпечатка — адресное пространство счётчика, потолка и гейта |
| P4.2 | solo | plan-run (manual) | implementation/high | — | редьюсер и durable-счётчик: корректность идентичности несёт весь механизм |
| P4.3 | solo | plan-run (manual) | frontier/high | — | freeze лестницы: первый local-fix → повтор/risk isolated-review → cap owner-gate |
| P4.4 | solo | plan-run (manual) | implementation/high | — | deterministic triage; первый локальный сбой даёт zero audit, occurrence сохраняется |
| P4.5 | solo | plan-run (manual) | frontier/high | — | scoped-review capsule, независимые actor/route, `return-to-root`, монотонность |
| P4.6 | solo | plan-run (manual) | implementation/high | — | e2e четырёх ветвей: 0/1 reviewer call, 0 лишних root restart, fallback fail-closed |
| P5.1 | solo | plan-run (manual) | frontier/high | — | freeze DecisionRequest + provider-neutral continuation identity для resume-root |
| P5.2 | solo | plan-run (manual) | frontier/high | ✅ утверждение ДЕЙСТВУЮЩЕГО инстанса рамки | изменение рамки само является `authority_change` (D65) |
| P5.3 | solo | plan-run (manual) | implementation/high | — | резолвер политики: одна ветка «разрешить по умолчанию» обесценивает всю фазу |
| P5.4 | solo | plan-run (manual) | implementation/high | — | очередь + адресная пауза + durable resume того же logical root run; explicit cold-start fallback |
| P5.5 | solo | plan-run (manual) | implementation/high | — | замыкающий адаптер + двусоставная приёмка на живых прогонах |
| P6.1 | solo | plan-run (manual) | implementation/high | — | команды различают auditor profile и context mode; fresh review не равен root handoff |
| P6.2 | solo | plan-run (manual) | implementation/high | — | root/specialist session provenance, triage production и session-context resolver |
| P6.3 | solo | plan-run (manual) | frontier/high | — | isolated child judgement по capsule; stronger route отдельно, затем resume root |
| P6.4 | solo | plan-run (manual) | implementation/high | — | включение защиты: ЧЕТЫРЕ коммита (по проверке), would-fail до включения, негативный e2e |
| P6.5 | solo | plan-run (manual) | frontier/high | — | канон enum `continue-root|isolated-child-return|cold-start-root` + hard-boundary reasons |
| P6.6 | solo | plan-run (manual) | implementation/high | ✅ запись в ЧУЖИЕ репозитории (раскатка) | единственный item, действующий за пределами репозитория; `--dry-run` до гейта |
| P6.7 | solo | plan-run (manual) | frontier/high | — | предобъявить machine `session_canary`: exact four branches/expected + command/result keys (D126) |
| P6.8 | solo | plan-run (manual) | frontier/high | — | две D2-руки + отдельный exact session-canary comparator; local field defect без automatic audit |
| P6.9 | solo | plan-exec | implementation/medium | — | бухгалтерия снятия паузы в чужом плане; предусловие — ВЕРДИКТ P6.8 |

## Готовые launch-block'и групп

### B1 — четыре контракта читателей одной сессией (P1.1–P1.4, завершён)

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high — открытые design-решения о числе читателей, классах носителей и слотах пути |
| Capabilities | — |
| Context | same-session — item |
| Суть | Заморозить `reader-contract` v1, `item-state-projection` v1, `history-projection` v1 и `read-path` v1 одной сессией: реестр — адресное пространство трёх остальных, поэтому разрыв сессии между ними стоит перечитывания того же контекста. Владельческий гейт стоит ПОСЛЕ батча (P1.5), внутрь не попадает |

```
run-items: task:plan-run 2026.08.07-PLAN-ECONOMY P1.1-P1.4
```

### B2 — две семьи проверок в одном файле (P3.4–P3.5)

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high — предикаты по объявлению поверх замороженных форм; тихое ослабление проверки выглядит как успех |
| Capabilities | — |
| Context | same-session — item |
| Суть | Обе семьи живут в `packages/task/lib/task/plan_gates.py` и обе доказываются одним и тем же приёмом (кейс на код таксономии + BACKCOMPAT-diff по планам v1); один и тот же маршрут и одна глубина ревью |

```
run-items: task:plan-run 2026.08.07-PLAN-ECONOMY P3.4-P3.5
```

### Одиночные items — общая форма запуска

`Exec = manual` (42 items): `task:plan-exec` их НЕ исполняет — он обязан отвергнуть undershoot.
Носитель — `task:plan-run <ID> Pn.m` под маршрутом, ПРЕДПИСАННЫМ §3 Routing, либо голый промпт
item'а; исполнитель обязан напечатать фактическую пару класс/effort в отчёте и в Update Log.

```
run-items: task:plan-run 2026.08.07-PLAN-ECONOMY <Pn.m>
```

Три item'а (`P0.2`, `P2.6`, `P6.9`) — `plan-exec`:

```
exec-items: task:plan-exec 2026.08.07-PLAN-ECONOMY <Pn.m>
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P0.5 | численный ПОРОГ бюджета чтения и его единицу | всю P1 (оценка выполнимости P1.5), гейты P3.3, приёмку P6.7/P6.8 |
| P1.5 | заморозку контракта ЧИТАТЕЛЕЙ v1 (четыре контракта одновременно) | всю P2 и P3 |
| P5.2 | ДЕЙСТВУЮЩИЙ инстанс рамки полномочий `packages/task/configs/authority-frame.json` | P5.3, P5.4, P5.5, раскатку P6.6 |
| P6.6 | запись в ЧУЖИЕ репозитории при раскатке (после `--dry-run`) | ничего внутри плана; за ним — только приёмка |

## Порядок и предусловия, которые карта не переопределяет

- Фаза-first: фаза N+1 не исполняется, пока фаза N не терминальна (`## 2. Execution Rules`).
- P6.4 исполняется ТОЛЬКО после P6.2 и P6.3 (включение гейта требует существующих производителей).
- P6.9 исполняется ТОЛЬКО при положительном вердикте P6.8; иначе остаётся 🔴 с `Возобновление:`.
- P6.5 внутри себя несёт жёсткий порядок двух коммитов: EN-only и перепривязка гейтов → канон v2.
- Оркестрация (workflow-скрипт) НЕ заявлена ни одной фазой: items последовательно зависимы по
  данным, `plans/2026.08.07-PLAN-ECONOMY/workflows/` не заводится.
- **Поверхность связности (D98, `supersedes D87` в части владельцев `plan.md`; числа пересчитаны D106) — ЧЕТЫРНАДЦАТЬ ПОЗИЦИЙ, по одной на файл, которые правят ≥2 фазы.**
  У каждого ровно один ЗАВОДЯЩИЙ item, остальные расширяют его по объявленной границе своей фазы;
  порядок карты этот инвариант соблюдает, но исполнитель поздней фазы обязан свериться с D98 ПЕРЕД
  правкой любого из них. Перечень (заводящий item в скобках):
  - модули: `plan_lint.py` (P2.1) · `plan_gates.py` (P3.3) · `plan-views.py` (P2.2) ·
    `plan_returns.py` (P4.2) · `plan_weight.py` (P0.3 — с P6.5 его правят ТРИ фазы, D93)
  - данные и конфиги: `lint-check-dispositions.json` (P3.6) · `tests/data/plan-v2/` (P2.3) ·
    `root/contracts/reader-contract-v1.registry.json` (P1.1; расширение — только отдельной D-записью)
  - тесты: `tests/test_plan_lint.py` (P2.3 — правят ЧЕТЫРЕ фазы) · `tests/test_plan_gates.py` (P3.3) ·
    `tests/test_lint_dispositions.py` (P3.6) · `tests/test_return_judgement.py` (P4.6)
  - документы: `packages/task/docs/reference/plan-layout-v2.md` (P2.1) ·
    **собственный `plan.md` этого плана — его правят ВСЕ СЕМЬ фаз, а не три (D98), ДВЕНАДЦАТЬЮ items (D106):**
    P0.5, P1.5, P2.8, **P3.1, P3.7, P4.1, P4.3, P4.5, P5.1, P5.2**, P6.2, P6.7 — все одной, полной формой пути.
    Девять выделенных items дописывают строку в `## 7. Contracts` и до D98 этого в `Files` не объявляли —
    то есть процедура пересчёта D87 читала поле, которого они не заполнили. **D106 снял с этого перечня P2.4 и
    P6.8:** у первого `plan.md` в `Files` был генерик-аргументом переводимого инструмента (правится
    `plan_lint.py`, а не этот план), у второго — файлом ЧУЖОГО плана `PLAN-MIGRATION`, создаваемого рукой B
    приёмки; обе позиции читались как собственный `plan.md` только через домысливание префикса.
    После P2.8 `plan.md` физически
    меняет состав по D32 (`## 4`/`## 6` исчезают, `## 7. Contracts` остаётся), поэтому правка
    «по привычке v1» промахнётся мимо носителя.
  - `CHANGELOG.md` исключён ЯВНО: его правят 30 items пяти фаз, но он append-only по канону
    `root.development-validation` — конфликт решается слиянием, а не порядком фаз.
- **Внутрифазовая связность — отдельный класс, в поверхность выше НЕ входит** (критерий «≥2 фазы» не
  срабатывает), но исполнителя связывает так же: `task_contract.py` и `test_task_contract.py` правят
  ТРИ item'а фазы P2 — P2.1 заводит адресацию, P2.3 даёт источник одиннадцати полей ТЗ, P2.4 — источник
  Meta и пяти полей исхода, P2.8 доказывает результат приёмочным кейсом (шов объявлен D84).
  Перечень пересобирается СЧЁТОМ по полям `Files` всех items `phases/P*.md`, а не чтением: предъявлять
  список как машинное доказательство, собрав его глазами, — ровно дефект, который D87 и чинит. **D98
  добавляет второе условие процедуры: перед счётом убедиться, что поле `Files` каждого item'а объявляет
  всё, что item реально правит** — иначе полнота доказывается по неполному входу (класс, который дважды
  прошёл мимо: F3 захода 1 и N3 захода 2). Практический признак: любой item, чьи `Deliverables` называют
  строку в `## 7. Contracts`, ОБЯЗАН нести `plan.md` в `Files`.
  **D106 добавляет ТРЕТЬЕ условие: перед счётом убедиться, что ни один токен `Files` не является
  продолжением префикса** — каждый путь полон от корня репозитория либо от явно объявленного `<plan-dir>`
  (для items, описывающих инструмент над ЛЮБЫМ планом); корневые файлы репозитория (`CHANGELOG.md`,
  `.gitignore`) сокращением не считаются. Без этого условия счёт либо роняет голое имя, либо приписывает
  его чужому каталогу, и «машинное доказательство» снова доказывается по входу, собранному глазами.
  Проверка условия — механическая: ни один backtick-токен поля не должен быть путём без `/`, кроме
  названных корневых файлов.
- **Правки в раскладке v2 адресуются по-новому (D90, D97).** После P2.8 D-записи живут в `decisions/`,
  доска и Update Log — в `status.md`, фазовый файл — `phases/<Pn>/<Pn>.md`; бухгалтерией закрытия
  становятся ещё `status.md` и `decisions/` (переведено в `harness/run/gate.py` тем же P2.1).
- Расширение замороженного реестра носителей в P5.4 законно ТОЛЬКО отдельной D-записью (D64):
  молчаливое расширение реестра — не правка, а расфриз контракта.
