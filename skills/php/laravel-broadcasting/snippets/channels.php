<?php

// Source: anonymized production Laravel project

declare(strict_types=1);

// routes/channels.php — авторизация broadcast-каналов.
// Проверьте, что файл подключён в bootstrap/app.php: ->withRouting(channels: ...).
// Список зарегистрированных каналов: php artisan channel:list

use App\Models\Order;
use App\Models\User;
use Illuminate\Support\Facades\Broadcast;

// Private-канал: возвращаем bool.
Broadcast::channel('orders.{orderId}', function (User $user, int $orderId) {
    return $user->id === Order::findOrNew($orderId)->user_id;
});

// Model binding: Laravel сам резолвит модель из параметра канала.
Broadcast::channel('orders.{order}', function (User $user, Order $order) {
    return $user->id === $order->user_id;
});

// Presence-канал: возвращаем МАССИВ данных пользователя, НЕ true.
// Вернуть true — подписка молча не сработает.
Broadcast::channel('warehouse.{warehouseId}', function (User $user, int $warehouseId) {
    if (! $user->worksAt($warehouseId)) {
        return false;
    }

    return [
        'id' => $user->id,
        'name' => $user->name,
    ];
});

// Несколько guard'ов: канал доступен и web-, и admin-пользователям.
Broadcast::channel('announcements', function ($user) {
    return true;
}, ['guards' => ['web', 'admin']]);

// Сложная авторизация — канал-класс с DI:
//     php artisan make:channel OrderChannel
//
// Broadcast::channel('orders.{order}', OrderChannel::class);
