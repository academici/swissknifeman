# changelog-gate — commit-гейт CHANGELOG-дисциплины (опционально)

Опциональный **Python-хук** Claude Code (`PreToolUse`, matcher `Bash`), который ловит
`git commit` содержательного типа (`feat`/`fix`/`perf`/`refactor`) без правки CHANGELOG среди
застейдженных файлов — enforcement секции «Повседневная дисциплина CHANGELOG» скилла
[`oss-dev/release-engineering`](../../../../../skiller/skills/oss-dev/release-engineering/SKILL.ru.md)
(правило держится на памяти модели — гейт детерминированно ловит пропуск). По умолчанию
**НЕ устанавливается**: включается явно per-project.

## Режимы

| Режим | Поведение |
|:--|:--|
| `off` (дефолт) | хук не регистрируется в проекте |
| `warn` (рекомендуется) | warning **в контекст модели** (`hookSpecificOutput.additionalContext`), **не блокирует** |
| `strict` | **блокирует** `git commit` (exit 2 + причина в stderr) |

## Детекция (D33)

- тип коммита и skip-маркер парсятся **ТОЛЬКО** из `-m`-сообщения самой команды: сообщение
  через `$EDITOR` (`git commit` без `-m`) не парсится — no-op, гейт не угадывает;
- содержательный тип — **ровно** `feat`/`fix`/`perf`/`refactor` (по началу первого `-m`);
  `docs`/`chore`/`test`/`style`/`ci`/`build` и любой иной префикс — авто-skip, без warning;
- маркер `[changelog-skip]` в любом `-m` — осознанное исключение, skip без warning;
- «CHANGELOG затронут» = среди `git diff --cached --name-only` есть путь, матчащий
  `(?i)changelog` — **любой** CHANGELOG (корневой либо per-package) удовлетворяет условие
  (монорепо-дружественно, путь не захардкожен);
- репо **без единого** `CHANGELOG*` в дереве (`git ls-files` не находит совпадения) → exit 0
  (проект не ведёт эту дисциплину — безопасный no-op, зеркалит pack-guard «нет lock'а»).

MAJOR/breaking гейт НЕ классифицирует (D32/D33 — это вручную владелец, вне скоупа гейта).

## Файлы

| Файл | Роль |
|:--|:--|
| `changelog-gate.py` | PreToolUse-хук: stdin → решение по `-m` + staged-файлам → exit 0/2 (+ warning) |
| `env.ini` | `MODE` (off/warn/strict). Per-project override в `.claude/changelog-gate.env.ini` |

## Установка / включение

```bash
harness hooks --global                                  # копирует хук в ~/.claude/hooks/changelog-gate/
harness hooks --target . --changelog-gate warn           # включить в проекте (env.ini + регистрация PreToolUse)
harness hooks --target . --changelog-gate strict         # блокирующий режим
harness hooks --target . --changelog-gate off             # выключить (kill-switch, хук остаётся зарегистрирован, но неактивен)
```

## I/O-контракт (для отладки)

Хук читает JSON payload PreToolUse на stdin (`cwd`/`tool_name`/`tool_input.command`), решение —
по `-m`-сообщению команды и `git diff --cached --name-only`/`git ls-files` в `cwd`. Ничего на
диск не пишет.

```bash
echo '{"cwd":"/proj","tool_name":"Bash","tool_input":{"command":"git commit -m \"feat: X\""}}' \
  | python3 changelog-gate.py   # warn + содержательный тип без CHANGELOG staged → JSON на stdout, exit 0
echo 'not json{' | python3 changelog-gate.py   # → exit 0 (никогда не роняет сессию)
```

## Non-blocking warning в контекст модели

RAG:✅ 2026-07-11 (`code.claude.com/docs/en/hooks.md`, perplexity-web): для `PreToolUse`
non-blocking контекст доставляется через JSON на stdout с exit 0 —
`hookSpecificOutput.{hookEventName:"PreToolUse", permissionDecision:"allow", additionalContext:<reason>}`
(поле `additionalContext` игнорируется только при `permissionDecision:"defer"`, поэтому warn
всегда несёт явный `"allow"`). `strict` не использует JSON-канал — блокирует стандартным
`exit 2` + причина в stderr (как `pack-guard`/`block-dangerous-git.sh`).

## Честные лимиты (не переобещаем)

- Тип и skip-маркер видны только если коммит делается через `-m` в самой Bash-команде;
  `git commit` без `-m` (открывает `$EDITOR`) хук не видит — не угадывает, no-op.
- «Содержательность» — исключительно по conventional-commit префиксу (D33): path-эвристика
  по изменённым файлам сознательно отвергнута как хрупкая.
- Гейт не классифицирует MAJOR/breaking — это всегда ручное решение владельца (D32).
