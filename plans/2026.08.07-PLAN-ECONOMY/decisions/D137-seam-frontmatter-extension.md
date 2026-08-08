---
id: D137
date: 2026-08-08
status: accepted
item: P4.1
items: [P4.1, P4.2]
supersedes: [D52]
superseded_by: null
---

## Решение

**Шов объявляется additive frontmatter-полями `file`, `rule_or_contract_locus` и
`defect_class` на item-scoped записи `decisions/` либо `findings/`; эти поля не входят в
обязательный минимум `history-projection` v1 и не добавляются в `journal.jsonl`.** P4.1
замораживает их форму внутри `return-fingerprint` v1; редьюсер P4.2 читает исходный
decision/finding carrier через `plan_decisions`/frontmatter, а связь с событием строит по
`item` и временному окну. Запись без полного schema-valid шва не считается `classified`.
RAG:— (repo-grounded: `root/contracts/history-projection-v1.spec.json` разрешает минимум,
а не закрывает additive metadata; `packages/task/lib/task/review_policy.py` задаёт тот же
трёхпольный seam vocabulary; `findings/P4.1-history-seam-metadata-gap.md`).

## Почему

D52 ошибочно утверждала, что все три seam-поля уже входят в frozen minimum
`history-projection` v1. Машинная спецификация требует у decisions только `item`, `date`,
`status`, `supersedes`, `superseded_by`, а у findings — `item`, `date`; следовательно,
полевой join из одного минимума невыразим. Additive frontmatter сохраняет D24: связь идёт
со стороны decisions/findings, sealed journal не меняется; минимальный контракт P1.3 тоже
не меняется и продолжает принимать записи без классификационного шва.

## Consequences

D137 `supersedes D52` только в ложном утверждении «шов удовлетворим уже frozen minimum».
Сохраняются направление связи, трёхпольный vocabulary и запрет нового journal field.
Цена — P4 вводит опциональные metadata-поля поверх минимального history contract; старые
записи остаются schema-valid, но без полного шва попадают только в `provisional` либо
`ungroupable`.
