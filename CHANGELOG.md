# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
версионирование — [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

## [0.1.0] — 2026-06-14

### Added
- Ядро на Python + bash (тонкий лаунчер `bin/maind` → `python3 -m maind`), stdlib-only.
- **Память**: оркестрация Node-демона `@agentmemory/agentmemory` (`memory start/stop/status`)
  + HTTP-обёртка со scope'ами (`store/recall/forget/export`), сверенная с реальным API
  agentmemory 0.9.x (`/agentmemory/remember` · `/agentmemory/search` · `/agentmemory/health`).
  Порты — из env/конфига, без хардкода.
- **Граф**: stdlib property-граф (`node/edge/neighbors/path/subgraph/stats`) с персистом
  в node-link JSON; `networkx`/`graphify` как опциональные адаптеры через `graph.adapter`.
  Автозасев проектов/связей из конфига (`depends_on`/`uses`/`belongs_to`).
- **Реестр агентов**: `register/heartbeat/list/kill/reap` (`~/.maind/agents.json`),
  деривация состояния `alive/stale/dead` из heartbeat + живости pid.
- **Реестр проектов**: `.maind.json` (надмножество brain `.projects.json`) + fallback на
  legacy с предупреждением; `projects sync --from brain` (маппинг реальной схемы brain).
- **MCP-сервер**: `maind mcp` — stdio JSON-RPC, 6 tools (memory/graph/agents/projects).
- **Миграция**: `migrate from-brain` (конфиг + граф), `migrate from-agentmemory` (iii-config).
- **CLI**: `start`, `status`, `doctor`, сводный статус узла.
- `install.sh`, `.maind.example.json`, `.env.example`, `config/memory/iii-config.yaml`
  (service_name: maind), `scripts/test.sh`, `scripts/validate.sh`.
- Документация (VitePress, ru-RU), 65 unit-тестов (без живого демона — `FakeMemoryServer`).

[Unreleased]: https://github.com/academici/maind/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/academici/maind/releases/tag/v0.1.0
