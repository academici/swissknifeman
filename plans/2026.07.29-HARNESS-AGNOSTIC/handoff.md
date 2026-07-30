# HANDOFF — 2026-07-30 — after P4

**Next:** exec-items: task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P4.5 — исполнить закрытое
решение D93 по дословным шаблонам `research/08` §9.4

| Параметр | Значение |
|:--|:--|
| Model class | implementation (§3 Routing строка P4.5) |
| Effort | medium |
| Capabilities | — |
| Context | same-session — item |
| Суть | Три текстовые правки без единого открытого решения: блок `## §0` + `status: historical` + `pin_status: expired` в историческом контракте `plans/archive/2026.07.18-FOREMAN/root/contracts/driver-plan-protocol.md` (§1–§6 и `pinned:` неприкосновенны, дифф обязан нести РОВНО одну удалённую строку); пункт «Parse-контракт донора историчен» в §Ограничения и пометка предусловия у п. 2 §Суть спеки `roadmap/artifex-thin-wrapper.md`; отметка об исполнении в §7 Consumed (bookkeeping) |

```
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P4.5
```

**Session:** Claude Opus 5 (1M context)/high — `plan-design` (frontier/high), ре-дизайн ТЗ P4.5
после эскалации; items не закрывались.

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 закрыта `plan-close`'ом (9/9 — 5 🟢 + 4 🟠,
`🟠 Done with deviations`) · P3 закрыта `plan-close`'ом (6/6 — 0 🟢 + 6 🟠,
`🟠 Done with deviations`), аудит P3 проведён (ATTENTION) и реконсилирован · P4.1 закрыт `🟢`
(item-коммит `7ed90cd0`) · P4.2 закрыт `🟢` (item-коммит `4d70e7a1`) · P4.3 закрыт `🟢`
(item-коммит `95ab0492`) · P4.4 закрыт `🟠 Done with deviations` (item-коммит `c20d40af` +
фикс-коммит `65343d45`) · **P4.5 ре-дизайнен этим заходом: эскалация снята (D93/D94), item
`🔴`→`⬜`, фаза P4 `🔴 Blocked`→`🟡 In progress` (3/5)**. Форма исполнения варианта B — контракт
`driver-plan-protocol.md` фиксируется ИСТОРИЧЕСКИМ артефактом, под живой канон не переписывается
и не перепинывается (замер на `300124fc`: ноль машинных потребителей вне архива донора),
обязательство переиздания parse-подмножества перенесено к строителю обвязки предусловием п. 2
`roadmap/artifex-thin-wrapper.md`; дословные шаблоны трёх правок — `research/08` §9.4.

