# HANDOFF — 2026-07-29 — after P7.2

**P7.2 закрыт 🟢 Done (`plan-run`, sonnet/high).** Router-таблица (`Operation | Canonical
procedure`, приём A2) + untrusted-import инвариант (приём F1) внесены секцией `## Operation
router` корневого `AGENTS.md`. Четыре поломки dogfood-прогона P7.1 (`findings/
P7.1-switch-test.md` §6) починены по адресу: №1 headless launch-форма для `codex exec` (нет
флага `-a`, подтверждено context7 `/openai/codex` — `-a`/`--ask-for-approval` объявлен только
в TUI CLI, `codex exec` использует `SharedCliOptions` без него); №2 preflight больше не
предписывает `codex doctor --json` для model/effort (структурно не умеет `-m`) — источник
истины теперь сама запущенная команда; №5 launch-block для plan-protocol-работы объявлен
MANDATORY нейтральной таблицей (с `Capabilities`) поверх нативной; №6 форма `Next` — через
роутер к канону `general/plan-protocol` §8. Поломки №3/№4/№7 (чужой носитель — канон/применение)
уже внесены в `roadmap.md` § «Добавлено прогоном P7.1» закрытием P7.1, здесь не дублировались.
Owner-вопрос (судьба per-package `AGENTS.md`, D62) снят: владелец делегировал выбор с критерием
«без хвостов, агенты работают идеально» → вариант D62(3)-b, правило `-C packages/<name>` в
router-таблице. D143 фиксирует операционную форму роли «второй водитель» с полем `Consequences`.
Вердикт записан при любом исходе: `docs/reference.md` (строка + карточка с числами
`findings/P7.3-plugin-cost-and-procedure.md`), `roadmap/codex-subagent-offload.md` закрыт
датированным вердиктом. `open-questions.md`: OQ-2 подтверждён `Resolved → D84` (owner-вопрос
закрыт), OQ-4 `Resolved → трек 1 закрыт P7.2`. Размер `AGENTS.md` — 7 252 б против потолка
32 768 б (запас ≈78%). Item-коммит `cccec4eb` (7 файлов вне `plans/**` + `research/21` +
`open-questions.md`); bookkeeping-коммит — следующим шагом этого же захода.

**Фаза P7 ТЕРМИНАЛЬНА** (2/3 🟢, 1/3 🟠: P7.1 `🟠`, P7.2 `🟢`, P7.3 `🟢`) — фазовое закрытие
отдельным `/task:plan-close`, не входит в `plan-run`.

**Docs-sync:** не требуется — правки `docs/` этого захода (`docs/reference.md`) зонтичные, а не
per-package; `scripts/docs-sync.sh` их не касается.

**Next:** фаза P7 терминальна (все три item'а закрыты) → `/task:plan-close 2026.07.25-ECO-OPT P7`
(шаг-не-item, реконсиляция по git-фактам + Phase Handoff + lint).

| Параметр | Значение |
|:--|:--|
| Model class | implementation (Claude Sonnet 5) |
| Effort | low (пин команды `plan-close`) |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P7: сверить статусы items с git-фактами, написать Phase Handoff, прогнать lint |

```
/task:plan-close 2026.07.25-ECO-OPT P7
```

**Done:** **57/57 items в фазах P1–P6/P8–P11 + P7.1–P7.3 терминальны.** Фаза P7 несёт P7.1
`🟠 Done with deviations`, P7.2 `🟢 Done` (этот заход), P7.3 `🟢 Done` — все три терминальны,
фаза P7 сама ждёт формального закрытия (`Phase Handoff` не написан, `closure/P7.json` не
заведён — обязанность следующего `plan-close`).

**Remaining:** формальное закрытие фазы **P7** (`/task:plan-close`). Отдельно в очереди висит
невыполненный `/task:plan-audit 2026.07.25-ECO-OPT P2` (унаследовано, этим заходом не
проверялось).

**Sources of truth:** `phases/P7.md` P7.2 Completion Notes (полный ход, коды границ, командные
выводы) · `research/21-P7.2-instruction-slice-spec.md` (целевой файл, якорь, формулировки,
поимённое соответствие 7 поломок, размер до/после) · `findings/P7.1-switch-test.md` §5–§6 (вердикт
и поломки) · `artifacts/P7.1/breakage-log.md` (полный журнал с адресами) · `plan.md` §5 D62/D84/
D143 · `open-questions.md` OQ-2/OQ-4 · item-коммит `cccec4eb`.

**Open risks:** унаследованные без изменений плюс два новых, названных этим заходом:
(63) **НОВЫЙ.** Поломки P7.1 №3 (`Files` реопененной фазы не называет `closure/<Pn>.json`) и №4
(перенос `Open risks` при перезаписи `handoff.md` не гарантирован каноном) остаются живым риском
канона `plan-protocol` — носитель чужой (`roadmap.md` § «Добавлено прогоном P7.1»), эта фаза их
не правит (D84). Следующий догфуд-заход на реопененной фазе или на потере рисков может их
повторить.
(64) **НОВЫЙ.** Численный пилот делегирования (дорожки A/B, `research/16-P7-target-design.md`
§2) сознательно не запускался этим заходом (D84) — экономика делегирования остаётся неизмеренной;
готовый протокол не устарел, вытягивается отдельным заходом по факту потребности.
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
`roadmap.md` + машинный чек `plan_lint` (этот риск сам демонстрируется списком выше — перенесён
руками, не машиной).
(57) Конфликт формы launch-блока: канон §8 предписывает нейтральную таблицу, корневой
`AGENTS.md` — нативную форму Codex; **починен этим заходом** (P7.2) — launch-block теперь
объявляет нейтральную таблицу MANDATORY поверх нативной; риск снят фактом.
(58) Канонический launch-блок корневого `AGENTS.md` не работает на headless-пути; **починен
этим заходом** (P7.2) — headless-форма `codex exec` добавлена; риск снят фактом.
(60) Две оценки цены (плагин/проект) имеют разную природу и разных оценщиков — их сумма
остаётся ОЦЕНКОЙ; `claude plugin details` без `--json`, формат может измениться.
(61) Правило отката (три ветви) и правило активации плагина (D84) живут ТЕКСТОМ, машинного
гейта у обоих нет — названо явно.
(62) **Унаследованный:** `verify-citations --strict` даёт 16 находок (все в `phases/P11.md`),
идентичны до и после этого захода — новых от диффа 0. Остаток вне скоупа, владелец не назначен.

**Workarounds / Deferred / Open questions:** унаследованные без изменений (F1 roadmap-кандидат,
расхождение flexcrm, апстрим-URL 404, backup-restore, `PreCompact`/`PostCompact` хук вне скоупа
P6 — кандидат roadmap, D53). Правило дорожки B (`U`/`P`, D64) в `roadmap.md`. «Единый измеритель
always-on» — стаб `roadmap/budget-first-turn-plugin-visibility.md` (P7.3). Numeric-пилот
делегирования (дорожки A/B) — deferred, протокол в `research/16-P7-target-design.md` §2.

**Дерево на момент handoff:** `git status --porcelain` несёт унаследованные untracked
`.swissknife/` и `packages/task/lib/.claude/` (не идентифицированы как продукт этого захода,
оставлены как есть, посторонний дифф — не наш). Item-коммит P7.2 — `cccec4eb`. Bookkeeping-коммит
по `plans/2026.07.25-ECO-OPT/**` — следующим шагом этого же захода.
