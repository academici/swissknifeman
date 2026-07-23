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

## P1.1 — минимальный disposable pilot после повторно пустого D7-set

Владелец распорядился не останавливать минимально рабочую раскатку после
повторного подтверждения пустого live D7 eligible-set и разрешил разрулить
конфликты только через безопасный disposable synthetic pilot/fixture. P1.1 не
повторяет registry scan: он выбирает ровно один изолированный local temp-root
dual-provider carrier, уже предоставляемый conformance-командой mAInd, и
фиксирует его проверяемый результат в артефакте плана. Это conformance MVP, не
live fleet pilot; весь live external rollout остаётся отдельным scope P2.

Это разрешение не распространяется на существующие consumer-репозитории и не
ослабляет D5–D7. `sibintek-insiders`, self-host, dirty/unmanaged bytes,
`--repair` и `--force` остаются запрещены. Красный disposable carrier означает
конкретный owning defect для P1.2, а не новый scan, подгонку или обход gate.
Внутренний temp-only repair safety case самой conformance-команды не считается
consumer repair и не разрешает CLI `--repair`.
