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
 * Broadcast-event: goes into queue (ShouldBroadcast),
 * is sent only after commit transactions (ShouldDispatchAfterCommit).
 *
 * For synchronous sending without queue - implements ShouldBroadcastNow.
 */
class OrderShipped implements ShouldBroadcast, ShouldDispatchAfterCommit
{
    // InteractsWithSockets is required for broadcast(...)->toOthers()
    use InteractsWithSockets, SerializesModels;

    public function __construct(public Order $order) {}

    /** Channels to which the event goes. */
    public function broadcastOn(): array
    {
        return [
            new PrivateChannel('orders.'.$this->order->id),
            new PresenceChannel('warehouse.'.$this->order->warehouse_id),
        ];
    }

    /**
     * Your event name instead FQCN.
     * IMPORTANT: The client must listen with a period: .listen('.order.shipped').
     */
    public function broadcastAs(): string
    {
        return 'order.shipped';
    }

    /** Explicit payload — does not leak unnecessary model attributes. */
    public function broadcastWith(): array
    {
        return [
            'id' => $this->order->id,
            'status' => $this->order->status,
            'shipped_at' => $this->order->shipped_at?->toIso8601String(),
        ];
    }

    /** Conditional send: skip «insignificant» changes. */
    public function broadcastWhen(): bool
    {
        return $this->order->total > 0;
    }

    /** Separate queue for real-time, so as not to wait for slow jobs. */
    public function broadcastQueue(): string
    {
        return 'broadcasts';
    }
}

// --- Usage ---
//
// Normal sending (via queue):
//     OrderShipped::dispatch($order);
//
// Exclude sender (optimistic UI — client has already updated from response API):
//     broadcast(new OrderShipped($order))->toOthers();
//
// Anonymous dispatch without event class:
//     Broadcast::private('orders.'.$order->id)
//         ->as('order.shipped')
//         ->with(['id' => $order->id])
//         ->send();
//
// Model broadcasting — auto-events created/updated/deleted per channel
// App.Models.Order.{id} without separate event classes:
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
