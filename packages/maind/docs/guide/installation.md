# Установка

## Полный bootstrap (рекомендуется)

Одной командой: CLI + демон памяти + автозапуск под systemd.

```bash
git clone <repo> maind && cd maind
./install.sh --with-memory --with-service
```

- `--with-memory` — `npm install` в корне (демон `@agentmemory/agentmemory`).
- `--with-service` — регистрирует демон как systemd --user сервис (`maind service install`):
  автозапуск при логине + авто-рестарт. См. [Демон памяти (systemd)](/guide/systemd).

Чтобы демон поднимался **при загрузке ОС** (а не только после логина) — включите linger (разово):

```bash
loginctl enable-linger $USER       # проверка: loginctl show-user $USER -p Linger → yes
```

После — подключайте проекты: `maind onboard <path>` (см. навык `ecosystem-integration`).

## Только CLI

```bash
./install.sh
```

Создаёт симлинк `~/.local/bin/maind → bin/maind` и каталог состояния `~/.maind`
(`projects.json`, `agents.json`). Опции: `--bin-dir DIR`, `--force`. Проверка: `maind doctor`.

## Память вручную (без systemd)

Демон памяти — Node-пакет `@agentmemory/agentmemory`:

```bash
npm install                  # ставит демон в node_modules
cp .env.example .env         # порты узла (по умолчанию 4111/4112)
maind start --only memory
maind memory status
```

::: tip Конфликт портов
Если на 4111/4112 уже крутится другой узел (например Brain), задайте в `.env` свои
`AGENTMEMORY_PORT` / `AGENTMEMORY_STREAM_PORT` — maind возьмёт их вместо дефолтов.
:::

## Документация

```bash
npm run docs:dev        # локальный сервер VitePress
npm run docs:build      # сборка статического сайта
```

## Требования

- **Python 3.8+** и **bash** — для ядра CLI (обязательно).
- **Node.js** — только для демона памяти и сборки документации.
- **uvx** (из [uv](https://docs.astral.sh/uv/)) — для графа кода в проекте (движок Serena, см.
  [граф кода](/guide/code-graph)); включается на проект полем `code:true`.

Дальше: [Конфиг config.json →](/guide/config) (живёт в корне монорепо, не в пакете maind)
