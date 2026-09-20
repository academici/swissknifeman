# P3 design evidence — 2026-09-20

## External method verification

Perplexity `search_advanced(web, academic)` и ordinary web search искали первичные
основания для memory/codegraph pilot. Публичные results не переносятся на
swissknifeman без локального matched evidence.

- RAG:✅ Di Wu et al., *LongMemEval*, ICLR 2025, access 2026-09-20:
  <https://arxiv.org/abs/2410.10813>. Разделяет indexing, retrieval и reading;
  проверяет information extraction, multi-session/temporal reasoning, knowledge updates
  и abstention. Для P3 это обосновывает раздельную оценку retrieval evidence
  и downstream task outcome, но не копирование большого benchmark.
- RAG:✅ Siru Ouyang et al., *RepoGraph*, ICLR 2025, access 2026-09-20:
  <https://arxiv.org/abs/2410.14684>. Показывает, что repository-level graph navigation может
  улучшать public SWE-bench/CrossCodeEval systems. Это обосновывает измерение cross-file
  navigation accuracy и efficiency, но не local rollout verdict.

Perplexity предложил 20–30 tasks; это отклонено как несоразмерное D2 и owner scope.
P3 использует две matched pairs на mechanism и может закончить `defer`;
это engineering pilot, а не statistical claim.

## Repository telemetry baseline

RAG:— 2026-09-20.

| Provider | Memory/maind capture | Codegraph capture | Design consequence |
|:--|:--|:--|:--|
| Claude Code | transcript parser считает calls, successful results и found counts для `maind_memory_*`/`maind_graph_*` | calls by operation | Самая глубокая automatic capture, но exact execution route её не выбрал. |
| Codex | при доступном transcript переиспользует Claude parser; без transcript остаётся calls-only sidecar | calls by operation | Coverage зависит от transcript presence; stub нельзя интерпретировать как нулевой result. |
| Cursor | pre-tool sidecar считает tool names; structured result/usefulness не пишет | calls by operation | Exact Cursor pilot должен связать run report с task-local evidence worksheet; несвязываемый result = `coverage-gap`. |

Observed 96-report zero baseline и `code_mcp=false` остаются activation/coverage gap.
Перед value pairs нужен один harmless known-result probe на exact selected provider;
новый telemetry subsystem для этого не нужен.

## Minimal pilot choice

- Memory: ordinary repository search versus selective recall одного committed-source fact;
  оценить retrieval correctness/provenance, stale/irrelevant result, abstention, task success и cost.
- Codegraph: ordinary `rg|find|read` versus session-local codegraph на cross-file task с 1–4 frozen
  required anchors; оценить anchor recall, wrong turns, reads/tool calls, time/tokens и task success.
- Одинаковые commit/prompt/model/effort/tools/sandbox/timeout; меняется только
  mechanism availability. Ровно две valid pairs на mechanism и максимум одна
  infrastructure-invalid replacement; mixed/under-covered evidence → `defer`, а не ещё один бенчмарк.

## Environment notes

- Perplexity MCP tool не был зарегистрирован в Codex turn, но локальный
  `perplexity-web-mcp/start.sh` успешно ответил через installed MCP SDK; ordinary web отдельно
  открыл обе arXiv primary pages.
- Первый ordinary-web open batch упал с `connection failed`; два узких retry завершились.
- `plan-delivery.py --kind handoff --subject P3` воспроизвёл описанный в P2
  Task 0.20.3 defect на следующей фазе: `PHASE_REENTRY_UNJUSTIFIED:
  PLAN_DESIGN_NOT_NEEDED`, хотя P4 имеет канонический skeleton marker, а все поля P4.1
  равны `—`. Correct semantic Next сохранён в `handoff.md`; runtime repair в P3 не вносился.
