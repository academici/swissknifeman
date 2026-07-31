# Индекс плана — `plans/2026.07.31-SKM-LEAN/`

**Обновлён:** 2026-07-31

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мастер-план: Meta, Context, Execution Rules, §3 Routing, Status Board, D-лог, `## Обсуждение` |
| `phases/P1.md … P7.md` | по файлу на фазу: Phase Context (контракт-блок; скелет-маркеров нет ни в одной фазе — D67) + items + Phase Handoff |
| `handoff.md` | rolling-указатель «где мы» (перезаписывается) |
| `journal.jsonl` | append-only история запусков `task:plan-*` |
| `brief/` | слой 0 «вход»: бриф владельца (уточнения по ходу — `01-refinements.md`) |
| `findings/` | слой 1 «сырьё»: RAG-выжимки с URL/датой/вердиктом, recon-отчёты |
| `research/` | слой 2 «синтез»: авторские design-документы |
| `open-questions.md` | спорное/нерешённое — семь открытых: OQ-1…OQ-6 и OQ-8 (OQ-7 закрыт вердиктом владельца, `Resolved → D61`) |
| `roadmap.md` | карта исполнения 36 items: очередь, батчи, гейты владельца (собрана и принята шагом `finish`, D67; обновлена по находкам захода 2 — D74/D77) |

Пока отсутствуют (заводятся по мере надобности): `closure/` — пишет `plan-close` при закрытии
фазы (`Closure Protocol | v1`); `workflows/` (оркестрация ни одной фазой не заявлена).
Заводятся по ходу: `artifacts/` — фазой **P1** (`artifacts/p1-2-fleet-sweep.sh`, P1.2; далее
P3.1 и P4.6), `root/contracts/` — фазой **P4** (P4.1).

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `brief/00-brief.md` | brief | все фазы | вход владельца: 7 фаз, закрытый список «вне скоупа P4», вердикты P7 |
| `findings/rag-2026-07-31-native-skill-fields.md` | findings | `P3`, `P2`, `P4` | справочник frontmatter Claude Code, липкость тела скилла, баги #49835/#17283, CooperBench, AgentTool suppression |
| `findings/repo-recon-2026-07-31.md` | findings | `P1`…`P7` | карта кодовых поверхностей с якорями `file:line`; §11 — расхождения замера с оценками брифа |
| `findings/P1-plugin-cli-probe-2026-07-31.md` | findings | `P1.1`, `P1.2` | живой замер `claude plugin list --json` / `plugin details` на 2.1.220: ключи, CWD-зависимость, формат строки `Always-on`, тайминги, состав реестра флота, конвенция закрытия roadmap-записи |
| `findings/P1-plugins-cwd-defect-2026-07-31.md` | findings | `P1.4`, `P1.2` | разбор дефектов агрегатора на живом `claude 2.1.220`: CWD-зависимость резолвинга `plugin details` (§1) при CWD-независимом значении цены (§2), разделитель тысяч в строке `Always-on` (§3), `brain@brain` как сломанная апстримом запись `scope: user` (§5), масштаб занижения 3,7× на контрольном проекте (§6), стоимость вызова как вход для таймаута обхода (§7) |
| `findings/P2-resident-layer-probe-2026-07-31.md` | findings | `P2`, `P3`, `P1.3` | живой замер резидентного слоя флота: доли хаб-блока в `CLAUDE.md`, tool search включён по умолчанию (§5.1), пере-проверка соседних допущений измерителя (§9) |
| `findings/P3-native-fields-context-cost-2026-07-31.md` | findings | `P3` (все items), косвенно `P2.5`, `P1.3` | «поле → на какую ОСЬ цены действует»: `paths` не снимает запись листинга, `disable-model-invocation` снимает; гейты `validate.sh`, которые задевает правка описаний; стенд `claude -p` и usage-сигнал как приборы |
| `research/01-user-intent.md` | research | все фазы | трассировка «мысль брифа → адрес», покрытие `audits/skm.md`, coupling-поверхность, обоснование порядка фаз |
| `research/02-p2-resident-model.md` | research | `P2` | целевая конструкция резидентного слоя, почему пилот, риски фазы |
| `findings/P4-headless-envelope-2026-07-31.md` | findings | `P4.1`, `P4.3`, `P4.4` | живой замер headless-слоя 2.1.220: флаги (`--max-turns` больше нет), полный список ключей конверта `--output-format json`, подтверждение, что слэш-команда через `-p` отрабатывает |
| `research/03-p3-native-scope-model.md` | research | `P3` | две оси и их приборы, целевая конструкция фазы, порядок items, связь с P1/P2, семь рисков |
| `research/04-p4-driver-model.md` | research | `P4` (все items) | четыре части драйвера и границы между ними, закрытый список источников чтения плана, вердиктная таблица, правило «кто пишет строку в журнал», форма приёмки, восемь рисков |
| `findings/P5-hygiene-surfaces-2026-07-31.md` | findings | `P5` (все items) | RAG по supply-chain скану скиллов (классы угрозы, позиция Anthropic «сканера нет — аудируй», вердикт CSA/Trail of Bits «сканеры обойдены») + разведка девяти поверхностей фазы с якорями `file:line` |
| `research/05-p5-hygiene-model.md` | research | `P5` (все items) | три опровергнутые замером постановки, целевая конструкция supply-chain проверки, разбор однородности §3, почему оркестрация не заявляется, порядок внутри фазы, пять рисков |
| `findings/P6-manifest-drift-2026-07-31.md` | findings | `P6.3`, косвенно `P6.1`, `P5.2` | разбор красного baseline `test_provider_manifest` для гейта OQ-7: когда покраснел, полный семантический дифф манифеста (29 `evidence`-путей), таблица четырёх носителей хеша (два устаревших — оба тестовые), область поражения CI, класс второго провала |
| `research/08-premortem-and-oq7-verdict.md` | research | `P6.3`, `P2.6`, `P5.1`, `P1.3` | вердикт владельца по OQ-7 и что он меняет в детализации; pre-mortem по Klein трёх high-stakes поверхностей (17 причин → 15 кластеров → 6 mitigations без носителя), сводка D61–D66 |
| `research/09-validation-executability-2026-07-31.md` | research | все items `Exec = plan-exec` | свип исполнимости команд `Validation` на живом дереве: 41 проверка, три дефекта (F5 `task/scripts/test.sh` не существует · F6 флаг `--dry` не существует · F7 протухший размер файла), подтверждённые числа приёмок |

