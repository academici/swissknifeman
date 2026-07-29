# HANDOFF — 2026-07-29 — after P7.3

**P7.3 закрыт 🟢 Done (`plan-run`, доисполнение по D142).** Остаток Scope доисполнен в этом
заходе: `claude plugin details codex@openai-codex` перепрогнан дословно (~449 ток always-on,
совпадает байт-в-байт с ранее снятым) · целостность `~/.codex/hooks.json` подтверждена (все три
хука — `log-bash-command`, `block-daemon-ops`, `review-gate` — на месте, `codex exec` отработал
без ошибок хука) · процедура вкл/выкл прогнана ФАКТИЧЕСКИ в обе стороны (`claude plugin
disable/enable codex@openai-codex`, подтверждено `enabledPlugins` до/после) · проба
маршрутизированного вызова в отдельном worktree (`codex-companion.mjs task --model
gpt-5.6-terra --effort low`, фактические `model`/`effort` подтверждены сырой сессией Codex) ·
`findings/P7.3-plugin-cost-and-procedure.md` написан (обе цены врозь · процедура · правило
активации дословно + строка «машинного гейта нет» · сработавшая ветвь правила отката — ветвь 2,
`T_before`=13915>10000, отката нет) · буллет `CLAUDE.md` §«Философия и рамки» стал
двухинструментным (+111 ток `claude_md`, ≤150) · строка `docs/rejected-optimizations.md` + стаб
`roadmap/budget-first-turn-plugin-visibility.md` с названным критерием вытягивания. Item-коммит
`102d6765` (три файла вне `plans/**`). Одна process-девиация: проба маршрутизированного вызова
сделана прямым вызовом `codex-companion.mjs task` (та же механика, что делает `/codex:rescue`),
а не через саму slash-команду/субагента — названо честно в Known Deviations, не подогнано.

**Docs-sync:** не требуется — правки `docs/` этого захода (строка в
`docs/rejected-optimizations.md`) зонтичные, а не per-package; `scripts/docs-sync.sh` их не
касается.

**Next:** run-items: task:plan-run 2026.07.25-ECO-OPT P7.2 — ТЗ P7.2 уже полностью
специфицировано (не скелет), `plan-design` первым не требуется.

| Параметр | Значение |
|:--|:--|
| Model class | implementation (Claude Sonnet 5) |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | Инструкционный слой по итогам P7.1 (список поломок) + P7.3 (числа бюджета, правило активации плагина): router-таблица + untrusted-строка в корневом `AGENTS.md`, D-запись роли Codex, вердикт в `docs/reference.md`, закрытие `roadmap/codex-subagent-offload.md`, owner-вопрос per-package `AGENTS.md` (D62) |

```
/task:plan-run 2026.07.25-ECO-OPT P7.2
```

**Done:** **55/55 items в фазах P1–P6/P8–P11 + P7.3 терминальны.** Фаза P7 несёт P7.1 `🟠 Done
with deviations`, P7.2 `⬜ Not started`, **P7.3 `🟢 Done`** (этим заходом: обе цены гейта
предъявлены врозь, целостность хуков и процедура вкл/выкл проверены фактически, проба
маршрутизированного вызова подтверждена сырой сессией Codex, `CLAUDE.md`/
`rejected-optimizations`/`roadmap/` носители границы правлены). Фаза P7 — 1/3 (🟡 In progress,
ждёт P7.2).

**Remaining:** **P7.2** — тонкий инструкционный слой (потребляет список поломок P7.1 и числа
бюджета P7.3, оба готовы) → фаза P7 терминальна → `/task:plan-close 2026.07.25-ECO-OPT P7`.
Отдельно в очереди висит невыполненный `/task:plan-audit 2026.07.25-ECO-OPT P2` (унаследовано,
этим заходом не проверялось).

