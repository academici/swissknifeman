# HANDOFF — 2026-07-30 — after P5.2

**Next:** ЗАПУСК ВРУЧНУЮ: Opus 5/high — P5.3 (frontier/high, `Exec = manual`, routing-гейт §3),
реинсталл контура из основного дерева, дельта флота против снимка «ДО», снятие изоляции.

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — вердикт «расхождение дельты объяснимо или это находка» открыт, а снятие изолированного контура делает ошибку вердикта дорогой (§3 Routing P5.3) |
| Context | continue (/clear) — ручной item |
| Суть | `./install.sh` из основного дерева, снимок «ПОСЛЕ» теми же тремя командами, `artifacts/P5.3-fleet-delta.md`, read-only `maind sync --dry-run` по трём проектам разных namespace, и ТОЛЬКО последним шагом — снятие worktree и `bin-skm-next` |

```
ЗАПУСК ВРУЧНУЮ: Opus 5/high — открой plans/2026.07.29-HARNESS-AGNOSTIC/phases/P5.md,
исполни P5.3 «Реинсталл контура, дельта флота, снятие изоляции» СТРОГО в ОСНОВНОМ рабочем
дереве (/home/vostrikov/projects/packages/swissknifeman) по её Scope Included/Inputs/
Validation дословно, затем закрой item через
/task:plan-close 2026.07.29-HARNESS-AGNOSTIC P5.3
```

**Session:** Opus 5/high — исполнение P5.2 (в ОСНОВНОМ дереве) + `plan-close` реконсиляция.

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 закрыта `plan-close`'ом (9/9 — 5 🟢 + 4 🟠,
`🟠 Done with deviations`) · P3 закрыта `plan-close`'ом (6/6 — 0 🟢 + 6 🟠,
`🟠 Done with deviations`), аудит P3 проведён (ATTENTION) и реконсилирован · P4 закрыта
`plan-close`'ом (5/5 — 4 🟢 + 1 🟠, `🟠 Done with deviations`) · P5.1 `🟠 Done with deviations`
(локальные эквиваленты CI-гейтов зелёные, релизные носители закрыты, снимок флота «ДО»
закоммичен) · **P5.2 `🟠 Done with deviations` этим заходом.**

**Что сделал P5.2 (граница внутрь пересечена).** Якорь отката снят ДО первой мутации:
`main` = **`8e16a811`**, 1473 коммита. `git merge --no-ff next/harness-agnostic` в ОСНОВНОМ
дереве — merge-коммит **`56eae069`**, два родителя (`8e16a811 acf73d61`, следовательно не
fast-forward), конфликтов нет, 1473 → 1576 коммитов; `--squash`/rebase/`--amend` не
применялись, провенанс пяти фаз сохранён. Пост-мердж валидация в основном дереве зелёная:
пять `validate.sh` (skiller · harness · maind 534 теста · analyst 256 · task `plan-lint OK`)
+ `core/tests` 251 тест, python `3.12.3`. Смоук флота ПРЕЖНИМ контуром (префикса
`bin-skm-next` в `PATH` нет; `readlink -f` → `…/swissknifeman/bin/swissknifeman`):
`swissknifeman doctor` — 105 строк против 105 в базлайне, вердикт идентичен построчно
(`Проблем: 2` · `harness: OK` · `Все проверки пройдены.` · `Окружение готово.`), расходятся
РОВНО две строки — HEAD `8e16a811`→`56eae069` и sha реестра `041735a37bd6`→`b4675c93e617`,
обе обязательны как следствие merge; перечень 18 отставших хабов совпал дословно.
`plan-lint` — 0 ошибок / 8 предупреждений, ровно тот же счёт, что на пред-мердж дереве ветки
(0 новых ERROR, 0 новых WARN). **Рабочий дом плана переехал в основное дерево (D46):** оба
коммита item'а сделаны там, ветка `next/harness-agnostic` после `acf73d61` коммитов не
принимала и НЕ удалена (второй, независимый от reflog якорь отката).

**⚠️ Граница наружу НЕ пересечена и остаётся у владельца:** `git push`, PR, тег, релиз и
публикация доков не выполнялись ни разу (Scope Excluded фазы P5, D41). `main` несёт результат
всех пяти фаз **только локально**.

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
`fab160fc` (docs-maintenance), `503dc68d` (isolation-procedure + снимок флота) — все в ветке.
P5.2 — **`56eae069`** (merge-коммит) + **`44864fec`** (носитель: факты прогона и исправленный
шаг 3 в `root/isolation-procedure.md`) — оба в `main`, в ОСНОВНОМ дереве.

