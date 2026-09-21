# Design baseline — 2026-09-20

## Внешняя перепроверка

Perplexity `search_advanced(web, academic)` и независимый web search подтвердили только
ограниченную предпосылку: persistent instructions загружаются в контекст, а skills
могут загружаться progressive-disclosure. Ни один публичный источник не доказывает, что
swissknifeman уже платит неприемлемую цену или что конкретный carrier нужно удалить.

RAG:✅ первичные источники:

- OpenAI Codex AGENTS.md: <https://developers.openai.com/codex/agent-configuration/agents-md>
- OpenAI Codex best practices: <https://developers.openai.com/guides/best-practices>
- Anthropic Agent Skills overview: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
- Anthropic Skill authoring best practices: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>
- Grok 4.6 official model page: <https://docs.x.ai/developers/grok-4-6>
- Composer 2.5 official model page: <https://cursor.com/docs/models/cursor-composer-2-5>

Официально подтверждены: `grok-4.6` — 500k context, reasoning effort и API/tool surface;
`composer-2.5` — 200k context и Cursor-native search/edit/terminal/browser tools. Это vendor facts,
а не независимый quality benchmark. Локальный `agent --list-models` показал
`cursor-grok-4.6-{low,medium,high,xhigh}` и `composer-2.5`.

## Repository evidence

- В `core/codegraph_telemetry.py`, `packages/maind/lib/maind/codegraph_usage.py` и run-report hooks уже есть
  базовый учёт codegraph calls; новый telemetry subsystem до доказанного пробела не нужен.
- Claude run-report parser учитывает `maind_memory_*` и `maind_graph_*`; Cursor sidecar сейчас
  агрегирует codegraph, но не считает maind result usefulness. Provider coverage нужно доказать до вывода о ценности.
- Агрегат по последним до 40 report на проект: swissknifeman 33, corex 22,
  agentools 5, edufy 36. Во всех 96 отчётах записано 0 maind memory calls,
  0 federation graph calls и 0 codegraph calls. Это RAG:— evidence gap, а не verdict.
- `maind_projects_status` показал для swissknifeman/corex/agentools/edufy `status=connected`,
  memory reachable и `code_mcp=false`. Измерять code graph на таком baseline без pilot-включения нельзя.
- Локальные деревья крупные и dirty: corex 4500 tracked/450 status entries,
  agentools 2073/138, edufy 2992/1104. Field audit обязан быть read-only и не смешивать эти изменения с кандидатом swissknifeman.

## Environment defects

- Perplexity MCP был записан в `.codex/config.toml`, но его tool не был зарегистрирован в текущем turn.
  Перепроверка выполнена через тот же локальный MCP server штатным SDK client; config не изменялся.
- Первый Codex route capture отклонил многострочный payload; повтор с exact Task invocation line
  подтвердил `gpt-5.6-sol/high`, cwd, `approval=never` и `danger-full-access` из provider thread state.
- Выборочная qualification `packages/task/scripts/validate.sh --plan <PLAN>` не green: 1108 тестов
  прошли, 1 skipped, а `test_generated_model_roles_reference_is_deterministic` упал вместе с
  `render-provider-commands --check` из-за drift `packages/task/docs/reference/provider-model-roles.md` относительно
  текущего канона. Источники генерации уже имеют чужие dirty changes, включая
  `packages/task/configs/command-routing.json` и provider locks; они не регенерировались в этом ходе.
  Проверки самого плана — `plan-lint`, strict citation verification, generated-view freshness и
  `git diff --check` — green; package qualification не помечается green до ремонта owning projection.
