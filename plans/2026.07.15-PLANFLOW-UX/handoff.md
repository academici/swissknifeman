# HANDOFF — 2026-07-15 — after P3.2

**Next:** /task:plan-exec 2026.07.15-PLANFLOW-UX P3.3

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — детерминированный чек `plan_lint` (имя/место workflow) + TDD-тесты, независимый python-scope |
| Context | continue (/clear) — ручной item |
| Суть | Добавить в `plan_lint.py` WARNING-детектор имени/места плановых workflow-скриптов (`wf-<id>-*.js` в `plans/<ID>/workflows/`), `dev-loop.js` exempt |

```
/task:plan-exec 2026.07.15-PLANFLOW-UX P3.3
```

**Done:** P3.2 закрыт 🟠 Done with deviations — боевой хардненинг вшит в 4 канон-шаблона
`packages/task/workflows/`: `safeAgent` (bare `await agent()` → `null` при throw) в
`wf-audit-adversarial.js`/`wf-dev-slice.js` (единственные с bare-вызовами вне
`parallel`/`pipeline`); REPO/путь-инвариант (`X.startsWith('/')`-assert) у `REPO`/`SPEC`/
`TARGET.paths`; guarded-optional-args (typeof-дефолт `riskOf(s)` в dev-slice + документация
существующих ternary-guard'ов); per-item cache-bust — комментарий-паттерн `asOf` у всех
4 item-массивов. `workflow-craft` §2.1: поднят `wf-edufy-2-design-wave.js` (vault Brain) как
high-water-mark эталон (SLOT-маркеры, judge-panel-гейт, `MAX_FIX_ROUNDS`), 2 прежних эталона
сохранены как база. Правки: `packages/task/workflows/{README.md,wf-research-fanout.js,
wf-author-by-spec.js,wf-audit-adversarial.js,wf-dev-slice.js}`, `workflow-craft`
`SKILL.ru.md`/`SKILL.md` §2.1. Item-коммиты b36db62 (Files ТЗ) + 47ed9a3 (registry-артефакты
вне Files — паттерн P2.1/P3.1 повторился 3-й раз). Прогон: `node --check` × 4 (0 ошибок),
`validate.sh` (140 тестов OK), `check-translations.sh --stamp` (159 SKILL.md), `skiller registry`
(215 скиллов), `packages/skiller/scripts/validate.sh` (379 тестов OK).

**Remaining:** P3.3 (независим, sonnet/medium `/task:plan-exec`) → P3.4 (независим, sonnet/medium
`/task:plan-exec`) → P3.5 (opus/high manual, доставка-гейт analysis). Затем `plan-close P3`
(Phase Handoff, фаза закроется 🟠 — P3.1/P3.2 оба Done with deviations) → детализация P4 → P5.

**Sources of truth:** `phases/P3.md` (P3.1–P3.2 Completion Notes + P3.3–P3.5 ТЗ) · `plan.md`
(§3 Routing P3.1–P3.5, §4 Phase Index P3 → 🟡 In progress 0/5, §6 Update Log) ·
`findings/P1-recon.md` §1.3/§1.4 (дефекты по строкам, edufy-2 «Ирония эталона») · каноны-правленные:
`packages/task/workflows/README.md` + 4 шаблона, `workflow-craft` `SKILL.ru.md`/`SKILL.md`.

**Open risks:** Known Deviation P3.2 — registry-артефакты вне `Files` (паттерн P2.1→P3.1→P3.2,
3-й раз подряд); fix-предложение P3.1 (внести артефакты `skiller registry` в `Files` любого
item'а, правящего `SKILL.ru.md`) при детализации P3.2 применено не было (P3.2 задизайнена ДО
закрытия P3.1) — следующему `plan-design`-проходу внести правило в сам шаблон ТЗ, не
документировать реактивно на каждом item'е. Validation-пункт «сухой прогон/бросающий agent»
выполнен статическим прослеживанием кода, не живым вызовом `Workflow()` (process-деviation,
см. Known Deviations P3.2). P3.1 pre-mortem (Обсуждение №5) остаётся открытым до P3.5/OQ-3.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: детализация P4–P5 (contract-first, just-in-time, D5); rollout доставки гейта (P3.5
  Pending — пост-резолв OQ-3, deleg skiller/maind); launch-block вне `plan-*` (OQ-2); правило
  «registry-артефакты в Files» для будущего `plan-design`-прохода (выше) — не в Scope P3.2.
- open_questions: **OQ-1** (артефакт exec-плана, P4) · **OQ-2** (launch-block в `dev.md`/`fix.md`) ·
  **OQ-3** (канал доставки гейта workflow-craft/make-workflow — CORE vs onboard-required; резолв в
  exec P3.5 на budget-данных; владелец Dmitry Vostrikov).
