---
name: git-commit-rules
bucket: general
version: 0.1.0
description: "Правила работы с Git в проекте: подготовка коммита, husky/commitlint, формат сообщений и безопасный порядок действий."
risk: write
persona: oss-dev
tags: [git, conventions]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Git Commit Rules

Используйте этот skill, когда задача включает:

- `git commit`, `git add`, `git status`, подготовку PR
- разбор ошибок git hooks
- проверку формата commit message

## Обязательный порядок перед коммитом

1. Проверить состояние: `git status --short`.
2. Проверить изменения: `git diff` (и `git diff --staged`, если нужно).
3. Перед запуском коммита применить preflight для Node/pnpm: `.ai/skills/node-pnpm-preflight/SKILL.md`.
4. Убедиться, что hooks не обходятся (`--no-verify` запрещен без явного запроса пользователя).
5. Выполнить `git commit` только после успешных локальных проверок.

## Husky + Commitlint

- `commit-msg` hook считается обязательной проверкой.
- Если hook падает из-за окружения (`pnpm`/`node` недоступны):
  - не отключать hook;
  - сначала восстановить окружение через `node-pnpm-preflight`;
  - только после этого повторять коммит.

## Формат сообщения коммита

- Использовать conventional-стиль проекта.
- Сообщение — на русском языке.
- Типовые префиксы: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.
- Scope брать из разрешенного списка проекта (commitlint): `ticket`, `policy`, `actions`, `services`, `workflow`, `filament`, `api`, `auth`, `meeting`, `notification`, `deps`.
- Заголовок формулировать как "сделали", а не как "сделать":
  - использовать прошедшее время, чаще множественное число: `добавили`, `исправили`, `убрали`, `обновили`.
  - избегать инфинитивов: `добавить`, `исправить`, `сделать`.
- Стиль: короткий заголовок + при необходимости 1-2 строки с причиной изменений.
- Формулировка должна выглядеть как сообщение от человека, а не шаблон ИИ:
  - конкретный результат + зачем это нужно;
  - без канцеляризмов и без "универсальных" фраз.

Пример:

```text
refactor(workflow): унифицировать кэш policy abilities

Убрал дубли в DTO и вынес общий helper для кэширования.
```

Дополнительные примеры для "человеческого" стиля:

```text
ci(deps): добавили php-расширения для composer install

Добавили ldap/gd/exif в GitLab CI, чтобы composer install не падал на platform req.
```

```text
fix(api): исправили проверку роли в ответе тикета

Убрали ложный 403 для участников без роли исполнителя.
```

Антипример:

```text
ci(deps): добавить php-расширения для composer install
```

## Безопасность

- Не выполнять destructive git-команды без явного запроса пользователя.
- Не смешивать в коммите несвязанные изменения.
- Не править generated AI-артефакты (`CLAUDE.md`, `AGENTS.md`) вручную.
