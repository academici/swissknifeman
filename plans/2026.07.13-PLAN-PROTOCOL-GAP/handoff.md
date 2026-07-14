# HANDOFF — 2026-07-14 — after P2.13

**Next:** /task:plan-close 2026.07.13-PLAN-PROTOCOL-GAP P2 (все 18 items фазы терминальны:
17 🟢 + 1 🟠 → закрыть фазу; аудит — следующим шагом)

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — реконсиляция статусов и Phase Handoff по git-фактам, новых решений нет (SSOT §9: docs-curator) |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P2: Status Board `17/18 🟡` → терминальный статус фазы, перезаписать `## Phase Handoff` в phases/P2.md (СНЯВ маркер `> УСТАРЕЛ — фаза реопенена D32` — блок перезаписывается целиком, канон §3) |

```
/task:plan-close 2026.07.13-PLAN-PROTOCOL-GAP P2
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). **P2: все 18 items терминальны** (17 🟢 +
P2.4 🟠) — третий реопен (D32) закрыт. Фаза 🟡 до `plan-close`.

**P2.13 закрыт** (item-коммит `d92ace0`) — терминальный item фазы: правила P2.9–P2.11 и
P2.14–P2.17 доехали до EN-канона, единственного, что грузит агент:
- **Скилл `plan-protocol` 2.5.0** (D31): `SKILL.ru.md` frontmatter → регенерация `SKILL.md`
  промтом `claude-canon-from-ru.md` целиком из RU (руками EN не правился) → `--stamp`
  (ровно 1 маркер `ru-source-sha256` — фикс G11 работает, обходка P2.4/P2.8 не понадобилась)
  → `skiller registry`.
- **Гейт литералов позеленел ровно регенерацией — G3 закрыт не декларативно:** 6 ❌ (на
  `466c7c4`) → **0 ❌ по всем 14 директивам `i18n-keep`** (на `d92ace0`). Шапки
  `Items 🟢/всего`, `D# | Дата | Решение | Почему`, `Дата | Кто (role/model) | Что` — в EN
  байт-в-байт ⇒ план, эмитенный по EN-канону, снова парсится линтером.
- **Правила третьего реопена в EN:** `Context` manual-item (D33), якорь дерева для чисел
  (D36), 4-й шаг реопена — инвалидация `## Phase Handoff` (D34), сведённая проза §6 о
  топологии (D26/P2.17).
- `packages/skiller/scripts/validate.sh` — **ПОЛНОСТЬЮ зелёный** (exit 0, 379 тестов):
  производный дрейф фазы (§6/D17) снят. `plan-lint plans --baseline HEAD` → **0 ERROR / 35 WARN,
  K = 0** (корень `plans/` монорепо, на bookkeeping-коммите).
- Known Deviation (process, 🟢): EN **764** строки против гейта ТЗ ≤700 — RU вырос 681 → 827
  (+146), а порог закладывал +50; плотность EN/RU улучшена (0.924 против 0.954 на `bef52c7`),
  дальнейшее сжатие било бы по условиям/порогам — Implementation Rules это запрещают.

**Remaining:**

1. **`plan-close P2`** ← Next. Фаза терминальна; `## Phase Handoff` несёт маркер
   `> УСТАРЕЛ — фаза реопенена D32` — по канону §3 его снимает ИМЕННО `plan-close`,
   перезаписывая блок целиком (текст команды этого ещё не предписывает — фаза P3, item P3.2:
   правку внести НЕ в этом шаге, а закрыть блок руками по канону).
2. `plan-audit P2` (четвёртый) — свежий контекст, opus/xhigh.
3. P3 (5 items: перенос правил фазы P2 в тексты команд `/task:plan-*`) → P4 (3 items: регресс
   по флоту, закрытие эскалации REGHUB, доки + CHANGELOG).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.3.0, §2 Execution
Rules + carve-out D34, §3 Routing, §5 D-лог D1–D41, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P2.md` (Completion Notes P2.1–P2.18, три append-only блока `## Audit P2`;
`## Phase Handoff` помечен маркером инвалидации — снимает `plan-close`) ·
`findings/P2-third-reopen-fleet-measurements.md` (замеры флота; §2 несёт дефект оракула — D41,
файл append-only) · `phases/P3.md`, `phases/P4.md` · SSOT канона:
`packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник **2.5.0**;
`SKILL.md` — EN-канон, СВЕЖИЙ (`d92ace0`); `snippets/`) ·
`packages/task/lib/task/plan_lint.py` (второй SSOT схемы; `CANON_LITERALS`/`HEURISTIC_LITERALS`;
резолвер форм — `_resolve_next_form`) · `packages/task/tests/test_plan_lint.py` +
`test_canon_literals.py` · `packages/skiller/scripts/check-translations.sh` ·
`packages/skiller/prompts/generate/claude-canon-from-ru.md`.

**Open risks:**
- Правила фазы P2 живут в SSOT (RU + EN + линтер), но команды `/task:plan-*` их ещё НЕ
  исполняют — фаза P3. До неё гейты держатся дисциплиной исполнителя, а не текстом команды.
- **`plan-close` не умеет снимать маркер `> УСТАРЕЛ`** (канон §3 требует, текст команды — нет):
  на шаге Next блок Phase Handoff перезаписывается вручную по канону; правка команды — P3.2.
- **Два чужих плана флота несут WARNING по гейту H2** (VLT-REMED/P5, 2026.07.12-BASE/P5 —
  themeon): приняты владельцем как истинно-положительные (D34/D39); их правка — вне scope.
- Остаточные **35 WARNING** по корню `plans/` монорепо (на bookkeeping-коммите P2.13) — чужие
  планы этого корня, вне Scope плана; ERROR — 0, K = 0 (диффом P2.13 не внесено ни одной новой).
  Счёт по 8 корням флота (116/390 на `87022d6`) живёт в `findings/` и своей командой здесь не
  воспроизводится — не переносить его в отчёты как текущий.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.
- EN-канон 764 строки (> ориентира 700) — тело CORE-скилла грузится on-trigger во всём флоте;
  при следующей правке канона сокращать прозу первым делом (`skiller budget --check-core`
  показывает ⊕-резидент 694/750 — ярус-0 не затронут, растёт только ↻ on-trigger).

**Workarounds/Deferred/Open questions:**
- workarounds: нет (обходка `--stamp` из P2.4/P2.8 больше не нужна — фикс G11 подтверждён).
- deferred: тексты команд под новые enum'ы и топологию — фаза P3 (`plan-close.md:104`,
  `plan-exec.md:70,96`, `plan-audit.md:59,65`, `plan-design.md:22,85`); **снятие маркера
  инвалидации Phase Handoff в `plan-close`** (P3.2); раскатка директив `i18n-keep` на остальные
  **158 локальных** скиллов (механизм универсален; 56 внешних гейт не видит by construction);
  миграция §3 Routing / `## Обсуждение` живых планов на канон-форму (back-compat); заполнение
  `## 7. Contracts` в живых планах (REGHUB — P4.2); правка `## Phase Handoff` двух чужих планов
  (вне scope); кросс-репо push-уведомление (роадмап); CHANGELOG + docs пакетов (P4.3);
  **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик `plan-lint` между прогонами
  (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
