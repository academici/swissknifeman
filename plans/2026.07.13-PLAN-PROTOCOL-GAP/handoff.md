# HANDOFF — 2026-07-13 — after P1.2

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — P2.1 (`plan.md` §3 Routing: P2.1–P2.4 = opus/high,
Exec = manual; `/task:plan-exec` пинит sonnet/medium и по своему собственному будущему
routing-гейту, P2.1 сам, обязан такие items отклонять — не запускать через `/task:plan-exec`)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка SSOT-канона протокола экосистемы (26 живых планов флота), public-contract-класс формулировок; `plan.md` §3 Routing и §9 SSOT-матрицы MANDATORY high+ |
| Context | continue (/clear) — ручной item (не Workflow-оркестрован: items P2 делят один файл `SKILL.ru.md`, строго последовательно) |
| Суть | Дописать в `SKILL.ru.md` §9 канон-форму строки Routing (колонка Exec) + правило деривации Exec + routing-гейт (F7) |

````
Запусти вручную под opus/high (НЕ /task:plan-exec — Exec=manual): исполни item P2.1
плана 2026.07.13-PLAN-PROTOCOL-GAP по протоколу plan-exec (packages/skiller/skills/general/
plan-protocol/SKILL.ru.md §8-11) — прочитай plan.md (Context, Execution Rules, §3 Routing,
D-лог), phases/P2.md (Phase Context + item P2.1 целиком), закрой item по каноническому
порядку закрытия (дифф → validate → bookkeeping → handoff → plan-lint ПОСЛЕ handoff → коммит).
````

**Done:** P1 терминальна (P1.1 🟢 коммит `4c03715`, P1.2 🟢 коммит `b45cd51`). P1.1: enum 8 форм
`handoff.Next` + канонический порядок закрытия item'а в `SKILL.ru.md` §8, резолвер форм в
`plan_lint.py`, `discover_plan_dirs` больше не линтит `plans/archive/` как план (N3/D14). P1.2:
`plan-lint --baseline [REF]`/`--gate {all,new}` — детерминированный счёт K новых ошибок от
рабочего дерева (git archive baseline-дерева во временный каталог, сравнение по нормализованному
ключу `(kind, отн_путь, msg)` без номера строки, graceful degrade без git). Тесты
`packages/task`: 85 → 100 (P1.1) → 104 (P1.2), все зелёные. `bash packages/task/scripts/validate.sh`
→ OK, 0 ошибок. Репро REGHUB: `plan-lint plans/REGHUB --baseline HEAD` →
`ПРОВАЛ (1 план(ов), 78 ошибок, 4 предупреждений; новых от рабочего дерева: 0)`. Регресс по 9
корням флота — ноль отклонений от замера после P1.1. Полные детали —
`phases/P1.md` P1.1/P1.2 Completion Notes.

**Remaining:** P2 (4 items, opus/high, manual — canon routing-gate/status-rule/Contracts/
EN-регенерация) → P3 (4 items, sonnet/medium, команды plan-*) → P4 (3 items — регресс по
флоту, REGHUB эскалация в чужом репо, доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, Execution Rules, §3
Routing, D-лог) · `phases/P1.md` (P1.1/P1.2 Completion Notes) · `phases/P2.md` (P2.1 ТЗ, уже
детализирован) · `findings/P0-protocol-gap-recon.md` · SSOT-цели:
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md`, `packages/task/lib/task/plan_lint.py`.

**Open risks:**
- Фаза P2 — правка SSOT-канона протокола: формулировки = public contract для 26 живых планов
  флота. Ошибка здесь тиражируется на весь флот при следующей `plan-design`/`plan-exec` сессии
  любого плана. opus/high и ручной запуск — не формальность.
- P2.1 сам вводит routing-гейт, которым потом проверяются P2.2–P2.4 и все будущие items —
  до P2.1 закрытого `/task:plan-exec` этот гейт не существует нигде (ни в SSOT, ни в команде).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там, отдельный, вне этого
  репо.
- Внутри `plans/archive/` (swissknifeman: чисто; vaulter: VLT-CANON/VLT-REMED несут новые
  ERROR/WARNING, впервые пролинтованы P1.1) — вне Scope этого плана, архивные планы не
  переоткрываем.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: кросс-репо push-уведомление о bump'е контракта (роадмап, вне scope); миграция §3
  Routing 26 живых планов на канон-форму с колонкой Exec (back-compat: старые формы валидны).
- open_questions: развилки `plan.md` §Обсуждение (авто-делегация в Workflow, релакс ERROR→WARNING
  на скелетах) — обе отклонены D-логом, возражение владельца перебивает новым D# со `supersedes`.
