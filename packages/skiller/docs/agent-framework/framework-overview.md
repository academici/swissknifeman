# Framework Overview — текущее состояние

Канонический срез того, что уже есть в каркасе. **Это вход для аудита**
([framework-audit](../workflows/framework-audit)): подаёшь Perplexity вместе с
[decisions-ledger](./decisions-ledger), чтобы аудит искал дельты, а не
перепредлагал готовое.

Статусы: ✅ есть · 🔜 в работе (фаза плана) · ⏸ отложено.

## Дистрибуция и версионность

- ✅ **Пакеты:** `harness` (окружение Claude Code: хуки/settings/MCP/паки),
  `skiller` (скиллы + hub), `maind` (память/граф). Запись в проекты — merge-only + `.bak`.
- 🔜 **agent-packs** — версионируемые паки (`harness/configs/claude-code/agent-packs/<pack>/`):
  `pack.json` (semver) + `CHANGELOG.md` + agents/workflows/hooks/settings/docs.
  Per-pack версия. Установка/upgrade — агент-driven через скилл `system/agent-packs`.
- 🔜 **lock** — `.claude/agent-pack.lock.json` в проекте: версия + ответы интервью +
  `sha256` отрендеренных файлов → upgrade без diff-движка (хэш-сравнение + CHANGELOG).
- ⏸ **профили-наследование** (`extends`) — как данные, не движок (отложено).

## Скиллы и их видимость

- ✅ **Реестр** `skills.json` (+ `_index.md`, marketplace) — `skiller registry`.
- ✅ **Hub = AI Skills Index**: `scripts/generate-hub.sh`; в Boost-проектах пишется в
  `.ai/guidelines/swissknifeman-hub.md` (маркеры `<!-- swissknifeman:hub:start/end -->`),
  не в сгенерённый CLAUDE.md.
- ✅ **Нативное поле `skills:`** на субагенте (preload, Claude Code ≥2.0.43);
  молча no-op на неизвестном имени — отсюда регрессия «скиллы не видны».
- 🔜 **Фикс видимости** (Фаза 1): hub получает agent-routing срез + сверку имён
  `skills:` со `skills.json` (`⚠` на несостыковке) + freshness-штамп; `skiller doctor` флагит дрейф.

## Роли и оркестрация

- ✅ **Плагин-агенты**: `laravel-reviewer`, `laravel-test-writer` (php), `code-coordinator` (system).
- ✅ **Скилл оркестрации** `laravel-architecture/laravel-subagents` (порог делегирования, ревью/тесты, worktree).
- 🔜 **Универсальные роли** (Фаза 3): reviewer/implementer/test-writer/explore/plan/spec-writer
  как seed-агенты в паке; общие, стек — из профиля. `skills:` preload + self-load fallback.
- 🔜 **path-scoped rules** (`.claude/rules/`, нативно) — тонкие правила по путям, индекс в hub.

## Хуки и гейты

- ✅ **auto-approve** (PreToolUse), **memory**, **notify**, **log** (harness).
- ✅ **review-gate** (SubagentStop, off|warn|strict) — первая реализация в memster;
  harness-заглушка ещё пустая (🔜 поднять generic-раннер в harness).
- ✅ **Agent Teams** (опц., эксперимент, CC ≥2.1.178): пресет
  `harness/configs/claude-code/settings.agent-teams.json` (env-флаг + `teammateMode`) +
  doc [agent-teams](./agent-teams) (spawn-шаблоны, module-boundaries, quality-gate хуки).
  Config форвард-совместим; роли каркаса годятся как teammates.

## Воркфлоу

- ✅ **Workflow-инструмент** (нативный, ~16 конкуррентно / 1000 на прогон).
- 🔜 **dev-loop** как pack-шаблон (срез→impl→test→review). Уроки зашиты: один branch
  на прогон, хард-кап литералом (переживает resume), circuit-breaker.

## Задачи и память

- ✅ TodoWrite (сессия) + `args.slices` (прогон dev-loop).
- ⏸ Персистентный task-граф (next-task между сессиями) — на maind/agentmemory, отложено.

## Качество

- ✅ `quality/code-simplifier`, `general/anti-drift`.
- 🔜 **ponytail-дисциплина** (YAGNI-лесенка + over-engineering-проход) — впитываем в
  reviewer-роль + опц. скилл `quality/lean-code` (без внешнего плагина).

## Версия каркаса

`v0.1.0-wip` (сборка по плану `stateful-waddling-tulip`, 2026-06-23). Обновляй этот
файл в конце каждой фазы/аудита — он вход следующего аудита.
