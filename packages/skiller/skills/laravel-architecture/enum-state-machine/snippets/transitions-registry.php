<?php

// Source: generalized from a runtime transition registry (anonymized)
// Thin runtime registry on top of the graph enum: builds adjacency is lazy and caches statically.
// Data source - only OrderStatus::transitionDefinitions().

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

        // Dedup targets by value, so that the repeated edge does not create duplicates in the list.
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
