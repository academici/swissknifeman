# HANDOFF — 2026-07-16 — after P5.1

**Next:** «ЗАПУСК ВРУЧНУЮ: sonnet/high» — P5.2 Exec = manual (§3 Routing: effort>medium → команда plan-exec не переключит модель; исполнять под предписанной sonnet/high)

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — канон-когерентность §6 (carve-out ↔ foreign-diff ↔ фазовая когерентность), читаемая всем флотом; §9 «канон, за которым следует флот → high MANDATORY» |
| Context | continue (/clear) — ручной item (регулярный item-by-item под предписанной моделью; NEW SESSION не требуется) |
| Суть | P5.2 — §6 carve-out «детерминированные производные артефакты — часть Scope item'а» (снять систематический ложный-🟠 6× подряд) + зеркало EN + регенерация реестра |

```
Исполни item P5.2 плана 2026.07.15-PLANFLOW-UX строго по ТЗ в
plans/2026.07.15-PLANFLOW-UX/phases/P5.md (раздел «### P5.2»). Модель sonnet, effort high
(предписано §3 Routing, Exec=manual — не понижать). Путь D18: /model sonnet + /effort high +
/task:plan-run 2026.07.15-PLANFLOW-UX P5.2 (равнозначно прямому исполнению по ТЗ).

Прочитай Required Reads по порядку, затем:
1. Допиши абзац-carve-out в plan-protocol §6 (SKILL.ru.md — ИСТОЧНИК, L305–312 рядом с foreign-
   diff-правилом): «детерминированный производный артефакт» = выход НАЗВАННОЙ команды регенерации
   над Files-источниками item'а (реестр-манифесты, EN-канон, локфайлы, снапшоты доков) → часть
   Scope, НЕ material-deviation, в Files можно не перечислять. ГРАНИЦА обязательна: carve-out НЕ
   покрывает недетерминированное/ручное/чужое (foreign-diff-защита F1 СУЖАЕТСЯ, не снимается).
   Generic-формулировка (D17), НЕ частный случай skills.json/budget.md. Согласуй с «фазовой
   когерентностью производного» (L373–381) — не противоречить.
2. Регенерируй SKILL.md из RU (промт prompts/generate/claude-canon-from-ru.md) →
   check-translations.sh --stamp → skiller registry. Производные реестра — в item-коммит (в Files).
3. Закрой item по §8. Validation: check-translations 0 дрейфа + skiller validate.sh зелёный +
   plan-lint K=0. НЕ трогать plan_lint.py; НЕ ослаблять foreign-diff-защиту; НЕ править SKILL.md руками.
```

**Done:** P5.1 закрыт 🟢 — подраздел «RECOVERY при клинче» в `plan-protocol §7` (RU `SKILL.ru.md`
+27 строк · EN `SKILL.md` +33, регенерация): средний-батч-вокруг-хотспота · интеграционная
валидация DoR после каждого батча · финальная консолидация одним проходом · progressive-freeze
(контракт-блок §5) · пустой feasible-set → удалить вариант (SBD) · эскалация к Perplexity · критерий
остановки. Зеркало-заметка в `plan-design.md §Refine-цикл`. Верификация анти-клинч-канона (D18):
`plan-audit.md` L22–35 закрывает AUDIT-петлю, P5.1 закрывает DESIGN-рефайн-петлю; RECOVERY additive
к P4.1(§5)/P4.2(§9). RAG:✅ SBD/LRM. Item-коммит `d9225f5`, bookkeeping `2deb44d`.

**Remaining:** exec P5.2 → P5.3 (последовательно, coupling на `SKILL.ru.md` §6↔§7). P5.3 —
терминальный item фазы (полный зелёный `validate.sh` обязателен, §6). После P5.3 — фаза P5
закрывается (`/task:plan-close P5`), затем план терминален целиком (`/task:plan-close archive`).

**Sources of truth:** `phases/P5.md` (ТЗ P5.1✅/P5.2/P5.3, Completion Notes P5.1) · `plan.md`
(§3 Routing P5.1–P5.3, §4 Status Board P5 1/3, §5 D15–D18, §6 Update Log) ·
`findings/P5-design-convergence.md` (RAG SBD/LRM) · `packages/skiller/skills/general/plan-protocol/SKILL.ru.md`
§6/§7 · `packages/task/commands/plan-audit.md` L22–35 (анти-клинч-канон, верифицирован D18).

**Open risks:**
- **Bookkeeping-коммит P5.1 аггрегировал ИНХЕРИТ-дифф** (в дереве до старта P5.1, всё в `plans/<ID>/**`
  = carve-out §8, НЕ foreign diff): (а) детализация P5 plan-design/opus (D15–D17, ТЗ P5.1–P5.3,
  `findings/P5-design-convergence.md`) — некоммичена прошлой сессией; (б) блок «## Audit P4 — 2026-07-16»
  в `phases/P4.md` (вердикт ATTENTION, F1–F3) — прогнан, но его СОБСТВЕННАЯ бухгалтерия неполна
  (§6 Update Log/§4 Status Board P4 не реконсилированы под аудит). Провенанс назван здесь; реконсиляцию
  P4-аудита сделать при `plan-close archive` (или отдельным bookkeeping-проходом).
- **6× Files-паттерн** (ложный-🟠 реестр-вне-Files) чинится именно **P5.2** (§6 carve-out) — до его
  закрытия item'ы (вкл. P5.1) обходят локальной дисциплиной (реестр в `Files` явно). P4-аудит F2 —
  тот же паттерн, PROMOTE-CANDIDATE → адресуется P5.2.
- `plan-lint --baseline HEAD` несёт предсуществующие WARN-false-positive (DoR §7 orchestration-эвристика
  P1/P3/P4 — P4-аудит F3, `plan_lint.py` грепает «оркестрац» без учёта отрицания) — не блокер, вне scope P5.

**Workarounds/Deferred/Open questions:**
- workarounds: P5.1 перечислил реестровые артефакты (`skills.json`/`budget.md`) в `Files` явно (обход
  ложного-🟠 до §6 carve-out P5.2).
- deferred: OQ-2 (launch-block в `dev.md`/`fix.md`); OQ-3 rollout доставки гейта `workflow-craft`
  (deleg skiller/maind, пост-Owner); P4-аудит бухгалтерия-реконсиляция перед архивацией.
- open_questions: **OQ-2** (pending Owner) · **OQ-3** (квантифицирован P3.5, рекомендация A=CORE_SKILLS,
  pending Owner). Оба вне exec-scope P5 (Границы фазы); план закроется 🟠 с ними pending либо промотируются
  follow-up-планом.

**Context:** continue (/clear) — P5.2 ручной item под sonnet/high; `/clear` перед стартом (читать план
с диска: plan.md → phases/P5.md → handoff.md). NEW SESSION не требуется (не Workflow, не шаг-не-item).
