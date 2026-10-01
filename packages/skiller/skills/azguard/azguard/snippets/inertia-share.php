<?php

// Source: azguard package docs (package: azguard/azguard)

declare(strict_types=1);

namespace App\Http\Middleware;

use App\AzGuard\App\Permissions\DocumentsPermission;
use App\AzGuard\App\Permissions\ReportsPermission;
use Illuminate\Http\Request;
use Inertia\Middleware;

/**
 * Global map of current user rights for Inertia SPA —
 * available as prop on every page. Share only what you need
 * frontend; per-resource flags - via Abilities DTO (abilities-dto.php).
 *
 * IMPORTANT: frontend checks only UX (hide/show button),
 * is not security. Each action is validated on the server
 * (Gate::allows() / policy / middleware).
 */
class HandleInertiaRequests extends Middleware
{
    public function share(Request $request): array
    {
        return array_merge(parent::share($request), [
            'auth' => [
                'user' => $request->user(),
                'permissions' => $request->user() ? [
                    'documents' => [
                        'view' => $request->user()->hasPermission(DocumentsPermission::View),
                        'create' => $request->user()->hasPermission(DocumentsPermission::Create),
                        'edit' => $request->user()->hasPermission(DocumentsPermission::Edit),
                        'delete' => $request->user()->hasPermission(DocumentsPermission::Delete),
                    ],
                    'reports' => [
                        'view' => $request->user()->hasPermission(ReportsPermission::View),
                        'export' => $request->user()->hasPermission(ReportsPermission::Export),
                    ],
                ] : [],
            ],
        ]);
    }
}

// ── TypeScript-rights constants ───────────────────────────────────────────────
//
// php artisan azguard:export-ts
// # outputs: resources/js/permissions.ts (auto-generated, do not edit)
//
// export const Permissions = {
//   app: {
//     documents: {
//       view:   'app.documents.view',
//       create: 'app.documents.create',
//     },
//   },
// } as const;
//
// ── Consumption in Vue (computed by page.props) ──────────────────────────────
//
// <!-- resources/js/Pages/Documents/Index.vue -->
// <script setup lang="ts">
// import { computed } from 'vue'
// import { usePage } from '@inertiajs/vue3'
// import { Permissions } from '@/permissions'
//
// const page = usePage()
//
// const canCreate = computed(
//   () => page.props.auth.permissions?.documents?.create
// )
// </script>
//
// <template>
//   <CreateButton v-if="canCreate" />
// </template>
