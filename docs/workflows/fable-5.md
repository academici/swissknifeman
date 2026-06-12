# Claude Fable 5 — промтинг

> **Референс:** [Официальный гайд Anthropic по промптингу Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5).

## Что такое Fable 5

Fable 5 — модель из семейства **Mythos** (Anthropic). Не путать с Sonnet/Opus/Haiku.
Оптимизирована под **long-horizon autonomous tasks**: способна работать без
прерывания на сложных многошаговых задачах, самостоятельно делегировать
подзадачи и верифицировать собственные выводы.

## Структура промпта (XML-теги)

```xml
<role>
Описание роли эксперта. Одно предложение. Чётко и без воды.
</role>

<context>
Контекст задачи: что за проект, технологии, ограничения.
Чем конкретнее — тем лучше.
</context>

<task>
Суть задачи. Можно разбить на оси/секции через вложенные теги:

<axis id="1" name="Название оси">
Что именно проверить/сделать по этой оси.
</axis>

<axis id="2" name="Другая ось">
...
</axis>
</task>

<output>
Формат и структура ожидаемого результата.
Заголовки, примеры кода, финальный summary — опишите явно.
</output>

<constraints>
Что модель НЕ должна делать.
Например: не изменять файлы, только отчёт, не придумывать проблемы без доказательств.
</constraints>
```

## Параметр `effort`

Выставляется **через UI** (селектор в интерфейсе), **не тегом в промпте**.

| Уровень | Когда использовать |
|---|---|
| `low` | Короткие вопросы, quick lookup |
| `medium` | Стандартные задачи |
| `high` | Аудит кода, архитектурный анализ, сложный рефакторинг |
| `xhigh` | Только для исключительно объёмных autonomous workflows |

Для анализа кода и технических аудитов — **`high` достаточно**.

## Режим Thinking (чекбокс в UI)

- Включать **не обязательно** для аудита кода.
- Fable 5 при `effort=high` уже работает в режиме глубокого reasoning.
- Чекбокс Thinking в некоторых клиентах управляет **отображением** внутренних
  рассуждений — не самим качеством ответа.
- **Не просить** модель «покажи свои рассуждения» / «show chain-of-thought» —
  это попадает под ограничения reasoning-extraction.

Вместо этого просить:

```
Before reporting each finding, verify it against actual code.
If you are not certain — state that explicitly.
```

## Ключевые отличия от обычного промптинга

| Обычные модели | Fable 5 (Mythos) |
|---|---|
| Нужны подсказки «думай пошагово» | Автономно планирует шаги сама |
| Один длинный монолитный промпт | XML-секции с чёткими ролями |
| Просить «show your thinking» | Нельзя — запрещено reasoning-extraction |
| `temperature`, `top_p` в промпте | Только через API-параметры |
| Effort не актуален | `effort` — ключевой параметр качества |

## Практика: шаблон для аудита кода

```xml
<role>
You are a senior [язык/фреймворк] architect specializing in [тип задачи].
</role>

<context>
Project: [название]
Repo: [ссылка]
Stack: [список технологий]
Goal: [что нужно улучшить]
</context>

<task>
Conduct a full technical audit across N axes.
For each finding include: file path, line number, severity (critical/major/minor),
concrete fix with code example.
Before reporting each finding, verify it against actual code.
If a module has no issues on an axis, state that explicitly.

<axis id="1" name="Architecture">...</axis>
<axis id="2" name="Reliability">...</axis>
...
</task>

<output>
## Axis N: [Name]
**Issues found:** X (critical: N, major: N, minor: N)

### [SEVERITY] Issue title
**File:** `path/to/File.php:42`
**Problem:** description
**Current code:** ```code```
**Fix:** ```code```

---
## Executive Summary
Top-5 priorities by impact.

## Refactoring Roadmap
Ordered phases with effort estimates.
</output>

<constraints>
- Report findings only — do not modify files.
- Only report issues with evidence in actual code.
- Keep findings actionable: drop details that don't change what the reader does next.
</constraints>
```

> `effort` выставляется в UI, а не тегом — см. выше.

## Передача кода в модель

Fable 5 не имеет прямого доступа к GitHub. Варианты:

**Собрать исходники скриптом:**

```bash
find packages -name "*.php" | while read f; do
  echo "// FILE: $f"
  cat "$f"
  echo -e "\n---\n"
done > source_dump.txt
```

Вставить содержимое между тегами:

```xml
<codebase>
// FILE: packages/core/src/...
...
</codebase>
```

**Поэтапный анализ:** запускать промпт отдельно по каждому модулю — даёт более
глубокий результат.

## Настройки клиента

| Параметр | Рекомендация |
|---|---|
| Model | Fable 5 / Mythos |
| Effort | `high` |
| Timeout | 5–10 минут (модель может думать долго) |
| Streaming | включить |
| Thinking checkbox | на усмотрение, не критично |
