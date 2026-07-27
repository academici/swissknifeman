# P5.1 — L_evidence: пять Laravel-конструкций (ручная сверка)

Проверка методом `code-review-graph query callees_of <qualified_name>` на реальных примерах
из flexcrm (граф построен на HEAD `80182e8`, детач-worktree). Для каждой конструкции: команда,
сырой список рёбер, вывод «ребро есть/нет» (edge = именованное ребро с реальным
`qualified_name` цели, а не только generic bare-name узел без атрибуции класса).

## 1. Facade (`Date::use`, `DB::prohibitDestructiveCommands`, `Password::defaults`)

Пример: `app/Providers/AppServiceProvider.php::AppServiceProvider.configureDefaults`
(`Date::use(CarbonImmutable::class)`, `DB::prohibitDestructiveCommands(...)`,
`Password::defaults(...)`/`Password::min(12)`).

```
code-review-graph query callees_of ".../AppServiceProvider.php::AppServiceProvider.configureDefaults"
→ 7 результатов: isProduction, app, uncompromised, symbols, numbers, letters, mixedCase
```

**Ребро на сам вызов facade-метода (`Date::use`, `DB::prohibitDestructiveCommands`,
`Password::defaults`, `Password::min`) — ОТСУТСТВУЕТ.** Часть fluent-цепочки (`mixedCase`,
`letters`, `numbers`, `symbols`, `uncompromised`) попала в вывод как bare-имя без
`qualified_name` (граф не знает, что это методы `Illuminate\Validation\Rules\Password`) — это
не резолюция, а совпадение по имени функции. **Вывод: ребро НЕТ** — facade-вызовы не
резолвятся к классу фасада.

## 2. `resolve()` (глобальный хелпер)

Пример: `app/Http/Middleware/HandleInertiaRequests.php::HandleInertiaRequests.share`
(`resolve(AuthViewFactory::class)->forGuest()`, `resolve(WebsocketRuntimeConfigFactory::class)->make()`,
`resolve(NotificationRepository::class)->unreadCount(...)`, `resolve(NavigationViewFactory::class)->fromConfig()`).

```
code-review-graph query callees_of ".../HandleInertiaRequests.php::HandleInertiaRequests.share"
→ 16 результатов, включая:
  Function forGuest  → .../AuthViewFactory.php::AuthViewFactory.forGuest
  Function make      → .../WebsocketRuntimeConfigFactory.php::WebsocketRuntimeConfigFactory.make
  Function unreadCount → .../NotificationRepository.php::NotificationRepository.unreadCount
  Function fromConfig  → .../NavigationViewFactory.php::NavigationViewFactory.fromConfig
  Function resolve (сам вызов resolve(...) — bare, без qualified_name)
```

**Вывод: ребро ЕСТЬ** — сам узел `resolve` остаётся bare, НО граф правильно разрешает
ПОСЛЕДУЮЩИЙ вызов метода цепочки (`->forGuest()`, `->make()`, …) к КОНКРЕТНОМУ классу,
переданному аргументом `X::class`. Это резолюция по типу аргумента, evidence-based —
**прямое опровержение пессимистичной части нашего `[UNVERIFIED]`** для этой конкретной
конструкции.

## 3. `macro()`

```
grep -rln "::macro(" app modules --include=*.php   → 0 совпадений
```

**Вывод: конструкция ОТСУТСТВУЕТ в кодовой базе flexcrm** — проверить нечем, не 0/5 по
неспособности графа, а N/A по составу репозитория. Кандидатов на будущее нет ни в одном из
405 распарсенных файлов.

## 4. Eloquent-связь (`belongsToMany`/`hasMany`/…)

Пример: `app/Models/Workspaces/Workspace.php::Workspace.users` (`return
$this->belongsToMany(User::class, 'wsp_workspace_user', ...)`).

```
code-review-graph query callees_of ".../Workspace.php::Workspace.users"
→ 3 результата: withTimestamps, withPivot, belongsToMany (все три — bare, без qualified_name)
```

**Вывод: ребро НЕТ** — `belongsToMany(User::class, …)` не резолвится в ребро на модель
`User`; строковый/class-string аргумент связи граф не читает как основание для ребра (в
отличие от `resolve()` выше, где `X::class` первым аргументом РЕЗОЛВИЛСЯ). Асимметрия
зафиксирована как факт, дальнейший разбор причины — вне scope ступени 0.

## 5. Blade-инклюд (`@include`/`@component`)

```
grep -rln "@include(\|@component(" resources --include=*.blade.php   → 0 совпадений
find . -iname "*.blade.php" -not -path "*/vendor/*"                  → resources/views/app.blade.php (1 файл)
```

flexcrm — Inertia-SPA: единственный Blade-файл (`app.blade.php`) — корневой шелл с
`<x-inertia::app />` (компонентный тег, НЕ `@include`), `@include`/`@component` в проекте не
встречаются вовсе. **Вывод: конструкция ОТСУТСТВУЕТ в кодовой базе** — N/A, как и `macro()`.
Дополнительно: `query file_summary resources/views/app.blade.php` вернул только 1 узел (сам
файл, без дочерних узлов) — граф вообще не разбирает содержимое единственного blade-файла на
директивы/компоненты, что отдельно подтверждает: даже если бы `@include` был, свидетельств за
парсинг Blade-специфики в этом репозитории у CRG нет.

## Итог

| Конструкция | В коде flexcrm | Ребро в графе |
|:--|:--|:--|
| Facade (`Date::`/`DB::`/`Password::`) | есть | **нет** |
| `resolve()` | есть | **есть** (через `X::class`-аргумент) |
| `macro()` | **отсутствует (N/A)** | не проверено |
| Eloquent-связь (`belongsToMany`/…) | есть | **нет** |
| Blade `@include`/`@component` | **отсутствует (N/A)** | не проверено |

**Снятие `[UNVERIFIED]` (частичное, не полное):** гипотеза «evidence-gated не покрывает
динамическую Laravel-магию» подтверждена для facade-вызовов и Eloquent-связей (ребро
отсутствует), но ОПРОВЕРГНУТА для `resolve()` — граф резолвит через явный `::class`-аргумент.
Две из пяти конструкций (`macro()`, Blade `@include`) в кодовой базе flexcrm физически не
встречаются — сверка на них невозможна на этом проекте, честно отмечено как N/A, а не
подогнано под 0/5 или 5/5. Формулировка `[UNVERIFIED]` из `findings/P5-codegraph-vs-serena-facts.md`
§5 заменяется на **смешанный, частично проверенный** вывод — не автоматический skip по
правилу ступени 0 (это факт для пакета решения P5.2), но и не безусловное подтверждение.
