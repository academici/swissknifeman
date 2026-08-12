# RAG: resilient execution and executable-schema cutover — 2026-08-12

## Внешние классы фактов

1. Как current durable workflow systems отделяют retryable сбой от terminal.
2. Как current durable workflow systems переносят breaking execution-schema/code changes при живых instances.
3. Как перед удалением legacy version доказывают, что активных consumers не осталось.

## Верифицированные выводы

- Perplexity Deep Research синтезировал continue-first invariant по current official sources:
  worker/process failure сначала восстанавливает checkpoint; retry применяется к target activity,
  а исчерпание retry budget требует новой классификации в external block или terminal defect.
  Terminal external block хранит проверяемое unblock condition; local repair остаётся bounded,
  journaled operation. Источники Perplexity:
  https://docs.temporal.io/encyclopedia/retry-policies и
  https://docs.temporal.io/design-patterns/non-retryable-errors
  (повторный MCP-проход после bridge fix 2026-08-12, confidence: high).
- Для schema retirement Perplexity подтвердил: каждый run пинится к execution contract/version;
  breaking semantics не меняются in-place; old executors остаются до zero-consumer proof,
  включая running/retry/blocked/timer/callback paths. Forced retirement является cancellation,
  а не migration. Источники Perplexity:
  https://docs.temporal.io/develop/safe-deployments и
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-versioning
  (повторный MCP deep/basic cross-check 2026-08-12, confidence: high).

- Google Cloud IAM рекомендует для retry-safe transient failures ограниченный
  exponential backoff с jitter и deadline; для concurrency `409 ABORTED` повторяется
  весь read-modify-write cycle, а не только последняя запись. Это поддерживает
  bounded retry и повтор правильного scope, а не terminal stop на первом signal.
  Источник: https://docs.cloud.google.com/iam/docs/retry-strategy?hl=en
  (проверен 2026-08-12, confidence: high, official current docs).
- AWS Step Functions явно разделяет error classes: retry/catch настраиваются для
  обрабатываемых failures, а `States.Runtime` объявлен non-retriable. Это подтверждает
  классификацию перед action и запрещает wildcard «retry/stop всё одинаково».
  Источник: https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html
  (проверен 2026-08-12, confidence: high, official current docs).
- Microsoft Durable Functions предупреждает, что breaking orchestration changes без
  migration/version strategy могут сломать или навсегда оставить живые instances в `Running`;
  до удаления legacy code path нужно проверить, что legacy instances больше не запущены.
  Источники:
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-versioning и
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-orchestration-versioning
  (проверено 2026-08-12, confidence: high, official docs, cross-check x2).
- Kubernetes deprecation guide требует перевести и manifests, и API clients на новую served
  version до удаления deprecated API. Это поддерживает отдельный inventory как plan
  data, как reader/consumer code. Источник:
  https://kubernetes.io/docs/reference/using-api/deprecation-guide/
  (проверен 2026-08-12, confidence: medium, один official source).

## Граница применения

Эти источники не определяют схему Task и не разрешают миграцию этого репозитория. Они
подтверждают общие инварианты: class-specific bounded recovery, миграция active instances до
legacy removal и проверка отсутствия live legacy consumers. Exact Task выводы остаются repo-grounded.

## Проверка (verification status)

- До ремонта: `perplexity-web` x7 — 1 ответ и 6 `No answer found`; daemon evidence показывал
  полный `.prose` при десяти пустых `[role=tabpanel]`.
- Ремонт: `/home/vostrikov/projects/packages/perplexity-web-mcp` commit `d77ce0e` выбирает
  непустой legacy tabpanel либо current `main .prose`; 51 passed, 1 skipped, lint/build GREEN.
- После ремонта: тот же Microsoft question через `search` → 660 chars/1 official source;
  schema migration через `advanced` → 1192 chars; recovery/schema query через `deep` →
  8462 chars/4 sources. Mandatory Perplexity gate — GREEN.
- P0.3 terminal rerun: `search` → 2238 chars/2 official URLs; `advanced` → 1285 chars,
  непустой CSV без source metadata после bounded retries; `deep` → 7104 chars/5 official URLs.
  Для advanced provenance записан отдельный Perplexity deep cross-check, а не вымышленные inline
  citations. Exact queries, SHA-256, modes, lengths, URLs/domains и bridge commit находятся в
  `artifacts/P0/rag-gate-evidence-v1.json`; полные generated answers не сохранены.
- WebSearch x4 остаётся independent official cross-check, но не считается заменой обязательного
  Perplexity результата.
- Downstream pre-close на item-коммите `1db68de9` выявил ложный RED: будущий
  validator P1.1 ещё не создан, а ASCII-only parser потерял path с `№`. Task fix
  `5294642e` классифицирует такой dependency-not-ready consumer как `unknown`; реальный
  non-zero от applicable command остаётся `red`.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего.
- Обходки/[POSSIBLE-DEFECT]: нет.
