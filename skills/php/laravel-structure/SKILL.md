---
name: laravel-structure
bucket: php
version: 0.1.0
description: "Канон структуры Laravel-проекта: доменная таксономия, правило зеркала слоёв, размещение и нейминг классов"
risk: write
persona: oss-dev
tags: ["php", "laravel", "architecture", "structure"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Laravel Structure

## Контекст

Флагманский скилл-канон: как формировать основу Laravel-проекта — папки, имена, размещение классов. Новый проект начинается со структуры; скиллы реализации (actions, repositories, DTO, Filament) опираются на этот канон и отвечают «как написать класс», этот скилл отвечает «куда его положить и как назвать». Применяй при старте проекта, добавлении домена/подпроцесса и в ревью размещения файлов.

## Принципы

1. **Две оси организации.** Доменная ось для бизнес-кода: в `Actions/`, `Models/`, `Enums/`, `Dto/`, `Events/`, `Exceptions/`, `Policies/`, `Repositories/`, `Services/`, `Http/{Controllers,Requests,Resources}/`, `Filament/Resources/`, `Notifications/`, `Observers/`, `Listeners/`, `Jobs/` — везде доменные подпапки (`Order/`, `Document/`, `User/`). Техническая ось для инфраструктуры: `Concerns/<Tech>`, `Attributes/Common`, `Support/<Tech>`, `Utils/`, `TypeScript/`, `MediaLibrary/`, `Health/`, `Services/<Tech>` (Broadcast/Log/Layout). Техническая ось не знает о доменах.
2. **Правило зеркала.** Одна таксономия доменов во всех слоях: `Models/Order` ↔ `Enums/Order` ↔ `Policies/Order` ↔ `Repositories/Order` ↔ `factories/Order` ↔ `tests/Feature/Order`. Подпроцессы (`Common/`, `Review/`, `Application/`) — одинаковые подпапки в `Actions/`, `Dto/Actions/`, `Enums/<Домен>/Permissions/`, `Policies/<Домен>/`.
3. **Без уровня потребителя.** НЕ `Enums/Models/<Домен>` — у enum много потребителей, домен стабилен. Исключение — правило одного потребителя: `Dto/Actions/<Домен>` зеркалит `Actions/<Домен>` (Command DTO имеет ровно одного потребителя — свой Action); Mapper живёт рядом с View DTO.
4. **Рост — внутрь домена.** Смысловые подпапки внутри домена (`Enums/Order/Workflow/`, `Enums/Order/Permissions/`, `Services/Order/Access/`, `Services/Order/Store/`), а не новые корневые оси. Пустых папок «на вырост» не держим.

## Куда класть новый класс

| Что создаю | Куда | Пример |
|---|---|---|
| Модель | `app/Models/<Домен>/` | `Models/Order/Order.php` |
| Enum-статус / код события | `app/Enums/<Домен>/` | `Enums/Order/OrderStatus.php` |
| Права домена (permission-enum) | `app/Enums/<Домен>/Permissions/` | `Enums/Order/Permissions/CommonPermission.php` |
| Use-case (Action) | `app/Actions/<Домен>/<Подпроцесс>/` | `Actions/Order/Common/StoreAction.php` |
| Command DTO | `app/Dto/Actions/<Домен>/<Подпроцесс>/` | `Dto/Actions/Order/Common/StoreCommand.php` |
| View DTO | `app/Dto/<Домен>/View/` | `Dto/Order/View/ListItemView.php` |
| Маппер DTO | `app/Dto/<Домен>/Mapper/` | `Dto/Order/Mapper/ViewMapper.php` |
| Form DTO | `app/Dto/<Домен>/Form/` | `Dto/Order/Form/Form.php` |
| Сервис доменный | `app/Services/<Домен>/[<Аспект>/]` | `Services/Order/Access/OrderAccessEvaluator.php` |
| Сервис инфраструктурный | `app/Services/<Tech>/` | `Services/Broadcast/ChannelManager.php` |
| Репозиторий чтения | `app/Repositories/<Домен>/` | `Repositories/Order/OrderReadRepository.php` |
| Репозиторий записи | `app/Repositories/<Домен>/` | `Repositories/Order/OrderStoreRepository.php` |
| Политика | `app/Policies/<Домен>/` | `Policies/Order/CommonPolicy.php` |
| Событие | `app/Events/<Домен>/` | `Events/Order/StatusChanged.php` |
| Слушатель | `app/Listeners/<Домен>/[<Назначение>/]` | `Listeners/Order/Notifications/SendStatusChanged.php` |
| Исключение | `app/Exceptions/<Домен>/` | `Exceptions/Order/OrderAccessException.php` |
| Job | `app/Jobs/<Домен>/` | `Jobs/User/SyncProfileJob.php` |
| Нотификация | `app/Notifications/<Домен>/` | `Notifications/Order/Notification.php` |
| Observer | `app/Observers/<Домен>/` | `Observers/Order/Observer.php` |
| Filament-ресурс | `app/Filament/Resources/<Домен>/<Models>/` | `Filament/Resources/Order/Orders/OrderResource.php` |
| Трейт-примесь | `app/Concerns/<Tech>/` | `Concerns/Enums/HasLabelAttribute.php` |
| PHP-атрибут | `app/Attributes/Common/` или `Attributes/<Домен>/` | `Attributes/Common/Label.php` |
| Хелпер статичный | `app/Support/<Tech>/` или `app/Utils/` | `Support/Enums/EnumCaseAttributeResolver.php` |
| UI-DTO оболочки страницы | `app/Dto/Layout/View/` (псевдодомен UI) | `Dto/Layout/View/SharedPageProps.php` |
| Фабрика | `database/factories/<Домен>/` | `factories/Order/OrderFactory.php` |
| Сидер | `database/seeders/` (префикс = домен) | `seeders/OrderSeeder.php` |
| Feature-тест | `tests/Feature/<Домен>/` | `Feature/Order/StoreOrderTest.php` |
| Unit-тест | `tests/Unit/<Домен>/` | `Unit/Order/WorkflowServiceTest.php` |

## Нейминг

| Тип | Шаблон | Пример |
|---|---|---|
| Action | `VerbNounAction` | `StoreAction`, `TakeInWorkAction` |
| Command DTO | `VerbNounCommand` | `StoreCommand`, `ReplyCommand` |
| View DTO | `XxxView` | `ListItemView`, `DetailExtraView` |
| Form DTO | `Form` (+ части) | `Form`, `Items` |
| Service | `XxxService` / `XxxEvaluator` | `WorkflowService`, `OrderAccessEvaluator` |
| Repository | `XxxReadRepository` / `XxxStoreRepository` | `OrderReadRepository`, `OrderStoreRepository` |
| Policy | `<Подпроцесс>Policy`, методы `canXxx` | `CommonPolicy::canEdit` |
| Exception | `XxxException` | `OrderAccessException` |
| Event | прошедшее время, без префикса домена | `StatusChanged`, `Created` |
| Concern | `HasXxx` | `HasLabelAttribute` |

## Когда какой reference открывать

| Ситуация | Файл |
|---|---|
| Полное дерево `app/`, правила и ошибки по каждой папке, Filament-канон | `references/app-structure.md` |
| Принцип «домен → слой», подпроцессы, запреты, рост домена | `references/domain-structure.md` |
| Все файлы одной сущности по слоям, зеркало `database/` и `tests/`, чеклисты «новый домен» / «новый подпроцесс» | `references/mirroring.md` |
| Куда выносить общий код: scope → Concern → атрибут → Support → Utils → DTO → пакет | `references/shared-code.md` |

## Чеклист качества

- [ ] Новый класс лежит по таблице размещения; имя — по таблице нейминга
- [ ] Доменная таксономия зеркальна: тот же домен в `Models/`, `Enums/`, `Policies/`, `factories/`, `tests/`
- [ ] Нет уровня потребителя (`Enums/Models/...`) — кроме `Dto/Actions/`
- [ ] Техническая ось (`Concerns/`, `Support/`, `Utils/`) не упоминает домены
- [ ] Нет пустых папок и файлов в плоских корнях (`app/Models/X.php`, `app/Exceptions/XException.php`)
- [ ] Подпроцесс добавлен синхронно в `Actions/`, `Dto/Actions/`, `Enums/Permissions/`, `Policies/`

## Смежные скиллы

- Реализация Action/DTO/слоёв: `php/laravel` → `snippets/layer-boundaries.md`, `snippets/dto.md`, `snippets/actions.md`
- Репозитории Read/Store: `php/repositories`
- Внедрение зависимостей и связывание: `php/dependency-injection`
- Атрибуты, Concern-трейты, резолвер, локальный пакет: `php/enum-attributes`
- Общие правила архитектуры: `php/laravel-best-practices` → `references/architecture.md`
