# RAG — локальный ремонт вместо автоматического design-цикла

Verification date: 2026-08-08.

## Внешний факт: дополнительная orchestration оправдана только измеримой пользой

- Anthropic рекомендует начинать с наиболее простого решения и повышать сложность лишь когда это
  необходимо; workflows дают предсказуемость для хорошо определённых задач, а agentic complexity
  имеет цену в latency и cost. Source: <https://www.anthropic.com/engineering/building-effective-agents>.
- OpenAI различает manager pattern, в котором центральный агент сохраняет контроль и вызывает
  specialist как tool, и handoff, который передаёт выполнение. Source:
  <https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/>.
- Anthropic связывает безопасную быструю итерацию с проверяемым результатом: automated checks дают
  наблюдаемую обратную связь, но защита от регрессии требует явно заданных evals. Source:
  <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>.

Verdict: policy `repair-now` для детерминированного малого исправления с точной валидацией согласуется
с источниками; автоматический cold start/design на каждый сбой не следует из них. Источники не дают
универсального числового порога и не разрешают bypass protected boundaries. Confidence: high (три
первичных источника, проверены 2026-08-08). `RAG:✅`.

## Репозиторная квалификация P2.7

Единственное расхождение — имя generated `phase-closure`: D34, D77, P2.7, P3, P6 и
`research/04-p2-carriers-design.md` требуют `phases/<Pn>/<Pn>.closed.md`; только четыре
синхронные registry/spec copies используют `.closure.md`. По поиску репозитория нет кода,
материализующего или потребляющего `.closure.md`; это декларации до реализации P2.7.

Следовательно, repair ограничен четырьмя копиями реестра/спецификации и справкой. Он не меняет
reader role, путь исполнителя, SemVer, чужой репозиторий или уже выпущенный runtime. Решение D130
достаточно определённо: каноническое имя — `.closed.md`.

## Проверка (verification status)

- RAG: WebSearch ×3 OK; `context7` и `perplexity-web` в этой сессии недоступны, поэтому применён
  допустимый fallback WebSearch.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего; внешний вывод не опирается на непроверенный числовой предел.
- Обходки/[POSSIBLE-DEFECT]: нет.
