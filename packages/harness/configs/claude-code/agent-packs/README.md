# agent-packs — версионируемые паки agent-практик

Пак = версионируемый бандл Claude Code артефактов (агенты/воркфлоу/хуки/settings/доки),
который агент устанавливает и обновляет в проекте. **Раздаёт не код, а данные**:
установку/адаптацию/upgrade выполняет агент по `pack.json` + `CHANGELOG.md` + lock,
без Python/Mustache движка (см. скилл `system/agent-packs` в skiller).

## Структура пака

```
<pack>/
  pack.json        # manifest: version, stack-detect, requires, interview[], files[]
  CHANGELOG.md     # per-pack semver + agent-facing Migration notes
  agents/          # шаблоны .md (name: {{PACK_PREFIX}}-<role>)
  workflows/       # шаблоны .js
  hooks/           # review-gate.sh (verbatim) + .env.ini (template)
  settings/        # settings.fragment.json (merge в .claude/settings.json)
  docs/            # guideline-шаблон
```

## Плейсхолдеры

`{{PLACEHOLDER}}` в файлах `kind: template` подставляются из ответов интервью
(`pack.json:interview`). Блоки `<!-- pack:if KEY -->...<!-- pack:endif -->` агент
оставляет/убирает по булеву ответу. Файлы `kind: verbatim` копируются без правок.

## Установка / upgrade

Через скилл **`system/agent-packs`** (skiller): детект стека → интервью → рендер+копия
→ lock (`.claude/agent-pack.lock.json`) → пост-проверка
(`docs/skiller/agent-framework/post-integration-checklist`). Upgrade — по CHANGELOG-дельте
с 3-way reasoning через sha256 в lock, без diff-движка.

## Паки

| Пак | Shape | Стек | Версия |
|---|---|---|---|
| `backend-laravel` | backend | Laravel/PHP | 0.1.0 |

Fullstack = композиция паков по концерну (`backend-laravel` + будущий `frontend-vue`);
роли универсальны, стек выбирает профиль.
