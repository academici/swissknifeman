# P5 design evidence — 2026-09-20

## External method verification

Perplexity `search_advanced(web, academic)` и ordinary web search проверили только
методическую границу P5: маленький обратимый change должен иметь заранее определённые
rollback/guardrail conditions, ограниченный exposure и сравнение с неизменным control.
Они не выбирают GO-slices, не задают numeric thresholds и не авторизуют production rollout.

- RAG:✅ Google SRE Workbook, *Canarying Releases*, access 2026-09-20:
  <https://sre.google/workbook/canarying-releases/>. Canary определён как partial,
  time-limited change versus control; source поддерживает small self-contained changes,
  pause/rollback on adverse divergence и несколько representative, attributable metrics.
  Для P5 это только аналогия: каждый local manifest slice сравнивает один frozen
  repository measurement с baseline и guardrails, без live traffic или deployment.

Perplexity synthesis также сослался на AWS rollback/canary documentation. Это discovery,
не несущий источник: в contract включён только independently opened Google SRE primary page.

## Repository method choice

RAG:— P1 владеет corpus, controls, practical thresholds и guardrails; P4 владеет
selection, exact Files, validation and rollback contracts. Поэтому P5 не создаёт metric,
candidate, runner, telemetry field или second portfolio. Она допускает product write лишь
после typed nonempty P4 producer readiness, GREEN D8 global audit и post-P4
route/review admission по D8, применяет один row, сразу
проверяет его и останавливается на первом non-GREEN result после rollback.

## Environment notes

- Perplexity не был зарегистрирован callable tool в этом Codex turn, хотя local MCP
  registration existed. Один `search_advanced(web, academic)` успешно выполнен через
  configured `perplexity-web-mcp/start.sh`; ordinary web отдельно открыл Google SRE.
- This evidence is design-only. No P1–P4 artifact, manifest, product/config/provider file
  or consumer was written.
