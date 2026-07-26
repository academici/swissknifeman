# HANDOFF — 2026-07-26 — after P2.1

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Context | `same-session — item` |
| Суть | Реализовать единый компилятор Task Contract, root-dispatch и tiered-portability lint против запечатанных P2.1-контрактов |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.2

РЕЖИМ: исполнение детализированного item'а (P2.2 ⬜, P2.1 закрыт 🟢 коммитом `575a49b2` — не реопен, не повторный дизайн).
ВХОД: phases/P2.md § P2.2 (ТЗ) → его 23 Required Reads в объявленном порядке, начиная с root/contracts/task-contract-v1.md; свежие входы этого шага — root/contracts/{execution-state-machine,risk-review-loop-budget,plan-portability}-v1.md и artifacts/P2.1/state-transition-cases.json (машинная форма: declared_sets, 135 ячеек, обе проекции, decide(), словарь находок).
СКОУП: 1) D36-baseline `assert_generated_scope.py baseline --owner P2.2 … --capture-or-verify` ПОСЛЕ Required Reads и ДО любой другой записи item'а; 2) один компилятор `task_contract.py`, владеющий precedence/conflict/hash/portability — команды его зовут, логику не пересказывают; 3) интеграция pre-mutation/pre-final переходов и последовательного fresh-subagent dispatch в канонические plan-команды; 4) tiered-portability компилятор + отказ `plan_lint` на high-risk/multi-session/handoff/audit-плане без коммиченного execution input; классификация по РОЛИ пути, регекс по подстроке `tmp/` запрещён; 5) self-conformance (D47) ВНУТРИ item'а: новые tier-правила применяются к ЭТОМУ плану, `plan-lint plans/2026.07.24-AGENT-RELIABILITY` — 0 ошибок до коммита; 6) версии `plan-protocol@2.12.0` / `skiller@0.5.0` / `task@0.4.0` + полная регенерация владеемых деревьев/локов/marketplace'ов + доказательство второго прогона; 7) §11-уведомление плана-потребителя `2026.07.25-ECO-OPT` до закрытия.
НЕ ТРОГАТЬ: запечатанные P2.1-контракты и `artifacts/P2.1/**` (владелец — P2.1; расхождение → D#, не тихая правка) — их множества ЗАКРЫТЫ: новое состояние/событие/выход решающей функции = major-бамп контракта, а не локальное расширение; классификация находок и cap — P2.3 (здесь только вызов); захват фактического route — P2.4; замороженные контракты P0/P1 и `artifacts/P1.1/remediation-map.json`; провайдерный рендеринг P1; FOREMAN.
```

Item-коммит P2.1 — `575a49b2` (пять `Files` ровно); плановые пути закрыты отдельным
bookkeeping-коммитом, его хеш — `git log -1 -- plans/2026.07.24-AGENT-RELIABILITY`.

**Done:**

- **P2.1 закрыт 🟢** (2026-07-26, `task:plan-run` под **opus/high** = предписанный §3 Routing
  `frontier/high`). Запечатаны три контракта: `execution-state-machine-v1` ·
  `risk-review-loop-budget-v1` · `plan-portability-v1` — каждый **надстройкой** над замороженным
  P0.2 (секция `## Frozen upstream` со ссылками `file:line`, ни один код P0.2 не перевыпущен, D64).
- **Тотальная машина исполнения**: 9 состояний × 15 событий = **135/135 ячеек** (63 перехода +
  72 объявленные невозможности с индивидуальными причинами, 17 именованных классов); wildcard/
  default-правило в формате носителя непредставимо. Проекции тотальны в обе стороны: **9/9**
  состояний → шесть канонических статусов (`DONE` берёт `material_deviation` входом проекции),
  **8/8** journal `RESULT_VALUES` достижимы.
- **Решающая функция** `decide(state, event, payload, profile)` — чистый детерминированный
  просмотр матрицы; шесть выходов, все достижимы. Это то, что потребляет
  `2026.07.18-FOREMAN` P2/P5 вместо второго движка решений.
- **Cap как параметр профиля authority** (D68): `owner-gated` (канон пакета,
  `plan-audit.md:52-54`) ↔ `self-host` (D50). Гейт машинный: ячейка разрешения cap ОБЯЗАНА быть
  guarded по профилю, иначе `AUTHORITY_PROFILE_UNDECLARED`.
- **F14-гейт**: **10/10** позитивных routine-кейсов дают `continue-next` (порог — 5).
- Фальсификация проверок: **11/11** объявленных мутаций красны КАЖДАЯ по своему коду; восемь
  новых кодов объявлены с `distinct_from` на замороженный код P0.2.
- **Долг A2 о workflow-carrier закрыт по существу** (D67): критерий `plan-protocol` §7 измерен на
  фактах фазы (`phases/P2.md:54,73,92,111` — цепочка строго последовательна) → скрипт для P2 не
  заводится; обратное условие зафиксировано правилом в контракте.

**Remaining:**

16/22 items. P2: 1/5 (P2.2 → P2.3 → P2.4 → P2.5, все `solo` по `roadmap.md`) → P3 (5) → P4 (3).
Все items P2 детализированы; повторный дизайн-заход не требуется.

**Sources of truth:**

`plan.md` v1.14.0 (§3 Routing, §4 Status Board, §5 D64–D68, §7 Contracts) ·
`phases/P2.md` § P2.1 Completion Notes (факты закрытия) ·
`root/contracts/{execution-state-machine,risk-review-loop-budget,plan-portability}-v1.md` ·
`artifacts/P2.1/state-transition-cases.json` (машинная форма) · `roadmap.md` § P2.2 ·
`journal.jsonl`.

**Open risks:**

- **Строка фазы P0 в `plan.md` §4 протухла:** `🟡 In progress` при четырёх терминальных items
  (`phases/P0.md`: 3🟢 + 1🟠). Precondition-гейт P2.1 требовал терминальности «in `plan.md` §4»
  и был вычислен по КАНОНИЧЕСКОМУ определению (статусы items), а не по ячейке. Владелец правки —
  `task:plan-close 2026.07.24-AGENT-RELIABILITY P0`; **осторожно: режим `Pn` перезаписывает
  `handoff.md` целиком** (заголовок `after P0`), поэтому после него Next надо вернуть на P2.2.
  Этим item'ом не правилось — чужая поверхность (И2).
- **Три новых контракта — новая публичная поверхность.** D23-секции (`## Contribution gate`)
  внутри каждого заполнены (extension points, названные потребители, ≥2 альтернативы,
  SemVer/ADR-результат), но качество их обоснования выявится только аудитом фазы.
- `check_collision_owners` структурно несовместим с фазовой ремедиацией — назван трижды
  (P1.1/P1.5/P1.4), владелец «отдельный proposal/ADR по D23» не назначен. P2 не блокирует.
- Прежний долг без изменений: две находки A2 (порядок capture `base-sha` — владельцы P2.2/P2.3;
  `research/01–03` без ссылок на слой 1); A1 F11; `command.interactive-user-input` вне каталога
  capability; Claude enabled-set `unknown`; Claude-проекция `workflow-craft` (нужен
  `skiller budget --first-turn`); расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых.
- **deferred:** протухшая строка фазы P0 в §4 (владелец — `plan-close P0`, § Open risks);
  структурный фикс `check_collision_owners`/`remediation-map.json`;
  `command.interactive-user-input`; Claude-проекция `workflow-craft`; расхождение провенанса
  harness-CLI ↔ maind-адаптера; две находки A2.
- **open_questions:** нет открытых для владельца — по D50 развилки закрываются записью.
