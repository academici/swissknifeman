# HANDOFF — 2026-07-31 — after P2.4

**Next:** /task:plan-design 2026.07.31-SKM-LEAN P2.4

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — design-решение по архитектурному расхождению (§9 Routing tier) |
| Context | NEW SESSION — шаг-не-item |
| Суть | Решить, как `mcp.emit_example` default-on производит эффект под provider-managed рендерингом (claude-code renderer) — или пере-сформулировать Deliverable item'а |

```
/task:plan-design 2026.07.31-SKM-LEAN P2.4
```

**Done:** P2.4 **эскалирован (🔴 Blocked)**, НЕ закрыт. Плюмбинг дефолта сделан и валиден
(item-коммит `d16e2ce7`, сохраняется, не откатывается): `EMIT_EXAMPLE_DEFAULT = True` — единственный носитель
(`packages/maind/lib/maind/constants.py`), подключён через `merge_defaults`
(`packages/maind/lib/maind/config.py::merge_defaults` — `mcp.setdefault("emit_example", ...)`);
`deploy.py:294` читает итог у резолвера (комментарий обновлён, логика чтения не менялась);
opt-out `"emit_example": false` работает и покрыт тестом. `config.example.json` (`_comment_mcp` +
значение `true`) и `packages/maind/docs/guide/config.md` пере-изданы под новый дефолт.
`roadmap/mcp-config-example-emit.md` удалён (`find roadmap -name … -delete`), строка добавлена в
`roadmap/README.md` §«Закрыто и удалено». Тесты: `packages/maind/tests/test_config.py`
(+2: `test_emit_example_defaults_on`, `test_emit_example_opt_out_preserved`) и
`packages/maind/tests/test_deploy.py` (+3: `test_emits_example_by_default`,
`test_emit_example_opt_out`, `test_emit_example_idempotent`) — `test.sh` 534 → 539 (на
дереве до bookkeeping-коммита); `validate.sh` зелёный.

**Найденное расхождение (причина эскалации):** живой прогон `maind sync --all --only mcp
--dry-run` (26 проектов реестра, до/после правки идентичны — проверено `git stash`) показал, что
ветка `emit_example` (`deploy.py:344–348`, срабатывает только когда `provider_plan is None`, т.е.
только на `legacy_targets`) НИКОГДА не выполняется в реальной эксплуатации: и `cmd_deploy`, и
`cmd_sync`/`_mcp_run` безусловно резолвят `provider_projections` (дефолт — минимум `claude-code`,
`provider_projection_context`/`_provider_projections` без явного конфига уже возвращают непустой
список — подтверждено существующим тестом `test_provider_projection_missing_project_carrier_preserves_defaults`),
поэтому `provider_plan` в проде никогда не `None`. Заявленный Code Guidance эффект item'а
(«ближайший `maind sync` начнёт писать `.example`+`.gitignore` в ~20 чужих репозиториях») —
ложен при текущей архитектуре provider-managed rendering; ни один из пяти «зелёных» по провайдеру
проектов драя (`botkit`/`vintera`/`dterema`/`dterema-app`/`agentools`) не получил `.example`.
Побочная находка: `maind health` уже несёт подсказку «чинить через `maind sync --only mcp»
(`test_health.py:168`), которая на живом флоте не сработает по той же причине — молчащий баг,
не предмет этого item'а, но релевантен design-решению.

**Remaining:** P2.4 ждёт `plan-design` — три варианта в ESCALATION-блоке
(`phases/P2.md` P2.4): (а) завести эмиссию `.example`/`.gitignore` в claude-code provider
renderer (другой пакет/Files) · (б) сузить Scope item'а до «плюмбинг корректен, эффекта на флоте
нет» и переписать Deliverable/Code Guidance под честную пустую dry-run таблицу · (в) принять как
известный долг новой roadmap-записью. Порядок фазы строгий (P2.1→…→P2.6) — **P2.5/P2.6 не
стартуют**, пока P2.4 не терминален. Доска: P1 `3/4` (закрыта 🟠) · P2 `3/6` 🟡 (P2.4 🔴
Blocked) · P3 `0/5` · P4 `0/6` · P5 `0/9` · P6 `0/3` · P7 `0/4`.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P2.md` §P2.4 (ESCALATION-блок + спека) ·
`plan.md` (§0 Meta, §3 Routing, §4 доска) · живой прогон `maind sync --all --only mcp --dry-run`
2026-07-31 (не сохранён файлом — воспроизводим командой, дерево — рабочая копия этого коммита) ·
`packages/maind/lib/maind/provision/deploy.py:198–360` · `packages/maind/lib/maind/provision/sync.py:87–197`
(`select_projects`/`contexts`/`_mcp_run`) · `packages/maind/tests/test_provider_deploy.py`
(`test_provider_projection_missing_project_carrier_preserves_defaults`).

**Open risks:**

- (перенесено из P2.3 handoff, в силе) **Гейт приёмки `pre_final` вырожден почти по всему плану
  вне закрытых items** — отдельный заход `plan-design` на разделитель ` · ` для P3.4/P5.5,
  без изменений:

  ```
  design-item: task:plan-design 2026.07.31-SKM-LEAN P3.4

  РЕЖИМ: правка ФОРМЫ Validation (разделитель), НЕ пере-дизайн предмета items
  ВХОД: plans/2026.07.31-SKM-LEAN/research/10-validation-acceptance-form-2026-07-31.md → §2 таблица, §4 предложение; затем plan.md §5 D90
  СКОУП: 1) P3.4 и P5.5 — разделить существующие проверки ` · ` вместо «; », текст проверок не менять 2) прогон §2 до/после: ноль красных 3) дальше — остальные items с «; » тем же приёмом
  НЕ ТРОГАТЬ: предмет и число проверок items; Scope/Deliverables; статусы; закрытые items P1.x, P2.1, P2.2, P2.3
  ```

- **`maind health` несёт ложную подсказку** (`test_health.py:168` — «чинить через
  `maind sync --only mcp`») для `missing-example` — сама ветка мертва в проде (см. выше);
  релевантно варианту (а) design-решения P2.4, отдельно не заведено.
- **Проекты флота с Boost/`.ai`-generated `CLAUDE.md` не покрыты процедурой P2.2 напрямую**
  (`findings/P2-rules-pilot.md` §6) — минимум `vintera/cms`, `sibintek-insiders`, `diabox`;
  до входа в **P2.6** для них нужно отдельное design-решение о пути правки.
- **Пять секций-кандидатов P2.1 остаются резидентными (436 ток)** — по D89 это решение, не долг.
- **Обход подкаталогов `.claude/rules/**` починен, но сегодня не проявлен на живом флоте.**
- **agelto/flexcrm остаются `WARN` и после исправления модели MCP** — предмет **P2.6**.
- (прежнее, в силе) **гейт размера меряет файл целиком** · **токенная оценка продублирована в
  двух пакетах** · **`closure/P1.json` `inputs_sha256["phases/P1.md"]` больше не совпадает с
  живым файлом** (D87).

**Workarounds/Deferred/Open questions:** «—» / сквозная правка формы `Validation` — отложена
(см. Open risks) / проекты флота с Boost/`.ai`-generated `CLAUDE.md` — отложены (см. Open risks) /
`maind health` ложная подсказка для `missing-example` — отложена, зависит от варианта design-решения /
OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8 (пять открытых, без изменений), см. `open-questions.md`.
