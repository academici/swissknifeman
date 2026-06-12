---
name: azguard
bucket: php
version: 0.1.0
description: "Роли и контроль доступа на базе пакета azguard: code-first RBAC, панели, scoped roles, direct grants, abilities для фронтенда"
risk: write
persona: oss-dev
tags: ["php", "laravel", "permissions", "azguard", "rbac"]
requires: []
produces_for: []
outputs: []
snippets:
  - role-class.php
  - permission-enum.php
  - panel-provider.php
  - policy-gateability.php
  - scoped-roles.php
  - direct-grants.php
  - abilities-dto.php
  - inertia-share.php
  - testing.php
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

RBAC для Laravel-проектов на базе пакета **azguard** (`azguard/azguard`) — code-first подход: права и роли живут в коде, версионируются в git и ревьюятся в PR, а не дрейфуют в БД (в отличие от spatie/permission). Монорепо пакета: `core` (основной RBAC), `filament` (интеграция с Filament), `context` (контекстные права).

Ключевые принципы:

- **Роли = PHP-классы** `RoleInterface` с методами `getName()` / `getLevel()` / `permissions()`. Уровни (`getLevel()`) — для сравнений (`$user->hasRoleLevel('>= 50')`), не для наследования прав. Wildcard `['*']` в `permissions()` = super-admin (срабатывает в `Gate::before`).
- **Permissions = backed enum** с атрибутами `#[GateAbility]` (регистрируется в Gate) и `#[RoleOnly]` (только `hasPermission()`, в Gate не попадает). Один enum на ресурс, ключи `{panel}.{resource}.{action}` — префикс панели добавляется автоматически.
- **Трейт `HasAzGuard` на User** (+ `HasDirectGrants` для прямых грантов): `assignRole()`, `hasRole()`, `hasPermission()`, `syncRoles()`, query scopes `User::role()` / `User::permission()`.
- **Панели = изолированные namespace** прав (`app`, `admin`, `api`). Объявляются классом `PanelProvider` (`id`, `path`, `permissionEnums`, `roleClasses`), регистрируются в `config/az-guard.php` → `panels`. Один пользователь может иметь разные роли в разных панелях.
- **Порядок резолва прав**: class roles → db roles (DynamicRole) → direct grants (`EffectivePermissionResolver` агрегирует GrantSources по приоритету).
- **Gate-first**: в PHP-коде всегда `Gate::allows(DocumentsPermission::View)` с enum-кейсом, никогда сырые строки (опечатка = тихая дыра в безопасности). Строки — только в middleware/Blade через `->value`.
- **Авторегистрация политик**: класс с `#[GuardPolicy(model: Document::class)]`, методы с `#[GateAbility(permission: Enum::Case)]` — PanelProvider сканирует `**/Policies/**/*Policy.php` и сам вызывает `Gate::define()` / `Gate::policy()`.
- **Scoped roles**: роль на конкретную сущность (`assignScopedRole(EditorRole::class, $project)`), `Gate::allows('app.documents.edit', $project)` использует scoped-резолв автоматически.
- **Direct grants с TTL**: исключение, не основной паттерн — `AzGuard::forUser($user)->on('app')->ttl(3600)->give(...)`; истёкшие гранты чистит `az-guard:prune-grants`.
- **Кеш**: по умолчанию in-memory на запрос; cross-request — `config/az-guard.php` → `cache.store = redis`. Сброс: `php artisan azguard:cache-reset`, в коде — `$user->flushPermissions()`.

Установка:

```bash
composer require azguard/azguard
php artisan vendor:publish --tag=az-guard-config
php artisan migrate
# затем трейт HasAzGuard на User
```

## Алгоритм

1. Установи пакет, опубликуй конфиг, прогони миграции, добавь `HasAzGuard` на User.
2. Создай панель: `panel-provider.php` + регистрация в `config/az-guard.php`.
3. Опиши permissions enum'ами (`permission-enum.php`) и роли классами (`role-class.php`), зарегистрируй их в PanelProvider.
4. Для проверок с моделью — политики с авторегистрацией (`policy-gateability.php`).
5. Роли на конкретную сущность (multi-tenant, команды) — `scoped-roles.php`.
6. Точечные/временные права одному пользователю — `direct-grants.php` (если грантишь одно право 5+ юзерам — пора делать роль).
7. Фронтенд: пер-ресурсные флаги — `abilities-dto.php`; глобальная карта прав — `inertia-share.php`.
8. Тесты на оба исхода (есть право / нет права) — `testing.php`.
9. Проверь конфигурацию: `php artisan azguard:doctor`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Нужна новая роль (статический класс, уровни, wildcard) | `snippets/role-class.php` |
| Нужны новые права (enum, `#[GateAbility]`/`#[RoleOnly]`, проверки) | `snippets/permission-enum.php` |
| Новая панель / регистрация enum'ов и ролей | `snippets/panel-provider.php` |
| Проверка права с учётом модели, авторегистрация политики | `snippets/policy-gateability.php` |
| Роль на конкретную сущность (Project/Team/Document) | `snippets/scoped-roles.php` |
| Временное/одноразовое право одному пользователю | `snippets/direct-grants.php` |
| Передать «что можно с этим ресурсом» во фронтенд (Inertia) | `snippets/abilities-dto.php` |
| Глобальная карта прав на фронте, TS-константы, Vue | `snippets/inertia-share.php` |
| Тесты ролей, прав, грантов (Pest) | `snippets/testing.php` |

## Чеклист качества

- [ ] В PHP-коде только enum-кейсы, сырые строки прав — только в middleware/Blade через `->value`
- [ ] Проверяются permissions, а не роли (`hasPermission()` / `Gate::allows()`, не `hasRole()`)
- [ ] Один enum на ресурс; CRUD-набор `view/create/edit/delete` как база
- [ ] `#[GateAbility]` указан явно даже там, где он default
- [ ] Direct grant вместо роли только для разовых исключений; TTL для временного доступа; `az-guard:prune-grants` в scheduler
- [ ] Abilities передаются на уровне страницы, не в глобальных shared props; фронтенд-проверки — только UX, сервер валидирует всегда
- [ ] Для каждого «разрешено» есть тест «запрещено»; между сменами состояния в тесте — `$user->flushPermissions()`
- [ ] `php artisan azguard:doctor` зелёный после изменений

## Ссылки

- Исходник: `/home/vostrikov/projects/packages/azguard` (docs/guide: basic-usage, permissions, roles, panels, entity-scopes, direct-grants, policies-and-gates, abilities-frontend, testing)
- Ручная реализация RBAC без пакета — скилл `php/laravel-permissions`
- Filament-интеграция — пакет `azguard/filament`, скилл `php/filament`
