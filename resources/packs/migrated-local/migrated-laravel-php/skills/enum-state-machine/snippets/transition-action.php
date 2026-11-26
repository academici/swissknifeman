<?php

// Source: generalized from a transition use-case Action + domain event (anonymized)
// Transition - atomic use-case: guard legality + subject right, mutation under
// transaction, domain event AFTER commit (ShouldDispatchAfterCommit).

declare(strict_types=1);

namespace App\Actions\Order;

use App\Enums\OrderStatus;
use App\Events\Order\OrderStatusChanged;
use App\Models\Order;
use App\Services\Order\OrderStatusTransitions;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\ValidationException;

final readonly class ShipOrderAction
{
    public function execute(Order $order, OrderStatus $to = OrderStatus::Shipped): Order
    {
        $from = $order->status;

        // 1) Legality of an edge in a graph (see transitions-registry.php).
        if (! OrderStatusTransitions::canTransition(from: $from, to: $to)) {
            throw ValidationException::withMessages([
                'status' => "Transition {$from->value} → {$to->value} not allowed.",
            ]);
        }

        // 2) Subject Right/context - separate check (guard/policy), is not equal to item 1.
        //    For example: Gate::authorize('canShip', $order) — in the controller/attribute.

        return DB::transaction(function () use ($order, $from, $to): Order {
            $order->status = $to;
            $order->save();

            // ...related mutations in the same transaction boundary (history, etc.)

            // 3) Event - after commit (see event below), otherwise the listener will see
            //    unsaved state or will work on a rolled back transaction.
            OrderStatusChanged::dispatch($order, $from, $to);

            return $order;
        });
    }
}

// --- Domain event (usually in app/Events/Order/OrderStatusChanged.php) -------------
//
// declare(strict_types=1);
//
// namespace App\Events\Order;
//
// use App\Enums\OrderStatus;
// use App\Models\Order;
// use Illuminate\Contracts\Events\ShouldDispatchAfterCommit;
// use Illuminate\Foundation\Events\Dispatchable;
//
// final readonly class OrderStatusChanged implements ShouldDispatchAfterCommit
// {
//     use Dispatchable;
//
//     public function __construct(
//         public Order $order,
//         public OrderStatus $from,
//         public OrderStatus $to,
//     ) {}
// }
// broadcast/listeners — skill php/laravel-broadcasting.
