<!-- plan-projection
projection: decision-current
projection_version: v1
source_scope: decisions/
through: 2026-08-14/D4
inputs_sha256: 07113cc25c1f8e208807eb693ca6538c0c0e782a015a425921e9b861bd4c8f17
generated_by: task plan-views decisions
-->

# Текущие решения

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D1 | 2026-08-14 | accepted | P1.1, P1.2 | `packages/task/lib/task/phase_assurance.py` становится единственным stdlib-only owner схемы `phase-assurance/v1`. Блок содержит ровно пять ordered fields; direct close совместим только с isolated/no-seam/non-live declaration. |
| D2 | 2026-08-14 | accepted | P1.1 | `review_policy.phase_audit_subject()` остаётся SSOT `phase-audit-subject/v1`. Все consumers нормализуются через него; new phase-audit writer персистирует только `Pn`, а raw historical rows не переписываются. |
| D3 | 2026-08-14 | accepted | P1.1, P1.2 | Latest normalized phase audit проверяется до unaudited admission. Его matching GREEN разрешает close; stale/ATTENTION/RED/invalid отказывает. Без audit direct close разрешён только valid `isolated` + empty seams + `no` + `direct-close-eligible` при полном objective green evidence. `Review` и item count не являются blockers. Валидный canonical assurance payload входит в fingerprint только при наличии; missing/invalid legacy input не добавляет key/sentinel. |
| D4 | 2026-08-14 | accepted | P2.1 | Recovery закрывает только `2026.08.02-PROVIDER-CONTRACT-LOCALE P1` через штатный phase-close после exact preflight fingerprint `7ce1…` и reuse journal line 97. Второй audit, P1.1–P1.3 Validation и любое изменение P1 product carriers запрещены. |
