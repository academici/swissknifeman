# HANDOFF — 2026-07-14 — after P3.5

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — P3.6 (`plan.md` §3 Routing: P3.6 = opus/high,
Exec = manual; `/task:plan-exec` пинит sonnet/medium и по routing-гейту обязан такие items
отклонять — не запускать через `/task:plan-exec`)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — терминальный item фазы: canon-authoring §13 SSOT + регенерация EN-канона + сквозная сверка «правило → команда» по пяти командам (D42) |
| Context | continue (/clear) — ручной item |
| Суть | `SKILL.ru.md` §13 — строка `/task:plan-run`, версия 2.6.0, регенерация EN + `check-translations.sh --stamp` + `skiller registry`, сквозная сверка правил фаз P1/P2 против всех пяти команд `plan-*` |

````
Запусти вручную под opus/high (НЕ /task:plan-exec — Exec=manual): исполни item P3.6
плана 2026.07.13-PLAN-PROTOCOL-GAP по протоколу plan-exec (packages/skiller/skills/general/
plan-protocol/SKILL.ru.md §8-11) — прочитай plan.md (Context, Execution Rules, §3 Routing,
D-лог), phases/P3.md (Phase Context + item P3.6 целиком), закрой item по каноническому
порядку закрытия (дифф → validate → bookkeeping → handoff → plan-lint ПОСЛЕ handoff → коммит).
````

**Done:** P1, P2 терминальны (P2 — 🟠 Done with deviations, 18/18, скилл `plan-protocol` 2.5.0).
**P3 (4/6 🟢 + P3.5 🟠):** P3.1 (`4cfc10a`) — `plan-exec.md`: routing-гейт, топология двух
коммитов, коммит-гигиена, status-rule, якорь дерева (180 строк). P3.2 (`0823cb4`) —
`plan-close.md`: enum 8 форм `Next` (D40), две формы заголовка handoff (D30), `Context` из
enum'а трёх значений, снятие маркера `> УСТАРЕЛ`, честный lint закрытия (145 строк). P3.3
(`f4ce8c9`) — `plan-audit.md`: правила остановки (D44) + чеклист канона 2.5.0 (115 строк).
P3.4 (`c95caed`) — `plan-design.md`: канон-Routing, скелет 16 полей, реопен-протокол,
`## 7. Contracts` (169 строк).
**P3.5 закрыт с отклонением** (item-коммит `b4146eb`, bookkeeping — этот): `commands/plan-run.md`
(28 строк) — команда БЕЗ пина `model`/`effort` (D18/D43), делегирует протокол `plan-exec.md`
целиком с ДВУМЯ отличиями (инвертированный routing-гейт + блок «Граница честности»); строки-
альтернативы `/model`+`/effort`+`/task:plan-run` добавлены в launch-block'и `plan-exec.md`/
`plan-close.md` БЕЗ превышения потолков объёма (180/180, 145/145 — слиты с существующими
строками); `packages/task/CLAUDE.md` и `description` `.claude-plugin/plugin.json` дополнены.
**Known Deviation:** item-коммит попутно пофиксил `packages/task/scripts/validate.sh`
(гейт `[4/5]` требовал `model`/`effort` у ВСЕХ команд — предвиденный Code Guidance дефект) →
дифф вне `Files` item'а ⇒ статус `🟠 Done with deviations` по status-rule, независимо от
корректности фикса. `validate.sh` зелёный (0 FAIL, на `b4146eb`).

**Remaining:**

1. **P3.6 ← Next** (ЗАПУСК ВРУЧНУЮ, opus/high — §13 SSOT + EN-канон 2.6.0 +
   `skiller registry` + сквозная сверка «правило → команда»). Закрывает фазу P3.
2. P4 (3 items): регресс по флоту (P4.1), закрытие эскалации REGHUB (P4.2, чужой репо Brain),
   доки + CHANGELOG (P4.3).
3. Аудит фазы P3 — по НОВЫМ правилам остановки (`plan-audit.md` с P3.3): один заход,
   `RED` только на сломанном продукте, бухгалтерия → `ATTENTION` + Pending Work, реопена
   по умолчанию нет.

**Sources of truth:** `plan.md` (Meta **1.4.0**, §2 Execution Rules + carve-out D34, §3 Routing —
**P3.1/P3.3/P3.6 = opus/manual**, §5 D-лог **D1–D46**, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P3.md` (6 items, P3.1–P3.5 терминальны) · `phases/P4.md` (скелет) ·
`findings/P3-command-layer.md` (матрица дыр §2, потолки объёма §3) ·
`roadmap/plan-audit-loop.md` (спека класса audit-loop) · SSOT канона:
`packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник 2.5.0; `SKILL.md` —
EN-канон; `snippets/`) · `packages/task/lib/task/plan_lint.py` ·
`packages/task/commands/plan-exec.md` (180/180) · `plan-close.md` (145/145) ·
`plan-audit.md` (115/115) · `plan-design.md` (169/185) · **`plan-run.md` (28/45, новая, ещё
не внесена в §13 SSOT — задача P3.6)**.

**Open risks:**
- **Долги аудита №4 P2 без носителя** (детали — Pending Work P3.3): (а) бухгалтерия плана его не
  отражает — D44 и Update Log говорят «аудит отменён», а блок `## Audit P2 (четвёртый)`
  (`phases/P2.md:3028`, 🔴 RED: 1 Blocker + 6 Major) записан и маршрутизирован владельцем;
  принятый долг (J2/J7/J9/J10/J15) не внесён D#; (б) **J1 (Blocker — ложно-положительный
  WARNING-гейт `plan_lint` на легальной форме `themeon/2026.07.12-BASE` P5) и J3 (шаг 1 реопена
  vs ERROR линтера) items'ов не получили**, хотя маршрутизация их обещала; Phase Context P3
  исключает `plan_lint.py` из scope фазы ⇒ нужен item P3.7 либо фаза P5 — **решение владельца**;
  (в) J5/J6 (механический агрегат Known Deviations в `plan-close`) — P3.2 закрыт без него.
- Три тела команд на потолке объёма: `plan-exec.md` 180/180, `plan-close.md` 145/145,
  `plan-audit.md` 115/115; `plan-design.md` 169/185 (16 строк запаса); `plan-run.md` 28/45
  (17 строк запаса). Пятая команда ещё НЕ внесена в `SKILL.ru.md` §13 — задача P3.6.
- Канон 2.5.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44): механический класс закрыт
  конфликт-сканом. P3.1–P3.5 расхождений канона не нашли.
- Два чужих плана флота несут WARNING по гейту H2 (VLT-REMED/P5, 2026.07.12-BASE/P5 — themeon);
  по аудиту №4 один из них (themeon) — **ложно-положительный** (J1), см. долг выше.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: раскатка директив `i18n-keep` на остальные локальные скиллы; миграция §3 Routing /
  `## Обсуждение` живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых
  планах (REGHUB — P4.2); правка `## Phase Handoff` чужих планов (вне scope); кросс-репо
  push-уведомление (роадмап); CLI-ступень `plan-lint --conflicts` (роадмап, по накоплению);
  CHANGELOG + docs пакетов (P4.3); **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик
  `plan-lint` между прогонами (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`;
  НОВЫЙ незакрытый вопрос — дом для J1/J3 (item P3.7 vs фаза P5, решение владельца), см. Open
  risks; трекер `open-questions.md` плану пока не заводится (решение — за `plan-design`).
