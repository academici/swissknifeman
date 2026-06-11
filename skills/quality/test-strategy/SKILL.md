---
name: test-strategy
bucket: quality
version: 0.1.0
description: Стратегия тестирования: пирамида (unit/integration/e2e), coverage policy, mock vs real, какие фичи требуют какой уровень тестов
risk: draft
persona: quality
tags: [quality, testing]
requires: []
produces_for: [code-review]
outputs: ["docs/03_Dev/Test_Strategy.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Test Strategy

Применять когда: проект достиг стадии, где количество фич и регрессий делает ad-hoc тестирование непрактичным. Обычно — после первого MVP, когда команда замечает что багфиксы ломают другие места. Также при онбординге нового продукта или при принятии legacy-кодбазы.

Не применять: до первого работающего MVP (нечего стабилизировать) или для одноразовых скриптов / PoC.

---

## Когда НЕ применять

- Прототип / PoC, который выкинут после демо
- Одноразовая миграция данных
- Скрипт автоматизации одного человека на 50 строк
- До того, как зафиксирована архитектура (`architecture.md`) — иначе тесты придётся переписывать

---

## Шаг 1. Test Pyramid — пропорции

| Уровень | Доля | Что тестирует | Скорость | Стоимость поддержки |
|:---|:---:|:---|:---|:---|
| **Unit** | ~70% | Чистые функции, бизнес-логика, edge-cases | мс | низкая |
| **Integration** | ~20% | Слой ↔ слой (репозиторий ↔ БД, сервис ↔ кэш) | сотни мс | средняя |
| **E2E** | ~10% | Сквозной сценарий пользователя через UI/API | секунды-минуты | высокая |

**Антипаттерн «ice-cream cone»:** много E2E + мало unit = медленный CI, хрупкие тесты, ложные алерты. Если так получилось — записать в `tech-debt-audit`.

---

## Шаг 2. Coverage Policy

| Слой кода | Минимум coverage | Обоснование |
|:---|:---:|:---|
| Бизнес-логика / domain | ≥ 90% | Здесь самые дорогие баги |
| Application / use-cases | ≥ 80% | Координация — нужны интеграционные |
| Adapters (БД, HTTP, external API) | ≥ 60% | Часть проверяется integration-тестами |
| UI / presentation | ≥ 40% | Хрупкие, дорого, низкий ROI |
| Generated / boilerplate | 0% | Исключить из coverage report |

**Правило:** coverage — нижняя граница, не цель. 100% coverage не означает 100% корректности. Важнее — **mutation testing** для критичных модулей (Stryker, mutmut, infection).

---

## Шаг 3. Mock vs Real — матрица выбора

| Что тестируем | Зависимость | Mock или Real? |
|:---|:---|:---|
| Unit-тест чистой функции | — | n/a |
| Unit-тест с инъекцией зависимости | внутренний сервис | **mock** (или fake/in-memory) |
| Integration: репозиторий | БД | **real** (testcontainers / SQLite in-memory) |
| Integration: внешний HTTP API | сторонний сервис | **mock** (wiremock / MSW / VCR) |
| Integration: очередь | Kafka/RabbitMQ | **real** (testcontainers) |
| E2E: критичный happy path | весь стек | **real** (или близкое staging) |
| E2E: платёжный шлюз | Stripe/PayPal | **sandbox** (никогда real) |

**Запрет:** мокать собственный код в integration-тестах — это превращает их в недо-unit.

---

## Шаг 4. Какие фичи требуют какой уровень

| Тип фичи | Unit | Integration | E2E |
|:---|:---:|:---:|:---:|
| Алгоритм / расчёт (биллинг, scoring) | ✅ обязательно | — | — |
| CRUD entity через слои | ✅ | ✅ | — |
| Авторизация / RBAC | ✅ | ✅ | ✅ (smoke) |
| Платёжный flow | ✅ | ✅ | ✅ |
| Регистрация пользователя | ✅ | ✅ | ✅ |
| UI-форма с валидацией | ✅ (логика) | — | ✅ (smoke) |
| Background job / cron | ✅ | ✅ | — |
| Migration скрипт | — | ✅ (на копии prod-данных) | — |

---

## Шаг 5. Test Data Strategy

3 подхода — выбрать один основной:

| Подход | Когда | Плюсы | Минусы |
|:---|:---|:---|:---|
| **Fixtures (статические)** | Простые сценарии | Воспроизводимо, читаемо | Сложно поддерживать при росте |
| **Factories / Builders** | Средний проект | Гибко, DRY | Скрытая магия, learning curve |
| **Production replicas (анонимизированные)** | Сложные регрессии | Реалистично | Дорого, GDPR-риски |

Анти-паттерн: shared mutable state между тестами (через общую БД без cleanup) — нарушает изоляцию, делает порядок прогона значимым.

---

## Шаг 6. CI Integration

```yaml
# .github/workflows/test.yml
stages:
  - lint           # ~10 сек, быстрый fail
  - unit           # ~30 сек, параллелится по модулям
  - integration    # ~2 мин, требует docker services
  - e2e            # ~5-10 мин, отдельная job, не блокирует merge
  - coverage       # gate: < min → fail PR
```

**Правило:** unit + integration — **обязаны проходить** до merge. E2E можно как nightly или as post-merge smoke.

---

## Что агент добавляет сам

- Расчёт «тестовый бюджет времени»: сколько % времени разработки фичи закладывается на тесты (стандарт — 30-40%, для критичных модулей 50%+)
- Рекомендация по test framework под язык (см. соответствующий `oss-dev/references/oss-*.md`)
- Предупреждение о flaky tests: правило «3 strikes — quarantine», метрика flakiness rate
- Шаблон test plan для крупной фичи (preconditions / scenarios / expected outcomes)

---

## Структура output-файла `Test_Strategy.md`

```markdown
# Test Strategy: [ProjectName]

## 1. Пирамида (целевые пропорции + текущее состояние)
## 2. Coverage policy (по слоям + текущий coverage)
## 3. Mock vs Real (таблица решений на конкретные зависимости проекта)
## 4. Test Data Strategy (выбранный подход + обоснование)
## 5. CI Pipeline (stages + gates)
## 6. Flaky tests policy (как ловим и убираем)
## 7. Test budget (% времени на тесты)
## 8. Open questions / TODO
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Писать E2E без unit-покрытия той же логики
- Coverage gate < 60% для domain-слоя (это маркер «тесты вообще не пишутся»)
- Shared mutable БД между тестами без cleanup
- Мокать стандартную библиотеку (datetime, fs) вместо инъекции абстракции — делает тесты хрупкими к рефакторингу
- Считать coverage целью вместо метрики риска
- Запускать тесты против production-окружения
