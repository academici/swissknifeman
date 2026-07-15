# HANDOFF — 2026-07-15 — after P3.2

**Next:** P4 (permission-friction) — **СКЕЛЕТ**, требует детализации через `/task:plan-design`
до исполнения. Альтернатива — P5 (discovery, детализирован, независим от P3/P4).

| Параметр | Значение |
|:--|:--|
| Model | opus (детализация P4 = дизайн, §3 Routing) |
| Thinking | high |
| Context | continue (/clear) |
| Суть | Фаза P3 закрыта (2/2 🟢). Дальше — детализация P4 (permission-friction) ИЛИ исполнение P5 (discovery) |

```
Детализируй фазу P4 (permission-friction) мастер-плана 2026.07.15-TELEMETRY-OPT под Opus/high: /task:plan-design 2026.07.15-TELEMETRY-OPT P4. Прочитай plan.md (§1 Context кластер 4 — 118 DENY(policy), Phase Index) + phases/P4.md (скелет) + findings/telemetry-baseline.md. Разложи P4 на item'ы (DoR), проставь Routing §3, пройди DoR-гейт.
```

**Done:** P3.2 закрыт, **фаза P3 терминальна (2/2 🟢)**. Вердикт P3.1 применён:
- **Downgrade Opus→Sonnet 5/high (2):** `dev`, `make-workflow` — Owner-делегировал выбор
  исполнителю (`AskUserQuestion` → «выбор оптимальных моделей — твоя работа»), оба применены по
  вердикту P3.1 (downgrade-candidate, safety-nets review-gate / статич.выходной ревьюер; Sonnet 5
  par/выше на coding-agentic 80.4/74.6). Frontmatter `model` + строка «Пинит Sonnet/high» в
  `description` + body-когерентность + `skiller registry` (идемпотентен) + `validate.sh` зелёный.
- **Keep-Opus подтверждены (4):** `design`/`plan-design` (opus/high), `plan-audit`/`review`
  (opus/xhigh) — правок пинов НЕТ, только политик-док.
- **research (needs-Owner) → OQ-4** «Decision pending (нужен владелец)», низкий приоритет.
- **Политик-док:** секция «Model-routing пинов task-команд» в `docs/routing.md` (рационал +
  вердикт всех 7 пинов, правило синхронизации frontmatter↔description↔registry). D9 в plan.md.

**Remaining:** P4 (permission-friction, СКЕЛЕТ — детализация обязательна); P5 (discovery,
детализирован, 3 items). P1 терминальна (🟠), P2 терминальна (🟢), P3 терминальна (🟢).
**Sources of truth:** `docs/routing.md` §Model-routing пинов task-команд (политика) ·
`packages/task/commands/{dev,make-workflow}.md` (новые пины sonnet/high) · plan.md (D9, Routing §3) ·
phases/P3.md P3.2 Completion Notes + Phase Handoff · open-questions.md OQ-4 ·
findings/P3-routing-audit.md (вердикты P3.1).
**Open risks:** downgrade dev/make-workflow — качество нарезки срезов / генерации workflow под
Sonnet 5 не измерено (нет quality-телеметрии); safety-nets (review-gate / статич.выходной
ревьюер) — страховка, но не гарантия. Откат — вернуть `model: opus` во frontmatter + синхронно
description + `skiller registry`.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: `--by phase` в analyst (токен-атрибуция на workflow-уровень) — не реализовано
  (`token_report.py:38-41`); ROI пер-команды downgrade НЕ квантифицируется → приоритет trial'ов
  качественный (по downgrade-risk), не по измеренной экономии.
- open_questions: **OQ-4** — `research` opus/high → возможный A/B `sonnet/high` (Decision pending,
  владелец Dmitry Vostrikov, низкий приоритет). OQ-1/OQ-2/OQ-3 Resolved.