**Карта «item → коммит» (P2, реконсилировано 2026-07-30, аудит P2, находка F1):**
P2.1 `ed306ca6` · P2.2 `632e75d3`(+`ad325a5e`) · P2.3 `c97e5cfb`(+`3e883a68`) ·
P2.4 `cf1498a1`(+`966d7764`) · P2.5 `fa826d47` · P2.6 `317622c0`+`23c1090c` · P2.7 `e16082a1` ·
P2.8 `a264a339` · P2.9 `ffda7173`.

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` · P3.5 `1373fccf` · P3.6 —
без item-коммита (законный исход «покрыто существующим скиллом», ноль диффа зафиксирован).

**Карта «item → коммит» (P4):** P4.1 `7ed90cd0` · P4.2 `4d70e7a1` · P4.3 `95ab0492` ·
P4.4 `c20d40af`(+`65343d45`) · P4.5 — item-коммита ещё нет (ТЗ переписано, исполнение впереди).

**Remaining:** P4.5 (исполнимо сразу, `plan-exec`), затем закрытие фазы P4 и P5 (3 items).
Итого **4 из 35** items плана не исполнено. Сверх items остаётся **рекомендованный аудит фазы P2**
(`/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P2`), владельцем не запускался; он не блокирует P4
(фаза P2 терминальна), но чем дальше уходит exec, тем дороже его находки.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D94, §6 Update Log, §4 Status Board — P2
`5/9`, P3 `0/6` обе `🟠`, P4 `3/5` `🟡`; §7 Consumed — строка `driver-plan-protocol.md` несёт
решение D93) · `research/08-p4-executor-layer-and-policy.md` §9 (разбор трёх форм + ДОСЛОВНЫЕ
шаблоны правок P4.5) · `research/03-foreman-absorption-inventory.md` §3–§4 (таблица пяти якорей,
вердикт OQ-2 D71 + поправка 2026-07-30) ·
`plans/archive/2026.07.18-FOREMAN/root/contracts/driver-plan-protocol.md` (контракт, пин и §1–§6
не тронуты) · `root/contracts/execution-policy-v1.md` (запечатанная схема P4.2) ·
`packages/harness/configs/common/agent-packs/execution-policy.json` (обе точки
`delegation_contract` `enforced`) · `packages/harness/lib/harness/execpolicy.py` (валидатор, P4.3) ·
`packages/harness/configs/common/agent-packs/roles.json` и
`packages/harness/configs/claude-code/agent-packs/_common/agents/orchestrator.md` (носители
приземлённого блока, P4.4) · `phases/P4.md` (Phase Context + контракт фазы, Completion Notes
P4.1–P4.4, ТЗ P4.5) · `root/executor-layer-rescope-v1.md` (граница «строит / не строит») ·
`roadmap/artifex-thin-wrapper.md` (дом остатка супервизора и адрес обязательства переиздания) ·
`phases/P2.md`/`phases/P3.md` (Completion Notes, Phase Handoff) · `roadmap.md` §«Карта запуска» ·
`journal.jsonl`.

**Open risks:**
- **Схема парсера НЕ починена — починен только статус документа.** `driver-plan-protocol.md`
  после P4.5 честно объявлен историческим, но §1–§6 остаются описанием канона v2.8.0; строитель
  обвязки обязан переиздать parse-подмножество против канона СВОЕГО дня (предусловие п. 2
  `roadmap/artifex-thin-wrapper.md`). Цена решения записана в `Consequences` D93.
- **«Чем парсится прогон Codex» — открытый вопрос без дома в этом плане** (`[UNVERIFIED]`): §2
  контракта знает только `claude -p`, а канон v2.21.0 несёт два провайдерских рендерера.

- **Delegation contract доказуемо приземлён только для провайдер-нейтрального канона и
  Claude-шаблона; Codex-хост НЕ покрыт** (D92, §5.5): роль `_common.orchestrator` не рендерится
  для Codex по замороженному ограничению `command.workflow-carrier` — контракт достигает Codex-хоста
  только после закрытия этого capability-разрыва. Отдельный дом долгу НЕ заводится — он записан
  `limitations[1]` каталога capability и §3.12 `root/contracts/codex-parity-verdicts-v1.md`.
- **`packages/skiller/scripts/validate.sh` красный на ОДНОМ предсуществующем гейте** (долг P0.5):
  §14 `ERROR: протухшие переводы SKILL.ru.md→SKILL.md`
  (`skills/repository-bootstrap/package-architecture/SKILL.md`, 225-строчный чужой RU-источник).
  Общий контур репо остаётся красным до починки; чинится одним заходом: перевод +
  `check-translations.sh --stamp` + `skiller registry` + коммит.
- **`decide` не является живой зависимостью** (замер P4.1 на `dde9382a`): машина решений
  `execution-state-machine-v1` существует данными в архиве AR (135 ячеек, 89 207 B), живого модуля
  в `packages/**` нет. Любая формулировка «потребляем `decide`» обязана нести `[UNVERIFIED]` (D91).
- **Приёмка AR формально не выполнена** (его D88/D89/D92): `F1 = 0.96`, `F10 = unknown`, 26/31
  кейсов `unmappable`, Codex-сторона наблюдаемости не пробовалась — четыре долга плюс два наших
  (§4 `root/executor-layer-rescope-v1.md`).
- **`plan-lint`: 0 ERROR / 6 WARN, все шесть — false positive предикатов линтера**, не контентные
  дефекты. Пять — DoR-гейт (SKILL §7) на строке-легенде каждой фазы (`plan_lint.py:1941-1948`).
  Шестая — «фаза P4 заявляет оркестрацию без workflow-скрипта»: `ORCHESTRATION_MARKER_RE`
  (`plan_lint.py:223`) матчит подстроку «оркестрац» в предложении «**Оркестрация НЕ объявляется**».
  Сужение предикатов — правка `packages/task`, дом `roadmap/` либо follow-up fix-item.
- **69 длинных описаний без триггера** в `desc-trigger-burndown.txt` (унаследованный долг P3.5) —
  сокращаются по одному при следующей содержательной правке скилла; критерий держит
  `roadmap/skill-description-quality.md`.
- **Структурный перебор фолбэк-бюджета обнаружения Codex** (9/10 профилей, WARN-гейт `validate.sh`
  §17) — три варианта в `roadmap/codex-skill-listing-fallback-overflow.md`, решение владельца не
  выбрано (OQ-7, D29).
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md` прогоном
  #4 не пополнена — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work) — кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10 (ни
  того ни другого)** — измеренный факт в ledger'е P3.2, кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work).
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — merge-режим кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **`phases/P1.md` несёт два остаточных вхождения фразы A7** вне трёх Files-локаций P2.9 —
  историческое свидетельство, требует D-записи владельца либо остаётся навсегда.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между маркерами
  запрещена навсегда.
- **Гейт `[10/10]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а. · Доказательство §16/§17 `validate.sh`
  изолированным раннером — вынужденная форма, пока §14 краснеет раньше по порядку.
- deferred: **весь остаток супервизора — ОДИН адрес `roadmap/artifex-thin-wrapper.md`** (каркас
  пакета · ядро цикла · retry-лестница · run-folder · unattended-профиль · поведенческий канон
  супервизора · каналы TG/MAX + remote-approve · репортинг в mAInd · пак раскатки · документация ·
  боевой пилот; три критерия внедрения в спеке) · замер формата транскрипта Codex · opt-in флаг
  Claude-половины `git-guardrails` · проекция `writable_roots` из allowlist'а · правка
  `_validate_conflicts`/схемы `obligations` · починка order-sensitivity `apply_instructions` (дом
  P2.8) · фикстурный `provenance` P1.2 · изоляция общего state (OQ-5) · round-trip гейт живым
  прогоном Codex (D3) · структурный перебор листинга Codex (заведён P3.4, решение — OQ-7) · общий
  differ канона ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · регенерация
  `package-architecture` SKILL.ru.md→SKILL.md (долг P0.5, сужен P3.4 до одного файла) · раскатка на
  потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на `analyst`/`task`
  (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима · удаление
  pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md` · декларативный merge-режим
  `harness hooks --provider codex` (P2.3) и `harness agent-packs --provider codex render` (P2.4) ·
  точная схема Codex `apply_patch` (P2.3) · отдельный machine-owned `check_command` для Codex
  `review-gate` (P2.3) · CLI-флаг `harness doctor --settings --provider codex` (P2.4) · индекс
  `path-scoped rules` в hub (P3.1) · унификация verification-контрактов паков 4/10→10/10 (P3.2) ·
  добор таблицы внешних источников (P3.3) · сокращение 69 длинных описаний, one-way (P3.5) ·
  перевод прозы «кап делегирования» в `packages/task/commands/{design,research,review,plan-design}.md`
  на ссылку к SSOT `execution-policy-v1.md` (Scope Excluded P4.2 — вне этой фазы) · рычаг №4
  владельца (ECO-OPT D74, OQ-7) · **Codex-досягаемость delegation contract** (D92 — до закрытия
  capability-разрыва `command.workflow-carrier`) · общий differ «канон ↔ инсталляционный шаблон»
  для ВСЕХ ролей (OQ-8, замечен повторно на P4.4).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5 (9/10),
  решение между тремя вариантами открыто · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не
  покрывает `analyst`/`task` (Deferred). **OQ-2 закрыта полностью: измерение — D71 (вариант B),
  форма исполнения — D93/D94 (исторический артефакт + перенос обязательства к строителю), ТЗ P4.5
  переписано, эскалация снята.** OQ-3/OQ-6 закрыты D86/D87
  (P2.1); OQ-1 — D31; OQ-4 — P3.4/D27.
