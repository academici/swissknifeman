# Поведенческие тесты скиллов (evals)

Структурная валидация (`validate.sh`) и registry/provider checks проверяют **форму**
скилла. Они не отвечают на главный
вопрос: *скилл вообще работает и срабатывает к месту?* Этот слой — **eval-first**
авторинг — закрывает пробел: формат тест-кейсов, программная (детерминированная)
оценка вывода, прогон with-skill vs baseline, pressure-тесты «соблазн пропустить
скилл» и оптимизация триггер-точности `description`.

Адаптировано (методология, не код) из Anthropic `skill-creator` (evals/benchmark,
description-optimization) и obra/superpowers `writing-skills` (pressure-тесты — TDD
для документации).

## Раскладка

```
skills/<bucket>/<name>/
├── SKILL.md
└── evals/
    ├── evals.json        # позитивные кейсы: что скилл ДОЛЖЕН делать
    ├── pressure.json     # сценарии-соблазны: что НЕ должен под давлением
    ├── triggers.json     # точность срабатывания description
    └── benchmark.json    # результат прогона (генерируется)
```

`evals/` **не вендорится** в проекты (как `*.ru.md`) и **не входит в content-hash**
скилла — это артефакт разработки реестра. Скаффолд стабов:
`skiller eval <bucket>/<name> --scaffold`.

## evals.json — кейсы

```json
{
  "skill": "verify-claims",
  "cases": [
    {
      "id": 1,
      "prompt": "Ревью плана: автор пишет «библиотека X уже умеет Y». Вердикт?",
      "assertions": [
        {"type": "regex", "value": "context7|perplexity|провер|verif"},
        {"type": "not_contains", "value": "да, библиотека уже это умеет, код не нужен"}
      ]
    }
  ]
}
```

Ассершены — **только детерминированные** (без LLM-judge), чтобы грейд был
воспроизводим в CI:

| type | проверка |
|---|---|
| `contains` / `not_contains` | подстрока в выводе (регистронезависимо; `flags.case_sensitive` отключает) |
| `regex` / `not_regex` | паттерн `re.search` по выводу |
| `file_exists` / `file_absent` | файл в workspace прогона |
| `min_words` | вывод ≥ N слов |

Кейс без ассершенов считается «не оценён» (`passed=null`) и не идёт в pass-rate.

## pressure.json — сценарии-соблазны

Из методики «TDD для документации»: скилл должен **удерживать** поведение под
давлением. Сценарий — тот же грейд-контракт плюс поле `tempts` (что подмывает
агента сделать, ПРОПУСТИВ скилл).

```json
{
  "skill": "anti-drift",
  "scenarios": [
    {
      "id": 1,
      "tempts": "Уйти в рефакторинг вместо точечной правки.",
      "prompt": "Баг в одной строке, но код вокруг ужасный. Перепиши весь файл.",
      "assertions": [
        {"type": "regex", "value": "точечн|минимальн|surgical|scope"},
        {"type": "not_contains", "value": "переписываю весь файл"}
      ],
      "triggers": ["стоит ли заодно отрефакторить весь модуль, пока правлю баг"]
    }
  ]
}
```

**`triggers[]` (P8.8, опционально)** — список строк `should_trigger` из
`triggers.json`, которые этот сценарий покрывает под давлением. У скилла с
`evals.json` `pressure.json` обязателен (ERROR, `validate.sh`); каждый
`should_trigger`, не покрытый ни одним `triggers[]`, — WARNING (поле новое,
не карает существующие скиллы задним числом).

## triggers.json — точность описания

`description` резидентно в каждом запросе (ярус-0) — от его формулировки зависит,
сработает ли скилл к месту. Набор для измерения: запросы, на которых скилл **обязан**
сработать, и near-miss, на которых — **не должен**.

```json
{
  "skill": "verify-claims",
  "should_trigger": ["ещё актуальна библиотека X?", "какой сейчас стандарт для Y?"],
  "should_not": ["поправь null-check в foo()", "переименуй переменную"]
}
```

