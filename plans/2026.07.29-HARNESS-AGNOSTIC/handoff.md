# HANDOFF — 2026-07-30 — after P5.1

**Next:** ЗАПУСК ВРУЧНУЮ: Opus 5/high — P5.2 (frontier/high, `Exec = manual`, routing-гейт §3),
локальный `git merge --no-ff` ветки изоляции в основное дерево.

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — единственная необратимая внутрь граница плана: решение «продолжать/откат по якорю» принимается на месте по смоуку (§3 Routing P5.2) |
| Context | continue (/clear) — ручной item |
| Суть | Зафиксировать якорь отката, слить `next/harness-agnostic` в `main` (`--no-ff`, ОСНОВНОЕ дерево), прогнать пять `validate.sh`+`core/tests`, немедленный смоук флота прежним контуром |

```
ЗАПУСК ВРУЧНУЮ: Opus 5/high — открой plans/2026.07.29-HARNESS-AGNOSTIC/phases/P5.md,
исполни P5.2 «Локальный merge ветки изоляции в основное дерево» СТРОГО в ОСНОВНОМ рабочем
дереве (/home/vostrikov/projects/packages/swissknifeman, НЕ в этом worktree) по её
Scope Included/Inputs/Validation дословно, затем закрой item через
/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P5.2
```

**Session:** Sonnet 5/high — исполнение P5.1 (в дереве изоляции) + `plan-close` реконсиляция.

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 закрыта `plan-close`'ом (9/9 — 5 🟢 + 4 🟠,
`🟠 Done with deviations`) · P3 закрыта `plan-close`'ом (6/6 — 0 🟢 + 6 🟠,
`🟠 Done with deviations`), аудит P3 проведён (ATTENTION) и реконсилирован · P4 закрыта
`plan-close`'ом (5/5 — 4 🟢 + 1 🟠, `🟠 Done with deviations`) · **P5.1
`🟠 Done with deviations` этим заходом** — все локальные эквиваленты CI-гейтов зелёные
(пять `validate.sh` · `core/tests` 251 · `docs-impact` · `status-check` 25 строк ·
`public-hygiene` 0 нарушений · `provider-docs --check`), сводная запись `[Unreleased]`
`CHANGELOG.md`, пять новых строк `docs/status.md` (Evidence — прогнанные команды),
docs-maintenance-вердикт (новая `packages/harness/docs/reference/execution-policy.md` +
строка `cli.md`), разделы «Возврат в основное дерево»/«Снятие и откат»
`root/isolation-procedure.md`, закоммиченный снимок флота «ДО»
(`artifacts/P5.1-fleet-baseline/`, резолв старого контура доказан). Material deviation:
дифф вышел за `Files` item'а — по решению owner чинил пять пре-существующих/P2-производных
красных гейтов сайд-патчем вместо эскалации (детали — Completion Notes P5.1).

