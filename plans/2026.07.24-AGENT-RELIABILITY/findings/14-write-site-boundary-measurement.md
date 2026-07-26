# findings/14 — измерение write-site P2.7 на границах pre-mutation/pre-final

**Дата:** 2026-07-26 · **Слой:** 1 (первичное измерение/репро, не синтез) ·
**Заход:** `task:plan-design 2026.07.24-AGENT-RELIABILITY P2.7` (Claude Opus 5/high) ·
**Дерево-якорь:** `c215bd04` (рабочее дерево чисто по `packages/**` на момент прогонов) ·
**Питает:** `research/08-pre-final-boundary-semantics.md`, D75–D79, items P2.10/P2.11.

Все числа ниже воспроизводимы приведёнными командами на указанном дереве. Ни одно
утверждение здесь не взято из прозы аудита или из Completion Notes P2.7 без перепрогона.

---

## М1 — репро находки review: `("allow", "n/a")` зеленит упавший `pre_mutation`

Команда (форма — дословно из `packages/task/commands/plan-close.md` шаг 4, литерал пина
команды `implementation`/`low`):

```
PYTHONPATH=packages/task/lib python3 - <<'PY'
from task import task_contract, route_evidence
for item in ("P2.1","P2.2","P2.6","P2.7"):
    c = task_contract.build("plans/2026.07.24-AGENT-RELIABILITY", item,
        actual_route=route_evidence.capture_actual("implementation","low",
            source="self-attested", model="sonnet"))
    print(item, task_contract.evaluate(c))
PY
```

| item | `route.required` (§3) | `pre_mutation` | `pre_final` | шаг 4 сегодня |
|:--|:--|:--|:--|:--|
| P2.1 | frontier/high | `block:ROUTE_UNDERSHOOT` | `n/a` | **exit 0 (зелено)** |
| P2.2 | implementation/high | `block:ROUTE_UNDERSHOOT` | `n/a` | **exit 0 (зелено)** |
| P2.6 | implementation/high | `block:ROUTE_UNDERSHOOT` | `n/a` | **exit 0 (зелено)** |
| P2.7 | implementation/high | `block:ROUTE_UNDERSHOOT` | `n/a` | **exit 0 (зелено)** |

Находка review подтверждена дословно: собственный пин `plan-close` (`implementation/low`)
ниже требуемого маршрута ЛЮБОГО item'а плана, поэтому `pre_mutation` падает всегда, а
`("allow","n/a")` объявляет этот отказ зелёным. Предикат нефальсифицируем на 26/26 items.

Причина категориальная, а не пороговая: `task_contract.build` берёт `route.required` из
строки §3 Routing **item'а** (`task_contract.py:317-320`) — это маршрут ИСПОЛНИТЕЛЯ item'а.
Подстановка маршрута РЕКОНСИЛИРУЮЩЕЙ команды сравнивает две разные величины.

## М2 — тот же прогон с маршрутом, под которым item реально исполнялся

Та же команда, `actual_route` = строка §3 Routing самого item'а (то, что должен был бы
подставить честный шаг 4):

| item | `pre_mutation` | `pre_final` |
|:--|:--|:--|
| P2.1 · P2.2 · P2.6 · P2.7 | `allow` | `allow` |

Расширенный прогон по ВСЕМ 26 items плана (P0.1–P4.3, `actual` = `required` каждой строки):
**26/26 `allow`/`allow`**, ни одного исключения. Вывод: ось маршрута с правильным `actual`
не ломает поток закрытия — она перестаёт быть тавтологией и начинает что-то утверждать.

## М3 — `pre_final` фальсифицируем (проверка «а не резиновый ли он»)

Тот же прогон по соседнему живому плану того же корня:

```
plans/2026.07.25-ECO-OPT: rows=29 {('allow','allow'): 26,
                                   ('allow','block:ACCEPTANCE_NOT_PUBLIC'): 3}
                          sample: P1.2, P7.3, P9.1
```

`pre_final` краснеет на 3 из 29 items — предикат живой. Но он утверждает **свойство СПЕКИ**
(«у item'а есть хотя бы один публично проверяемый acceptance-пункт на детерминированном
классе доказательства»), а НЕ факт исполнения: он зелен на ⬜-items, которые не стартовали
(P3.1–P4.3 этого плана). Это не дефект — это ровно то, что объявляет
`root/contracts/task-contract-v1.md:156-165`; но текст шага 4 сегодня этой границы не
называет, и читатель вправе прочесть «pre_final: allow» как «item сдан хорошо».

## М4 — **новое (не было в находке review): write-site падает необработанным `ValueError`
на легаси-форме §3 Routing**

```
PYTHONPATH=packages/task/lib python3 -c "
from task import task_contract, route_evidence
c=task_contract.build('plans/2026.07.18-FOREMAN','P0.1',
   actual_route=route_evidence.capture_actual('frontier','high',source='self-attested',model='opus'))
print('route =', c['route']); print(task_contract.evaluate(c))"
```

Вывод:

```
route = {'required': {'model_class': '', 'effort': ''},
         'actual': {'model_class': 'frontier', 'effort': 'high'}, 'capabilities': []}
Traceback (most recent call last):
  File ".../task_contract.py", line 663, in evaluate
    mutation_code = pre_mutation(contract, work=work)
  File ".../task_contract.py", line 600, in pre_mutation
    < _rank(MODEL_CLASS_ORDER, route["required"]["model_class"])):
  File ".../task_contract.py", line 515, in _rank
    return order.index(value)
ValueError: tuple.index(x): x not in tuple
```

Два независимых дефекта в одной цепочке:

