# P1 — RAG-выжимка: факты Claude Code settings / permissions / hooks

**Дата верификации:** 2026-07-10 · **Движок:** агент `claude-code-guide` над официальными доках
(`code.claude.com/docs/en/{settings,permissions,permission-modes,hooks}.md`) · **Повод:** таксономия
проверок `settings-doctor` (`roadmap/settings-doctor.md`) стоит на этих фактах — их надо было сверить
до фиксации плана, а не после.

## Вердикты

| # | Утверждение спеки | Вердикт | Источник |
|:--|:--|:--|:--|
| 1 | Precedence слоёв: managed → CLI args → local → project → user | **ВЕРНО**, но с исключением (см. ниже) | settings.md |
| 2 | `defaultMode` задаёт только стартовый режим НОВОЙ сессии | **ВЕРНО** | permission-modes.md |
| 3 | `ask`-правила форсируют промпт в ЛЮБОМ режиме, включая `bypassPermissions`; `deny` применяется всегда | **ВЕРНО** | permissions.md · permission-modes.md |
| 4 | `dontAsk` = «тихо отклонять всё, что не в allow» (а не «разрешить всё») | **ВЕРНО** | permission-modes.md |
| 5 | Верхнеуровневый ключ `skipDangerousModePermissionPrompt` в settings.json | **НЕ ПОДТВЕРЖДЁН** — в таблице документированных ключей его нет | settings.md |
| 6 | VSCode: `claudeCode.initialPermissionMode` (default `"default"`) переопределяет `defaultMode` слоёв на старте сессии | **ЧАСТИЧНО**: `initialPermissionMode` документирован; второй параметр в доках дан UI-лейблом «Allow dangerously skip permissions», точное имя ключа не задокументировано | permission-modes.md (вкладка VS Code) |
| 7 | Хук не может обойти `deny`/`ask` | **ВЕРНО**, + хук-событие `PermissionRequest` СУЩЕСТВУЕТ (спека знала только `PreToolUse`) | hooks.md · permissions.md |
| 8 | `permissions.autoApprove` — канонический ключ | **НЕВЕРНО** — такого ключа нет | settings.md |
| 9 | `additionalDirectories` влияет на матчинг `Bash(...)`-правил | **НЕВЕРНО** — влияет только на path-доступ Read/Edit и авто-approve в `acceptEdits` | permissions.md |

## Ключевые цитаты

- **Исключение precedence (несущее для D4):** «5-tier scope system … (highest to lowest):
  1. Managed, 2. Command line arguments, 3. Local, 4. Project, 5. User. **Exception: Permission
  rules merge across scopes rather than override.**»
- **Ask поверх bypass (несущее для D3):** «Deny and ask rules are evaluated regardless of what a
  PreToolUse hook returns … Explicit ask rules still force a prompt in this mode [bypassPermissions]».
- **dontAsk:** «`dontAsk` mode auto-denies every tool call that would otherwise prompt. Only actions
  matching `permissions.allow` rules and read-only Bash can execute; explicit ask rules are **denied**
  rather than prompting.»

## Что это меняет в плане

1. Проверка №10 спеки («`bypassPermissions` заявлен, но `skipDangerousModePermissionPrompt`
   отсутствует» → warn) **переформулируется в info** и не гейтит: ключ недокументирован (D3).
2. Построитель «эффективной конфигурации» — ДВА режима слияния: override для обычных ключей,
   merge для `permissions.{allow,deny,ask,additionalDirectories}` (D4). Наивный override →
   ложные вердикты проверок №3/№4/№7.
3. Проверка №5 («объявленные хуки существуют и исполняемы») покрывает и `PermissionRequest` (D5).
4. Проверка №2 (неканонические ключи) получает эталонный кейс `permissions.autoApprove` (D6).
5. Проверка №6 VSCode-слоя: `claudeCode.initialPermissionMode` — гейтим; имя второго ключа
   (`allowDangerouslySkipPermissions`) сверить эмпирически по `package.json` расширения при
   исполнении P1.5 — в доках оно только UI-лейблом.

## Пере-сверка 2026-07-10 (проход 2, при проектировании P1)

**Движок:** агент `claude-code-guide` (два независимых запроса) + **эмпирика локальной ФС**
(`~/.vscode/extensions/anthropic.claude-code-2.1.206-linux-x64/package.json`).

### Подтверждено (несущее для реализации)

| Факт | Значение | Статус |
|:--|:--|:--|
| Managed-слой, путь | linux `/etc/claude-code/managed-settings.json` · macOS `/Library/Application Support/ClaudeCode/managed-settings.json` · win `C:\Program Files\ClaudeCode\managed-settings.json` (+ каталог `managed-settings.d/*.json`) | RAG:✅ server-managed-settings.md |
| Слияние `hooks` между слоями | **merge** массивов по событию + дедуп идентичных хендлеров (не override) | RAG:✅ hooks.md |
| Слияние `env` между слоями | **пер-ключевой override** (ключи низшего слоя выживают) | RAG:✅ settings.md |
| `permissions.*` подключи | `allow` `deny` `ask` `defaultMode` `additionalDirectories` `disableBypassPermissionsMode` `disableAutoMode`; **`autoApprove` отсутствует** (подтверждает D6) | RAG:✅ permissions.md |
| `defaultMode` enum | `default` (alias `manual`) · `acceptEdits` · `plan` · `auto` (research preview) · `dontAsk` · `bypassPermissions` | RAG:✅ permission-modes.md |
| `skipDangerousModePermissionPrompt` | по-прежнему **не задокументирован** (подтверждает D3 — проверка №10 остаётся `info`) | RAG:✅ settings.md |
| Официальная JSON-схема | `https://json.schemastore.org/claude-code-settings.json` (уже стоит в `$schema` пресетов harness) | RAG:✅ |
| VSCode-ключи (снимают оговорку п.5 «Что это меняет») | `claudeCode.initialPermissionMode` (string, default `"default"`) и `claudeCode.allowDangerouslySkipPermissions` (boolean, без default) — **существуют**; всего 14 ключей `claudeCode.*` | RAG:✅ эмпирика: `package.json` расширения 2.1.206 + vs-code-extension.md |

### Не подтверждено — обходится дизайном

- **`permissions.additionalDirectories`: merge across scopes или override?** Два прохода RAG
  разошлись (проход 1: «arrays merge, включая additionalDirectories»; проход 2: «не
  задокументировано, вероятен override»). → **[UNVERIFIED]**. Дизайн P1.1 не выбирает вариант:
  ядро хранит значения **per-layer** + union, а проверка №8 (существование путей) работает
  per-layer → её вердикт не зависит от неизвестной семантики. См. D15.
- **Полнота списка hook-событий.** Проход 2 вернул ~25 событий (`Setup`, `PermissionDenied`,
  `PostToolBatch`, `UserPromptExpansion`, `TeammateIdle`, …) — одним источником, без
  перекрёстной сверки. → **[UNVERIFIED]**. Отсюда правило P1.2: неизвестное событие в
  `hooks` даёт уровень **`info`** («нет в снапшоте от <дата>»), никогда не `warn`/`error`.

## Срок годности

Доки Claude Code меняются между версиями CLI (сверка велась против CLI/расширения **2.1.206**).
При исполнении P1.* — пере-сверить два `[UNVERIFIED]`-пункта выше и снапшот канонических ключей
(RAG-лестница: `claude-code-guide` → `perplexity-web` → `WebSearch`). Устаревшая выжимка хуже
отсутствующей.
