---
name: laravel-data
bucket: php
version: 0.1.0
description: "DTO на spatie/laravel-data: типизированные Data-классы, вложенные DataCollection, casts/transformers, computed-свойства, mapName/mapInputName, создание from(request) с валидацией, отдача в API/Inertia и аннотация #[TypeScript]. Активировать: нужен типобезопасный DTO вместо массива/array-доступа, разбор входящего запроса в объект, единая форма данных между бэком и фронтом, замена ad-hoc JsonResource на Data."
risk: write
persona: oss-dev
tags: [laravel, spatie, laravel-data, dto, data-transfer-object, casts, validation, inertia, api]
requires: []
produces_for: [backend-type-sync]
outputs: []
snippets: [OrderData.php, from-request-usage.php]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: spatie/laravel-data DTO

## Контекст

`spatie/laravel-data` — типизированный слой данных, который заменяет ассоциативные массивы, `$request->input()` и ad-hoc `JsonResource` единым объектом. Один Data-класс одновременно: разбирает входящий запрос (с валидацией), описывает форму данных типизированными свойствами, сериализуется в API/Inertia и экспортируется в TypeScript-тип. Без него каждый слой (контроллер, сервис, ресурс, фронт) держит свою копию структуры, и при первой правке поля возникает молчаливый рассинхрон.

**Активировать, когда:**
- вместо передачи массива `['title' => ..., 'items' => [...]]` между слоями нужен типобезопасный объект с автодополнением;
- входящий запрос надо превратить в объект с валидацией (`OrderData::from($request)` вместо ручного `$request->validate()` + сборки массива);
- одна структура нужна и на бэке, и на фронте (Data → `#[TypeScript]` → `App.Data.*`, см. `frontend/backend-type-sync`);
- старый `JsonResource` оброс ручными хелперами рендера связей/enum/дат — это сигнал перейти на Data, где связи и касты декларативны;
- нужна вложенная коллекция дочерних DTO (заказ → позиции, документ → строки) с типизацией каждого элемента.

**Laravel Boost** даёт версионные основы `spatie/laravel-data` как upstream-скилл (`vendor/laravel/boost/.ai/`); здесь — авторский паттерн поверх них: вложенные DataCollection, направление каст/трансформер, дисциплина «Data ≠ God-object» и подготовка класса к TS-экспорту. Версионный API пакета — за Boost, эти конвенции — за этим скиллом. Пакет: https://github.com/laravel/boost.

## Алгоритм

1. **Базовый Data-класс**: наследуй `Spatie\LaravelData\Data`, объявляй свойства через **promoted constructor properties** — типизированные, с `?` для nullable. Тип свойства = контракт; никаких «голых» `array` там, где структура известна.

   ```php
   class OrderData extends Data
   {
       public function __construct(
           public string $reference,
           public OrderStatus $status,       // enum кастуется автоматически
           public ?CustomerData $customer,   // вложенный Data
       ) {}
   }
   ```

2. **Вложенные DTO и коллекции**: одиночный дочерний объект — просто тип-свойство (`?CustomerData $customer`). Список дочерних элементов — `DataCollection` с указанием типа элемента через `#[DataCollectionOf(ItemData::class)]` (или PHPDoc-аннотацию `@var DataCollection<ItemData>`):

   ```php
   /** @var DataCollection<ItemData> */
   #[DataCollectionOf(ItemData::class)]
   public DataCollection $items,
   ```
   Тип элемента обязателен — иначе пакет не знает, во что разворачивать массив, и теряет типизацию/TS-экспорт.

3. **Касты (входные преобразования)**: для типов, которые не кастуются «из коробки», вешай `#[WithCast(...)]` на свойство. Дата — `DateTimeInterfaceCast`, enum — `EnumCast` (обычно автоматом по типу), кастомное правило — свой класс, реализующий `Cast`. Каст применяется при `from()` (вход), трансформер — при `toArray()` (выход).

4. **Трансформеры (выходные преобразования)**: для нестандартной сериализации свойства вешай `#[WithTransformer(...)]` (формат даты, денежная сумма, обрезка). Глобальные правила (например формат всех `DateTimeInterface`) задаются в `config/data.php`, точечные — атрибутом на свойстве.

5. **Computed-свойства**: значение, вычисляемое из других полей и попадающее в выход, объяви как `public` свойство и пометь `#[Computed]`, инициализируя его в конструкторе телом метода или через отдельный геттер. `#[Computed]`-свойство **не** ожидается во входных данных, но присутствует в `toArray()` и в TS-типе (`total`, `is_overdue`, `display_name`).