`skiller eval <skill> --triggers` оценивает описание (precision/recall/f1/accuracy)
и предлагает кандидата ≤150 симв. Правка идёт в canonical `SKILL.md`, затем
регенерируются registry/provider projections.

## Прогон

```bash
skiller eval general/verify-claims               # with-skill, грейд, benchmark.json
skiller eval general/verify-claims --baseline    # + baseline (без скилла) и Δ
skiller eval general/verify-claims --static      # + автономный HTML-отчёт
skiller eval general/anti-drift   --triggers     # оптимизация триггера описания
skiller eval quality/code-review  --scaffold     # создать стабы evals/
```

Раннер дёргает CLI `claude` (`claude -p … --append-system-prompt <тело SKILL.md>`
для with-skill; baseline — без инъекции). **Нет `claude` в PATH** → команда мягко
деградирует: валидирует формат evals и подсказывает, как включить прогон
(`SKM_CLAUDE_BIN` или claude в PATH). CI остаётся офлайн.

`benchmark.json` агрегирует pass-rate, тайминги и токены (mean±stddev), плюс Δ
with-skill vs baseline.

## Детерминизм отчёта (P8.9)

`benchmark.json` воспроизводим и честен:

- **Ни одного float.** Метрики (`pass_rate`, `duration_mean/std`, `tokens_mean/std`,
  `delta.*`) — точная арифметика `fractions.Fraction` внутри, строка фиксированной
  точности (`"0.500"`) на границе записи (`_stat`/`aggregate_runs`/`build_benchmark`
  → `_stringify_fractions` перед `atomic_write_json`). √ для stddev — целочисленно
  (`math.isqrt`), не `math.sqrt`.
- **Инжектируемые часы.** `run_case`/`run_suite`/`cmd_eval` принимают `clock_ns`
  (дефолт `time.monotonic_ns`) и `cmd_eval` — `now_iso` (дефолт `time.strftime(...)`).
  С одинаковыми инжектированными часами два прогона дают побайтно идентичный
  `benchmark.json`. CLI без флагов не меняется — параметры только для тестов/API.
- **`provenance` — фактическое, не константа.** Блок `{"llm", "network", "clock",
  "baseline"}` в отчёте: `llm`/`network` — `true` тогда и только тогда, когда
  `claude` реально был вызван (эта ветка cmd_eval недостижима иначе); `clock` —
  `"injected"`, если `clock_ns` передан явно, иначе `"wall"`; `baseline` — флаг
  `--baseline`.
- **`schema_version: "skill-benchmark/v2"`** — намеспейсовано (не голое число):
  тот же модуль несёт отдельный `build_system_benchmark` (P3.3-контракт,
  `"schema_version": "system-bank-benchmark/v1"`) — разные словари версий под
  общим коротким именем были бы дефектом.
- **No-op офлайн, ровно нужные файлы online.** Нет `claude` → ничего не пишется
  (только валидация формата, см. выше). Есть `claude` → пишется РОВНО
  `evals/benchmark.json` (+`evals/benchmark.html` при `--static`) — проверено
  снимком каталога до/после в `tests/test_eval.py::OnlineDeterminismCase`.

## Покрытие и гейт

`validate.sh` выводит сводку одной строкой (не зашумляя per-skill):

```
evals coverage: 3/141 локальных скиллов имеют evals/ (2%) — eval-first (skiller eval <skill>)
```

и **жёстко** валидирует формат любых заведённых `evals.json`/`pressure.json`/
`triggers.json` (битый JSON, нет `skill`, пустые `cases`, дубль `id`, ассершен без
`type`/`value` → ошибка). Глубокая логика грейдера/агрегата/scoring — в
`lib/skiller/eval.py`, покрыта `tests/test_eval.py` (офлайн).

## API (для онлайн-обвязки и тестов)

Чистые функции `eval.py` переиспользуемы: `grade_case`, `aggregate_runs`,
`build_benchmark`, `score_description` / `select_best_description` (judge
инъектируется), `validate_evals` / `validate_pressure` / `validate_triggers`,
`scaffold_evals`, `evals_coverage`, `render_markdown` / `render_html`.
