# HANDOFF — 2026-07-14 — after P2.14

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high»

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона §3 + новый WARNING-гейт в `plan_lint`: формулировка бьёт по 26 живым планам флота (3 чужих плана получат новый WARNING — приняты владельцем, D34); `/task:plan-exec` пинит sonnet и по routing-гейту (P2.1) обязан такие items отклонять |
| Context | continue (/clear) — ручной item |
| Суть | P2.15 — §3: реопен фазы получает 4-й шаг (инвалидация `## Phase Handoff` маркером `> УСТАРЕЛ — фаза реопенена <D#>`, блок не удаляется) + УЗКИЙ WARNING-гейт в `plan_lint.py` (фаза НЕтерминальна + блок непуст + утверждает закрытие + нет маркера) + 3 теста (D34) |

```text
Голый промпт item'а — читать `plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md`, раздел
`### P2.15 — §3: инвалидация Phase Handoff при реопене + гейт линтера (H2)` целиком
(Intent/Scope Included/Scope Excluded/Required Reads/Implementation Rules/Code Guidance/Validation) —
Exec = manual (§9 Routing), команды `/task:plan-exec` для этого item'а не существует.
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2: items P2.1–P2.12 + **P2.14** закрыты
(12 🟢 + P2.4 🟠 из 18); фаза 🟡 — **третий реопен (D32)**: третий аудит дал 🔴 RED (3 Major),
фаза выросла до 18 items.

**P2.14 закрыт** (item-коммит `7110507`) — снят H1 (Major) + канонизированы D36/D38:
- **D33/H1:** §8 `SKILL.ru.md` (`:503–515`) получил правило `Exec = manual` — форма «ЗАПУСК
  ВРУЧНУЮ» (Model из Routing, code-block = ГОЛЫЙ ПРОМПТ, slash-команда запрещена) и `Context` =
  `continue (/clear) — ручной item`; enum остался из ТРЁХ значений. Снипет
  `launch-block-template.md` перестал быть вторым SSOT — цитирует §8 (нормативная строка `:35`
  «Exec = manual → NEW SESSION» удалена). Проверено grep'ом ДО (`0eebe4b`) и ПОСЛЕ (`7110507`).
- **D36/H4–H6/H12:** §8 (`:458–475`) — правило **якоря дерева**: любое число в отчёте item'а
  приводится с `git-ref`, на котором воспроизводимо (дифф Scope → item-коммит; файлы плана →
  bookkeeping-коммит). Число с дерева момента написания = ложное утверждение (класс B1).
- **D38/H11:** §8, шаг 2 bookkeeping'а (`:436–437`) — `Last Updated` в `plan.md` обновляется датой
  закрытия item'а; линтер-гейта НЕТ (сверяет чеклист `plan-audit`).

