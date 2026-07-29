# HANDOFF — 2026-07-29 — after P6

**Фаза P6 закрыта `🟠 Done with deviations`** (все три items терминальны: P6.1 🟢 · P6.2 🟠 ·
P6.3 🟠). Сдано: statusline context-notify в `harness` (opt-in, доки
`docs/configs/statusline.md`, P6.1); 4 дельты compact-дисциплины в `general/context-economy` +
`general/compact-responses` (P6.2); 3 дельты anti-overconfidence в `general/verify-claims` +
аддитивный абзац `CLAUDE.md` + 3 pressure-сценария + анкерованная спека DoR-пункта, потреблённая
P2.3 по D81 (P6.3). Docs-sync: обновлено P6.1 (`docs/configs/statusline.md` + индекс/сайдбар);
P6.2/P6.3 доставляются через `skiller registry` (тела скиллов реестра), не через `docs/`.
Детали — `phases/P6.md` Phase Handoff и Completion Notes items.

**Известные отклонения (агрегат, собран механически из Known Deviations items):**
- P6.2: item-коммит несёт дифф вне `Files` — `packages/skiller/docs/guide/budget.md`,
  `adapters/codex/core/publication-lock.json` и codex-зеркала правленых `SKILL.md`
  (детерминированный продукт `skiller registry`).
- P6.3 (material): `skiller eval` вернул 6/7 — красный `pressure#2` пре-существующий
  (коммит `34ae85f1`, вне Scope P6.3), не почищен этим item'ом.
- P6.3 (process): Validation ТЗ несла несуществующие флаги CLI `skiller eval` — прогнан
  функционально эквивалентный `skiller eval general/verify-claims`.
- P6.3 (process): чистый прирост тела RU-источника ~17 строк против ориентира «~15».

**Next:** фаза закрыта с deviations (🟠 на двух из трёх items) — по правилу launch-block'а
«была хоть одна 🟠/эскалация → сперва `plan-audit`» следующий шаг — адверсариальный аудит
фазы P6, не сразу exec следующего item'а.

| Параметр | Значение |
|:--|:--|
| Model | opus — пин `/task:plan-audit` |
| Thinking | xhigh — пин команды (adversarial-аудит закрытой фазы) |
| Context | NEW SESSION — шаг-не-item |
| Суть | Adversarial-аудит закрытой фазы P6: сверка 🟢/🟠 с кодом/git, no-op, scope drift, handoff |

```
/task:plan-audit 2026.07.25-ECO-OPT P6
```

**Done:** **52/52 items в затронутых фазах терминальны в P1–P6, P8–P11** (счёт items не
меняется закрытием фазы). Закрыты фазы **P1** (1/2, 🟢), **P2** (1/3, 🟠), **P3** (2/6, 🟠),
**P4** (3/3, 🟠), **P5** (5/6, 🟠), **P6** (3/3, 🟠 — этот заход), **P8** (7/10, 🟠), **P9**
(3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). Фаза **P7** не начата (0/3, ⬜).

**Remaining:** 3 items: P7.1–P7.3 (порядок `P7.1 + P7.3 → P7.2`, все `Exec = manual`;
кандидаты dogfood P7.1 по roadmap — P8.7 · P1.2 · P3.2, статус сверить перед прогоном).
Плюс аудит `/task:plan-audit 2026.07.25-ECO-OPT P6` (этот handoff) и, по прежней очереди,
`/task:plan-audit 2026.07.25-ECO-OPT P2` (не выполнен предыдущим заходом — проверить очередь
перед стартом).

**Sources of truth:** `plan.md` (§0 Meta; §4 Phase Index — P6 теперь `🟠 Done with
deviations`, `1/3`) · `phases/P6.md` (Phase Status + Phase Handoff + Completion Notes/Known
Deviations всех трёх items) · `findings/P6-context-hygiene-facts.md`,
`findings/P6.3-pressure-run.md` · `research/13-P6-target-design.md`,
`research/14-P6.3-dor-delta-spec.md` · машинные гейты `packages/skiller/scripts/validate.sh`,
`packages/skiller/scripts/check-translations.sh`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (наследованные, без изменений этим заходом, см. предыдущий `handoff.md`
git-историей, записи (49)–(52)):
(49) `Files` items, правящих `packages/task/commands/*.md`, структурно неполон — не
называет golden-фикстуры и сгенерированный `docs/reference/provider-commands.md`.
(50) Пре-существующий дрейф Codex-проекции (`render-provider-commands.py --check`).
(51) `confidence` в пяти agent-pack ревьюерах не добавлен.
(52) Пункт DoR живёт в ОДНОМ носителе из двух — `SKILL.ru.md` канона `plan-protocol` не
тронут.
Новое этим заходом:
(53) P6.3: красный `pressure#2` (`general/verify-claims`, коммит `34ae85f1`) остаётся
непочищенным — вне Scope P6, требует отдельного item'а.

**Workarounds / Deferred / Open questions:** без изменений этим заходом (см. предыдущий
`handoff.md` — F1 roadmap-кандидат, расхождение flexcrm, апстрим-URL 404, backup-restore,
`PreCompact`/`PostCompact` хук вне скоупа P6 (кандидат roadmap, D53), перекалибровка
`skiller budget --first-turn`).

**Дерево на момент handoff:** `git status --short` показывает незакоммиченные правки
`plans/2026.07.25-ECO-OPT/{plan.md,phases/P2.md,closure/P2.json,journal.jsonl}` (наследие
незавершённого прохода P2-реконсиляции ДО этой сессии — вне `Files` items фазы P6, не
трогать в рамках этого закрытия) и untracked
`packages/skiller/skills/general/verify-claims/evals/benchmark.json`,
`.swissknife/`, `packages/task/lib/.claude/` — не идентифицированы как продукт P6, оставлены
как есть (не удалялись, не коммитились).
