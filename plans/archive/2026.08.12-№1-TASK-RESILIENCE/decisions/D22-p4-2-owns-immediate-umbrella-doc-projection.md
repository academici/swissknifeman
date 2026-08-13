---
id: D22
date: 2026-08-13
status: accepted
item: P4.2
items: [P4.2, P5.3]
supersedes: []
superseded_by: null
---
## Решение

P4.2 дополнительно синхронизирует immediate umbrella projection
`docs/task/reference/provider-commands.md` из уже обновлённого package reference только
owning `scripts/docs-sync.sh`. P5.3 сохраняет final aggregate docs sweep для всего
P0–P5.2 surface; его validation должна увидеть эту проекцию no-op. RAG:—
(repo-grounded: root.docs-build, docs-maintenance closeout и observed `docs-sync.sh --check` drift).

## Почему

Package documentation уже изменилась в P4.2, а root aggregate остался stale. Откладывать
механическую проекцию до P5.3 противоречит repository docs-build invariant и повторяет
уже устранённый immediate-projection deadlock. Изменение обратимо, детерминировано и
не меняет provider semantics.

Append-only `CHANGELOG.md` обновляется отдельно по root release discipline и не входит в
product coupling surface `Files`: иначе future tag item ложно становится downstream consumer
раннего canonical-command producer.
