# Целевой дизайн: continue-first Task

## 1. Единая лестница сигнала

```text
signal
  → minimal reproduce
  → deterministic classify
  → local/transient/procedural: repair/retry/continue
  → external: mandatory RAG evidence
  → material block candidate: isolated reviewer
  → JUSTIFIED + deterministic boundary: terminal Blocked
  → AVOIDABLE: owning-root repair
  → insufficient/malformed/out-of-scope: gather/fix evidence, nonterminal
```

Raw tool exit, route mismatch, pending decision и первая гипотеза о blast radius не являются
terminal product outcomes. RAG:— (repo-grounded:
`roadmap/2026.08.11-local-repair-vs-escalation-classifier.md:35`).

## 2. State/event separation

Append-only journal сохраняет provenance, но reducer отделяет observation results от state
transitions. `routing-rejected`, `decision-pending`, `local-repair` и `block-candidate` не
увеличивают attempt и не меняют item в `🔴`; `in-progress`/terminal outcomes остаются владельцами
позиции. RAG:— (repo-grounded:
`roadmap/2026.08.10-plan-run-routing-blocked-terminal-loop.md:31`).

## 3. Block confirmation

Новый stdlib reducer принимает schema-valid capsule. Terminal разрешён только когда:

- material class входит в закрытый allowlist;
- external class имеет непустое verified RAG evidence;
- reviewer actor/context отличны от executor/root;
- reviewer verdict `JUSTIFIED`;
- reducer, а не reviewer, выбирает действие.

Reviewer не авторизует side effects и не закрывает item; он подтверждает или опровергает
block hypothesis. RAG:— (repo-grounded:
`packages/task/prompts/return-judgement-rubric-v1.md:1`).

## 4. Continuity receipt

Перед terminal final команда строит byte-bound receipt по фактическому status/journal и
`handoff.md`. Nonterminal subject получает `FINAL_BEFORE_TERMINAL_FORBIDDEN`; terminal receipt
несёт exact Next и digest. Provider transcript enforcement/heartbeat, если transport не даёт
hook на final, остаётся явно названным остатком, а не ложным green. RAG:— (repo-grounded:
`roadmap/2026.08.11-terminal-final-continuity-receipt.md:22`).

## 5. Идентичность

Новый канон: `YYYY.MM.DD-№N-CODE`, `N` — уникальный положительный ordinal внутри даты; Meta
Title начинается `План №N —`. Ссылки из комментария/docstring: полный
`YYYY.MM.DD-№N-CODE Pn.m`, никогда bare `Pn.m`. Старые dated/legacy IDs читаются для back-compat.
RAG:— (owner-grounded: `brief/00-brief.md:12`).
