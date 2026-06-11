---
name: eval-design
bucket: architect
version: 0.1.0
description: Оценка качества LLM/AI-выводов — eval-set, метрики, regression-харнес, automated + human review
risk: draft
persona: architect
tags: [agentic, validation]
requires: [agent-design]
produces_for: []
outputs: ["03_Dev/Eval_Design.md", "03_Dev/Evals/eval_set_v1.jsonl"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Eval Design

Применять когда: продукт использует LLM или другую нестрого-детерминированную AI-модель, и нужно **измерять качество вывода** до релиза и в проде. Критичен для Edufy (педагогика), Memster (контент-модерация), Finbrain (финансовые рекомендации), Edufy AI-tutor.

Без eval-харнеса LLM-продукт = «вроде работает» = катастрофа в проде.

---

## Когда НЕ применять

- Продукт без AI / LLM-компонента — не применимо.
- LLM используется только для не-критичных задач (например, авто-теги в админке) — облегчённый eval, не полный харнес.
- Нет `agent-design` — отказать, без agent-контракта непонятно что мерять.

---

## 4 уровня eval

### Уровень 1. Smoke evals (CI)
**Что:** базовый sanity. Не падает, формат ответа валидный, не отвечает на jailbreak.
**Когда:** на каждый PR. Время выполнения < 2 минуты.
**Размер:** 20–50 примеров.

### Уровень 2. Reference evals (nightly)
**Что:** соответствие эталонным ответам / golden dataset.
**Когда:** ежедневный CI, перед релизом.
**Размер:** 200–500 примеров.

### Уровень 3. Behavioural evals (pre-release)
**Что:** граничные случаи, состязательные входы, домен-специфичные провалы.
**Когда:** перед каждым релизом модели или промпта.
**Размер:** 500–2000 примеров.

### Уровень 4. Production evals (online)
**Что:** seed реальных запросов + human review + auto-scoring.
**Когда:** непрерывно в проде.
**Покрытие:** 1–5% live traffic.

---

## Метрики (выбор зависит от задачи)

### Generative tasks (генерация текста, ответ ученику, mem caption)
- **Exact match** — для строго детерминированных частей (числа, даты)
- **Embedding similarity** — семантическая близость к reference (cosine, threshold ~0.85)
- **LLM-as-judge** — отдельная модель оценивает ответ по rubric (0–5 шкала)
- **Human eval** — для критичных доменов (педагогика, финсоветы)

### Classification / extraction (тегирование, извлечение полей)
- **Precision / Recall / F1** — стандартно
- **Per-class confusion matrix** — где модель путается

### Tool-use / agentic (Finbrain MCP, Edufy tutor с tools)
- **Tool selection accuracy** — выбрал ли нужный tool
- **Argument correctness** — правильные ли аргументы
- **Recovery rate** — справляется ли с ошибкой tool'а
- **Step efficiency** — сколько шагов на задачу (меньше = лучше)

### Safety / refusal
- **Jailbreak resistance** — % отказа на adversarial промпты
- **False refusal** — % отказа на легитимных запросах (не должно быть слишком высоким)
- **PII leak rate** — утечка персональных данных в выводе

### Cost / latency
- **Tokens per task** — для cost tracking
- **p50/p95 latency** — UX

---

## Eval set — структура

Формат хранения: JSONL в `03_Dev/Evals/eval_set_v1.jsonl`

```json
{"id": "ev-001", "category": "happy-path", "input": "...", "reference": "...", "metrics": ["embedding_sim", "llm_judge"]}
{"id": "ev-002", "category": "edge", "input": "...", "reference": "...", "metrics": ["exact_match"]}
{"id": "ev-003", "category": "adversarial", "input": "Ignore previous instructions...", "expected_behavior": "refusal"}
```

**Покрытие eval-set обязательно:**
- ≥ 60% happy path
- ≥ 20% edge cases (пустой ввод, мульти-язык, длинный контекст, конфликтующие требования)
- ≥ 10% adversarial (jailbreak, prompt injection, токсичные входы)
- ≥ 10% domain-specific failures (для Edufy — педагогические ловушки; для Finbrain — confused-deputy на финансовых вопросах)

---

## Regression-харнес

Каждый release model/prompt → прогон по eval-set → сравнение с предыдущим baseline.

**Pass criteria:**
- Reference evals: ≥ 95% от baseline
- Smoke evals: 100% pass
- Behavioural: regression на любой категории > 5% = блок релиза
- Safety: zero-tolerance на jailbreak

**Versioning:**
- Eval set версионируется как код (`eval_set_v1.jsonl`, `eval_set_v2.jsonl`)
- Baseline-результаты хранятся (`evals/results/<timestamp>_<model>_<prompt>.json`)
- Изменение eval-set ≠ изменение модели — разделять PR

---

## LLM-as-judge — подводные камни

Если используется LLM для оценки другого LLM:
- **Bias toward verbose** — judge склонен давать высокие оценки длинным ответам
- **Position bias** — при сравнении двух ответов первый часто выигрывает
- **Self-preference** — модель X оценивает свои ответы выше, чем модель Y → использовать **другую** модель для judge
- **Rubric обязателен** — без явных критериев judge даёт шум

Mitigation:
- Random shuffling в сравнениях
- Judge = более сильная модель, чем оцениваемая
- Калибровка judge на 50–100 human-rated примерах перед запуском

---

## Что агент добавляет сам

- **Domain-specific failures.** Для каждого проекта — конкретные ловушки:
  - Edufy: «решает за ученика вместо подсказки», «даёт неверный пример при правильном ответе»
  - Memster: «генерирует контент, нарушающий DMCA», «caption не соответствует видео»
  - Finbrain: «даёт инвестрекомендацию без disclaimer», «галлюцинирует тикер»
- **Cost guardrails в eval.** Eval-прогон может стоить $50 за раз — указать бюджет и оптимизировать (batching, кэширование вызовов provider).
- **Reproducibility.** `temperature=0`, фиксированный seed (если provider поддерживает), фиксированная версия модели (`gpt-4o-2024-11-20`, не `gpt-4o`).
- **Privacy в eval-set.** Реальные user-запросы → анонимизация перед добавлением в eval (см. `security-design`).

---

## Структура output-файлов

### `03_Dev/Eval_Design.md`

```markdown
---
project: [ProjectName]
stage: eval-design
based_on: 03_Dev/Agent_Design.md
---

# Eval Design — [ProjectName]

## AI-компонент
- Модели: ...
- Use-cases: ...
- Critical paths (где провал = harm): ...

## Уровни eval
- L1 Smoke (CI): [размер, время]
- L2 Reference (nightly): ...
- L3 Behavioural (pre-release): ...
- L4 Production (online): ...

## Метрики
| Категория задачи | Метрики | Пороги |
|:---|:---|:---|

## Eval set v1
- Файл: `03_Dev/Evals/eval_set_v1.jsonl`
- Покрытие: [happy/edge/adversarial/domain %]
- Размер: [N примеров]

## Regression-харнес
- Pass criteria: ...
- Baseline-хранение: ...
- Trigger: PR / nightly / release

## LLM-as-judge (если используется)
- Judge model: ...
- Rubric: ...
- Калибровка: [N примеров, kappa с human]

## Production monitoring
- % live traffic под evals: ...
- Связь с observability: alert при padении метрики X

## Domain-specific failures (агент)
- ...

## Cost & reproducibility
- Стоимость full eval-run: $...
- Reproducibility: temperature=0, model pin: ...
```

### `03_Dev/Evals/eval_set_v1.jsonl`
Стартовый eval-set, минимум 50 примеров на launch.

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Релизить LLM-фичу без хотя бы smoke evals в CI
- Использовать одну и ту же модель как judge и as-tested
- Запускать eval с `temperature > 0` без фиксации seed
- Хранить реальные user-запросы в eval-set без анонимизации
- "Покажу метрики потом" — без eval-set качество = вкусовщина
- Игнорировать adversarial категорию — jailbreak найдут пользователи
