<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Attributes;

use Attribute;
use UnitEnum;

/**
 * Declarative permission check at the controller method level.
 *
 * Repeatable (IS_REPEATABLE) — you can attach several to one action
 * checks, they all must pass. Goal - TARGET_METHOD: attribute read
 * middleware via ReflectionMethod, and not the controller itself.
 *
 * @example
 *   #[CheckPermission(Permission::ViewOrder, arguments: ['order'])]
 *   #[CheckPermission(Permission::ViewCompany, arguments: ['order'], status: 404)]
 *   public function show(Order $order): View { ... }
 */
#[Attribute(flags: Attribute::TARGET_METHOD | Attribute::IS_REPEATABLE)]
final readonly class CheckPermission
{
    /**
     * @param  UnitEnum  $permission  enum-right; in Gate leaves $permission->value
     * @param  list<string>  $arguments  names of route parameters that
     *                                    are resolved and sent to Gate::allows
     *                                    as arguments (usually - Model from
     *                                    route-model binding)
     * @param  int  $status  HTTP-status for abort on failure (403 / 404 / 401)
     * @param  string|null  $message  message for abort; null → empty string
     */
    public function __construct(
        public UnitEnum $permission,
        public array $arguments = [],
        public int $status = 403,
        public ?string $message = null,
    ) {}
}
