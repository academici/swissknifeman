# P0 — Recon: кластер protocol-gap plan-протокола (2026-07-13)

Разведка design-сессии `/task:design` перед авторингом плана `2026.07.13-PLAN-PROTOCOL-GAP`.
Всё ниже — ФАКТЫ, проверенные в этой сессии (repo-grounded — чтением кода/прогоном;
external — через RAG). Плановые items ссылаются на этот файл в `Inputs`/`Required Reads`,
чтобы не восстанавливать контекст по чату.

---

## 1. Внешние факты (RAG:✅ 2026-07-13 — docs.claude.com / code.claude.com, актуальность подтверждена)

Запрос: возможности пиннинга модели/effort в Claude Code (frontmatter команд/скиллов,
субагенты, workflow-`agent()`), и есть ли API смены модели сессии изнутри команды.
Ступени: `perplexity-web` (search_advanced) + агент `claude-code-guide` (читает офдоку).

| Факт | Источник | Следствие для дизайна |
|:--|:--|:--|
| `model` — валидный ключ frontmatter slash-команды/скилла; пинит модель **на исполнение этой команды**, сессию не перенастраивает | `code.claude.com/docs/en/skills` (Command/Skill frontmatter reference) | `/task:plan-exec` жёстко = sonnet, пока файл команды не изменён |
| `effort` — валидный ключ frontmatter (low/medium/high/xhigh/max), переопределяет effort сессии | там же | `plan-exec` = medium; пин работает, но статичен |
| **Механизма сменить модель сессии программно (из команды/агента) — НЕТ**; `/model`, `/effort`, `--model/--effort` — только пользовательские | `code.claude.com/docs/en/model-config`, slash-commands ref | **plan-exec не может «переключиться» на fable/opus по §3 Routing — только ОТКАЗАТЬСЯ и попросить владельца** |
| Субагент: `model` задаётся (frontmatter агента / per-invocation), **`effort` per-subagent НЕ поддерживается** — наследуется от родителя | `code.claude.com/docs/en/sub-agents` | Делегация item'а субагенту не даёт требуемого `high/xhigh` — недобор effort'а тихо остаётся |
| Workflow `agent(prompt, {model, effort})` — принимает и модель, и effort | tool-схема `Workflow` (описание опций `opts.model`/`opts.effort`) | Единственный путь авто-делегации с ПОЛНЫМ роутингом — Workflow; см. «Обсуждение» плана (отклонено, D3) |
| Механизма «команда отказывается исполняться и предлагает перезапуск под другой моделью» в API нет — только текстом отчёта | офдока (не документировано) | Гейт = стоп + `launch-block` формы «ЗАПУСК ВРУЧНУЮ» |

## 2. Repo-grounded: линтер — фактические дыры (прогнано в этой сессии)

`packages/task/lib/task/plan_lint.py`, проверка форм `handoff.Next` (строки ~834–861):

```
'/task:plan-exec REGHUB P2.7'    → PLAN_EXEC_RE:   MATCH   ✔ принимается
'/task:plan-design REGHUB P2'    → PLAN_DESIGN_RE: MATCH   ✔ принимается
'/task:plan-design REGHUB P2.7'  → НИ ОДНА          ✘ ERROR  ← НОВАЯ находка (N1)
'/task:plan-audit REGHUB P2'     → НИ ОДНА          ✘ ERROR  ← m8
'/task:plan-close REGHUB P2'     → НИ ОДНА          ✘ ERROR  ← N2
```

- **m8** (из аудита REGHUB): канон plan-close предписывает после закрытия фазы с 🟠/эскалацией
  `Next = /task:plan-audit <ID> Pn` → линтер даёт ERROR на предписанном каноном handoff'е.
- **N1 (новая, найдена этой сессией):** `commands/plan-exec.md` §5 (эскалация) прямо предписывает
  `Next: /task:plan-design <PLAN-ID> Pn.m` — **item-level**; `PLAN_DESIGN_PHASE_RE` = `(P\d+)(?!\.\d)`
  принимает только phase-level → любой ЭСКАЛИРОВАННЫЙ item оставляет план с ERROR в линте.
- **N2 (новая):** `/task:plan-close <ID> Pn` в `Next` тоже не принимается.

