# HANDOFF — 2026-07-29 — after P7

**Фаза P7 закрыта повторно `🟠 Done with deviations`** (реконсиляция `plan-close`, не новое
исполнение). Все шесть items терминальны: P7.1 🟠, P7.2 🟢, P7.3 🟠, P7.4 🟠, P7.5 🟠, P7.6 🟠 —
доска `1/6` (зелёных), все 6/6 items терминальны. Ремедиация реопена D144 (аудит RED) доведена до конца батчем B7R (P7.4/P7.5/P7.6,
детали в предыдущей версии этого файла и Completion Notes item'ов); эта реконсиляция:
- переписала `## Phase Handoff` фазы P7 БЕЗ маркера `> УСТАРЕЛ` — финальный агрегат Known
  Deviations (грепом полей шести items: P7.1 — 6 записей, P7.2 — пусто, P7.3 — 2, P7.4 — 1,
  P7.5 — 2, P7.6 — 2);
- синхронизировала `## 4. Phase Index & Status Board` `plan.md` (`P7 1/6 🟠 Done with
  deviations`) и `## 0. Meta` (`Status: 🟠 Done with deviations`, `Last Updated`);
- перегенерировала `closure/P7.json` целиком: все шесть статусов items, `phase_status`,
  `git`/`inputs_sha256` на текущее дерево, `limitations[]` (перенесены обе записи из версии
  design-захода — граница P7.3/D146 и P7.1 synthetic — плюс новая про self-reference
  P7.5/P7.6), `metrics.items_green_of_total = 1/6` — снимает накопленный `items[]`-ERROR
  линтера (K=3 → 0 после этой перезаписи);
- прогнала `plan-lint --baseline HEAD` (0 ERROR новых, 28 WARN — baseline) и
  `verify-citations.py --strict` (16 находок, все унаследованные `phases/P11.md`, 0 новых).

**Все 11 фаз плана теперь терминальны — план `2026.07.25-ECO-OPT` закрыт ЦЕЛИКОМ**
(`## 4. Phase Index & Status Board`: P1 🟢, P2/P3/P4/P5/P6/P7/P8/P9/P10/P11 🟠 — все
Done/Done with deviations). `plans/ACTIVE.md` сброшен на `—`.

**Next:** план закрыт.

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low |
| Context | NEW SESSION — шаг-не-item |
| Суть | Архивировать терминальный план целиком (перенос plans/<ID> → plans/archive/<ID> + миграция root/ → docs) |

```
/task:plan-close archive 2026.07.25-ECO-OPT
```

**Done:** все 56 items плана (P1–P11) терминальны, все 11 фаз терминальны, план закрыт целиком
этим заходом.

**Remaining:** архивация плана (`/task:plan-close archive 2026.07.25-ECO-OPT`) — решение
владельца, вне протокола обязательности. Отдельно унаследован невыполненный
`/task:plan-audit 2026.07.25-ECO-OPT P2` (owner-приоритет, не блокирует архивацию).

**Sources of truth:** `phases/P7.md` (`## Audit P7 — 2026-07-29` — находки F1–F13, все
адресованы; `## Phase Handoff` — финальный агрегат без маркера `УСТАРЕЛ`; Completion Notes
P7.1/P7.2/P7.3/P7.4/P7.5/P7.6) · `research/29-P7-reopen-2026-07-29-remediation-map.md` (карта
правок, исполнена целиком) · `plan.md` §0 Meta (`Status`), §4 Status Board (все 11 фаз
терминальны), §5 D144/D145/D146, §6 Update Log · `closure/P7.json` (перегенерирован, согласован
со статусами) · `plans/ACTIVE.md` (`—`).

**Open risks:** унаследованные без изменений (49)–(67) из предыдущего handoff (перенесены
руками — канон §8 их перенос не гарантирует, см. (56)):
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
`AGENTS.md` — нативную форму Codex; починен P7.2 — риск снят фактом.
(58) Канонический launch-блок корневого `AGENTS.md` не работал на headless-пути; починен
P7.2/P7.4 — headless-форма `codex exec` добавлена и приведена к валидному флагу; риск снят
фактом.
(60) Две оценки цены (плагин/проект) имеют разную природу и разных оценщиков — их сумма
остаётся ОЦЕНКОЙ; `claude plugin details` без `--json`, формат может измениться.
(61) Правило отката (три ветви) и правило активации плагина (D84) живут ТЕКСТОМ, машинного
гейта у обоих нет — названо явно.
(62) **Унаследованный:** `verify-citations --strict` даёт 16 находок (все в `phases/P11.md`),
новых от закрытия P7 — 0. Остаток вне скоупа, владелец не назначен.
(63) Поломки P7.1 №3 (`Files` реопененной фазы не называет `closure/<Pn>.json`) и №4 (перенос
`Open risks` при перезаписи `handoff.md` не гарантирован каноном) остаются живым риском канона
`plan-protocol` — носитель чужой (`roadmap.md` § «Добавлено прогоном P7.1»).
(64) Численный пилот делегирования (дорожки A/B, `research/16-P7-target-design.md` §2)
сознательно не запускался (D84) — экономика делегирования остаётся неизмеренной.
(65) Граница D145 («авто-драйв — контур DUAL-PROVIDER, D143(2) — режим теста P7.1») держится
ТЕКСТОМ; машинного гейта у неё нет, расхождение практики обнаружится только инцидентом.
(66) `/codex:rescue` как поверхность остаётся НЕПРОВЕРЕННОЙ (D146) — верифицирован только путь
кода `codex-companion.mjs task`; следующий заход, которому обёртка понадобится, обязан считать
её непроверенной, а не выводить проверенность из статуса.
(67) F11 (ложный скоуп `feat(root,task)` в сообщении коммита `cccec4eb`) сознательно не чинится
— история git неизменяема, компенсирующей записи аудит не требовал.
**Сняты этим заходом:** прежние (68)/(69) («`closure/P7.json` items[] несогласован» и «Validation
self-reference буквально не сошлась») — оба были структурными дырами реконсиляции, а не
предметными рисками; закрытие фазы синхронизировало `closure/P7.json` (K=0) и объяснило
self-reference в Known Deviations P7.5/P7.6 — дальнейшего действия не требуют.

**Workarounds / Deferred / Open questions:** обходок этим заходом не вводилось. Отложено:
`open-questions.md` без изменений (OQ-2 `Resolved → D84`, OQ-4 `Resolved → трек 1 закрыт P7.2`).

**Дерево на момент handoff:** `git status --porcelain` несёт унаследованные untracked
`.swissknife/` и `packages/task/lib/.claude/` (runtime-артефакты analyst/task, посторонний дифф
— не наш, вне `Files` этой реконсиляции). Правки этой реконсиляции — `plan.md`, `phases/P7.md`,
`closure/P7.json`, `handoff.md`, `plans/ACTIVE.md`, `journal.jsonl` — коммитятся одним закрытием
фазы (§8, только плановые пути).

## Архивация (2026-07-29)

План перенесён `plans/2026.07.25-ECO-OPT` → `plans/archive/2026.07.25-ECO-OPT`.

**Чек-лист миграции `root/` → docs:**
- `root/adr/ADR-0001-cross-machine-memory.md` → перенесён в
  `packages/maind/docs/adr/ADR-0001-cross-machine-memory.md`, со ссылкой из
  `packages/maind/docs/architecture.md` (раздел «Cross-machine память»).

**Осталось в архиве** (не мигрирует в docs): `artifacts/`, `findings/`, `research/`,
`brief/`, `closure/`, `open-questions.md`, `roadmap.md`, `journal.jsonl`, `plan.md`,
`phases/*`.

**Реестры/ссылки обновлены** на `plans/archive/2026.07.25-ECO-OPT/...`:
`docs/develop.md`, `docs/deploy.md`, `docs/reference.md`, `docs/rejected-optimizations.md`,
`packages/maind/docs/guide/memory.md`, `packages/skiller/docs/guide/profiles.md`,
`packages/skiller/docs/guide/bucket-audit-2026-07.md`,
`packages/harness/configs/claude-code/agent-packs/README.md`, `plans/README.md`.
`plans/ACTIVE.md` уже указывал `—` до архивации (план закрыт целиком раньше этой команды).
