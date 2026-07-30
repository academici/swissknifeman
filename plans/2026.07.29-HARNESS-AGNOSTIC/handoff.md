# HANDOFF — 2026-07-30 — after P2.3

**Next:** «ЗАПУСК ВРУЧНУЮ: implementation/high»

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — §3 Routing строка P2.4 (`implementation/high`, `Exec = manual`, D39/D47: effort выше пина `plan-exec`) |
| Context | continue (/clear) — ручной item под `task:plan-run` |
| Суть | P2.4 — не-хуковые capability класса C (`settings.audit`, `agent-packs.lifecycle`, `workflows.status`, `lifecycle.notification`) + честная форма ВСЕХ остающихся `unsupported`; крупнейшая работа фазы (два bounded-closure ряда, D89 п.1) |

Перед запуском выставить сессию: `/model sonnet`, затем `/effort high` (команда `task:plan-run`
модель НЕ пинит — Routing-гейт сверяет ФАКТИЧЕСКУЮ модель сессии, недобор = ROUTING-BLOCKED).

````
/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P2.4
````

Если предпочтителен ручной прогон без команды — тот же item по промпту:

````
Исполни item P2.4 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, implementation/high —
сессия sonnet/high; /task:plan-exec пинит sonnet/medium и по Routing-гейту отклонит item).

Порядок чтения (ровно этот, без повторов):
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — §0 Meta, §1 Context, §2 Execution Rules,
   §3 Routing (строка P2.4), §4 Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P2.md — Phase Context + P2.1/P2.2/P2.3 Completion Notes
   (вход item'а) + P2.4 целиком
4) Required Reads item'а P2.4 (в указанном там порядке; пункты 341–382 provider_audit.py — читай
   ТЕКУЩЕЕ состояние: P2.3 уже сняла спец-ветку `security.safe-dirs`, работай с деревом ПОСЛЕ
   коммитов `c97e5cfb`/`3e883a68`)

Дом плана — repo:/home/vostrikov/projects/packages/swissknifeman, но по Execution Rules (§2)
все работы ведутся в worktree swissknifeman-next (ветка next/harness-agnostic) — запускай
сессию именно там.

Перед мутацией и перед закрытием собери Task Contract (task.task_contract.build +
route_evidence.capture_actual("implementation", "high", source="self-attested",
model="sonnet") — actual_route ЭТОЙ сессии) и убедись, что pre_mutation/pre_final = "allow"
ПЕРЕД любой правкой файлов — не постфактум; красный код — см. таблицу в
packages/task/commands/plan-exec.md п.2/п.7.

Исполняй СТРОГО Scope Included P2.4, не трогай Scope Excluded. Уровень манифеста и binding
меняются ОДНИМ коммитом и одним item'ом (иначе HARNESS_CAPABILITY_MANIFEST_INVALID) — тот же
инвариант, что уже применялся в P2.2/P2.3. **Объём — крупнейший в фазе** (Open risks ниже):
`settings.audit` (P2.11) и `agent-packs.lifecycle` (P2.12) — bounded closure по D89, каждый со
своим измеренным ограничением (`tomllib` с Python 3.11 против матрицы CI 3.9…3.13 у первого;
исключённые `.claude/workflows/*.js`/pack-члены runtime у второго). Если весь объём (два bounded
closure + три честных `claude-only` ряда — `lifecycle.notification`, `workflows.status`,
`analytics.legacy-migration`, `context.output-style`, `context.plans-directory`) не помещается в
ОДИН item по разумному Validation-циклу — НЕ понижай вердикт до `claude-only` (D89 п.1 это прямо
запрещает) и НЕ дели молча: остановись, ESCALATION-блок (триггер «неясные acceptance» либо
«многопакетный рефакторинг», п.5 `plan-exec.md`), решение о разбиении — `plan-design`.
Пометь Status: 🟡 In progress до работы, journal.append --result in-progress ПЕРЕД началом
работы (не после).

