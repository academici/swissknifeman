# P5 — факты под закрытие находок аудита (F1/F2)

**Слой 1** (внешнее/repo-grounded сырьё, собрано `plan-design` 2026-07-27 при реопене фазы P5 по
блоку `phases/P5.md` → `## Audit P5 — 2026-07-27`). Потребители — ТЗ **P5.5** и **P5.6**.
Синтез и решения — `plan.md` §5 D115/D116/D117.

---

## §1. F1 — где пин Serena живёт СЕЙЧАС, и где его нет

Проверено `grep` по дереву на `6e04c10d` + рабочее дерево (2026-07-27).

| Носитель | Слой | Состояние | Адрес |
|:--|:--|:--|:--|
| `constants.SERENA_SRC` | tracked, код | **пиннован** `@026b007bb889366283c925527e9a3bab317f66c1` | `packages/maind/lib/maind/constants.py:62` |
| `config.json` `code_graph.args` | **gitignored** | пиннован (правка P5.3, в `git log` не существует) | корень монорепо |
| `config.json` `code_graph.index_args` | **gitignored** | пиннован (там же) | корень монорепо |
| `config.example.json` `code_graph.args` | **tracked** | ❌ `"--from", "git+https://github.com/oraios/serena"` — БЕЗ `@REF` | `config.example.json:34` |
| `config.example.json` `code_graph.index_args` | **tracked** | ❌ без `@REF` | `config.example.json:35` |
| `.mcp.json.example` `serena.args` | **tracked** | ❌ без `@REF` | `.mcp.json.example:21` |
| `packages/maind/docs/guide/code-graph.md` (пример `.mcp.json`) | **tracked, дока** | ❌ без `@REF` | `code-graph.md:42` |

`.gitignore:25` — «Приватный конфиг узла maind; шаблон — config.example.json» ⇒ единственный
ВЕРСИОНИРУЕМЫЙ носитель политики `code_graph` — `config.example.json`.

**Путь регрессии (repo-grounded, `packages/maind/install.sh:100-101`):**

```bash
if [[ ! -f "$CFG_ROOT/config.json" && -f "$CFG_ROOT/config.example.json" ]]; then
  cp "$CFG_ROOT/config.example.json" "$CFG_ROOT/config.json"
```

Свежая установка / вторая машина / другой оператор ⇒ `config.json` = непиннованный шаблон ⇒
политика перебивает пиннованный `CODE_GRAPH_DEFAULTS` (`codegraph.settings()` кладёт `args`
конфига поверх дефолта) ⇒ флот снова резолвит плавающий HEAD Serena. Это дословно дефект **D65**,
воспроизведённый собственным установщиком.

## §2. F1-гейт — почему тестового гейта P5.4 недостаточно

`grep -rn "check_schema_connectivity" --include="*.py"` по `packages/`/`core/`/`bin/`
(2026-07-27) — **0 продуктовых вызовов**; единственные вызовы — 4 теста
`packages/maind/tests/test_codegraph.py::TestSchemaConnectivity` (строки 188/197/207/219).
Зелёный тест `test_consistent_state_is_green` строит конфиг фикстурой `_setup(...)`, то есть из
`CODE_GRAPH_DEFAULTS`, где пины совпадают **по построению** ⇒ ни `config.example.json`, ни живой
`config.json` гейтом не видятся никогда.

`maind doctor` (`packages/maind/lib/maind/doctor.py:180-300`) — готовая точка врезки: у него есть
локальный хелпер `check(ok, label, hint="")` (инкремент `issues`, печать `[ok ]`/`[FAIL]`,
`sys.exit(1)` при `issues > 0`) и блок `if config:` после успешного `load_config`, где уже
вызываются `_skill_drift_report`/`_channel_hygiene_report`. Конфига нет ⇒ ветка
`check(True, "config.json отсутствует …")` — врезка туда не попадает по построению.

## §3. F2 — что пиннованная Serena требует НА САМОМ ДЕЛЕ

Прямое чтение исходника **пиннованной** версии из локального uv-архива (офлайн, без сети),
2026-07-27:

```
~/.cache/uv/archive-v0/qZbCs51WSg6q7OGey7q1P/          # dist-info: serena_agent-1.6.2.dev0
  serena/config/serena_config.py:341
      FIELDS_WITHOUT_DEFAULTS = {"project_name", "language_servers"}
  serena/config/serena_config.py:564
      data.setdefault(key, default_value)              # все ОСТАЛЬНЫЕ ключи
```

Сверено по всем 20+ архивам Serena в кэше: `{"project_name", "languages"}` — во всех сборках
ДО переименования; `{"project_name", "language_servers"}` — ровно в двух архивах, и это
`serena_agent-1.6.2.dev0`, т.е. пин `026b007b…`. Совпадает с D109 (`RENAMED_FIELDS:
languages → language_servers`) и с §10 `findings/P5.3-serena-pin-and-provider-gate.md`.