1. **`_find_routing_row` читает ровно один заголовок колонки** —
   `row.get("Model class/effort", "")` (`task_contract.py:189,196`). На легаси-таблице с
   заголовком `Model/effort` `.get()` возвращает `""`, `partition("/")` даёт `("","","")`, и
   `build()` кладёт в контракт `required = {"model_class": "", "effort": ""}` — **пустое
   значение, выданное за данные**. Это прямое нарушение собственного анти-паддинг-правила
   `build()` (докстринг `task_contract.py:225-228`: «an item field that is empty … raises
   `TaskContractBuildError` naming the field and item — never a fabricated placeholder
   dressed up as data»); правило применено к полям item'а и не применено к §3 Routing.
2. **`_rank` роняет `ValueError` вместо типизированного кода** на любом значении вне
   замороженной лестницы — тот же корень, что D74 (`.index(None)`), другой вход
   (`.index("")` / `.index("opus")`). Команда объявляет таблицу код→действие; необработанное
   исключение в этой таблице отсутствует, поэтому исполнитель получает traceback вместо
   названного отказа с ПРОХОДОМ.

### М4.1 — охват дефекта по корню `plans/` этого репозитория

```
for f in plans/*/plan.md plans/archive/*/plan.md; do
  awk '/^## 3\. Routing/,/^## 4\./' "$f" | grep -m1 '^|.*|'; done
```

| Заголовок колонки маршрута в §3 | Планов | Компилятор читает |
|:--|--:|:--|
| `Model class/effort` (канон) | 3 | да |
| `Model/effort` · `Model/Effort` · `Model/effort И/ИЛИ Tool Capability` · `Model/effort · Tool Capability` | 9 | **нет → пустой `required` → `ValueError`** |
| таблицы §3 нет вовсе | 2 | `TaskContractBuildError` (типизированно, корректно) |

**11 из 14 планов корня не проходят write-site**, причём 9 из них — необработанным
исключением. Легаси-формы §3 объявлены ДЕЙСТВУЮЩИМИ каноном `plan-protocol` §9
(«Back-compat: legacy `## 3. Routing` forms … stay VALID»), поэтому это регрессия
компилятора, а не «плохие планы».

Второй, независимый слой того же дефекта: даже прочитанная легаси-ячейка несёт ИМЯ МОДЕЛИ
(`opus/high`, `sonnet/medium` — FOREMAN §3), а не класс замороженной лестницы
`MODEL_CLASS_ORDER = (economy, implementation, frontier)` → тот же `_rank`-крах. Детерминированная
committed-карта имён в классы в репозитории есть:
`packages/task/configs/command-routing.json::mappings.<provider>.class_selectors`
(`claude-code`: haiku/sonnet/opus · `codex`: gpt-5.6-luna/gpt-5.6-terra/gpt-5.6-sol);
объединение по провайдерам взаимно-однозначно (ни одно имя не встречается в двух классах) —
проверено чтением файла.

## М5 — `plan-exec` закрывает item, не пройдя границу pre-final

Чтение `packages/task/commands/plan-exec.md`: исполняемый write-site есть только в шаге 2
(pre-mutation). Шаг 7 («ЗАКРЫТИЕ ОБЯЗАТЕЛЬНО») по-прежнему несёт ПРОЗУ —
«прозовая реализация `task_contract.py::pre_final`» (`plan-exec.md:135-141`), вызова нет
(`grep -n 'pre_final' packages/task/commands/plan-exec.md` → одна строка, прозовая).

`plan-exec` закрывает item сам (топология двух коммитов — его шаг 7); `plan-close Pn.m` —
отдельная реконсиляционная команда, на штатном пути exec'а не вызывается. Следовательно
граница pre-final на штатном пути закрытия **не пересекается ни разу**. Канон §13
(`SKILL.md:1088-1089`) буквально не лжёт («`task:plan-close`'s pre-final checkpoint CALLs
it»), но читатель канона получает картину «обе границы проверяются машинно», которой в
штатном потоке нет. Класс тот же, что F1.

## М6 — литеральный тест не ловит ни один из М1/М4/М5

`packages/task/tests/test_canon_literals.py::TestTaskContractCanonClaimIsBackedByCommands`
(5 тестов, все зелёные на `d11c3b74`) проверяет ТОЛЬКО наличие подстрок:
`task_contract.build`, `task_contract.evaluate`, `result["pre_final"]`, отсутствие
F1-условной формулировки. Предикат выхода (`in ("allow","n/a")`) ни одним ассершеном не
затронут; таблица код→действие — тоже. Тест прошёл через весь дефект М1 зелёным.

Обобщение (кандидат в канон, см. D79): литеральный тест, утверждающий наличие
ИДЕНТИФИКАТОРА, не защищает утверждение о ПОВЕДЕНИИ. Защищает только ассершен на
различающий предикат — тот, который отличает исправное поведение от дефектного.

---

## Сводка: что именно неверно в поставке P2.7

| # | Утверждение канона/команды | Факт | Владелец ремонта |
|:--|:--|:--|:--|
| М1 | «падая закрыто на любом коде, отличном от `allow`» (§13) | `n/a` зеленит | P2.11 |
| М1 | маршрут pre-final = пин `plan-close` | категориальная ошибка: `required` — маршрут исполнителя item'а | P2.11 |
| М3 | шаг 4 не называет, ЧТО утверждает `pre_final` | читатель переоценивает границу | P2.11 |
| М4 | «команды зовут компилятор» | на 11/14 планов корня вызов падает (9 — `ValueError`) | P2.10 |
| М5 | «обе границы машинно проверяются» | pre-final не пересекается на штатном пути | P2.11 |
| М6 | «утверждение защищено литеральным тестом» | тест проверяет подстроки, не поведение | P2.11 |
