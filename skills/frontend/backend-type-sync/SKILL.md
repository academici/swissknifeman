---
name: backend-type-sync
bucket: frontend
version: 0.1.0
description: "Синхронизация типов backend→frontend через spatie/laravel-typescript-transformer: #[TypeScript] на enum/DTO/Spatie-Data, php artisan typescript:transform → generated.d.ts, использование App.Enums.* / App.Data.* в Vue/TS. Активировать: новый enum/DTO нужен на фронте, рассинхрон типов фронта с бэком, настройка type-sync. Граница с wayfinder (роуты ≠ типы)."
risk: write
persona: oss-dev
tags: [typescript, laravel, spatie, types, enum, dto, frontend, type-sync]
requires: [wayfinder]
produces_for: []
outputs: []
snippets: [typescript-transformer.php, annotated-enum.php, generated-type-usage.vue]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Backend → Frontend type sync

## Контекст

Один источник правды для типов: PHP-классы на бэке (enum, DTO, Spatie-Data) автоматически превращаются в TypeScript-декларации, которые фронт импортирует как `App.Enums.*` и `App.Data.*`. Пакет — `spatie/laravel-typescript-transformer`. Без этого фронт руками копирует поля DTO и значения enum, и при первой же правке на бэке возникает молчаливый рассинхрон.

**Активировать, когда:**
- на фронте нужен новый enum или DTO, уже существующий в PHP (не дублируй типы руками — аннотируй и генерируй);
- фронт «не знает» про новое поле/case, типы фронта разошлись с бэком (рассинхрон);
- настраиваешь type-sync в проекте с нуля (установка, config, npm-скрипт, git-hook, CI).

**Границы (важно, чтобы не лезть в чужой скилл):**
- **Типы (этот скилл)** — структура данных: поля DTO, значения enum. Артефакт: `resources/js/types/generated.d.ts`, неймспейс `App.*`.
- **Роуты (`frontend/wayfinder`)** — типобезопасные URL и controller-actions. Артефакт: `resources/js/wayfinder/`. Это **отдельная** генерация (`php artisan wayfinder:generate`) и отдельный пакет (`laravel/wayfinder`). Эти два пакета — пара: wayfinder типизирует «куда ходить», typescript-transformer — «какие данные приходят/уходят». Не пытайся получить типы DTO из wayfinder и наоборот.
- **PHP-сторона enum (`php/enum-attributes`)** — как устроен сам enum: backed-значения, атрибуты `#[Label]`/`#[Priority]`, методы. Этот скилл только добавляет `#[TypeScript]` поверх готового enum и не диктует его внутреннее устройство.

**Laravel Boost** даёт версионные основы Spatie-Data/transformer как upstream-скиллы; здесь — проектные конвенции type-sync, git-hook и CI-проверка. Пакет: https://github.com/laravel/boost.

## Алгоритм

1. **Проверь установку.** В `composer.json` должна быть `spatie/laravel-typescript-transformer` (для DTO/Spatie-Data также `spatie/laravel-data`). Если нет:
   ```
   composer require spatie/laravel-typescript-transformer
   php artisan vendor:publish --provider="Spatie\LaravelTypeScriptTransformer\TypeScriptTransformerServiceProvider"
   ```
   Это создаёт `config/typescript-transformer.php`.

2. **Настрой `config/typescript-transformer.php`** (см. `snippets/typescript-transformer.php`). Ключевое:
   - `auto_discover_types` — пути сканирования (по умолчанию `app_path()`); **неймспейс PHP-класса задаёт неймспейс TS** (`App\Enums\Order\OrderStatus` → `App.Enums.Order.OrderStatus`);
   - `collectors` — `DefaultCollector` ловит классы с атрибутом `#[TypeScript]`;
   - `transformers` — включи нужные: `EnumTransformer` (PHP-enum), `SpatieEnumTransformer`, `DtoTransformer` (Spatie-Data), `SpatieStateTransformer` (при использовании States);
   - `default_type_replacements` — отдай `Carbon`/`DateTimeImmutable` как `string` (на проводе они JSON-строки), иначе на фронте получишь нечитаемый тип;
   - `output_file` — единый файл `resource_path('types/generated.d.ts')`;
   - `transform_to_native_enums` — `false` (тип-объединение) по умолчанию; `true` если фронту нужны рантайм-значения как `enum`;
   - `transform_null_to_optional` — `false` (`null` в union) либо `true` (поле опциональное `?`), выбери одно и держи единообразно.

3. **Аннотируй PHP-класс** атрибутом `#[TypeScript]` (см. `snippets/annotated-enum.php`):
   - **enum** (backed) — даёт `App.Enums.*`;
   - **Spatie-Data DTO** (`extends Spatie\LaravelData\Data`) — даёт `App.Data.*` (или `App.Dto.*` — зависит от неймспейса класса, не от пакета);
   - типизируй массивы коллекций через PHPDoc `@param Foo[] $items` / `@var Foo[]` — без этого `array` превратится в `any[]`;
   - вложенные DTO/enum в полях должны быть **тоже** аннотированы, иначе сгенерируется `any`.

