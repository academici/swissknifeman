# HANDOFF — 2026-07-31 — after P2.4

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — форма раздаваемого хаб-блока на всём флоте (замораживаемая поверхность), критерий «где нативный листинг» — открытое design-решение (D20); §3 Routing P2.5 |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P2.5 — снять дубль нативного листинга скиллов в `generate-hub.sh`: провайдер-зависимая форма хаб-блока (краткая/полная), сверка обнаружения, пилот |

```
Исполни item P2.5 мастер-плана 2026.07.31-SKM-LEAN строго по его ТЗ.

ТЗ: plans/2026.07.31-SKM-LEAN/phases/P2.md → `### P2.5 — Хаб-индекс: снять дубль нативного
листинга скиллов` (все 16 полей; Required Reads — до первой правки). Протокол исполнения и
закрытия item'а — packages/task/commands/plan-run.md: Pre-mutation Task Contract ДО первой
мутации, статус 🟡 до работы, два коммита (item + bookkeeping), строка
`write-site: pre_mutation: … · pre_final: …`, запись в journal.jsonl.

РЕЖИМ: exec item P2.5 по готовому ТЗ (design-заходов не требуется, открытых решений нет)
ВХОД: plans/2026.07.31-SKM-LEAN/phases/P2.md → `### P2.5` целиком; затем `findings/P2-resident-layer-probe-2026-07-31.md` §2, §9 (числа блока по проектам)
СКОУП: см. Scope Included P2.5 — различение каналов-целей в `generate-hub.sh`, краткая/полная форма блока, сверка перед сокращением (нативный активный набор), тесты генератора (первые), пилотный прогон на `agelto` (72 % блока) с числами «до/после», обновление доков раздачи
НЕ ТРОГАТЬ: отмену хаб-механизма (D20); состав подключаемых скиллов/дефолт `connect` (D5); `.claude/agents`-секцию блока, если не относится к дублю листинга; массовую раскатку на флот (это P2.6); нативный листинг/frontmatter скиллов (P3); закрытые items P2.1–P2.4
```

**Done:** **P2.4 закрыт: 🟢.** Точка эффекта заведена в provider-ветке `deploy_project`:
предикат Rule 2 (`emit_example` включён · операция не refused ЦЕЛИКОМ · строка `planned` ·
канал claude-code), байты `.example` — из `row.rendered` (второго рендера нет). `write_example`
стал идемпотентным по факту (`changed`, честный no-write `dry`). Граница подсказки
`missing-example` дописана в `health.py`/`probe.py`/докстринге `check_hygiene` — чинит только
зелёный провайдерский план, `unmanaged-target` эмиссии не получает. Тесты провайдерского пути
+6 (`test.sh` 539 → 545: emit/opt-out/refuse/dry/repeat в `test_provider_deploy.py`,
идемпотентность в `test_mcpconfig.py`). Живой dry-run по 22 достижимым проектам реестра —
`findings/P2.4-fleet-emit-dryrun.md`: класс A (появится `.example`) 4 — `botkit`, `vintera`,
`dterema`, `dterema-app`; класс B (уже совпадает) 1 — `agentools`; класс C (провайдер отказал)
17, поимённо с диагностикой (15 `unmanaged-target` + 2 отказа по codex-каналу при зелёной
claude-code строке — `azguard`, `sibintek-insiders`) — вход **P2.6** (D93). Живое применение на
`botkit` (выбран по `missing-example` И зелёному провайдеру, Implementation Rule 9): создан
`.mcp.json.example`, `.gitignore` приведён в порядок; коммит в репозитории `botkit`
(`feat/core-0.1-hardening`) — `a7261e259ee4c0acc44ec235ece4a2557d796f05`. Item-коммит
swissknifeman — `2cd6fbf3621b82ac86f4530ab8b2c3a78406f04a`. Материальных отклонений нет,
Known Deviations — пусто.

**Remaining:** доска P2: **4/6** — `P2.5` (⬜, форма хаба, launch-block выше) и `P2.6` (⬜,
раскатка на флот, `plan-exec`) остаются. Порядок фазы строгий (P2.1 → … → P2.6) —
**P2.6 не стартует**, пока P2.5 не терминален. Общая доска: P1 3/4 (закрыта 🟠) · P2 4/6 🟡 ·
P3 0/5 · P4 0/6 · P5 0/9 · P6 0/3 · P7 0/4.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P2.md` §P2.4 Completion Notes (реализация
+ живые прогоны) · `findings/P2.4-fleet-emit-dryrun.md` (таблица трёх классов, вход P2.6) ·
`findings/P2.4-provider-emit-probe-2026-07-31.md` (факты, на которых стоят D91–D93) ·
`plan.md` §0 Meta, §3 Routing, §4 доска (4/6), §5 D91–D93, §6 Update Log ·
`packages/maind/lib/maind/provision/deploy.py:296–363` · `packages/maind/lib/maind/mcpconfig.py`
(`write_example`/`check_hygiene`) · для следующего шага — `findings/P2-resident-layer-probe-2026-07-31.md` §2, §9 · `packages/skiller/scripts/generate-hub.sh`.

