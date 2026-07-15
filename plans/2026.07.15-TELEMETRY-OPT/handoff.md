# HANDOFF — 2026-07-15 — after P3.1

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high» — P3.2 manual (§3 Routing: применение вердикта = архитектурное решение + Owner-гейт downgrade; effort high). Downgrade correctness-critical пинов — ТОЛЬКО с Owner-одобрением (`AskUserQuestion`).

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high |
| Context | continue (/clear) — ручной item |
| Суть | Исполнить P3.2 — применить вердикт P3.1: (а) секция model-routing в docs/routing.md (рационал всех 7 пинов); (б) ТОЛЬКО Owner-одобренные downgrade (dev/make-workflow → sonnet/high) + синхронно description-строка + `skiller registry`; (в) спорное (research) → open-questions.md; D-запись в plan.md |

```
Исполни item P3.2 мастер-плана 2026.07.15-TELEMETRY-OPT под Opus/high (Owner-гейт downgrade — AskUserQuestion в этой сессии). Прочитай по порядку: plans/2026.07.15-TELEMETRY-OPT/findings/P3-routing-audit.md → phases/P3.md (item P3.2) → plan.md (D8 pre-mortem) → docs/routing.md. Затем выполни P3.2 строго по ТЗ: (а) секция «Model-routing пинов task-команд» в docs/routing.md — per-command рационал + вердикт аудита P3.1 (всегда безопасно); (б) downgrade применять ТОЛЬКО для dev/make-workflow (вердикт downgrade-candidate) И ПОСЛЕ явного Owner-одобрения через AskUserQuestion — правка frontmatter model/effort + СИНХРОННО строка «Пинит X/Y» в description того же файла + `skiller registry` (идемпотентно) + `bash packages/skiller/scripts/validate.sh` зелёный; (в) research (needs-Owner) → строка в open-questions.md статус «Decision pending (нужен владелец)»; keep-Opus команды (design/plan-design/plan-audit/review) — правок пинов НЕТ, только политик-док. Итоговая D-запись в plan.md. Закрой item по plan-protocol §8 (2 коммита: item-diff по Files → bookkeeping; handoff; plan-lint K=0).
```

**Done:** P3.1 закрыт (item-коммит `cbdb47b`). Систематический аудит 7 Opus-пинов task-команд
по Варианту A (D8): когнитивный класс (repo-grounded) + фактический `analyst token-report
--by model` (tree-anchor `5ae6488`) + RAG-верификация возможностей моделей 2026-07
(claude-api canonical reference + perplexity-web, оба согласованы). Вердикты:
- **keep-Opus (4):** design/plan-design (opus/high, plan-design Owner-blessed D1),
  plan-audit/review (opus/xhigh) — correctness-critical, downgrade-risk HIGH, quality-телеметрии нет.
- **downgrade-candidate → Owner-gated sonnet/high (2):** dev (планировочный слой,
  coding-agentic домен Sonnet-par/выше), make-workflow (процедурный контур + статич.гейт).
- **needs-Owner A/B (1):** research (низкий приоритет).
- **Fable 5** исключён из downgrade-оси (out $50 = 2× Opus; up-tier для frontier, вне цели P3).
Выход — `findings/P3-routing-audit.md` (вердикт-таблица + рекомендация P3.2 + footer «Проверка»).
**Remaining:** P3.2 (применение вердикта + политик-док) → затем P4 (permission-friction, СКЕЛЕТ —
детализация через `/task:plan-design`). P5 (discovery) детализирован, независим от P3/P4.
**Sources of truth:** plans/2026.07.15-TELEMETRY-OPT/findings/P3-routing-audit.md (вердикты +
рекомендация) · plan.md (D8, Routing §3) · phases/P3.md P3.1 Completion Notes ·
packages/task/commands/*.md (пины) · docs/routing.md.
**Open risks:** P3.2 downgrade correctness-critical пинов — только Owner-гейт (design/plan-audit/
review НЕ трогать без явного одобрения; D8 pre-mortem: тихий downgrade → деградация качества
экосистемы без quality-телеметрии). При правке пина — рассинхрон frontmatter↔description = дефект.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: `--by phase` в analyst (токен-атрибуция на workflow-уровень) — не реализовано
  (`token_report.py:38-41`); ROI пер-команды НЕ квантифицируется → приоритет downgrade-trial'ов
  качественный (по downgrade-risk), не по измеренной экономии.
- open_questions: OQ-1 → Resolved (D8). `research`-downgrade → откроется в P3.2 как Decision
  pending, если Owner не решит сразу. Новых на уровне P3.1 нет.
