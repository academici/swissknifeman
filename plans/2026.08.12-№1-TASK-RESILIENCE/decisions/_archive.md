<!-- plan-projection
projection: decision-archive
projection_version: v1
source_scope: decisions/
through: 2026-08-13/D29
inputs_sha256: 1d76f51b14371f9dfd83c6a73eb764d4a610e7783f98f0c007721796d376646a
generated_by: task plan-views decisions
-->

# Архив решений

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D27 | 2026-08-13 | superseded | P6.2 | Выбран owner-option `repair-and-patch-release`: P6.2 реопенится как один recovery item, делает phase-candidate fingerprint детерминированным по Git tracked set, повторяет полные release gates и создаёт новый локальный annotated patch tag `v0.13.1`. `v0.13.0` не удаляется, не перезаписывается и не двигается; P6.3/P6.4 evidence не переписывается. Push/GitHub release остаются неавторизованными. RAG:— (owner-grounded: `decisions/queue.jsonl`; repo-grounded: `findings/22-P6-audit-2026-08-13.md`, `research/09-P6.2-tracked-tree-patch-release-design.md`). |
