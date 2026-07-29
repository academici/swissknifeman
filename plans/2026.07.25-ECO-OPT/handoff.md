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
- P6.1 (process): перебор тира — Routing §3 предписывает `implementation/high`, item исполнен
  под `frontier/high` (Claude Opus 5/high, `/task:plan-run`, D18); эффорт совпал, перебор только
  по классу модели.
- P6.1 (минорный, найден реконсиляцией F6/D139): в 3/40 SIGKILL-прогонов наблюдения отмены
  in-flight остался осиротевший `*.tmp`-файл — стартовая уборка `context-notify.sh` чистит
  только `*.state`. Не искажает полосу/доставку; roadmap-кандидат `roadmap/context-notify-tmp-cleanup.md`.
- P6.2: item-коммит несёт дифф вне `Files` — `packages/skiller/docs/guide/budget.md`,
  `adapters/codex/core/publication-lock.json` и codex-зеркала правленых `SKILL.md`
  (детерминированный продукт `skiller registry`).
- P6.3 (material): item-коммит несёт дифф вне `Files` — `packages/skiller/docs/guide/budget.md`,
  `adapters/codex/core/publication-lock.json` и codex-зеркало `.../SKILL.md` правленого
  `verify-claims` (детерминированный продукт `skiller registry`).
- P6.3 (material): `skiller eval` вернул 6/7 — красный `pressure#2` пре-существующий
  (коммит `34ae85f1`, вне Scope P6.3), не почищен этим item'ом.
- P6.3 (process): Validation ТЗ несла несуществующие флаги CLI `skiller eval` — прогнан
  функционально эквивалентный `skiller eval general/verify-claims`.
- P6.3 (process): чистый прирост тела RU-источника ~17 строк против ориентира «~15».

**Next:** «ЗАПУСК ВРУЧНУЮ: Claude Opus 5/high». Фаза P6 закрыта `🟠 Done with deviations` и
проаудирована ДВАЖДЫ (`## Audit P6 — 2026-07-29` заход 1, вердикт ATTENTION → реконсиляция
`838cae56`; заход 2, вердикт ATTENTION → эта реконсиляция, последняя бухгалтерская правка P6 —
повторный `/task:plan-audit P6` не назначается, AUDIT-CAP). Следующий шаг — первый item фазы
**P7** (детализирована до DoR, 3 items `⬜`, все `Exec = manual`; порядок `P7.1 + P7.3 → P7.2`,
`roadmap.md:66`).

| Параметр | Значение |
|:--|:--|
| Model | opus — Routing §3 `implementation/high` (P7.1) |
| Thinking | high — dogfood-тест переключения на Codex, не механическая правка |
| Context | continue (/clear) — ручной item |
| Суть | P7.1 — Codex ведёт живой item плана целиком (cold start → исполнение → закрытие по §8), вердикт «дошёл» / «дошёл с N вмешательствами» / «сломался на X» |

```
Прочитать: plans/2026.07.25-ECO-OPT/plan.md (§0 Meta, §2 Execution Rules, §4 Status Board) →
plans/2026.07.25-ECO-OPT/phases/P7.md (P7.1 Intent/Why/Scope/Validation) → этот handoff.md.
Исполнить P7.1 по ТЗ item'а (phases/P7.md:123-…): предстартовая сверка гейтов → отбор 1–2
кандидатов dogfood (P8.7 · P1.2 · P3.2 — сверить статус) → cold-start прогон Codex'ом от начала
до закрытия item'а по протоколу §8 → `artifacts/P7.1/breakage-log.md` → `findings/P7.1-switch-test.md`.
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
(54) P6.1: наблюдённая отмена in-flight (реконсиляция F6, `findings/P6.1-statusline-measure.md`
§4) выявила осиротевший `*.tmp` в 3/40 SIGKILL-прогонов — стартовая уборка чистит только
`*.state`. Минорный файловый мусор, не искажает полосу/доставку; roadmap-кандидат: расширить
glob уборки `context-notify.sh` на `*.tmp` — правка кода вне Scope этого захода.

**Workarounds / Deferred / Open questions:** без изменений этим заходом (см. предыдущий
`handoff.md` — F1 roadmap-кандидат, расхождение flexcrm, апстрим-URL 404, backup-restore,
`PreCompact`/`PostCompact` хук вне скоупа P6 (кандидат roadmap, D53), перекалибровка
`skiller budget --first-turn`).

**Дерево на момент handoff:** `git status --porcelain` = ровно два untracked пути,
`.swissknife/` и `packages/task/lib/.claude/` — не идентифицированы как продукт P6, оставлены
как есть (не удалялись, не коммитились). Все правки `plans/2026.07.25-ECO-OPT/{plan.md,
phases/P2.md,closure/P2.json,journal.jsonl}` из предыдущей версии этого раздела закоммичены:
`phases/P2.md`/`closure/P2.json` — коммитом `7b0156d0` (закрытие P2); `plan.md`/`journal.jsonl`
— коммитом `838cae56` (реконсиляция P6, заход 1). Прежняя формулировка «незавершённый проход
P2-реконсиляции» соврала — снята реконсиляцией P6 (заход 2, находка G5).
`packages/skiller/skills/general/verify-claims/evals/benchmark.json` — прямой продукт прогона
P6.3 (`generated_at 2026-07-28T22:33:29`, назван в `findings/P6.3-pressure-run.md:16-18`), не
неопознанный untracked; судьба решена этим заходом — паттерн
`packages/skiller/skills/**/evals/benchmark.json` добавлен в `.gitignore` (F5).
