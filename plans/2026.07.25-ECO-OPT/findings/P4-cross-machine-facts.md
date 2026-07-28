# P4 — внешние факты cross-machine памяти (слой 1, 2026-07-25)

Захват в день получения (§16 immediate-capture). Карта классов, по которой шёл поиск, —
`research/05-P4-fact-classes.md` (написана ДО запросов, D20). Синтез — `research/06-P4-target-design.md`.

Дисциплина источников: свойства **установленного** пакета `@agentmemory/agentmemory@0.9.27`
снимались прямым чтением артефакта в `packages/maind/node_modules/@agentmemory/agentmemory`
(README + собранный `dist/index.mjs`) — это внешний факт, верифицированный по первоисточнику,
а не по памяти; поведение Claude Code — first-party дока; сеть/эксплуатация — Tailscale-дока и
полевая практика (perplexity-web).

---

## §1 — Tailscale: как публикуется loopback-сервис и что даёт аутентификацию (FC-1)

Источник: perplexity-web 2026-07-25 → tailscale.com/docs/reference/tailscale-cli/serve ·
/docs/features/access-control/acls · /docs/reference/reserved-ip-addresses.

- **`tailscale serve` проксирует ТОЛЬКО loopback-бэкенд**: «для reverse proxy поддерживается
  только `http://127.0.0.1` / `localhost`». Практически:
  `tailscale serve --http=4111 127.0.0.1:4111` — сервис остаётся на 127.0.0.1, Tailscale
  публикует его внутри tailnet по MagicDNS-имени; `tailscale serve --https=443 127.0.0.1:4111` —
  тот же бэкенд с TLS, терминируемым демоном Tailscale. Это публикация **внутри tailnet**;
  публичный интернет — отдельная команда `tailscale funnel` (её не используем).
- **Цена варианта serve**: бэкенд видит соединение от локального прокси, а не оригинальный
  client IP ⇒ авторизация «по адресу источника» на стороне приложения невозможна.
- **Bind на tailnet-IP (100.64.0.0/10)** — второй вариант: приложение слушает конкретный 100.x
  вместо loopback; плюс — прямое TCP-соединение и видимый client IP; минусы — адрес может
  смениться при переинициализации узла, и сервис перестаёт быть loopback-only.
- **Bind `0.0.0.0` + firewall** — максимальная поверхность атаки (слушает на всех интерфейсах,
  включая LAN/Wi-Fi), защита целиком зависит от корректности локальных правил.
- **Что тут «аутентификация»:** не логин в HTTP-сервис, а членство устройства/пользователя в
  tailnet + политика. Модель **deny-by-default**; ограничение до одного порта:
  ACL `{"action":"accept","src":["<user|group|tag>"],"dst":["<host>:4111"]}` либо grants
  `{"src":[…],"dst":["<host>"],"ip":["tcp:4111"]}` (grants — рекомендуемый современный синтаксис,
  ACL поддерживаются и не удаляются).
- **Key expiry работает как предохранитель**: при истечении ключа устройство перестаёт быть
  действующим участником tailnet — доступ через `serve` и прямой bind на 100.x отваливается
  автоматически. Важное следствие: у варианта `0.0.0.0`+firewall этот предохранитель НЕ работает —
  сервис остаётся доступен по другим интерфейсам.

**Вердикт для P4:** вариант `tailscale serve` на loopback совместим с текущим
`iii-config.yaml` (`host: 127.0.0.1`) БЕЗ его правки; выбор транспорта в ADR идёт между ним и
bind на 100.x, `0.0.0.0` — только как явно отклонённый.

---

## §2 — agentmemory 0.9.27: сеть, аутентификация, remote-режим (FC-2)

Источник: прямое чтение установленного пакета (2026-07-25).

- **Bind по умолчанию — loopback, и это документировано как дефолт, а не как ограничение**:
  «128 endpoints on port `3111`. The REST API binds to `127.0.0.1` by default» (README §API).
  Наш узел использует тот же механизм с переопределёнными портами: `iii-http host: 127.0.0.1`,
  порт 4111 (`packages/maind/config/memory/iii-config.yaml`).
