<?php

// Source: anonymized production project

declare(strict_types=1);

namespace App\Settings\Order;

use Spatie\LaravelSettings\Settings;

/**
 * Типизированный класс настроек.
 *
 * Правила:
 * - extends Settings, класс final;
 * - только PUBLIC TYPED свойства — каждое = одна строка в БД (ключ "group.property");
 * - имена свойств в snake_case, совпадают с ключами в settings-миграции;
 * - nullable (?T) для опциональных значений;
 * - НЕ задавать значения по умолчанию здесь — дефолты живут в миграции;
 * - НЕ объявлять конструктор;
 * - group() возвращает префикс группы (полный ключ строки = "order.<property>").
 *
 * После создания зарегистрировать класс в config/settings.php → 'settings' => [...]
 * (если не включён auto_discover_settings).
 */
final class OrderSettings extends Settings
{
    /** Включает рантайм-переопределение остальных значений (типичный «флаг-выключатель»). */
    public bool $enabled;

    /** Скаляры работают из коробки: int / float / string / bool / array. */
    public int $max_items_per_order;

    public float $default_discount_rate;

    /** Опциональное значение — nullable. */
    public ?string $support_email;

    /** Массивы поддерживаются нативно (хранятся как JSON). */
    public array $allowed_currencies;

    public static function group(): string
    {
        return 'order';
    }

    /**
     * Касты для нетипизированных значений (DateTime, enum, DTO).
     * Скалярам не нужны. Глобальные касты можно вынести в config/settings.php → global_casts.
     *
     * public static function casts(): array
     * {
     *     return [
     *         'opening_at' => DateTimeInterfaceCast::class,
     *     ];
     * }
     */
}
