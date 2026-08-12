# RAG: resilient execution and executable-schema cutover — 2026-08-12

## Внешние классы фактов

1. Как current durable workflow systems отделяют retryable сбой от terminal.
2. Как current durable workflow systems переносят breaking execution-schema/code changes при живых instances.
3. Как перед удалением legacy version доказывают, что активных consumers не осталось.

## Верифицированные выводы

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

- RAG: `perplexity-web` x3 — 1 partial recovery synthesis, 2 `No answer found`; WebSearch fallback x4 official-domain queries — OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего; все три несущих класса покрыты official sources.
- Обходки/[POSSIBLE-DEFECT]: Perplexity migration synthesis unavailable; official-source fallback дал прямую проверку, не workaround в product design.

