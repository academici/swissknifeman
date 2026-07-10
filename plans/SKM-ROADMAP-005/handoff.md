# HANDOFF — 2026-07-10 — after P1.0

**Next:** /task:plan-exec SKM-ROADMAP-005 P1.1

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session |
| Суть | Ядро settings-doctor в harness: загрузчик 4 слоёв настроек CC + эффективная конфигурация с провенансом |

````
/task:plan-exec SKM-ROADMAP-005 P1.1 — исполнить item строго по ТЗ. Cold-start reads: plans/SKM-ROADMAP-005/plan.md · plans/SKM-ROADMAP-005/phases/P1.md (Phase Context + item P1.1 целиком) · plans/SKM-ROADMAP-005/findings/P1-cc-settings-facts.md · packages/harness/CLAUDE.md. Дом движка — packages/harness (D10). stdlib-only, doctor read-only. Факты [UNVERIFIED] (семантика additionalDirectories, полнота hook-событий) не «додумывать» — обходить дизайном по D15.
````

**Done:** Фаза P1 развёрнута из скелета: 6 items с полными ТЗ (16 полей каждый, Code Guidance
заполнен), Scope Included/Excluded фазы, DoR-чеклист пройден (0 маркеров `[NEEDS CLARIFICATION]`).
Три развилки закрыты владельцем → D10 (дом движка — harness, уточняет D8), D11 (декларация
профиля — `.swissknife.json:policy_profile`), D12 (opt-in хук вне scope). Пере-сверка внешних
фактов (проход 2 + эмпирика `package.json` расширения 2.1.206) → D13/D14/D15, выжимка дописана
в `findings/P1-cc-settings-facts.md`. D16 — канон имён планов `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ`, внедряется
в P4 (отмечен в его Phase Context).

**Remaining:** P1 — 6 items к исполнению (P1.1 ядро → P1.2 проверки 1–3,5,9 → P1.3 профили +
проверки 4,11 → P1.4 CLI и фасад → P1.5 второй срез + VSCode → P1.6 fleet и закрытие фазы).
Фазы P2–P7 — скелеты, каждую разворачивать `/task:plan-design SKM-ROADMAP-005 Pn` ДО `plan-exec`:
P2 wf-status (5) · P3 workflow-craft (5) · P4 канон планов (6) · P5 changelog-discipline (3) ·
P6 ecosystem-glossary (4) · P7 ephemeral + закрытие пакета (2).

**Sources of truth:** plans/SKM-ROADMAP-005/plan.md (Meta, Routing, D-лог D1–D16) ·
plans/SKM-ROADMAP-005/phases/P1.md (ТЗ items) ·
plans/SKM-ROADMAP-005/findings/P1-cc-settings-facts.md (сверенные внешние факты + два `[UNVERIFIED]`) ·
roadmap/settings-doctor.md (спека, §Проблема = критерий интеграционного теста) ·
packages/harness/CLAUDE.md (SSOT окружения Claude Code) ·
packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола) ·
packages/task/lib/task/plan_lint.py (валидатор схемы)

**Open risks:**
- Доки Claude Code меняются между версиями CLI (сверка велась против 2.1.206). Снапшот
  `settings-keys.json` (P1.2) протухает — он несёт `verified`/`cli_version`, обновляется руками.
- Проверка №10 остаётся `info` по D3: соблазн «усилить» её до `warn` при исполнении — прямой
  путь к красному doctor'у на недокументированном ключе.
- P1.3 трогает публичный конфиг skiller (`CONFIG_KEYS` + `schema/swissknife.schema.json`) —
  расхождение двух ловится `test_schema.py` и `skiller doctor`; правятся одним коммитом.
- P1.6 зависит от контракта `--json` из P1.4: любой лишний `print` в stdout при `--json`
  роняет fleet-скан.

**Workarounds/Deferred/Open questions:**
- workarounds: семантика слияния `permissions.additionalDirectories` неизвестна → проверка №8
  работает per-layer, вердикт от семантики не зависит (D15); полнота списка hook-событий не
  подтверждена → неизвестное событие даёт `info`, не `warn`.
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12); авто-починка `--fix`; семантический
  glob-матчер перекрытий allow/deny; форки VSCode (Cursor/Insiders); `workflow-craft` ч.2,
  `skill-rules-sidecar`, остаток `self-learning-memory`, default-on `mcp-config-example-emit` (D1).
- open_questions: содержание «ephemeral-дисциплины» — снимается интервью владельца в P7.1 (D7).