**Карта «item → коммит» (P2, реконсилировано 2026-07-30, аудит P2, находка F1):**
P2.1 `ed306ca6` · P2.2 `632e75d3`(+`ad325a5e`) · P2.3 `c97e5cfb`(+`3e883a68`) ·
P2.4 `cf1498a1`(+`966d7764`) · P2.5 `fa826d47` · P2.6 `317622c0`+`23c1090c` · P2.7 `e16082a1` ·
P2.8 `a264a339` · P2.9 `ffda7173`.

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` · P3.5 `1373fccf` · P3.6 —
без item-коммита (законный исход «покрыто существующим скиллом», ноль диффа зафиксирован).

**Карта «item → коммит» (P4):** P4.1 `7ed90cd0` · P4.2 `4d70e7a1` · P4.3 `95ab0492` ·
P4.4 `c20d40af`(+`65343d45`) · P4.5 `58845143`.

**Карта «item → коммит» (P5):** P5.1 — пять коммитов: `e42cd412` (тест-фикстуры
core/maind), `11fbf79e` (реестр skiller + канон каркаса), `485b9702` (CHANGELOG+status.md),
`fab160fc` (docs-maintenance), `503dc68d` (isolation-procedure + снимок флота).

**Remaining:** P5.2 и P5.3 (⬜ Not started) — единственные нетерминальные items плана. Итого
**2 из 35** items плана не исполнено. Сверх items остаётся **рекомендованный аудит фазы P2**
(`/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P2`), владельцем не запускался; не блокирует
P5.2/P5.3. **P5.2 исполняется в ОСНОВНОМ рабочем дереве** (`/home/vostrikov/projects/packages/
swissknifeman`), не в этом worktree — рабочий дом плана переезжает туда после merge (D46).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D94, §6 Update Log, §4 Status Board — P2
`5/9`, P3 `0/6`, P4 `4/5` все `🟠`, P5 `0/3 🟡 In progress`) ·
`research/09-p5-return-and-fleet-acceptance.md` (карта распространения, инвентарь гейтов,
дисциплина дельты, якоря отката, pre-mortem R1–R7) ·
`root/isolation-procedure.md` (разделы «Возврат в основное дерево»/«Снятие и откат» —
исполняемые последовательности с host-путями) ·
`artifacts/P5.1-fleet-baseline/` (снимок «ДО»: `doctor-before.txt`,
`projects-status-before.json`, `provider-audit-before.json`, `README.md` с якорями SHA
обоих деревьев и доказательством контура) · `phases/P5.md` (Phase Context + контракт фазы,
Completion Notes P5.1) · `research/08-p4-executor-layer-and-policy.md` §9 ·
`research/03-foreman-absorption-inventory.md` §3–§4 ·
`plans/archive/2026.07.18-FOREMAN/root/contracts/driver-plan-protocol.md` ·
`root/contracts/execution-policy-v1.md` · `packages/harness/lib/harness/execpolicy.py` ·
`packages/harness/configs/common/agent-packs/roles.json` ·
`packages/harness/configs/claude-code/agent-packs/_common/agents/orchestrator.md` ·
`roadmap/artifex-thin-wrapper.md` · `root/executor-layer-rescope-v1.md` ·
`phases/P2.md`/`phases/P3.md`/`phases/P4.md` · `roadmap.md` §«Карта запуска» · `journal.jsonl`.

**Open risks:**
- **P5.2 — единственная необратимая внутрь граница плана** (R1): якорь отката (`SHA main`
  ДО merge) обязан быть записан ДО первой мутации; merge — строго в ОСНОВНОМ дереве.
- **Схема парсера НЕ починена — починен только статус документа.** `driver-plan-protocol.md`
  после P4.5 честно объявлен историческим, но §1–§6 остаются описанием канона v2.8.0; строитель
  обвязки обязан переиздать parse-подмножество против канона СВОЕГО дня (предусловие в
  `roadmap/artifex-thin-wrapper.md` §Ограничения). Цена решения записана в `Consequences` D93.
- **«Чем парсится прогон Codex» — открытый вопрос без дома в этом плане** (`[UNVERIFIED]`): §2
  контракта знает только `claude -p`, а канон v2.21.0 несёт два провайдерских рендерера.
- **Delegation contract доказуемо приземлён только для провайдер-нейтрального канона и
  Claude-шаблона; Codex-хост НЕ покрыт** (D92, §5.5): роль `_common.orchestrator` не рендерится
  для Codex по замороженному ограничению `command.workflow-carrier`. Дом долгу НЕ заводится — он
  записан `limitations[1]` каталога capability и §3.12 `root/contracts/codex-parity-verdicts-v1.md`.
- **`decide` не является живой зависимостью** (замер P4.1 на `dde9382a`): машина решений
  `execution-state-machine-v1` существует данными в архиве AR (135 ячеек, 89 207 B), живого модуля
  в `packages/**` нет. Любая формулировка «потребляем `decide`» обязана нести `[UNVERIFIED]` (D91).
- **Приёмка AR формально не выполнена** (его D88/D89/D92): `F1 = 0.96`, `F10 = unknown`, 26/31
  кейсов `unmappable`, Codex-сторона наблюдаемости не пробовалась.
- **`plan-lint`: 0 ERROR / 6 WARN на закрытии P4/P5.1, все шесть — false positive предикатов
  линтера**, не контентные дефекты (см. `phases/P4.md` Completion Notes P4.1). Сужение
  предикатов — правка `packages/task`, дом `roadmap/` либо follow-up fix-item.
- **69 длинных описаний без триггера** в `desc-trigger-burndown.txt` (унаследованный долг P3.5).
- **Структурный перебор фолбэк-бюджета обнаружения Codex** (9/10 профилей) — решение владельца не
  выбрано (OQ-7, D29).
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md` не
  пополнена — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work) — кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10 (ни
  того ни другого)** — измеренный факт в ledger'е P3.2, кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work).
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — merge-режим кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **`phases/P1.md` несёт два остаточных вхождения фразы A7** — историческое свидетельство.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков запрещена.
- **Гейт `[10/10]` живёт только в `packages/harness/scripts/validate.sh`** — OQ-9.
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47).
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.2–P5.3 (P5.1 закрыт).
- **Ruff (`0.15.19`, `F,B`) и python-матрица 3.9–3.13 не прогонялись локально на P5.1** — только
  push/CI даёт полную картину (R2, честно названо в Completion Notes P5.1).
- **`verify-citations.py --strict`: 8 остаточных находок**, все в `phases/P1.md`/`phases/P4.md`/
  `plan.md` (поля закрытых items P1/P4), ни одна не в диффе P5.1 (новых от P5.1: 0) — вне Scope
  этого item'а, кандидат на follow-up-заход.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а. · Доказательство §16/§17 `validate.sh`
  изолированным раннером — вынужденная форма, пока §14 краснеет раньше по порядку.
  · P5.1 починил пять пре-существующих/P2-производных красных гейтов сайд-патчем вне `Files`
  item'а по явному решению owner (детали — Completion Notes P5.1, Known Deviations).
- deferred: **весь остаток супервизора — ОДИН адрес `roadmap/artifex-thin-wrapper.md`** (каркас
  пакета · ядро цикла (предусловие — переиздание parse-подмножества) · retry-лестница ·
  run-folder · unattended-профиль · поведенческий канон супервизора · каналы TG/MAX +
  remote-approve · репортинг в mAInd · пак раскатки · документация · боевой пилот) · замер
  формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` · проекция
  `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` · починка
  order-sensitivity `apply_instructions` (дом P2.8) · фикстурный `provenance` P1.2 · изоляция
  общего state (OQ-5) · round-trip гейт живым прогоном Codex (D3) · структурный перебор листинга
  Codex (заведён P3.4, решение — OQ-7) · общий differ канона ролей (OQ-8) · машинные гейты
  PROMOTE-CANDIDATE · раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) ·
  расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка
  adoption-режима · удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md` ·
  декларативный merge-режим `harness hooks --provider codex` (P2.3) и
  `harness agent-packs --provider codex render` (P2.4) · точная схема Codex `apply_patch` (P2.3) ·
  отдельный machine-owned `check_command` для Codex `review-gate` (P2.3) · CLI-флаг
  `harness doctor --settings --provider codex` (P2.4) · индекс `path-scoped rules` в hub (P3.1) ·
  унификация verification-контрактов паков 4/10→10/10 (P3.2) · добор таблицы внешних источников
  (P3.3) · сокращение 69 длинных описаний, one-way (P3.5) · перевод прозы «кап делегирования» в
  `packages/task/commands/{design,research,review,plan-design}.md` на ссылку к SSOT
  `execution-policy-v1.md` (Scope Excluded P4.2) · рычаг №4 владельца (ECO-OPT D74, OQ-7) ·
  **Codex-досягаемость delegation contract** (D92 — до закрытия capability-разрыва
  `command.workflow-carrier`) · общий differ «канон ↔ инсталляционный шаблон» для ВСЕХ ролей
  (OQ-8, замечен повторно на P4.4) · ruff+python-матрица CI не воспроизведены локально P5.1 (R2).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5 (9/10),
  решение между тремя вариантами открыто · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не
  покрывает `analyst`/`task` (Deferred). OQ-2 закрыта полностью (D71 + D93/D94, исполнено P4.5).
  OQ-3/OQ-6 закрыты D86/D87 (P2.1); OQ-1 — D31; OQ-4 — P3.4/D27.
