---
id: D85
date: 2026-08-16
status: accepted
item: P6.3
items: [P6.3]
supersedes: []
superseded_by: null
---
## Решение

Владелец выбирает `admit_public_schema_carrier` для DecisionRequest
`DR-P6.3-PUBLIC-HEALTH-SCHEMA-1` с
`action_digest=c05f33aa04306f666cc310067ad2cf2602ae3f91501ca9dca44edb38d9797be8`.

P6.3 получает отдельный frozen plan-local carrier
`root/contracts/provider-health-evidence-set-v1.schema.json`. Carrier точно описывает
входной wrapper публичной команды `maind projects health --evidence-set`, имеет provenance
к owning P6.2 source и является единственным schema-input для runtime-exporter. Для его
проектирования разрешено одно bounded чтение owning interface
`packages/maind/lib/maind/provider_health.py`; после материализации carrier этот source не
входит в P6.3 execution bundle и не читается исполнителем.

## Почему

Публичная команда принимает evidence-set, но опубликованные CLI-документы не фиксировали
точную wrapper-схему. Перебор догадок не даёт доказуемого контракта и создаёт риск построить
ожидаемый результат из наблюдаемой ошибки. Отдельный frozen carrier устраняет этот разрыв,
сохраняет публичный CLI единственной runtime-границей и не расширяет P6.3 до изменений mAInd.

## Consequences

Изменение owning wrapper после pinned source digest считается contract drift и оставляет
флот non-green до явного обновления carrier. P6.3 не импортирует package internals, не читает
provider targets и не выполняет repair/apply/fix; schema carrier, item spec и bundle
регенерируются вместе до продолжения исходного routed run.
