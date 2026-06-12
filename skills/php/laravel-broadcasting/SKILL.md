---
name: laravel-broadcasting
bucket: php
version: 0.1.0
description: "Laravel Echo + Reverb/Pusher/Ably: broadcast-события, авторизация каналов, presence/whisper, model broadcasting"
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

## Контекст

Real-time события в Laravel: серверная часть (события `ShouldBroadcast`, авторизация каналов) + клиентская (Laravel Echo поверх Reverb/Pusher/Ably). Скилл активируется при настройке broadcasting, создании broadcast-событий, presence-каналах, whisper, model broadcasting.

## Алгоритм

1. **Установка**: `php artisan install:broadcasting` (флаги `--reverb`/`--pusher`/`--ably`). Создаёт `config/broadcasting.php` и `routes/channels.php`.
2. **Событие**: `php artisan make:event OrderShipped`, имплементировать интерфейс:
   - `ShouldBroadcast` — через очередь (нужен `queue:work`);
   - `ShouldBroadcastNow` — синхронно (dev, time-critical);
   - `ShouldDispatchAfterCommit` — после commit транзакции (защита от race condition).
3. **Настройка события**: `broadcastOn()` (Channel/PrivateChannel/PresenceChannel), опционально `broadcastAs()` (своё имя), `broadcastWith()` (контроль payload), `broadcastWhen()` (условие).
4. **Авторизация**: closures в `routes/channels.php`; для public-каналов не нужна, private — bool, presence — массив данных пользователя. Сложная логика — `php artisan make:channel`. Проверка: `php artisan channel:list`.
5. **Клиент**: `npm i -D laravel-echo pusher-js`, конфиг Echo из `VITE_REVERB_*` переменных; `Echo.private().listen()`, `Echo.join()` (presence), `whisper()/listenForWhisper()` (клиент-клиент без сервера).
6. **Процессы**: `php artisan queue:work` (для ShouldBroadcast) + `php artisan reverb:start` (для Reverb).
7. **Model broadcasting**: трейт `BroadcastsEvents` на модели — авто-события created/updated/deleted/trashed/restored на канал `App.Models.Order.{id}`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Создаю broadcast-событие (broadcastOn/As/With/When, toOthers) | `snippets/broadcast-event.php` |
| Настраиваю авторизацию каналов (private, presence, model binding) | `snippets/channels.php` |
| Конфигурирую Echo на клиенте, слушаю события и нотификации | `snippets/echo-client.ts` |
| Presence-канал (кто онлайн) и whisper (typing-индикатор) | `snippets/presence-whisper.ts` |

## Типичные грабли

- **Queue worker должен работать** для `ShouldBroadcast` — иначе события «молча» копятся в очереди. В dev используйте `ShouldBroadcastNow`.
- **`BROADCAST_CONNECTION`, не `BROADCAST_DRIVER`** — Laravel 11+ переименовал env-ключ.
- **`toOthers()`** требует трейт `InteractsWithSockets` И заголовок `X-Socket-ID`. Echo сам добавляет его в глобальный Axios; для `fetch` шлите `Echo.socketId()` вручную.
- **`VITE_`-префикс обязателен** для клиентских env-переменных — без него `import.meta.env.*` вернёт undefined.
- **Reverb — long-running процесс**: изменения кода требуют `php artisan reverb:restart`.
- **Presence-авторизация возвращает массив** данных пользователя (`['id' => ..., 'name' => ...]`), не `true` — иначе подписка молча падает.
- **Точка-префикс при `broadcastAs()`**: клиент слушает `.listen('.custom.name')`. Без точки Echo ищет `App\Events\custom.name` и молча не находит.
- **Три уровня Reverb-host**: `REVERB_SERVER_HOST/PORT` (на чём слушает процесс), `REVERB_HOST/PORT` (публичный адрес для backend), `VITE_REVERB_HOST/PORT` (адрес для браузера). В Docker/за прокси они различаются.
- **Sanctum SPA**: `/broadcasting/auth` под `auth:sanctum`, CSRF + `withCredentials: true` в authorizer; при разных origin — добавить путь в `config/cors.php` и `supports_credentials: true`.
- **`channels.php` не загружен**: проверьте `withRouting(channels: ...)` в `bootstrap/app.php`.

## Чеклист качества

- [ ] Выбран правильный интерфейс (Now для dev, AfterCommit при создании записей в транзакции)
- [ ] `broadcastWith()` не утекает чувствительные атрибуты модели
- [ ] Presence-авторизация возвращает массив, private — bool
- [ ] Клиент использует точку-префикс, если задан `broadcastAs()`
- [ ] Запущены оба процесса: queue worker и reverb (или настроен supervisor)
- [ ] env разнесён: REVERB_SERVER_* / REVERB_* / VITE_REVERB_*

## Ссылки

- https://laravel.com/docs/broadcasting
- https://laravel.com/docs/reverb
- https://github.com/laravel/echo
