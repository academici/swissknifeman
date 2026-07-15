# HANDOFF — 2026-07-15 — after P4.1

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high»

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — чужой замороженный контекст (Brain-vault, REGHUB) + суждение о статусах эскалации (§3 Routing P4.2) |
| Context | continue (/clear) — ручной item |
| Суть | P4.2: закрыть эскалацию REGHUB (5 пунктов `open-questions.md` → `Resolved → D#`) + дозаполнить 8 скелет-items `phases/P3.md` (16 полей) + секция `## 7. Contracts / Exported`; коммит В ДРУГОМ РЕПО (Brain-vault) |

````
Ты исполняешь item P4.2 мастер-плана 2026.07.13-PLAN-PROTOCOL-GAP (репо swissknifeman) —
ЗАПУСК ВРУЧНУЮ (Exec = manual, opus/high, §3 Routing): чужой замороженный контекст (Brain-vault,
план REGHUB) + решения о статусах — не для дешёвой модели.

Прочитай (в этом порядке, ничего сверх):
1) /home/vostrikov/projects/packages/swissknifeman/plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P4.md
   — раздел "### P4.2 — REGHUB: закрыть эскалацию + дозаполнить скелет P3" целиком (Intent, Why,
   Scope Included/Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance,
   Validation, Deliverables);
2) /home/vostrikov/projects/packages/swissknifeman/plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md
   §5 Decision Log D1–D12 (источник D# для ссылок в open-questions.md REGHUB);
3) /home/vostrikov/Vaults/Brain/plans/REGHUB/open-questions.md §Процессные (целиком, 127 строк);
4) /home/vostrikov/Vaults/Brain/plans/REGHUB/phases/P3.md (8 скелет-items);
5) /home/vostrikov/Vaults/Brain/plans/REGHUB/plan.md §2 Execution Rules и §5 Decision Log
   (D21/D22 — решения владельца, НЕ переигрывать).

Исполни Scope Included P4.2 (см. phases/P4.md), прогони Validation (4 команды из ТЗ), закрой item
ПОЛНЫМ протоколом закрытия (§7 команды plan-exec): коммит В BRAIN-VAULT отдельно (префикс
`docs(reghub):`), затем bookkeeping ЭТОГО плана (Status/Completion Notes/Pending
Work/Known Deviations/Phase Status/Status Board/Update Log/Last Updated) — со ссылкой на sha
коммита Brain — коммит в swissknifeman, перезапись handoff.md, `plan-lint --baseline HEAD` после
handoff, счёт с атрибуцией K.

Работа в swissknifeman-репо этим item'ом диффа НЕ оставляет, кроме bookkeeping плана.
````

**Done:** P1 (2/2 🟢), P2 (18/18 — терминальна, `🟠 Done with deviations`), P3 (11/11 —
терминальна, `🟠 Done with deviations`, 2-й и 3-й заход аудита завершены — AUDIT-CAP, `## Audit P3`
в `phases/P3.md`, реопен не назначен). **P4.1 закрыт 🟢 (`4922ddc`)**: парный regression-замер
`plan-lint` по **10 корням / 30 планам** (D53) — **ноль новых ERROR/WARNING** вне двух объяснённых
классов (archive/ впервые линтуется — N3/D14 расширение покрытия; message-rewording пары D14 —
идентичный текст поля скелета репортится другой формулировкой, net 0, построчно проверено `comm`).
Собственные фиксы кластера видны как чистое снижение ERROR: swissknifeman 4→0, corex 1→0,
agelto 9→7 (сняты 2 фантомные `plans/archive/*`, N3), Brain 86→84. Отчёт —
`findings/P4-regression-flotilla.md`.

**Remaining:**
1. **P4.2 ← Next** (opus/high, ЗАПУСК ВРУЧНУЮ) — закрыть эскалацию REGHUB в её SSOT
   (`open-questions.md` §Процессные → `Resolved → D#`), дозаполнить 8 скелет-items `phases/P3.md`
   (16 полей, «—»), заполнить `## 7. Contracts / Exported` (6 контрактов, версии сверить с
   баннерами `root/contracts/*.md`). Коммит в Brain-vault отдельно от bookkeeping swissknifeman.
2. Затем **P4.3** (sonnet/low, `plan-exec`) — `CHANGELOG.md` (`plan-protocol` 2.4.0 → 2.7.0, итог
   кластера), `docs/task/plan-structure.md`, `docs/reference.md`, `docs/rejected-optimizations.md`.
   После P4.3 — фаза P4 терминальна, план близок к архивации (`plan-close archive`, после
   `plan-audit P4`, если потребуется по канону).

**Sources of truth:** `plan.md` (Meta **1.5.0**, Status 🟡, §3 Routing, §5 D-лог **D1–D57**,
`## Обсуждение`) · `phases/P4.md` (P4.1 🟢, P4.2/P4.3 ⬜) · `phases/P3.md` (11 терминальны,
`## Audit P3` — 3 захода, AUDIT-CAP) · `open-questions.md` (**OQ-1** — Decision pending, долг
владельцу, не в Scope P4) · `findings/P4-regression-flotilla.md` (регресс 10/30, метод, команда
воспроизведения) · `findings/P3-reopen-gates-and-fleet.md` (§2 инвентарь флота, источник D53) ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md`/`SKILL.md` **2.7.0**) ·
`packages/task/lib/task/plan_lint.py` · команды `plan-{exec,close,audit,design,run}`.

**Open risks:**
- **OQ-1 (Decision pending)** — дедлайн «до закрытия P3» прошёл неснятым (J16: канон §6 не знает
  «мягкого пункта Validation»). Вне Scope P4.1; маршрут — владелец/`plan-design`, не блокирует P4.2/P4.3.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, REGHUB) — коммит там отдельный, вне git-истории
  swissknifeman; сверять версии контрактов с баннерами `root/contracts/*.md`, не по памяти (класс B1).
- Остаточные WARN `plan-lint` по флоту (Brain, vaulter, themeon, agelto) — вне Scope P4.1
  (архив-покрытие впервые + рост живых планов не диффом этого плана); не блокер.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: см. предыдущий handoff (принятый долг аудита №4 P2, миграция §3 Routing живых планов,
  CLI-ступень `plan-lint --conflicts`, кросс-репо push-уведомление — роадмап); CHANGELOG/доки — P4.3.
- open_questions: **OQ-1** (`open-questions.md`) — «мягкий пункт Validation», Decision pending,
  дедлайн прошёл, эскалирован в Open risks.
