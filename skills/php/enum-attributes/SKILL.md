---
name: enum-attributes
bucket: php
version: 0.2.0
description: "Активируй при работе с метаданными enum: когда match-простыни label()/color()/description() пора заменить на PHP-атрибуты #[Label]/#[Color]/#[Description] над кейсами + Concern-трейты с reflection-резолвером, или когда нужно экспортировать enum как TS-тип через стэк #[TypeScript] (App.Enums.* union в .d.ts). Триггеры: PHP enum, атрибуты на кейсах, getLabel()/getColor(), Filament HasLabel, spatie/laravel-typescript-transformer, локальный enum-concern через path-repository"
risk: write
persona: oss-dev
tags: ["php", "enum", "attributes", "reflection", "laravel", "patterns", "typescript"]
requires: []
produces_for: []
outputs: []
snippets: [attribute.php, concern-trait.php, enum-example.php, composer-path-repo.json, enum-typescript.php]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Декларативные метаданные enum-кейсов: вместо `match`-простыней `label()`/`color()` на 20 кейсов — PHP-атрибуты `#[Label('...')]`, `#[Color('...')]`, `#[Description('...')]` прямо над кейсом + Concern-трейты, дающие методы `getLabel()`/`getColor()`. Чтение — через единый reflection-резолвер. Коллекционные операции (all/values/labels) — пакет `emreyarligan/enum-concern`, подключаемый как локальный path-repository.

### Когда активировать

- В enum есть/назревает `match($this) { ... }` для меток, цветов, описаний, приоритетов — пора вынести в атрибуты на кейсах.
- Нужны методы `getLabel()`/`getColor()`/`getDescription()` на enum, в т.ч. для совместимости с Filament `HasLabel`.
- Пишешь свой класс PHP-атрибута (`#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]`) или reflection-резолвер метаданных кейсов.
- Делаешь доменные оси метаданных (`#[Stage(...)]`, `#[Dashboard(priority: N)]`) и статические выборки кейсов через `ReflectionEnum::getCases()`.
- Нужно отдать enum как TypeScript-тип на фронт (`#[TypeScript]`, `spatie/laravel-typescript-transformer`, `App.Enums.*` union в `.d.ts`).
- Подключаешь локальный пакет (`enum-concern`) как `repositories: [{type: path, ...}]` с `symlink`.

Не активировать: простые enum без метаданных, где хватает backing-значения; задачи чисто о фронтенд-потреблении типов — там `frontend/backend-type-sync`.

## Алгоритм

1. **Атрибут**: `final readonly class Label` с `#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]` и публичным конструктором-значением. Один атрибут — одна ось метаданных (Label, Color, Description, Priority...).
2. **Резолвер**: статический `EnumCaseAttributeResolver::forCase(UnitEnum $case, string $attributeClass): ?object` — `ReflectionEnum` → `getCase($case->name)` → `getAttributes($attributeClass)` → `newInstance()`. Generic-аннотация `@template TAttribute` даёт типизацию в IDE/PHPStan.
3. **Concern-трейт**: `HasLabelAttribute::getLabel()` вызывает резолвер, проверяет instanceof и возвращает значение либо дефолт (пустая строка, серый цвет `#6c757d`).
4. **Enum**: `use HasLabelAttribute, HasColorAttribute, ...` + атрибуты над каждым кейсом. Можно совмещать с `EnumConcern` (коллекции) и Filament `HasLabel`.
5. **Доменные атрибуты**: по тому же паттерну добавляются свои оси (`#[Stage(...)]`, `#[Dashboard(priority: N)]`) и статические выборки `allForStage()` через `ReflectionEnum::getCases()`.
6. **Локальный пакет**: enum-concern подключается через `repositories: [{type: path, url: packages/enum-concern, options: {symlink: true}}]` + `composer require vendor/enum-concern`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Создаю новый класс атрибута (Label/Color/своя ось) | `snippets/attribute.php` |
| Пишу Concern-трейт и/или reflection-резолвер | `snippets/concern-trait.php` |
| Обогащаю enum атрибутами и статическими выборками | `snippets/enum-example.php` |
| Подключаю локальный пакет через path-repository | `snippets/composer-path-repo.json` |
| Навешиваю #[TypeScript] поверх #[Label]/#[Priority] и экспортирую тип на фронт | `snippets/enum-typescript.php` |

## Типичные грабли

