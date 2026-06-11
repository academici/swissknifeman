---
name: ticket-workflow
bucket: general
version: 0.1.0
description: "Use for ticket domain logic: Actions, Services, Repositories, Observers, Policies, Notifications in the ticket system. Activate when working with Ticket, Participant, History, Message models; TicketStatus transitions via StateMachine; Actions in app/Actions/Ticket/; NotificationService; UserService::getPrimaryRole; or ticket authorization via Gate/Policies."
risk: write
persona: oss-dev
tags: [workflow, domain, laravel]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Ticket Workflow

## Domain Overview

Ticket domain is the core of {{project_name}}. State transitions are based on `TicketStatus` and executed through `StateMachine`.

**Master graph of allowed edges:** `App\Enums\Ticket\TicketStatus::transitionDefinitions()` (metadata for UI, policies, codegen). Runtime registry: `App\Services\Ticket\TicketStatusTransitions`; do not reintroduce a parallel transition graph elsewhere.

Practical split:
- **Question flow** — statuses around processing, revision, approval, final answer.
- **Application flow** — statuses for call-center and tech-capabilities subprocesses.

Transition side effects (history/events/notifications) must stay explicit and predictable.

## Strict (Action-driven)

- **Mutation** — only in `Action` (or model observer aligned with domain). `*Service` classes do not persist domain entities and do not accept `Request`.
- **Composite use-case** — a dedicated `Action` that calls other `Action`s (e.g. `RegisterStoreAction`: `StoreAction` → written reply branch OR `RegisteredAction`). Not a "use-case Service" wrapping Actions.
- **Evaluators** — read-only services (`WorkflowService`, `StageViewService`, `DeadlineService`, `ParticipantAccessService`, approval-cycle evaluator, etc.) compute predicates / views; Actions call them then persist via `StateMachine` or `*StoreRepository`.

## Actions (`app/Actions/Ticket/`)

Each Action has one public method `execute()`. Rules:
- Accept models, primitives, User — **never** `Request` or inline Gate checks (use `Gate::authorize` in controller or attribute).
- Return model or void
- Use `DB::transaction()` for multi-model operations (single transactional boundary per atomic use-case).
- Throw `ValidationException` for business rule violations
- Call domain evaluators (`WorkflowService`, …), `StateMachine`, and write-repositories — not low-level orchestration in controllers

**Composite Action**: orchestrates multiple Actions for one HTTP entrypoint; still one `execute()`, still no `Request`.

**Wrapper pattern**: if operations differ only by enum values, parametrize the base Action and create thin wrappers:
```php
// Base action with parameters
final readonly class TakeInWorkAction
{
    public function execute(TakeInWorkCommand $command): void { /* ... */ }
}

// Thin wrapper for specific role
final readonly class CallCenterTakeInWorkAction
{
    public function __construct(private TakeInWorkAction $action) {}

    public function execute(Ticket $ticket, User $user): void
    {
        $this->action->execute(
            command: new TakeInWorkCommand(
                ticket: $ticket,
                user: $user,
                triggerStatus: TicketStatus::ApplicationCallCenterStarted,
                nextStatus: TicketStatus::ApplicationCallCenterWorking,
            ),
        );
    }
}
```

## UserService::getPrimaryRole

Single point of truth for user role resolution. Use instead of direct role checks everywhere.

```php
// Without context — uses Auth::user(), picks role by forTicket priority
UserService::getPrimaryRole();

// With ticket context — checks participant roles first
UserService::getPrimaryRole(user: $user, scopeModel: $ticket);
```

Role priority (1 = highest): Secretary → Registrar → RegistrarLocal → Presidium → Approving → Responsible → Expert → CallCenterOperator → TechSpec

## Services (allowed types only)

- **`WorkflowService`** — role/status rules (evaluator).
- **`StageViewService`** — stage view / diff data for UI (read-side).
- **`DeadlineService`** — deadline computation (evaluator).
- **`ParticipantAccessService`** (under `Access/`) — edit permissions resolution (evaluator).
- **`NotificationService`** — notifications (side-effect).
- **`UpdatedBroadcaster`** — websocket refresh queue (side-effect).
- **`UserService`** — primary role resolution and role-driven selections.

Do not add new "domain facade" services that only proxy these without value. Do not put HTTP guards or `Request` mapping into `*Service`.

## Repositories

Repository layer is split by responsibility:

- `*Repository` — read-side (query builders, list/search/filter, access-aware selections).
- `*StoreRepository` — write-side (mutations, sync operations, state-related persistence).

For ticket domain:
- `Repository` / `TicketReadRepository` — read/use-case selections.
- `StoreRepository` (legacy) / split `*StoreRepository` — write operations (being decomposed per architecture plan).

Do not duplicate the same `where` chains in Actions/Policies/Services when model scope or repository method already exists.

## Model scopes and helpers

If identical query predicates repeat in multiple places:
- move them to model scopes / model methods;
- keep names domain-oriented (`withRole`, `forTicket`, `hasHistoryStatus`, etc.);
- avoid extraction for one-off code paths.

DTO mapping helpers should live near DTOs (e.g., `SelectedUser::fromUserId()` / `fromUserIds()`), not inside orchestration services.

## Authorization

- Gates defined in `AppServiceProvider` via `Gate::define(PermissionEnum::Case->value, ...)`
- Gate ability identifier is taken directly from permission enum `->value`
- Gate registration is centralized via `PolicyAttributeRegistrar` and `#[GateAbility(...)]` on policy methods
- Policies accept `User` and `Ticket` — no requests
- Frontend abilities are collected in DTOs: `CommonAbilities`, `ApplicationAbilities`

## Testing

Feature tests for ticket Actions live in `tests/Feature/Ticket/`. Always test:
- Happy path (valid state transition)
- Forbidden path (wrong role, wrong stage)
- Validation failure (invalid data)

## Reference Docs (load when needed)

| Need | File |
|---|---|
| Full Question workflow steps, transitions, Actions | `docs/workflow/question.md` |
| Full Application workflow (call center, tech spec) | `docs/workflow/application.md` |
| Domain terms, statuses, entities | `docs/workflow/glossary.md` |
| Roles table, permissions matrix, participant roles | `docs/workflow/roles.md` |

## For complex changes

If task is cross-layer or ambiguous, activate:

- `complex-task-orchestrator` — decomposition, risks, DoD;
- `cross-layer-change-checklist` — mandatory synchronization checks before finalization.
