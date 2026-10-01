<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\AzGuard\App\Permissions;

use AzGuard\Attributes\GateAbility;
use AzGuard\Attributes\RoleOnly;

/**
 * Permissions — this PHP enum cases, not recorded in the database. One enum to resource
 * (DocumentsPermission, UsersPermission), more than one giant AppPermission.
 *
 * Full key: {panel}.{resource}.{action} — panel prefix ('app.')
 * adds AzGuard at the place of registration enum'and in PanelProvider,
 * inside enum'and is declared only 'documents.view'.
 *
 * Attributes:
 *   #[GateAbility] — is registered in Laravel Gate like '{panel}.{value}'
 *                    (available in Gate::allows, @can, policies); this default,
 *                    but indicate it explicitly - the intention is visible in the review.
 *   #[RoleOnly]    — is in the catalog, but in Gate NOT registered:
 *                    is only checked via $user->hasPermission();
 *                    in policy or @can will always return false.
 */
enum DocumentsPermission: string
{
    #[GateAbility]
    case View = 'documents.view';

    #[GateAbility]
    case Create = 'documents.create';

    #[GateAbility]
    case Edit = 'documents.edit';

    #[GateAbility]
    case Export = 'documents.export';

    // Internal check, not exposed through Gate
    #[RoleOnly]
    case Purge = 'documents.purge';
}

// ── Permission checks ───────────────────────────────────────────────────────────
//
// Always enum-cases, never raw lines: typo in line
// (Gate::allows('app.documents.veiw')) will silently return false — inconspicuous hole.
//
// On the model (HasAzGuard):
//   $user->hasPermission(DocumentsPermission::View);
//   $user->hasPermission('app.documents.view');         // full string key also works
//   $user->hasAnyPermission([DocumentsPermission::Edit, DocumentsPermission::Export]);
//   $user->hasAllPermissions([DocumentsPermission::View, DocumentsPermission::Edit]);
//
// Via Gate (needed #[GateAbility]; Gate accepts BackedEnum directly):
//   Gate::allows(DocumentsPermission::View);             // bool
//   Gate::allows(DocumentsPermission::Edit, $document);  // via policy
//   $this->authorize(DocumentsPermission::View);         // 403 on failure
//
// Middleware — is the only place where the line is unavoidable:
//   Route::get('/documents', DocumentController::class)
//       ->middleware('can:' . DocumentsPermission::View->value);
//
// Blade (no use-statements — FQCN + ->value, or transfer ready bool):
//   @can(\App\AzGuard\App\Permissions\DocumentsPermission::Edit->value) ... @endcan
//
// Introspection:
//   $user->getAllPermissions();        // roles + direct grants, Collection<string>
//   $user->getPermissionsViaRoles();   // only from roles
//   $user->getDirectPermissions();     // direct grants only
//
// ── Artisan ────────────────────────────────────────────────────────────────
//
// php artisan azguard:make-permission App DocumentsPermission
// php artisan azguard:list-permissions --panel=app --with-roles
