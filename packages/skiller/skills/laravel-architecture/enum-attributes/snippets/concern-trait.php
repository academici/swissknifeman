<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

// --- Part 1. Resolver (app/Support/Enums/EnumCaseAttributeResolver.php) ---
// Single point of attribute reading enum-cases via reflection, with cache.

namespace App\Support\Enums;

use ReflectionEnum;
use UnitEnum;

final class EnumCaseAttributeResolver
{
    /** @var array<class-string, array<string, array<class-string, object|null>>> */
    private static array $cache = [];

    /**
     * @template TAttribute of object
     *
     * @param  class-string<TAttribute>  $attributeClass
     * @return TAttribute|null
     */
    public static function forCase(UnitEnum $case, string $attributeClass): ?object
    {
        $enumClass = $case::class;

        // Reflection for every road call in hot roads (tables, lists) —
        // cache attribute instances statically.
        if (array_key_exists($attributeClass, self::$cache[$enumClass][$case->name] ?? [])) {
            return self::$cache[$enumClass][$case->name][$attributeClass];
        }

        $reflection = new ReflectionEnum($enumClass);
        $enumCase = $reflection->getCase($case->name);
        $attributes = $enumCase->getAttributes($attributeClass);

        $instance = $attributes === [] ? null : $attributes[0]->newInstance();

        self::$cache[$enumClass][$case->name][$attributeClass] = $instance;

        return $instance;
    }
}

// --- Part 2. Concern-traits (app/Concerns/Enums/) ---
// Each trait = one metadata axis + meaningful default:
// not every case is required to carry every attribute.

namespace App\Concerns\Enums;

use App\Attributes\Common\Color;
use App\Attributes\Common\Label;
use App\Support\Enums\EnumCaseAttributeResolver;

/** @property-read string $name */
trait HasLabelAttribute
{
    public function getLabel(): string
    {
        $attribute = EnumCaseAttributeResolver::forCase($this, Label::class);

        if ($attribute instanceof Label) {
            return $attribute->value;
        }

        return '';
    }
}

/** @property-read string $name */
trait HasColorAttribute
{
    public function getColor(): string
    {
        $attribute = EnumCaseAttributeResolver::forCase($this, Color::class);

        if ($attribute instanceof Color) {
            return $attribute->value;
        }

        return '#6c757d'; // neutral gray by default
    }
}
