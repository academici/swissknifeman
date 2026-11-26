---
name: enum-state-machine
description: "Activate when a domain status (Order/Document/Subscription) needs transition rules: edge graph via enum transitionDefinitions(), runtime registry (canTransition/allowedFrom), Action-executed transition under DB::transaction(). Triggers: PHP status enum, allowed transitions, StateMachine, canTransitionTo, illegal status transition."
---

Single source of truth: edge graph as a static enum method `transitionDefinitions(): array`; thin runtime registry (`*StatusTransitions`) builds adjacency and answers `canTransition(from, to)` / `allowedFrom(from)`. Transition executes in an `Action` under `DB::transaction()` and publishes a domain event.

## Activate when

- Status enum is growing/has `match`/`if` about "from A can go to B" — move to edge graph.
- A second copy of the transition list appeared (in service/policy/frontend) — unify.
- Need "which transitions are available from current status" for UI (action buttons).
- Transition must be atomic with side effects (history, notification, broadcast).
- Need edge metadata: button label, required policy, Action class.

## Do NOT activate

- Plain status without transition rules (any→any) — backing-enum suffices.
- Task only about **case metadata** (label/color/priority) without transition graph — that's `laravel-architecture/enum-attributes` (it complements this skill, not state-machine).
- Domain-specific single-project impl (concrete status/action names) — make it a **project-local** skill (`<project>/.ai|.claude/skills/`), not the shared registry.

## Algorithm

1. **Edge graph on enum.** Static `public static function transitionDefinitions(): array` returns edge list. Min: `from`/`to` (enum cases); optional: `guard` (predicate/ability name), `action` (Action FQCN), `label` (UI), domain axes (`role`, `process`, `condition`). This is the **only** graph source — no parallel copies. See `snippets/enum-with-transitions.php`.
2. **Runtime registry.** `final class XxxStatusTransitions` builds adjacency (`array<string, list<Status>>`) **lazily, cached in static** (reflection/array walk expensive on hot paths). Public: `allowedFrom(Status $from): array`, `canTransition(Status $from, Status $to): bool`. Data source — only `transitionDefinitions()`. See `snippets/transitions-registry.php`.
3. **Guard before transition.** Before mutation check `canTransition($from, $to)` (edge legality) **and** the domain predicate/policy from `guard` (the specific user/context right). Illegal transition → `ValidationException`/`abort`, not a silent no-op.
4. **Execute in Action.** Transition is a use-case: `final readonly` Action with one `execute()`, opens `DB::transaction()`, writes new status (+ history/related models), then `dispatch()` the domain event. Action takes no `Request` (boundaries — `php/laravel`, `general/cross-layer-change-checklist`). See `snippets/transition-action.php`.
5. **Event after commit.** Domain event implements `ShouldDispatchAfterCommit` so listeners/broadcast don't see unsaved state on rollback. Broadcast/listener details — `laravel-data-layer/laravel-broadcasting` (don't duplicate here).
6. **UI-available actions.** Frontend buttons/actions built from `allowedFrom($current)` + each edge's `label`/`guard` — UI reads the graph, doesn't hardcode transitions.
7. **Graph evolution.** New transition = new row in `transitionDefinitions()` (+ Action if needed). Graph test (see checklist) catches dangling edges and unreachable statuses.

## Which snippet

| Situation | File |
|---|---|
| Describing transition graph on the enum itself | `snippets/enum-with-transitions.php` |
| Writing runtime registry (adjacency, canTransition, allowedFrom) | `snippets/transitions-registry.php` |
| Executing transition in Action (transaction + after-commit event) | `snippets/transition-action.php` |

## Pitfalls

- **Parallel graph.** Any second transition list (service/policy/frontend) = desync source. Everything reads `transitionDefinitions()`.
- **Reflection/walk per call.** `allowedFrom` hit in lists/tables — cache adjacency in static; no invalidation needed (graph static at runtime).
- **Silent no-op on illegal transition.** Must throw, else the bug hides.
- **Event without `ShouldDispatchAfterCommit`.** Listener in same transaction sees uncommitted state; on rollback — phantom side-effect.
- **Transition logic in controller/service.** Mutation and transactional boundary go in the Action.
- **Guard ⊆ canTransition.** `canTransition` checks edge legality, `guard` checks subject right; different checks, both needed.

## Quality checklist

- [ ] Transition graph is the only one, in `transitionDefinitions()` on enum
- [ ] Runtime registry reads only `transitionDefinitions()`, adjacency cached
- [ ] `canTransition()` called before mutation; illegal transition → exception
- [ ] Subject right (`guard`/policy) checked separately from edge legality
- [ ] Transition executed in `final readonly` Action under `DB::transaction()`, no `Request`
- [ ] Domain event implements `ShouldDispatchAfterCommit`
- [ ] UI actions built from `allowedFrom($current)`, not hardcoded
- [ ] Graph test exists: no dangling edges (from/to exist), no unreachable statuses

## Links

- `laravel-architecture/enum-attributes` — case metadata (label/color/priority) via attributes+Concern; here — transition graph over such enums (skills complement each other).
- `laravel-data-layer/laravel-broadcasting` — `ShouldDispatchAfterCommit`, broadcast and transition listeners.
- `php/laravel`, `php/repositories` — Action/Repository boundaries the transition lives in.
- `general/cross-layer-change-checklist` — layer sync when adding a transition.
