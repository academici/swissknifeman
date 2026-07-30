# Framework Overview — текущее состояние

Канонический срез того, что уже есть в каркасе. **Это вход для аудита**
([framework-audit](../workflows/framework-audit)): подаёшь Perplexity вместе с
[decisions-ledger](./decisions-ledger), чтобы аудит искал дельты, а не
перепредлагал готовое.

Статусы: ✅ есть · 🔜 в работе (фаза плана) · ⏸ отложено.

## Дистрибуция и версионность

- ✅ **Пакеты:** `harness` (окружение Claude Code: хуки/settings/MCP/паки),
  `skiller` (скиллы + hub), `maind` (память/граф). Запись в проекты — merge-only + `.bak`.
- ✅ **agent-packs** — версионируемые паки (`harness/configs/claude-code/agent-packs/<pack>/`):
  `pack.json` (semver) + `CHANGELOG.md` + agents/workflows/hooks/settings/docs.
  Per-pack версия. Установка/upgrade — агент-driven через скилл `system/agent-packs`.
  Десять живых паков (`configs/claude-code/agent-packs/backend-laravel/pack.json` 0.12.2,
  `_common/pack.json` 0.5.0, `dart-flutter/pack.json` 0.5.2, `laravel-package/pack.json`
  0.2.2, `node-frontend/pack.json` 0.5.2, `python-backend/pack.json` 0.5.2,
  `role-cto/pack.json` 0.1.2, `role-founder/pack.json` 0.1.2, `role-maintainer/pack.json`
  0.2.2, `role-tech-lead/pack.json` 0.2.2).
- ✅ **lock** — `.claude/agent-pack.lock.json` в проекте: версия + ответы интервью +
  `sha256` отрендеренных файлов → upgrade без diff-движка (хэш-сравнение + CHANGELOG).
  Носитель — `packages/harness/lib/harness/agentpacks.py`.
- ⏸ **профили-наследование** (`extends`) — как данные, не движок (отложено); в
  `profiles/*.json` не используется (`grep -l extends packages/skiller/profiles/*.json` — пусто).

## Скиллы и их видимость

- ✅ **Реестр** `skills.json` (+ `_index.md`, marketplace) — `skiller registry`.
- ✅ **Hub = AI Skills Index**: `scripts/generate-hub.sh`; в Boost-проектах пишется в
  `.ai/guidelines/swissknifeman-hub.md` (маркеры `<!-- swissknifeman:hub:start/end -->`),
  не в сгенерённый CLAUDE.md.
- ✅ **Нативное поле `skills:`** на субагенте (preload, Claude Code ≥2.0.43); на
  неизвестном/отключённом имени — пропуск + запись в debug-лог, не тихий no-op без следа
  (first-party `https://code.claude.com/docs/en/sub-agents`, проверено 2026-07-29) — отсюда
  регрессия «скиллы не видны», пока имена не сверены.
- ✅ **Фикс видимости** (Фаза 1, `packages/skiller/scripts/generate-hub.sh`): hub получает
  agent-routing срез + сверку имён `skills:` со `skills.json` (`⚠` на несостыковке) +
  freshness-штамп; `skiller doctor` флагит дрейф (`generate-hub.sh:194` freshness-хэш,
  `:253-255` `⚠` на несостыковке; `packages/skiller/lib/skiller/doctor.py:1062-1090` дрейф хабов).

## Роли и оркестрация

- ✅ **Плагин-агенты**: `laravel-reviewer`, `laravel-test-writer` (php), `code-coordinator` (system).
- ✅ **Скилл оркестрации** `laravel-architecture/laravel-subagents` (порог делегирования, ревью/тесты, worktree).
- ✅ **Универсальные роли** (`configs/claude-code/agent-packs/role-bindings.json`):
  reviewer/implementer(slice-builder)/test-writer/explore/plan/spec-writer как seed-агенты
  рендерятся из паков через связывание (`binding_version 1.0.0`, роли `_common` +
  стек-паков); общие, стек — из профиля.
  `skills:` preload + self-load fallback — preload **не применяется**, когда роль
  запущена как teammate агент-команды (см. [roles](./roles), [agent-teams](./agent-teams)).
