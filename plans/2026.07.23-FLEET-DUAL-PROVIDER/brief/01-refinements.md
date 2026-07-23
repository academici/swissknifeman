# Уточнения владельца — 2026-07-23

## P0.1 — project-scoped Codex connect carrier

Внешний connect consumer должен получать детерминированный repo marketplace
Codex и self-contained bundles только выбранных плагинов. Их semantic plugin
set совпадает с выбором Claude connect. Self-host сохраняет thin-проекцию.
Ordinary connect не вызывает и не имитирует глобальную установку, cache или
enable: это отдельное user-level действие.

До первой записи должны быть проверены capability, containment, completeness и
ownership всех выбранных provider targets. Missing, escaping, incomplete,
corrupt или unowned Codex target завершает всю операцию fail-closed до записи
Claude settings. Реальные consumer-проекты в P0.1 не изменяются; проверки
проводятся только во временных каталогах.

## P1.1 — replacement pilot и instruction target scope

Владелец исключил активно разрабатываемый `sibintek-insiders` и распорядился
продолжить со следующим совместимым pilot. Следующий pilot нельзя угадывать:
до единственной consumer-записи он проходит детерминированный no-write preflight.
Ordinary consumer получает только root instruction scope; package scope
применим лишь при наличии соответствующего package root. Fail-closed ownership
сохраняется; `--repair`, `--force` и overwrite unmanaged targets запрещены.

## P1.1 — продолжение rollout после D7 no-candidate evidence

Владелец подтвердил, что rollout продолжается и не переводится в defer. Это не
даёт права назвать candidate заранее или ослабить D5–D7. Следующее исполнение
P1.1 начинает с нового read-only скана живого registry в его порядке, исключая
`sibintek-insiders` и self-host. Только первый external candidate, который в
этом новом прогоне проходит полный D7 eligibility/provider/worktree/instruction
preflight, может получить ровно один normal apply. Если таких кандидатов снова
нет, фиксируется no-write blocked evidence; `--repair`, `--force` и overwrite
dirty/unmanaged user bytes по-прежнему запрещены.
