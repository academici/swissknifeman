# HANDOFF — 2026-07-30 — after P4.3

**Next:** exec-items: task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P4.4

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — правка кросс-поверхностной грамматики оркестратора, D39/D47: effort high выше пина plan-exec |
| Context | continue (/clear) — ручной item |
| Суть | P4.4: аддитивное поле формата возврата + блок «Контракт задания» в ОБОИХ носителях `_common.orchestrator` (канон `roles.json` + шаблон `_common/agents/orchestrator.md`), бамп версии пака, перевод точки принуждения `delegation_contract` `pending → enforced`, расширение `execpolicy.py` строгой проверкой адреса |

**ЗАПУСК ВРУЧНУЮ: opus/high**

```
/model opus
/effort high
/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P4.4
```

**Session:** Claude Sonnet 5/medium (implementation/medium, `Exec = plan-exec`): носитель политики
исполнения и валидатор по запечатанной схеме P4.2.

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · **P2 закрыта `plan-close`'ом (9/9 — 5 🟢 + 4 🟠,
`🟠 Done with deviations`)** · **P3 закрыта `plan-close`'ом (6/6 — 0 🟢 + 6 🟠,
`🟠 Done with deviations`), аудит P3 проведён (ATTENTION) и реконсилирован** ·
**P4 в работе: P4.1 закрыт `🟢`** (item-коммит `7ed90cd0`) — вердикт по 24 незакрытым items
`2026.07.18-FOREMAN`, дом остатка `roadmap/artifex-thin-wrapper.md`, D90/D91 · **P4.2 закрыт `🟢`**
(item-коммит `4d70e7a1`) — запечатана схема политики исполнения
`root/contracts/execution-policy-v1.md` · **P4.3 закрыт `🟢`** (item-коммит `95ab0492`) — данные
`execution-policy.json` (четыре раздела, обе точки принуждения `delegation_contract` в
`status: pending` с адресатом P4.4, D58), валидатор `packages/harness/lib/harness/execpolicy.py`
(stdlib-only, `--check`, семь функций-проверок покрывают 20 пунктов §10 контракта) по образцу
`reviewroles.py`, тесты `test_exec_policy.py` (8 тестов — шесть негативных классов + позитивный
`pending`-кейс), шаг `[10/10]` в `packages/harness/scripts/validate.sh` (фактический знаменатель
ПЕРЕД правкой — девять, совпал с ожиданием ТЗ), деградация в пропуск при отсутствии `core/`
(standalone-раскладка).

