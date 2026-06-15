---
name: laravel-echo-client
bucket: frontend
version: 0.1.0
description: "Фронтовый realtime-клиент Laravel Echo (Reverb/Pusher) во Vue 3: настройка Echo из runtime-конфига/env, подписка на private/presence-каналы, listen на broadcastAs-события, отписка в onUnmounted, проброс X-Socket-ID в axios. Активировать когда: подключаешь websockets на фронте, делаешь useEcho/useChannel-composable, слушаешь .broadcastAs-событие, видишь window.echo / Echo / laravel-echo / реактивный realtime в Vue."
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

# Skill: Laravel Echo realtime-клиент (фронт)

## Контекст

Фронтовая (browser) сторона Laravel-broadcasting: подключение к Reverb/Pusher через `laravel-echo`, подписка на private/presence-каналы и реакция на серверные события в Vue 3. Применять когда:

- подключаешь websockets на фронте впервые (есть `laravel-echo` в зависимостях, нет/сломан клиент);
- пишешь composable вида `useEcho` / `useChannel` / `use<Домен>Realtime`, который должен подписаться при монтировании и **гарантированно отписаться** при размонтировании;
- слушаешь серверное событие, у которого backend задаёт `broadcastAs()` — имя на фронте начинается с точки (`.order.updated`);
- видишь в коде `window.echo`, `new Echo(...)`, `.private(...)`, `.listen(...)` и нужно понять/починить жизненный цикл подписки;
- realtime «дублируется у инициатора» — нужен `X-Socket-ID` + `toOthers()` на backend.

**Граница**: backend-сторона (события, `ShouldBroadcast`, определение каналов в `routes/channels.php`, авторизация каналов) — это скилл `php/laravel-broadcasting`, не здесь. Здесь — только фронт-композабл и конфиг клиента.

**Laravel Boost**: версионные основы broadcasting — за Boost; здесь — фронт-композабл.

## Алгоритм

1. **Один Echo-инстанс на сессию.** Создавай `window.echo = new Echo({...})` ровно один раз за жизнь страницы (флаг-гард `isEchoInitialized`). Не создавай Echo внутри composable — composable только подписывается на уже готовый `window.echo`.
2. **Runtime-конфиг важнее env.** Параметры подключения (key, host, port, scheme, path) бери из двух слоёв с приоритетом runtime → env → дефолт:
   - **env** (`import.meta.env.VITE_REVERB_*`) — дефолты на этапе сборки;
   - **runtime** — объект, переданный с сервера в браузер (Inertia-проп `page.props`, shared-данные или встроенный `<script>`), позволяет менять окружение **без пересборки фронта**.
   Каждое поле runtime-конфига перекрывает env, только если оно непустое (`if (runtime.host) config.wsHost = runtime.host`). См. `snippets/echo-config.ts`.
3. **broadcaster по бэкенду.** `broadcaster: 'reverb'` для Laravel Reverb, `'pusher'` для Pusher/совместимого. `forceTLS` выводи из scheme (`scheme === 'https'`), `enabledTransports: ['ws', 'wss']`.
4. **Подписка — через composable, не в компоненте.** Компонент вызывает `use<Домен>Realtime(id)`; вся работа с `window.echo` спрятана в composable/адаптере. Внутри:
   - `const channel = window.echo.private(channelName)` для private, `.encryptedPrivate(...)` / `.join(...)` (presence) по типу канала;
   - **гард `if (!window.echo) return () => {}`** — Echo может быть выключен (guest, disabled-режим), подписка должна деградировать в no-op, а не падать.
