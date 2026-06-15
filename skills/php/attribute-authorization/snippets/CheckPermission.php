<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Attributes;

use Attribute;
use UnitEnum;

/**
 * Декларативная проверка прав на уровне метода контроллера.
 *
 * Повторяемый (IS_REPEATABLE) — на один экшен можно навесить несколько
 * проверок, все они должны пройти. Цель — TARGET_METHOD: атрибут читается
 * middleware через ReflectionMethod, а не самим контроллером.
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
     * @param  UnitEnum  $permission  enum-право; в Gate уходит $permission->value
     * @param  list<string>  $arguments  имена параметров маршрута, которые
     *                                    резолвятся и передаются в Gate::allows
     *                                    как аргументы (обычно — Model из
     *                                    route-model binding)
     * @param  int  $status  HTTP-статус для abort при отказе (403 / 404 / 401)
     * @param  string|null  $message  сообщение для abort; null → пустая строка
     */
    public function __construct(
        public UnitEnum $permission,
        public array $arguments = [],
        public int $status = 403,
        public ?string $message = null,
    ) {}
}
