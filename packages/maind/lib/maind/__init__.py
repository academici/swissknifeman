"""maind — центральный узел экосистемы academici (память + граф + агенты).

Логика — в пакете lib/maind; bin/maind тонкий лаунчер, вызывает
`python3 -m maind <repo_root> <cmd> [args...]`.

Модули:
  common    — Env, die/warn/now_iso/confirm, parse_args, atomic JSON, HTTP
  constants — порты памяти, типы узлов/рёбер графа, дефолты
  config    — config.json (+ fallback на legacy .projects.json из brain)
  memory    — жизненный цикл agent-memory демона + HTTP-обёртка (scopes)
  graph     — property-граф: node/edge/neighbors/path/subgraph/stats
  agents    — реестр агентов: register/heartbeat/list/kill
  projects  — реестр проектов (надмножество .projects.json) + sync из brain
  mcp       — stdio JSON-RPC MCP-сервер (tools для memory/graph/agents/projects)
  start     — оркестрация воркеров (start) + сводный статус (status)
  migrate   — импорт из brain (.projects.json) и agent-memory (.agentmemory)
  doctor    — диагностика окружения
  cli       — диспетчер команд (точка входа __main__)

Окружение передаётся через Env (common.Env) — без модульных глобалей, тестируемо.
"""
