<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Settings\Order;

use Spatie\LaravelSettings\Settings;

/**
 * Typed settings class.
 *
 * Rules:
 * - extends Settings, class final;
 * - only PUBLIC TYPED properties - each = one line in the database (key "group.property");
 * - property names in snake_case, match the keys in settings-migrations;
 * - nullable (?T) for optional values;
 * - DO NOT set defaults here - defaults live in migration;
 * - DO NOT declare constructor;
 * - group() returns the group prefix (full string key = "order.<property>").
 *
 * After creation, register the class in config/settings.php → 'settings' => [...]
 * (if not enabled auto_discover_settings).
 */
final class OrderSettings extends Settings
{
    /** Enables runtime override of other values (typical «flag switch»). */
    public bool $enabled;

    /** Scalars work out of the box: int / float / string / bool / array. */
    public int $max_items_per_order;

    public float $default_discount_rate;

    /** Optional value - nullable. */
    public ?string $support_email;

    /** Arrays are supported natively (are stored as JSON). */
    public array $allowed_currencies;

    public static function group(): string
    {
        return 'order';
    }

    /**
     * Castes for untyped values (DateTime, enum, DTO).
     * Scalars are not needed. Global castes can be taken into account config/settings.php → global_casts.
     *
     * public static function casts(): array
     * {
     *     return [
     *         'opening_at' => DateTimeInterfaceCast::class,
     *     ];
     * }
     */
}
