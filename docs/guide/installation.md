# Установка

Установка состоит из двух шагов: один раз ставится CLI `swissknifeman`,
дальше каждый проект подключается командой из его собственного каталога —
реестру не нужно знать о ваших проектах.

> Хочешь выбрать сразу весь функционал (скиллы + permissions + хуки + память + hub)
> через один интерактивный визард — см. [Чеклист интеграции](./integration-checklist)
> (`swissknifeman integrate`). Ниже — установка скиллов по отдельности.

## Шаг 1. CLI (один раз на машину)

```bash
cd ~/projects/packages/swissknifeman
./install.sh
```

`install.sh` создаёт симлинк `~/.local/bin/swissknifeman → <repo>/bin/swissknifeman`
и каталог состояния `~/.swissknifeman/`. Симлинк означает: после `git pull`
CLI всегда свежий, а путь к реестру он определяет сам (через `readlink`).
Репозиторий переехал — просто перезапустите `./install.sh` из нового места.

Флаги: `--bin-dir DIR` (по умолчанию `~/.local/bin`), `--force` (заменить
чужой файл без вопроса). Если `~/.local/bin` не в `PATH`, установщик подскажет
команду для вашего шелла. Проверка установки: `swissknifeman doctor`.

## Шаг 2. Подключение проекта

Из каталога проекта (корень ищется автоматически вверх от CWD по
`.swissknife.json` → `.claude/` → `.git`):

```bash
# Claude Code — нативный plugin marketplace (рекомендуется)
cd ~/projects/my-app
swissknifeman connect

# Cursor и другие агенты — вендоринг копий скиллов
cd ~/projects/my-app
swissknifeman vendor --agent cursor
```

| Канал | Команда | Что попадает в проект |
|---|---|---|
| **Claude Code** | `swissknifeman connect` | только записи в `.claude/settings.local.json` |
| **Cursor / generic** | `swissknifeman vendor` | сами скиллы в `.cursor/skills` / `.ai/skills` |

::: tip Агенты — только в plugin-канале
Бакет-плагин может нести не только скиллы, но и каталог `agents/` в своём корне
(`*.md` с YAML-frontmatter `name`/`description`/`tools`) — Claude Code
обнаруживает его автоматически. Такие агенты доступны **только через канал
`connect`**: `vendor` копирует скиллы, но не агентов, поэтому в Cursor и других
generic-агентах их не будет. Пример — бакет `php` с агентами `laravel-reviewer`
и `laravel-test-writer` (см. скилл `laravel-subagents`).
:::

Каждое подключение автоматически регистрирует проект в
`~/.swissknifeman/projects.json` — это включает `swissknifeman list` и
`swissknifeman update --all`.

## Проект с Laravel Boost (мульти-агент, единый источник истины)

Если проект уже использует [Laravel Boost](/boost-compatibility) — у него есть
`boost.json`, каталог `.ai/` (guidelines + skills) и команда
`php artisan boost:update`, которая генерирует `CLAUDE.md`/`AGENTS.md` и
раскидывает копии скиллов по `.cursor/`, `.gemini/`, `.codex/`, `.github/`.
Чтобы скиллы swissknifeman жили в **одном источнике истины** и расходились по
всем тулзам автоматически — вендорим прямо в `.ai/skills/` и отдаём раздачу
Boost-у.

```bash
cd ~/projects/my-laravel-app
swissknifeman vendor \
  --agent generic \
  --skills-path .ai/skills \
  --profile laravel-project \
  --exclude code-style-spatie,node-pnpm-preflight \
  --hub
php artisan boost:update      # или: composer ai:sync
```

Что происходит:

1. **`vendor --skills-path .ai/skills`** — скиллы копируются в источник истины
   Boost. При обнаружении `boost.json` CLI автоматически берёт **flat-раскладку**
   `.ai/skills/<skill>/SKILL.md` (Boost обнаруживает user-скиллы через
   `glob('.ai/skills/*')` на один уровень — bucket-подпапки он бы не нашёл).
   Если имя нашего скилла совпадает с уже существующим в проекте — установка
   остановится на коллизии; добавь такой скилл в `--exclude` (проектная версия
   приоритетна).
2. **Обнаружен `boost.json`** — CLI идемпотентно дозаписывает вендоренные скиллы
   в `boost.json::skills` (по `name` из frontmatter) и печатает подсказку
   `php artisan boost:update`.
3. **`--hub`** — индекс установленного пишется в
   `.ai/guidelines/swissknifeman-hub.md`; Boost сам встроит его в
   `CLAUDE.md`/`AGENTS.md` при `boost:update`.
4. **`boost:update`** — перегенерирует корневые доки и копии скиллов по всем
   агентам из `boost.json::agents`.

