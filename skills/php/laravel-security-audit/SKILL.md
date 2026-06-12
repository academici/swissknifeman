---
name: laravel-security-audit
bucket: php
version: 0.1.0
description: "Аудит Laravel-кода на «острые грани»: raw-запросы Eloquent, mass assignment, XSS в Blade, CSRF-обходы, open redirect, небезопасная сериализация, дыры авторизации."
risk: draft
persona: oss-dev
tags: [php, laravel, security]
requires: [static-analysis]
produces_for: [security-design]
outputs: []
snippets: ["security-audit-scheduled.yml"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Laravel Security Audit

## Когда активировать

- Перед релизом/деплоем или при подготовке security-ревью.
- При ревью PR, затрагивающего auth, ввод пользователя, запросы к БД, файлы.
- По расписанию как фоновый аудит (см. сниппет).

Методика — «sharp edges»: ищем не только баги, но и паттерны, которые
выглядят безобидно и провоцируют уязвимости при следующей правке.

## Алгоритм аудита

1. **Grep-проход.** Прогнать поисковые паттерны из таблицы ниже по
   `app/`, `routes/`, `resources/views/`, `config/`.
2. **Ручная верификация.** Каждое совпадение — проверить контекст:
   действительно ли пользовательский ввод достигает опасного места.
   Совпадение ≠ уязвимость; отчёт без верификации — шум.
3. **Отчёт с severity.** Каждая находка: файл:строка, цепочка от ввода
   до уязвимого вызова, severity (critical / high / medium / low),
   рекомендация. Результат — вход для `security-design`.

## Таблица «острых граней»

| Грань | Что ищем (grep) | Детали |
|---|---|---|
| Raw-запросы Eloquent | `DB::raw`, `whereRaw`, `selectRaw`, `orderByRaw`, `DB::statement` | [references/eloquent-raw-queries.md](references/eloquent-raw-queries.md) |
| Mass assignment | `$guarded = []`, `request()->all()` рядом с `create(`/`update(`, `forceFill` | [references/mass-assignment.md](references/mass-assignment.md) |
| XSS в Blade | `{!!`, `@js(`, `v-html`, `Js::from` | [references/blade-xss.md](references/blade-xss.md) |
| CSRF и redirect | `VerifyCsrfToken` `$except`, `redirect($request`, `redirect()->to($` | [references/csrf-and-redirects.md](references/csrf-and-redirects.md) |
| Сериализация и авторизация | `unserialize(`, отсутствие Policy/`authorize()`, IDOR по id из запроса | [references/serialization-authz.md](references/serialization-authz.md) |

## Чего НЕ делает этот скилл

- Не проверяет зависимости — это `dependency-audit` (composer audit и т.п.).
- Не заменяет статический анализ — `static-analysis` (PHPStan/larastan)
  должен уже стоять; аудит опирается на его сигналы.
- Не чинит найденное автоматически — аудит производит отчёт, фиксы
  идут отдельными задачами по приоритету severity.

## Фоновый режим

`snippets/security-audit-scheduled.yml` — шаблон GitHub Actions: аудит
по cron + ручной запуск, результат — GitHub Issue с категоризацией
по severity. См. docs/workflows/background-agents.
