# Экономика стадий, контекста и подписочных лимитов

Разделение по моделям полезно, когда сокращает суммарную работу дорогой модели с сохранением качества. Число дешёвых агентов само по себе экономию не доказывает. В этом исследовании оплаченные model runs не выполнялись; тарифы и конкретные модельные цены не используются.

## Что считать

Для API при известных rates:

```text
cost(stage) = uncached_input × input_rate
            + cached_input × cached_rate
            + cache_write_cost_if_applicable
            + output × output_rate
            + tools_and_runtime_cost

cost(task) = Σ stage_cost + retries + repair + integration
effective_cost = total_experiment_cost / accepted_tasks
```

Время владельца учитывается отдельно: ручной ремонт, решения о зависаниях, сбор утраченных artifacts, повторный запуск. Для подписочных CLI вместо выдуманных token dollars записываются доступные показатели quota, model usage, время до rate limit и ожидание восстановления лимита. Неизвестный usage не равен бесплатному run.

Context pack, собранный Python, не расходует LLM на сбор. Но его отправка модели всё равно потребляет input/context budget. Передача большого pack последовательно пяти моделям создаёт пять вводов, а не одну общую память. Поэтому надо измерять context bytes/tokens по стадиям, повторяющиеся префиксы и обязательную информацию.

## Условный числовой пример

Ниже искусственные единицы стоимости, **не тарифы каких-либо моделей**:

| Компонент | Одна сильная модель | Разделённый pipeline |
| --- | ---: | ---: |
| Основная работа | 100 | Strong design 45 |
| Context scout | 0 | 5 |
| Bounded implementation | 0 | 20 |
| Review | 0 | 20 |
| Дополнительная передача контекста | 0 | 10 |
| Ожидаемый repair | 15 | 20 |
| Всего | **115** | **120** |

Если cheap implementation позволяет сократить strong design до 35, а repair остаётся 10, pipeline стоит 100. Если лишний review не требовался, его отсутствие меняет сравнение ещё сильнее. В реальном эксперименте review policy должна быть одинаковой между сравниваемыми вариантами; иначе приписываем экономию качественно другому процессу.

Общая граница окупаемости: saved strong work > cheap stages + дополнительный input + дополнительный repair/integration. Самое важное неизвестное обычно — repair и необходимость заново объяснить задачу.

## Какие операции кому отдавать

Python подходит для plan JSON, dependencies, source hashes, diff, tests, scope checks и lifecycle. Economy scout полезен для семантической карты кода и поиска возможных связанных мест, но его предположения надо помечать. Если карта не улучшает работу сильной модели, профиль с обязательным scout останется пользовательским выбором, а не доказанной оптимизацией.

Сильная модель нужна для архитектурных решений, сложной реализации, frontend UX и неоднозначного debugging. Economy executor — для небольшого task с ясным контрактом, локальными files и checks. Разделение «сильная думает, слабая пишет весь код» без конкретной декомпозиции увеличивает риск потерять неявные решения.

Git bookkeeping и закрытие фазы почти всегда лучше выполнять кодом. Дешёвая модель может написать changelog/summary, но это отдельный optional artifact. Ни summary, ни красивый final answer не заменяют прохождение checks и Task acceptance.

## Cache нельзя считать общей памятью между провайдерами

Cache связан с конкретным backend/model и подходящим повторяемым префиксом. Переход Claude → Codex → Grok не переносит prompt cache. Изменение instructions/tool definitions или вставка динамических данных в начало может уменьшить попадания. Документированные API cache mechanisms не доказывают аналогичную скидку/квоту подписочного CLI. Источники: [Anthropic caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [OpenAI caching](https://developers.openai.com/api/docs/guides/prompt-caching).

Стабильные инструкции и форматы стоит отделять от переменных task artifacts. Фактические cache hits измеряются по доступному usage. В аудите намеренно не фиксируются конкретные TTL и коэффициенты из Perplexity Q04b: они меняются и для выбора engine не нужны.

## Как сохранить полноту без бессмысленного повторения

Authoritative context pack остаётся полным. Python делает index, links, dependency map и mandatory read list. Scout дополняет навигацию, а каждый исполнитель получает обязательную информацию своей роли и доступ к исходному pack. Это proposed extra projection, которую нужно проверить на полноту; текущий Task context не обрезается.

Для реализации передаётся design contract, relevant files и checks. Для reviewer — actual diff, criteria, design decisions и результаты tests. Не надо автоматически добавлять весь dialogue предыдущих агентов, внутреннюю болтовню или уже нерелевантные logs. При существенной неопределённости лучше сохранить исполнение у сильной модели, чем создавать ещё один handoff.

## Минимальный эксперимент

Сначала шесть representative задач в трёх вариантах: strong-only с deterministic context; mandatory economy scout + strong full implementation; scout + strong design + bounded economy implementation. Review одинаково включается для выбранных задач во всех вариантах. Повторения нужны, поскольку один удачный run не показывает распределение ошибок.

Считать accepted tasks, стоимость/квоту, total latency, время владельца, repair loops, tests, scope violations и качество frontend приёмки. Отдельно считать простые и сложные задачи. Малая выборка даёт предварительный engineering signal, а не статистическое доказательство; расширять её, если различия близки или решения дорогие. Сравнительный протокол: [pilot](pilot-and-claude-handoff.md).
