# External RAG — strict frame, adaptive execution

Дата: 2026-08-10. Обязательный retrieval выполнен через обычный Perplexity Web.

## Состояние retrieval

- `perplexity-web search`: 4/4 запросов завершились с ответом и источниками.
- `search_advanced`: 3 попытки вернули `No answer found`; это деградация advanced-режима,
  а не недоступность MCP. После уточнения владельца запросы повторены через базовый search.
- Нагрузочные выводы ниже сверены по первичным официальным материалам; WebSearch применялся
  только для открытия и перепроверки первоисточников, не вместо Perplexity RAG.

## Подходы, которые сходятся

1. **Progressive elaboration / rolling wave.** Жёстко фиксировать ближайший исполнимый
   контракт, дальнюю работу держать крупнее и уточнять только при приближении. Это поддерживает
   компактный initial skeleton без повторного проектирования каждого малого шага.
2. **Management by exception.** Исполнитель действует внутри tolerances; escalation нужна при
   прогнозе выхода за них, а не при каждом отклонении.
3. **Risk-based assurance.** Глубина независимой проверки определяется последствиями и
   неопределённостью изменения. Новый evidence может сделать повторную проверку нужной;
   неизменившийся low-risk diff — нет.
4. **Progressive disclosure for agents.** Always-on файл содержит короткий индекс и устойчивые
   правила; подробные процедуры загружаются по задаче. Перечень всех edge cases в prompt
   ухудшает полезную плотность контекста.
5. **Bounded repair, not bounded progress.** Ограничивать повторение одного и того же failure
   fingerprint; новый причинный фикс внутри scope может продолжаться. Эскалировать material
   boundary или подтверждённый no-progress.
6. **Decompose only when needed.** GitHub Spec Kit полезен строгим Spec→Plan→Tasks→Implement,
   но его же материалы называют decomposition самым дорогим вариантом и рекомендуют сначала
   ограничить объём исполнения или применить более лёгкое разделение.

## Проектный синтез

Для Task подходит комбинированная модель:

`strict contract → adaptive work group → local verify/repair → risk-triggered review → accept`

Каркас строг к intent, acceptance, boundaries и authority. Внутри него агент сам выбирает
порядок и группировку, пока не меняет публичный смысл и остаётся в repair envelope. Статус
фазы не является самостоятельным основанием для новой сессии или аудита.

## Первичные источники

- Anthropic, *Claude Code Best Practices* — короткие инструкции и progressive disclosure:
  https://code.claude.com/docs/en/best-practices
- Anthropic, *Manage Claude's memory* — concise/project-specific rules и path-scoped details:
  https://code.claude.com/docs/en/memory
- Anthropic, *Effective context engineering for AI agents* — context as finite resource,
  just-in-time retrieval, simplest workable structure:
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- OpenAI, *Codex customization* — небольшой `AGENTS.md`, recurring rules only:
  https://developers.openai.com/codex/customization/overview
- OpenAI, *Codex prompting guide* — rollout autonomy; лишние обязательные preamble/status/plan
  требования могут приводить к преждевременной остановке:
  https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide
- PMI, *Practice Standard for Scheduling* — rolling-wave planning:
  https://www.pmi.org/-/media/pmi/documents/public/pdf/certifications/practice-standard-scheduling.pdf
- NIST, *AI Risk Management Framework 1.0* — assurance proportional to context and risk:
  https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- Liu et al., *Lost in the Middle* — sensitivity of long-context use to placement:
  https://aclanthology.org/2024.tacl-1.9/
- GitHub, *Spec Kit* and *Complex Features* — structured contract plus escalation to
  decomposition only for genuinely large work:
  https://github.com/github/spec-kit
  https://github.github.com/spec-kit/concepts/complex-features.html

## Verification footer

External fact classes covered: agent instruction design, context limits, progressive planning,
risk-based assurance and real-world workflow examples. Confidence: high for the combined
operating model; medium for exact local tolerances, which must be calibrated by field canary.
No load-bearing conclusion rests only on a tool-poor summary or on the failed advanced mode.
