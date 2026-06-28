---
name: eloquent-accessors
bucket: laravel-architecture
version: 0.1.0
description: "Активируй при написании/рефакторинге Eloquent accessors и mutators: когда видишь legacy getXxxAttribute()/setXxxAttribute() и пора перевести на современный Attribute::make() (get/set), или решаешь, где разместить и как типизировать вычисляемое свойство модели. Триггеры: getFooAttribute, Attribute::make, accessor, mutator, computed attribute, Illuminate\\Database\\Eloquent\\Casts\\Attribute"
risk: write
persona: oss-dev
tags: ["php", "laravel", "eloquent", "attributes", "accessors", "mutators", "patterns"]
requires: []
produces_for: []
outputs: []
snippets: [accessor.php]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Современный Laravel задаёт accessors/mutators одним методом, возвращающим
`Illuminate\Database\Eloquent\Casts\Attribute` через `Attribute::make(get:, set:)`,
вместо пары legacy-методов `getXxxAttribute()` / `setXxxAttribute()`. Это единая
точка для геттера и сеттера, лучше для статанализа и IDE, и это рекомендованный
Laravel путь. Скилл фиксирует канон: синтаксис, именование, видимость, типизацию,
размещение в классе и порядок миграции legacy-аксессоров.

### Когда активировать

- Пишешь новое вычисляемое свойство модели (`full_name`, `full_address`, нормализованный email и т.п.).
- Видишь legacy `getXxxAttribute()` / `setXxxAttribute()` и рефакторишь модель на `Attribute::make()`.
- Ревью Eloquent-модели: проверяешь, что аксессоры — современного синтаксиса, типизированы и стоят на своём месте.
- Нужен сеттер-нормализатор (привести email/телефон к канону при записи).

Не активировать: backing-касты простых типов (`casts()` массив — это не accessor),
метаданные enum-кейсов (там `laravel-architecture/enum-attributes`).

## Алгоритм

1. **Импорт**: `use Illuminate\Database\Eloquent\Casts\Attribute;` в начале модели.
2. **Метод**: `protected function fooBar(): Attribute` — `protected`, camelCase **без** префикса `get`, обязательный возвращаемый тип `Attribute`. Laravel сам спроецирует `fooBar` → доступ `$model->foo_bar` (snake_case).
3. **Тело**: `return Attribute::make(get: ..., set: ...)`. Только getter — передаёшь один `get:`; нужен сеттер — добавляешь `set:`.
4. **Замыкание**: получает `($value, $attributes)` — сырое значение из БД (для вычисляемых обычно `null`) и массив всех атрибутов модели. Для простых случаев — стрелочная функция; для многострочной логики — обычное замыкание с типом возврата.
5. **Размещение**: блок аксессоров — **после relations, перед scopes**. Держи единый порядок: `$fillable`/`casts()` → relations → attributes → scopes.
6. **Миграция legacy**: удали `getXxxAttribute()`/`setXxxAttribute()`, добавь `protected function xxx(): Attribute` с тем же поведением, добавь импорт, прогони тесты на эквивалентность.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Нужны эталоны: getter, getter+setter, многострочный аксессор, миграция legacy, размещение в классе | `snippets/accessor.php` |

## Типичные грабли

- **Префикс `get`/`set` в имени метода** — у `Attribute::make` его быть НЕ должно (`fullName()`, не `getFullName()`); legacy-методы, наоборот, требовали `getFullNameAttribute`.
- **`public` вместо `protected`** — методы-аксессоры всегда `protected`.
- **Забытый возвращаемый тип `Attribute`** — без него Laravel не распознает метод как аксессор.
- **Сырое `$value` у вычисляемых свойств** — для свойства без своей колонки `$value` обычно `null`; собирай значение из `$attributes` или `$this->...`.
- **Кеширование**: по умолчанию Laravel кеширует результат `get` в рамках жизни модели; для аксессоров над объектами (не примитивами) при необходимости `->shouldCache()` / `->withoutObjectCaching()`.
- **Смешение с `casts()`** — простое приведение типа колонки делается в `casts()`, а не аксессором; аксессор — для вычислений и нормализации.

## Чеклист качества

- [ ] Импорт `Illuminate\Database\Eloquent\Casts\Attribute` присутствует
- [ ] Метод `protected`, camelCase без префикса `get`/`set`, тип возврата `Attribute`
- [ ] Геттер и (при необходимости) сеттер — в одном `Attribute::make()`
- [ ] Вычисляемое значение собирается из `$attributes`/`$this`, а не из «пустого» `$value`
- [ ] Блок аксессоров стоит после relations и перед scopes
- [ ] Legacy `getXxxAttribute()`/`setXxxAttribute()` удалены при рефакторинге, поведение покрыто тестом
- [ ] Простые приведения типов остались в `casts()`, не продублированы аксессором

## Ссылки

- https://laravel.com/docs/eloquent-mutators#accessors-and-mutators
- https://laravel.com/docs/eloquent-mutators#attribute-casting
- `snippets/accessor.php` — эталоны: getter, getter+setter, многострочный, миграция legacy, размещение
- Связанные скиллы: `laravel-architecture/enum-attributes` (метаданные enum-кейсов через PHP-атрибуты), `php/laravel` (структура модели: casts/relations/scopes/accessors), `laravel-data-layer/laravel-data` (вычисляемые поля в DTO), `php/code-style-spatie` (стиль: strict_types/типизация/именование)
