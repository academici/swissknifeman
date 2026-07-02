# pack-guard — слой 2 mutation-защиты generated-ассетов (опционально)

Опциональный **Python-хук** Claude Code (`PreToolUse`), который ловит правку generated-файла
agent-pack'а **до** того, как она случится — в отличие от слоя 1 (`lock_drift()` /
[`harness agent-packs doctor --drift`](../../../lib/harness/agentpacks.py) / `pack_drift()` в
`maind analyze`), который ловит правку **постфактум**. По умолчанию **НЕ устанавливается**:
включается явно per-project, рекомендация — overnight/unattended dev-loop.

## Режимы

| Режим | Поведение |
|:--|:--|
| `off` (дефолт) | хук не регистрируется в проекте |
| `warn` | stderr-предупреждение при правке generated-файла, **не блокирует** |
| `strict` | **блокирует** Edit/Write/MultiEdit/NotebookEdit по generated-файлу (exit 2) |

`user_owned`-файлы (оверлеи — точка расширения base+overlay, D11) guard'ом НЕ трогает: их
редактировать можно и нужно.

## Решение — по lock-файлу проекта

Хук читает `<project>/.claude/agent-pack.lock.json`, собирает `packs[].files[].target` БЕЗ
`user_owned` — это и есть managed-набор. Тот же разбор, что `_protected_sets()` в
[`../run-report/_lib.py`](../run-report/_lib.py) (осознанный маленький дубль — автономность
хука, PYTHONPATH монорепо в `~/.claude/hooks` недоступен). Нет lock'а / он битый / файл не под
управлением пака → пропуск (exit 0), никогда не блокирует «на всякий случай».

## Файлы

| Файл | Роль |
|:--|:--|
| `pack-guard.py` | PreToolUse-хук: stdin → решение по lock → exit 0/2 (+ stderr-сообщение) |
| `env.ini` | `MODE` (off/warn/strict). Per-project override в `.claude/pack-guard.env.ini` |

## Установка / включение

```bash
harness hooks --global                              # копирует хук в ~/.claude/hooks/pack-guard/
harness hooks --target . --pack-guard strict         # включить в проекте (env.ini + регистрация PreToolUse)
harness hooks --target . --pack-guard off            # выключить (kill-switch, хук остаётся зарегистрирован, но неактивен)
```

## I/O-контракт (для отладки)

Хук читает JSON payload PreToolUse на stdin (`cwd`/`tool_name`/`tool_input`), решение — по
lock-файлу `<cwd>/.claude/agent-pack.lock.json`. Ничего на диск не пишет.

```bash
echo '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/.claude/agents/x.md"}}' \
  | python3 pack-guard.py   # strict + managed-файл → exit 2, причина в stderr
echo 'not json{' | python3 pack-guard.py   # → exit 0 (никогда не роняет сессию)
```

## Честные лимиты (не переобещаем)

- **Дубль разбора lock'а с `run-report/_lib.py`** — сознательный (оба хука автономны в
  `~/.claude/hooks`, PYTHONPATH монорепо там недоступен); дрейф между копиями ловить некому
  автоматически (см. D8 для аналогичного случая `_usage.py` — здесь sync-скрипта нет,
  разбор простой ~15 строк).
- **Сообщение в stderr — best-effort**, не содержит точный путь к оверлею конкретного
  файла (это несёт `Extension-points:` в самом provenance-header) — только имя пака.
