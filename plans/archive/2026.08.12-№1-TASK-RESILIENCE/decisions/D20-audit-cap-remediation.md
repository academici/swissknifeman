---
id: D20
date: 2026-08-13
status: accepted
item: P3.3
items: [P3.1, P3.2, P3.3]
supersedes: []
superseded_by: null
---
## Решение

AUDIT-CAP: третьего Audit P3 нет; фаза закрывается штатным `task:plan-close`

Владелец разрешает единственный repair-forward P3.3: повторить исходные Validation для
P3.1, P3.2, P3.3 только в fresh native roots с provider-attested route; новых terminal
attempts после закрытия фазы не допускается.

## Почему

Второй Audit P3 обнаружил воспроизводимый defect в Layout v2 predicate. Исправление
ограничено P3.3 и подтверждается focused tests, package validation, scoped views и
generator checks; новый аудит запрещён исчерпанным cap.

## Consequences

P3.3 закрывается по фактическому результату validation, после чего phase-close gate
вызывается с `owner_decision="D20"`. P3 не получает третьего Audit; P4–P6 и stable
спецификации P3.1–P3.3 не изменяются.
