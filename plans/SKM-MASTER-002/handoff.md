# HANDOFF — 2026-07-02 — after P5.5

**Next:** /task:plan-exec SKM-MASTER-002 P3.1 (волна 2: фазы C и F стартуют)
**Done:** волна 1 исполнена и реконсилирована по фактам (все validate.sh зелёные): P1.1–P1.7
(скилл plan-protocol RU+EN, plan-lint + тесты, validate.sh task, bootstrap plans/, 4 команды
/task:plan-*, plugin.json+registry); P2 целиком (core/usage.py, хук run-report SCHEMA=2 +
вендоринг _usage.py, skiller analyze-run на core.usage, maind analyze tokens-блок vs медиана,
harness doctor свежесть хука) — фаза закрыта 🟢 Done, Phase Handoff в phases/P2.md заполнен;
P5.1–P5.5 (provenance headers, lock_drift+doctor --drift, pack_drift в maind, _common
rules/generated-assets.md, ось generated-core-edited в 4 стек-паках + patch-bump) — P5.5 закрыта
🟠 Done with deviations (per-pack CHANGELOG не обновлены).
**Remaining:** P1.8–P1.10 (пилотный exec→audit цикл, point-расширения 3 скиллов, cold-start
валидация); P5.6–P5.7 (опц. pack-guard хук, docs+CHANGELOG фазы E); волна 2 — P3 (после P2,
теперь разблокирована) и P6 (после P5, частично разблокирована — P5.1–P5.5 готовы, P5.6/P5.7
не блокируют старт); волна 3 — P4 (после P2+P3) и P7; волна 4 — P8.
**Sources of truth:** plans/SKM-MASTER-002/plan.md · plans/SKM-MASTER-002/phases/P1.md–P8.md ·
скилл packages/skiller/skills/general/plan-protocol/ · валидатор packages/task/scripts/plan-lint.py
**Open risks:** CHANGELOG deny-правило — обновления per-pack CHANGELOG.md паков в P5.5 пропущены
из-за permission deny окружения, нужно вернуться и закрыть точечно; sonnet «дорисовывает» план
при расхождении с кодом (купируется запретом+эскалацией+audit, ещё не проверено на живом
цикле — P1.8); CLAUDE_PLUGIN_ROOT вне plugin-контекста (fallback warning + прямой путь в
plans/README.md); поведение effort-пина для haiku в Claude Code не проверено.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: per-pack CHANGELOG.md 4 стек-паков (P5.5, вернуться отдельным точечным item);
  пилотный цикл exec→audit (P1.8) и cold-start валидация (P1.10) — после старта волны 2;
  `none_of` в pack detect — проверить при P6.4; body_path в upstream-схеме — сверить при P7.3.
- open_questions: —
