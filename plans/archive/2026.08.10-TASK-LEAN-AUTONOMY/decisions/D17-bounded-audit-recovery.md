---
id: D17
date: 2026-08-11
status: accepted
item: P1.1
items: [P1.1, P1.2]
supersedes: [D14, D16]
superseded_by: null
actor: repository-owner (explicit one-repair-limit directive)
model: gpt-5.6-sol/high (current Codex session)
evidence: RAG:— phases/P1/P1.md + packages/task/commands/plan-audit.md + packages/task/commands/plan-exec.md + packages/task/lib/task/task_contract.py
---

## Решение

Сохраняется pre-close boundary D14/D16: terminal items образуют phase candidate, fresh GREEN audit
разрешает единственный `task:plan-close <PLAN-ID> Pn`. Recovery-ветка заменяется bounded-контуром:

`candidate → audit 1 → GREEN/close | non-GREEN → один repair-forward → audit 2 → GREEN/close | owner incident`

- первый `RED`/`ATTENTION` разрешает ровно один repair-forward в явно названные owning items под
  неизменным стабильным ТЗ; terminal item может вернуться в `🟡 In progress` через его штатный
  `plan-exec`/`plan-run`, без `plan-design` и без реопена фазы;
- `plan-design` допустим только если finding требует изменить стабильные Intent/Scope/Files/Validation,
  public/frozen semantics либо authority;
- второй audit финальный. Повторный non-GREEN исчерпывает `audit_rounds_max`: третьего repair,
  audit или автоматического design-pass нет; дальнейший исход выбирает владелец — принять `🟠` с
  названным долгом либо остановить фазу;
- Task Contract блокирует дальнейшую item mutation при `observed_rounds >= audit_rounds_max`.

Для текущего P1 audit это означает прямой bounded repair P1.1/P1.2; команда `plan-design P1` из
первого audit launch-block недействительна и заменяется repair-forward route.

## Consequences

Риск после второго non-GREEN становится owner-visible раньше и не маскируется третьим циклом.
Цена — после исчерпания единственного repair attempt автомат не может «попробовать ещё раз» даже
при дешёвой правке; владелец принимает долг или явно авторизует новый контракт.

## Почему

План уже требовал D3 material-triggered review reuse и запрещал automatic audit loop, но реализация
оставила три несовместимых шва: `plan-audit` печатал `plan-design` как шаблон RED, `plan-exec`
отказывал любому terminal item, а compiler блокировал только при `observed_rounds > 2`. Вместе они
делали обещанный repair-forward недостижимым и допускали лишний третий цикл. RAG:— (repo-grounded:
`phases/P1/P1.md:54`, `packages/task/commands/plan-audit.md`,
`packages/task/commands/plan-exec.md`, `packages/task/lib/task/task_contract.py`).