**Карта «item → коммит» (P2, реконсилировано 2026-07-30, аудит P2, находка F1):**
P2.1 `ed306ca6` · P2.2 `632e75d3`(+`ad325a5e`) · P2.3 `c97e5cfb`(+`3e883a68`) ·
P2.4 `cf1498a1`(+`966d7764`) · P2.5 `fa826d47` · P2.6 `317622c0`+`23c1090c` · P2.7 `e16082a1` ·
P2.8 `a264a339` · P2.9 `ffda7173`.

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` · P3.5 `1373fccf` · P3.6 —
без item-коммита (законный исход «покрыто существующим скиллом», ноль диффа зафиксирован).

**Карта «item → коммит» (P4):** P4.1 `7ed90cd0` · P4.2 `4d70e7a1` · P4.3 `95ab0492`.

**Remaining:** P4.4 → P4.5 (порядок фазы строгий), затем P5 (3 items). Итого
**5 из 35** items плана не исполнено. Сверх items остаётся **рекомендованный аудит фазы P2**
(`/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P2`), владельцем не запускался; он не блокирует P4
(фаза P2 терминальна), но чем дальше уходит exec, тем дороже его находки.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D91, §6 Update Log, §4 Status Board — P2 `5/9`,
P3 `0/6` обе `🟠`, P4 `3/5` `🟡`; §7 Exported — политика исполнения `sealed (P4.2)`) ·
`root/contracts/execution-policy-v1.md` (**запечатанная схема — вход P4.3 и P4.4**, включая
канонические marker-литералы §5.3 и чек-лист §10) ·
`packages/harness/configs/common/agent-packs/execution-policy.json` (живой носитель данных,
P4.3) · `packages/harness/lib/harness/execpolicy.py` (валидатор, P4.3) · `phases/P4.md` (Phase
Context + контракт фазы, Completion Notes P4.1–P4.3, порядок P4.1→P4.5) ·
`root/executor-layer-rescope-v1.md` (граница «строит / не строит») ·
`roadmap/artifex-thin-wrapper.md` (дом остатка супервизора) · `phases/P2.md`/`phases/P3.md`
(Completion Notes, Phase Handoff) · `roadmap.md` §«Карта запуска» · `journal.jsonl`.

**Open risks:**
- **Дефект ТЗ P4.4, найденный замером P4.2 (нужен заход `plan-design` ДО исполнения P4.4):** его
  Scope требует «обе провайдерские проекции роли рендерятся без ошибок», а Validation — прогон
  `plan_agent_artifact(r, provider_id='codex', …)` с ожиданием `codex OK`; для `_common.orchestrator`
  это НЕВЫПОЛНИМО по замороженному контракту — роль несёт `activation_requirements:
  ('command.workflow-carrier',)`, и рендерер отказывает
  (`HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4`, `agentpacks.py:1120`;
  ограничение запечатано P2.1 в `configs/provider-capabilities.json`
  `capabilities[0].support.codex.limitations[1]`). Схема P4.2 фиксирует честную границу (§5.5,
  §9 п. 2): доказательством Codex-стороны служит запись КАНОНА, не рендер
  `.codex/agents/*-orchestrator.toml`, которого по конструкции нет. Этот дефект НЕ снят P4.3 —
  P4.4 обязан начаться эскалацией к нему, а не попыткой исполнения устаревшей Validation.
- **`packages/skiller/scripts/validate.sh` красный на ОДНОМ предсуществующем гейте** (долг P0.5):
  §14 `ERROR: протухшие переводы SKILL.ru.md→SKILL.md`
  (`skills/repository-bootstrap/package-architecture/SKILL.md`, 225-строчный чужой RU-источник).
  Пакетная Validation P4.3 («`bash packages/harness/scripts/validate.sh` — зелёный») относится к
  `harness` (гейт §14 живёт в `skiller`) и прошла зелёной; общий контур репо остаётся красным до
  починки; чинится одним заходом: перевод + `check-translations.sh --stamp` + `skiller registry`
  + коммит.
- **`decide` не является живой зависимостью** (замер P4.1 на `dde9382a`): машина решений
  `execution-state-machine-v1` существует данными в архиве AR (135 ячеек, 89 207 B), живого модуля
  в `packages/**` нет. Любая формулировка «потребляем `decide`» обязана нести `[UNVERIFIED]` (D91).
- **Приёмка AR формально не выполнена** (его D88/D89/D92): `F1 = 0.96`, `F10 = unknown`, 26/31
  кейсов `unmappable`, Codex-сторона наблюдаемости не пробовалась — четыре долга плюс два наших
  (§4 `root/executor-layer-rescope-v1.md`).
- **`plan-lint`: 0 ERROR / 6 WARN, все шесть — false positive предикатов линтера**, не контентные
  дефекты (P4.3 новых не добавил). Пять — DoR-гейт (SKILL §7) на строке-легенде каждой фазы, чей
  статус перешёл в `🟡`/`🟠`/`🟢` (`plan_lint.py:1941-1948`). Шестая — «фаза P4 заявляет оркестрацию
  без workflow-скрипта»: `ORCHESTRATION_MARKER_RE` (`plan_lint.py:223`) матчит подстроку «оркестрац»
  в предложении Phase Context «**Оркестрация НЕ объявляется**». Сужение предикатов — правка
  `packages/task`, дом `roadmap/` либо follow-up fix-item.
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
  владельца (ECO-OPT D74, OQ-7).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5 (9/10),
  решение между тремя вариантами открыто · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не
  покрывает `analyst`/`task` (Deferred). **OQ-2 (якоря parse-контракта) закрыта измерением P0.3;
  её исполнитель — P4.5, и вердикт «вариант B» заранее переводит item в ветку эскалации** (D37,
  `research/03` §4). OQ-3/OQ-6 закрыты D86/D87 (P2.1); OQ-1 — D31; OQ-4 — P3.4/D27. Новых
  открытых вопросов P4.3 не добавил.
