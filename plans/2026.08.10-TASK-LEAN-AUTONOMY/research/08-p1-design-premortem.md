# P1 design pre-mortem — 6–12 month failure view

**Дата:** 2026-08-11
**Вопрос:** план провалился через 6–12 месяцев — почему?

## Кластеры причин и mitigations

| Причина провала | Класс | Mitigation | Owner |
|:--|:--|:--|:--|
| Donor `D2(a)/D2(b)` приняли за локальное D2 и молча изменили repair semantics | contract ambiguity | D15 явно разводит namespaces и pin'ит точную frozen v1.1.0 copy | plan designer |
| GO снова закрыл фазу до проверки кандидата и вернул close→audit→reopen loop | lifecycle conflict | D16 supersedes только D8 direct-close branch; D14 fresh GREEN остаётся gate | P1.2 executor + phase auditor |
| Неактивный plan-lint скрыл невалидный read graph до canary | stage-aware blind spot | direct `plan-weight item/plan` до P1.2; D2(a), D2(b), aggregate и gaps сохраняются в findings/09 | plan designer |
| Dirty `docs/reference.md` ошибочно посчитали committed authority | provenance/ownership | D9+D13 six-URL `git grep HEAD` до journal start; structural waiting при red | foreign-diff owner + P1.2 executor |
| Missing Claude hooks либо unattested route объявили product RED/GREEN | evidence confusion | findings/08 отделяет environment coverage limitation от required journal/acceptance predicates | Harness owner + P1.2 executor |
| После stable edit bundle/state остались stale, а handoff повёл executor на старые bytes | generated drift | owner generators, `--check`, targeted lint/citations и digest-qualified bundle before handoff | plan designer |

## Verdict

Все high-severity причины имеют владельца и уже выраженный carrier/gate; новых открытых design
решений pre-mortem не создал. Остаточный риск — owner pause на external ledger и optional Claude
telemetry coverage — честно остаётся в handoff, а не маскируется как готовый P1.2 start.

RAG:— (repo-grounded: `findings/08-p1-read-budget-and-preflight.md`,
`findings/09-p1-read-budget-measurement.md`, D9, D13–D16, `phases/P1/P1.2.md`).
