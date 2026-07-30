# Универсальные роли-агенты

> Статус: ✅ реализовано (`configs/claude-code/agent-packs/role-bindings.json`,
> `binding_version 1.0.0`). Здесь — модель; seed-агенты рендерятся из `_common` и
> стек-паков (`backend-laravel`, `node-frontend`, `python-backend`, `dart-flutter`,
> `laravel-package`) через связывание ролей.

Ключевая идея универсальности: **роли одинаковы для любого проекта, меняется только
стек — через профиль.** Reviewer на Laravel и на Nuxt — одна роль; различается набор
преднагруженных скиллов и path-scoped правил, выбранный профилем.

## Набор ролей

| Роль | Ответственность | tools |
|---|---|---|
| `implementer` (slice-builder) | реализует один срез по канону, коммитит, тесты не пишет | Read/Grep/Glob/Edit/Write/Bash |
| `test-writer` | тесты по готовому коду, до зелёного; код не меняет | Read/Grep/Glob/Edit/Write/Bash |
| `reviewer` | read-only ревью + over-engineering-проход (ponytail) | Read/Grep/Glob/Bash |
| `explore` | read-only исследование, собирает контекст | read-only |
| `plan` | архитектурный план | read-only |
| `spec-writer` (опц.) | `tech-spec.md` на крупные фичи (не глоб. гейт) | Read/Grep/Glob/Write |

## Как роль становится стек-специфичной

- `skills:` preload из профиля (`skills_map`) + self-load fallback в промте — на
  неизвестном/отключённом имени preload пропускается с записью в debug-лог, не тихим
  no-op без следа (first-party `https://code.claude.com/docs/en/sub-agents`, проверено
  2026-07-29). **Оговорка (teammate):** этот preload не применяется, когда роль запущена
  как teammate агент-команды — там skills/mcpServers берутся из проектных/user settings
  сессии, а не из определения агента (first-party `https://code.claude.com/docs/en/agent-teams`,
  проверено 2026-07-29). На этом пути self-load fallback в промте — ЕДИНСТВЕННЫЙ носитель,
  не подстраховка (см. [agent-teams](./agent-teams)).
- Стек-гейты (php8.4 vs node, PHPUnit vs Pest, access-layer вкл/выкл) — из ответов
  интервью пака, не хардкод в роли.
- path-scoped rules по путям стека (`app/**` vs `resources/js/**`).

## Наследование — на build-time пака, НЕ рантайм

Claude Code **не поддерживает** `extends:`/`@include` у агентов (проверено, офиц.
доки). Поэтому «общая база ролей» реализуется так: пак хранит обобщённые шаблоны →
при установке рендерит их в `.claude/agents/<prefix>-*.md` под профиль проекта.
Никакого рантайм-инклюда, который молча не сработал бы.

## Анти-паттерны (из аудитов, отклонено)

- Нумерация файлов `01_`,`02_` для приоритета — на `/agents` не влияет.
- Frontmatter `triggers/role/version/project_type` — не нативны, не использовать.
- file-lock (`touch {file}.lock`) против параллельных правок — заменён one-branch/worktree
  и module-boundaries.
