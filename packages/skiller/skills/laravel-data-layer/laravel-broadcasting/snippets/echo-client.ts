// Source: anonymized production Laravel project

// resources/js/echo.ts — конфигурация Laravel Echo (Reverb).
// Установка: npm install --save-dev laravel-echo pusher-js
// ВАЖНО: клиентские env-переменные обязаны иметь префикс VITE_,
// иначе import.meta.env.* вернёт undefined.

import Echo from 'laravel-echo';
import Pusher from 'pusher-js';

declare global {
    interface Window {
        Pusher: typeof Pusher;
        Echo: Echo<'reverb'>;
    }
}

window.Pusher = Pusher;

window.Echo = new Echo({
    broadcaster: 'reverb',
    key: import.meta.env.VITE_REVERB_APP_KEY,
    // VITE_REVERB_HOST — публичный адрес для браузера.
    // Не путать с REVERB_SERVER_HOST (на чём слушает процесс reverb)
    // и REVERB_HOST (адрес, по которому backend публикует события).
    wsHost: import.meta.env.VITE_REVERB_HOST,
    wsPort: import.meta.env.VITE_REVERB_PORT ?? 80,
    wssPort: import.meta.env.VITE_REVERB_PORT ?? 443,
    forceTLS: (import.meta.env.VITE_REVERB_SCHEME ?? 'https') === 'https',
    enabledTransports: ['ws', 'wss'],

    // Sanctum SPA: авторизация подписок через cookie-сессию + CSRF.
    authEndpoint: '/broadcasting/auth',
    authorizer: (channel) => ({
        authorize: (socketId: string, callback: Function) => {
            window.axios
                .post(
                    '/broadcasting/auth',
                    { socket_id: socketId, channel_name: channel.name },
                    { withCredentials: true },
                )
                .then((response) => callback(null, response.data))
                .catch((error) => callback(error, null));
        },
    }),
});

// --- Прослушивание событий ---

// Стандартное событие (класс App\Events\OrderShipped, без broadcastAs):
window.Echo.private(`orders.${orderId}`).listen('OrderShipped', (e: { id: number }) => {
    console.log(e.id);
});

// Событие с broadcastAs('order.shipped') — ОБЯЗАТЕЛЬНА точка-префикс:
window.Echo.private(`orders.${orderId}`).listen('.order.shipped', (e: { id: number }) => {
    console.log(e.id);
});

// Broadcast-нотификации Laravel на приватном канале пользователя:
window.Echo.private(`App.Models.User.${userId}`).notification((notification: { type: string }) => {
    console.log(notification.type);
});

// Model broadcasting (трейт BroadcastsEvents): события .OrderUpdated и т.п.
window.Echo.private(`App.Models.Order.${orderId}`).listen('.OrderUpdated', (e: unknown) => {
    console.log(e);
});

// Управление подключением: индикатор связи, очистка при logout.
// window.Echo.connectionStatus(); window.Echo.leaveAllChannels(); window.Echo.disconnect();
