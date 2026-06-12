---
name: repositories
bucket: php
version: 0.1.0
description: "Система репозиториев Laravel: read/store split, model scopes, delta-DTO, фасад, VisibilityService"
risk: write
persona: oss-dev
tags: ["php", "laravel", "repository", "architecture"]
requires: []
produces_for: []
outputs: []
snippets: ["read-repository.php", "store-repository.php", "member-store-repository.php", "members-delta.php", "repository-facade.php", "model-scopes.php", "visibility-service.php"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Репозитории в Laravel: read/store split

## Контекст

Eloquent сам по себе — уже repository + active record, поэтому «репозиторий ради репозитория» (обёртка над `find`/`create`) — антипаттерн. Слой репозиториев оправдан, когда:

- **повторяемые выборки**: один и тот же запрос «документы пользователя со статусом X и связями для списка» нужен в контроллере, Livewire-компоненте и команде — без репозитория where-цепочки расползаются и расходятся;
- **изоляция write-side**: мутации с нетривиальной механикой (sync пивотов, нормализация пар, updateOrCreate с приоритетами) не должны жить в Action — Action описывает бизнес-сценарий, репозиторий — работу со строками;
- **тестируемость**: Action тестируется с замоканным репозиторием; запросная логика тестируется отдельно интеграционно;
- **видимость данных**: фильтрация по правам должна быть невозможной для забывания — единая точка входа `queryForUser()` это гарантирует.

Канон — **CQRS-облегчённый split** в `app/Repositories/<Домен>/`:

| Класс | Сторона | Отвечает за |
|---|---|---|
| `XxxReadRepository` | read | запросы, фильтры, пагинация, eager load |
| `XxxStoreRepository` | write | мутации, sync-операции |
| `Repository` (фасад) | read | делегирование, единая точка для контроллеров (опционален) |

## Алгоритм

1. **Определи сторону.** Выборка → `XxxReadRepository`; мутация → `XxxStoreRepository`. Не смешивай в одном классе.
2. **Read-side: начни с видимости.** Каждый публичный read-метод строится поверх `queryForUser(?User $user, bool $ignorePermissions = false)`, который делегирует в `XxxVisibilityService::apply()`. Сигнатура явно сообщает потребителю, что выборка фильтруется по правам.
3. **Вынеси повторяемые предикаты в model scopes** с доменными именами (`withStatus`, `withListRelations`, `forUser`). Репозиторий их КОМПОНУЕТ — если пишешь вторую одинаковую where-цепочку, это сигнал создать scope.
4. **Выбери возвращаемый тип:**
   - `Builder` — когда потребитель докомпонует запрос (счётчики, секции, доп. фильтры);
   - `Model` / `Collection` / `Paginator` — когда запрос терминальный;
   - **delta-DTO** (`added`/`removed`) — для sync-операций write-side: Action узнаёт, кого уведомлять, не перечитывая базу.
5. **Write-side принимает DTO-команды** (`Form`), не массивы и не `Request`. `persistFromForm(Form $form, User $user): Model` — типовая точка входа.
6. **Не открывай транзакций** в репозитории: `DB::transaction()` принадлежит Action, репозиторий работает внутри неё. Несколько вызовов store-репозиториев в одном Action атомарны автоматически.
7. **Фасад добавляй по необходимости:** когда read-методов стало много и контроллеры инжектят репозиторий повсеместно — заведи `Repository` с чистым делегированием. При 2-3 методах — инжекти read-репозиторий напрямую.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Новая выборка/список/поиск, нужна фильтрация по правам | `snippets/read-repository.php` |
| Создание/обновление модели по DTO-форме, sync отношения | `snippets/store-repository.php` |
| Sync участников/ролей, Action должен узнать кто добавлен/удалён | `snippets/member-store-repository.php` |
| Нужен тип результата sync-операции | `snippets/members-delta.php` |
| Read-методов много, контроллерам нужна единая точка | `snippets/repository-facade.php` |
| Where-цепочка повторяется второй раз | `snippets/model-scopes.php` |
| Правила «кто какие записи видит» (роли, статусы, владение) | `snippets/visibility-service.php` |

## Чеклист качества

- [ ] Read и store разделены: в `ReadRepository` нет мутаций, в `StoreRepository` нет выборок-для-отображения.
- [ ] Каждый публичный read-метод проходит через `queryForUser()`; обход прав — только явным `ignorePermissions: true`.
- [ ] Репозиторий **НЕ открывает транзакций** — работает внутри транзакции Action.
- [ ] Репозиторий **НЕ пишет историю и НЕ диспатчит события**. Типичная ошибка: `recordHistory()` внутри `persistFromForm()` — это утечка бизнес-логики; история и события принадлежат Action/StateMachine.
- [ ] Репозиторий **НЕ принимает `Request`** — только DTO-команды (write) и скаляры/енумы/модели (read).
- [ ] Репозиторий **НЕ принимает авторизационных решений** — видимость только через инжектируемый `VisibilityService` с явной сигнатурой `apply(Builder, ?User, bool $ignorePermissions): Builder`.
- [ ] Повторяемые предикаты вынесены в model scopes с доменными именами; репозиторий не дублирует where-цепочки.
- [ ] Sync-операции идемпотентны (updateOrCreate + удаление выпавших) и возвращают delta-DTO, а не `void`/`bool`.
- [ ] «Не найдено» и «нет доступа» неразличимы для потребителя (`findByIdOrFail` ищет поверх `queryForUser`).
- [ ] Фасад — чистое делегирование, без логики; классы `final`, store-репозитории `final readonly`.
- [ ] Delta-DTO — `final readonly`, лежит в `app/Dto/<Домен>/Repository/`.

## Ссылки

- `php/laravel-structure` — размещение слоёв (`app/Repositories/<Домен>/`, `app/Dto/<Домен>/Repository/`, `app/Services/<Домен>/Access/`).
- `php/dependency-injection` — кто кого инжектит: VisibilityService → ReadRepository → Repository(фасад) → контроллер; StoreRepository → Action.
- `php/laravel` → `layer-boundaries.md` — границы слоёв: что разрешено Action, что репозиторию, что модели.
