<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\AzGuard\Panels;

use App\AzGuard\App\Permissions\DocumentsPermission;
use App\AzGuard\App\Permissions\UsersPermission;
use App\AzGuard\App\Roles\EditorRole;
use App\AzGuard\App\Roles\ViewerRole;
use AzGuard\PanelProvider;
use AzGuard\Support\Panel;

/**
 * Panel - isolated namespace rights within one application
 * (app — end users, admin — staff, api — clients API).
 *
 * Permission 'documents.view', registered in the panel 'app',
 * is stored and checked as 'app.documents.view' — prefix is automatic.
 *
 * When boot provider also scans directories recursively Policies/
 * next to you (files *Policy.php) and autoregisters policies
 * by attributes (see policy-gateability.php).
 */
class AppPanelProvider extends PanelProvider
{
    public function panel(Panel $panel): Panel
    {
        return $panel
            ->id('app')
            ->path('app')
            ->permissionEnums([
                DocumentsPermission::class,
                UsersPermission::class,
            ])
            ->roleClasses([
                EditorRole::class,
                ViewerRole::class,
            ]);
    }
}

// ── Registration in config/az-guard.php ──────────────────────────────────────
//
// 'panels' => [
//     \App\AzGuard\Panels\AppPanelProvider::class,
//     \App\AzGuard\Panels\AdminPanelProvider::class,
// ],
//
// ── One user - different roles in different panels ───────────────────────
//
// $user->assignRole('editor', panel: 'app');
// $user->assignRole('viewer', panel: 'admin');
// $user->hasPermission('app.documents.edit');   // true
// $user->hasPermission('admin.users.delete');   // false
//
// ── Typical project structure ──────────────────────────────────────────────
//
// app/AzGuard/
//   Panels/AppPanelProvider.php
//   App/
//     Permissions/DocumentsPermission.php
//     Roles/EditorRole.php
//   Admin/
//     Permissions/UsersPermission.php
//     Roles/OperatorRole.php
//
// ── Artisan ────────────────────────────────────────────────────────────────
//
// php artisan azguard:make-panel App
// php artisan azguard:doctor          // shows all panels and their status
