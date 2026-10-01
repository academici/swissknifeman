<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\Models;

use AzGuard\Concerns\InteractsWithAzScopes;
use Illuminate\Database\Eloquent\Model;

/**
 * Entity-scoped roles: role for a specific model instance -
 * user editor in Project A, but without a role in Project B.
 * Lays OVER global roles, does not replace them.
 *
 * Use cases: multi-tenant projects, team-admin on Team,
 * reviewer on Document, owner to any Eloquent-model.
 *
 * The trait is attached to a scope entity; User is already using HasAzGuard.
 */
class Project extends Model
{
    use InteractsWithAzScopes;
}

// ── Purpose / removal / check scoped-roles ──────────────────────────────
//
// use App\AzGuard\App\Roles\EditorRole;
//
// $user->assignScopedRole(EditorRole::class, $project);
// $user->removeScopedRole(EditorRole::class, $project);
// $user->hasScopedRole(EditorRole::class, $project);      // bool
//
// ── Verification scoped-rights ───────────────────────────────────────────────────
//
// Resolution order hasScopedPermission():
//   1. Wildcard — global role with ['*'] → immediately true.
//   2. Global roles (assignRole) — are checked first.
//   3. Scoped-roles (assignScopedRole) — for the passed entity.
//
// use AzGuard\Facades\AzGuard;
// use App\AzGuard\App\Permissions\DocumentsPermission;
//
// if ($user->hasScopedPermission(
//     AzGuard::permission('app', DocumentsPermission::Edit),  // 'app.documents.edit'
//     $project,
// )) {
//     // the user can edit this particular project
// }
//
// Gate uses scoped-resolve automatically when the second argument
// entity passed:
//
// Gate::allows('app.documents.edit', $project);
//
// ── Cache ─────────────────────────────────────────────────────────────────────
//
// Cache scoped-rights are reset automatically when assignScopedRole() /
// removeScopedRole(). Manual reset for user:
//
// php artisan azguard:cache-reset --user=42
