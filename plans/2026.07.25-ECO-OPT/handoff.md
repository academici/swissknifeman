# HANDOFF — 2026-07-29 — after P6

**P6 закрыта `🟠 Done with deviations`** (4/4 items терминальны: P6.1 🟢 · P6.2 🟠 · P6.3 🟠 ·
P6.4 🟠). Реопен D140 закрыт: P6.4 (Codex, item-коммит `b445a727`, bookkeeping `aefe8dd1`)
расширил стартовую уборку `context-notify.sh` на осиротевшие `*.tmp` рядом с `*.state`, закрыв
`Open risk` (54) и минорную деградацию, найденную реконсиляцией P6.1 (F6/D139). Известные
отклонения фазы — механически из Known Deviations всех четырёх items, см.
`phases/P6.md` `## Phase Handoff`.

**Docs-sync:** не требуется — P6.1 уже несёт `docs/configs/statusline.md`; P6.2/P6.3/P6.4 не
трогают `docs/` (доставка тел скиллов через `skiller registry`, P6.4 — правка одной строки glob'а
без изменения описанной поверхности).

**Next:** item-exec следующего живого item'а фазы **P7** — `P7.3` (`⬜ Not started`,
`Exec = manual`, порядок `P7.1 + P7.3 → P7.2`, P7.1 уже 🟠 Done). Форма «ЗАПУСК ВРУЧНУЮ»
(`/model`+`/effort`+`/task:plan-run`, D18).

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — Routing §3 P7.3 (`implementation/medium`) |
| Context | continue (/clear) — ручной item |
| Суть | Поставить `codex-plugin-cc` как второстепенную явно маршрутизируемую возможность: гейт `skiller budget --first-turn` до/после, процедура вкл/выкл, правило активации |

```
/model sonnet
/effort medium
/task:plan-run 2026.07.25-ECO-OPT P7.3
```

**Done:** **54/54 items в затронутых фазах терминальны** (P1–P6, P8–P11 плюс P7.1; счёт не
менялся закрытием фазы P6 — реопен и P6.4 уже посчитаны прежним handoff'ом, закрытие фазы саму
терминальность items не меняет). Закрыты фазы **P1**
(1/2, 🟢), **P2** (1/3, 🟠), **P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P6** (4/4,
🟠 — закрыта этим заходом), **P8** (7/10, 🟠), **P9** (3/4, 🟠), **P10** (1/4, 🟠), **P11**
(6/8, 🟠). **P7** — `🟡 In progress` (P7.1 🟠 Done, P7.2/P7.3 `⬜`).

**Remaining:** **P7.3** (плагин `codex-plugin-cc`), затем **P7.2** (инструкционный слой по
списку поломок P7.1 + трек 1 OQ-4; потребляет список поломок P7.1 — готов — и числа бюджета
P7.3 — ждёт). Отдельно в очереди висит невыполненный `/task:plan-audit 2026.07.25-ECO-OPT P2`
(унаследовано, этим заходом не проверялось).

**Sources of truth:** `phases/P6.md` `## Phase Status` / `## Phase Handoff` / `## Audit P6 —
2026-07-29` (заход 1 и 2) · `plan.md` §5 D139/D140 · `closure/P6.json` · `roadmap.md:66-67`
(P7.1/P6.4/P7.2 связки) · `phases/P7.md` P7.3 (ТЗ следующего шага).

**Open risks:** унаследованные, ни один не закрыт этим заходом:
(49) `Files` items, правящих `packages/task/commands/*.md`, структурно неполон — не называет
golden-фикстуры и сгенерированный `docs/reference/provider-commands.md`.
(50) Пре-существующий дрейф Codex-проекции (`render-provider-commands.py --check`).
(51) `confidence` в пяти agent-pack ревьюерах не добавлен.
(52) Пункт DoR живёт в ОДНОМ носителе из двух — `SKILL.ru.md` канона `plan-protocol` не тронут.
(53) P6.3: красный `pressure#2` (`general/verify-claims`, коммит `34ae85f1`) остаётся
непочищенным — вне Scope P6, требует отдельного item'а.
(55) Класс «Files не называет машинно-обязательный побочный продукт» (реопен фазы оставляет на
диске `closure/<Pn>.json`, чей гейт краснеет на любую смену статуса item'а, а канон §3 «Phase
reopen — FOUR steps» отчёт закрытия среди носителей НЕ называет) — кандидат `roadmap.md`,
носитель чужой (канон).
(56) Канон §8 разрешает терять незакрытые риски (нет правила переноса `Open risks`/
`Workarounds/Deferred/Open questions` при перезаписи `handoff.md`) — кандидат `roadmap.md` +
машинный чек `plan_lint`.
(57) Конфликт формы launch-блока: канон §8 предписывает нейтральную таблицу, корневой
`AGENTS.md` — нативную форму Codex; адресат — **P7.2**.
(58) Канонический launch-блок корневого `AGENTS.md` не работает на headless-пути (`codex exec`
без `-a`, `codex doctor --json` не принимает `-m`); адресат — **P7.2**.

**Workarounds / Deferred / Open questions:** унаследованные без изменений (F1 roadmap-кандидат,
расхождение flexcrm, апстрим-URL 404, backup-restore, `PreCompact`/`PostCompact` хук вне скоупа
P6 — кандидат roadmap, D53, перекалибровка `skiller budget --first-turn`). Правило дорожки B
(`U`/`P`, D64) окончательно ушло в `roadmap.md` (условие разрешено 2026-07-29, ревью-проба не
проводилась). **Owner-вопрос P7.2 (судьба per-package `AGENTS.md`, D62) остаётся открытым.**

**Дерево на момент handoff:** `git status --porcelain` = ровно два untracked пути,
`.swissknife/` и `packages/task/lib/.claude/` — унаследованные, не идентифицированы как продукт
этого захода, оставлены как есть. Всё остальное закоммичено вплоть до `7e7f1539` (роадмап-шапка
v0.24.0), плюс bookkeeping-коммит этого закрытия фазы P6.