Итог: линтер и командный канон рассинхронизированы на **трёх** формах из пяти реально
предписываемых. Это один класс, а не три случайности.

## 3. Repo-grounded: «зелёный lint до коммита» недостижим — из чего состоят 78 ERROR REGHUB

Прогон: `python3 packages/task/scripts/plan-lint.py plans/REGHUB` (из `/home/vostrikov/Vaults/Brain`)
→ **79 ERROR / 4 WARN** (79-я — `handoff.md:3`, форма `Next` = plan-audit, т.е. m8).

Классификация остальных 78:

| Класс | Кол-во | Причина |
|:--|:--|:--|
| `item P3.m: нет обязательного поля «X»` | **78** | фаза-скелет `P3` (8 items) не несёт 16 канонических полей: `Code Guidance`/`Deliverables`/`Escalation Needed`/`Scope Excluded`/`Known Deviations`/`Pending Work` — у 0 items из 8; `Scope Included`/`Files`/`Implementation Rules`/`Completion Notes` — у 1 из 8 |

Т.е. остаточные 78 — **дефект конкретного плана** (недозаполненный скелет), а не свойство протокола.
Подтверждение (разведка по 26 живым планам, §5 ниже): у скелет-фаз ERP-IMPL (18 items),
EDUFY-SCHOOL (18), FLEXCMS, FLEXSTORE, FLEX-2, FLEXCRM-W2 — **все 16 полей на месте** (со значением «—»).
REGHUB/P3 — единственный неполный скелет из ~52 скелет-items флота.

**Вывод:** ослаблять ERROR-гейт (missing field → WARNING в скелет-фазе) НЕ нужно — 90% флота
уже соблюдает канон. Нужно (а) снять ложную ERROR формы `Next` (m8/N1/N2) и (б) дать
честный delta-механизм «новых ошибок от диффа item'а: K» вместо абсолютного N.

## 3-бис. Repo-grounded: `validate.sh` пакета `task` КРАСНЫЙ прямо сейчас (N3)

Прогон в этой сессии (`cd packages/task && bash scripts/validate.sh`):

```
plan-lint: ПРОВАЛ (6 план(ов), 2 ошибок, 44 предупреждений)
  FAIL: plan-lint.py plans/ — см. вывод выше
validate: ПРОВАЛ
```

Обе ERROR — фантомные:

```
ERROR: plans/archive/plan.md: plan.md отсутствует или не читается
ERROR: plans/archive/handoff.md: handoff.md отсутствует или не читается
```

Причина: `discover_plan_dirs` (`plan_lint.py:942`) перебирает ВСЕ подкаталоги `plans/` — включая
`plans/archive/`, которая планом не является (она контейнер планов). Как только в репо
архивируется первый план (в swissknifeman это произошло 2026-07-12), `validate.sh` пакета `task`
становится КРАСНЫМ, а с ним — commit-гейт протокола («validate.sh зелёный ДО коммита»). Побочно:
`_plan_codename("archive")` = `archive` → два ложных WARNING про «неканоничное имя workflow-скрипта
`wf-archive-…`».

Проверка, что дело именно в этом: `plan-lint.py plans/archive/2026.07.10-SKM-ROADMAP-005` →
**OK, 0 ошибок** (сам архивный план валиден).

Это тот же класс, что m8/B1: **гейт требует зелёного, которого нельзя достичь честной работой** —
и агент либо игнорирует красный `validate.sh` (обесценивая гейт), либо «чинит» его случайными
правками. Чинится в P1.1 (D14).

## 4. Repo-grounded: где именно живёт кластер

| Находка | SSOT-файл | Якорь |
|:--|:--|:--|
| F7 (routing) | `packages/task/commands/plan-exec.md` | п.2 «Предусловия» (гейта нет) · п.7 «Routing-adherence gate» (post-факт запись, ПОСЛЕ работы) |
| F7 (канон) | `.../skills/general/plan-protocol/SKILL.ru.md` | §9 Routing & Thinking Policy (матрица есть, правила «кто имеет право исполнять» — нет) |
| m8/B1/N1/N2 | `packages/task/lib/task/plan_lint.py` | `PLAN_EXEC_RE`/`PLAN_DESIGN_PHASE_RE` (:84–88), ветка проверки `Next` (:834–861) |
| B1 (порядок) | `commands/plan-exec.md` п.7 · `commands/plan-close.md` п.6 | lint — последним пунктом, но commit-гейт стоит ВЫШЕ перезаписи handoff → счёт публикуется до финального состояния дерева |
| A5 (status-rule) | `SKILL.ru.md` §6 «Статусы» | правила «что переводит item в 🟠» нет вообще |
| m7 (notification) | `SKILL.ru.md` §11 «Межплановые паттерны» | есть только cross-plan **gate** (потребитель читает донора); обратного канала (донор уведомляет) нет |

