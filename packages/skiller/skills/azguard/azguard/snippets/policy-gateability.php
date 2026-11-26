<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\AzGuard\App\Documents\Policies;

use App\AzGuard\App\Permissions\DocumentsPermission;
use App\Models\Document;
use App\Models\User;
use AzGuard\Attributes\GateAbility;
use AzGuard\Attributes\GuardPolicy;

/**
 * Auto-registration: when boot panels PanelProvider scans recursively
 * directories Policies/ (files *Policy.php), reads the attributes and calls itself:
 *   - Gate::define(resolvedAbility, [Policy::class, 'method'])
 *     for each method with #[GateAbility(permission: ...)];
 *   - Gate::policy(Document::class, DocumentsPolicy::class)
 *     by #[GuardPolicy(model: ...)].
 * Nothing with your hands AuthServiceProvider does not need to be registered.
 *
 * Gate::before registered by itself AzGuard and works ONLY for
 * wildcard-roles (permissions() === ['*']) — policy is then not called.
 * All other logic is here, via hasAzPermission().
 */
#[GuardPolicy(model: Document::class)]
class DocumentsPolicy
{
    #[GateAbility(permission: DocumentsPermission::View)]
    public function canView(User $user, Document $document): bool
    {
        return $user->hasAzPermission('app.documents.view')
            && $user->id === $document->owner_id;
    }

    #[GateAbility(permission: DocumentsPermission::Edit)]
    public function canEdit(User $user, Document $document): bool
    {
        return $user->hasAzPermission('app.documents.edit')
            && ! $document->isLocked();
    }

    #[GateAbility(permission: DocumentsPermission::Export)]
    public function canExport(User $user, Document $document): bool
    {
        return $user->hasAzPermission('app.documents.export');
    }
}

// ── Call Gate: always enum-case, not string ────────────────────────────────
//
// Gate::allows(DocumentsPermission::View, $document);     // bool
// Gate::authorize(DocumentsPermission::Edit, $document);  // 403 on failure
// $this->authorize(DocumentsPermission::Edit, $document); // in the controller
//
// Blade — pass the finished ones bool from controller (preferred)
// or FQCN + ->value:
//
// @can(\App\AzGuard\App\Permissions\DocumentsPermission::Edit->value, $document)
//     <button>Edit</button>
// @endcan
//
// @azcan('documents.view')   {{-- short key, panel from context --}}
//     <a href="...">View</a>
// @endazcan
//
// ── Artisan ────────────────────────────────────────────────────────────────
//
// php artisan azguard:make-policy Documents --panel=app
// php artisan azguard:doctor   // will find enum-cases without policy-method and orphan-policies
