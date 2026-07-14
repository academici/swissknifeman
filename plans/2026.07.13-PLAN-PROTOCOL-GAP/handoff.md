# HANDOFF — 2026-07-14 — after P3.1

**Next:** `/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.2`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — копипаст готовых формулировок, Validation детерминированна |
| Context | continue (/clear) — ручной item |
| Суть | `plan-close.md`: enum 8 форм `Next`, заголовок `after Pn`, честный lint закрытия, снятие `> УСТАРЕЛ` |

```
/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.2
```

P3.2 — `Exec = plan-exec` (§3 Routing, sonnet/medium): формулировки уже написаны в
`plan-exec.md` (P3.1) — Implementation Rules P3.2 требуют КОПИПАСТ блока «порядок закрытия /
счёт с атрибуцией», не парафраз; расхождение формулировок = второй SSOT.

**Done:** P1 терминальна (`4c03715`, `b45cd51`). **P2 закрыта: 18/18 items терминальны**
(17 🟢 + P2.4 🟠) → фаза **🟠 Done with deviations**; скилл `plan-protocol` **2.5.0**, EN-канон
свежий (`d92ace0`), гейт литералов 0 ❌. Аудит №4 P2 отменён (D44) в пользу детерминированного
конфликт-скана.

**P3.1 закрыт** (item-коммит `4cfc10a`, bookkeeping — этот): `packages/task/commands/plan-exec.md`
**124 → 180 строк** (на `4cfc10a`) — исполнительный слой впервые несёт правила фаз P1/P2:
- **routing-гейт** (§9, 5 веток) в п. 2, ДО пометки 🟡: `ROUTING-BLOCKED` при `Exec = manual`
  (задан ИЛИ выведен деривацией по тир-порядку), `ROUTING-INCONSISTENT` при `Exec = plan-exec`
  с model>sonnet / effort>medium, fail-safe «при сомнении — СТОП» — **F7 закрыт в тексте команды**;
- **топология ДВУХ коммитов** (§8, шаги 1–6): item-коммит по путям `Files` → bookkeeping
  (+ `Last Updated`) → перезапись handoff → **`plan-lint --baseline HEAD` ПОСЛЕ handoff** → счёт
  `N ERROR / M WARN — новых от диффа item'а: K`, гейт закрытия **K = 0** → bookkeeping-коммит (B1);
- **коммит-гигиена** (запрет `git add -A`/`-a`, carve-out плановых путей), **status-rule**
  (6 material-триггеров; process → 🟢 + запись; дефект ТЗ → эскалация + D#), **якорь дерева** для
  чисел (D36), **`Context` — enum трёх значений** и форма «ЗАПУСК ВРУЧНУЮ» с голым промптом (D33).

**Remaining:**

1. **P3** (1/6): **P3.2 `plan-close` ← Next** → P3.3 `plan-audit` (**ЗАПУСК ВРУЧНУЮ, opus/high** —
   правила остановки, D44) → P3.4 `plan-design` → P3.5 `plan-run` → **P3.6 терминальный**
   (**ЗАПУСК ВРУЧНУЮ, opus/high** — §13 SSOT + EN-канон 2.6.0 + сквозная сверка).
   Порядок обязателен: P3.2/P3.5 читают тело `plan-exec.md` ПОСЛЕ P3.1 (оно готово).
2. P4 (3 items): регресс по флоту, закрытие эскалации REGHUB, доки + CHANGELOG.
3. Аудит фазы P3 — по НОВЫМ правилам остановки (после P3.3): один заход, RED только на сломанном
   продукте, бухгалтерия → ATTENTION + Pending Work, реопена по умолчанию нет.

**Sources of truth:** `plan.md` (Meta **1.4.0**, §2 Execution Rules + carve-out D34, §3 Routing —
**P3.1/P3.3/P3.6 = opus/manual**, §5 D-лог **D1–D45**, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P2.md` (Completion Notes P2.1–P2.18, три блока `## Audit P2`, `## Phase Handoff`) ·
`phases/P3.md` (**6 items**, P3.1 🟢) · `phases/P4.md` (скелет) · `findings/P0-protocol-gap-recon.md`,
`findings/P2-third-reopen-fleet-measurements.md`, `findings/P3-command-layer.md` (матрица дыр §2,
потолки объёма §3) · SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` —
источник 2.5.0; `SKILL.md` — EN-канон; `snippets/`) · `packages/task/lib/task/plan_lint.py` ·
**`packages/task/commands/plan-exec.md` — эталон формулировок для P3.2/P3.5** (порядок закрытия,
routing-гейт, status-rule).

**Open risks:**
- **Тело `plan-exec.md` на потолке — 180/180 строк** (на `4cfc10a`). P3.5 обязан дописать в его
  launch-block строку-альтернативу `/task:plan-run` ⇒ сперва высвободить строки сокращением ПРОЗЫ
  (правила не выбрасывать) либо согласовать поднятие потолка `findings/P3-command-layer.md` §3.
- Канон 2.5.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44): механический класс закрыт
  конфликт-сканом, «правило непротиворечиво, но вредно» — нет. Первое живое применение — эта фаза
  (P3.1 расхождений канона не нашёл: 5 веток гейта и 6 шагов закрытия переносятся без конфликтов).
- Остальные четыре команды `/task:plan-*` правил канона ещё НЕ несут — до закрытия P3 гейты
  держатся дисциплиной исполнителя.
- Два чужих плана флота несут WARNING по гейту H2 (VLT-REMED/P5, 2026.07.12-BASE/P5 — themeon):
  приняты владельцем как истинно-положительные (D34/D39); их правка — вне scope.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: раскатка директив `i18n-keep` на остальные локальные скиллы; миграция §3 Routing /
  `## Обсуждение` живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых
  планах (REGHUB — P4.2); правка `## Phase Handoff` двух чужих планов (вне scope); кросс-репо
  push-уведомление (роадмап); CHANGELOG + docs пакетов (P4.3); **[POSSIBLE-DEFECT]** нестабильный
  порядок вывода диагностик `plan-lint` между прогонами (пре-существующий, на счётчики/`--baseline`
  не влияет).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