По завершении: прогони ВСЮ Validation P2.4 построчно (включая полный
`bash packages/harness/scripts/validate.sh` и `python3 scripts/test-provider-docs.py -v` —
у обоих уже есть один известный пре-экзистентный сюрприз от P2.2/P2.3: если этот item тоже
поднимет уровень capability, canonical/carrier sha256-пин в scripts/test-provider-docs.py и
сгенерированные packages/harness/docs/reference/provider-harness.md +
plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md снова протухнут —
регенерируй их тем же способом, каким это сделали P2.2/P2.3, ПЕРЕД тем как объявлять Validation
красной; также проверь test_provider_conformance.py/test_provider_hooks.py на evidence-фикстуры,
ссылающиеся на записи, чей уровень ты поднимаешь — они потребуют той же точечной коррекции), закрой
item по топологии plan-protocol §7 (item-коммит по Files P2.4 → bookkeeping → перезапись
handoff.md → plan-lint --baseline HEAD → bookkeeping-коммит), обнови Status Board/Update
Log/Last Updated, append журнал финал-записи. Строка `Session: <model>/<effort>` в отчёте и
Update Log ОБЯЗАТЕЛЬНА (D47). Отчёт — в формате Expected Output plan-exec, launch-block
следующего шага — P2.5.
````

**Что сделано этим заходом (ручной прогон, implementation/high).** P2.3 закрыт `🟠 Done with
deviations` (item-коммит `c97e5cfb`, follow-up-коммит `3e883a68`). Диспетчер
`.codex/hooks/lifecycle.py` расширен шестью обработчиками класса B из вердикта P2.1:
`lifecycle.pack-guard` (`PreToolUse` `^apply_patch$`, деньга managed-ассетов пака по
`.claude/agent-pack.lock.json`, best-effort substring-match — точная схема пейлоада
`apply_patch` `[UNVERIFIED]`), `lifecycle.changelog-gate` (`PreToolUse` `^Bash$`, парсинг `-m`),
`lifecycle.review-gate` (`SubagentStop`, exit 2 принуждает продолжать — семантика НЕ инвертирована
относительно Claude, D88; loop-guard на файле состояния, cap 3, `check_command` читается из ТОГО
ЖЕ machine-owned `~/.claude/hooks/review-gate/config.json`, что уже использует Claude-хук),
`security.safe-dirs` (`PreToolUse` `^Bash$`, ВЫЗЫВАЕТ единое вердикт-ядро
`configs/claude-code/hooks/auto-approve/lib/safedirs.py` через `importlib` по найденному корню
монорепо — заведена как поверхность класса `security` в каталоге, `_LIFECYCLE_KINDS` расширен,
хардкоженная спец-ветка `_named_surface_state` для неё СНЯТА), `lifecycle.daemon-safety`
(`PreToolUse` `^Bash$`, уровень поднят на ОБЕИХ сторонах — Claude-биндинг был описательно неверным
при уже рабочей регистрации, D87), `lifecycle.git-guardrails` (Codex-половина `adapted`,
Claude-половина остаётся `unsupported` честной формулировкой — активация фактически меняет
поведение флота, D89/§4). CLI обобщён: `harness hooks --provider codex [--observer]
[--pack-guard M] [--changelog-gate M] [--review-gate M] [--git-guardrails M] [--safe-dirs]
[--daemon-safety] [--trusted] [--repair]` — ОДНА декларативная пересборка `.codex/hooks.json`;
`block_codex_observer` сохранён обёрткой над новым `block_codex_lifecycle` (D104-путь
`maind/provider_deploy.py` не задет — вызывает `plan_lifecycle`/`codex_d104_observer_fragment`
напрямую). Уровни 6 записей подняты `unsupported`→`adapted` (`adapter_id`/`limitations`/`evidence`
из `codex-parity-verdicts-v1.md` §3.5–§3.10). 15 новых тестов в `test_codex_lifecycle_gates.py`
(манифест+bindings + два теста на каждый гейт «отказал»/«пропустил») + 2 скорректированные
assertion `test_provider_hooks.py`.