**Open risks:**

- (перенесено из P2.3 handoff, в силе) **Гейт приёмки `pre_final` вырожден почти по всему плану
  вне закрытых items** — отдельный заход `plan-design` на разделитель ` · ` для P3.4/P5.5,
  без изменений:

  ```
  design-item: task:plan-design 2026.07.31-SKM-LEAN P3.4

  РЕЖИМ: правка ФОРМЫ Validation (разделитель), НЕ пере-дизайн предмета items
  ВХОД: plans/2026.07.31-SKM-LEAN/research/10-validation-acceptance-form-2026-07-31.md → §2 таблица, §4 предложение; затем plan.md §5 D90
  СКОУП: 1) P3.4 и P5.5 — разделить существующие проверки ` · ` вместо «; », текст проверок не менять 2) прогон §2 до/после: ноль красных 3) дальше — остальные items с «; » тем же приёмом
  НЕ ТРОГАТЬ: предмет и число проверок items; Scope/Deliverables; статусы; закрытые items P1.x, P2.1, P2.2, P2.3, P2.4
  ```

- **`maind sync --only mcp` отказывает `unmanaged-target` (или косвенно, по codex-каналу) у 17
  из 22 достижимых проектов флота** (подтверждено ДВАЖДЫ живым прогоном: design-заход 2026-07-31
  и этот exec-заход, `findings/P2.4-fleet-emit-dryrun.md`) — значит эффект ЛЮБОЙ эмиссии сегодня
  ограничен пятью проектами (4 получат `.example` + `agentools` уже чист). Адрес — **P2.6**
  (D93: вход, Implementation Rule 10, приёмка 6в); усыновление целей требует отдельной D-записи
  владельца.
- **Проекты флота с Boost/`.ai`-generated `CLAUDE.md` не покрыты процедурой P2.2 напрямую**
  (`findings/P2-rules-pilot.md` §6) — минимум `vintera/cms`, `sibintek-insiders`, `diabox`;
  до входа в **P2.6** для них нужно отдельное design-решение о пути правки.
- **Пять секций-кандидатов P2.1 остаются резидентными (436 ток)** — по D89 это решение, не долг.
- **Обход подкаталогов `.claude/rules/**` починен, но сегодня не проявлен на живом флоте.**
- **agelto/flexcrm остаются `WARN` и после исправления модели MCP** — предмет **P2.6**.
- (прежнее, в силе) **гейт размера меряет файл целиком** · **токенная оценка продублирована в
  двух пакетах** · **`closure/P1.json` `inputs_sha256["phases/P1.md"]` больше не совпадает с
  живым файлом** (D87).
- **Остаточная находка `verify-citations` вне диффа этого захода:** `phases/P2.md:296`
  (Completion Notes закрытого **P2.3**) несёт сокращённую ссылку на строку 89 файла
  `context-economy/SKILL.md`, которая не резолвится ни от корня репо, ни от каталога плана (полный путь —
  `packages/skiller/skills/general/context-economy/SKILL.md`). Присутствует на `HEAD`
  (проверено `git show HEAD:… | grep`), то есть отчёт закрытия P2.3 «находок 0» её не поймал.
  Счёт этого захода: `verify-citations --strict` 1 находка — новых от диффа item'а 0
  (та же строка). ТЗ закрытого item'а задним числом не правится — адрес: ближайший заход,
  правящий `phases/P2.md` вне закрытых Completion Notes, либо запись в
  `plans/verify-citations-known-exceptions.json` с обоснованием.
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый `RESEARCH/AUDIT-loqum-findings.md`,
  неотслеживаемые `.swissknife/`, `audits/`) — этим заходом не тронут, не коммитился;
  исполнителю P2.5 его тоже не трогать (`plan-protocol` §6).

**Workarounds/Deferred/Open questions:** «—» / сквозная правка формы `Validation` — отложена
(см. Open risks) · проекты флота с Boost/`.ai`-generated `CLAUDE.md` — отложены (см. Open risks) ·
усыновление `unmanaged-target` целей — отложено до P2.6 (D93) / OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8
(пять открытых, без изменений — этот заход трекер не менял), см. `open-questions.md`.