5. **listen на broadcastAs-имя.** Если backend объявил `public function broadcastAs(): string { return 'order.updated'; }`, на фронте слушай **с ведущей точкой**: `channel.listen('.order.updated', handler)`. Без `broadcastAs()` имя — FQCN-класс события (`.App\\Events\\OrderUpdated`) — хрупко; настаивай на `broadcastAs()` на backend.
6. **Именованный handler — обязателен для отписки.** Передавай в `.listen()` именованную функцию-ссылку, а не инлайн-лямбду, иначе нельзя точечно снять слушатель через `stopListening(eventName, handler)`.
7. **Отписка детерминирована.** На каждую подписку возвращай `dispose`-функцию, которая: `channel.stopListening('.event', handler)` для каждого слушателя, затем `window.echo.leave(channelName)`. Вызывай её в `onUnmounted`. См. `snippets/useEcho.ts`.
8. **Ref-count для разделяемых каналов.** Если один канал (канал доски, канал уведомлений пользователя) слушают несколько компонентов одновременно — веди счётчик подписчиков на имя канала: подписка увеличивает, dispose уменьшает, реальный `leave()` — только когда счётчик дошёл до 0. Иначе размонтирование одного компонента оборвёт realtime у остальных.
9. **Presence — те же правила + участники.** `window.echo.join(channelName)` даёт `.here(users => ...)`, `.joining(user => ...)`, `.leaving(user => ...)`, плюс обычный `.listen(...)`. Отписка та же — `leave(channelName)`. Состояние «кто онлайн» держи в `ref`, наполняй из `here/joining/leaving`.
10. **X-Socket-ID в каждый запрос.** В axios-интерсепторе подставляй `config.headers['X-Socket-ID'] = window.echo?.socketId?.()`, если socketId есть. Это позволяет backend через `broadcast(...)->toOthers()` исключить инициатора из рассылки, чтобы он не получил собственное событие дважды (оптимистичный UI + echo). См. `snippets/axios-socket-id.ts`. То же значение прокидывай в Inertia-визиты через `headers: { 'X-Socket-ID': ... }`.
11. **Очистка при выходе.** При логауте / переходе в guest-контекст вызывай `window.echo.disconnect()` и сбрасывай флаг-гард, чтобы при повторном входе пересоздать соединение с новой авторизацией.

## Жизненный цикл подписки (минимальный контракт)

```
mount/setup ──▶ acquire(channelName): if (!window.echo) return no-op
                  channel = window.echo.private(channelName)
                  channel.listen('.event', namedHandler)
                  return dispose
onUnmounted ──▶ dispose(): channel.stopListening('.event', namedHandler)
                           window.echo.leave(channelName)   // при ref-count: только на 0
```

Нарушение любого звена даёт классические баги: подписка падает у guest (нет гарда), realtime «утекает» после ухода со страницы (нет `leave`), двойные события (инлайн-лямбда не снимается / нет `X-Socket-ID`), мёртвый канал у соседнего компонента (нет ref-count).

## Типы каналов

| Тип | Метод | Когда |
|:---|:---|:---|
| public | `window.echo.channel(name)` | данные без авторизации (редко) |
| private | `window.echo.private(name)` | данные конкретного пользователя/ресурса; авторизация на backend |
| presence | `window.echo.join(name)` | private + список участников (онлайн, «кто печатает») |
| encrypted private | `window.echo.encryptedPrivate(name)` | private с E2E-шифрованием payload |

Имя канала строй из нейтральной доменной модели: `order.${orderId}`, `notifications.user.${userId}`, `documents.board` — без имён реального проекта/клиента.

## Чеклист качества

- [ ] `new Echo(...)` создаётся один раз за сессию (флаг-гард), а не в каждом composable
- [ ] Конфиг собран по приоритету runtime → env → дефолт; runtime перекрывает env только непустыми полями
- [ ] `broadcaster` соответствует backend (`reverb`/`pusher`); `forceTLS` выведен из scheme
- [ ] Подписка инкапсулирована в composable/адаптере, компонент не трогает `window.echo` напрямую
- [ ] Есть гард `if (!window.echo) return () => {}` — деградация в no-op без исключений
- [ ] `listen` использует broadcastAs-имя с ведущей точкой (`.order.updated`)
- [ ] Handler — именованная функция (снимается через `stopListening(event, handler)`)
- [ ] `onUnmounted` вызывает dispose: `stopListening` + `leave(channelName)`
- [ ] Разделяемые каналы под ref-count: `leave()` только когда счётчик подписчиков = 0
- [ ] `X-Socket-ID` подставляется в axios-интерсептор и в Inertia-визиты
- [ ] Никаких имён реального проекта/клиента в именах каналов и payload-типах

## Ссылки

- https://laravel.com/docs/broadcasting (Receiving Broadcasts / Presence Channels)
- https://github.com/laravel/echo
- https://reverb.laravel.com/
- snippets/useEcho.ts, snippets/echo-config.ts, snippets/axios-socket-id.ts
- Связанные скиллы: `php/laravel-broadcasting` (backend: события, каналы, ShouldBroadcast), `frontend/inertia-vue`, `frontend/vue-composition-api`
