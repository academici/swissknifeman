<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Attributes\CheckPermission as CheckPermissionAttribute;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Gate;
use ReflectionMethod;
use Symfony\Component\HttpFoundation\Response;

/**
 * Middleware-attribute executor #[CheckPermission].
 *
 * Algorithm for the request:
 *  1. By route action (Controller@method) find the controller method.
 *  2. Via ReflectionMethod::getAttributes() read everything #[CheckPermission].
 *  3. For each: resolve argument names from route parameters and
 *     pull Gate::allows($permission->value, $arguments) with abort_if.
 *
 * If the action has no attributes - middleware transparent (skips further).
 */
final class CheckAccess
{
    /**
     * @param  Closure(Request): (Response)  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        foreach ($this->getPermissionAttributes(request: $request) as $attribute) {
            $arguments = $this->resolveArguments(
                request: $request,
                parameterNames: $attribute->arguments,
            );

            abort_if(
                boolean: ! Gate::allows(
                    ability: $attribute->permission->value,
                    arguments: $arguments,
                ),
                code: $attribute->status,
                message: $attribute->message ?? '',
            );
        }

        return $next($request);
    }

    /**
     * @return list<CheckPermissionAttribute>
     */
    private function getPermissionAttributes(Request $request): array
    {
        $route = $request->route();

        if (! $route) {
            return [];
        }

        $actionName = $route->getActionName();

        // Closure-routes and invokable without @ — skip (no method for reflection).
        if (! is_string($actionName) || ! str_contains(haystack: $actionName, needle: '@')) {
            return [];
        }

        [$controllerClass, $methodName] = explode(separator: '@', string: $actionName, limit: 2);

        if (! class_exists($controllerClass) || ! method_exists(object_or_class: $controllerClass, method: $methodName)) {
            return [];
        }

        $method = new ReflectionMethod($controllerClass, $methodName);

        return array_map(
            callback: static fn (object $attribute): CheckPermissionAttribute => $attribute->newInstance(),
            array: $method->getAttributes(name: CheckPermissionAttribute::class),
        );
    }

    /**
     * Route parameter names → their meanings (usually - Model from route-model
     * binding). Returning list in the same order in which they are declared in
     * attribute to Gate-ability got them positionally.
     *
     * @param  list<string>  $parameterNames
     * @return list<mixed>
     */
    private function resolveArguments(Request $request, array $parameterNames): array
    {
        return array_values(array: array_map(
            callback: static fn (string $parameterName): mixed => $request->route($parameterName),
            array: $parameterNames,
        ));
    }
}