**Третий аудит P2 (2026-07-14, opus/xhigh)** — блок `## Audit P2 (третий)` в `phases/P2.md`.
Ремедиация №2 (G1–G13) засчитана по существу; RED дали НОВЫЕ дефекты, внесённые самой ремедиацией:
H1 (снят P2.14), **H2** (реопен не инвалидирует `## Phase Handoff` — рецидив, failure scenario уже
наступил: третий аудит запущен по протухшему блоку), **H3** (гейт литералов слеп к инлайн-литералу
`«план закрыт»` — регенерация EN прошла бы через слепое пятно), H4/H5/H6/H8/H12 (ложные числа в
bookkeeping'е — правит P2.18), H7/H9/H10/H13 (гигиена канона — правит P2.17).

**Решения владельца (2026-07-14):** D33 (`Context` manual = `continue`, enum из трёх) · D34 (реопен
инвалидирует Phase Handoff маркером `> УСТАРЕЛ` + узкий WARNING-гейт; 3 новых WARNING чужим планам
приняты как истинно-положительные → carve-out §2) · D35 (реестр `CANON_LITERALS` + AST-тест полноты)
· D36 (якорь дерева для чисел) · D37 (гейт item-формы, whitelist bootstrap `P0.0`) · D38
(`Last Updated` — правило без линтер-гейта).

**Remaining:** пять items P2 — порядок исполнения ≠ порядок номеров (D32):

1. **P2.15** (opus/high, ЗАПУСК ВРУЧНУЮ) — §3: 4-й шаг реопена (инвалидация Phase Handoff) + узкий
   WARNING-гейт в `plan_lint` + 3 теста. ← Next
2. **P2.16** (opus/high, manual) — реестр `CANON_LITERALS` + AST-тест полноты гейта литералов
   (**обязательно ДО P2.13**).
3. **P2.17** (opus/high, manual) — гигиена канона §6 (проза топологии, якоря F1/G2) + гейт
   item-формы заголовка handoff.
4. **P2.18** (sonnet/medium, `/task:plan-exec`) — bookkeeping-правда, третий заход
   (H4/H5/H6/H8/H12).
5. **P2.13** (opus/high, manual, **ТЕРМИНАЛЬНЫЙ — исполняется ПОСЛЕДНИМ**) — скилл 2.5.0 +
   регенерация EN-канона + `skiller registry`; только после него
   `packages/skiller/scripts/validate.sh` обязан быть ПОЛНОСТЬЮ зелёным.
6. Далее: `plan-audit P2` (четвёртый) → P3 (5 items: перенос правил в команды `/task:plan-*`) →
   P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.3.0, §2 Execution Rules
+ carve-out D34, §3 Routing, §5 D-лог D1–D38, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P2.md` (Completion Notes P2.1–P2.12 + P2.14, ТЗ P2.13 и P2.15–P2.18, три append-only блока
`## Audit P2` — третий несёт H1–H13 с командами-доказательствами; `## Phase Handoff` помечен
`> УСТАРЕЛ`) · `findings/P2-third-reopen-fleet-measurements.md` (замеры флота под новые гейты: H2 —
104 vs 4 попадания, H10 — 1 (bootstrap), H11 — 14; AST-скан литералов) · `phases/P3.md`,
`phases/P4.md` · SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` —
источник; `SKILL.md` — EN-канон, ПРОТУХ; `snippets/`) · `packages/task/lib/task/plan_lint.py`
(второй SSOT схемы) · `packages/skiller/scripts/check-translations.sh` (гейт литералов) ·
`packages/skiller/prompts/generate/claude-canon-from-ru.md`.

**Open risks:**
- **EN-канон `SKILL.md` по-прежнему ЛОМАЕТ линтер** (G3): несёт `Items 🟢/total`,
  `D# | Date | Decision | Why` — план, эмитенный по EN-канону, не парсится (5 ERROR). Чинит
  регенерация в **P2.13**; до тех пор `/task:plan-design` в проектах флота может эмитить невалидный
  Status Board.
- **Правил P2.9–P2.11 и P2.14–P2.17 в EN-каноне НЕТ:** агент грузит `SKILL.md`. До P2.13 новые
  правила (включая `Context` manual-item и якорь дерева, внесённые P2.14) обязывают только тех, кто
  читает RU-источник или этот план.
- **Слепое пятно гейта литералов ЖИВО до P2.16** (H3): регенерация EN, запущенная раньше, может
  тихо перевести `«план закрыт»` — и гейт останется зелёным. Порядок P2.16 → P2.13 обязателен.
- **Производный дрейф ожидаем и легален** (§6/D17): `packages/skiller/scripts/validate.sh` КРАСЕН
  (registry-drift `skills.json`/`budget.md` — **пре-существующий**, воспроизводится на чистом
  `0eebe4b`; `check-translations` — 5 ❌ протухшего EN + ⚠️ «EN протух» от правки P2.14). Полный
  зелёный требуется только на терминальном P2.13. Красное по любой ДРУГОЙ причине — блокер.
- **Три чужих плана флота получат новый WARNING** после P2.15 (VLT-REMED/P5, COREX-CORE/P1,
  2026.07.12-BASE/P5) — приняты владельцем как истинно-положительные (D34); их правка — вне scope.
- Правила фазы P2 попадают в SSOT, но команды `/task:plan-*` их ещё не исполняют (фаза P3; P3.3 уже
  дополнен чеклистом якоря дерева / протухшего Phase Handoff / `Last Updated`).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: тексты команд под новые enum'ы и топологию — фаза P3 (`plan-close.md:104`,
  `plan-exec.md:70,96`, `plan-audit.md:59,65`, `plan-design.md:22,85`); **раскатка директив
  `i18n-keep` на остальные локальные скиллы** (внешние гейт не видит by construction — у них EN
  канон upstream); миграция §3 Routing / `## Обсуждение` живых планов на канон-форму (back-compat);
  заполнение `## 7. Contracts` в живых планах (REGHUB — P4.2); правка `## Phase Handoff` трёх чужих
  планов (вне scope); кросс-репо push-уведомление (роадмап).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
