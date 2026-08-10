---
id: D122
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Provider-specific implementation surface минимален и закрыт:** допускаются только thin transport adapters для реально различающегося raw usage/runtime и generated command/skill projections с locks. Python reducers/gates/migration/plan tools, schemas, canonical commands, skills и rubric assets — один shared SSOT; копии алгоритмов «под Codex/Claude» запрещены. Item без фактического provider seam не получает provider matrix/отдельный прогон. **Consequences:** shared tests исполняются один раз; текущий Codex дополнительно проверяет только свои edges, Claude позже повторяет shared suite и проверяет свои edges. Provider feedback меняет core только если доказан дефект общей границы; иначе patch остаётся в adapter/projection.

## Почему

Уточнение владельца: продукт — протокол `task`, в основном stdlib Python scripts + skills, которыми каждый provider руководствуется отдельно; ожидаемая выгода общая. RAG:— (owner intent + repo-grounded package architecture/provider parity).
