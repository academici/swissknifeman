# HANDOFF — 2026-07-29 — after P7.1

**P7.1 закрыт `🟠 Done with deviations`.** Dogfood-тест переключения проведён: Codex
(`gpt-5.6-terra` / effort `medium`) провёл живой item плана **P6.4** от cold start до закрытия
по протоколу §8. **Вердикт — «дошёл с 4 вмешательствами»** (дословно из закрытого списка трёх).
Семь поломок с названными адресами — `artifacts/P7.1/breakage-log.md`; полный разбор, границы
результата и §8 про непроведённую ревью-пробу — `findings/P7.1-switch-test.md`.

Побочно этим же заходом (решение владельца **D140**): фаза **P6 реопенена** под новый item
**P6.4**, он исполнен Codex'ом и закрыт `🟠` (item-коммит `b445a727`, bookkeeping `aefe8dd1`) —
стартовая уборка `context-notify.sh` теперь одним `find` подметает устаревшие `*.state` **и**
`*.tmp`; закрыт `Open risk` (54).

**Почему понадобился реопен.** Предстартовая сверка P7.1 нашла структурный блокер: все три
названных его ТЗ кандидата dogfood закрыты 2026-07-27 (`P8.7` 🟢, `P1.2` 🟢, `P3.2` 🟠), а живых
items в плане оставалось три — `P7.1`/`P7.2`/`P7.3`, оба оставшихся `Exec = manual` ⇒ условие
(1) критерия отбора (`Exec = plan-exec`) стало невыполнимым ни одним живым item'ом. План обнулил
себе выборку, поставив P7 последней волной.

**Next:** item-close: `task:plan-close 2026.07.25-ECO-OPT P6` — закрыть реопененную фазу P6
(её `## Phase Handoff` несёт маркер `> УСТАРЕЛ — фаза реопенена D140.`, снимает его только
`plan-close`; все четыре items терминальны: P6.1 🟢 · P6.2 🟠 · P6.3 🟠 · P6.4 🟠).

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | `command.filesystem-write`, `command.git-write` |
| Context | NEW SESSION (/clear) |
| Суть | Закрыть фазу P6 после P6.4: Phase Status, §4 Status Board, `closure/P6.json` регенерацией, снятие маркера реопена с `## Phase Handoff`, bookkeeping-коммит |

```
/task:plan-close 2026.07.25-ECO-OPT P6
```

Провайдер-нативная форма того же шага (корневой `AGENTS.md` § «Codex launch and hook integrity»):

| Model | Reasoning effort | Approval | Sandbox | CWD | Context |
|:--|:--|:--|:--|:--|:--|
| gpt-5.6-terra | low | never | danger-full-access | `/home/vostrikov/projects/packages/swissknifeman` | NEW SESSION |

```
codex -C /home/vostrikov/projects/packages/swissknifeman -c 'model="gpt-5.6-terra"' -c 'model_reasoning_effort="low"' -a never -s danger-full-access
$ task:plan-close 2026.07.25-ECO-OPT P6
```

> Форма пина — через `-c model=`, а НЕ `-m`: поломка №2 этого захода показала, что `codex doctor`
> флага `-m` не принимает вовсе и preflight-самопроверка даёт на нём ложный конфликт. При
> неинтерактивном `codex exec` флаг `-a` не поддерживается — опускать (поломка №1).

**Done:** **54/54 items в затронутых фазах терминальны** (P1–P6, P8–P11 плюс P7.1; счёт вырос
52 → 53 реопеном P6 под P6.4 и → 54 закрытием P7.1). Закрыты фазы **P1** (1/2, 🟢), **P2**
(1/3, 🟠), **P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9**
(3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). **P6** — `🟡 In progress` (1/4, реопенена
D140, все items терминальны, ждёт `plan-close`). **P7** — `🟡 In progress` (0/3, P7.1 🟠).

**Remaining:** закрытие фазы P6; затем **P7.3** (плагин `codex-plugin-cc`: гейт
`skiller budget --first-turn` до/после, процедура вкл/выкл, правило активации) и после него
**P7.2** (инструкционный слой по списку поломок P7.1 + трек 1 OQ-4). Порядок
`P7.1 + P7.3 → P7.2` соблюдается: P7.2 потребляет И список поломок (готов), И числа бюджета
(производит P7.3).