**Sources of truth:** `phases/P7.md` P7.3 Completion Notes (полный ход доисполнения, коды
границ, командные выводы) · `findings/P7.3-plugin-cost-and-procedure.md` (обе цены, процедура,
правило активации, ветвь отката) · `findings/P7.3-budget-tool-boundary.md` (почему инструмент
слеп) · `research/28-P7.3-redesign-2026-07-29.md` §2.3 (формула правила отката) ·
`docs/rejected-optimizations.md` (новая строка D142) · `roadmap/budget-first-turn-plugin-visibility.md`
(критерий вытягивания) · `plan.md` §5 D141/D142 · item-коммит `102d6765`.

**Open risks:** унаследованные; риск (59) закрыт этим заходом:
(59) **ЗАКРЫТ.** Гейт `skiller budget --first-turn` не видит marketplace-плагины Claude Code
структурно — буллет `CLAUDE.md` §«Философия и рамки» теперь называет второй измеритель
(`claude plugin details`) и правило дельты; `docs/rejected-optimizations.md` фиксирует, почему
`budget.py` не расширяется; `roadmap/` держит отложенную цель (стаб с критерием). Правка сделана
и закоммичена (`102d6765`), риск снят фактом.
(49) `Files` items, правящих `packages/task/commands/*.md`, структурно неполон — не называет
golden-фикстуры и сгенерированный `docs/reference/provider-commands.md`.
(50) Пре-существующий дрейф Codex-проекции (`render-provider-commands.py --check`).
(51) `confidence` в пяти agent-pack ревьюерах не добавлен.
(52) Пункт DoR живёт в ОДНОМ носителе из двух — `SKILL.ru.md` канона `plan-protocol` не тронут.
(53) P6.3: красный `pressure#2` (`general/verify-claims`, коммит `34ae85f1`) остаётся
непочищенным — вне Scope P6, требует отдельного item'а.
(55) Класс «Files не называет машинно-обязательный побочный продукт» — кандидат `roadmap.md`,
носитель чужой (канон).
(56) Канон §8 разрешает терять незакрытые риски при перезаписи `handoff.md` — кандидат
`roadmap.md` + машинный чек `plan_lint`.
(57) Конфликт формы launch-блока: канон §8 предписывает нейтральную таблицу, корневой
`AGENTS.md` — нативную форму Codex; адресат — **P7.2**.
(58) Канонический launch-блок корневого `AGENTS.md` не работает на headless-пути; адресат —
**P7.2**.
(60) Две оценки цены (плагин/проект) имеют разную природу и разных оценщиков — их сумма
остаётся ОЦЕНКОЙ; `claude plugin details` без `--json`, формат может измениться — вывод
прикладывается дословно (закрыто фактически: см. `findings/P7.3-plugin-cost-and-procedure.md`
§1, §2 — митигация применена этим заходом, риск остаётся названным на будущее).
(61) Правило отката (три ветви) и правило активации плагина (D84) живут ТЕКСТОМ, машинного
гейта у обоих нет — названо явно и в `findings/P7.3-plugin-cost-and-procedure.md` §6/§7.
(62) **Унаследованный:** `verify-citations --strict` даёт 16 находок (все в `phases/P11.md`),
идентичны до и после этого захода — новых от диффа 0. Остаток вне скоупа, владелец не назначен.
**Owner-вопрос P7.2 (судьба per-package `AGENTS.md`, D62) остаётся открытым.**

**Workarounds / Deferred / Open questions:** унаследованные без изменений (F1 roadmap-кандидат,
расхождение flexcrm, апстрим-URL 404, backup-restore, `PreCompact`/`PostCompact` хук вне скоупа
P6 — кандидат roadmap, D53). Правило дорожки B (`U`/`P`, D64) в `roadmap.md`. Новый deferred:
«единый измеритель always-on» — стаб `roadmap/budget-first-turn-plugin-visibility.md` создан
этим заходом, критерий вытягивания — второй независимый прецедент установки marketplace-плагина.

**Дерево на момент handoff:** `git status --porcelain` несёт унаследованные untracked
`.swissknife/` и `packages/task/lib/.claude/` (не идентифицированы как продукт этого захода,
оставлены как есть, посторонний дифф — не наш). Item-коммит P7.3 — `102d6765` (три файла вне
`plans/**`). Bookkeeping-коммит по `plans/2026.07.25-ECO-OPT/**` — следующим шагом этого же
захода.