## 5. Repo-grounded: карта §3 Routing по флоту (26 планов, 9 корней `plans/`)

Разведка (Explore, read-only) по `Brain/plans`, `swissknifeman/plans`, `vaulter`, `azguard`,
`corex`, `loqum`, `themeon`, `edufy`, `agelto`:

- `## 3. Routing` есть в **100%** планов (заголовок стабилен байт-в-байт).
- **Форматы тела:** таблица — 20; буллеты/проза — 9 (ECOSYSTEM, MODKIT, REGHUB, COREX-CORE,
  LOQUM-DEV, EST-AI, DOMLANG, FLEX-IMPL, SKM-MASTER-002/003); пусто («—») — 3 (FLEXCMS,
  FLEXSTORE, PILOT-AZG).
- **Заголовки колонок:** items — 5 вариантов (`Item`/`Item(ы)`/`Items`/`Фаза`); модель — 8
  (`Отклонение`, `Model/effort`, `Model/Effort`, `Модель/effort`, `Model/effort · Tool Capability`,
  `Model/effort И/ИЛИ Tool Capability`, …); обоснование — 2 (`Почему`/`Why`).
- **Синтаксис множеств items:** одиночные, списки через запятую, диапазоны через **en-dash `–`
  И ASCII-дефис `-`** (иногда в одном файле), слэш-множества (`P2.20/P2.22/P2.23`), wildcard
  (`P2.*`, `P3.x`), диапазоны ФАЗ (`P0–P2`), не-`Pn.m` ID (`SP-2`…`SP-20` у ERP-IMPL),
  catch-all прозой («остальные», «Прочие exec-items …»).
- **Синтаксис модели:** `fable/high`, `opus / xhigh` (с пробелами), дизъюнкции
  («fable или opus/high», «~~fable~~ → opus/xhigh»), стадийные раздвоения
  («sonnet/medium (impl) + opus/high (review)»), effort по подмножеству ВНУТРИ ячейки
  («sonnet (P2.20 medium; P2.22-P2.25 low)»), ячейки вообще без модели (только Tool Capability).

**Вывод (несущий, D7 плана):** детерминированный парсер §3 Routing в `plan-lint` построить
нельзя без слома ~30% живых планов. Routing читает и интерпретирует ИСПОЛНИТЕЛЬ (LLM) —
он это умеет; линтер §3 не парсит. Канон-форма вводится только для НОВЫХ планов
(эмитит `plan-design`), плюс грепаемый маркер `ЗАПУСК ВРУЧНУЮ` / колонка `Exec` как опора.

## 6. Прецедент-кейс (почему это не косметика)

REGHUB фаза P2: **4 подряд RED-аудита** при нулевом Blocker-остатке по существу
(контракт-семантика сошлась после wave-1). Blocker 3→0→0→0, Major 6→3→1→1 — но фаза
не могла закрыться, потому что:

1. `plan-exec` уводил contract-item'ы под sonnet вопреки мандату fable/high (F7) → пришлось
   вписывать в §3 Routing костыль «**ЗАПУСК ВРУЧНУЮ, НЕ `/task:plan-exec`**» ×4 строки;
2. закрывающий item физически не мог дать честный lint (B1): гнал его ДО перезаписи handoff →
   опубликовал 78 при факте 79 (79-ю внёс сам, формой `Next` = plan-audit, m8);
3. класс воспроизводился **трижды** (F11 → M2 → A4 → B1) — каждый раз чинился «по месту»,
   каждый раз возвращался на следующем закрытии.

Владелец (2026-07-13, D21/D22 REGHUB): чинить в SSOT, не в REGHUB — «без этого каждый
следующий план экосистемы соберёт те же находки заново».