- `Attribute::TARGET_CLASS_CONSTANT` — именно эта цель покрывает enum-кейсы; без правильного target PHP бросит ошибку при `newInstance()`.
- Резолвер на каждый вызов делает reflection — для горячих путей (списки в таблицах) кешируйте результат статическим массивом `[$enumClass][$caseName][$attrClass]`.
- Дефолты в трейтах обязательны: не каждый кейс обязан нести каждый атрибут (см. кейс без Color).
- path-repository с `symlink: true` — правки пакета видны сразу, но в Docker симлинк должен попадать внутрь build-контекста.
- Версию локального пакета фиксируйте в его composer.json (`"version": "1.0.0"`), иначе constraint `^1.0` не зарезолвится.

## #[TypeScript] + экспорт типов на фронт

На одном enum уживаются два независимых слоя метаданных: доменные кастомные атрибуты на кейсах и атрибут экспорта типа на классе. Они не конфликтуют — живут на разных уровнях (константа vs класс) и обрабатываются разными механизмами.

1. **Стэк атрибутов**: на класс enum вешается `#[TypeScript]` (`Spatie\TypeScriptTransformer\Attributes\TypeScript`), на каждый кейс — доменные `#[Label('...')]`, `#[Priority(...)]`. Дополнительно enum может `implements HasLabel` (Filament) и `use HasLabelAttribute, EnumConcern`.
2. **Резолв метаданных на бэке**: concern `HasLabelAttribute::getLabel()` через `EnumCaseAttributeResolver::forCase($this, Label::class)` достаёт `#[Label]` на каждый case (reflection: `ReflectionEnum->getCase($name)->getAttributes(Label::class)->newInstance()`). Это бэкенд-сторона — `#[TypeScript]` к ней отношения не имеет.
3. **Экспорт на фронт**: `spatie/laravel-typescript-transformer`. В `config/typescript-transformer.php` — `DefaultCollector` собирает классы с `#[TypeScript]`, `EnumTransformer` превращает enum в union-тип, `auto_discover_types => [app_path()]`, `output_file => resource_path('types/generated.d.ts')`. Генерация: `php artisan typescript:transform`.
4. **Namespace на выходе**: путь PHP-класса проецируется в TS-namespace — `App\Enums\User\UserRole` → `App.Enums.User.UserRole`. При `transform_to_native_enums => false` (дефолт) получается union строковых литералов: `export type UserRole = 'admin' | 'secretary' | ...`.
5. **Граница экспорта**: `#[TypeScript]` отдаёт на фронт ТОЛЬКО backing-значения кейсов. Метки из `#[Label]` в `.d.ts` НЕ попадают — если в UI нужны человекочитаемые названия, отдавайте отдельную мапу значение→label через DTO/ресурс (тоже под `#[TypeScript]`) либо кастомный writer.
6. **Frontend-сторона потребления** (импорт `App.Enums.*`, синхронизация типов, разбиение на модули вместо одного `generated.d.ts`) — связанный скилл `frontend/backend-type-sync`. Здесь только бэкенд-источник типа.

## Чеклист качества

- [ ] `#[TypeScript]` на классе enum, доменные атрибуты — на кейсах; они не мешают друг другу
- [ ] config: `DefaultCollector` + `EnumTransformer`, `auto_discover_types` включает `app_path()`, задан `output_file`
- [ ] После правки enum прогнан `php artisan typescript:transform`, `generated.d.ts` пересобран
- [ ] Понятно, что на фронт уходят backing-значения, а не `#[Label]`; для меток — отдельная мапа/DTO
- [ ] Атрибуты — `final readonly`, target `TARGET_CLASS_CONSTANT`
- [ ] Резолвер один на проект, с generic-аннотациями для статанализа
- [ ] Каждый трейт возвращает осмысленный дефолт при отсутствии атрибута
- [ ] Enum не содержит match-дублирования меток — только атрибуты
- [ ] Локальный пакет: path-repo + symlink + версия в composer.json пакета

## Ссылки

- https://www.php.net/manual/en/language.attributes.php
- https://github.com/emreyarligan/enum-concern
- https://getcomposer.org/doc/05-repositories.md#path
- https://github.com/spatie/laravel-typescript-transformer
- `snippets/enum-typescript.php` — enum со стэком #[TypeScript]+#[Label], Label-атрибут и concern, фрагмент config
- Связанные скиллы: `frontend/backend-type-sync` (потребление App.Enums.* на фронте), `php/filament`