- 🔜 **path-scoped rules** (`.claude/rules/`, нативно) — тонкие правила по путям есть у пяти
  паков (`agent-packs/{_common,backend-laravel,dart-flutter,laravel-package,node-frontend,
  python-backend}/rules`), **индекса правил в hub нет** (`grep -n rules
  packages/skiller/scripts/generate-hub.sh` — пусто).

## Хуки и гейты

- ✅ **auto-approve** (PreToolUse), **memory**, **notify**, **log** (`packages/harness/configs/claude-code/hooks/`).
- ✅ **review-gate** (SubagentStop, off|warn|strict, `packages/harness/configs/claude-code/hooks/review-gate/review-gate.sh`)
  — полноценный generic-раннер, 128 строк, диспетчер `checks/`.
- ✅ **Agent Teams** (опц., эксперимент, CC ≥2.1.178, дефолт `teammateMode` — `in-process`
  с v2.1.179): пресет `harness/configs/claude-code/settings.agent-teams.json` (env-флаг +
  `teammateMode`) + doc [agent-teams](./agent-teams) (spawn-шаблоны, module-boundaries,
  quality-gate хуки). Config форвард-совместим; роли каркаса годятся как teammates, **но без
  своего `skills:`-preload** — см. [agent-teams](./agent-teams) «Ограничения».

## Воркфлоу

- ✅ **Workflow-инструмент** (нативный, ~16 конкуррентно / 1000 на прогон — потолок workflow-рантайма, `findings/04` Ф17) — Agent-тул несёт СВОИ потолки, см. «Лимиты
  субагентов» ниже; агенты workflow в них не считаются.
- ✅ **dev-loop** как pack-шаблон (`workflows/dev-loop.js`) у пяти паков
  (backend-laravel, node-frontend, python-backend, dart-flutter, laravel-package),
  срез→impl→test→review. Уроки зашиты: один branch на прогон, хард-кап литералом
  (переживает resume), circuit-breaker.

## Лимиты субагентов (Agent-тул, first-party `https://code.claude.com/docs/en/sub-agents`,
проверено 2026-07-29)

- Всего субагентов за сессию: **200** (`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`, v2.1.212+).
- Одновременно: **20** (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, v2.1.217+).
- Глубина вложенности: **3** (v2.1.219; было 1 в v2.1.217–218, 5 неизменяемо до v2.1.172–216).

## Задачи и память

- ✅ TodoWrite (сессия) + `args.slices` (прогон dev-loop).
- ⏸ Персистентный task-граф (next-task между сессиями) — на `maind`/agentmemory, отложено.

## Качество

- ✅ `quality/code-simplifier`, `general/anti-drift`.
- ✅ **ponytail-дисциплина** (YAGNI-лесенка + over-engineering-проход, `agent-packs/{backend-laravel,laravel-package}/agents/reviewer.md`)
  впитана в reviewer-роль; опциональный скилл `quality/lean-code` не заведён и не
  планировался обязательным (`packages/skiller/skills/quality/` — 11 скиллов, `lean-code`
  среди них нет).

## Проверено против дерева: 2026-07-30

| Пак | Версия |
|:--|:--|
| _common | 0.5.0 |
| backend-laravel | 0.12.2 |
| dart-flutter | 0.5.2 |
| laravel-package | 0.2.2 |
| node-frontend | 0.5.2 |
| python-backend | 0.5.2 |
| role-cto | 0.1.2 |
| role-founder | 0.1.2 |
| role-maintainer | 0.2.2 |
| role-tech-lead | 0.2.2 |

Таблица — машинный якорь гейта свежести (P3.3): версии сверяются с `pack.json` каждого пака
в `packages/harness/configs/claude-code/agent-packs/*/pack.json`. Обновляй этот файл и штамп
в конце каждой фазы/аудита — он вход следующего аудита.
