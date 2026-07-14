# HANDOFF — 2026-07-14 — after P2.12

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high»

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — терминальный item фазы: скилл 2.5.0 + регенерация EN-канона под НОВЫМ гейтом литералов (P2.11) — формулировки протокола = public contract для 26 живых планов флота, `/task:plan-exec` пинит sonnet и по собственному routing-гейту (P2.1) обязан такие items отклонять |
| Context | continue (/clear) — ручной item |
| Суть | Bump `plan-protocol` 2.4.0 → 2.5.0 (D31), регенерация `SKILL.md` из `SKILL.ru.md` промтом `claude-canon-from-ru.md` (несёт правило `i18n-keep`), штамп `check-translations.sh --stamp`, `skiller registry`. Терминальный: после него `packages/skiller/scripts/validate.sh` обязан быть ПОЛНОСТЬЮ зелёным |

```text
Голый промпт item'а — читать `plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md`, раздел
`### P2.13 — version 2.5.0 + регенерация EN-канона + registry (терминальный)` целиком
(Intent/Scope Included/Scope Excluded/Implementation Rules/Code Guidance/Validation) —
Exec = manual (§9 Routing), команды `/task:plan-exec` для этого item'а не существует.
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2: items P2.1–P2.12 закрыты (11 🟢 + P2.4 🟠),
фаза 🟡 (второй реопен, D31) — остаётся P2.13 (терминальный).

**P2.12** (`7bbeb76`) — закрыты G4/G5/G6/G8 (bookkeeping-правда по git-фактам):

- **G5** — `plan.md` Update Log, строка `plan-close`: несла невалидный числитель Status Board
  (числитель ≠ фактическому счётчику 🟢 — линтер такое отвергает ERROR'ом). Факт `git show
  0c976a3 -- plan.md`: числитель борда НЕ менялся, менялся только статус (🟡→🟠). Строка
  исправлена на фактическое значение; факт правки зафиксирован НОВОЙ строкой Update Log
  (append-only не нарушен).
- **G6** — Completion Notes P2.7 отчитывались о понижении числителя борда, которого в
  `git show 4cb9b77 -- plan.md` нет (диф борда в коммите отсутствует). Заменено на честное:
  правки не было и она не требовалась (на момент item'а `🟢`-items было ровно 6, борд был верен).
- **G4** — карта «коммит → item» (записанная P2.11) сверена по `git log -1 --format='%h %s'`
  для всех 20 коммитов фазы — расхождений не найдено, карта уже верна (см. таблицу ниже).
- **G8** — `tail -1 handoff.md` уже содержательная строка — расхождения не было, правка не
  потребовалась.
- Топология — ДВА коммита (D26): item-коммит `7bbeb76` (G5/G6, по путям `plan.md`+`phases/P2.md`),
  bookkeeping-коммит несёт Status/Phase Status/Board/Update Log/Completion Notes P2.12.

Карта «коммит → item» (сверена `git log`, 2026-07-14, P2.12):

| Item | Item-коммит | Bookkeeping/фикс |
|:--|:--|:--|
| P2.1 §9 routing-гейт | `38954ab` | — |
| P2.2 §6 status-rule | `cd749ab` | — |
| P2.3 §4/§11 Contracts + линтер | `1451ed9` | — |
| P2.4 snippets + EN-канон 2.3.0 (🟠, D21/D22) | `365079c` | — |
| реопен №1 по RED-аудиту (plan-design, D21–D25) | `c90b5fb` | — |
| P2.5 §6 коммит-гигиена + 6-й триггер | `4a4af60` | `9f3ec28` (реальный хеш вместо плейсхолдера) |
| P2.6 §3/§4 носитель развилок (D23) | `d17ad8c` | — |
| P2.7 ремедиация плана по аудиту | `4cb9b77` | `6501ea8` (handoff) |
| P2.8 EN-канон 2.4.0 + реестр | `bef52c7` | `620ef0d` (handoff) |
| закрытие фазы P2 (plan-close) | `0c976a3` | — |
| реопен №2 по RED-аудиту №2 (plan-design, D26–D31) | `270d460` | — |
| P2.9 §6/§8 топология + carve-out (D26/D27) | `3f70d2c` | `41b2049` |
| P2.10 §7/§8 RAG:— + after Pn + Context (D29/D30) | `f33a6cc` | `475a094` |
| P2.11 гейт литералов EN + фикс `--stamp` (D28) | `4a0e6f6` | `5e6fa36` |
| **P2.12 bookkeeping-правда по git-фактам (G4/G5/G6/G8)** | **`7bbeb76`** | bookkeeping — этой сессией |

**Remaining:**
- **P2.13** (opus/high, ЗАПУСК ВРУЧНУЮ, терминальный) — скилл 2.5.0 + регенерация EN-канона
  **под новым гейтом литералов** + `skiller registry`; только после него
  `packages/skiller/scripts/validate.sh` обязан быть ПОЛНОСТЬЮ зелёным. Гейт теперь ТРЕБУЕТ
  верных шапок: регенерация, потерявшая литерал, не пройдёт (в этом и был смысл P2.11). ← Next
- Далее: повторный `plan-audit P2` → P3 (5 items: перенос правил в команды `/task:plan-*`) →
  P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.2.0, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D31, `## Обсуждение` — 6 развилок со статусами) · `phases/P2.md`
(Completion Notes P2.1–P2.12, ТЗ P2.13, два append-only блока `## Audit P2` — второй несёт
G1–G13 с командами-доказательствами) · `phases/P3.md`, `phases/P4.md` (ТЗ следующих фаз) ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник, несёт
правила P2.9–P2.11 и блок `i18n-keep`; `SKILL.md` — EN-канон, ПРОТУХ; `snippets/`) ·
`packages/task/lib/task/plan_lint.py` (второй SSOT схемы — ИСТОЧНИК списка литералов) ·
`packages/skiller/scripts/check-translations.sh` (гейт) ·
`packages/skiller/prompts/generate/claude-canon-from-ru.md` (правило переноса).

