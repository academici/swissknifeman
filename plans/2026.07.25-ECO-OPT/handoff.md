# HANDOFF — 2026-07-29 — after P7.3

**P7.3 эскалирован `🔴 Blocked`, D141.** Плагин `openai/codex-plugin-cc` установлен
(marketplace add + install + `/codex:setup --disable-review-gate`, все шаги зелёные) — но
обязательный гейт `skiller budget --first-turn` даёт delta=0 (13915→13915, оба WARN) не
потому что цена нулевая, а потому что пять источников измерителя (`packages/skiller/lib/
skiller/budget.py`) структурно не сканируют marketplace-плагины Claude Code
(`~/.claude/plugins/**`, глобальный `enabledPlugins`) — только project-local `.claude/
{skills,agents,settings.json}` + skiller-собственный реестр. Реальная цена по нативному
`claude plugin details codex@openai-codex` — **~449 ток** always-on, строго положительна.
Отдельно: бюджет проекта был WARN (13915>10000) ДО установки, независимо от плагина —
буквальное правило «total>10000 после ⇒ откат» откатило бы ЛЮБУЮ установку. Owner-решение
2026-07-29: плагин ОСТАЁТСЯ установленным, формальный откат не проводится, эскалация — на
`plan-design` (переписать Validation P7.3 под реальный инструмент + сузить правило отката до
дельты). Подробности — `phases/P7.md` P7.3 blockquote + Completion Notes + `plan.md` §5 D141.

**P6 закрыта `🟠 Done with deviations`** (4/4 items терминальны: P6.1 🟢 · P6.2 🟠 · P6.3 🟠 ·
P6.4 🟠), этим заходом не тронута — контекст из прежнего handoff (архив ниже во «Done»).

**Docs-sync:** не требуется — P7.3 не трогает `docs/` (машинное состояние вне репо, D61).

**Next:** ре-дизайн эскалированного item'а — `/task:plan-design 2026.07.25-ECO-OPT P7.3`.
Причина — blockquote `> 🔴 ESCALATION P7.3` в `phases/P7.md` и Open risk (59) ниже.

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — план-протокол `plan-design`, конфликт правил требует владельческого решения по формулировке Validation |
| Context | NEW SESSION — шаг-не-item |
| Суть | Снять конфликт правил P7.3: переписать Validation под инструмент, видящий marketplace-плагины (`claude plugin details`), и сузить правило отката к дельте ОТ установки, не унаследованному WARN; продолжить Scope Included с шага «процедура вкл/выкл» |

```
/task:plan-design 2026.07.25-ECO-OPT P7.3
```

**Done:** **54/54 items в фазах P1–P6/P8–P11 терминальны**, П7 несёт P7.1 🟠 Done, P7.2 `⬜`,
**P7.3 🔴 Blocked** (этот заход: предстартовая сверка + оба budget-отчёта + установка плагина +
`/codex:setup` — сделаны и зафиксированы; процедура вкл/выкл, целостность хуков, findings-документ,
проба `/codex:rescue` — НЕ начаты). Закрыты фазы **P1** (1/2, 🟢), **P2** (1/3, 🟠), **P3**
(2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P6** (4/4, 🟠), **P8** (7/10, 🟠), **P9**
(3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). **P7** — `🟡 In progress`.

**Remaining:** ре-дизайн **P7.3** снимает конфликт правил → возврат к `plan-run`/`plan-exec` на
недоделанном хвосте Scope (процедура вкл/выкл, целостность хуков, findings, проба `/codex:rescue`).
Затем **P7.2** (инструкционный слой; потребляет список поломок P7.1 — готов — и числа бюджета
P7.3 — теперь есть: ~449 ток реальных). Отдельно в очереди висит невыполненный
`/task:plan-audit 2026.07.25-ECO-OPT P2` (унаследовано, этим заходом не проверялось).

**Sources of truth:** `phases/P7.md` P7.3 (blockquote эскалации + Completion Notes + Pending
Work — точная развилка для `plan-design`) · `plan.md` §5 D141 · `artifacts/P7.3/
budget-first-turn-{before,after}.json` (оба 13915/WARN) · `packages/skiller/lib/skiller/
budget.py:170-236` (пять `_measure_*` — репо-факт слепоты к marketplace-плагинам) ·
`~/.claude/settings.json` `enabledPlugins`/`extraKnownMarketplaces` (машинный факт установки,
вне репо, D61).

**Open risks:** унаследованные + новый (59), ни один не закрыт этим заходом:
(59) **Гейт `skiller budget --first-turn` не видит marketplace-плагины Claude Code
структурно** (project-local сканеры, не глобальный `~/.claude/plugins/**`/`enabledPlugins`) —
любой будущий item, устанавливающий плагин, наступит на тот же конфликт правил, что и P7.3;
кандидат: явная граница применимости инструмента в его же доке/help ИЛИ отдельный roadmap-item
расширения (не Scope P7.3 — `budget.py` stdlib-only, правка пакета требует своего item'а).
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
этого захода, оставлены как есть; плюс untracked `plans/2026.07.25-ECO-OPT/artifacts/P7.3/`
(два JSON-отчёта budget, добавляются этим же bookkeeping-коммитом). Всё остальное закоммичено
вплоть до `52b4e1c7` (закрытие фазы P6), плюс bookkeeping-коммит этой эскалации P7.3.
Item-коммита нет: Scope Included не поставлен (эскалация до завершения), пакеты монорепо этот
заход не трогал.
