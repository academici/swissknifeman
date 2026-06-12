---
name: user-roles
bucket: general
version: 0.1.0
description: "Use when working with UserRole enum, user permissions, role priority resolution, or any code that calls UserService::getPrimaryRole(). Activate when the task involves role-based access, participant roles in tickets, #[Priority] attributes on UserRole enum cases, or determining which role a user has in a given ticket context."
risk: read
persona: oss-dev
tags: [roles, authorization, laravel]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# User Roles

## UserRole Enum

Located at `app/Enums/User/UserRole.php`. Each case has a `#[Priority(forTicket: N)]` attribute that defines its priority when resolving the primary role.

Priority order (lower number = higher priority):
| Role | forTicket priority |
|------|--------------------|
| Secretary | 1 |
| Registrar | 2 |
| RegistrarLocal | 3 |
| Presidium | 4 |
| Approving | 5 |
| Responsible | 6 |
| Expert | 7 |
| CallCenterOperator | 8 |
| TechSpec | 9 |

## Role Resolution via UserService::getPrimaryRole

`UserService::getPrimaryRole(?User $user = null, ?Model $scopeModel = null): ?UserRole`

- No arguments → uses `Auth::user()`, picks role with lowest `forTicket` number
- With `$scopeModel instanceof Ticket` → first looks at `Participant` roles for this user in this ticket; if found, returns that role; otherwise falls back to global priority
- This method is the **single source of truth** — never check roles with `$user->hasRole()` or array comparisons directly

## Participant Roles

`Participant` model links users to tickets with a specific `UserRole`. A user can be a participant in a ticket with a different role than their global role. `getPrimaryRole($user, $ticket)` always returns the participant role when one exists.

## Usage in Policies

```php
// In a Policy:
$role = UserService::getPrimaryRole(user: $user, scopeModel: $ticket);

return match($role) {
    UserRole::Secretary, UserRole::Registrar => true,
    default => false,
};
```

## Attributes

`#[Priority(forTicket: N)]` attribute lives at `app/Attributes/User/Role/Priority.php`. Used by `UserService` via reflection to sort roles.

## Ссылки

- Для универсального RBAC в новых проектах — `php/azguard`
