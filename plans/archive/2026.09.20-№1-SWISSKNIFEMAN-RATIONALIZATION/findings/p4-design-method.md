# P4 design evidence — 2026-09-20

## External method verification

Perplexity `search_advanced(web, academic)` и ordinary web search проверили только
методическую предпосылку P4: небольшой portfolio можно решать hard gates и bounded
reversible experiments без отдельной scoring system. Публичные рекомендации не определяют
конкретные кандидаты или thresholds swissknifeman — они берутся только из P1–P3.

- RAG:✅ Google SRE Workbook, *Canarying Releases*, access 2026-09-20:
  <https://sre.google/workbook/canarying-releases/>. Canary определяется как partial,
  time-limited candidate-vs-control evaluation; exposure ограничивается размером и временем,
  а simultaneous canaries могут загрязнять signal. Для P4 это поддерживает один изменяемый
  factor, bounded duration и stop, но не production rollout.
- RAG:✅ NIST SP 800-37 Rev. 2, access 2026-09-20:
  <https://csrc.nist.gov/pubs/sp/800/37/r2/final>. Документ поддерживает structured,
  accountable и continuously monitored risk decisions. Он применим только как общий guardrail;
  `go|keep|defer|reject` и experiment cap — локальное решение P4, не требование NIST.

Perplexity предложил one-page record, hard gates вместо weighted score, один primary metric,
малое число guardrails и явный rollback. Это synthesis/recommendation, не primary evidence.
P4 принимает компактную форму, но не создаёт новый шаблон, schema или governance process.

## Repository method choice

RAG:— P1 уже владеет corpus, metrics, thresholds, invalid-run и reducer; P2 даёт
case-bound evidence IDs; P3 отдельно закрывает memory/codegraph. Поэтому P4 не повторяет
research и не переоценивает thresholds. Он выполняет только четыре операции:

1. полный intake и deduplication входных hypotheses;
2. hard eligibility gates;
3. максимум четыре различающих experiments по две valid pairs;
4. deterministic verdict и P5-ready contract только для `go`.

Max four experiments — programme budget, а не утверждение о полноте. Пустой GO-set допустим,
но typed empty producer output требует отдельного owner decision; design его не фабрикует.

## Environment notes

- Perplexity tool не был зарегистрирован в текущем Codex turn; штатный локальный
  `perplexity-web-mcp/start.sh` выполнен через installed MCP SDK без изменения config.
- Ordinary web search отдельно открыл Google SRE и NIST primary pages.
- `plan-delivery.py --kind handoff --subject P4` воспроизвёл Task 0.20.3 defect:
  P5 skeleton с полями `—` ошибочно классифицирован как detailed и возвращает
  `PHASE_REENTRY_UNJUSTIFIED: PLAN_DESIGN_NOT_NEEDED`. Correct semantic Next остаётся
  в `handoff.md`; runtime repair в P4 не вносился.
