---
name: naming-conventions
bucket: general
version: 0.1.0
description: "Naming discipline (language-agnostic): name reveals intent, not implementation; fight noise words (Manager/Helper/data/process) and combinatorial method explosion (findByXOrFail/getOrNull). Activate when naming or reviewing names of functions, classes, variables, methods."
risk: read
persona: oss-dev
tags: [naming, conventions, readability, code-style, discipline, clean-code]
requires: []
produces_for: []
outputs: []
snippets: ["naming-gallery.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Naming discipline

Language-agnostic **policy** (not a pattern); stack-specific skills (`general/naming-conventions` etc.) build on it.

## Activate when

- Naming a function, method, class, variable, file, flag.
- Reviewing code where a name doesn't reveal *what it does* without reading the body.
- Spotting AI-junk names: `findByCodeOrFail`, `getDataProcessor`, `handleStuff`, `UserManager`, `result2`, `tmpArr`.
- User mentions readability, naming conventions, "what to call it".

## Core principle

Name reveals **intent**, not implementation, not type. Reader understands *what* and *why* without opening the body. If a name needs a comment, it's bad.

```
# bad: implementation leaks into name     # good: intent
loopThroughUsersAndFilter()               activeUsers()
recordWithStatusEqual2()                  publishedRecords()
arr / arr2 / tmp / data / obj             pendingInvoices / recipient / payload
```

## Seven rules

1. **Verbs for actions, nouns for data.** Function/method with effect = verb phrase (`sendInvoice`, `archive`); pure query = noun or side-effect-free `get` (`totalPrice`, `nextAvailableSlot`). Class/variable = noun (`Invoice`, `recipient`).
2. **Booleans = question:** prefixes `is`/`has`/`can`/`should`/`needs` (`isActive`, `hasAccess`, `canPublish`); not `active`/`flag`/`status` for bool.
3. **CQS in names:** command changes state, usually `void` (`open`, `cancel`); query returns data with no effects (`status`, `findOpenOrders`). Name must not lie about effects.
4. **One word per concept.** Don't mix `fetch`/`get`/`retrieve`/`load` for one operation — pick one across the codebase. Same for `delete`/`remove`/`destroy`.
5. **Symmetric opposites:** `open`/`close`, `begin`/`end`, `show`/`hide`, `create`/`delete` — not `open`/`terminate`, not `add`/`destroy`.
6. **Length ∝ scope.** Loop index `i` fine; class field or public API = full meaningful name. Wider visibility → more descriptive.
7. **Pronounceable & searchable.** No `genymdhms`, `dtaRcrd102`. Abbreviations only well-known (`id`, `url`, `http`); no Hungarian notation (`strName`, `iCount`).

## Anti-pattern gallery (AI-generated → replacement)

| Anti-pattern | Why bad | Replacement |
|:--|:--|:--|
| **Combinatorial explosion** `findByCodeOrFail`, `findByEmailOrFail`, `findBySlugOrFail`… | method-per-field → exponential API growth; duplication | one accessor + criteria/specification: `find(criteria)`, or named query by *intent* (`activeBySlug`) — see rule below |
| **`…OrNull`/`…OrFail`/`…OrThrow` tails on every method** | error policy baked into name N times | error policy once (result type `Optional`/exception by layer contract), name about *what* you look for |
| **Noise suffixes** `UserManager`, `OrderHelper`, `DataProcessor`, `*Util`, `*Info`, `*Handler` | "manager of what, why?" — class with no responsibility, method dump | name by *role*: `OrderRepository`, `PriceCalculator`, `InvoiceMailer`. No role → no class |
| **Noise data names** `data`, `info`, `obj`, `item`, `temp`, `value`, `result`, `arr`, `list` | meaningless, unsearchable | by content: `invoice`, `recipients`, `parsedPayload`, `dueDate` |
| **Redundant `get`/type prefix** `getUserById`, `getAllUsers`, `OrderObject`, `OrderClass`, `IUserInterface` | `get`+arg already clear; type suffix is noise | `user(id)` / `users()`; `Order`; `UserRepository` (role, not "Interface") |
| **Numeric/mechanical suffixes** `user2`, `tempList`, `handleData2`, `processX` | copy-paste without rethinking | split by meaning: `existingUser`/`incomingUser` |
| **Name lies about effects** `getUser()` sends email; `isValid()` mutates | breaks CQS, reader trap | `getUser` no effects; effect = separate command `notifyUser` |

### `findByXOrFail` rule

Don't spawn a method per field. Allowed:
- **One canonical lookup** by primary key / single criterion (`find(id)`, `findOrFail(id)`).
- **Named queries by intent** when the selection is domain-meaningful (`activeBySlug`, `pendingForReview`) — *business meaning*, not "per column".
- Otherwise — criteria param / specification / query object, not a new method.

## Quality checklist

- [ ] Name reveals *what it does* without reading body or comment.
- [ ] Action = verb, data = noun; boolean = `is/has/can/should`.
- [ ] No noise words: `data/info/obj/temp/result` and suffixes `Manager/Helper/Util/Handler/Processor` without a clear role.
- [ ] No method-per-field (`findByX…OrFail` × N); error policy expressed once.
- [ ] One verb per concept across the base (no `get`/`fetch`/`load` mix).
- [ ] Opposite operations named symmetrically.
- [ ] Name length matches scope; pronounceable and searchable.
- [ ] Name doesn't lie about side effects (CQS).

## Snippet

`snippets/naming-gallery.md` — extended cross-language "bad → good" table (functions, classes, variables, booleans, collections, tests) for review/CLAUDE.md.

## Related skills

- `general/naming-conventions` — Laravel specifics (Actions/Repository/DTO/VO/Enum, `findByXOrFail` breakdown).
- `general/writing-style` — prose & message style; naming is about code identifiers.
- `quality/code-review` — where name checks fit into review (P2/P3 findings).
- `general/anti-drift` — "simplicity first": simpler name = less drift.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: fa860d2c16747dee89bb959a04f353de4646d59f7c29465b7373e6f238dd632a -->
