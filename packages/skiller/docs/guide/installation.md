# Установка

Установка состоит из двух шагов: один раз ставится CLI `swissknifeman`,
дальше каждый проект подключается командой из его собственного каталога —
реестру не нужно знать о ваших проектах.

> Хочешь выбрать сразу весь функционал (скиллы + permissions + хуки + память + hub)
> через один интерактивный визард — см. [Чеклист интеграции](./integration-checklist)
> (`skiller integrate`). Ниже — установка скиллов по отдельности.

## Шаг 1. CLI (один раз на машину)

```bash
cd ~/projects/packages/swissknifeman
./install.sh
```

`install.sh` создаёт симлинк `~/.local/bin/skiller → <repo>/bin/skiller`,
каталог состояния `~/.swissknifeman/` и, если Codex CLI доступен, автоматически
добавляет локальный marketplace `swissknifeman` и устанавливает базовые плагины
`core` + `task`. Поэтому `$ task:*` доступен в новой Codex-сессии без ручного
`codex plugin add` или симлинка внутри проекта. Симлинк означает: после `git pull`
CLI всегда свежий, а путь к реестру он определяет сам (через `readlink`).
Репозиторий переехал — перезапустите `./install.sh` из нового места, чтобы обновить
также источник Codex marketplace.

Флаги: `--bin-dir DIR` (по умолчанию `~/.local/bin`), `--force` (заменить
чужой файл без вопроса), `--no-codex-plugins` (осознанно пропустить машинную
установку `core` + `task`). Дополнительный плагин можно поставить повторяемым
`./packages/skiller/install.sh --codex-plugin NAME`; базовые плагины при этом
сохраняются. Если `~/.local/bin` не в `PATH`, установщик подскажет команду для
вашего шелла. Проверка установки: `skiller doctor`.

## Шаг 2. Подключение проекта

Из каталога проекта (корень ищется автоматически вверх от CWD по
`.swissknife.json` → `.claude/` → `.git`):

```bash
# Claude Code — нативный plugin marketplace (рекомендуется)
cd ~/projects/my-app
skiller connect

# Cursor и другие агенты — вендоринг копий скиллов
cd ~/projects/my-app
skiller vendor --agent cursor
```

| Канал | Команда | Что попадает в проект |
|---|---|---|
| **Claude Code** | `skiller connect` | только записи в `.claude/settings.local.json` |
| **Cursor / generic** | `skiller vendor` | сами скиллы в `.cursor/skills` / `.ai/skills` |
| **Codex (vendor)** | `skiller sync` с `providers.codex.enabled=true` | managed copies в `.agents/skills` + provider-qualified lock |

Базовые Codex-плагины устанавливаются один раз на машину шагом 1 и доступны во
всех проектах. Профильные Codex skills по-прежнему доставляются в конкретный проект
через vendor sync: установщик сознательно не включает глобально все профильные
плагины, чтобы один проект не раздувал остальные сессии.

::: tip Агенты — только в plugin-канале
Бакет-плагин может нести не только скиллы, но и каталог `agents/` в своём корне
(`*.md` с YAML-frontmatter `name`/`description`/`tools`) — Claude Code
обнаруживает его автоматически. Такие агенты доступны **только через канал
`connect`**: `vendor` копирует скиллы, но не агентов, поэтому в Cursor и других
generic-агентах их не будет. Пример — бакет `php` с агентами `laravel-reviewer`
и `laravel-test-writer` (см. скилл `laravel-subagents`).
:::

Каждое подключение автоматически регистрирует проект в
`~/.swissknifeman/projects.json` — это включает `skiller list` и
`skiller update --all`.

## Проект с Laravel Boost (мульти-агент, единый источник истины)

Если проект уже использует [Laravel Boost](../boost-compatibility) — у него есть
`boost.json`, каталог `.ai/` (guidelines + skills) и команда
`php artisan boost:update`, которая генерирует `CLAUDE.md`/`AGENTS.md` и
раскидывает копии скиллов по `.cursor/`, `.gemini/`, `.codex/`, `.github/`.
Чтобы скиллы swissknifeman жили в **одном источнике истины** и расходились по
всем тулзам автоматически — вендорим прямо в `.ai/skills/` и отдаём раздачу
Boost-у.

