# HANDOFF — 2026-07-13 — after P2.8

**Next:** `ЗАПУСК ВРУЧНУЮ: opus/high` — item **P2.9** (Exec = manual, §3 Routing).

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона протокола: формулировки = public contract для 26 планов флота |
| Context | continue (/clear) — ручной item |
| Суть | §6/§8 канона `plan-protocol`: закрепить ОДНУ топологию item-коммита (два коммита, D26) и вывести файлы плана из-под 6-го material-триггера (carve-out, D27) — сейчас два правила взаимоисключающи и по букве красят 🟠 почти весь флот |

`/task:plan-exec` этот item ОТКЛОНИТ (пин sonnet/medium < opus/high — routing-гейт §9).
Запускать вручную: `/model opus` + `/effort high`, затем промпт ниже.

```
Исполни item P2.9 мастер-плана plans/2026.07.13-PLAN-PROTOCOL-GAP строго по ТЗ:
plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P2.md → раздел «### P2.9». Сначала прочитай
Required Reads целиком, затем правь. Закрытие — по §8 канона (порядок закрытия item'а),
статус — по §6 (status-rule). Не выходи за Scope Included.
```

**Done:** P1 терминальна (`4c03715`, `b45cd51`). Items P2.1–P2.8 терминальны (7 🟢 + P2.4 🟠),
но **фаза P2 РЕОПЕНЕНА второй раз** (D31) — повторный `plan-audit` дал 🔴 RED (6 Major).
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

Этой сессией (`/task:plan-design`, реопен №2): `plan.md` 1.1.0 → **1.2.0**, фаза P2 `🟠 → 🟡`,
Status Board `7/13`, D26–D31, две новые развилки в `## Обсуждение` (топология коммита; RAG:—);
`phases/P2.md` — ТЗ пяти items **P2.9–P2.13**. Здесь же сняты Nit'ы аудита G12 (D4: «7 форм» → 8)
и G13 (суффикс в заголовке `## Обсуждение`).

**Remaining:** (строгий порядок)
- **P2.9** (opus/manual) — §6/§8: одна топология item-коммита (D26) + carve-out плановых путей (D27). ← Next
- **P2.10** (opus/manual) — §7/§8: маркер `RAG:—` (D29), форма заголовка `after Pn`, третье значение
  `Context` (D30) + `plan_lint.py` + снипеты + тесты.
- **P2.11** (opus/manual) — гейт непереводимых литералов EN (D28) в `check-translations.sh` + промт
  генератора + фикс `--stamp`.
- **P2.12** (sonnet, `plan-exec`) — bookkeeping-правда плана по git-фактам (G4/G5/G6/G8).
- **P2.13** (opus/manual, терминальный) — скилл 2.5.0 + регенерация EN-канона + registry;
  только после него `packages/skiller/scripts/validate.sh` обязан быть ПОЛНОСТЬЮ зелёным.
- Далее: повторный `plan-audit P2` → P3 (5 items: перенос правил в команды `/task:plan-*`) →
  P4 (3 items: регресс по флоту, закрытие эскалации REGHUB, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta 1.2.0, §2 Execution Rules,
§3 Routing, §5 D-лог D1–D31, `## Обсуждение` — 6 развилок со статусами) · `phases/P2.md`
(Completion Notes P2.1–P2.8, ТЗ P2.9–P2.13, два append-only блока `## Audit P2` — второй несёт
G1–G13 с командами-доказательствами) · `phases/P3.md`, `phases/P4.md` (ТЗ следующих фаз) ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` 2.4.0 — источник;
`SKILL.md` — EN-канон; `snippets/`) · `packages/task/lib/task/plan_lint.py` (второй SSOT схемы).

**Open risks:**
- **EN-канон `SKILL.md` сегодня ЛОМАЕТ линтер** (G3): предписывает шапки `Items 🟢/total`,
  `D# | Date | Decision | Why`, а `plan_lint.py` сверяет русские байт-в-байт. План, эмитенный по
  EN-канону, не парсится (5 ERROR). Чинится P2.11 (гейт) + P2.13 (регенерация) — до тех пор
  `/task:plan-design` в проектах флота может эмитить невалидный Status Board.
- **Производный дрейф ожидаем и легален** (§6/D17): после P2.9–P2.11 `packages/skiller/scripts/
  validate.sh` будет КРАСНЫМ на `check-translations` (EN устарел) — полный зелёный требуется
  только на терминальном P2.13. Красное по любой ДРУГОЙ причине — блокер.
- Правила P2.9–P2.11 попадут в SSOT, но команды `/task:plan-*` их ещё не исполняют (фаза P3).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: обходка `check-translations.sh --stamp` (дописывает второй маркер вместо замены
  `PENDING`) — БОЛЬШЕ НЕ обходка: фикс включён в Scope P2.11 (решение владельца по G11).
- deferred: миграция §3 Routing / `## Обсуждение` живых планов на канон-форму (back-compat);
  заполнение `## 7. Contracts` в живых планах (REGHUB — P4.2); кросс-репо push-уведомление
  (роадмап); раскатка директив `i18n-keep` на остальные 215 скиллов (механизм универсален,
  применяется пока только к `plan-protocol`).
- open_questions: все шесть развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
