<!-- plan-projection
projection: decision-index
projection_version: v1
source_scope: decisions/
through: 2026-09-22/D1
inputs_sha256: 1eec3b750c14c0c3227194b97fc1945e5d6445e17b23075b9756a6d5ff2370d8
generated_by: task plan-views decisions
-->

# Индекс решений

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D1 | 2026-09-22 | accepted | P1.1 | `v0.24.0` остаётся неизменным историческим tag. Исправление version truth, attestation, provider publication и fleet delivery входит в новый patch/minor release candidate, выбранный штатным SemVer tooling. Все downstream writes проходят ownership/preimage/readback gates; внешний publish остаётся owner gate. |
