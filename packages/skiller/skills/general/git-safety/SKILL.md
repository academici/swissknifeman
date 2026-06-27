---
name: git-safety
bucket: general
version: 0.1.0
lifecycle: init
description: "Guard against destructive git commands via a Claude Code PreToolUse hook: blocks push/reset --hard/clean -f/branch -D/checkout ./rebase --onto BEFORE execution. Activate on project init (esp. production/embedded) or when asked to add git guardrails / forbid dangerous git."
risk: write
persona: oss-dev
tags: [git, safety, hooks, guardrails, init]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
disable-model-invocation: false
sha256: ""
---

# Git Safety (guardrails)

Ставит PreToolUse-хук, который блокирует опасные git-команды **до** исполнения. В нашей экосистеме
сам хук-скрипт принадлежит пакету **harness** (источник истины хуков), а этот скилл — точка входа:
объясняет и помогает включить.

## Когда активировать

Один раз на проект (`lifecycle: init`) — на онбординге, особенно для production и embedded-проектов
(POS, фискальные устройства), где `git reset --hard`/`git push` на ветке устройства = поход к железу.
Или по явной просьбе «добавь git-guardrails / запрети опасный git».

## Что блокируется

`git push` (вкл. `--force`/`--force-with-lease`), `git reset --hard`, `git clean -f`/`-fd`,
`git branch -D`, `git checkout .`/`git restore .`, `git rebase --onto`.

## Как включить

1. Поставить файлы хуков глобально (один раз на машину): `harness hooks --global` — кладёт
   `~/.claude/hooks/git-guardrails/block-dangerous-git.sh`.
2. Зарегистрировать PreToolUse-хук (merge-only) в `.claude/settings.json` проекта
   (или `~/.claude/settings.json` глобально):

   ```json
   {
     "hooks": {
       "PreToolUse": [
         { "matcher": "Bash", "hooks": [
           { "type": "command", "command": "~/.claude/hooks/git-guardrails/block-dangerous-git.sh" }
         ] }
       ]
     }
   }
   ```

   Если settings уже есть — влить в существующий массив `hooks.PreToolUse`, не перетирая остальное.
3. Проверка: `echo '{"tool_input":{"command":"git push origin main"}}' | ~/.claude/hooks/git-guardrails/block-dangerous-git.sh` → exit 2 + BLOCKED.

> Кастомизация списка паттернов — правкой скрипта (источник: `packages/harness/configs/claude-code/hooks/git-guardrails/`).
> Follow-up: флаг `harness hooks --git-guardrails on` для авто-регистрации в settings.

## Связанные скиллы

- `general/git-commit-rules` — формат коммитов (что разрешено), git-safety — что запрещено.
- `oss-dev/github-flow` — общий git-поток, поверх которого работают guardrails.