**Sources of truth:** `findings/P7.1-switch-test.md` (§1 гейты цитатами · §2 отбор и его провал ·
§3 ожидание ДО прогона · §4 ход трёх заходов и независимая перепроверка чисел · §5 вердикт ·
§6 семь адресов · §7 границы · §8 дорожка B не прогонялась) ·
`artifacts/P7.1/breakage-log.md` · `artifacts/P7.1/run-2-codex-escalation.diff` (эскалация
захода 2 как доказательство) · `plan.md` §5 **D140** · `phases/P7.md` P7.1 Completion
Notes/Known Deviations · `phases/P6.md` P6.4 · `closure/P6.json`.

**Open risks:** **унаследованные (перенесены вручную — Codex обронил их при перезаписи
`handoff.md`, поломка №4 этого захода; ни один не закрыт):**
(49) `Files` items, правящих `packages/task/commands/*.md`, структурно неполон — не называет
golden-фикстуры и сгенерированный `docs/reference/provider-commands.md`.
(50) Пре-существующий дрейф Codex-проекции (`render-provider-commands.py --check`).
(51) `confidence` в пяти agent-pack ревьюерах не добавлен.
(52) Пункт DoR живёт в ОДНОМ носителе из двух — `SKILL.ru.md` канона `plan-protocol` не тронут.
(53) P6.3: красный `pressure#2` (`general/verify-claims`, коммит `34ae85f1`) остаётся
непочищенным — вне Scope P6, требует отдельного item'а.
(54) **ЗАКРЫТ** item'ом P6.4 (`b445a727`): осиротевшие `*.tmp` теперь подметаются стартовой
уборкой; регресс-тест `test_fresh_session_cleans_old_state_and_tmp_files`.
**Новое этим заходом:**
(55) **Класс «Files не называет машинно-обязательный побочный продукт» подтверждён третьим
случаем** (после (49) и Known Deviations P6.2/P6.3): реопен фазы оставляет на диске
`closure/<Pn>.json`, чей гейт краснеет на любую смену статуса item'а, а канон §3 «Phase reopen —
FOUR steps» отчёт закрытия среди носителей НЕ называет — пятый шаг отсутствует. Кандидат
`roadmap.md`, носитель чужой (канон).
(56) **Канон §8 разрешает терять незакрытые риски:** у полей `Open risks` и
`Workarounds/Deferred/Open questions` нет правила переноса, а «rolling pointer, OVERWRITTEN …
history lives in git» прямо это лицензирует. Реализовалось живьём — шесть открытых рисков
утрачены одним закрытием item'а, восстановлены вручную. Кандидат `roadmap.md` + машинный чек
`plan_lint`.
(57) **Конфликт формы launch-блока:** канон §8 предписывает нейтральную таблицу
(`Model class`/`Effort`/`Capabilities`), корневой `AGENTS.md` — нативную
(`model`/`effort`/`approval`/`sandbox`/`cwd`); второй водитель выдал только нативную, поле
`Capabilities` потеряно. Адресат — **P7.2** (корневой `AGENTS.md` — его легальная дельта).
(58) **Канонический launch-блок корневого `AGENTS.md` не работает на headless-пути:** у
`codex exec` нет флага `-a`, а предписанный preflight `codex doctor --json` не принимает `-m` и
показывает конфиг вместо пина сессии ⇒ правило «подтверди фактические model/effort, а не выводи
из файлов» невыполнимо в предписанной форме. Адресат — **P7.2**.

**Workarounds / Deferred / Open questions:** унаследованные без изменений (F1 roadmap-кандидат,
расхождение flexcrm, апстрим-URL 404, backup-restore, `PreCompact`/`PostCompact` хук вне скоупа
P6 — кандидат roadmap, D53, перекалибровка `skiller budget --first-turn`). **Новое:** правило
дорожки B (`U`/`P`, **D64**) в этом заходе **НЕ применялось** — ревью-проба не проводилась
(дифф в 29 добавленных строк не даёт осмысленного эталона находок), правило уходит в
`roadmap.md`, где строка под него уже стоит. **Owner-вопрос P7.2 (судьба per-package
`AGENTS.md`, D62) остаётся открытым и этим заходом не проверялся:** таких файлов в дереве нет
вовсе, проверять было нечего.

**Дерево на момент handoff:** `git status --porcelain` = ровно два untracked пути,
`.swissknife/` и `packages/task/lib/.claude/` — унаследованные, не идентифицированы как продукт
этого захода, оставлены как есть (не удалялись, не коммитились). Всё остальное закоммичено:
`023f9349` (реопен P6 + ТЗ P6.4), `703d5145` (ожидание P7.1 ДО прогона), `f2dacb1b` (починка
`Files` P6.4 по находке прогона), `b445a727` + `aefe8dd1` (работа и бухгалтерия Codex по P6.4),
плюс bookkeeping-коммит этого закрытия.
