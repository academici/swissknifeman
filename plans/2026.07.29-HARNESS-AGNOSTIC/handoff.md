# HANDOFF — 2026-07-30 — after P2.2

**Next:** «ЗАПУСК ВРУЧНУЮ: implementation/high»

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — §3 Routing строка P2.3 (`implementation/high`, `Exec = manual`, D39/D47: effort выше пина `plan-exec`) |
| Context | continue (/clear) — ручной item под `task:plan-run` |
| Суть | P2.3 — группа гейтов класса B (`pack-guard`/`changelog-gate`/`review-gate`/`safe-dirs`): могут отказать оператору, парные тесты «отказал»/«пропустил» |

Перед запуском выставить сессию: `/model sonnet`, затем `/effort high` (команда `task:plan-run`
модель НЕ пинит — Routing-гейт сверяет ФАКТИЧЕСКУЮ модель сессии, недобор = ROUTING-BLOCKED).

````
/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P2.3
````

Если предпочтителен ручной прогон без команды — тот же item по промпту:

````
Исполни item P2.3 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, implementation/high —
сессия sonnet/high; /task:plan-exec пинит sonnet/medium и по Routing-гейту отклонит item).

Порядок чтения (ровно этот, без повторов):
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — §0 Meta, §1 Context, §2 Execution Rules,
   §3 Routing (строка P2.3), §4 Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P2.md — Phase Context + P2.1/P2.2 Completion Notes
   (вход item'а) + P2.3 целиком
4) Required Reads item'а P2.3 (в указанном там порядке; пункт 7 — результат P2.2, генератор
   диспетчера в packages/harness/lib/harness/hooks.py, УЖЕ многоповерхностный после этого захода)

Дом плана — repo:/home/vostrikov/projects/packages/swissknifeman, но по Execution Rules (§2)
все работы ведутся в worktree swissknifeman-next (ветка next/harness-agnostic) — запускай
сессию именно там.

Перед мутацией и перед закрытием собери Task Contract (task.task_contract.build +
route_evidence.capture_actual("implementation", "high", source="self-attested",
model="sonnet") — actual_route ЭТОЙ сессии) и убедись, что pre_mutation/pre_final = "allow"
ПЕРЕД любой правкой файлов — не постфактум (P2.2 нёс process-отклонение именно из-за этого,
см. phases/P2.md P2.2 Known Deviations (1)); красный код — см. таблицу в
packages/task/commands/plan-exec.md п.2/п.7.

Исполняй СТРОГО Scope Included P2.3, не трогай Scope Excluded. Уровень манифеста и binding
меняются ОДНИМ коммитом и одним item'ом (иначе HARNESS_CAPABILITY_MANIFEST_INVALID) — тот же
инвариант, что уже применялся в P2.2. У КАЖДОГО гейта — ДВА теста («отказал»/«пропустил»,
Code Guidance §2). Для `security.safe-dirs` — переиспользование ЕДИНОГО вердикт-ядра allowlist'а,
без второй копии правил. Помни: `Stop`/`SubagentStop` семантика `block` НЕ инвертирована
относительно Claude — премиса P2.3 Why/Implementation Rules опровергнута D88 (см.
codex-parity-verdicts-v1.md §5); строка 7 контракта авторитетна над прозой самого item'а.
Пометь Status: 🟡 In progress до работы, journal.append --result in-progress ПЕРЕД началом
работы (не после).

По завершении: прогони ВСЮ Validation P2.3 построчно (включая полный
`bash packages/harness/scripts/validate.sh` и `python3 scripts/test-provider-docs.py -v` —
у обоих уже есть один известный пре-экзистентный сюрприз от P2.2: если следующий item тоже
поднимет уровень capability, canonical/carrier sha256-пин в scripts/test-provider-docs.py и
сгенерированные packages/harness/docs/reference/provider-harness.md +
plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md снова протухнут —
регенерируй их тем же способом, каким это сделал P2.2, ПЕРЕД тем как объявлять Validation
красной), закрой item по топологии plan-protocol §7 (item-коммит по Files P2.3 → bookkeeping →
перезапись handoff.md → plan-lint --baseline HEAD → bookkeeping-коммит), обнови Status
Board/Update Log/Last Updated, append журнал финал-записи. Строка `Session: <model>/<effort>`
в отчёте и Update Log ОБЯЗАТЕЛЬНА (D47). Отчёт — в формате Expected Output plan-exec,
launch-block следующего шага — P2.4.
````

**Что сделано этим заходом (ручной прогон, implementation/high).** P2.2 закрыт `🟠 Done with
deviations` (item-коммит `632e75d3`, follow-up-коммит `ad325a5e`). `render_codex_hook_handler()`
теперь генерирует ОДНУ table-driven функцию-диспетчер (`_SURFACE_EVENTS`/`_HANDLERS`) вместо
реализации ровно `context.observer`, с fail-closed на неизвестной поверхности/битом JSON/
недостающем поле. Включены четыре наблюдателя вердикта P2.1: `lifecycle.command-log`
(`PreToolUse ^Bash$` → `~/.codex/logs/bash-commands.jsonl`, Claude-лог не тронут),
`lifecycle.run-report` (`SessionEnd` → `<cwd>/.codex/runs/<sid>.json`, транскрипт не парсится),
`lifecycle.router` (`UserPromptSubmit`; общий catalog `agent-router/config.json` читается на
этапе РЕНДЕРА и печётся в артефакт с командами в codex-нативной форме `task:x`, не `/task:x`;
порог 2, тихо ниже порога), `lifecycle.memory` (`SessionStart`; читает project-scoped
`.codex/memory.env.ini`, best-effort вызов `maind memory status`, состояния не пишет).
`adapt_codex_hook_payload` починен по обоим дефектам §3.3 контракта вердиктов: `permission_mode`
обязателен только при `SessionStart` (не безусловно), событийные поля обобщены таблицей
(`UserPromptSubmit`→`prompt`, `SessionEnd`→`reason`, `PreToolUse`/`PostToolUse`/
`PermissionRequest`→`tool_name`+`tool_input`). Уровни четырёх capability подняты
`unsupported`→`adapted` синхронно с bindings (`adapter_id`/`limitations`/`evidence` дословно из
`codex-parity-verdicts-v1.md` §3.1–§3.4). 9 новых тестов в `test_codex_lifecycle_surfaces.py` +
2 существующие assertion `test_provider_hooks.py` скорректированы под факт подъёма (третья
проверка «unsupported не протекает в hooks.json» переставлена с `lifecycle.router` на
`lifecycle.pack-guard`, чтобы сохранить исходный смысл, не ослабить его).