::: warning Исключайте конфликтующее
`--exclude` убирает скиллы, чьи правила противоречат проекту. Типичные
конфликты: `code-style-spatie` (не-`final` по умолчанию) против проекта с
обязательным `final`; `node-pnpm-preflight` (pnpm) против yarn-проекта.
Политика совместимости — [boost-compatibility.md](/boost-compatibility),
принцип ядра — [Что такое SwissKnifeMan](/guide/#_6-совместимое-ядро-политика-конфликтов).
:::

**Обновление** такого проекта — обычный `swissknifeman update`: он повторно
вендорит, дозаписывает `boost.json` и регенерирует хаб; затем вручную
`php artisan boost:update`.

### Тулзы вне Boost: managed-блок в корневых файлах

Для проектов **без** Boost тот же индекс можно класть managed-блоком прямо в
корневые файлы агентов:

```bash
./scripts/generate-hub.sh --target . --root-files AGENTS.md,GEMINI.md
```

Блок вставляется между маркерами `<!-- swissknifeman:hub:start -->` …
`<!-- swissknifeman:hub:end -->` в `CLAUDE.md` (по умолчанию) и в каждый
указанный файл; контент вне маркеров не трогается, файл создаётся при
отсутствии.

## Шаг 3. Обновление

```bash
cd ~/projects/my-app && swissknifeman update   # текущий проект
swissknifeman update --all                     # все зарегистрированные
```

`update` сам определяет канал(ы) проекта по маркерам на диске, обновляет
вендоренные скиллы / настройки marketplace, чинит путь к реестру, если тот
переехал, и регенерирует хаб. Подробности всех команд — в
[справочнике CLI](./cli).

## Превью без установки

```bash
swissknifeman vendor --list      # что будет установлено, файлы не трогаются
swissknifeman connect --dry-run  # итоговый settings.json без записи
```

## Явное управление

Автодетект профиля (`.obsidian/` → obsidian-vault; `artisan`+`composer.json`
→ laravel-project; `composer.json` → php-package; иначе standalone) можно
переопределить:

```bash
swissknifeman vendor --profile php-package
swissknifeman vendor --buckets php,quality
swissknifeman vendor --buckets php,quality --exclude botkit
swissknifeman connect --plugins php,quality
```

Приоритет источников конфигурации: **флаги CLI → `.swissknife.json` → автодетект**.
Явный выбор (`--profile`, `--buckets`, `--plugins`) запоминается в
`projects.json` и воспроизводится при `update`; автодетект пере-резолвится
с диска каждый раз.

## Зависимости между скиллами

Поле `requires` во frontmatter скилла разрешается транзитивно: при выборочной
установке (`--buckets`, `--exclude`) `vendor` дотягивает зависимости — в том
числе из бакетов, которые вы не выбирали (в bucket-раскладке дотянутый скилл
сохраняет директорию своего бакета, например `founder/competitive-analysis`
при установке `--buckets pm`). Дотянутые скиллы помечаются в `--list` и
`--dry-run` как `(dependency of <skill>)`.

`--exclude` побеждает зависимость: исключённый скилл не ставится никогда,
CLI лишь предупреждает (`WARN: ... excluded by --exclude, skipping`).

Картина связей целиком — на [странице графа зависимостей](./graph).

::: warning Marketplace-канал не разрешает зависимости
В plugin marketplace Claude Code плагин = бакет: включение плагина `php`
не включит зависимый скилл из бакета `architect`. Resolution работает только
в канале вендоринга. Включайте связанные бакеты вручную — по графу зависимостей.
:::

## Фиксация конфигурации: `.swissknife.json`

Проект может зафиксировать свою конфигурацию установки в `.swissknife.json`
в корне — `connect`, `vendor` и `update` прочтут его автоматически:

```json
{
  "project_type": "laravel-project",
  "buckets": ["architect", "php", "quality"],
  "exclude": ["botkit", "devops/gitops"],
  "skills_path": ".claude/skills",
  "agent": "claude"
}
```

Все ключи опциональны. Если задан `buckets`, поле `project_type` игнорируется.
Файл проходит схема-валидацию: неизвестный ключ или неверный тип — понятная
ошибка с подсказкой (`unknown key 'bucket' — did you mean 'buckets'?`).
Ключи, начинающиеся с `_`, считаются комментариями.
Шаблон — [.swissknife.example.json](https://github.com/academici/swissknifeman/blob/main/.swissknife.example.json).

## Манифест, переустановка и коллизии

`vendor` пишет манифест `.swissknifeman-manifest.json` рядом со скиллами —
в обеих раскладках (плоской и bucket). Переустановка сначала удаляет
**только** перечисленное в манифесте, затем ставит заново — чужие скиллы не
трогаются.

Если целевая папка скилла уже существует и не числится в манифесте, установка
прерывается со списком коллизий. Перезаписать осознанно: `--force`.

## Режим `--agent claude` (deprecated)

Вендоринг для Claude Code оставлен для совместимости (плоская раскладка
`.claude/skills/<name>/SKILL.md`, коллизии разрешаются префиксом bucket-а),
но предпочтительный путь — `swissknifeman connect` ([marketplace](/adapters/claude-code)).
Мигрировать с вендоринга: `swissknifeman connect --cleanup-vendored`.

## Что дальше

После установки скиллов подтяните пресеты permissions, чтобы агент сразу мог
работать без промптов — см. [Permissions для Claude Code](/configs/claude-permissions).
