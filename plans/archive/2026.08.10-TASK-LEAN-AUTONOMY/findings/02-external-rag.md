# External RAG — strict frame, adaptive execution

Дата: 2026-08-10. Обязательный retrieval выполнен через обычный Perplexity Web.

## Состояние retrieval

- `perplexity-web search`: 4/4 запросов завершились с ответом и источниками.
- `search_advanced`: 3 попытки вернули `No answer found`; это деградация advanced-режима,
  а не недоступность MCP. После уточнения владельца запросы повторены через базовый search.
- Post-audit remediation: два узких `search_advanced(sources=web)` запроса завершились 2/2;
  найденные official URLs открыты и проверены напрямую 2026-08-10.
- Field-telemetry follow-up 2026-08-11: обычный `perplexity-web search` получил семь узких
  запросов; четыре вернули usable synthesis, три — `No answer found`. No-answer не трактовался
  как факт. Load-bearing resilience/alerting/session claims перепроверены по official Google SRE,
  Azure, Kubernetes и Claude Code pages.
- Нагрузочные выводы ниже сверены по первичным официальным материалам; WebSearch применялся
  только для открытия и перепроверки первоисточников, не вместо Perplexity RAG.

## Подходы, которые сходятся

1. **Progressive elaboration / rolling wave.** Жёстко фиксировать ближайший исполнимый
   контракт, дальнюю работу держать крупнее и уточнять только при приближении. Это поддерживает
   компактный initial skeleton без повторного проектирования каждого малого шага.
2. **Management by exception.** В публичном материале PRINCE2/PeopleCert явно задана узкая
   граница: команда действует внутри согласованных/явно определённых tolerances/acceptable
   parameters, а выход за пределы эскалируется через governance. Более сильная формула про любой
   forecast не приписывается источнику. Проверено 2026-08-10 по exact official pages ниже.
3. **Risk-based assurance.** Глубина независимой проверки определяется последствиями и
   неопределённостью изменения. Новый evidence может сделать повторную проверку нужной;
   неизменившийся low-risk diff — нет.
4. **Progressive disclosure for agents.** Always-on файл содержит короткий индекс и устойчивые
   правила; подробные процедуры загружаются по задаче. Перечень всех edge cases в prompt
   ухудшает полезную плотность контекста.
5. **Bounded repair, not bounded progress.** Ограничивать повторение одного и того же failure
   fingerprint; новый причинный фикс внутри scope может продолжаться. Эскалировать material
   boundary или подтверждённый no-progress.
6. **Decompose only when needed.** GitHub Spec Kit сохраняет `/specify → /plan → /tasks →
   /implement` для каждого bounded slice и рекомендует spec-of-specs только когда lighter
   complex-feature strategies недостаточны. Официальная формулировка — decomposition “adds the
   most overhead of any strategy”, не «самый дорогой вариант»; финансовая/token-cost
   интерпретация не делается. Проверено 2026-08-10.
7. **Actionable symptom, not every cause.** Google SRE отделяет human-interrupt alert от
   diagnostic cause: page должен быть urgent/actionable и отражать active/imminent impact.
   Для Task tool error остаётся diagnostic, пока не доказан current acceptance impact.
8. **Classify before retry.** Azure разделяет cancel/immediate/delayed retry, требует учитывать
   idempotency и рекомендует восстановленные ранние failures логировать informational; финальная
   неудача после bounded policy становится error.
9. **Readiness is not liveness.** Kubernetes оставляет временно not-ready процесс живым и
   резервирует restart для действительной inability to progress. Future carrier, живой PID и
   временная dependency поэтому не равны terminal failure.

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
- PRINCE2/PeopleCert, *How to report progress in an agile setting with dashboards* — deviations
  beyond agreed scope/schedule/quality tolerances are escalated through governance:
  https://www.prince2official.com/Prince2-News-and-Announcements/agile-progress-reporting-dashboards
- PRINCE2/PeopleCert, *Delivering AI projects: structure, control and governance are imperative
  for ROI* — explicitly defined acceptable parameters enable bounded experimentation and prompt
  escalation beyond acceptable limits:
  https://www.prince2official.com/Prince2-News-and-Announcements/delivering-ai-projects-structure-control-and-governance-are-imperative-for-roi
- Liu et al., *Lost in the Middle* — sensitivity of long-context use to placement:
  https://aclanthology.org/2024.tacl-1.9/
- GitHub, *Spec Kit*, *Complex Features* and *Spec of Specs* — structured per-slice workflow plus
  conditional decomposition only after lighter strategies are insufficient:
  https://github.com/github/spec-kit
  https://github.github.com/spec-kit/concepts/complex-features.html
  https://github.github.com/spec-kit/concepts/spec-of-specs.html
- Google SRE, *Monitoring Distributed Systems* — actionable symptom-based human interruption,
  cause signals for diagnosis and alert-fatigue boundary:
  https://sre.google/sre-book/monitoring-distributed-systems/
- Microsoft Azure Architecture Center, *Retry pattern* — transient classification, bounded
  retry, idempotency and informational early failures:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/retry
- Microsoft Azure Architecture Center, *Circuit Breaker pattern* — stop repeating a persistent
  failure while allowing the rest of the system to continue:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
- Kubernetes, *Liveness, Readiness, and Startup Probes* — temporary readiness vs terminal
  liveness distinction:
  https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Anthropic, *Claude Code environment variables* — observed `CLAUDE_CODE_SESSION_ID` in Bash/
  PowerShell subprocesses:
  https://code.claude.com/docs/en/env-vars

## Verification footer

External fact classes covered: agent instruction design, context limits, progressive planning,
management by exception, risk-based assurance, conditional decomposition, actionable alerting,
transient/idempotent retry, readiness/liveness and provider session identity. Confidence: high
for the exact official tolerance/escalation boundary and Spec Kit workflow/overhead wording;
medium for local tolerance calibration, which remains a field-canary responsibility. Nothing
unverified; no workaround. No load-bearing conclusion rests only on a tool-poor summary or on the
earlier failed advanced mode.
