# Свип исполнимости команд `Validation` на живом дереве

**Дата:** 2026-07-31 · **Дерево:** `HEAD = ebd42655` · Слой 2 (авторский синтез свипа).
Прогон дизайна 3/3, шаг «выборочная проверка исполнимости».

Проверялось не «правильна ли приёмка по смыслу» (это предмет DoR прогона 2), а **физическая
исполнимость**: существуют ли пути, есть ли у команд названные флаги, не протухли ли номера
строк в `Required Reads`. Приоритет — семь items с `Exec = plan-exec` (их поведёт дешёвая
модель или драйвер P4, у которых нет права импровизировать): **P1.2 · P2.4 · P2.6 · P5.2 ·
P5.3 · P5.6 · P7.2**; дополнительно затронуты P1.3 и P6.1 (их команды пересекаются с теми же
поверхностями).

## 1. Итог

| Класс | Число |
|:--|:--|
| Проверено команд/якорей | 41 |
| Исполнимо как записано | 38 |
| **Дефектов (правится этим свипом)** | **3** |

Дефекты — F5, F6, F7 ниже. Все три — в командах, которые дешёвая модель выполнила бы
буквально и получила бы ошибку без подсказки, что делать.

## 2. Дефекты

### F5 — `packages/task/scripts/test.sh` не существует (P6.1 `Validation` §5)

```
$ ls packages/task/scripts/
plan-lint.py  render-provider-commands.py  validate.sh
```

У пакета `task` **нет** `test.sh` — в отличие от `analyst`/`harness`/`maind`/`skiller`.
Тесты пакета гоняет `packages/task/scripts/validate.sh:72`
(`python3 -m unittest discover -s tests -p "test_*.py"`). CI `.github/workflows/test.yml`
пакет `task` не гоняет вовсе.

**Правка:** в `Validation` P6.1 §5 `bash packages/task/scripts/test.sh` →
`bash packages/task/scripts/validate.sh`. Смысл шага сохраняется: `task` — один из четырёх
пакетов с правлеными импорт-сайтами, его тесты обязаны быть зелёными.

> **Дополнено 2026-07-31 (D71, находка аудита F4).** Носителей несуществующего раннера было
> **три**, а этот свип починил один: `phases/P5.md` §P5.8 Validation §2 и §P5.9 Validation §5
> остались с `test.sh` (у P5.9 — без оговорки «или штатный раннер пакета»). Переиздание
> правила свипа: исполнимость команды проверяется грепом носителя по ВСЕМУ корню плана, а не
> в том item'е, где дефект замечен.

### F6 — флаг `maind sync --dry` не существует (P2.4 `Validation` §3)

Фактический флаг — `--dry-run`:

```
packages/maind/lib/maind/provision/sync.py:919   "--only": "str", "--mode": "str", "--dry-run": "bool",
packages/maind/lib/maind/provision/deploy.py:400 "--dry-run": "bool", "--json": "bool",
```

**Правка:** `maind sync --dry` → `maind sync --dry-run` (и `deploy --dry` → `deploy --dry-run`).
Тот же флаг фигурирует в mitigation A4 pre-mortem'а (D64), поэтому имя обязано быть точным в
обоих местах.

### F7 — размер `scripts/provider-docs.py` в `Required Reads` P5.2 протух

Записано «целиком (218 строк: `GUIDE_PATH` `:23`, … `main` `:320`)» — при 218 строках
якорь `:320` невозможен. Фактически:

```
$ wc -l scripts/provider-docs.py
330 scripts/provider-docs.py
```

Сами шесть якорей строк **верны** (проверено построчно: `:23` `GUIDE_PATH`, `:160`
`render_readme_block`, `:175` `render_guide`, `:276` `expected_outputs`, `:300` `run`,
`:320` `main`). Протухло только число строк.

**Правка:** `218 строк` → `330 строк`.

## 3. Проверено и исполнимо (выборка)

### 3.1 Существование путей

| Путь | Итог |
|:--|:--|
| `packages/{skiller,harness,maind}/scripts/{test,validate}.sh` | ✅ все шесть |
| `packages/task/scripts/{validate.sh,plan-lint.py}` | ✅ |
| `packages/skiller/tests/test_budget_first_turn.py` · `docs/guide/cli.md` | ✅ |
| `packages/maind/lib/maind/provision/deploy.py` · `tests/test_mcpconfig.py` | ✅ |
| `packages/harness/configs/claude-code/mcp/{playwright,bindings}.json` · `configs/codex/mcp/bindings.json` · `tests/test_mcp.py` | ✅ (P5.6) |
| `roadmap/{playwright-mcp-output-dir,mcp-config-example-emit,analyst-plan-scan,analyst-fleet-coverage}.md` | ✅ (P5.6/P2.4/P7.2) |
| `packages/analyst/docs/roadmap.md` | ✅ (P7.2 — цель переезда существует) |
| `plans/verify-citations.py` · `plans/verify-citations-known-exceptions.json` | ✅ |
| `packages/skiller/scripts/{update-upstreams.sh,check-translations.sh,desc-trigger-burndown.txt}` | ✅ |
| `packages/harness/lib/harness/hooks.py` (1191 строка — якорь `:830–905` внутри) | ✅ |

### 3.2 Числа, на которые опираются приёмки

| Утверждение плана | Замер | Итог |
|:--|:--|:--|
| P1.2: 26 `enabled`-записей `config.json` | `total 26 enabled 26` | ✅ |
| P5.1: 56 вендоренных бандлов | `find … -name upstream.json \| wc -l` → `56` | ✅ |
| P6.1: baseline 251 тест | `Ran 251 tests` | ✅ |
| P6.1: `len(core.__all__) == 110` | **пере-замерено 2026-07-31 аудитом: `108`** (`PYTHONPATH=. python3 -c "import core; print(len(core.__all__))"` на `ebd42655`) | ❌ → исправлено, инвариант = **108** (D68). Пропуск этого замера свипом и был находкой F1 |
| P5.3: `.gitignore:14,16` — `auto-approve.env.ini`/`memory.env.ini` | совпало дословно | ✅ |
| P1.3: `budget.py:193–194` — константы порога | `FIRST_TURN_TARGET_MAX = 7_000` / `FIRST_TURN_WARN = 10_000` | ✅ |

### 3.3 Флаги CLI

| Команда `Validation` | Итог |
|:--|:--|
| `harness hooks … --dry-run` (P5.3 §6) | ✅ (`packages/harness/bin/harness:11`) |
| `plan-lint.py … --baseline HEAD` (все items) | ✅ (`--baseline [REF]` в `--help`) |
| `plan-lint.py --conflicts` (P5.9 §1) | ⬜ ожидаемо отсутствует — этот флаг item и ВВОДИТ |
| `skiller budget --first-turn --target … --json` (P1.3 §5) | ✅ (ветка `opts.get("first_turn")`, `budget.py:678`) |
| `provider-docs.py --check` (P5.2 §1) | ✅ и **зелёный** на `HEAD` (exit 0) |
| `npx @playwright/mcp@<версия> --help` (P5.6 §2) | ⬜ внешний — по построению проверяется В item'е, не здесь |

## 4. Побочная находка свипа (не дефект `Validation`)

`P5.2` кладёт свой новый структурный тест в раннер `scripts/test-provider-docs.py`, а тот на
`HEAD` **красный** (2 провала, `findings/P6-manifest-drift-2026-07-31.md` §4). Приёмка P5.2
§5 «новый тест зелёный в штатном раннере» как записано недостижима до P6.3. Правка —
дельтовая формулировка приёмки; носитель — **D63**.
