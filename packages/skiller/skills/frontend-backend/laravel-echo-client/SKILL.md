---
name: laravel-echo-client
bucket: frontend-backend
version: 0.1.0
description: "Frontend realtime client Laravel Echo (Reverb/Pusher) in Vue 3: configure Echo from runtime-config/env, subscribe to private/presence channels, listen on broadcastAs events, unsubscribe in onUnmounted, inject X-Socket-ID into axios. Activate wiring websockets on frontend, useEcho/useChannel composable, .broadcastAs event, window.echo/laravel-echo in Vue."
risk: write
persona: oss-dev
tags: [laravel-echo, reverb, pusher, websockets, realtime, vue, broadcasting, frontend]
requires: []
produces_for: []
outputs: []
snippets: [useEcho.ts, echo-config.ts, axios-socket-id.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Laravel Echo realtime client (frontend)

Browser side of Laravel broadcasting: connect to Reverb/Pusher via `laravel-echo`, subscribe to private/presence channels, react to server events in Vue 3.

**Boundary**: backend (events, `ShouldBroadcast`, channel definitions in `routes/channels.php`, channel auth) → skill `laravel-data-layer/laravel-broadcasting`, NOT here. Here = frontend composable + client config only. Versioned broadcasting basics → Laravel Boost.

## Rules

- **One Echo instance per session.** Create `window.echo = new Echo({...})` exactly once per page lifetime (guard flag `isEchoInitialized`). Never create Echo inside a composable — composable only subscribes to ready `window.echo`.
- **Runtime config > env.** Connection params (key, host, port, scheme, path) from two layers, priority runtime → env → default:
  - **env** (`import.meta.env.VITE_REVERB_*`) — build-time defaults;
  - **runtime** — object passed from server to browser (Inertia prop `page.props`, shared data, or inline `<script>`); changes environment without rebuilding frontend.
  Each runtime field overrides env only if non-empty (`if (runtime.host) config.wsHost = runtime.host`). See `snippets/echo-config.ts`.
- **broadcaster per backend.** `broadcaster: 'reverb'` for Reverb, `'pusher'` for Pusher/compatible. Derive `forceTLS` from scheme (`scheme === 'https'`); `enabledTransports: ['ws', 'wss']`.
- **Subscribe via composable, not in component.** Component calls `use<Domain>Realtime(id)`; all `window.echo` work hidden in composable/adapter. Inside:
  - `const channel = window.echo.private(channelName)` for private; `.encryptedPrivate(...)` / `.join(...)` (presence) per channel type;
  - **guard `if (!window.echo) return () => {}`** — Echo may be off (guest, disabled mode); subscription degrades to no-op, not crash.
- **listen on broadcastAs name.** If backend declares `public function broadcastAs(): string { return 'order.updated'; }`, listen on frontend **with leading dot**: `channel.listen('.order.updated', handler)`. Without `broadcastAs()` the name is event FQCN (`.App\\Events\\OrderUpdated`) — fragile; insist on `broadcastAs()` on backend.
- **Named handler required for unsubscribe.** Pass a named function reference to `.listen()`, not inline lambda — otherwise can't remove listener via `stopListening(eventName, handler)`.
- **Deterministic unsubscribe.** Per subscription return a `dispose` fn that: `channel.stopListening('.event', handler)` per listener, then `window.echo.leave(channelName)`. Call it in `onUnmounted`. See `snippets/useEcho.ts`.
- **Ref-count for shared channels.** If one channel (board channel, user notifications channel) is listened by multiple components at once — keep a subscriber counter per channel name: subscribe increments, dispose decrements, real `leave()` only when counter hits 0. Else unmounting one component breaks realtime for the rest.
- **Presence = same rules + participants.** `window.echo.join(channelName)` gives `.here(users => ...)`, `.joining(user => ...)`, `.leaving(user => ...)`, plus normal `.listen(...)`. Unsubscribe same — `leave(channelName)`. Keep "who is online" state in a `ref`, fill from `here/joining/leaving`.
- **X-Socket-ID in every request.** In axios interceptor set `config.headers['X-Socket-ID'] = window.echo?.socketId?.()` if socketId exists. Lets backend `broadcast(...)->toOthers()` exclude initiator from broadcast (avoid own event twice: optimistic UI + echo). See `snippets/axios-socket-id.ts`. Pass same value to Inertia visits via `headers: { 'X-Socket-ID': ... }`.
- **Cleanup on logout.** On logout / switch to guest context call `window.echo.disconnect()` and reset guard flag, so re-login recreates connection with new auth.

## Subscription lifecycle (minimal contract)

```
mount/setup ──▶ acquire(channelName): if (!window.echo) return no-op
                  channel = window.echo.private(channelName)
                  channel.listen('.event', namedHandler)
                  return dispose
onUnmounted ──▶ dispose(): channel.stopListening('.event', namedHandler)
                           window.echo.leave(channelName)   // with ref-count: only at 0
```

Breaking any link → classic bugs: subscription crashes for guest (no guard), realtime "leaks" after leaving page (no `leave`), double events (inline lambda not removed / no `X-Socket-ID`), dead channel for sibling component (no ref-count).

## Channel types

| Type | Method | When |
|:---|:---|:---|
| public | `window.echo.channel(name)` | data without auth (rare) |
| private | `window.echo.private(name)` | data of specific user/resource; auth on backend |
| presence | `window.echo.join(name)` | private + participant list (online, "who is typing") |
| encrypted private | `window.echo.encryptedPrivate(name)` | private with E2E-encrypted payload |

Build channel name from neutral domain model: `order.${orderId}`, `notifications.user.${userId}`, `documents.board` — no real project/client names.

## Quality checklist

- [ ] `new Echo(...)` created once per session (guard flag), not per composable
- [ ] Config built priority runtime → env → default; runtime overrides env only with non-empty fields
- [ ] `broadcaster` matches backend (`reverb`/`pusher`); `forceTLS` derived from scheme
- [ ] Subscription encapsulated in composable/adapter, component never touches `window.echo` directly
- [ ] Guard `if (!window.echo) return () => {}` — degrades to no-op without exceptions
- [ ] `listen` uses broadcastAs name with leading dot (`.order.updated`)
- [ ] Handler is named function (removable via `stopListening(event, handler)`)
- [ ] `onUnmounted` calls dispose: `stopListening` + `leave(channelName)`
- [ ] Shared channels under ref-count: `leave()` only when subscriber counter = 0
- [ ] `X-Socket-ID` injected into axios interceptor and Inertia visits
- [ ] No real project/client names in channel names and payload types

## Links

- https://laravel.com/docs/broadcasting (Receiving Broadcasts / Presence Channels)
- https://github.com/laravel/echo
- https://reverb.laravel.com/
- snippets/useEcho.ts, snippets/echo-config.ts, snippets/axios-socket-id.ts
- Related skills: `laravel-data-layer/laravel-broadcasting` (backend: events, channels, ShouldBroadcast), `frontend-backend/inertia-vue`, `frontend-vue/vue-composition-api`, `frontend-vue/pinia-stores` (realtime "who is online"/notifications state in store, store access from ws-adapter outside component)

<!-- ru-source-sha256: 389f4932933c877ebe39c7552c899712e5676e66c13d89a52c9c563072618991 -->
