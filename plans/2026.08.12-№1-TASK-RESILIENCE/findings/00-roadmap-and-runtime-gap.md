# Roadmap ↔ runtime gap — 2026-08-12

## Прочитанные roadmap-входы

- `roadmap/2026.08.10-adaptive-plan-governance.md` — статические audit/design цепочки
  повторяют проверки без нового риска.
- `roadmap/2026.08.11-local-repair-vs-escalation-classifier.md` — bounded syntax/input repair
  ошибочно превращается в terminal escalation.
- `roadmap/2026.08.10-plan-run-routing-blocked-terminal-loop.md` — preflight route rejection
  записывается как product `Blocked` и делает повтор невозможным.
- `roadmap/2026.08.11-codex-effective-route-observability.md` — отсутствие thread-bound route
  evidence порождает ложные routing verdicts.
- `roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md` — self-invalidating evidence topology
  порождает послойные RED-аудиты вместо seam-fix.
- `roadmap/2026.08.10-audit-before-close-phase-gate.md` — phase close не должен предшествовать
  проверке candidate state.
- `roadmap/2026.08.11-terminal-final-continuity-receipt.md` и
  `roadmap/2026.08.11-terminal-handoff-recommendation-receipt.md` — ранний `final` и потеря
  точного Next разрывают уже авторизованное исполнение.
- `roadmap/2026.08.11-plan-views-history-cli-contract.md` — procedural CLI mismatch не должен
  становиться продуктовым блокером.

## Что уже есть

- `packages/skiller/skills/general/plan-protocol/SKILL.md` разрешает inline repair для
  обратимых сигналов и один isolated review после повтора/risk trigger.
- `packages/task/commands/plan-design.md` содержит `Conflict-impact assessment before a stop`.
- `packages/task/lib/task/plan_returns.py` и
  `packages/task/prompts/return-judgement-rubric-v1.md` дают provider-neutral isolated judgement,
  но применяют его к повторным return fingerprints, а не как обязательное подтверждение любого
  terminal block candidate.
- `plans/archive/2026.08.10-TASK-LEAN-AUTONOMY` ввёл evidence-first loop, repair-forward и
  phase candidate lifecycle.

## Воспроизводимые пробелы

1. `journal.RESULT_VALUES` не различает `routing-rejected`, `decision-pending`, `local-repair`
   и `block-candidate`; `blocked`/`escalated` остаются terminal input generated state.
2. `plan_item_state.RESULT_STATUS` проецирует любой `blocked` в `🔴 Blocked`; observation events
   не имеют отдельной nonterminal семантики.
3. Нет детерминированного reducer, который запрещает terminal block без независимого reviewer
   и требует RAG evidence для внешнего класса.
4. Terminal delivery остаётся prompt-only: нет машинного receipt, который отказывает для
   nonterminal subject и переносит exact persisted `handoff.Next` в финальный ответ.
5. `PLAN_ID_DATED_RE` принимает только `YYYY.MM.DD-CODE`; формат `YYYY.MM.DD-№N-CODE` и
   согласованность `Title = План №N — …` не реализованы.
6. Исторический `2026.07.25-ECO-OPT` D3 выбрал только полный PLAN-ID и явно отверг внутренний
   номер. Нынешняя директива владельца supersedes этот выбор.

## Preflight evidence

- `codex doctor --json` — overall `ok`, config model `gpt-5.6-sol`, approval `Never`, filesystem
  unrestricted; effective effort активного thread не экспонирован.
- Первый вызов `maind health --cwd <path>` был procedural misuse: CLI ожидает flag без значения.
  Worktree-local `packages/maind/bin/maind health --cwd --json` затем дал `status=connected` и
  зелёный trust для Claude/Codex.
- `packages/harness/bin/harness doctor` обнаружил stale глобальный `run-report`; восстановлено
  владельцем-генератором `packages/harness/bin/harness hooks --global`, с backup settings.

Все выводы выше repo-grounded; внешних продуктовых фактов для design verdict не требуется.
