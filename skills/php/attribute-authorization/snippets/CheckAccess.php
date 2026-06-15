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
 * Middleware-исполнитель атрибутов #[CheckPermission].
 *
 * Алгоритм на запрос:
 *  1. По route action (Controller@method) находим метод контроллера.
 *  2. Через ReflectionMethod::getAttributes() читаем все #[CheckPermission].
 *  3. Для каждого: резолвим имена аргументов из параметров маршрута и
 *     дёргаем Gate::allows($permission->value, $arguments) с abort_if.
 *
 * Если на экшене нет атрибутов — middleware прозрачен (пропускает дальше).
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

        // Closure-роуты и invokable без @ — пропускаем (нет метода для рефлексии).
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
     * Имена параметров маршрута → их значения (обычно — Model из route-model
     * binding). Возвращаем list в том же порядке, в каком они объявлены в
     * атрибуте, чтобы Gate-ability получил их позиционно.
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