- **Встроенная аутентификация ЕСТЬ — bearer-токен `AGENTMEMORY_SECRET`**: «Protected endpoints
  require `Authorization: Bearer <secret>` when `AGENTMEMORY_SECRET` is set, and mesh sync
  endpoints require `AGENTMEMORY_SECRET` on both peers» (README §API). В коде это глобальный
  middleware: `registerApiTriggers` регистрирует `middleware::api-auth`, который при заданном
  секрете отвечает `401 {"error":"unauthorized"}` на любой запрос без корректного
  `Bearer` (`dist/index.mjs:20209-20221`, сравнение — `timingSafeCompare`).
  **Если секрет НЕ задан — middleware пропускает всё (`if (!secret) return {action:"continue"}`)**,
  то есть сетевая экспозиция без секрета = анонимный доступ на чтение И запись памяти.
- **`GET /agentmemory/health` — «always public»** (README, таблица endpoint'ов): healthcheck
  работает и без токена. Это же значит, что «демон отвечает» ≠ «наши вызовы авторизованы».
- **Remote-deployment — поддерживаемый сценарий upstream**: «For remote or protected deployments,
  launch Claude Code with `AGENTMEMORY_URL` and `AGENTMEMORY_SECRET` set» (README §MCP);
  готовые деплой-шаблоны (fly/railway/render/coolify) «overwrite the npm-bundled iii config
  (which binds `127.0.0.1`) with a deploy-tuned one that binds `0.0.0.0`… generates the HMAC
  secret, then drops privileges» и публикуют **только порт 3111**, оставляя вьюер на loopback с
  SSH-туннелем (README §Deploy).
- **Прецедент «не-loopback bind обязан иметь секрет»** есть внутри самого пакета — для вьюера это
  жёсткий отказ старта: `AGENTMEMORY_VIEWER_HOST=<не-loopback> requires AGENTMEMORY_SECRET to be
  set so the viewer can validate inbound bearer tokens` (`dist/index.mjs:15276`), плюс требование
  `VIEWER_ALLOWED_HOSTS` (`:15277`). Для основного REST-порта такого жёсткого гейта в коде НЕТ —
  правило приходится держать на своей стороне.
- **Консоль/вьюер:** «no auth is enforced on the console itself — keep it bound to `127.0.0.1`
  (the default) and never expose it publicly» (README §Viewer).

**Вердикт для P4:** удалённый режим — штатный для движка; безопасная конфигурация = bearer-секрет
на хосте + доступ только из tailnet. Наш клиент к этому **не готов**: `core/http.py`
(`http_get_json`/`http_post_json`/`ping`) не умеет передавать заголовки вовсе — при включённом
секрете все вызовы `maind` получат `HTTP 401`.

---

## §3 — Mesh-sync внутри agentmemory: что это и почему не заменяет вариант 1 (FC-2/FC-3, побочное)

Источник: прямое чтение `dist/index.mjs:10177-10400` + README (`memory_mesh_sync` — «P2P sync
between instances»).

В 0.9.27 существует **встроенная P2P-синхронизация** между инстансами: `mem::mesh-register`
(регистрация пира по URL) · `mem::mesh-list` · `mem::mesh-sync` (`direction: push|pull|both`,
эндпойнты `POST /agentmemory/mesh/receive` и `GET /agentmemory/mesh/export?since=…`,
`AbortSignal.timeout(30000)`, `redirect:"error"`). Свойства, важные для решения:

1. **Мерж — LWW по таймстемпу**: `lwwMergeList` перезаписывает запись, если
   `new Date(ts) > new Date(existingTs)` (`:10212-10258`). Разрешения конфликтов сверх этого нет.
2. **Требуется секрет на обоих концах**: без него — `{"success":false,"error":"mesh sync requires
   AGENTMEMORY_SECRET"}` (`:10307-10311`).
3. **Приватные адреса пиров ЗАПРЕЩЕНЫ**: `isAllowedUrl` отклоняет `localhost` и приватные IP
   (`:10187-10202`), а `isPrivateIP` (`:10178-10186`) покрывает `127.0.0.1`, `::1`, `0.0.0.0`,
   `10.*`, `192.168.*`, `172.16–31.*`, `169.254.169.254`, `fe80:/fc00:/fd*`.
   **Диапазон Tailscale `100.64.0.0/10` в этот список НЕ входит** ⇒ mesh поверх tailnet-IP
   формально проходит, а mesh поверх обычного LAN (`192.168.*`/`10.*`) — блокируется движком.

**Вердикт:** mesh — это upstream-реализация «варианта 2» стаба (event-sync + LWW), а не
альтернатива варианту 1. Он не снимает ни одной причины выбора D4 (единственный писатель,
целостность scope-маркеров, отсутствие своего конфликт-резолвера), зато добавляет два писателя и
LWW-перетирание. Факт зафиксирован здесь, потому что при выборе ADR владельцу его нужно
предъявить как существующую опцию, а не умолчать.

---

## §4 — Формат стора и чем доказывается «единственный писатель» (FC-3)

Источник: прямое чтение живого узла + конфига (2026-07-25).

- `store_method: file_based`, `file_path: ./data/state_store.db` (`config/memory/iii-config.yaml`).
  Фактически `state_store.db` — **каталог**, а не файл: 9 файлов `mem%3A*.bin` общим объёмом
  **6,4 МБ** (`packages/maind/data/state_store.db/`), каждый — целый scope одним JSON-объектом
  (`mem%3Amemories.bin`, `mem%3Aaudit.bin`, `mem%3Aindex%3Abm25*.bin`).
- **Поправка к формулировке стаба** (`roadmap/cross-machine-memory.md` говорит о «бинарном
  SQLite/индексе»): физически это не SQLite. Запрет file-sync от этого не слабеет, а **усиливается**:
  при пофайловой синхронизации двух писателей конфликт разрешается перезаписью **целого scope**
  (все факты разом), а не отдельной записи. Слой 1 задним числом не переписывается — это
  датированная поправка.
- **Наблюдаемые доказательства «писатель ровно один»** (годятся как машинные гейты):
  (а) на клиенте отсутствует systemd-юнит `maind-memory.service` и нет живого pidfile
  `data/agentmemory.pid`; (б) на клиенте порт 4111 никем не занят; (в) `config.memory.url`
  клиента указывает на хост, а не на loopback. Косвенный, но полезный признак — audit-журнал
  движка (`mem%3Aaudit.bin`, `recordAudit`) фиксирует источник операций.

---

## §5 — Бэкап/восстановление (FC-4)

Источники: прямое чтение пакета (endpoint'ы) + perplexity-web 2026-07-25 (практика).

- У движка есть **app-level экспорт**: `GET /agentmemory/export` («Export all data», README
  §API) и инструмент `memory_snapshot_create` («Git-versioned snapshot»), опция `SNAPSHOT_ENABLED`.
  У `maind` уже используется родственный `GET /agentmemory/memories?namespace=`
  (`memory.export()`).
- **Практика (perplexity, 2026-07-25):** `cp`/`rsync` каталога на живом демоне даёт не «старую» и
  не «новую» версию, а **смесь состояний** — даже при атомарной записи отдельного файла снимок
  каталога не является точкой во времени. Предпочтительный порядок: app-level export (приложение
  само собирает согласованный снимок) → остановка демона на короткое окно → снимок тома/ФС.
- Проверка целостности — многоуровневая: checksum артефакта → валидация структуры → **тестовое
  восстановление в изолированную среду со smoke-тестом чтения** («самый сильный тест — поднятый из
  бэкапа сервис читает все ключевые объекты»). Рядом с экспортом держать manifest: размер,
  sha256, версия схемы, timestamp.
- Ретеншн для персональной агентной памяти: оперативное окно 7–30 дней + 1–3 месячных точки;
  важнее срока — соответствие RPO/RTO и периодическая проверка восстановлением.

---

## §6 — Офлайн-деградация: полевая практика (FC-5)

Источник: perplexity-web 2026-07-25 (web).

- Консенсус: **чтение — fail-soft** (агент продолжает без памяти, но с явным режимом «memory
  unavailable» и журналированием), **критичные операции — fail-hard**. «Молча скрыть» — не
  fail-soft, а источник самого опасного отказа: `silent mismatch`, когда система уверенно
  возвращает нерелевантное вместо того, чтобы признать недоступность.
- **Цена локального кэша/очереди отложенной записи** — три класса проблем: дубли, рассинхрон
  порядка, конфликты при мерже; у write-behind добавляется окно потери данных, у LWW — перетирание
  более осмысленного, но более раннего изменения. Условия, при которых кэш допустим:
  версия/`updated_at` рядом с записью, идемпотентная запись, дедупликация по operation-id, явная
  пометка stale, outbox.
- **Таймауты для LAN/VPN:** старт с коротких — 1–2 с для лёгких запросов, 5–10 с для тяжёлых;
  2–3 ретрая с экспоненциальным backoff и jitter, общий бюджет — единицы секунд. Отдельно назван
  типовой отказ VPN: «первый запрос после тишины упал» из-за idle-timeout на стороне пира —
  лечится keepalive и одним быстрым retry, а не серией долгих зависаний.

---

## §7 — Claude Code: таймауты и поведение при недоступном MCP-сервере (FC-6)

Источник: first-party `/docs/en/mcp`, WebFetch 2026-07-25.

- «Configure MCP server startup timeout using the `MCP_TIMEOUT` environment variable»;
  per-server `timeout` в `.mcp.json` — «a hard wall-clock limit per tool call», перебивает
  `MCP_TOOL_TIMEOUT`; «values below 1000 are ignored»; дефолт незаданного `MCP_TOOL_TIMEOUT` —
  «about 28 hours».
- **Per-request таймер (60 с) существует только для http/sse/connector-серверов**: «Stdio and
  WebSocket servers have no per-request timer». Наш `maind` — **stdio** ⇒ этого предохранителя у
  него нет.
- **Idle-timeout**: вызов без ответа и progress-уведомлений прерывается по idle-окну — «30 minutes
  for stdio servers» (настраивается `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`).
- **Авто-переподключение — не про нас**: «If an HTTP or SSE server disconnects mid-session, Claude
  Code automatically reconnects with exponential backoff… **Stdio servers are local processes and
  are not reconnected automatically**».
- MCP-старт по умолчанию неблокирующий; блокирует только `alwaysLoad: true` — «capped at the
  standard 5-second connect timeout».

**Вердикт для P4:** клиентские предохранители Claude Code нашему случаю почти не помогают —
`maind` стартует локально всегда, а «недоступен хост памяти» проявляется **внутри** вызова.
Значит бюджет ожидания обязан жить в НАШЕМ HTTP-клиенте (сейчас: `ping` 3 с,
`http_get_json` 5 с, `http_post_json` 10 с — `core/http.py`), а не в настройках клиента.

---

## §8 — systemd `--user` как always-on (FC-7)

Источник: perplexity-web 2026-07-25 → systemd.io/NETWORK_ONLINE · freedesktop.org loginctl(1).

- `loginctl enable-linger <user>` поднимает user-manager на boot и держит его после logout ⇒
  user-юнит стартует после перезагрузки без интерактивного логина. Это условие роли «always-on
  хост» (в `provision/service.py` подсказка уже печатается, но выполнение остаётся на человеке).
- **`After=/Wants=network-online.target` в ПОЛЬЗОВАТЕЛЬСКОМ юните не даёт ожидания сети**:
  этот target принадлежит модели boot-синхронизации system-manager'а, а user-manager — другой
  инстанс. Рабочие замены: проверка готовности в `ExecStartPre=` либо опора на
  `Restart=on-failure` + `RestartSec=`.
- Прямое следствие для нас **мягкое**: демон на хосте слушает loopback (публикация — через
  `tailscale serve`), сети на старте ему не требуется, поэтому текущие строки
  `After=network-online.target`/`Wants=…` в `packages/maind/lib/maind/provision/service.py:31-32` безвредны, но
  **вводят в заблуждение** — зафиксировано как наблюдение, отдельной правки в этой фазе не
  требует.
