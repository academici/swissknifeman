<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

namespace App\Attributes\Common;

use Attribute;

/**
 * Атрибут метаданных enum-кейса. Одна ось = один класс.
 * TARGET_CLASS_CONSTANT — цель, покрывающая кейсы enum.
 */
#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Label
{
    public function __construct(
        public string $value,
    ) {}
}

// По тому же шаблону — остальные оси метаданных:

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

// Атрибут может нести несколько параметров и доменные типы:

#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]
final readonly class Dashboard
{
    public function __construct(
        public int $priority,
        public bool $visible = true,
    ) {}
}
