---
name: attribute-authorization
bucket: php
version: 0.1.0
description: "Декларативная авторизация на уровне методов контроллера через атрибут #[CheckPermission] (enum-право + аргументы маршрута) и reflection-middleware CheckAccess поверх Gate. Активировать когда нужна декларативная проверка прав на экшенах, enum-права вместо строк, рефлексия-middleware."
risk: write
persona: oss-dev
tags: [php, laravel, authorization, attribute, reflection, middleware, gate, enum]
requires: []
produces_for: []
outputs: []
snippets: [CheckPermission.php, CheckAccess.php, OrderController.php]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Attribute-based authorization

## Контекст

Декларативная авторизация на уровне методов контроллера: право указывается атрибутом `#[CheckPermission]` прямо над экшеном, а не повторяется в теле как `$this->authorize(...)` или `Gate::allows(...)`. Атрибут несёт **enum-право** (а не строку), список имён параметров маршрута (которые резолвятся в модели через route-model binding) и параметры `abort` (статус + сообщение). Исполняет атрибуты middleware `CheckAccess`, который читает их рефлексией и сводит к `Gate::allows()`.

Активировать когда:
- нужна **декларативная** проверка прав на экшенах (право видно в сигнатуре метода, контроллер о Gate не знает);
- права моделируются **enum**, а не строками, и хочется типобезопасность на месте объявления;
- проектируется или правится **reflection-middleware**, читающий атрибуты метода контроллера;
- на одном экшене нужно **несколько** проверок с разными abort-статусами (403 для отказа, 404 для маскировки чужого ресурса).

### Граница с `php/laravel-permissions`

Это **ортогональный слой поверх** Gate, а не замена политик/гейтов:

| | `laravel-permissions` (RBAC) | `attribute-authorization` (этот скилл) |
|:---|:---|:---|
| Что определяет | **сами права**: ability через `Gate::define`, политики, RBAC, entity-scoped grants | **как право проверяется на экшене** — декларативно через атрибут |
| Идентификатор права | строка ability (`'order.view'`) | **enum-кейс**, в Gate уходит `$permission->value` |
| Точка применения | `Gate::allows`, `$user->can`, политики в сервис-слое | атрибут над методом + middleware-исполнитель |
| Механизм | контейнер, policy-резолвер, контекст | `ReflectionMethod::getAttributes()` |

Связка на практике: ability-логику (что значит «может ли») держим в Gate/policy по скиллу `laravel-permissions`; `enum::value` каждого права = строка ability там. Этот скилл лишь декларативно вешает вызов нужного ability на экшен. Enum-права как метаданные/типобезопасный слой — см. `php/enum-attributes`.

## Алгоритм

1. **Enum прав.** Заведи backed-enum (string) с кейсами-правами; значение каждого кейса = строка ability, зарегистрированного в Gate (см. `laravel-permissions`). Атрибут принимает `UnitEnum`, в Gate уходит `$permission->value`.
2. **Атрибут `CheckPermission`** (`app/Attributes/`, см. `snippets/CheckPermission.php`):
   - флаги `Attribute::TARGET_METHOD | Attribute::IS_REPEATABLE` — цель только метод, можно несколько на один экшен;
   - `final readonly`, конструктор с promoted-свойствами: `UnitEnum $permission`, `array $arguments = []` (имена параметров маршрута), `int $status = 403`, `?string $message = null`.
3. **Middleware `CheckAccess`** (`app/Http/Middleware/`, см. `snippets/CheckAccess.php`):
   - в `handle()` получить атрибуты экшена, для каждого — резолвнуть аргументы и вызвать `abort_if(! Gate::allows(ability: $attr->permission->value, arguments: $args), code: $attr->status, message: $attr->message ?? '')`;
   - **чтение атрибутов**: `$request->route()->getActionName()` → если строка содержит `@`, разобрать на `[$controllerClass, $methodName]`; проверить `class_exists` + `method_exists`; `new ReflectionMethod(...)->getAttributes(CheckPermission::class)`; каждый → `->newInstance()`. Closure-роуты и отсутствие `@` → вернуть `[]` (middleware прозрачен).
   - **резолв аргументов**: `array_values(array_map(fn($name) => $request->route($name), $attr->arguments))` — имена параметров маршрута в значения (обычно Model из route-model binding), позиционно, в порядке объявления.
