# HANDOFF — 2026-07-14 — after P2

**Next:** /task:plan-audit 2026.07.13-PLAN-PROTOCOL-GAP P2

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — четвёртый аудит закрытой фазы с material Known Deviations, свежий контекст (SSOT §9) |
| Context | NEW SESSION — фаза закрыта, рекомендован /clear |
| Суть | Адверсариальный аудит фазы P2 (18/18 терминальны, 17 🟢 + 1 🟠) перед стартом P3 — сверить ремедиацию H1–H13/G1–G13 с git-фактами, no-op, scope drift |

```
/task:plan-audit 2026.07.13-PLAN-PROTOCOL-GAP P2
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). **P2 закрыта: 18/18 items терминальны**
(17 🟢 + P2.4 🟠 Done with deviations) → фаза **🟠 Done with deviations**. Третий реопен (D32)
ремедиирован items P2.14–P2.18 (H1–H13), терминальный item P2.13 исполнен последним (D32);
`## Phase Handoff` в `phases/P2.md` перезаписан `plan-close` (маркер `> УСТАРЕЛ` снят, финальный
агрегат Known Deviations + сдача H1–H13). `plan-lint plans/2026.07.13-PLAN-PROTOCOL-GAP` →
**0 ERROR / 0 WARN**.

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
  производный дрейф фазы (§6/D17) снят.
- Known Deviation (process, 🟢): EN **764** строки против гейта ТЗ ≤700 — RU вырос 681 → 827
  (+146), а порог закладывал +50; плотность EN/RU улучшена (0.924 против 0.954 на `bef52c7`),
  дальнейшее сжатие било бы по условиям/порогам — Implementation Rules это запрещают.

**Remaining:**

1. **`plan-audit P2`** ← Next (четвёртый аудит; прошлые три — 🔴 RED, но back-compat-гейт и
   весь класс H1–H13/G1–G13 к моменту этого аудита уже устранены — оценивает ремедиацию, не
   с нуля).
2. Аудит 🟢/🟠 без новых Blocker'ов → P3 (5 items: перенос правил фазы P2 в тексты команд
   `/task:plan-*`) → P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки + CHANGELOG).
   Аудит находит новый класс — пятый реопен по канону §3 (D32-прецедент).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.3.0, §2 Execution
Rules + carve-out D34, §3 Routing, §5 D-лог D1–D41, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P2.md` (Completion Notes P2.1–P2.18, три append-only блока `## Audit P2`;
`## Phase Handoff` перезаписан плоским финальным блоком — маркер инвалидации снят) ·
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
- **Два чужих плана флота несут WARNING по гейту H2** (VLT-REMED/P5, 2026.07.12-BASE/P5 —
  themeon): приняты владельцем как истинно-положительные (D34/D39); их правка — вне scope.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.
- EN-канон 764 строки (> ориентира 700) — тело CORE-скилла грузится on-trigger во всём флоте;
  при следующей правке канона сокращать прозу первым делом (`skiller budget --check-core`
  показывает ⊕-резидент 694/750 — ярус-0 не затронут, растёт только ↻ on-trigger).

**Workarounds/Deferred/Open questions:**
- workarounds: нет (обходка `--stamp` из P2.4/P2.8 больше не нужна — фикс G11 подтверждён).
- deferred: тексты команд под новые enum'ы и топологию — фаза P3 (`plan-close.md:104`,
  `plan-exec.md:70,96`, `plan-audit.md:59,65`, `plan-design.md:22,85`); раскатка директив
  `i18n-keep` на остальные **158 локальных** скиллов (механизм универсален; 56 внешних гейт не
  видит by construction); миграция §3 Routing / `## Обсуждение` живых планов на канон-форму
  (back-compat); заполнение `## 7. Contracts` в живых планах (REGHUB — P4.2); правка
  `## Phase Handoff` двух чужих планов (вне scope); кросс-репо push-уведомление (роадмап);
  CHANGELOG + docs пакетов (P4.3); **[POSSIBLE-DEFECT]** нестабильный порядок вывода
  диагностик `plan-lint` между прогонами (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
