---
id: D19
date: 2026-08-12
status: accepted
item: P3.3
items: [P3.3]
supersedes: []
superseded_by: null
---
## Решение

Владелец потребовал довести P3.2–P3.3 до terminal без парковки. Поэтому P3.3 получает
узкое разрешение регенерировать generated provider/runtime parity, которую детерминированно
изменяют её canonical plan-lint, authoring и audit sources, включая агрегированный docs projection.
Запись не разрешает менять workflow runtime или provider semantics вручную: только owning renderer,
`docs-sync` и их `--check`.
RAG:— (owner-grounded: direct mandate 2026-08-12; repo-grounded: P3.3 validation).

## Почему

P3.3 обязана держать canonical authoring/audit meaning в source, а полный package validation
проверяет его generated projections. Разделение source и stale projection сделало бы declared
acceptance невыполнимым и повторило бы уже устранённый P3.2 defect.
