# Демон памяти как systemd-сервис

Демон общей памяти (`agent-memory`) — это Node-процесс на узле mAInd, через который идут
`recall`/`store` всех проектов. Чтобы он поднимался автоматически (при логине / загрузке ОС) и
сам перезапускался при краше, его регистрируют как **пользовательский** systemd-юнит
(`systemctl --user`, без root). Управление — командой `maind service`.

## Быстрый старт

```bash
maind service install     # создать юнит, daemon-reload, enable --now (сразу поднять)
maind service status      # состояние юнита
maind service logs        # journalctl -u maind-memory (последние 100 строк + follow)
```

После `install` память поднимается сразу и стартует при каждом логине. Проверка связи проекта:

```bash
maind health --cwd        # статус connected, демон отвечает на :4111
```

## Команды

| Команда | Что делает |
|:--|:--|
| `maind service install` | записать `~/.config/systemd/user/maind-memory.service`, `daemon-reload`, `enable --now` |
| `maind service uninstall` | `disable --now` + удалить юнит |
| `maind service start` / `stop` / `restart` | управление запущенным юнитом |
| `maind service status` | `systemctl --user status maind-memory` |
| `maind service enable` / `disable` | автостарт при логине вкл/выкл |
| `maind service logs [args]` | `journalctl --user -u maind-memory` (доп. аргументы прокидываются) |

## Как устроен юнит

`ExecStart` запускает демон в **переднем плане** — `maind memory run` делает `exec node …`,
заменяя процесс, поэтому systemd трекает сам Node-демон как `MAINPID` и корректно им рулит
(рестарт, остановка). Юнит (генерируется из абсолютных путей установки):

```ini
[Unit]
Description=mAInd — демон общей памяти экосистемы (agent-memory)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=<корень maind>
ExecStart=<корень maind>/bin/maind memory run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`maind memory run` — foreground-запуск для systemd; для ручного фонового запуска по-прежнему
есть `maind start --only memory` / `maind memory start` (детач + pidfile).

## Автостарт без логина (сервер по SSH)

Пользовательские юниты живут, пока есть сессия пользователя. Чтобы демон стартовал при загрузке
ОС и держался без входа в систему — включите **linger** (разовый шаг). Для роли `memory.role =
"host"` (cross-machine память, ADR-0001) linger — **условие роли, не опция**: без него демон не
переживёт перезагрузку хоста без интерактивного логина, и все клиенты теряют память одновременно
(см. [umbrella deploy.md «Вторая машина»](https://github.com/academici/swissknifeman/blob/main/docs/deploy.md)):

```bash
loginctl enable-linger $USER
loginctl show-user $USER -p Linger    # проверка → Linger=yes
```

Без linger демон поднимется только после первого логина в сессию. С linger — сразу при загрузке.

## Порты и конфиг

Демон слушает `:4111` (HTTP) и `:4112` (stream) — переопределяются через `.env` в корне maind
(`AGENTMEMORY_PORT` / `AGENTMEMORY_STREAM_PORT`); конфиг воркеров — `config/memory/iii-config.yaml`.
См. [Память (agent-memory)](./memory).

## Если нет systemd

На системах без `systemctl` (или голый SSH без user-сессии) `maind service` подскажет
альтернативу — поднимать память вручную: `maind start --only memory`.
