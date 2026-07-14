# HANDOFF — 2026-07-14 — after P2.18

**Next:** ЗАПУСК ВРУЧНУЮ (P2.13, Exec=manual — `plan-exec` пинит sonnet/medium, ниже требуется opus/high)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — терминальный item фазы: регенерация EN-канона под новым гейтом литералов — canon-authoring, не механика |
| Context | continue (/clear) — ручной item |
| Суть | P2.13 — version 2.5.0 + регенерация EN-канона (все правила P2.9–P2.17) + `skiller registry`; ТОЛЬКО после него `packages/skiller/scripts/validate.sh` обязан быть полностью зелёным и гейт литералов — дать 0 ❌ по всем 14 директивам |

```
Прочитай plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md (Context, Execution Rules, Routing, Status
Board), handoff.md (этот файл), phases/P2.md (Phase Context + item P2.13 целиком), затем
Required Reads item'а — и исполни P2.13 по протоколу plan-exec (см. общий скилл plan-protocol,
§ «Закрытие»), под моделью opus/effort high.
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2: items P2.1–P2.12 + P2.14–P2.18 закрыты
(16 🟢 + P2.4 🟠 из 18); фаза 🟡 — третий реопен (D32) почти закрыт, остался ровно один item.

**P2.18 закрыт** (item-коммит `39d1a43`) — устранены пять ложных/невоспроизводимых утверждений
bookkeeping'а, по правилу якоря дерева (D36):
- **H4** (`phases/P2.md`, Completion Notes P2.7): обоснование «🟢 не убавилось» переписано на
  факт — `plan_lint.py:52,897` считают числитель строгим равенством `🟢 Done`, P2.4 из множества
  🟢 вышел (🟢→🟠), число удержалось на 6 только за счёт ТОГО ЖЕ коммита `4cb9b77`, где P2.7
  перешёл ⬜→🟢 (оба флипа в одном диффе).
- **H5** (Known Deviations P2.12): число попаданий `5/8` — 3 (на item-коммите `7bbeb76`) vs
  7 (на закоммиченном дереве после bookkeeping-коммита `0eebe4b`); оба записаны с явным якорем.
- **H6** (Completion Notes P2.10): «посимвольно» заменено на честную формулировку — счётчики
  совпадают (128 ERROR / 380 WARN), 15 текстов диагностик переформулированы (2 ERROR + 13 WARN),
  back-compat по существу не нарушен.
- **H8** (Completion Notes/Pending Work/Scope Excluded P2.11): «остальные 215 скиллов» → «остальные
  158 локальных» (159 локальных − 1 `plan-protocol`; 56 внешних гейт не видит by construction;
  159 + 56 = 215 всего).
- **H12** (карта «коммит → item» P2.12): «сверено 20 коммитов фазы» переписано — 20 хешей карты ≠
  25 коммитов окна фазы (`git log --oneline 348c60a..0eebe4b`); в карту добавлен плановый коммит
  `fc57561` («D18 + item P3.5»), которого в ней не было.
- Шестого ложного утверждения вне H4/H5/H6/H8/H12 не найдено.
- `plan-lint --baseline HEAD` → K = 0. `packages/task/scripts/validate.sh` → OK (124 теста).

**Remaining:** один item P2 — терминальный, исполняется ПОСЛЕДНИМ (D32):

1. **P2.13** (opus/high, manual, **ТЕРМИНАЛЬНЫЙ**) — скилл 2.5.0 + регенерация EN-канона +
   `skiller registry`; несёт правила P2.9–P2.17 (Context manual-item, якорь дерева, инвалидация
   Phase Handoff, реестр CANON_LITERALS, гигиена §6, гейт item-формы). ← Next
2. Далее: `plan-audit P2` (четвёртый) → P3 (5 items: перенос правил в команды `/task:plan-*`) →
   P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.3.0, §2 Execution Rules
+ carve-out D34, §3 Routing, §5 D-лог D1–D41, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P2.md` (Completion Notes P2.1–P2.12 + P2.14–P2.18, ТЗ P2.13, три append-only блока
`## Audit P2` — третий несёт H1–H13 с командами-доказательствами; `## Phase Handoff` помечен
маркером инвалидации — гейт на нём молчит) ·
`findings/P2-third-reopen-fleet-measurements.md` (замеры флота; §2 несёт дефект оракула — см. D41,
файл append-only и не правится) · `phases/P3.md`, `phases/P4.md` · SSOT канона:
`packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник; `SKILL.md` — EN-канон,
ПРОТУХ — снимет P2.13; `snippets/`) · `packages/task/lib/task/plan_lint.py` (второй SSOT схемы;
реестр литералов — `CANON_LITERALS`/`HEURISTIC_LITERALS`; резолвер форм — `_resolve_next_form`) ·
`packages/task/tests/test_plan_lint.py` + `test_canon_literals.py` ·
`packages/skiller/scripts/check-translations.sh` ·
`packages/skiller/prompts/generate/claude-canon-from-ru.md`.

**Open risks:**
- **EN-канон `SKILL.md` по-прежнему ЛОМАЕТ линтер** (G3): несёт `Items 🟢/total`,
  `D# | Date | Decision | Why` — план, эмитенный по EN-канону, не парсится (5 ERROR). Чинит
  регенерация в **P2.13**; до тех пор `/task:plan-design` в проектах флота может эмитить невалидный
  Status Board.
- **Правил P2.9–P2.11 и P2.14–P2.17 в EN-каноне НЕТ:** агент грузит `SKILL.md`. До P2.13 новые
  правила обязывают только тех, кто читает RU-источник или этот план.
- **Гейт литералов на P2.13 идёт под полным реестром** (P2.16): `check-translations.sh` держит
  6 ❌ (протухший EN), снимает регенерация.
- **Производный дрейф ожидаем и легален** (§6/D17): `packages/skiller/scripts/validate.sh` КРАСЕН
  ТОЛЬКО registry-drift'ом (`skills.json`/`budget.md` — пре-существующий). Полный зелёный требуется
  только на терминальном P2.13. Красное по любой ДРУГОЙ причине — блокер.
- **Два чужих плана флота несут WARNING по гейту H2** (VLT-REMED/P5, 2026.07.12-BASE/P5 — themeon):
  приняты владельцем как истинно-положительные (D34/D39); их правка — вне scope.
- Правила фазы P2 попадают в SSOT, но команды `/task:plan-*` их ещё не исполняют (фаза P3).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: тексты команд под новые enum'ы и топологию — фаза P3 (`plan-close.md:104`,
  `plan-exec.md:70,96`, `plan-audit.md:59,65`, `plan-design.md:22,85`); **`plan-close` обязан
  снимать маркер инвалидации Phase Handoff, перезаписывая блок** (канон §3 требует, текст команды —
  ещё нет: P3.2); раскатка директив `i18n-keep` на остальные **158 локальных** скиллов (механизм
  универсален; 56 внешних гейт не видит by construction); миграция §3 Routing / `## Обсуждение`
  живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых планах (REGHUB —
  P4.2); правка `## Phase Handoff` двух чужих планов (вне scope); кросс-репо push-уведомление
  (роадмап); **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик `plan-lint` между
  прогонами (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
