# Verified provider capabilities — 2026-07-19

**Тип источника:** current first-party documentation review  
**Маркер:** RAG:✅ 2026-07-19 — официальные руководства OpenAI и Anthropic

## Codex / ChatGPT

Официальный Codex manual подтверждает repo-level `AGENTS.md`, `.agents/skills`,
project `.codex/config.toml`, MCP, custom agents/subagents, lifecycle hooks рядом с
активными config layers и Codex plugins/marketplace. Project config и hooks зависят от
trust. Custom prompts помечены как deprecated, поэтому устойчивый аналог task-команды
для Codex следует делать skill adapter'ом, а не новым prompt-файлом.

Источники:

- <https://learn.chatgpt.com/docs/agent-configuration/agents-md>
- <https://learn.chatgpt.com/docs/config-file/config-basic>
- <https://learn.chatgpt.com/docs/hooks>
- <https://learn.chatgpt.com/docs/skills>
- <https://learn.chatgpt.com/docs/plugins>
- локальный snapshot полного Codex manual: `/tmp/openai-docs-cache/codex-manual.md`

Текущая security-модель различает approval policy и sandbox. Для автономной работы
`approval_policy=never` не расширяет sandbox: вместе с ограниченным sandbox он fail-closed;
полный автономный доступ является отдельным явным выбором режима.

## Claude Code

Официальная документация Anthropic подтверждает `CLAUDE.md`, project/user settings,
plugin marketplaces, skills/commands/agents, hooks, MCP и permission modes. Это означает,
что Claude surface остаётся полноценным adapter'ом, а не legacy-файлами, которые можно
удалить после Codex migration.

Источники:

- <https://code.claude.com/docs/en/plugin-marketplaces>
- <https://code.claude.com/docs/en/hooks>
- <https://code.claude.com/docs/en/mcp>
- <https://code.claude.com/docs/en/configuration>
- <https://code.claude.com/docs/en/permissions>

## Архитектурный вывод

Оба провайдера имеют общие классы возможностей, но разные файловые контракты,
trust/permission vocabulary и packaging semantics. RAG:✅ подтверждает необходимость
capability adapters; точное равенство форматов или семантики не предполагается.

## Повторная проверка перед детализацией P0

**Проверено:** 2026-07-19  
**Уверенность:** high для Codex (fresh first-party manual), medium для Claude Code
(один first-party corpus через `perplexity-web`; ссылки ограничены официальной документацией).

Fresh Codex manual (`/tmp/openai-docs-cache/codex-manual.md`, helper status
`local manual was already current`) уточнил несущие различия:

- project `.codex/config.toml`, project hooks и rules загружаются только для trusted project;
- `approval_policy` отвечает за запрос подтверждения, а `sandbox_mode` — за границу доступа;
  `approval_policy="never"` сам по себе sandbox не расширяет;
- custom prompts deprecated; reusable command semantics следует переносить в skills;
- repo skills живут в `.agents/skills`, plugins являются installable distribution unit и могут
  поставлять skills, MCP и hooks; repo marketplace живёт в `.agents/plugins/marketplace.json`;
- `AGENTS.md` строит цепочку инструкций root→cwd, а более близкая инструкция имеет приоритет.

First-party anchors из manual:

- <https://learn.chatgpt.com/docs/agent-configuration/agents-md>
- <https://learn.chatgpt.com/docs/config-file/config-basic>
- <https://learn.chatgpt.com/docs/agent-approvals-security>
- <https://learn.chatgpt.com/docs/build-skills>
- <https://learn.chatgpt.com/docs/plugins>
- <https://learn.chatgpt.com/docs/build-plugins>
- <https://learn.chatgpt.com/docs/hooks>

`perplexity-web` отдельным focused query по official Anthropic docs подтвердил для Claude Code:

- слои managed/CLI/local/project/user имеют собственный precedence, а permission rules merge;
- skills и legacy commands сосуществуют, но skills являются текущей reusable surface;
- plugins могут поставлять agents, hooks, MCP и skills;
- hooks имеют provider-specific event/handler contract;
- MCP имеет local/project/user/plugin scopes и собственный precedence;
- workspace trust влияет на activation project settings/permissions.

First-party anchors:

- <https://docs.anthropic.com/en/docs/claude-code/settings>
- <https://docs.anthropic.com/en/docs/claude-code/memory>
- <https://docs.anthropic.com/en/docs/claude-code/skills>
- <https://docs.anthropic.com/en/docs/claude-code/hooks>
- <https://docs.anthropic.com/en/docs/claude-code/mcp>

**Вердикт для P0:** capability contract должен разделять capability identity, support level,
provider-native configuration и trust/permission semantics. Одна общая таблица полей или
«одинаковый config для обоих» противоречит first-party contracts; общий слой фиксирует смысл,
а adapter — нативную реализацию.