4. **Регистрация middleware** (см. секцию ниже) — алиас + навешивание на нужные группы/маршруты.
5. **Применение в контроллере** (см. `snippets/OrderController.php`): навесить `#[CheckPermission(Permission::Foo, arguments: ['order'])]` над экшеном; имена в `arguments` обязаны совпадать с именами параметров маршрута. Несколько атрибутов = логическое И (все должны пройти).
6. **Тестирование** (см. секцию ниже): feature-тесты на 200/403/404 при разных правах + при отсутствии атрибута; unit на резолв аргументов и порядок.

## Регистрация middleware

**Laravel 11/12** (`bootstrap/app.php`) — алиас, затем навешивание на группу/маршруты:

```php
->withMiddleware(function (Middleware $middleware): void {
    $middleware->alias([
        'check-access' => \App\Http\Middleware\CheckAccess::class,
    ]);
    // вариант: на всю web-группу
    $middleware->appendToGroup('web', \App\Http\Middleware\CheckAccess::class);
})
```

**Применение к маршрутам:**

```php
Route::middleware(['auth', 'check-access'])->group(function (): void {
    Route::resource('orders', OrderController::class);
});
```

**Laravel 10 и ниже** — алиас в `App\Http\Kernel::$middlewareAliases` (или `$routeMiddleware`).

Порядок: `CheckAccess` должен идти **после** `auth` (Gate опирается на текущего пользователя) и **после** SubstituteBindings, если в `arguments` нужны уже разрезолвленные модели (route-model binding). При навешивании на всю группу экшены без атрибутов остаются открытыми — middleware на них прозрачен.

## Тестирование

- **Feature (happy path)**: пользователь с правом → 200; вызов `Gate::allows` получает разрезолвленную модель.
- **Feature (deny)**: пользователь без права → `abort` с `status` из атрибута (по умолчанию 403; для второй ветки экшена — 404).
- **Несколько атрибутов**: проходит право A, не проходит B → отказ; меняем местами — снова отказ (логическое И).
- **Нет атрибута**: экшен без `#[CheckPermission]` под группой с middleware → 200 (прозрачность).
- **Closure-роут / нестандартный action**: middleware не падает, возвращает `[]`.
- **Unit на резолв**: `arguments: ['a', 'b']` → в Gate уходит `[$routeA, $routeB]` именно в этом порядке и через `array_values` (без строковых ключей).
- Удобно подменять Gate через `Gate::shouldReceive`/фейк или регистрировать тестовый ability, чтобы изолировать middleware от реальной RBAC-логики.

## Чеклист качества

- [ ] Атрибут `final readonly`, флаги `TARGET_METHOD | IS_REPEATABLE`, право типа `UnitEnum`
- [ ] В Gate уходит `$permission->value`, а не сам enum
- [ ] Middleware читает атрибуты через `ReflectionMethod::getAttributes()`, а не парсит строки иначе
- [ ] Closure-роуты, отсутствие `@`, несуществующий класс/метод → `[]` (middleware не бросает исключений)
- [ ] Аргументы резолвятся из параметров маршрута через `array_values` (позиционно, без строковых ключей)
- [ ] `abort_if` использует `status` и `message` из атрибута; `message ?? ''`
- [ ] Имена в `arguments` совпадают с именами параметров маршрута; модели приходят разрезолвленными (middleware после SubstituteBindings)
- [ ] Middleware зарегистрирован и навешен после `auth`; контроллер не содержит ручных `Gate::allows`/`$this->authorize`
- [ ] Сами abilities определены отдельно (Gate/policy, скилл `laravel-permissions`), здесь — только декларация
- [ ] Тесты на 200 / 403 / 404, на несколько атрибутов, на отсутствие атрибута и на порядок аргументов

## Ссылки

- snippets/CheckPermission.php — атрибут
- snippets/CheckAccess.php — reflection-middleware
- snippets/OrderController.php — контроллер с `#[CheckPermission]`
- https://www.php.net/manual/en/language.attributes.php
- https://laravel.com/docs/authorization (Gate::allows)
- Связанные скиллы: `php/laravel-permissions` (определение прав/политик/гейтов — граница выше), `php/enum-attributes` (enum как метаданные), `php/named-arguments` (стиль вызовов в сниппетах)
