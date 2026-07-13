# HANDOFF — 2026-07-13 — after P2.9

**Next:** `ЗАПУСК ВРУЧНУЮ: opus/high` — item **P2.10** (Exec = manual, §3 Routing).

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона + второго SSOT (линтер): формулировки = public contract для 26 планов флота |
| Context | continue (/clear) — ручной item |
| Суть | §7/§8 канона `plan-protocol`: канонизировать третий RAG-маркер `RAG:—` (D29), форму заголовка handoff `after Pn` для закрытия фазы (G10) и третье значение поля `Context` (D30) + синхронно `plan_lint.py` и `snippets/` |

`/task:plan-exec` этот item ОТКЛОНИТ (пин sonnet/medium < opus/high — routing-гейт §9).
Запускать вручную: `/model opus` + `/effort high`, затем промпт ниже.

```
Исполни item P2.10 мастер-плана plans/2026.07.13-PLAN-PROTOCOL-GAP строго по ТЗ:
plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md → раздел «### P2.10». Сначала прочитай
Required Reads целиком, затем правь. Закрытие — по §8 канона (порядок закрытия item'а),
статус — по §6 (status-rule). Не выходи за Scope Included.
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). P2: items P2.1–P2.9 закрыты (8 🟢 + P2.4 🟠),
фаза 🟡 (второй реопен, D31) — остаются P2.10–P2.13. **P2.9** (`3f70d2c`): `SKILL.ru.md` §6/§8 —
ДВА коммита объявлены ЕДИНСТВЕННОЙ топологией item'а (item-коммит по путям `Files` → bookkeeping-коммит
по путям плана; handoff берёт РЕАЛЬНЫЙ хеш из item-коммита, плейсхолдер = дефект; бандл —
process-отклонение, покупаемое чинящим коммитом) + carve-out D27 в 6-м material-триггере
(«дифф вне `Files`» считается только по НЕплановым путям). G1/G2 сняты в SSOT-источнике; EN-канон
их ещё НЕ несёт (регенерация — P2.13).

Карта «коммит → item» (сверена `git log`, 2026-07-13):

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
| **P2.9 §6/§8 топология + carve-out (D26/D27)** | **`3f70d2c`** | bookkeeping — этой сессией |

> Строки P2.5–P2.7 несут искажения, зафиксированные аудитом (G4) — их ремедиация принадлежит
> **P2.12**; здесь перенесены как есть, чтобы одна находка не чинилась двумя items.

**Remaining:** (строгий порядок)
- **P2.10** (opus/manual) — §7/§8: маркер `RAG:—` (D29), форма заголовка `after Pn`, третье значение
  `Context` (D30) + `plan_lint.py` + снипеты + тесты. ← Next
- **P2.11** (opus/manual) — гейт непереводимых литералов EN (D28) в `check-translations.sh` + промт
  генератора + фикс `--stamp`.
- **P2.12** (sonnet, `plan-exec`) — bookkeeping-правда плана по git-фактам (G4/G5/G6/G8).
- **P2.13** (opus/manual, терминальный) — скилл 2.5.0 + регенерация EN-канона + registry;
  только после него `packages/skiller/scripts/validate.sh` обязан быть ПОЛНОСТЬЮ зелёным.
- Далее: повторный `plan-audit P2` → P3 (5 items: перенос правил в команды `/task:plan-*`) →
  P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.2.0, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D31, `## Обсуждение` — 6 развилок со статусами) · `phases/P2.md`
(Completion Notes P2.1–P2.9, ТЗ P2.10–P2.13, два append-only блока `## Audit P2` — второй несёт
G1–G13 с командами-доказательствами) · `phases/P3.md`, `phases/P4.md` (ТЗ следующих фаз) ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник, уже несёт
правила P2.9; `SKILL.md` — EN-канон, ПРОТУХ; `snippets/`) · `packages/task/lib/task/plan_lint.py`
(второй SSOT схемы).

**Open risks:**
- **EN-канон `SKILL.md` сегодня ЛОМАЕТ линтер** (G3): предписывает шапки `Items 🟢/total`,
  `D# | Date | Decision | Why`, а `plan_lint.py` сверяет русские байт-в-байт. План, эмитенный по
  EN-канону, не парсится (5 ERROR). Чинится P2.11 (гейт) + P2.13 (регенерация) — до тех пор
  `/task:plan-design` в проектах флота может эмитить невалидный Status Board.
- **Правил P2.9 в EN-каноне ещё НЕТ:** агент грузит `SKILL.md`, а он несёт прежнюю одно-коммитную
  §6 без carve-out. До P2.13 топология D26/D27 обязывает только тех, кто читает RU-источник или
  этот план.
- **Производный дрейф ожидаем и легален** (§6/D17): `packages/skiller/scripts/validate.sh` КРАСЕН на
  `check-translations` (EN устарел) — полный зелёный требуется только на терминальном P2.13.
  Красное по любой ДРУГОЙ причине — блокер.
- Правила P2.9–P2.11 попадают в SSOT, но команды `/task:plan-*` их ещё не исполняют (фаза P3).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: обходка `check-translations.sh --stamp` (дописывает второй маркер вместо замены
  `PENDING`) — БОЛЬШЕ НЕ обходка: фикс включён в Scope P2.11 (решение владельца по G11).
- deferred: команды `/task:plan-exec` (`commands/plan-exec.md:54-59`) и `/task:plan-close`
  (`commands/plan-close.md:29-35`) пересказывают коммит-гейт §6, но топологию двух коммитов и
  источник хеша для handoff не несут — фаза P3 (Pending Work P2.9); миграция §3 Routing /
  `## Обсуждение` живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых
  планах (REGHUB — P4.2); кросс-репо push-уведомление (роадмап); раскатка директив `i18n-keep` на
  остальные 215 скиллов (механизм универсален, применяется пока только к `plan-protocol`).
- open_questions: все шесть развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
