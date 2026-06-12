<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

namespace App\Events;

use App\Models\Order;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PresenceChannel;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Contracts\Events\ShouldDispatchAfterCommit;
use Illuminate\Queue\SerializesModels;

/**
 * Broadcast-событие: уходит в очередь (ShouldBroadcast),
 * отправляется только после commit транзакции (ShouldDispatchAfterCommit).
 *
 * Для синхронной отправки без очереди — implements ShouldBroadcastNow.
 */
class OrderShipped implements ShouldBroadcast, ShouldDispatchAfterCommit
{
    // InteractsWithSockets обязателен для broadcast(...)->toOthers()
    use InteractsWithSockets, SerializesModels;

    public function __construct(public Order $order) {}

    /** Каналы, на которые уходит событие. */
    public function broadcastOn(): array
    {
        return [
            new PrivateChannel('orders.'.$this->order->id),
            new PresenceChannel('warehouse.'.$this->order->warehouse_id),
        ];
    }

    /**
     * Своё имя события вместо FQCN.
     * ВАЖНО: клиент должен слушать с точкой: .listen('.order.shipped').
     */
    public function broadcastAs(): string
    {
        return 'order.shipped';
    }

    /** Явный payload — не утекают лишние атрибуты модели. */
    public function broadcastWith(): array
    {
        return [
            'id' => $this->order->id,
            'status' => $this->order->status,
            'shipped_at' => $this->order->shipped_at?->toIso8601String(),
        ];
    }

    /** Условная отправка: пропускаем «незначимые» изменения. */
    public function broadcastWhen(): bool
    {
        return $this->order->total > 0;
    }

    /** Отдельная очередь для real-time, чтобы не ждать медленные джобы. */
    public function broadcastQueue(): string
    {
        return 'broadcasts';
    }
}

// --- Использование ---
//
// Обычная отправка (через очередь):
//     OrderShipped::dispatch($order);
//
// Исключить отправителя (optimistic UI — клиент уже обновился из ответа API):
//     broadcast(new OrderShipped($order))->toOthers();
//
// Анонимная отправка без класса события:
//     Broadcast::private('orders.'.$order->id)
//         ->as('order.shipped')
//         ->with(['id' => $order->id])
//         ->send();
//
// Model broadcasting — авто-события created/updated/deleted на канал
// App.Models.Order.{id} без отдельных классов событий:
//
//     use Illuminate\Database\Eloquent\BroadcastsEvents;
//
//     class Order extends Model
//     {
//         use BroadcastsEvents;
//
//         public function broadcastOn(string $event): array
//         {
//             return [$this, $this->user];
//         }
//     }
