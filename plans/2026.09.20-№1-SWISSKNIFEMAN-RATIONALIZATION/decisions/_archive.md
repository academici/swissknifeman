<!-- plan-projection
projection: decision-archive
projection_version: v1
source_scope: decisions/
through: 2026-09-20/D8
inputs_sha256: 9fd7122d6f40a4e0dd908d8d1f183773be4723a5ed5460a37630485d73fa3ea4
generated_by: task plan-views decisions
-->

# Архив решений

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D1 | 2026-09-20 | superseded | P1.1, P2.1, P3.1, P4.1, P5.1 | План состоит из пяти крупных фаз, детализируемых по одной в три ограниченных захода. Для detail pass выбирается Grok 4.6, если evidence packet широкий/cross-project или требует внешней tool orchestration; Composer 2.5 — если packet bounded и работа Cursor-local. |
| D3 | 2026-09-20 | superseded | P1.1, P2.1, P3.1, P4.1, P5.1 | P1–P5 детализируются полностью до любого execution. Затем один сквозной design audit проверяет межфазные контракты и запечатывает execution routing: состав и порядок батчей, точную модель `Grok 4.6` или `Composer 2.5`, effort/review и профильные и provider-specific исправления. Audit findings применяются в owning contracts одним bounded fix pass; execution открывается только после GREEN focused re-check и регенерации projections/bundles. |