**Session:** Claude Sonnet 5/high (implementation/high, `Exec = manual` — совпадает с §3 Routing
строкой P2.2, перебора/недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · блок follow-up P2.6–P2.9 (4/4) · P2.1 `🟢` ·
**P2.2 `🟠` — диспетчер многоповерхностный, четыре наблюдателя класса A включены и заевиденчены.**

**Карта «item → коммит» (P1–P2; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` · P1.7 `003180bf` | `a8abbf9e`,
`7d4f12b7` · P2.6 `317622c0` + `23c1090c` (item-коммит) · P2.7 `e16082a1` · P2.8 `a264a339` ·
P2.9 `ffda7173` · P2.1 `ed306ca6` · **P2.2 `632e75d3` (диспетчер+наблюдатели, item-коммит) +
`ad325a5e` (follow-up: регенерация двух provider-audit артефактов + golden-хеш
test-provider-docs.py, вне Files)**.

**Remaining:** P2.3–P2.5 (3) → P3 (6) → P4 (5) → P5 (3). Итого **17 из 35** items плана ещё не
исполнено.

**Sources of truth:** `root/contracts/codex-parity-verdicts-v1.md` (**sealed v1** — §3.5–§3.10
вход P2.3) · `root/contracts/provider-parity-definition.md` (**sealed v1**) · `plan.md` (§3
Routing, §5 D1–D89, §6 Update Log с картой хешей, §4 Status Board — P2 `4/9 🟡` (счёт только `🟢`;
P2.1/P2.6–P2.8 — четыре; P2.2/P2.9 закрыты `🟠`)) · `phases/P2.md`
(P2.1/P2.2 Completion Notes — прогоны и числа; P2.3–P2.5 ТЗ) · `configs/provider-capabilities.json`
(4 записи класса A теперь `adapted`, 13 ещё `unsupported`/`config-native` из 17 Codex-овых) ·
`roadmap.md` (v0.10.0, 35 items) · `journal.jsonl`.

**Open risks:**
- **Проза P2.3 несёт опровергнутую премису** («семантика `block` у `Stop`/`SubagentStop`
  инвертирована относительно Claude») — не правилась (вне `Files` P2.1/P2.2). Исполнитель P2.3
  обязан читать §5 контракта вердиктов как приоритетный носитель.
- **Три долга, созданные триажем P2.1, дома НЕ получили**: замер формата транскрипта Codex,
  opt-in-флаг Claude-половины `git-guardrails`, проекция `writable_roots` из allowlist'а. Дом —
  `roadmap/`, заведение — отдельный item либо заход `plan-design`.
- **Объём P2.4:** два bounded-closure ряда (`settings.audit`, `agent-packs.lifecycle`) —
  крупнейшая работа фазы. Не несёт одним item'ом → разбиение через `plan-design`, а НЕ понижение
  вердикта до `claude-only` (D89 п.1).
- **Пол интерпретатора:** `tomllib` — stdlib с Python 3.11, матрица CI — `3.9…3.13`. Codex-аудитор
  P2.4 читает содержимое только на 3.11+ (D89 п.2).
- **Golden-хеш `scripts/test-provider-docs.py` и два сгенерированных provider-audit артефакта
  (`packages/harness/docs/reference/provider-harness.md`,
  `plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md`) дрейфуют при
  КАЖДОМ подъёме уровня capability** — P2.2 их регенерировал (Known Deviation, диф вне `Files`);
  P2.3/P2.4 столкнутся с тем же и обязаны повторить регенерацию тем же способом ПЕРЕД закрытием,
  а не молчаливым игнорированием красного `test-provider-docs.py`.
- **`plan-lint` WARN нового рода на `phases/P2.md`** (сохраняется, K=0 не задет): DoR-чеклист фазы
  цитирует синтаксис маркера уточнения дословно.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена пятый заход
  подряд — не наш предмет.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом правки
  `roadmap/`, спека не заведена.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8 (`roadmap/instruction-authorize-order.md`),
  реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5); `scripts/test-provider-docs.py`
  несёт один ПРЕДСУЩЕСТВУЮЩИЙ красный (`test_internal_markdown_links...` — битая ссылка
  `roadmap/self-learning-memory.md`, `provider-parity-definition` §6.3, не регрессия P2.x);
  `scripts/public-hygiene.py` — предсуществующе красный.
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (OQ-7) · общий differ канона
  ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · `skiller registry` не прогнан (P0.5) ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима ·
  удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md`. **Снято из
  deferred:** ничего (P2.2 долгов не закрывал).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 — D27. Новых открытых вопросов P2.2 не добавил.
