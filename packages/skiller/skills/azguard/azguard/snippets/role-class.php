<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\AzGuard\App\Roles;

use App\AzGuard\App\Permissions\DocumentsPermission;
use AzGuard\Contracts\RoleInterface;

/**
 * Static role - PHP-class, the source of truth in the code (git, PR-review).
 * Registers in PanelProvider via ->roleClasses([...]).
 *
 * Level convention: viewer=1, editor=10, manager=50, admin=100, super-admin=999.
 * Levels do NOT inherit rights - manager does not get rights editor automatically,
 * list explicitly. Levels are needed for comparisons: $user->hasRoleLevel('>= 50').
 */
class EditorRole implements RoleInterface
{
    public function getName(): string
    {
        return 'editor';
    }

    public function getLevel(): int
    {
        return 10;
    }

    public function permissions(): array
    {
        return [
            DocumentsPermission::View,
            DocumentsPermission::Create,
            DocumentsPermission::Edit,
        ];
    }
}

/**
 * Super-admin: wildcard '*' — Gate::before will return true, without calling the policy.
 */
class SuperAdminRole implements RoleInterface
{
    public function getName(): string
    {
        return 'super-admin';
    }

    public function getLevel(): int
    {
        return 999;
    }

    public function permissions(): array
    {
        return ['*'];
    }
}

// ── Role assignment and verification (User uses the trait HasAzGuard) ──────────
//
// $user->assignRole(EditorRole::class);            // by class - preferred
// $user->assignRole('editor');                     // by name
// $user->assignRole('admin', panel: 'admin');      // explicit panel for name collision
// $user->syncRoles([EditorRole::class]);           // replaces the ENTIRE list of roles
// $user->syncRoles([]);                            // removes all roles
// $user->removeRole(EditorRole::class);
//
// $user->hasRole('editor');                        // bool
// $user->hasAnyRole(['editor', 'admin']);          // at least one
// $user->hasAllRoles(['editor', 'moderator']);     // all at once
// $user->hasRoleLevel('>= 50');                    // comparison by level
// $user->getRoleLevel();                           // int: maximum level
//
// ── Query scopes ────────────────────────────────────────────────────────────
//
// User::role('editor')->where('active', true)->paginate();
// User::withoutRole('editor')->get();
// User::permission(DocumentsPermission::Edit)->get();
// User::with('azRoles')->paginate();               // eager-load vs N+1
//
// ── Synchronizing static roles in the database (for Filament-dropdowns) ─────────
//
// php artisan azguard:sync-roles --panel=app       // safe in CI/CD