6. **Маппинг имён**: расхождение имён свойств и ключей данных решается атрибутами, а не переименованием:
   - `#[MapInputName('snake_case')]` — как ключ называется во **входе** (`from()`);
   - `#[MapOutputName(...)]` — как называется в **выходе** (`toArray()`);
   - `#[MapName(...)]` — обе стороны сразу.
   Классовый атрибут `#[MapName(SnakeCaseMapper::class)]` (или `MapInputName`) задаёт стратегию для всех свойств класса — типично «camelCase в PHP ↔ snake_case в JSON».

7. **Создание из запроса с валидацией**: `OrderData::from($request)` — пакет сам собирает правила валидации из типов и атрибутов свойств (`#[Required]`, `#[Max]`, `#[Rule]`, и т.п.), валидирует вход и бросает `ValidationException` при ошибке. Не дублируй `$request->validate()` — правила живут на свойствах Data. `from()` принимает что угодно: `Request`, массив, модель, другой Data — пакет нормализует источник.

8. **Отдача в API / Inertia**:
   - вернул Data из контроллера → Laravel сериализует через `toArray()`/`toResponse()`;
   - Inertia: `Inertia::render('Order/Show', ['order' => OrderData::from($order)])` — фронт получает ровно ту форму, что описана в Data;
   - частичная отдача/ленивые поля — `Lazy::create(...)` для тяжёлых вложенных коллекций (грузятся только при запросе).

9. **Синхронизация типов с фронтом**: пометь Data-класс `#[TypeScript]` (из `spatie/typescript-transformer`), чтобы он попал в `generated.d.ts` как `App.Data.OrderData`. Дальнейшее (`artisan typescript:transform`, импорт на фронте) — скилл `frontend/backend-type-sync`; этот скилл лишь корректно объявляет Data, пригодный для экспорта (явные типы, типизированные коллекции, без «сырых» `array`).

10. **Не превращай Data в God-object**: Data описывает форму данных и преобразования вход/выход. Бизнес-логику (изменение состояния, запись в БД, побочные эффекты) держи в сервисах/действиях, которые принимают и возвращают Data. Контроллер: `from(request)` → передать в сервис → вернуть Data.

## Касты vs трансформеры (направление)

| Что | Атрибут | Когда срабатывает | Пример |
|:---|:---|:---|:---|
| Каст | `#[WithCast(...)]` | вход, при `from()` | строка `"2026-01-31"` → `CarbonImmutable` |
| Трансформер | `#[WithTransformer(...)]` | выход, при `toArray()` | `CarbonImmutable` → `"2026-01-31T00:00:00Z"` |
| Каст+трансформер | `#[WithCastAndTransformer(...)]` | обе стороны | единое правило money/enum |
| Computed | `#[Computed]` | только выход (вычисляется) | `total`, `is_overdue` |

Глобально (для всех свойств данного типа) — в `config/data.php`; точечно — атрибутом на свойстве.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Объявить Data-класс: вложенная `DataCollection`, каст, трансформер, `#[Computed]`, маппинг имён, `#[TypeScript]` | `snippets/OrderData.php` |
| Создать DTO из запроса с валидацией и отдать в API/Inertia; `toArray()` | `snippets/from-request-usage.php` |

## Чеклист качества

- [ ] Свойства типизированы (promoted constructor properties), nullable помечены `?`; нет «сырых» `array` там, где структура известна
- [ ] Вложенный список — `DataCollection` с обязательным типом элемента (`#[DataCollectionOf(...)]` или `@var DataCollection<...>`)
- [ ] Нестандартный вход кастуется `#[WithCast(...)]`, нестандартный выход — `#[WithTransformer(...)]`; направление не перепутано
- [ ] Вычисляемые поля — `#[Computed]`, а не дублирование логики в контроллере/ресурсе
- [ ] Расхождение имён решено `MapName`/`MapInputName`/`MapOutputName` (или классовым маппером), а не переименованием свойств
- [ ] Вход создаётся через `from()`, валидация — на свойствах Data, без дублирующего `$request->validate()`
- [ ] Бизнес-логика не утекла в Data: состояние меняют сервисы/действия, Data описывает только форму и преобразования
- [ ] Если тип нужен на фронте — класс помечен `#[TypeScript]` (дальше см. `frontend/backend-type-sync`)
- [ ] Домены/неймспейсы нейтральны (`App\Data\...`), без бизнес-терминов конкретного проекта

## Ссылки

- https://spatie.be/docs/laravel-data
- https://spatie.be/docs/laravel-data/advanced-usage/typescript
- Связанные скиллы: `frontend/backend-type-sync` (Data → TS-типы), `php/enum-attributes` (enum в свойствах Data), `php/named-arguments` (создание Data явными именованными аргументами)
