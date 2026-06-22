<?php

// Source: generalized from a runtime transition registry (anonymized)
// Тонкий рантайм-реестр поверх графа enum: строит adjacency лениво и кэширует в статике.
// Источник данных — только OrderStatus::transitionDefinitions().

declare(strict_types=1);

namespace App\Services\Order;

use App\Enums\OrderStatus;

final class OrderStatusTransitions
{
    /** @var array<string, list<OrderStatus>>|null */
    private static ?array $adjacency = null;

    /** @return list<OrderStatus> */
    public static function allowedFrom(OrderStatus $from): array
    {
        self::ensureBuilt();

        return self::$adjacency[$from->value] ?? [];
    }

    public static function canTransition(OrderStatus $from, OrderStatus $to): bool
    {
        return in_array(needle: $to, haystack: self::allowedFrom(from: $from), strict: true);
    }

    private static function ensureBuilt(): void
    {
        if (self::$adjacency !== null) {
            return;
        }

        // Дедуп целей по value, чтобы повторное ребро не плодило дубли в списке.
        /** @var array<string, array<string, OrderStatus>> $byFrom */
        $byFrom = [];

        foreach (OrderStatus::transitionDefinitions() as $edge) {
            $byFrom[$edge['from']->value][$edge['to']->value] = $edge['to'];
        }

        $adjacency = [];
        foreach ($byFrom as $fromValue => $targets) {
            $adjacency[$fromValue] = array_values(array: $targets);
        }

        self::$adjacency = $adjacency;
    }
}
