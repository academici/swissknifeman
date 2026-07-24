# Finding 05 — внешние практики, проверено 2026-07-24

Perplexity Web использован как discovery/synthesis. Несущие выводы
перепроверены primary sources.

## OpenAI Codex

Fresh manual cache: `/tmp/openai-docs-cache/codex-manual.md`.

- Prompt contract: Goal, Context, Constraints, Done when.
- План полезен для сложных задач, но не нужен для каждой tiny task.
- AGENTS guidance должна быть короткой/практичной; повторяющиеся ошибки
  закрепляются durable rule, task-specific details выносятся.
- Subagents полезны для независимой read-heavy работы, но расходуют больше
  tokens; main agent удерживает requirements/decisions.
- Skills используют progressive disclosure; большой/дублированный catalog
  может быть shortened/omitted, а implicit triggering зависит от description.
- Все matching hooks из разных sources исполняются; precedence layer не
  заменяет lower hooks.

Sources:

- https://learn.chatgpt.com/guides/best-practices.md
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/agent-configuration/subagents.md
- https://learn.chatgpt.com/docs/build-skills.md
- https://learn.chatgpt.com/docs/plugins.md
- https://learn.chatgpt.com/docs/hooks.md

## Anthropic agent evals

“Demystifying evals for AI agents”, 2026-01-09:

- eval = task + trials + graders + transcript/outcome + harness;
- trace включает outputs/tool calls/intermediate results;
- отсутствие evals создаёт reactive loop: исправление одного failure рождает
  другой;
- capability eval и regression eval имеют разные thresholds;
- 20–50 простых реальных failure cases — разумный старт;
- нужно читать transcripts и проверять сам grader;
- static task bank позволяет сравнивать quality/latency/tokens/cost.

Source:
https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

## OpenTelemetry GenAI vocabulary

Conversation/agent/tool identifiers, token usage, latency и evaluation
attributes дают полезный общий shape. Статус части conventions development,
поэтому план использует терминологию и совместимый schema shape, но не
добавляет dependency и не обещает standard compliance.

Source:
https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/

## Google SRE postmortem

Материализовавшийся риск оформляется как incident с impact, causes,
action items, prevention и follow-up ownership. Это поддерживает решение:
третье повторение одного finding — root-cause incident, а не очередной
audit/fix cycle.

Source:
https://sre.google/sre-book/postmortem-culture/

## Perplexity synthesis, принятые как hypotheses

- requirements artifact с authority/Done;
- stateful audit gates с retry budget;
- compact authoritative startup payload;
- unique source resolution;
- metrics: pass@1, owner intervention, audit reopen, requirement retention,
  context amplification, telemetry completeness, loop depth.

Числовые canary/rollback thresholds Perplexity не приняты автоматически:
P0.3 замораживает их на repo failure corpus.