**Open risks:**
- **EN-канон `SKILL.md` по-прежнему ЛОМАЕТ линтер** (G3): несёт `Items 🟢/total`,
  `D# | Date | Decision | Why` — план, эмитенный по EN-канону, не парсится (5 ERROR). P2.11 поставил
  ГЕЙТ (расхождение стало громко-красным, а не тихим), но само расхождение чинит регенерация в
  **P2.13** — до тех пор `/task:plan-design` в проектах флота может эмитить невалидный Status Board.
- **Правил P2.9–P2.11 в EN-каноне ещё НЕТ:** агент грузит `SKILL.md`, а он несёт прежнюю
  одно-коммитную §6 без carve-out, два RAG-маркера и одну форму заголовка handoff. До P2.13 новые
  правила обязывают только тех, кто читает RU-источник или этот план.
- **Производный дрейф ожидаем и легален** (§6/D17): `packages/skiller/scripts/validate.sh` КРАСЕН —
  сперва на registry-drift (`skills.json`, `docs/guide/budget.md` — наследие правки снипетов в P2.10;
  воспроизводится на чистом HEAD), затем на `check-translations` (протухший EN + 5 недостающих
  литералов). Оба — производные артефакты; полный зелёный требуется только на терминальном P2.13
  (он несёт и регенерацию EN, и `skiller registry`). Красное по любой ДРУГОЙ причине — блокер.
- **Форма `after Pn.m` не гейтится существованием item'а** (осознанно — P2.10 Known Deviations):
  12 планов флота несут `after P0.0` при отсутствующем item'е. Резолвится только фазовая форма.
- Правила P2.9–P2.11 попадают в SSOT, но команды `/task:plan-*` их ещё не исполняют (фаза P3).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.
- **P2.12 Known Deviations:** устаревшие числа в собственном ТЗ P2.12 — Validation (4) ожидала
  борд `7/13`, факт `11/13` (K=0 в обоих случаях); Validation (6) ожидала 0 попаданий строки о
  понижении числителя из G6 вне
  блока аудита, факт 3 (все — пре-существующий текст самого ТЗ P2.12, не новая ложь). Не блокер,
  не требует правки — правка спеки Scope Excluded.

**Workarounds/Deferred/Open questions:**
- workarounds: нет. Обходка `check-translations.sh --stamp` (дописывал второй маркер вместо замены
  `PENDING`) ЗАКРЫТА фиксом в P2.11 — при регенерации EN в P2.13 маркер руками чинить не нужно.
- deferred: тексты команд под новые enum'ы — фаза P3, поимённо в Pending Work P2.9/P2.10
  (`commands/plan-close.md:104` несёт запрещённую D16 статику `Context`; `plan-exec.md:70,96`;
  `plan-audit.md:59,65`; `plan-design.md:22,85`; топологию двух коммитов и источник хеша для handoff
  команды тоже ещё не несут); **раскатка директив `i18n-keep` на остальные 215 скиллов** (механизм
  универсален, применён пока только к `plan-protocol` — Scope Excluded P2.11); миграция §3 Routing /
  `## Обсуждение` живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых
  планах (REGHUB — P4.2); кросс-репо push-уведомление (роадмап).
- open_questions: все шесть развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
