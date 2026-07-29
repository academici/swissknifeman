# Finding 01 — оценка Perplexity-аудита

**Canonical source:** committed
`artifacts/source-evidence/perplexity-audit.md`, 2993 строки. Original
user-owned `tmp/swissknifeman-audit.md` is optional provenance only; the
initial user path `/tmp/swissknifeman-audit.md` was absent.

## Что в источнике подтверждено

- Репозиторий имеет много пересекающихся delivery/runtime surfaces:
  `.agents`, `.claude`, `.claude-plugin`, `.codex`, `packages`, `configs`.
- `packages/harness/configs/claude-code/hooks/run-report/_lib.py` совмещает
  parsing, normalization-by-heuristics, derived metrics и report assembly.
- Fail-open telemetry нуждается в completeness/quality flags.
- Agent/provider projections нуждаются в canonical semantic source,
  provenance и cross-surface drift checks.
- Для semantic regressions полезны invariant, replay, golden и scenario tests.

Эти выводы совпали с независимой repo/runtime проверкой и вошли в P1/P3/P4.

## Что не переносится как факт

Большая часть разделов о `core/provider_*`, CLI и target architecture написана
по именам файлов и использует формулировки «вероятно», «может», «почти
наверняка». Аудит не строит dependency graph, не читает большинство
публичных функций и не проверяет существующие tests/contracts. Поэтому:

- общий domain/application/infra rewrite не планируется;
- provider truth model не объявляется сломанной заранее;
- CLI backlog `status/validate/doctor/explain/trace/repair` не принимается
  оптом;
- 30/60/90-day и 12-PR схемы не используются как execution evidence.

P4.1 сначала проводит code-grounded проверку. Его легитимный результат —
не только ADR/refactor, но и no-op/rejection внешней гипотезы.

## Мета-находка

Сам аудит демонстрирует нежелательный паттерн текущего процесса: узкая
evidence base разрастается в 2993-строчный governance dossier, а confidence
гипотез не управляет приоритетом. План заменяет это правилом:
`наблюдение → falsifiable hypothesis → fixed test → decision`, с отдельной
маркировкой repo-grounded/RAG и bounded follow-up.
