---
id: D25
date: 2026-08-13
status: accepted
item: P5.3
items: [P5.1, P5.2, P5.3]
supersedes: []
superseded_by: null
---
## Решение

Владелец применил option `expand-p5.3-files` из DecisionRequest
`P5.3-files-boundary-2026-08-13`: stable `Files` P5.3 включает четыре generated Codex
carrier `task-plan-exec`/`task-plan-run`, уже произведённые owning renderer в product commit
`4d03ff55`. Разрешение не меняет Intent, Scope, Validation или generated product bytes и не
распространяется на иные файлы. RAG:— (owner/repo-grounded: durable response в
`decisions/queue.jsonl`, `findings/16-P5.3-files-boundary.md`, commit `4d03ff55`).

## Почему

Эти четыре carrier входят в declared provider-parity deliverable и детерминированно следуют
из canonical sources; их исключение из stable `Files` скрывало фактическую release/rollback
границу, а revert ломал бы уже зелёный product. Расширение спецификации восстанавливает точную
топологию без product mutation.

## Consequences

P5.3 повторяет exact Validation, регенерирует state/status/decisions/bundle и пересобирает
phase candidate. AUDIT-CAP следует D24: второй audit не запускается; третьего Audit P5 также
нет, фаза закрывается штатным `task:plan-close` с owner decision D25 только после прямой
green Validation и byte-fresh generated carriers.
