---
name: enum-state-machine
bucket: laravel-architecture
version: 0.1.0
description: "Активируй, когда статус домена (Order/Document/Subscription) растёт в граф переходов: единый граф рёбер как метод enum transitionDefinitions() (from→to + guard + action + label), рантайм-реестр переходов (canTransition/allowedFrom) поверх него, и исполнение перехода в Action под DB::transaction() с доменным событием. Триггеры: PHP enum статусов, разрешённые переходы, StateMachine/workflow, parallel transition graph пора свести в один источник, canTransitionTo, allowedTransitions, нелегальный переход статуса"
risk: write
persona: oss-dev
tags: ["php", "enum", "state-machine", "workflow", "laravel", "transitions", "domain", "actions"]
requires: []
produces_for: []
outputs: []
snippets: [enum-with-transitions.php, transitions-registry.php, transition-action.php]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Доменный статус (`OrderStatus`, `DocumentStatus`, `SubscriptionStatus`) перестаёт быть
плоским списком значений и обрастает **правилами переходов**: из какого статуса в какой
можно перейти, кто/что это разрешает, какое действие исполняется. Антипаттерн — размазать
эти правила: где-то `if ($status === ...)` в контроллере, где-то отдельный массив в
сервисе, где-то проверка в политике. Граф рассыпается на параллельные неконсистентные
копии.

Паттерн: **один источник истины — граф рёбер как статический метод enum**
(`transitionDefinitions(): array`), а поверх — тонкий **рантайм-реестр** (`*StatusTransitions`),
который строит из него adjacency и отвечает на `canTransition(from, to)` / `allowedFrom(from)`.
Сам переход исполняется в `Action` под `DB::transaction()` и публикует доменное событие.

### Когда активировать

- В enum статусов назревает/есть `match`/`if` про «из A можно в B» — пора в граф рёбер.
- Появилась вторая копия списка переходов (в сервисе, политике, фронте) — свести в один.
- Нужен ответ «какие переходы доступны из текущего статуса» для UI (кнопки действий).
- Переход должен быть атомарным и с побочными эффектами (история, уведомление, broadcast).
- Нужно навесить на ребро метаданные: подпись кнопки, требуемая политика, класс Action.

### Не активировать

- Простой статус без правил переходов (любой→любой) — хватит backing-enum.
- Задача только про **метаданные кейсов** (label/color/priority) без графа переходов — это
  `laravel-architecture/enum-attributes` (тот скилл явно не про state-machine; этот — дополняет его).
- Доменно-специфичная реализация одного проекта (имена конкретных статусов/действий) —
  оформляется как **project-local** скилл (`<project>/.ai|.claude/skills/`), а не общий реестр.

## Алгоритм

1. **Граф рёбер на enum.** Статический `public static function transitionDefinitions(): array`
   возвращает список рёбер. Минимум — `from`/`to` (кейсы enum); по необходимости —
   `guard` (имя предиката/ability), `action` (FQCN Action-класса), `label` (для UI),
   и доменные оси (`role`, `process`, `condition`). Это **единственный** источник графа —
   никаких параллельных копий. См. `snippets/enum-with-transitions.php`.
2. **Рантайм-реестр.** `final class XxxStatusTransitions` строит из определений adjacency
   (`array<string, list<Status>>`) **лениво и кэширует** в статике (reflection/обход
   массива — на горячих путях дорого). Публично: `allowedFrom(Status $from): array`,
   `canTransition(Status $from, Status $to): bool`. Источник данных — только
   `transitionDefinitions()`. См. `snippets/transitions-registry.php`.
3. **Guard перед переходом.** Перед мутацией проверяй `canTransition($from, $to)` (легальность
   ребра) **и** доменный предикат/политику из `guard` (право конкретного пользователя/контекста).
   Нелегальный переход → `ValidationException`/`abort`, не молчаливый no-op.
4. **Исполнение в Action.** Переход — это use-case: `final readonly` Action с одним
   `execute()`, открывает `DB::transaction()`, пишет новый статус (+ историю/связанные
   модели), затем `dispatch()` доменного события. Action не принимает `Request` (границы —
   `php/laravel`, `general/cross-layer-change-checklist`). См. `snippets/transition-action.php`.
5. **Событие после коммита.** Доменное событие реализует `ShouldDispatchAfterCommit`, чтобы
   слушатели/broadcast не увидели несохранённое состояние при откате транзакции. Детали
   broadcast/listener — `laravel-data-layer/laravel-broadcasting` (не дублировать здесь).
6. **UI-доступные действия.** Кнопки/экшены на фронте строятся из `allowedFrom($current)` +
   `label`/`guard` каждого ребра — UI не хардкодит переходы, а читает граф.
7. **Эволюция графа.** Новый переход = новая строка в `transitionDefinitions()` (+ Action,
   если нужен). Тест на графе (см. чеклист) ловит висячие рёбра и недостижимые статусы.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Описываю граф переходов на самом enum | `snippets/enum-with-transitions.php` |
| Пишу рантайм-реестр (adjacency, canTransition, allowedFrom) | `snippets/transitions-registry.php` |
| Исполняю переход в Action (transaction + событие after-commit) | `snippets/transition-action.php` |

## Типичные грабли

- **Параллельный граф.** Любой второй список переходов (в сервисе/политике/фронте) —
  источник рассинхрона. Всё читает `transitionDefinitions()`.
- **Reflection/обход на каждый вызов.** `allowedFrom` дёргается в списках/таблицах —
  кэшировать adjacency в статике, инвалидация не нужна (граф статичен на рантайме).
- **Молчаливый no-op при нелегальном переходе.** Должно быть исключение, иначе баг прячется.
- **Событие без `ShouldDispatchAfterCommit`.** Слушатель в той же транзакции увидит
  незакоммиченное состояние; при откате — фантомный side-effect.
- **Логика перехода в контроллере/сервисе.** Мутация и транзакционная граница — в Action.
- **Guard ⊆ canTransition.** `canTransition` проверяет легальность ребра, `guard` — право
  субъекта; это разные проверки, нужны обе.

## Чеклист качества

- [ ] Граф переходов — единственный, в `transitionDefinitions()` на enum
- [ ] Рантайм-реестр читает только `transitionDefinitions()`, adjacency закэширована
- [ ] `canTransition()` вызывается перед мутацией; нелегальный переход → исключение
- [ ] Право субъекта (`guard`/policy) проверяется отдельно от легальности ребра
- [ ] Переход исполняется в `final readonly` Action под `DB::transaction()`, без `Request`
- [ ] Доменное событие реализует `ShouldDispatchAfterCommit`
- [ ] UI-действия строятся из `allowedFrom($current)`, а не хардкодом
- [ ] Есть тест графа: нет висячих рёбер (from/to существуют), нет недостижимых статусов

## Ссылки

- `laravel-architecture/enum-attributes` — метаданные кейсов (label/color/priority) через атрибуты+Concern;
  здесь — граф переходов поверх таких enum (скиллы дополняют друг друга).
- `laravel-data-layer/laravel-broadcasting` — `ShouldDispatchAfterCommit`, broadcast и listeners перехода.
- `php/laravel`, `php/repositories` — границы Action/Repository, в которых живёт переход.
- `general/cross-layer-change-checklist` — синхронизация слоёв при добавлении перехода.
