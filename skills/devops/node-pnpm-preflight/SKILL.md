---
name: node-pnpm-preflight
bucket: devops
version: 0.1.0
description: "Проверка доступности Node/pnpm на хосте перед командами и git hooks, которые используют pnpm (commitlint, lint, сборка)."
risk: read
persona: operator
tags: [node, pnpm, devops]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Node/pnpm Preflight

Используйте этот skill перед любыми хостовыми командами, где нужен `pnpm` или `node`:

- git hooks (`commit-msg`, `pre-commit`, `commitlint`)
- frontend-команды (`pnpm lint`, `pnpm test`, `pnpm build`)
- любые локальные скрипты из `package.json`

## Порядок проверки

1. Проверьте `pnpm --version`.
2. Если `pnpm` не найден: выполните `nvm use 22`.
3. Повторно проверьте `pnpm --version`.
4. Если после `nvm use 22` `pnpm` всё ещё недоступен — остановитесь и сообщите блокер.  
   Не пропускайте hooks.

## Для коммитов

Перед `git commit` убедитесь, что `pnpm` и `node` доступны в текущем shell-сеансе, иначе `commit-msg` hook с `commitlint` упадет.