**Итог: обязательных ключей ДВА, а не двенадцать.** Остальные одиннадцать
(`symbol_info_budget`, `ignored_paths`, `fixed_tools`, `excluded_tools`,
`included_optional_tools`, `read_only`, `ignore_all_files_in_gitignore`, `initial_prompt`,
`encoding`, `added_modes`, `default_modes`) имеют дефолты и добираются `data.setdefault(...)` в
том же `_from_dict` — их отсутствие в файле **не** даёт `KeyError`.

**Два расходящихся носителя этого факта в нашем дереве:**

1. `packages/maind/lib/maind/constants.py:63-72` — `SERENA_SCHEMA_FIELDS` (12 ключей) с
   комментарием «Обязательные ключи `.serena/project.yml` (Serena `_from_dict`
   `FIELDS_WITHOUT_DEFAULTS`)» — **ложная ссылка**: подписывает наш набор чужим фактом.
2. `packages/maind/lib/maind/codegraph.py:91-98` — докстринг `render_project_yaml`: «Serena
   `_from_dict` читает РЯД ключей без `.get()` (`FIELDS_WITHOUT_DEFAULTS` + обязательные): …
   отсутствие ЛЮБОГО → `KeyError` при загрузке» — **неверно** для одиннадцати из двенадцати.
   Написан ДО P5.4 (эпоха `ccd4505b`), но ТЗ P5.4 назвало его «ожидаемой схемой»
   (`Required Reads` п.2) — отсюда и разошлась константа.

**Что при сужении набора гейт НЕ теряет:** историческое расхождение D109 (`SERENA_SRC@v1.5.3`
требует `languages`, рендерер печатает `language_servers`) он ловит через `language_servers`,
остающийся в наборе — ядро гейта рабочее (подтверждено аудитом и тестом
`test_schema_mismatch_detected`, который мокает константу и от её состава не зависит).

**Что мы теряем сознательно:** проверку «наш шаблон печатает все 12 ключей». Она никогда не была
проверкой требований апстрима — это контракт формы нашего собственного рендерера, и именно он
красил бы весь `packages/maind` ложным «пиннованная Serena требует этот ключ» при любой законной
правке рендерера (перестать печатать `encoding`, сделать `initial_prompt` условным).

## §4. Числа линтера по items P5 (под F5)

Замерено этой сессией `python3 packages/task/scripts/plan-lint.py` на git-worktree каждого якоря:

| Якорь | Что это | ERROR / WARN |
|:--|:--|:--|
| `ef056839` | дерево ДО первого коммита работ P5.3 (baseline) | 0 / 22 |
| `518df4ef` | bookkeeping-коммит закрытия **P5.3** | 0 / 23 |
| `bbe3be21` | bookkeeping-коммит закрытия **P5.4** | 0 / 23 |
| `36607f2a` | bookkeeping-коммит закрытия **P5.1** | 0 / 24 |
| `a476527f` | bookkeeping-коммит закрытия **P5.2** | 0 / 24 |
| `6e04c10d` | коммит закрытия фазы | 0 / 24 |

Хронология коммитов фазы (`git log --date=short`): P5.3 (`930ad0ac`→`518df4ef`) → P5.4
(`253ae4a6`→`bbe3be21`) → P5.1 (`a8639c82`→`629cf09d`→`36607f2a`) → P5.2
(`8149829f`→`1844ab29`→`a476527f`) → `6e04c10d`. Отсюда атрибуция «новых от диффа item'а»:
**P5.3 → K=+1 WARN** (22→23), **P5.4 → K=0** (23→23), **P5.1 → K=+1 WARN** (23→24),
**P5.2 → K=0** (24→24). ERROR — 0 везде.

## §5. Карта коммитов фазы (под F3)

| item | коммит работ | bookkeeping-коммит закрытия |
|:--|:--|:--|
| P5.1 | `629cf09d` (эталон ДО замера — `a8639c82`) | `36607f2a` |
| P5.2 | `1844ab29` (протокол k-fold ДО прогона — `8149829f`) | `a476527f` |
| P5.3 | `930ad0ac` | `518df4ef` |
| P5.4 | `253ae4a6` | `bbe3be21` |
| фаза | — | `6e04c10d` |

Действующее значение пина во всех носителях, где он есть, —
`@026b007bb889366283c925527e9a3bab317f66c1` (`Serena 1.6.2.dev0`). Строка `v1.5.3` в
`## Phase Handoff` и `handoff.md` — **отменённое** D107/D110 значение и один из двух тегов,
объявленных D109 ломающими флот.

## §6. Что этим заходом НЕ проверялось

- Дельта `v1.6.1` → `1.6.2.dev0` на breaking changes — по-прежнему `[UNVERIFIED]` (D110
  Consequences); настоящий заход её не читал и не обязан.
- Наличие свежего стабильного тега апстрима сверх проверенного аудитом `v1.6.1` — не
  перепроверялось: значение пина закрыто D110 и переоткрытию этим реопеном не подлежит.
- Поведение `uvx` при резолве пина на машине БЕЗ прогретого кэша — офлайновый факт §3 снят с
  локального архива, сетевой сверки не делалось (гейт по построению офлайновый).
