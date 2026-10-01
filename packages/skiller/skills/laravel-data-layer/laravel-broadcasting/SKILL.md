---
name: laravel-broadcasting
bucket: laravel-data-layer
version: 0.1.1
description: "Use for Laravel broadcast events, channel auth, Echo/Reverb/Pusher/Ably integration."
risk: write
persona: oss-dev
tags: ["php", "laravel", "broadcasting", "echo", "reverb", "websockets", "realtime"]
requires: []
produces_for: []
outputs: []
snippets:
  - broadcast-event.php
  - channels.php
  - echo-client.ts
  - presence-whisper.ts
adapters: [claude, cursor, fable]
sha256: ""
---

## Context

Real-time events in Laravel: server part (events `ShouldBroadcast`, channel authorization) + client (Laravel Echo on top Reverb/Pusher/Ably). The skill is activated when setting up broadcasting, creation broadcast-events, presence-channels, whisper, model broadcasting.

## Algorithm

1. **Installation**: `php artisan install:broadcasting` (flags `--reverb`/`--pusher`/`--ably`). Creates `config/broadcasting.php` and `routes/channels.php`.
2. **Event**: `php artisan make:event OrderShipped`, implement the interface:
   - `ShouldBroadcast` — via queue (needed `queue:work`);
   - `ShouldBroadcastNow` — synchronously (dev, time-critical);
   - `ShouldDispatchAfterCommit` — after commit transactions (protection against race condition).
3. **Event setup**: `broadcastOn()` (Channel/PrivateChannel/PresenceChannel), optional `broadcastAs()` (your name), `broadcastWith()` (control payload), `broadcastWhen()` (condition).
4. **Authorization**: closures in `routes/channels.php`; for public-channels are not needed, private — bool, presence — array of user data. Complex logic - `php artisan make:channel`. Check: `php artisan channel:list`.
5. **Client**: `npm i -D laravel-echo pusher-js`, config Echo from `VITE_REVERB_*` variables; `Echo.private().listen()`, `Echo.join()` (presence), `whisper()/listenForWhisper()` (client-client without server).
6. **Processes**: `php artisan queue:work` (for ShouldBroadcast) + `php artisan reverb:start` (for Reverb).
7. **Model broadcasting**: trait `BroadcastsEvents` on the model - auto-events created/updated/deleted/trashed/restored per channel `App.Models.Order.{id}`.

## When to open which snippet

| Situation | File |
|---|---|
| I create broadcast-event (broadcastOn/As/With/When, toOthers) | `snippets/broadcast-event.php` |
| Setting up channel authorization (private, presence, model binding) | `snippets/channels.php` |
| Configuring Echo on the client, listening to events and notifications | `snippets/echo-client.ts` |
| Presence-channel (who is online) and whisper (typing-indicator) | `snippets/presence-whisper.ts` |

## Typical rake

- **Queue worker should work** for `ShouldBroadcast` — otherwise events «silently» are piling up in the queue. B dev use `ShouldBroadcastNow`.
- **`BROADCAST_CONNECTION`, not `BROADCAST_DRIVER`** — Laravel 11+ renamed env-key.
- **`toOthers()`** requires trait `InteractsWithSockets` And the title `X-Socket-ID`. Echo itself adds it to the global Axios; for `fetch` send `Echo.socketId()` manually.
- **`VITE_`-prefix is required** for client env-variables - without it `import.meta.env.*` will return undefined.
- **Reverb — long-running process**: code changes require `php artisan reverb:restart`.
- **Presence-authorization returns an array** user data (`['id' => ..., 'name' => ...]`), not `true` — otherwise the subscription silently drops.
- **Prefix dot when `broadcastAs()`**: client listening `.listen('.custom.name')`. Without dot Echo looking for `App\Events\custom.name` and silently does not find it.
- **Three levels Reverb-host**: `REVERB_SERVER_HOST/PORT` (what the process is listening on), `REVERB_HOST/PORT` (public address for backend), `VITE_REVERB_HOST/PORT` (browser address). B Docker/behind the proxy they differ.
- **Sanctum SPA**: `/broadcasting/auth` under `auth:sanctum`, CSRF + `withCredentials: true` in authorizer; for different origin — add path to `config/cors.php` and `supports_credentials: true`.
- **`channels.php` not loaded**: check `withRouting(channels: ...)` in `bootstrap/app.php`.

## Quality checklist

- [ ] Correct interface selected (Now for dev, AfterCommit when creating records in a transaction)
- [ ] `broadcastWith()` does not leak sensitive model attributes
- [ ] Presence-authorization returns an array, private — bool
- [ ] Client uses prefix dot if specified `broadcastAs()`
- [ ] Both processes are running: queue worker and reverb (or configured supervisor)
- [ ] env spaced: REVERB_SERVER_* / REVERB_* / VITE_REVERB_*

## Links

- https://laravel.com/docs/broadcasting
- https://laravel.com/docs/reverb
- https://github.com/laravel/echo
