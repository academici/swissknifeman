# Naming gallery: bad → good (cross-lingual)

Ready table for review or insertion into `CLAUDE.md`/`AGENTS.md`. There is only one principle:
**the name reveals the intent, not the implementation or the type.**

## Functions and methods

| Bad | Okay | Why |
|:--|:--|:--|
| `handleData(d)` | `parseInvoice(raw)` | verb + what exactly |
| `processX()` / `doStuff()` | `chargeCard()`, `rebuildIndex()` | specific action |
| `getDataFromDbAndCache()` | `loadUser(id)` | implementation (db+cache) not in name |
| `getUserById(id)` | `user(id)` / `findUser(id)` | argument already says «by id» |
| `getAllActiveUsersList()` | `activeUsers()` | without `getAll…List` noise |
| `findByCodeOrFail`, `findByEmailOrFail`, … | `find(criteria)` / `activeBySlug(slug)` | is not a method-on-field |
| `checkUser()` (and inside there is a mutation) | request `isEligible()` + command `activate()` | CQS: the name doesn't lie about the effect |

## Classes and types

| Bad | Okay | Why |
|:--|:--|:--|
| `UserManager` | `UserRepository` / `UserRegistrar` | role, not «manager» |
| `OrderHelper`, `StringUtils` | `OrderTotals`, `Slugifier` | dump → specific responsibility |
| `DataProcessor` | `CsvImporter`, `PaymentSettler` | what it processes and why |
| `OrderObject`, `OrderClass`, `OrderData2` | `Order` | type suffix - noise |
| `IUserRepository` (Hungarian) | `UserRepository` | without type encoding prefix |

## Variables and fields

| Bad | Okay | Why |
|:--|:--|:--|
| `data`, `info`, `obj`, `item` | `invoice`, `recipient`, `row` | by content |
| `tmp`, `temp`, `val`, `res`, `arr` | `parsed`, `dueDate`, `pendingIds` | intriguing, meaningful |
| `list`, `users2`, `arr3` | `recipients`, `incomingUser` | make sense |
| `flag`, `status` (for bool) | `isPublished`, `hasAccess` | boolean - question |
| `strName`, `iCount`, `bOk` | `name`, `count`, `accepted` | without Hungarian notation |

## Boolean

`is*` / `has*` / `can*` / `should*` / `needs*`:
`isActive`, `hasInvoice`, `canEdit`, `shouldRetry`, `needsReview`.

## Collections

Plural for collections (`users`, `orderIds`); single - for element (`user`).
Not `userList`/`userArray` — storage type is not in the name.

## Tests

Test name = condition + waiting:
`it_archives_paid_orders_after_30_days`, and not `test1`, `testOrders`, `itWorks`.

## Symmetry

`open`/`close` · `begin`/`end` · `show`/`hide` · `create`/`delete` · `lock`/`unlock` ·
`enable`/`disable`. Don't mix (`open`/`terminate`, `add`/`destroy`).
