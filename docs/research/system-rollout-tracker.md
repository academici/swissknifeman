# System-бакет: топология / координатор / память — трекер внедрения

Рабочий трекер фич бакета `system` (топология → координатор → память).
Статус на 2026-06-14. Для возобновления работы.

## ✅ Отгружено в `main`

- **Топология** (PR #8): конфиг `~/.swissknifeman/topology.json`, бакет `system`,
  скилл `local-topology`, CLI `swissknifeman topology init|show`, notify-хук.
- **auto-approve** (PR #9): файлы хука `configs/claude-code/hooks/auto-approve/`
  + мелкие правки конфигов/доков.
- **Координатор + память** (PR #10): скилл `system/cross-project-coordinator`
  + агент `code-coordinator` (read-only); папка-хук
  `configs/claude-code/hooks/memory/` с режимами `file|federation|agentmemory|off`,
  membership, per-project override; скилл `system/shared-memory`; `validate.sh`
  проверяет хук-скрипты.

## ⬜ Осталось

### A. Активация на машине (one-time — без неё фичи не «оживают»)
- [ ] `swissknifeman topology init` — создать `~/.swissknifeman/topology.json`
      (авто-детект: swissknifeman=этот репо, projects_base=`~/projects`,
      brain=`~/Vaults/Brain` — подтвердить/поправить). **Координатор и память
      (federation/membership) зависят от него.**
- [ ] `./scripts/apply-permissions.sh --global` — поставить `hooks/{memory,notify,
      auto-approve}` в `~/.claude/hooks/`.
- [ ] Память: выбрать `MODE` в `~/.claude/hooks/memory/env.ini`, описать brains/
      members в `config.json`. Опц. — per-project хуки `SessionStart → recall` /
      `Stop → remember`.

### B. Docs «Фаза 2» (отдельный PR, отложено)
- [ ] Страница «Архитектура и топология» — диаграмма трёх узлов + каналы.
- [ ] Референс ВСЕХ хуков в одном месте (log-bash-command, auto-approve, notify, memory).
- [ ] Сквозной getting-started «с чистой ОС».
- [ ] Декомпозиция связи swissknifeman ↔ проекты ↔ Brain.

### C. agentmemory-режим — сверить API
- [ ] При включении `MODE=agentmemory`: проверить реальную форму HTTP-API
      (`/memories`, `/search`, `/health`) против демона
      (`cd ~/Vaults/Brain && npm run memory:start`) и поправить пути/jq в
      `configs/claude-code/hooks/memory/modes/agentmemory.sh`.

### D. Связать координатор ↔ память (enhancement)
- [ ] Координатор пишет межпроектные находки в общий мозг (`memory.sh remember`),
      чтобы `recall` их потом поднимал. Сейчас блоки независимы.

### E. Координатор: режим действия (roadmap)
- [ ] Из read-only советника → авто-вынесение в общий пакет + PR в целевые проекты.

### F. Память: доработки (future)
- [ ] Ранжирование по топология-близости (сейчас federation — только keyword).
- [ ] Дедуп/lifecycle фактов.
- [ ] Авто-хуки SessionStart/Stop как opt-in установка.

### G. Уборка
- [ ] Удалить `.claude/settings.local.json.bak`.
- [ ] Подчистить смёрдженные локальные ветки: `chore/product-readiness`,
      `feat/auto-approve-hook-files`, `feat/system-coordinator-memory`.
- [ ] Релиз/тег: в `CHANGELOG [Unreleased]` накопилось ~49 пунктов — нарезать
      версию, когда захочешь (`release-discipline`).

## Где что лежит
- Топология: `lib/swissknifeman/topology.py`, `skills/system/local-topology/`.
- Координатор: `skills/system/cross-project-coordinator/SKILL.md`,
  `skills/system/agents/code-coordinator.md`.
- Память: `configs/claude-code/hooks/memory/` (memory.sh, env.ini, config.json,
  lib/, modes/), скилл `skills/system/shared-memory/SKILL.md`.
- Установщик: `scripts/apply-permissions.sh` (`--global`); валидатор: `scripts/validate.sh`.
