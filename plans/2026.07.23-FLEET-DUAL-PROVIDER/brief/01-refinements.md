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
