# Agent Teams (Mesh) — опциональный слой

> Статус: эксперимент Claude Code. **Предпосылка: CC ≥ 2.1.178** (на 2.1.158
> недоступно). Конфиг форвард-совместим — флаг и team-события на старой версии просто
> не активны, ничего не ломают.

## Что это и когда

Agent Teams — несколько независимых сессий Claude, общающихся mesh-style (direct
messages + broadcast) через общий task list, а не только через оркестратора. Отличие
от субагентов: teammates полностью независимы и координируются сами; дороже (~3-4x
токенов).

| Берём Agent Teams | Остаёмся на субагентах/workflow |
|---|---|
| Несвязанные слои одновременно (API+фронт+тесты) | Последовательная задача / tight deps |
| Конкурирующие гипотезы (дебаг) | Нужна только параллелизация без общения |
| Архитектурный дебат между агентами | Ограничен бюджет токенов |

Роли каркаса (`reviewer`/`implementer`/`test-writer`/`spec-writer`) **годятся как
teammates** без изменений — те же `.claude/agents/*.md`.

## Включение (опц.)

Влить пресет (merge-only) `harness/configs/claude-code/settings.agent-teams.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }, "teammateMode": "auto" }
```

`teammateMode`: `in-process` (один терминал) | `auto` (split при tmux/iTerm2) | `tmux`
| `iterm2`. Конфиг сосуществует с PreToolUse(auto-approve)/SubagentStop(review-gate) —
события разные, конфликта нет.

## Quality-gate хуки (опц., после апгрейда CC)

Официальные события `TeammateIdle` / `TaskCompleted` — можно повесить ту же проверку,
что review-gate (exit 2 → задача не завершается, агент чинит). Добавлять в
`.claude/settings.json` append-if-absent, когда CC обновлён и можно протестировать:

```json
{ "hooks": { "TeammateIdle": [ { "hooks": [ { "type": "command",
  "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/review-gate.sh" } ] } ] } }
```

## Module-boundaries (предотвращение конфликтов)

Параллельные teammates НЕ должны писать в один файл. Координация через task list, НЕ
file-lock (`touch *.lock` отклонён как хрупкий). В `.ai/guidelines/` проекта (в Boost —
не в сгенерённый CLAUDE.md) зафиксируй зоны:

```
- app/Http/, app/Actions/, app/Repositories/  → backend-роль
- resources/js/, pages/                        → frontend-роль
- tests/                                        → test-writer
- Общие модели/маршруты: один владелец за прогон; пересечение — последовательно
  или worktree-изоляция, не параллельная запись.
```

## Spawn-шаблоны

**Full-stack фича:**
```
Spawn 3 teammates:
1. backend-implementer: API-эндпоинт
2. frontend-implementer: фронт для эндпоинта
3. reviewer: ревью обоих диффов (over-engineering + канон)
Требуй plan approval перед изменениями.
```

**Параллельный дебаг:**
```
Spawn 2 teammates (read-only) для бага <описание>:
1. hypothesis-a: проверяет <причина А>
2. hypothesis-b: проверяет <причина Б>
Обменяйтесь находками, верните lead единый вывод.
```

## Ограничения

- Экспериментально (CC ≥2.1.178); resume не сохраняет team config (task list персистентен).
- Teammate-модель не наследует `/model` лида — указывай явно в spawn.
- Broadcast дорог — только direct messages, broadcast как исключение.
- file-lock протокол — НЕ используем (отклонён); зоны через module-boundaries.
