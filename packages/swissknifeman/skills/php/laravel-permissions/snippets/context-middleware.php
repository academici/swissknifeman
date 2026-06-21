<?php

// Source: azguard/context (anonymized)

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Authorization\AuthorizationContext;
use App\Authorization\AuthorizationContextManager;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

final readonly class SetAuthorizationContext
{
    public function __construct(
        private AuthorizationContextManager $manager,
    ) {}

    public function handle(Request $request, Closure $next): Response
    {
        $workspaceId = $request->route('workspace');

        if ($workspaceId !== null) {
            $this->manager->set(new AuthorizationContext(
                panelId: 'app',
                contextType: 'workspace',
                contextId: (int) $workspaceId,
            ));
        }

        return $next($request);
    }
}