```bash
cd ~/projects/my-laravel-app
skiller vendor \
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
Политика совместимости — [boost-compatibility.md](../boost-compatibility),
принцип ядра — [Что такое SwissKnifeMan](./#_6-совместимое-ядро-политика-конфликтов).
:::

**Обновление** такого проекта — обычный `skiller update`: он повторно
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

### Форма блока: по каналу-цели, а не по проекту

У Claude Code есть **свой** листинг скиллов: имя и описание каждого доступного
скилла (проектного и плагинного) резидентны с начала сессии, тело грузится по
вызову. Индекс внутри `CLAUDE.md` был бы вторым платным экземпляром того же
списка, поэтому форма блока зависит от того, куда он пишется:

| Цель | Нативный листинг | Форма блока |
|:--|:--|:--|
| `CLAUDE.md` | есть | **краткая** — приоритеты источников, правила поиска, указатель |
| `.ai/guidelines/swissknifeman-hub.md` (Boost) | есть (фрагмент едет в `CLAUDE.md`) | **краткая** |
| `AGENTS.md`, `GEMINI.md` и прочие `--root-files` | нет | **полная** — с индексом скиллов |

Один и тот же прогон пишет обе формы: `CLAUDE.md` получает краткую, а
`AGENTS.md` из `--root-files` — полную. Вернуть индекс всем целям (откат):

```bash
./scripts/generate-hub.sh --target . --full-index
./scripts/generate-hub.sh --target . --full-index --dry-run   # только посмотреть
```

Перед сокращением генератор **сверяет обнаружение**: скилл уходит из блока,
только если он есть и в активном наборе проекта (`skiller budget`), и в канале,
который клиент перечисляет нативно (включённый плагин маркетплейса либо копия в
`.claude/skills`). Неподтверждённые скиллы остаются в блоке разделом «Скиллы вне
нативного листинга», а расхождение печатается в вывод команды. Freshness-штамп
`<!-- swissknifeman:registry sha=… -->`, который сверяет `skiller doctor`,
присутствует в обеих формах.

## Шаг 3. Обновление

```bash
cd ~/projects/my-app && skiller update   # текущий проект
skiller update --all                     # все зарегистрированные
```

`update` сам определяет канал(ы) проекта по маркерам на диске, обновляет
вендоренные скиллы / настройки marketplace, чинит путь к реестру, если тот
переехал, и регенерирует хаб. Подробности всех команд — в
[справочнике CLI](./cli).

## Превью без установки

```bash
skiller vendor --list      # что будет установлено, файлы не трогаются
skiller connect --dry-run  # итоговый settings.json без записи
```

## Явное управление

Автодетект профиля (`.obsidian/` → obsidian-vault; `artisan`+`composer.json`
→ laravel-project; `composer.json` → php-package; иначе standalone) можно
переопределить:

```bash
skiller vendor --profile php-package
skiller vendor --buckets php,quality
skiller vendor --buckets php,quality --exclude botkit
skiller connect --plugins php,quality
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

### Носитель конфига внутри skiller

Прочитанный файл живёт в коде не голым словарём, а объектом
`skiller.config.ProjectConfig` — frozen dataclass на stdlib (никаких `pydantic`
или `jsonschema`). Поля объекта — единственный носитель перечня ключей: список
`CONFIG_KEYS`, с которым `skiller doctor` и `tests/test_schema.py` сверяют
`schema/swissknife.schema.json`, **выводится** из полей (`metadata["json_type"]`
каждого поля несёт тот же Python-тип, которым валидируется значение). Добавить
ключ = добавить поле и свойство в схему; третьего места, где ключи можно забыть
обновить, нет.

Объект read-only: конфиг проекта после загрузки никто не мутирует, поэтому
`frozen=True` (в отличие от обёртки конфига УЗЛА mAInd — там подкласс `dict`
с `save()`). Исходный словарь сохраняется как `raw` — из него читаются
`_`/`$`-ключи и подветка `providers`; старый доступ отображением
(`config.get("agent")`, `config["agent"]`) продолжает работать байт-в-байт.

Дом объекта — пакет `skiller`, а не общий `core/`: критерий приёма примитива в
фундамент — «дублируется между ≥2 пакетами со стабильной границей», а валидация
`.swissknife.json` завязана на локальное знание реестра (список профилей,
`AGENT_DEFAULTS`, зарезервированные ключи). Единственный внешний читатель файла —
`maind` — берёт только подветку `providers`, и она типизирована в `core`.

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
но предпочтительный путь — `skiller connect` ([marketplace](../adapters/claude-code)).
Мигрировать с вендоринга: `skiller connect --cleanup-vendored`.

## Что дальше

После установки скиллов подтяните пресеты permissions, чтобы агент сразу мог
работать без промптов — см. [Permissions для Claude Code](/harness/configs/claude-permissions).
