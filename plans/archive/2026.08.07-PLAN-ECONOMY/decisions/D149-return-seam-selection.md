---
id: D149
date: 2026-08-09
status: accepted
item: P6.2
items: [P6.2]
supersedes: []
superseded_by: null
---

## Решение

По прямому указанию владельца P6.2 продолжается без design-прохода: `plan_returns` отбирает
finding как return-seam carrier только при наличии полного набора `file`,
`rule_or_contract_locus`, `defect_class` в frontmatter до строгого разбора. Downstream-gate record
без этого набора остаётся собственным immutable carrier и не попадает в return reducer.

## Почему

Репетиция P6.2 доказала, что downstream record с обязательной парой consumer spec × producer commit
иначе ломает `plan-views returns`. Изменение не добавляет поле, не меняет schema/journal и сохраняет
fail-closed разбор для всякого record, который объявляет полный return-seam набор. RAG:—
(repo-grounded: `findings/P6.2-downstream-return-seam-conflict-2026-08-09.md`; указание владельца
в текущей сессии).
