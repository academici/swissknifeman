# P5 read-only recon — текущие harness surfaces

**Дата:** 2026-07-19  
**Метод:** чтение `packages/harness/CLAUDE.md`, `rg --files`, `rg -n` и точечное чтение
модулей/конфигов. Package code, package scripts, FOREMAN и fleet не исполнялись и не
изменялись.

## Наблюдаемая граница

- `Env.configs_dir` жёстко указывает на `configs/claude-code`; `mcp_dir` и
  `agent_packs_dir` наследуют эту provider-specific базу.
- `permissions.py` делегирует `scripts/apply-permissions.sh`, который рендерит только
  `.claude/settings*.json`; current presets и policy-аудит используют Claude vocabulary.
- `hooks.py` одновременно хранит semantic intent (`memory`, `router`, `run-report`,
  `plans-dir`) и Claude registration details (`PreToolUse`, `SessionStart`,
  `~/.claude/hooks`, `.claude/settings.json`).
- `mcp.py` читает `configs/claude-code/mcp/*.json` и merge-only пишет `.mcp.json`.
- `agentpacks.py` имеет зрелые provenance/lock/upgrade/conflict semantics, но target paths,
  lock path и manifests ориентированы на `.claude/agents|hooks|settings|workflows`.
- `settings_audit.py` моделирует Claude layers `user→project→local→managed` и не является
  generic provider audit engine.

RAG:— (repo-grounded: `packages/harness/lib/harness/{common,permissions,hooks,mcp,agentpacks,settings_audit}.py`)

## Существующие сильные seams, которые надо сохранить

- merge-only запись, backup и уважение user-owned значений;
- dry-run/check-friendly functions и tempdir tests;
- provenance/hash/lock и категории upgrade для agent packs;
- fail-closed safe-dirs/auto-approve policy и read-only settings doctor;
- stdlib-only runtime и явный `Env`.

RAG:— (repo-grounded: `packages/harness/CLAUDE.md`,
`packages/harness/tests/test_{permissions,hooks,mcp,agentpacks,settings_audit}.py`)

## Design consequence

Общий слой не может быть переименованным `configs/claude-code`: он должен хранить stable
profile/surface intent и explicit provider mapping. Claude hook/settings/audit semantics
остаются named adapter'ом с compatibility gate; Codex получает самостоятельный native
adapter. Provider-native event names, trust layers и target files не переносятся в common
schema как универсальные поля.

RAG:— (repo-grounded: `research/01-target-architecture-options.md`, D2/D5/D9)

## Protected boundary для P5 execution

До P7 self-host apply любые P5 tests/renders работают только в `TemporaryDirectory` или
declared package fixture targets. Root `.agents/**`, root `.claude*`,
`plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md` и fleet project roots — read-only protected
paths; delta вне item `Files` равна нулю.

RAG:— (repo-grounded: `AGENTS.md`, `brief/00-brief.md`, D6/D7/D12)