4. **Сгенерируй типы:**
   ```
   php artisan typescript:transform
   ```
   Запиши это в `composer.json` (`"typescript:transform"`) и продублируй npm-скриптом в `package.json` (`"types": "php artisan typescript:transform"`), чтобы фронтендеры звали привычным `npm run`. После генерации проверь diff `generated.d.ts`.

5. **Используй на фронте** через глобальный неймспейс `App.*` (см. `snippets/generated-type-usage.vue`):
   - enum-значения: `App.Enums.Order.OrderStatus` как тип, литералы — обычные строки (`'paid'`), TS проверит принадлежность;
   - DTO как пропсы/реактивные данные: `defineProps<{ item: App.Data.Order.OrderListItem }>()`;
   - `generated.d.ts` подключается как `declare namespace App` — он глобален, **импорт не нужен**; убедись, что файл входит в `include` твоего `tsconfig.json`.

6. **Защити от рассинхрона** — генерация не должна быть «вручную по памяти»:
   - **git pre-commit hook** (Husky или нативный) — регенерирует и падает, если `generated.d.ts` изменился, но не закоммичен (см. секцию «Git-hook»);
   - **CI** — отдельный шаг `php artisan typescript:transform` + `git diff --exit-code resources/js/types/generated.d.ts`: PR краснеет, если автор забыл перегенерировать.

7. **Коммить сгенерированный файл.** `generated.d.ts` **коммитится в репозиторий** (не в `.gitignore`): он нужен для `tsc`/IDE/CI без запуска PHP, а diff в ревью показывает изменение контракта backend↔frontend. Vendor-артефакты wayfinder (`resources/js/wayfinder/`) — по той же логике коммить, но это зона скилла `frontend/wayfinder`.

## Аннотируемые цели

| Что аннотируем `#[TypeScript]` | Базовый класс | TS-неймспейс | Что даёт |
|:---|:---|:---|:---|
| PHP backed-enum | `enum X: string` | `App.Enums.*` | union строк/чисел или native enum |
| Spatie-Data DTO | `extends Spatie\LaravelData\Data` | `App.Data.*` / `App.Dto.*` | объектный тип с полями |
| Spatie-Enum (если используется пакет) | `Spatie\Enum\Enum` | `App.Enums.*` | через `SpatieEnumTransformer` |

Неймспейс TS = неймспейс PHP-класса под `auto_discover_types`. Хочешь `App.Data.*` — клади DTO в `App\Data\...`; видишь `App.Dto.*` — значит классы лежат в `App\Dto\...`. Пакет на это не влияет.

## Git-hook (защита от рассинхрона)

Husky-хук `.husky/pre-commit` (проект уже использует Husky):
```sh
php artisan typescript:transform
if ! git diff --quiet -- resources/js/types/generated.d.ts; then
  git add resources/js/types/generated.d.ts
  echo "types/generated.d.ts перегенерирован и добавлен в коммит"
fi
```
Вариант для CI (строгий, без авто-`add` — только проверка):
```sh
php artisan typescript:transform
git diff --exit-code -- resources/js/types/generated.d.ts \
  || { echo "generated.d.ts устарел: запусти 'npm run types' и закоммить"; exit 1; }
```

## Чеклист качества

- [ ] `spatie/laravel-typescript-transformer` в `composer.json`, `config/typescript-transformer.php` опубликован
- [ ] Нужные `transformers` включены (Enum/SpatieEnum/Dto/State — по факту использования)
- [ ] `default_type_replacements` отдаёт `Carbon`/datetime как `string`
- [ ] `output_file` — единый `resources/js/types/generated.d.ts`, файл в `include` `tsconfig.json`
- [ ] PHP-класс помечен `#[TypeScript]`; вложенные DTO/enum в полях — тоже помечены
- [ ] Коллекции типизированы PHPDoc (`@var Foo[]`), нет случайного `any[]`
- [ ] `typescript:transform` есть и в `composer.json`, и в `package.json` (npm-скрипт)
- [ ] Фронт использует `App.Enums.*` / `App.Data.*`, типы DTO **не** продублированы руками
- [ ] git pre-commit hook ИЛИ CI-шаг ловит устаревший `generated.d.ts` (`git diff --exit-code`)
- [ ] `generated.d.ts` закоммичен в репозиторий (не в `.gitignore`)
- [ ] Не перепутаны зоны: роуты — `frontend/wayfinder`, устройство enum — `php/enum-attributes`

## Ссылки

- snippets/typescript-transformer.php — конфиг transformer (collectors, transformers, replacements, output_file)
- snippets/annotated-enum.php — enum и Spatie-Data DTO с `#[TypeScript]`, типизация коллекций
- snippets/generated-type-usage.vue — использование `App.Enums.*` / `App.Data.*` в Vue/TS
- https://spatie.be/docs/typescript-transformer
- https://spatie.be/docs/laravel-data
- Связанные скиллы: `frontend/wayfinder` (роуты), `php/enum-attributes` (устройство enum), `frontend/inertia-vue` (слой types/)