Ожидаемые к появлению (производятся items плана, потребляются позднее):

| Источник | Слой | Производит | Питает |
|:--|:--|:--|:--|
| `findings/P1-fleet-baseline.md` | findings | `P1.2` | `P1.3`, `P2.6`, `P3` |
| `artifacts/p1-2-fleet-sweep.sh` | artifacts | `P1.2` | повторный замер после P2/P3 (судьба — архив плана) |
| `findings/P2-rules-pilot.md` · `findings/P2-hub-pilot.md` | findings | `P2.2`, `P2.5` | `P2.6` |
| `findings/P2-fleet-after.md` | findings | `P2.6` | `P1.3`/OQ-4, `P3` |
| `artifacts/p3-1-native-fields-bench.sh` + `artifacts/p3-1-fixtures/**` | artifacts | `P3.1` | `P3.2`, `P3.3`, `P3.4`, `P3.5` |
| `findings/P3-native-fields-smoke.md` | findings | `P3.1` | `P3.2`, `P3.4`, `P3.5` |
| `findings/P3-scope-pilot.md` | findings | `P3.2` | `P3.3`, OQ-2 |
| `findings/P3-scope-rollout.md` | findings | `P3.3` | OQ-5, `P7.3` |
| `findings/P3-fork-selection.md` | findings | `P3.4` | `docs/guide/skill-taxonomy.md` |
| `findings/P3-desc-burndown.md` | findings | `P3.5` | `P7.1` (решение по Codex-фолбэку), `P7.3` |
| `root/contracts/driver-plan-protocol-v2.md` | root | `P4.1` | `P4.2`, `P4.3`, `P4.4`, `P4.5` (судьба — docs пакета harness при архивации) |
| `artifacts/p4-6-fixture-plan.sh` | artifacts | `P4.6` | повторная приёмка драйвера (судьба — архив плана) |
| `findings/P4-wave-acceptance.md` | findings | `P4.6` | `P7.1` (первое число критерия «N волн», OQ-3) |
| `findings/P5-vendored-audit.md` | findings | `P5.1` | OQ-6 (гейт владельца), `P7.3` |
| `findings/P5-codex-visibility.md` | findings | `P5.4` | канон Codex-ветки инструкций, `P7.3` |
