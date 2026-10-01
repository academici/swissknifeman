<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

namespace App\Attributes\Common;

use Attribute;

/**
 * Metadata attribute enum-case. One axis = one class.
 * TARGET_CLASS_CONSTANT — target covering cases enum.
 */
#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Label
{
    public function __construct(
        public string $value,
    ) {}
}

// Following the same pattern - the remaining metadata axes:

#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Color
{
    public function __construct(
        public string $value,
    ) {}
}

#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Description
{
    public function __construct(
        public string $value,
    ) {}
}

// An attribute can carry several parameters and domain types:

#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Dashboard
{
    public function __construct(
        public int $priority,
        public bool $visible = true,
    ) {}
}
