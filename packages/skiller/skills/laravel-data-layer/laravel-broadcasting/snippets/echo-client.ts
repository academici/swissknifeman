// Source: anonymized production Laravel project

// resources/js/echo.ts — configuration Laravel Echo (Reverb).
// Installation: npm install --save-dev laravel-echo pusher-js
// IMPORTANT: client env-variables must have a prefix VITE_,
// otherwise import.meta.env.* will return undefined.

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
    // VITE_REVERB_HOST — public address for the browser.
    // Not to be confused with REVERB_SERVER_HOST (what the process is listening on reverb)
    // and REVERB_HOST (address where backend publishes events).
    wsHost: import.meta.env.VITE_REVERB_HOST,
    wsPort: import.meta.env.VITE_REVERB_PORT ?? 80,
    wssPort: import.meta.env.VITE_REVERB_PORT ?? 443,
    forceTLS: (import.meta.env.VITE_REVERB_SCHEME ?? 'https') === 'https',
    enabledTransports: ['ws', 'wss'],

    // Sanctum SPA: authorization of subscriptions via cookie-session + CSRF.
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

// --- Listening to events ---

// Standard event (class App\Events\OrderShipped, without broadcastAs):
window.Echo.private(`orders.${orderId}`).listen('OrderShipped', (e: { id: number }) => {
    console.log(e.id);
});

// Event with broadcastAs('order.shipped') — Prefix dot is REQUIRED:
window.Echo.private(`orders.${orderId}`).listen('.order.shipped', (e: { id: number }) => {
    console.log(e.id);
});

// Broadcast-notifications Laravel on the user's private channel:
window.Echo.private(`App.Models.User.${userId}`).notification((notification: { type: string }) => {
    console.log(notification.type);
});

// Model broadcasting (trait BroadcastsEvents): events .OrderUpdated etc.
window.Echo.private(`App.Models.Order.${orderId}`).listen('.OrderUpdated', (e: unknown) => {
    console.log(e);
});

// Connection management: link indicator, clear when logout.
// window.Echo.connectionStatus(); window.Echo.leaveAllChannels(); window.Echo.disconnect();
