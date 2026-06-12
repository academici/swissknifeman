---
name: skills-ssot
bucket: general
version: 0.1.0
description: "Единый источник истины скиллов для нескольких AI-агентов: .ai/skills + симлинки, gitignore, цикл обновления"
risk: write
persona: oss-dev
tags: ["ai-context", "skills", "ssot", "workflow"]
requires: []
produces_for: []
outputs: []
snippets: ["gitignore-ai.txt", "symlink-sync.sh", "boost-json.example", "skills-lock.example.json"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skills SSOT — единый источник истины скиллов

## Контекст

Когда в проекте работают несколько AI-агентов (Claude Code, Cursor, прочие), у каждого свой каталог скиллов: `.claude/skills/`, `.cursor/skills/` и т.д. Если вести их независимо, правила расползаются по копиям и начинают противоречить друг другу. Решение: **один источник** — `.ai/skills/` (плюс `.ai/guidelines/` для постоянных правил), всё остальное — генерируемые симлинки/копии, перечисленные в `.gitignore`.

### Схема

```text
.ai/
  guidelines/                  # постоянные правила (коммитится)
  skills/<name>/SKILL.md       # источник скиллов проекта (коммитится)
.agents/skills/<name>/         # внешние vendor-скиллы (коммитятся)
skills-lock.json               # source + hash vendor-скиллов (коммитится)
boost.json                     # конфиг генерации Laravel Boost (коммитится)
.claude/skills/<name> -> ../../.ai/skills/<name>   # генерируется, в .gitignore
.cursor/skills/<name> -> ../../.ai/skills/<name>   # генерируется, в .gitignore
CLAUDE.md / AGENTS.md / GEMINI.md                  # генерируются, в .gitignore
```

Кто генерирует:

- **Есть Laravel Boost**: `boost.json` — конфиг (agents, guidelines, mcp, packages, skills), `php artisan boost:update` — генератор; он же пересоздаёт `CLAUDE.md`/`AGENTS.md`, поэтому они тоже генерируемые и игнорируются.
- **Boost нет**: сниппет `symlink-sync.sh` — идемпотентная генерация симлинков из `.ai/skills/` в `.claude/skills/` и `.cursor/skills/`.

### Что коммитится

| Путь | Зачем |
|---|---|
| `.ai/guidelines/*.md` | постоянные правила проекта |
| `.ai/skills/*/SKILL.md` | источник скиллов |
| `.agents/skills/*` | внешние vendor-скиллы (после ревью) |
| `skills-lock.json` | фиксация source/hash vendor-скиллов |
| `boost.json` | конфиг генерации (если используется Boost) |
| `scripts/symlink-sync.sh` | генератор симлинков (если Boost нет) |

### Что в .gitignore

| Путь | Почему |
|---|---|
| `/CLAUDE.md`, `/AGENTS.md`, `/GEMINI.md` | генерируются из `.ai/` |
| `/.claude/settings.json` | локальные настройки агента |
| `/.claude/skills/` | симлинки/копии, восстанавливаются генератором |
| `/.cursor/skills/` | симлинки/копии, восстанавливаются генератором |

### Цикл обновления

1. Правки **только** в `.ai/skills/` и `.ai/guidelines/` (и `boost.json`, если меняется состав).
2. Regen: `php artisan boost:update` (Boost) или `scripts/symlink-sync.sh` (без Boost).
3. Коммит источников: `.ai/*`, `boost.json`, `skills-lock.json`.

**Запрещено** редактировать руками `CLAUDE.md`, `AGENTS.md`, содержимое `.claude/skills/` — правки сотрёт следующая генерация.

### Интеграция со swissknifeman

- **Claude Code** — через нативный plugin marketplace: `scripts/connect-claude.sh`; скиллы реестра **не копируются** в проект и не попадают в `.ai/skills/`.
- **Остальные агенты** — `./install.sh --agent generic --target <project>` ставит выбранные бакеты в `.ai/skills/`, дальше обычный regen (`symlink-sync.sh` или `boost:update`).
- **Корневой хаб** генерируется `scripts/generate-hub.sh`; в Boost-проектах хаб подключается через `.ai/guidelines/swissknifeman-hub.md`, чтобы пережить регенерацию `CLAUDE.md`.

## Алгоритм (внедрение с нуля)

1. Создать `.ai/skills/` и `.ai/guidelines/`; перенести в `.ai/skills/` существующие скиллы из каталогов агентов (один каталог `<name>/SKILL.md` на скилл, дубликаты слить).
2. Добавить в `.gitignore` блок из сниппета `gitignore-ai.txt`; убрать уже закоммиченные генерируемые файлы из индекса: `git rm -r --cached CLAUDE.md AGENTS.md .claude/skills .cursor/skills` (что есть по факту).
3. Внешние vendor-скиллы положить в `.agents/skills/` и зафиксировать в `skills-lock.json` (`npx skills add <owner/repo@skill>`, `npx skills check`) — см. `skills-lock.example.json`.
4. Если проект на Laravel Boost — заполнить `boost.json` (см. `boost-json.example`: каждый скилл из `.ai/skills/` должен быть в массиве `skills`) и выполнить `php artisan boost:update`. Иначе — положить `symlink-sync.sh` в `scripts/` и запустить.
5. Проверить результат: `ls -la .claude/skills/` — симлинки ведут в `../../.ai/skills/*`, битых нет, реальные каталоги остались только у vendor-копий.
6. Подключить swissknifeman: для Claude Code — `connect-claude.sh`; для остальных — `install.sh --agent generic`, затем повторный regen из шага 4.
7. Закоммитить источники (`.ai/`, `.agents/skills/`, `skills-lock.json`, `boost.json`, `.gitignore`, `scripts/symlink-sync.sh`); сгенерированное не коммитить.

## Когда какой сниппет открывать

| Ситуация | Сниппет |
|---|---|
| Настраиваете `.gitignore` под SSOT | `gitignore-ai.txt` |
| Проект без Laravel Boost — нужны симлинки агентов | `symlink-sync.sh` |
| Проект на Laravel Boost — настройка генерации | `boost-json.example` |
| Подключаете внешний vendor-скилл с фиксацией хеша | `skills-lock.example.json` |

## Чеклист качества

- [ ] Каждый скилл существует ровно в одном экземпляре — в `.ai/skills/`; в `.claude/skills/` и `.cursor/skills/` только симлинки (плюс vendor-копии из `.agents/skills/`).
- [ ] `.gitignore` содержит блок генерируемых файлов; `git status` чист после regen.
- [ ] У каждого `SKILL.md` заполнен `description` с реальными триггерами (классы, сценарии), а не абстракцией.
- [ ] Все скиллы из `.ai/skills/` перечислены в `boost.json` → `skills` (если Boost используется).
- [ ] Внешние скиллы зафиксированы в `skills-lock.json`; `npx skills check` проходит.
- [ ] В PR с правками контекста — только источники, ни одного сгенерированного файла.

## Ссылки

- `general/ai-context-workflow` — регламент правок AI-контекста (что править, запреты, `boost:update`); этот скилл — про **структуру** SSOT, тот — про **workflow правок**, не дублируются.
- `docs/routing.md` реестра — маршрутизация скиллов по бакетам и агентам.
- `docs/boost-compatibility.md` реестра — совместимость скиллов реестра с Laravel Boost (пакет: https://github.com/laravel/boost, документация: https://laravel.com/docs/boost).
- `references/ssot-source-layout.md` — детальное устройство `.ai/`: потоки данных, три слоя приоритета, guidelines vs skills, команды, частые ошибки.
- `references/ssot-scenarios.md` — таблица «сценарий → скилл» для типовых задач агента.
