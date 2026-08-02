# HANDOFF — 2026-08-02 — after P7.3

**Next:** `«ЗАПУСК ВРУЧНУЮ: opus/high»`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — Routing `implementation/high`/`manual` (суждение о ЗРЕЛОСТИ сданного: ложное `available` неотличимо от честного) |
| Context | continue (/clear) — ручной item |
| Суть | последний item плана: сводная запись `[Unreleased]` корневого `CHANGELOG.md` + строки матрицы зрелости `docs/status.md` + поимённый вердикт по пяти страницам корневого агрегата доков (D74/D78/D115) |
| Команда | `—` |

```
ЗАПУСК ВРУЧНУЮ: opus/high
/model opus
/effort high
/task:plan-run 2026.07.31-SKM-LEAN P7.4
```

**Done:** **P7.3 закрыт `🟠 Done with deviations`** (item-коммит `a1955b94`; bookkeeping-коммит —
следом за этим handoff). Каталог `roadmap/` сведён к **9 спекам + `README.md`**; инвариант «ноль
записей БЕЗ адреса» проверен СКРИПТОМ и даёт три пустых множества (файл без строки / ссылка без
файла / строка без класса — `0/0/0`), таблица «файл → класс → носитель» покрывает все девять и
опубликована в Completion Notes. Разрешены все четыре находки фазы:

- **F1** (три записи под ложным заголовком «Входы активных планов») — сверкой Completion Notes
  архивного `ECO-OPT`, с РАЗНЫМИ классами: `cross-machine-memory.md` и `codex-subagent-offload.md`
  → `closed-by-item` (реализованы/закрыты вердиктом, удалены, строки в §«Закрыто и удалено» с
  адресом архива), `2026.07.25-memory-hub-service.md` → `deferred-with-criterion` (четыре
  структурных критерия §12, файл остаётся). Сам заголовок раздела снят целиком
  (`grep -c 'Входы активных планов'` → 0).
- **F5** — исход (а) правила (9): `provider-docs-snapshot-daemon-noise.md` получил структурный
  критерий пере-открытия («первый item, правящий `scripts/test-provider-docs.py`», с проверяемой
  git-командой); исход (б) отвергнут фактом — `snapshot()` по-прежнему `root.rglob("*")`.
- **F2** — вердикт «критерий НЕ сработал»: диета P3 правила frontmatter и описания, тел вендорных
  бандлов не касалась (`grep -c 'notify\|upstream\|вендор' phases/P3.md` → 0); ложную
  правдоподобность находки создал омоним `context: fork` (Claude Code) ≠ `strategy: fork`
  (skiller). Правлена одна строка Статуса в `README`, файл записи не тронут.
- **F3** — таблица `research/01-user-intent.md` §4 приведена к D52 и D58; свод по `git log` вскрыл
  ЧЕТВЁРТОЕ расхождение → **D122**: фаз, трогающих `roadmap/**`, **шесть**, и P6.3 не удаляет
  запись, а ЗАВОДИТ — класс правки, который правило `plan.md` §2 не нормирует вовсе (первопричина
  F5).

Носители правок: item-коммит — `roadmap/README.md`, удаление двух спек,
`research/01-user-intent.md`, плюс три файла вне `Files` (`docs/deploy.md`, `docs/reference.md`,
`packages/maind/docs/guide/memory.md` — ссылки на удалённые спеки, иначе 404 в опубликованных
доках); bookkeeping — `plan.md` (§0 Last Updated, §5 D122, §6 Update Log), `phases/P7.md`,
`journal.jsonl`.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢) · P5 6/11 (🟠) ·
P6 0/3 (🟠) · **P7 1/4 (🟡)** — остался ОДИН item плана: **P7.4**, последний по конструкции фазы
(зрелость — суждение о СДАННОМ, перечень релиз-видимых изменений известен только когда терминальны
все семь фаз). `Inputs` P7.4 — `Deliverables` и Completion Notes ВСЕХ семи фаз. `plans/ACTIVE.md`
и `Status` плана не трогаются — план не терминален.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P7.md` (P7.3 Completion Notes; P7.4 ТЗ) ·
`plan.md` §3 Routing (P7.4 = `implementation/high` / `manual`), §5 **D74**/**D115**/**D122** ·
`research/07-p7-roadmap-address-map.md` §7.4 (три уже написанные записи `[Unreleased]`; верхний
выпущенный заголовок `CHANGELOG.md` — `## [0.9.0] - 2026-07-12`).

**Open risks:**

- **P7.3 закрыт `🟠`, не `🟢`** — material-отклонение одно: item-коммит несёт правку трёх файлов
  вне `Files` ТЗ (`docs/deploy.md`, `docs/reference.md`, `packages/maind/docs/guide/memory.md`),
  обязательную из-за удаления двух спек — без неё в доках остались бы мёртвые ссылки, две из них
  абсолютные на GitHub. Тот же класс, что 🟠 у P7.2. P7.4 обязана видеть эту запись как
  легитимную.
- **Правило `plan.md` §2 неполно** (D122): нормирует удаление roadmap-записи, но не её заведение
  фазой посреди плана. Правка §2 — вне Scope P7.3, Pending Work (1); чинит `plan-design`.
- **Две ссылки на удалённые спеки остались в ТЕЛАХ спек** (`artifex-thin-wrapper.md:120`,
  `2026.07.25-memory-hub-service.md:9,262`) — правка тел спек запрещена `Code Guidance` P7.3,
  предъявлены находкой (Pending Work (2)).
- **Находка о `plan_lint.py`** (не чинилась — линтер в `Scope Excluded` фазы P7): разбор item-блока
  ломается о содержимое `Completion Notes` — строка с `##` внутри fenced-блока обрезает тело item'а
  («нет обязательных полей» при полях на месте), а прозаический `**Заголовок:** текст` матчит
  `FIELD_RE` и обрезает `Completion Notes`, из-за чего гейт `write-site` краснеет при напечатанных
  кодах (родственно D90). Обход применён на месте; см. P7.3 Pending Work (4).
- **Чужой дифф в рабочем дереве** (не тронут): изменённый `configs/provider-capabilities.json`,
  удалённый `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`.
  `git add -A` запрещён.
- Прежние (не изменились): `verify-citations --strict` — пред-существующие находки ·
  остаточные WARN `plan-lint` (все пред-существующие) · `ruff` несёт 3 пред-существующие ошибки на
  путях skiller · `scripts/test-provider-docs.py` — 1 известный FAIL (F5: адрес получен, ФИКС не
  сделан — он вне Scope P7.3) · U1/U2 `[UNVERIFIED]`, контракт P4.1 пинован на `06fefc87` ·
  окружной дефект `codex exec -s read-only` (bwrap/AppArmor) · Pending Work P5.3/P5.5/P5.9/P6.2.

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений по составу (унификация парсеров `*.env.ini` P5.3 · `codex plugin
  update` round-trip P5.5 · DX-схема `upstream.schema.json` P5.11 · снимок
  `test_committed_outputs…` P6.3 · типизация `.swissknifeman/config.json` P6.2 · перевод 4
  потребителей `load_config` на атрибуты P6.2 · `plan-lint` WARN D29 по фазам с заявленной
  оркестрацией).
- **open_questions:** один открытый — **OQ-9** (владелец протокола, вне плана). Новых этим
  заходом не заведено.
