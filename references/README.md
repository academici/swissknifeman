# References — каталог внешних источников

Анализ внешних репозиториев и маркетплейсов скиллов: что это, что из него **стоит взять
выборочно**, что не нужно, и текущий статус. Это документация для отбора — файлы отсюда
не попадают в `skills.json` и не устанавливаются в проекты.

> Не путать со `skills/oss-dev/references/` — это языковые reference-файлы внутри
> bucket-а oss-dev (часть контента скиллов).

## Принцип отбора

Из источников берём **не всё, а только то, что реально подходит** под мои сценарии:
документация, Obsidian vault, ТЗ, PHP-пакеты (Laravel), крупные Laravel-проекты.
Решение по каждому скиллу/сниппету — отдельное. Импорт оформляется через
`upstream.json` в папке скилла (см. [CONTRIBUTING.md](../CONTRIBUTING.md)).

## Статусы

| Статус | Значение |
|---|---|
| `planned` | Источник изучен, отобраны кандидаты, импорт ещё не делался |
| `imported` | Что-то уже взято (есть скиллы с `upstream.json` на этот источник) |
| `rejected` | Изучен и отклонён (причина в файле) |
| `trusted` | Не импортируем — доверяем на месте в проектах; реестр дополняет, не дублирует |

## Индекс

| Источник | Ценность | Статус |
|---|---|---|
| [laravel/boost](laravel-boost.md) | Версионно-специфичные Laravel-скиллы + MCP + генератор CLAUDE.md | trusted |
| [get-zeked/perplexity-super-skills](get-zeked-perplexity-super-skills.md) | 12 super-skills, gap-analysis формат | imported |
| [anthropics/claude-code](anthropics-claude-code.md) | Официальная спецификация SKILL.md | imported |
| [VoltAgent/awesome-agent-skills](voltagent-awesome-agent-skills.md) | Курируемый индекс официальных скиллов | planned |
| [jpcaparas/superpowers-laravel](jpcaparas-superpowers-laravel.md) | Laravel workflow-скиллы (TDD, debug, plan) | planned |
| [skills.laravel.cloud](skills-laravel-cloud.md) | Laravel-маркетплейс, 175 скиллов | planned |
| [mwguerra/claude-code-plugins](mwguerra-claude-code-plugins.md) | Obsidian-vault интеграция | planned |
| [muratcankoylan/Agent-Skills-for-Context-Engineering](muratcankoylan-context-engineering.md) | Context engineering принципы | planned |
| [PatrickJS/awesome-cursorrules](patrickjs-awesome-cursorrules.md) | 500+ правил → источник сниппетов | planned |
| [anthropics/knowledge-work-plugins](anthropics-knowledge-work-plugins.md) | Официальная plugin-архитектура | planned |
| [alexeymezenin/laravel-best-practices](alexeymezenin-laravel-best-practices.md) | 40+ Laravel best practices (bad/good) | planned |
| [LaravelDaily/laravel-tips](laraveldaily-laravel-tips.md) | 1000+ Laravel tips | planned |
| [WendellAdriel/laravel-expressive](wendelladriel-laravel-expressive.md) | 8 скиллов разработки Laravel-пакетов → `php/` | imported |
| [adr/madr](adr-madr.md) | MADR шаблоны ADR | planned |
| [nicholasjconn/docker-best-practices](nicholasjconn-docker-best-practices.md) | Docker паттерны | planned |
| [DenisSergeevitch/agents-best-practices](denissergeevitch-agents-best-practices.md) | Агентные workflow-паттерны | planned |
