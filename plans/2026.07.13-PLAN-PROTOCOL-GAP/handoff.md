# HANDOFF — 2026-07-13 — after P2.6

**Next:** `/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P2.7`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — §3 Routing: `P2.7 \| sonnet/medium \| plan-exec` (решения приняты D21–D23, правки механические) |
| Context | NEW SESSION — item правит ТОЛЬКО файлы плана; свежий контекст не обязателен, но чище |
| Суть | Ремедиация плана по вердикту аудита: P2.4 `🟢` → `🟠 Done with deviations` + Known Deviations (D21/D22, 6-й material-триггер §6); строка Phase Status; счётчик фазы P2 на доске; 4 развилки `## Обсуждение` получают `**Статус:** Resolved → D#` (D23, форма канонизирована P2.6); F4 — число «23 попадания» в Completion Notes P2.1 заменить ПРОГОНОМ команды из его Validation |

````
Исполни item P2.7 плана 2026.07.13-PLAN-PROTOCOL-GAP (репо swissknifeman) строго по ТЗ.

ТЗ: plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md, раздел «### P2.7 — Ремедиация плана по
аудиту: статус P2.4, статусы развилок, F4» — все 16 полей, включая Code Guidance и Validation.
Правила плана: plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md §2 Execution Rules, §5 D21/D22/D23.
Основание: находки F2/F3/F4 в блоке «## Audit P2 — 2026-07-13» (конец phases/P2.md).

Правятся ДВА файла плана: plan.md и phases/P2.md. Кода item НЕ касается. Блок `## Audit P2`
append-only — не править. `open-questions.md` НЕ заводить (незакрытых развилок нет — правило
§3 канона после P2.6).

Закрытие item'а — по канону §8: дифф → validate.sh → bookkeeping плана (Phase Status,
Status Board, Update Log) → перезапись handoff.md → `python3 packages/task/scripts/plan-lint.py
plans/2026.07.13-PLAN-PROTOCOL-GAP --baseline HEAD` ПОСЛЕ handoff → счёт с атрибуцией
(«новых от диффа item'а: K», гейт K=0) → коммит ПО ЯВНЫМ ПУТЯМ (`git add plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md
plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md`; `git add -A` запрещён — §6 канона, P2.5).
````

**Done:** P1 терминальна (`4c03715`, `b45cd51`). Фаза P2 — **6/8**: `38954ab` P2.1 §9
routing-гейт · `cd749ab` P2.2 §6 status-rule · `1451ed9` P2.3 §4/§11 Contracts + линтер ·
`365079c` P2.4 snippets + EN-канон 2.3.0 (закрыт 🟢, но по 6-му триггеру §6 обязан стать 🟠 —
переоценка в P2.7) · `c90b5fb` реопен P2 по RED-аудиту (plan-design, D21–D25) · `4a4af60` P2.5
§6 коммит-гигиена + 6-й material-триггер (D22) · **P2.6 — §3/§4 носитель развилок (D23)**.

Что даёт P2.6 в SSOT (`SKILL.ru.md` 2.3.0 + `snippets/plan-template.md`): развилка дизайна
имеет КАНОНИЧЕСКИЙ носитель. §4 — опциональная **ненумерованная** секция `## Обсуждение`
(последней; опознаётся по ЗАГОЛОВКУ, а не по номеру — прецедент D20, легаси держат её под
номером 7) с ОБЯЗАТЕЛЬНОЙ строкой `**Статус:** Resolved → D# | Decision pending | Exploration`
у каждой развилки. §3 — разграничение ролей без дублей: план = ПРОВЕНАНС (архивируется с
планом), `open-questions.md` = ТРЕКЕР незакрытого (статус ≠ `Resolved` ⇒ запись обязательна;
резолвнутое не копируется; незакрытых нет → файла нет). §7 — DoR-пункт переписан под это.
Линтер секцию НЕ парсит (D23 — back-compat).

**Remaining:** P2.7 (ремедиация плана: P2.4 → 🟠, статусы 4 развилок, F4 — sonnet,
`/task:plan-exec` — СЛЕДУЮЩИЙ) → P2.8 (терминальный: version 2.4.0 + регенерация EN-канона +
`skiller registry`, opus/manual) → повторный аудит P2 → P3 (5 items) → P4 (3 items).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D25, `## Обсуждение`) · `phases/P2.md` (ТЗ P2.7–P2.8 + Completion Notes
P2.1–P2.6 + блок `## Audit P2`) · `phases/P3.md`, `phases/P4.md` (ТЗ следующих фаз; в них уже
вписаны зеркала D22/D23) · SSOT канона: `packages/skiller/skills/general/plan-protocol/`
(`SKILL.ru.md` — источник; `SKILL.md` — EN-канон, генерируется; `snippets/`) ·
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- **Два производных гейта скилла красные** (`packages/skiller/scripts/validate.sh`):
  `check-translations` (EN-канон протух с P2.5/P2.6) И `registry --check` (дрейф `skills.json` +
  `docs/guide/budget.md` от правки `snippets/plan-template.md` в P2.6 — snippets входят в
  `sha256` скилла и в ярус ⌥ бюджета; RU-правки реестр НЕ двигают). Оба снимает терминальный
  P2.8 (`skiller registry` уже в его Scope и Files — план менять не пришлось). Легально по
  §6/D17 ТОЛЬКО потому, что терминальный item есть и назван. До P2.8 правила P2.5/P2.6 агентам
  флота НЕ доехали (RU в контекст не грузится).
- **Правила уже в SSOT, но команды `/task:plan-*` их ещё не исполняют** (фаза P3): routing-гейт,
  status-rule, коммит-гигиену и носитель развилок применяет только читающий человек/агент.
  Зеркала D22/D23 в `plan-exec`/`plan-close`/`plan-audit`/`plan-design` — P3.1–P3.4.
- Статус P2.4 остаётся 🟢 до P2.7 (по 6-му триггеру §6 обязан стать 🟠) — доска до этого момента
  завышена на один item.
- Back-compat живых планов: `vaulter/VLT-HSEAM`, `themeon` несут `## Обсуждение` БЕЗ статусов —
  линтер её не парсит (D23), гейт только в DoR-чеклисте §7 и в `plan-audit` (P3.3). Регресс по
  vaulter после P2.6: 9 ERROR / 22 WARN — без изменений.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: `check-translations.sh --stamp` ДОПИСЫВАЕТ второй маркер `ru-source-sha256` вместо
  замены плейсхолдера `PENDING` — строку-заглушку удаляем вручную (обходка в процессе, файл
  корректен). Понадобится снова в P2.8.
- deferred: фикс `check-translations.sh --stamp` (дефект skiller, отдельный item вне плана);
  миграция §3 Routing 26 живых планов на канон-форму (back-compat: легаси валидны); миграция
  живых `## Обсуждение` на форму со статусами (back-compat: секция без статусов остаётся
  валидной, гейт — DoR новых планов); заполнение `## 7. Contracts` в живых планах (REGHUB —
  P4.2); кросс-репо push-уведомление о бампе контракта (роадмап).
- open_questions: развилки `plan.md` `## Обсуждение` — все четыре закрыты D-логом (D1/D3 ·
  D5/D6/D11 · D10 · D9); строки статусов проставит P2.7 (D23, форма — §4 канона после P2.6).
  Незакрытых развилок нет → `open-questions.md` плану не заводится.
