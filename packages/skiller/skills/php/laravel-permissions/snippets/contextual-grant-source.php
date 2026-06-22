<?php

// Source: azguard/context (anonymized)

declare(strict_types=1);

namespace App\Authorization;

use Illuminate\Contracts\Auth\Authenticatable;
use Illuminate\Support\Facades\DB;

/**
 * GrantSource: permissions from entity-scoped roles.
 * Priority between class roles (100) and database roles (90).
 */
final readonly class ContextualRoleGrantSource
{
    public function __construct(
        private AuthorizationContextManager $manager,
    ) {}

    /** @return list<string> */
    public function permissionsFor(Authenticatable $user, string $panelId): array
    {
        $context = $this->manager->current($panelId);

        if ($context === null) {
            return [];
        }

        return DB::table('context_roles')
            ->where('model_type', $user::class)
            ->where('model_id', $user->getAuthIdentifier())
            ->where('context_type', $context->contextType)
            ->where('context_id', $context->contextId)
            ->where('panel_id', $panelId)
            ->pluck('permission_key')
            ->all();
    }
}