**Remaining:** **P5.3 (⬜ Not started) — единственный нетерминальный item плана.** Итого
**1 из 35** items плана не исполнено. Сверх items остаётся **рекомендованный аудит фазы P2**
(`/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P2`), владельцем не запускался; не блокирует
P5.3. **P5.3 исполняется в ОСНОВНОМ рабочем дереве** — снимаемое дерево
(`swissknifeman-next`) не должно быть рабочим каталогом сессии.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D94, §6 Update Log, §4 Status Board — P2
`5/9`, P3 `0/6`, P4 `4/5` все `🟠`, P5 `0/3 🟡 In progress`) ·
`research/09-p5-return-and-fleet-acceptance.md` (карта распространения, инвентарь гейтов,
дисциплина дельты, якоря отката, pre-mortem R1–R7) ·
`root/isolation-procedure.md` (§«Возврат в основное дерево» с таблицей «Факты прогона P5.2»
и исправленным шагом 3; §«Снятие worktree и откат» — исполняемая последовательность P5.3 с
host-путями) · `artifacts/P5.1-fleet-baseline/` (снимок «ДО»: `doctor-before.txt`,
`projects-status-before.json`, `provider-audit-before.json`, `README.md` с якорями SHA
обоих деревьев, доказательством контура и ПОИМЁННЫМ перечнем волатильных полей) ·
`root/contracts/provider-parity-definition.md` (критерий приёмки паритета) ·
`docs/provider-support.md` §«Security and operations` (перечень неразрушающих проверок) ·
`install.sh` · `phases/P5.md` (Phase Context + контракт фазы, Completion Notes P5.1/P5.2) ·
`research/08-p4-executor-layer-and-policy.md` §9 ·
`research/03-foreman-absorption-inventory.md` §3–§4 ·
`plans/archive/2026.07.18-FOREMAN/root/contracts/driver-plan-protocol.md` ·
`root/contracts/execution-policy-v1.md` · `packages/harness/lib/harness/execpolicy.py` ·
`packages/harness/configs/common/agent-packs/roles.json` ·
`packages/harness/configs/claude-code/agent-packs/_common/agents/orchestrator.md` ·
`roadmap/artifex-thin-wrapper.md` · `root/executor-layer-rescope-v1.md` ·
`phases/P2.md`/`phases/P3.md`/`phases/P4.md` · `roadmap.md` §«Карта запуска» · `journal.jsonl`.

**Open risks:**
- **P5.3 снимает изоляцию — порядок не рекомендация, а условие обратимости** (R4): реинсталл →
  снимок «ПОСЛЕ» → дельта → read-only проверки → коммиты → и ТОЛЬКО последним действием
  `git worktree remove` + `rm -rf ~/.local/bin-skm-next`. Ветка `next/harness-agnostic` НЕ
  удаляется ни при каких условиях (D46) — пока `main` не отправлен наружу, она второй якорь.
- **Пересъём снимка «ДО» после merge ЗАПРЕЩЁН** (R5): базлайн неполон → назвать пробел в
  Pending Work, не заменять базлайн. Волатильный набор назван поимённо в `README.md` базлайна
  (`hub.memory.running`/`url`, `hub.graph.nodes`/`edges`, счётчики уроков analyst, тайминги) —
  расхождение ВНЕ него не чинится по месту: ESCALATION-блок.
- **`main` слит локально и НЕ отправлен наружу.** Откат стоит одной команды
  (`git reset --hard 8e16a811` в основном дереве) ровно до первого `push` — после него цена
  меняется необратимо. Push/PR/тег — гейт владельца, вне плана.
- **Предусловие «дерево чистое» у P5.2 не выполнилось буквально** и было пройдено решением
  владельца: три untracked-пути в основном дереве (`.swissknife/`, `audits/`,
  `packages/task/lib/.claude/`) на месте и после merge. У P5.3 буквального гейта «status пусто»
  нет, но `git add -A` в основном дереве по-прежнему утащил бы их — коммитить только плановые
  пути.
- **Флот НЕ получил новые правила** (D45): скиллы connect-канала живут кэшем плагинов
  (auto-update локального marketplace выключен), vendor-копии и agent-packs обновляются своими
  командами. P5.3 обязан перечислить это разделом «НЕ раскатано» артефакта дельты — раскатка
  отдельная работа вне плана.
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
- **`plan-lint`: 0 ERROR / 8 WARN на закрытии P5.2** — счёт не изменился ни на единицу
  относительно пред-мердж дерева ветки; все восемь — false positive предикатов линтера, не
  контентные дефекты (см. `phases/P4.md` Completion Notes P4.1). Сужение предикатов — правка
  `packages/task`, дом `roadmap/` либо follow-up fix-item.
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
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4);
  именно P5.3 проверяет, что он пережил волну изменений.
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.3 (P5.1/P5.2 закрыты).
- **Ruff (`0.15.19`, `F,B`) и python-матрица 3.9–3.13 не прогонялись локально** ни на P5.1, ни
  на пост-мердж прогоне P5.2 — только push/CI даёт полную картину (R2, честно названо; формула
  «CI зелёный» не употребляется).
- **`verify-citations.py --strict`: 8 остаточных находок**, все в `phases/P1.md`/`phases/P4.md`/
  `plan.md` (поля закрытых items P1/P4), новых от диффа P5.2: 0 — вне Scope этого item'а,
  кандидат на follow-up-заход.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а. · Доказательство §16/§17 `validate.sh`
  изолированным раннером — вынужденная форма, пока §14 краснеет раньше по порядку.
  · P5.1 починил пять пре-существующих/P2-производных красных гейтов сайд-патчем вне `Files`
  item'а по явному решению owner (детали — Completion Notes P5.1, Known Deviations).
  · P5.2 прошёл предусловие «дерево чистое» при трёх untracked-путях по явному решению owner,
  предъявив замером нереализуемость R1 (детали — Completion Notes P5.2, Known Deviations).
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
  (OQ-8, замечен повторно на P4.4) · ruff+python-матрица CI не воспроизведены локально (R2).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5 (9/10),
  решение между тремя вариантами открыто · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не
  покрывает `analyst`/`task` (Deferred) · OQ-5 изоляция общего state (Deferred) — действует на
  P5.3. OQ-2 закрыта полностью (D71 + D93/D94, исполнено P4.5).
  OQ-3/OQ-6 закрыты D86/D87 (P2.1); OQ-1 — D31; OQ-4 — P3.4/D27.
