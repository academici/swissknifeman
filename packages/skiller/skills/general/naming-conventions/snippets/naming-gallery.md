# Галерея именования: плохо → хорошо (кросс-языково)

Готовая таблица для ревью или вставки в `CLAUDE.md`/`AGENTS.md`. Принцип один:
**имя раскрывает намерение, а не реализацию и не тип.**

## Функции и методы

| Плохо | Хорошо | Почему |
|:--|:--|:--|
| `handleData(d)` | `parseInvoice(raw)` | глагол + что именно |
| `processX()` / `doStuff()` | `chargeCard()`, `rebuildIndex()` | конкретное действие |
| `getDataFromDbAndCache()` | `loadUser(id)` | реализация (db+cache) не в имени |
| `getUserById(id)` | `user(id)` / `findUser(id)` | аргумент уже говорит «by id» |
| `getAllActiveUsersList()` | `activeUsers()` | без `getAll…List` шума |
| `findByCodeOrFail`, `findByEmailOrFail`, … | `find(criteria)` / `activeBySlug(slug)` | не метод-на-поле |
| `checkUser()` (а внутри мутация) | запрос `isEligible()` + команда `activate()` | CQS: имя не врёт про эффект |

## Классы и типы

| Плохо | Хорошо | Почему |
|:--|:--|:--|
| `UserManager` | `UserRepository` / `UserRegistrar` | роль, а не «менеджер» |
| `OrderHelper`, `StringUtils` | `OrderTotals`, `Slugifier` | свалка → конкретная ответственность |
| `DataProcessor` | `CsvImporter`, `PaymentSettler` | что обрабатывает и зачем |
| `OrderObject`, `OrderClass`, `OrderData2` | `Order` | суффикс типа — шум |
| `IUserRepository` (венгерский) | `UserRepository` | без префикса-кодировки типа |

## Переменные и поля

| Плохо | Хорошо | Почему |
|:--|:--|:--|
| `data`, `info`, `obj`, `item` | `invoice`, `recipient`, `row` | по содержимому |
| `tmp`, `temp`, `val`, `res`, `arr` | `parsed`, `dueDate`, `pendingIds` | искабельно, осмысленно |
| `list`, `users2`, `arr3` | `recipients`, `incomingUser` | разведи по смыслу |
| `flag`, `status` (для bool) | `isPublished`, `hasAccess` | булево — вопрос |
| `strName`, `iCount`, `bOk` | `name`, `count`, `accepted` | без венгерской нотации |

## Булевы

`is*` / `has*` / `can*` / `should*` / `needs*`:
`isActive`, `hasInvoice`, `canEdit`, `shouldRetry`, `needsReview`.

## Коллекции

Множественное число для коллекций (`users`, `orderIds`); единственное — для элемента (`user`).
Не `userList`/`userArray` — тип хранилища не в имени.

## Тесты

Имя теста = условие + ожидание:
`it_archives_paid_orders_after_30_days`, а не `test1`, `testOrders`, `itWorks`.

## Симметрия

`open`/`close` · `begin`/`end` · `show`/`hide` · `create`/`delete` · `lock`/`unlock` ·
`enable`/`disable`. Не смешивай (`open`/`terminate`, `add`/`destroy`).
