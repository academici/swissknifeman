---
id: D19
date: 2026-08-11
status: accepted
item: P2.1
items: [P2.1]
supersedes: []
superseded_by: null
actor: repository-owner (delegated conflict resolution via D18)
model: gpt-5.6-terra/high (session route; effective effort self-attested)
evidence: RAG:— packages/task/tests/test_provider_command_parity.py + phases/P2/P2.1.md
---

## Решение

Добавить `packages/task/tests/test_provider_command_parity.py` в exact Files P2.1. Тест является
не факультативным follow-up, а владельцем двух acceptance-фактов context-enum change: canonical
command больше не содержит historical `/clear`, а generated Codex runtime сохраняет новый
provider-neutral enum. Одновременно тест получает уже принятый в соседних Task tests package/direct
import fallback, потому что P2.1 Validation вызывает его как `tests.test_provider_command_parity`.

## Consequences

P2.1 item diff остаётся полностью объявленным, а provider parity проверяется той exact командой,
которая записана в Validation. Bundle/spec регенерируются до продолжения product edits.

## Почему

Первый red-first запуск показал `canonical_clear_controls 0 != 4` и package-import failure.
Оставить файл вне Files означало бы сознательно повторить Major scope drift P1.1; ослабить либо
пропустить тест — нарушить P2 anti-shortcuts. Acceptance и public semantics P2 не меняются.
RAG:— (repo-grounded).
