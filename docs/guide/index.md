# Что такое SwissKnifeMan

**SwissKnifeMan** — универсальный личный реестр AI-скиллов, сниппетов и конфигов.
Принцип «швейцарского ножа»: всё, что нужно для продуктивной работы AI-агента
в проекте, лежит в одном месте и ставится одной командой — скиллы, permissions,
профили, адаптеры под разные IDE.

## Зачем

Когда проектов много, а агентов — несколько (Claude Code, Cursor, Perplexity),
возникают одни и те же проблемы:

- скиллы и промпты копипастятся между проектами и расходятся;
- каждый новый проект начинается с десятков permission-промптов;
- внешние наработки (чужие скиллы с GitHub) устаревают незаметно;
- нет единого места, где видно, что откуда взято и какой версии.

SwissKnifeMan решает это одним реестром: **один источник истины → установка
в любой проект и любую IDE → отслеживание внешних источников**.

## Основные принципы

### 1. Один источник истины

Все скиллы живут в этом репозитории и распределены по **bucket-ам** — тематическим
папкам:

| Bucket | Скиллов | Тематика |
|---|---|---|
| `architect` | 9 | архитектура, API, данные, безопасность |
| `devops` | 6 | Docker, CI/CD, GitOps |
| `founder` | 5 | идеи, анализ конкурентов, питчи |
| `imported` | 12 | внешние super-skills (upstream-tracked) |
| `operator` | 5 | инциденты, runbook, postmortem |
| `oss-dev` | 5 | open-source разработка + языковые references |
| `php` | 7 | Laravel, пакеты, тесты, паттерны |
| `pm` | 8 | BRD, PRD, roadmap, монетизация |
| `quality` | 4 | code review, тесты, техдолг |
| `roles` | 4 | персоны: tech-lead, startup-cto, ... |

### 2. Provider-neutral формат

Скилл — это папка с `SKILL.md` (frontmatter + инструкции) и `snippets/`.
Формат не привязан к конкретному агенту: специфика IDE выносится в
delta-файлы `adapters/*.md` внутри скилла. Подробнее — в
[Анатомии скилла](/guide/skill-anatomy).

### 3. Выборочный импорт с provenance

Внешние скиллы берутся **выборочно** — только то, что реально подходит, а не
репозитории целиком. У каждого внешнего скилла есть `upstream.json` с источником,
стратегией обновления и sha256 — см. [Upstream-sync](/guide/upstream-sync).
Каталог источников-кандидатов ведётся в `references/`.

### 4. Контекстная установка

`swissknifeman vendor` определяет тип целевого проекта по маркерам (`artisan`,
`composer.json`, `.obsidian/`) и ставит подходящий набор bucket-ов — см.
[Профили](/guide/profiles). Той же логикой
[`apply-permissions.sh`](/configs/claude-permissions) подбирает пресеты
разрешений.

### 5. Всё проверяется

`scripts/validate.sh` валидирует frontmatter, `upstream.json`, профили и
манифесты — локально и в CI. Реестр `skills.json` хранит sha256 и provenance
каждого файла.

## Сценарии использования

Пакет заточен под пять рабочих сценариев:

1. **Документация** — написание и сопровождение технической документации
2. **Obsidian vault** — управление знаниями, заметки, базы знаний
3. **Технические задания** — составление ТЗ (BRD → PRD → архитектура)
4. **PHP-пакеты** — разработка open-source пакетов, в первую очередь Laravel
5. **Крупные Laravel-проекты** — архитектура, паттерны, DevOps, качество

## Структура репозитория

```
skills/             # скилл = папка + SKILL.md + snippets/ (+ upstream.json у внешних)
profiles/           # тип проекта → набор bucket-ов
configs/            # готовые конфиги: пресеты permissions для Claude Code
references/         # каталог внешних источников (что брать, статус)
adapters/           # доки по интеграции: claude-code, cursor, perplexity
scripts/            # validate, update-upstreams, scanner, apply-permissions
generate-skill/     # мета-скилл создания новых скиллов
skills.json         # реестр (генерируется swissknifeman registry, с provenance)
bin/swissknifeman   # CLI: connect, vendor, update, status, registry
install.sh          # установка CLI симлинком в ~/.local/bin
docs/               # эта документация (VitePress)
```

## С чего начать

1. [Установить скиллы в проект](/guide/installation) — одна команда с автодетектом
2. [Подтянуть пресеты permissions](/configs/claude-permissions) — чтобы агент работал без промптов
3. [Посмотреть примеры](/examples/laravel) — типовые сценарии от и до
