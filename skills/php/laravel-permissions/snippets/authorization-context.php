<?php

// Source: azguard/context (anonymized)

declare(strict_types=1);

namespace App\Authorization;

/**
 * Entity-scoped authorization context.
 * Set per-request via middleware, consumed by grant sources.
 */
final readonly class AuthorizationContext
{
    public function __construct(
        public string $panelId,
        public string $contextType,
        public int|string $contextId,
    ) {}
}