**Session:** Claude Sonnet 5/high (implementation/high, `Exec = manual` — совпадает с §3 Routing
строкой P2.3, перебора/недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · блок follow-up P2.6–P2.9 (4/4) · P2.1 `🟢` ·
P2.2 `🟠` · **P2.3 `🟠` — шесть гейтов класса B (pack-guard/changelog-gate/review-gate/
safe-dirs/daemon-safety/git-guardrails), диспетчер и CLI обобщены.**

**Карта «item → коммит» (P1–P2; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` · P1.7 `003180bf` | `a8abbf9e`,
`7d4f12b7` · P2.6 `317622c0` + `23c1090c` (item-коммит) · P2.7 `e16082a1` · P2.8 `a264a339` ·
P2.9 `ffda7173` · P2.1 `ed306ca6` · P2.2 `632e75d3` (диспетчер+наблюдатели, item-коммит) +
`ad325a5e` (follow-up: регенерация двух provider-audit артефактов + golden-хеш
test-provider-docs.py, вне Files) · **P2.3 `c97e5cfb` (шесть гейтов класса B, item-коммит) +
`3e883a68` (follow-up: регенерация двух provider-audit артефактов + golden-хеш
test-provider-docs.py + одна evidence-фикстура test_provider_conformance.py, вне Files)**.

**Remaining:** P2.4–P2.5 (2) → P3 (6) → P4 (5) → P5 (3). Итого **16 из 35** items плана ещё не
исполнено.

**Sources of truth:** `root/contracts/codex-parity-verdicts-v1.md` (**sealed v1** — §3.5–§3.10
уже закрыты P2.3) · `root/contracts/provider-parity-definition.md` (**sealed v1**) · `plan.md` (§3
Routing, §5 D1–D89, §6 Update Log с картой хешей, §4 Status Board — P2 `4/9 🟡` (счёт только `🟢`;
P2.1/P2.6–P2.8 — четыре; P2.2/P2.3/P2.9 закрыты `🟠`)) · `phases/P2.md`
(P2.1–P2.3 Completion Notes — прогоны и числа; P2.4–P2.5 ТЗ) · `configs/provider-capabilities.json`
(10 записей класса A+B теперь `adapted` у Codex, плюс `lifecycle.daemon-safety` у Claude; 7 ещё
`unsupported`/`config-native` из 17 Codex-овых, минус 2 both-provider уже закрытых) · `roadmap.md`
(v0.10.0, 35 items) · `journal.jsonl`.

**Open risks:**
- **Объём P2.4:** два bounded-closure ряда (`settings.audit`, `agent-packs.lifecycle`) —
  крупнейшая работа фазы, плюс пять честных `claude-only` рядов. Не несёт одним item'ом → разбиение
  через `plan-design`, а НЕ понижение вердикта до `claude-only` (D89 п.1).
- **Пол интерпретатора:** `tomllib` — stdlib с Python 3.11, матрица CI — `3.9…3.13`. Codex-аудитор
  P2.4 читает содержимое только на 3.11+ (D89 п.2).
- **Golden-хеш `scripts/test-provider-docs.py` и два сгенерированных provider-audit артефакта
  (`packages/harness/docs/reference/provider-harness.md`,
  `plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md`) дрейфуют при
  КАЖДОМ подъёме уровня capability** — P2.2 и P2.3 их регенерировали (Known Deviation, диф вне
  `Files`); P2.4 столкнётся с тем же (крупнейший подъём фазы) и обязан повторить регенерацию тем же
  способом ПЕРЕД закрытием, а не молчаливым игнорированием красного `test-provider-docs.py`.
  Аналогично — evidence-фикстуры в `test_provider_conformance.py`/`test_provider_hooks.py`,
  ссылающиеся на записи, чей уровень поднимается: P2.2 и P2.3 оба находили и точечно корректировали
  по одной такой фикстуре; предмет закрытого item'а не переписывается, только сам факт уровня.
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex`** (заведён P2.3):
  оператор обязан перечислять ВСЕ желаемые поверхности при каждом вызове — ранее задеплоенные
  молча выпадают из `.codex/hooks.json`, если не повторены. Задокументировано в докстринге
  `block_codex_lifecycle` и печатается при каждом вызове; merge-режим — кандидат `roadmap/`, не
  предмет P2.4/P2.5.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`
  (`findings/03`); `lifecycle.pack-guard` детектирует управляемый путь best-effort
  substring-match'ем, а не точным полем. Носитель — `roadmap/`, снимет ограничение только
  first-party доки или живой прогон (вне D3).
- **`plan-lint` WARN нового рода на `phases/P2.md`** (сохраняется, K=0 не задет): DoR-чеклист фазы
  цитирует синтаксис маркера уточнения дословно.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена шестой заход
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
  несёт один ПРЕДСУЩЕСТВУЮЩИЙ красный (`test_internal_markdown_links_resolve...` — битая ссылка
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
  удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md` · декларативный
  merge-режим `harness hooks --provider codex` (заведён P2.3) · точная схема Codex `apply_patch`
  (заведён P2.3) · отдельный machine-owned `check_command` для Codex `review-gate` (заведён P2.3).
  **Снято из deferred:** ничего (P2.3 долгов не закрывал, только назвал новые три).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 — D27. Новых открытых вопросов P2.3 не добавил.
