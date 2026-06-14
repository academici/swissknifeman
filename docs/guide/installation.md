# Установка

## CLI

```bash
git clone <repo> maind && cd maind
./install.sh
```

`install.sh` создаёт симлинк `~/.local/bin/maind → bin/maind` и каталог состояния
`~/.maind` (`projects.json`, `agents.json`). Опции: `--bin-dir DIR`, `--force`.

Проверка окружения:

```bash
maind doctor
```

## Память (опционально)

Демон памяти — Node-пакет `@agentmemory/agentmemory`. Нужен, только если используете
долгосрочную память:

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

Дальше: [CLI →](/guide/cli)
