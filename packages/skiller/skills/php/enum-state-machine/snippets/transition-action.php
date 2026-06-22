<?php

// Source: generalized from a transition use-case Action + domain event (anonymized)
// Переход — атомарный use-case: guard легальности + право субъекта, мутация под
// транзакцией, доменное событие ПОСЛЕ коммита (ShouldDispatchAfterCommit).

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

        // 1) Легальность ребра в графе (см. transitions-registry.php).
        if (! OrderStatusTransitions::canTransition(from: $from, to: $to)) {
            throw ValidationException::withMessages([
                'status' => "Переход {$from->value} → {$to->value} не разрешён.",
            ]);
        }

        // 2) Право субъекта/контекста — отдельная проверка (guard/policy), не равно п.1.
        //    Например: Gate::authorize('canShip', $order) — в контроллере/атрибуте.

        return DB::transaction(function () use ($order, $from, $to): Order {
            $order->status = $to;
            $order->save();

            // ...связанные мутации в той же транзакционной границе (история и т.п.)

            // 3) Событие — после коммита (см. событие ниже), иначе слушатель увидит
            //    несохранённое состояние или отработает на откаченной транзакции.
            OrderStatusChanged::dispatch($order, $from, $to);

            return $order;
        });
    }
}

// --- Доменное событие (обычно в app/Events/Order/OrderStatusChanged.php) -------------
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
// broadcast/listeners — скилл php/laravel-broadcasting.
