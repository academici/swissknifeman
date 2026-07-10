# HANDOFF — 2026-07-10 — after P1.6

**Next:** /task:plan-design SKM-ROADMAP-005 P2

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high |
| Context | fresh session |
| Суть | Развернуть фазу P2 (`wf-status`) из скелета: 5 items с полными ТЗ, Scope Included/Excluded, DoR-чеклист — ДО plan-exec |

````
/task:plan-design SKM-ROADMAP-005 P2 — развернуть фазу-скелет из плана: детализировать 5 items
(`wf-status` — консольный статус-репортер фоновых workflow-прогонов, `swissknifeman wf status`,
D8/D9 «новых пакетов не заводим», парсинг journal.jsonl+meta вместо LLM-импровизаций и совета
несуществующей `/workflows`). Cold-start reads: plans/SKM-ROADMAP-005/plan.md (Context, Routing
P2.1, D8) · plans/SKM-ROADMAP-005/phases/P2.md (скелет). P2.1 требует чтение реальной transcript-
директории (`~/.claude/projects/**/subagents/workflows/wf_*`) — источник истины формат, не доки.
````

**Done:** Фаза P1 (`settings-doctor`) закрыта 6/6 🟢. Движок в harness
(`lib/harness/settings_audit.py`, D10): 4 слоя настроек CC + эффективная конфигурация с
провенансом, таксономия 13 проверок, 2 policy-профиля (`max-permissive`/`base`) + декларация
`.swissknife.json:policy_profile`, CLI `harness doctor --settings [--target] [--json] [--profile]`
(exit-code 0/1/2), фасад `skiller doctor --settings`, VSCode-слой (JSONC-reader), интеграционный
fieldcase-тест (все 6 пунктов полевого кейса 2026-07-10 ловятся разом), fleet-измерение
`maind doctor --audit settings|all` (subprocess к harness, fail-soft). `roadmap/README.md` и
шапка `roadmap/settings-doctor.md` приведены к факту: `🟢 внедрено (SKM-ROADMAP-005 P1)`.
`CHANGELOG.md [Unreleased]` заполнен по каждому item'у. Реальный прогон `maind doctor --audit
settings` по флоту (21 проект) подтвердил рабочесть измерения.

**Remaining:** P2–P7 — скелеты, каждую разворачивать `/task:plan-design SKM-ROADMAP-005 Pn` ДО
`plan-exec`: P2 wf-status (5) · P3 workflow-craft (5) · P4 канон планов (6) · P5
changelog-discipline (3) · P6 ecosystem-glossary (4) · P7 ephemeral + закрытие пакета (2).

**Sources of truth:** plans/SKM-ROADMAP-005/plan.md (Meta, Routing, D-лог D1–D16) ·
plans/SKM-ROADMAP-005/phases/P1.md (закрыт, Phase Handoff заполнен — образец для P2–P7) ·
roadmap/README.md (статус settings-doctor приведён к факту) ·
packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола) ·
packages/task/lib/task/plan_lint.py (валидатор схемы)

**Open risks:**
- P1.4 Pending Work не закрыт: проверка №5 даёт ложный `error` на хук-командах с
  интерпретатор-префиксом (`bash …`, `python3 …`) — резолвится по первому токену. Вне scope P1,
  следующий срез или отдельное решение владельца.
- P1.6 Pending Work: `maind doctor --audit all` падает на измерении `core` (`_present_skills`,
  список вместо объекта в `skills-lock.json:skills` на части флота) — воспроизведено ДО диффа
  P1.6, вне scope (расширение `DIMS` запрещено ТЗ P1.6). `--audit settings` в изоляции не задет.
- D16 (канон имён планов `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`) внедряется в P4 — этот план (SKM-ROADMAP-005)
  НЕ переименовывается (back-compat, ломает git-историю/ссылки).

**Workarounds/Deferred/Open questions:**
- workarounds: семантика слияния `permissions.additionalDirectories` неизвестна → проверка №8
  работает per-layer, вердикт от семантики не зависит (D15); полнота списка hook-событий не
  подтверждена → неизвестное событие даёт `info`, не `warn`.
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12); авто-починка `--fix`; семантический
  glob-матчер перекрытий allow/deny; форки VSCode (Cursor/Insiders); P1.4/P1.6 Pending Work (выше);
  `workflow-craft` ч.2, `skill-rules-sidecar`, остаток `self-learning-memory`, default-on
  `mcp-config-example-emit` (D1).
- open_questions: содержание «ephemeral-дисциплины» — снимается интервью владельца в P7.1 (D7).
