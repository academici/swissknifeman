---
name: enum-attributes
bucket: php
version: 0.1.0
description: "Метаданные enum-кейсов через PHP-атрибуты (#[Label], #[Color], #[Description]) + Concern-трейты с reflection-резолвером"
risk: write
persona: oss-dev
tags: ["php", "enum", "attributes", "reflection", "laravel", "patterns"]
requires: []
produces_for: []
outputs: []
snippets:
  - attribute.php
  - concern-trait.php
  - enum-example.php
  - composer-path-repo.json
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Декларативные метаданные enum-кейсов: вместо `match`-простыней `label()`/`color()` на 20 кейсов — PHP-атрибуты `#[Label('...')]`, `#[Color('...')]`, `#[Description('...')]` прямо над кейсом + Concern-трейты, дающие методы `getLabel()`/`getColor()`. Чтение — через единый reflection-резолвер. Коллекционные операции (all/values/labels) — пакет `emreyarligan/enum-concern`, подключаемый как локальный path-repository.

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

## Типичные грабли

- `Attribute::TARGET_CLASS_CONSTANT` — именно эта цель покрывает enum-кейсы; без правильного target PHP бросит ошибку при `newInstance()`.
- Резолвер на каждый вызов делает reflection — для горячих путей (списки в таблицах) кешируйте результат статическим массивом `[$enumClass][$caseName][$attrClass]`.
- Дефолты в трейтах обязательны: не каждый кейс обязан нести каждый атрибут (см. кейс без Color).
- path-repository с `symlink: true` — правки пакета видны сразу, но в Docker симлинк должен попадать внутрь build-контекста.
- Версию локального пакета фиксируйте в его composer.json (`"version": "1.0.0"`), иначе constraint `^1.0` не зарезолвится.

## Чеклист качества

- [ ] Атрибуты — `final readonly`, target `TARGET_CLASS_CONSTANT`
- [ ] Резолвер один на проект, с generic-аннотациями для статанализа
- [ ] Каждый трейт возвращает осмысленный дефолт при отсутствии атрибута
- [ ] Enum не содержит match-дублирования меток — только атрибуты
- [ ] Локальный пакет: path-repo + symlink + версия в composer.json пакета

## Ссылки

- https://www.php.net/manual/en/language.attributes.php
- https://github.com/emreyarligan/enum-concern
- https://getcomposer.org/doc/05-repositories.md#path
