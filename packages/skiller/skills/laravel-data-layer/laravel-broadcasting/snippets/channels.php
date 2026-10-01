<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

// routes/channels.php — authorization broadcast-channels.
// Check that the file is included in bootstrap/app.php: ->withRouting(channels: ...).
// List of registered channels: php artisan channel:list

use App\Models\Order;
use App\Models\User;
use Illuminate\Support\Facades\Broadcast;

// Private-channel: return bool.
Broadcast::channel('orders.{orderId}', function (User $user, int $orderId) {
    return $user->id === Order::findOrNew($orderId)->user_id;
});

// Model binding: Laravel itself resolves the model from the channel parameter.
Broadcast::channel('orders.{order}', function (User $user, Order $order) {
    return $user->id === $order->user_id;
});

// Presence-channel: return ARRAY of user data, NOT true.
// Return true — subscription will not work silently.
Broadcast::channel('warehouse.{warehouseId}', function (User $user, int $warehouseId) {
    if (! $user->worksAt($warehouseId)) {
        return false;
    }

    return [
        'id' => $user->id,
        'name' => $user->name,
    ];
});

// Several guard'ov: the channel is available and web-, and admin-users.
Broadcast::channel('announcements', function ($user) {
    return true;
}, ['guards' => ['web', 'admin']]);

// Complex authorization - channel-class with DI:
//     php artisan make:channel OrderChannel
//
// Broadcast::channel('orders.{order}', OrderChannel::class);
