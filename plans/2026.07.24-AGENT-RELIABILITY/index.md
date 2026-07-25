# Индекс — 2026.07.24-AGENT-RELIABILITY

**Обновлён:** 2026-07-25 (plan.md v1.10.0; bounded A3 repair под Owner authority E, D50–D55; `G-EXEC` выдан для self-host, за владельцем только G1)

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | master plan, routing, decisions, contracts и metrics |
| `phases/` | 5 исполнимых фаз, 22 items (P1 несёт 5: порядок P1.1→P1.2→P1.3→P1.5→P1.4) |
| `handoff.md` | rolling exact-next carrier |
| `journal.jsonl` | append-only plan operations |
| `brief/` | исходный запрос и границы (00 бриф · 01 refinements, включая Owner options B, authority D и **authority E** · 02 historical authority C) |
| `findings/` | первичная evidence и вердикты аудитов без проектных выводов |
| `research/` | root-cause, target operating model и experiment design |
| `roadmap.md` | canonical execution table + 22 native Codex recovery carriers |
| `artifacts/source-evidence/` | immutable committed bundle (по D30 не меняется) |

## Evidence routing

| Источник | Питает |
|:--|:--|
| `findings/00-source-evidence-manifest.md` | committed self-contained evidence bundle and provenance boundary |
| `artifacts/source-evidence/` | full audit, seven journals, sanitized incidents, runtime snapshots, corpus/baseline и verifier |
| `findings/01-perplexity-audit-assessment.md` | D4, P4 hypothesis verdict |
| `findings/02-telemetry-2026-07-20-24.md` | D1, D7–D11, P0/P3 baseline |
| `findings/03-ssot-runtime-inventory.md` | D6, P1 |
| `findings/04-runtime-preflight.md` | D16/D25, P0.4 |
| `findings/05-external-practices.md` | D3–D4, D8–D10 |
| `findings/06-independent-review.md` | design pass 3 corrections |
| `findings/07-design-audit-red-attempt-1.md` | Pass 2 remediation contract и Pass 3 input |
| `findings/08-design-audit-red-attempt-2.md` | RED 2/2 → Pass 4 (D30/D31) |
| `findings/09-design-audit-exceptional-attempt-3.md` | RED attempt 3 → Pass 5 (D36–D38) |
| `findings/10-design-audit-a1-attempt-4.md` | RED A1 (authority C, дерево `fe3e1646`) → bounded repair под authority D (D39–D48) |
| `findings/11-design-audit-owner-b-a2.md` | RED A2 (option B, committed `916acdb5`) → D49; 2 Blocker + 1 Major вне скоупа authority D — открытый долг |
| `findings/12-effective-collision-remeasure.md` | D40–D44, P1.1 before-state и P1.5 scope |
| `findings/13-design-audit-a3.md` | RED A3 (6-й заход) → bounded repair под authority E (D50–D55) |
| `research/01-root-cause-analysis.md` | P0/P2 |
| `research/02-target-operating-model.md` | P0.3, P1, P2 |
| `research/03-metrics-and-experiment.md` | P0.3, P3 |
| `research/04-p1.4-fixture-composition.md` | D51/D53, состав фикстуры P1.4 и негативный D42-прогон |
