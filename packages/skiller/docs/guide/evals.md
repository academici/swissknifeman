# Поведенческие тесты скиллов (evals)

Структурная валидация (`validate.sh`) и двуязычная когерентность
(`check-translations.sh`) проверяют **форму** скилла. Они не отвечают на главный
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
      ]
    }
  ]
}
```

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
и предлагает кандидата ≤150 симв. **Двуязычие соблюдается:** правка идёт в
`SKILL.ru.md` (SSOT) → регенерация EN-канона → `check-translations.sh --stamp`.
EN-канон напрямую не правим.

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
