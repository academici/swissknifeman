<!-- plan-projection
projection: decision-archive
projection_version: v1
source_scope: decisions/
through: 2026-08-13/D31
inputs_sha256: 9b37242b553d7970fdc919e6f85fbc7707f009d537c5159580168337fca87093
generated_by: task plan-views decisions
-->

# Архив решений

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D27 | 2026-08-13 | superseded | P6.2 | Выбран owner-option `repair-and-patch-release`: P6.2 реопенится как один recovery item, делает phase-candidate fingerprint детерминированным по Git tracked set, повторяет полные release gates и создаёт новый локальный annotated patch tag `v0.13.1`. `v0.13.0` не удаляется, не перезаписывается и не двигается; P6.3/P6.4 evidence не переписывается. Push/GitHub release остаются неавторизованными. RAG:— (owner-grounded: `decisions/queue.jsonl`; repo-grounded: `findings/22-P6-audit-2026-08-13.md`, `research/09-P6.2-tracked-tree-patch-release-design.md`). |
| D30 | 2026-08-13 | superseded | P6.2 | AUDIT-CAP: третьего Audit P6 нет. Владелец разрешает единственный forward repair P6.2: повторить исходные Validation для P6.2 только в fresh native roots с provider-attested route; новых terminal attempts после закрытия фазы не допускается. Это разрешение применяет уже accepted D29: построить exact committed `v0.13.2` candidate с byte-fresh P6.2 carriers, выполнить всю release-gate matrix в clean detached worktree без overlay и создать только новый локальный annotated tag после всех нулевых exit-кодов. `v0.13.0` и `v0.13.1` immutable. |
