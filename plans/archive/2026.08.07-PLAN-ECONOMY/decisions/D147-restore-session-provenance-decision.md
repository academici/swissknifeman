---
id: D147
date: 2026-08-09
status: accepted
item: P6.2
items: [P6.2]
supersedes: [D91]
superseded_by: null
---

## Решение

**D147 заменяет D91 только как активный carrier решения о session provenance:** все пять
canonical `task:plan-*` commands обязаны передавать `--session-id` через provider-neutral
resolver; схема `journal.jsonl` не расфриживается. Codex получает thin adapter над наблюдаемым
`CODEX_THREAD_ID`, а иной provider остаётся отдельной certification row и не имитируется.
**Consequences:** historical body D91 остаётся неизменным; активные ссылки и bundle P6.2 переходят
на D147; scope и полномочия P6.2 не расширяются, но потерянное миграцией обоснование больше не
является execution input.

## Почему

Layout-v2 миграция оборвала `## Почему` D91 внутри inline-code `str | None`; полная исходная
строка детерминированно восстанавливается командой
`git show b3c6435a^:plans/2026.08.07-PLAN-ECONOMY/plan.md`, поэтому смысл решения не реконструируется
по памяти. Текущий `packages/task/lib/task/journal.py` уже несёт `session_id` в sealed schema,
принимает `--session-id` и пишет его через общий writer; в текущем Codex runtime наличие
`CODEX_THREAD_ID` проверено без раскрытия значения. Значит граница остаётся дисциплиной producer
commands и thin adapter, а не изменением носителя. RAG:— (repo-grounded:
`findings/P6.2-d91-and-bundle-dor-recon-2026-08-09.md`;
`packages/task/lib/task/journal.py`; D119; D122).

## Consequences

D147 заменяет только повреждённый carrier D91, созданный layout-v2 миграцией: семантика решения
и finite scope P6.2 не меняются. D91 остаётся в архиве решений с двусторонней связью замещения;
активные Inputs/Required Reads переходят на D147. Цена — новая идентичность решения и явная
provenance-цепочка вместо бесшумной правки immutable body.
