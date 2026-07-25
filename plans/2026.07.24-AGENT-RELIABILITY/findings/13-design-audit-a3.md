# Design audit A3 (новый Owner-слот) — 2026.07.24-AGENT-RELIABILITY

**Дата:** 2026-07-25 · **Режим:** pre-exec design audit всего плана (cold context, adversarial)
**Исполнитель:** Claude Opus 5 / xhigh (frontier/xhigh по §3 Routing)

## Audit design — 2026-07-25

**Вердикт: RED**

`AUDIT-CAP: design-аудит — 6-й заход, решение за владельцем` (историч. cap 2/2 RED,
exceptional attempt 3 RED, authority-C A1 RED, option-B A2 RED — 5 записей `plan-audit`
в `journal.jsonl`; этот заход шестой, по явному новому гранту владельца). Ремонт/редизайн/
исполнение этим заходом не назначаются: грант выдан только на вердикт. `G-EXEC` не наступил,
P0.1 не авторизован.

### Якорь и детерминированные проверки

**Якорь — РАБОЧЕЕ ДЕРЕВО поверх `916acdb5`, не коммит.** Ремонт v1.9.0 (D39–D49, item P1.5)
не закоммичен; `findings/10`, `findings/11`, `findings/12` — untracked. Это само по себе
находка (F4), но и ограничение всех чисел ниже: они воспроизводимы только на этом дереве,
а не по `git ref`. A1 и A2 работали на запиненных SHA — этот заход такой возможности не имел.

- `python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY` →
  **0 ERROR / 0 WARN** (`OK (1 план(ов))`) — на рабочем дереве поверх `916acdb5`.
- `git status --porcelain plans/2026.07.24-AGENT-RELIABILITY` → 10 `M` + 3 `??`;
  `phases/P4.md` **не изменён** ремонтом (прямая причина F2).
- Независимый перезамер коллизий (свой stdlib-скрипт, не скрипт `findings/12`):
  51 запись marketplace · 30 каталогов `.agents/skills` (все с `SKILL.md`) ·
  13 каталогов `.claude/skills` · **worst-case 20 коллизий** — множество совпало
  с `findings/12` поимённо.
- `codex plugin list --json` (read-only, cwd = корень репо) → **23 units `@swissknifeman`,
  23 enabled**, имена совпали с `findings/12` посимвольно. Отсюда: **16 root↔installed**
  (5 core + `query-craft` + 6 task + 4 `architect`) и **1 installed↔installed**
  (`query-craft`: `core` + `research`), **14** уникальных root-carriers (13 class-A +
  `workflow-craft`). **D40–D44 подтверждены независимо.**
- `claude --version` → **2.1.220**; `claude --help` содержит `--effort <level>`, `--model`,
  `--permission-mode` — **RAG:✅ D46 подтверждён независимо.**
- Структурный свип: 22/22 items × 16 обязательных полей — 0 пропусков; 22 строки §3 Routing ·
  22 строки Карты roadmap · 22 `**Next:**` · 22 native carrier'а.
- 49 D-записей, у **каждой** ровно один маркер из enum §7 (0 без маркера).
- `[NEEDS CLARIFICATION]` в плане — 0; секции `## Обсуждение` нет.
- `plans/2026.07.25-ECO-OPT/plan.md:49-50` (coupling) и `D9`/`D10` там же — существуют
  дословно, как утверждает D47.

Средовых блокеров, влияющих на вердикт, не было.

### Findings

#### F1 — Терминальный гейт P1.4 неисполним как написан: состав фикстуры не объявлен, а единственный объявленный состав противоречит D42

- **Severity:** Blocker · **Label:** issue
- **Items:** P1.4 (терминальный гейт P1), производно P2.1/P2.5/P3.4 (пинят его артефакт)
- **Evidence:**
  - `phases/P1.md:115` — Scope: «actual cold generated install/discovery **of the repository
    marketplaces**»; `phases/P1.md:120` — «install **only normal generated marketplace
    bundles** … гейт строит полное множество identity→носители … **падает на ЛЮБОЙ identity
    с ≥2 носителями**»; `roadmap.md:274` (carrier P1.4) — «cold-install only normal
    repository marketplace bundles … fail on ANY identity with two or more carriers».
  - Нигде — ни в ТЗ P1.4, ни в contracts P1.1, ни в carrier'е — не объявлено, **какое
    подмножество units включается в позитивной фикстуре**.
  - Машинная проверка (мой прогон, дерево аудита): после ремедиации P1.2/P1.3/P1.5
    (удалены ровно 16 root-дублей) в репозиторных marketplace остаются **9 unit↔unit
    коллизий по построению**: `anti-drift`, `compact-responses`, `context-economy`,
    `mcp-advisor`, `plan-protocol`, `session-handoff`, `verify-claims` (`core`+`general`),
    `gh-review` (`core`+`oss-dev`), `query-craft` (`core`+`research`).
  - `plan.md:236` (D42) прямо запрещает их чинить: публикацию донорских бакетов и состав
    `core` план не трогает, enabled-множество не меняет — только диагностика.
  - Десятая: при наличии `general` в фикстуре `workflow-craft` получает второго носителя
    (`unit:general` + declared class-B root-проекция), что **нарушает precondition самой
    class-B записи** «no enabled unit serves this identity» (`phases/P1.md:44`, D43).
- **Failure scenario:** холодный исполнитель P1.4 читает «install only normal repository
  marketplace bundles» буквально → ставит все ~50 units → catalog-wide гейт падает на 9–10
  identity, **ни у одной из которых нет owning item'а** (D42 запретил их чинить, P1.5 их
  Scope Excluded). Терминальный item фазы становится неисполним ПОСЛЕ трёх мутационных
  items. Альтернатива хуже: исполнитель молча сужает фикстуру до `{core, task, architect}`
  (единственный состав, при котором сходится перечисление Deliverables), получает
  «catalog-wide collisions 0» и пинит этот артефакт в P2.1/P2.5/P3.4 — то есть выдаёт
  зелёное по **необъявленному** сужению набора, ровно «suppression, not ownership»,
  запрещённое D28/D40. Живая коллизия `query-craft` (`core`+`research` включены обе) при
  этом остаётся непокрытой, а `findings/P1.4-effective-runtime-proof.md` утверждает 0.
- **PROMOTE-CANDIDATE:** гейт «uniqueness над каталогом» обязан объявлять **состав каталога**
  (какие units включены) в том же ТЗ; иначе «catalog-wide» — это «wide по усмотрению
  исполнителя», и метрика 0 недоказуема. Кандидат в `plan-protocol`: если item доказывает
  свойство множества, множество должно быть declared literal, а не «всё, что найдётся».

#### F2 — Ремонт ввёл P1.5 (`repository-bootstrap@0.2.0`, 27 targets), но downstream-литералы остались `0.1.0`/26 — в P2.2 и P4.3

- **Severity:** Blocker · **Label:** issue
- **Items:** P2.2, P4.3
- **Evidence:**
  - `phases/P1.md:44` (ledger P1.1, обновлён ремонтом): «P2.2 … while `repository-bootstrap`
    remains **`0.2.0`** byte-identical»; `phases/P1.md:101` (P1.5): «`repository-bootstrap`
    `0.1.0→0.2.0`», combined lock «до **27** targets».
  - `phases/P2.md:57` (P2.2 Implementation Rules, изменён ремонтом ради D47, но литерал не
    свёрстан): «In particular **`repository-bootstrap@0.1.0`**, its 13 private canonical
    skill bytes, **26 root projections** and combined lock are read-only inputs and must
    remain byte-identical».
  - `phases/P4.md:72` (P4.3 Implementation Rules): «… including private
    **`repository-bootstrap@0.1.0`**, its **26** thin root projections, combined lock and
    zero normal marketplace entries. **Any drift reopens the exact owning item под D27/D31**».
  - `git status`: `phases/P4.md` вообще не входит в дифф ремонта — файл не просматривался.
- **Failure scenario:** P2.2 исполняется ПОСЛЕ P1.5, где unit уже `0.2.0`/27. Его собственное
  правило «changed unaffected unit … fails the item» делает утверждение неудовлетворимым:
  либо item падает closed посреди P2 с уже раскатанными бампами `plan-protocol@2.12.0`/
  `skiller@0.5.0`/`task@0.4.0`, либо исполнитель «восстанавливает» заявленное состояние —
  удаляет class-B проекцию `workflow-craft` и откатывает `repository-bootstrap` к `0.1.0`,
  обнуляя P1.5 и делая уже выданный `findings/P1.4-effective-runtime-proof.md` ложным.
  P4.3, read-only терминальный item, по своему же правилу отчитывается о drift и
  **переоткрывает P1.5** — реопен-цикл на ровном месте, ровно тот failure mode, который
  этот план создан устранить.
- **PROMOTE-CANDIDATE:** добавление item'а внутри bounded repair обязано тянуть машинный
  свип литералов версии/числа целей по ВСЕМ фазам, а не только по фазе реопена. Кандидат:
  `plan-lint` — гейт «версия publication-unit упоминается более чем в одном месте → все
  упоминания обязаны совпадать или нести явный `(состояние до <item>)`».

#### F3 — Deliverables P1.4 несёт число «29», противоречащее собственному перечислению (30)

- **Severity:** Major · **Label:** issue
- **Item:** P1.4
- **Evidence:** `phases/P1.md:123` — «**29** exactly-once IDs в Codex-каталоге (13 class-A +
  1 class-B + 6 core + 6 task + 4 `architect` — из installed bundles)». 13+1+6+6+4 = **30**.
  Проверено против фактического инвентаря: 30 каталогов `.agents/skills` = 16 удаляемых
  дублей + 14 остающихся root-carrier'ов; после ремедиации Codex-каталог по этим группам
  несёт ровно 30 identity (14 из root + 16 из installed bundles).
- **Failure scenario:** ассершен пишется по числу, а не по перечислению: гейт зеленеет при
  30 фактических против ожидаемых 29 только если исполнитель «потеряет» одну identity —
  вероятнее всего именно class-B `workflow-craft`, единственную новую и единственную
  асимметричную; либо гейт падает на 30 и исполнитель «чинит» его, вычеркнув declared target.
  Замороженный литерал, не сходящийся со своей же формулой, — тот самый класс дефекта
  (`pinned-not-recomputable`, использованный как exact scope), ради устранения которого
  писалась D40.

#### F4 — Весь аудируемый ремонт не закоммичен; несущие слои знаний (`findings/11`, `findings/12`) — untracked, при этом `findings/12` запинен как execution input

- **Severity:** Blocker · **Label:** issue
- **Items:** P1.1 (Inputs/Required Reads), план целиком (портируемость D25/D26)
- **Evidence:**
  - `git status --porcelain plans/2026.07.24-AGENT-RELIABILITY` → `M` на
    `plan.md`/`roadmap.md`/`index.md`/`handoff.md`/`journal.jsonl`/`brief/01`/`phases/P0–P3`;
    `??` на `findings/10`, `findings/11`, `findings/12`. HEAD (`916acdb5`) содержит v1.8.0:
    21 item, без P1.5, без D39–D49.
  - `phases/P1.md:41` (Inputs P1.1) и `phases/P1.md:43` (Required Reads #24) пинят
    `findings/12-effective-collision-remeasure.md`; `plan.md:234` (D40) несёт маркер
    `RAG:— (repo-grounded: findings/12…)` на **не существующем в репозитории** файле.
  - `roadmap.md:51-52`: «All execution-required historical evidence **is committed**».
  - `handoff.md:41` — carrier A3 предписывает аудит «**on the committed post-repair tree**»;
    такого дерева нет, и этот заход физически не мог его использовать.
  - D26/`brief/01-refinements.md:83-88`: multi-session/high-risk/audit-план обязан ссылаться
    только на committed execution inputs; D47/`phases/P2.md:57` вводит именно это правило в
    `plan_lint` и делает **этот план** self-conformance-фикстурой.
- **Failure scenario:** любой cold-start (новая сессия по `git log`, клон, worktree, как у A2)
  видит v1.8.0 — 21 item, замороженные «12 коллизий», отсутствующий P1.5 и отсутствующий
  `findings/12`. Исполнитель P1.1 либо падает closed на несуществующем Required Read, либо
  работает по опровергнутой премиссе D28. Отдельно: когда P2.2 включит собственное tier-
  правило и прогонит self-conformance `plan-lint` на этом плане, `findings/12` как
  execution input вне репозитория обязан дать ERROR — план не удовлетворяет правилу,
  которое сам вводит.
- **PROMOTE-CANDIDATE:** design pass / bounded repair не завершён, пока bookkeeping-коммит
  не сделан: «состояние в рабочем дереве» не является планом для холодного исполнителя.
  Кандидат в `plan-protocol` §8: handoff, предписывающий следующему шагу «committed tree»,
  обязан нести хеш этого дерева — плейсхолдер/отсутствие = ERROR линтера.

#### F5 — §8 Acceptance замораживает недостижимый floor «Effective semantic identity collisions | 0»

- **Severity:** Minor · **Label:** issue
- **Items:** P0.3 (freeze), P3.5/P4.3 (измерение)
- **Evidence:** `plan.md:295` — метрика без квалификатора «0». `plan.md:236` (D42) и
  `phases/P1.md:106` (Pending Work P1.5): живая пара `core`+`research` даёт коллизию
  `query-craft`, план её не закрывает, «живая правка enabled-множества остаётся
  Owner-решением **вне этого item'а**». Ни G0, ни G1 (`plan.md:355-359`) этого Owner-решения
  не содержат.
- **Failure scenario:** P0.3 замораживает floor, который по построению плана не берётся на
  живом хосте. На P3.5/P4.3 остаётся выбор: RED по метрике, которую план сам себе запретил
  чинить, либо тихое переопределение метрики в «0 в фикстуре» — то есть риск «Self-host
  GREEN is called fleet GREEN» из §9, только внутри self-host.

#### F6 — Inputs P1.4 требуют Completion Notes P1.5, Required Reads их не называют

- **Severity:** Nit · **Label:** nitpick
- **Item:** P1.4
- **Evidence:** `phases/P1.md:117` (Inputs) — «P1.2/P1.3/**P1.5** committed Completion Notes
  (P1.5 обязан быть 🟢…)»; `phases/P1.md:119` (Required Reads #4) — «`phases/P1.md`
  **P1.2/P1.3** Completion Notes».
- **Failure scenario:** исполнитель читает Required Reads как исчерпывающий список и не
  открывает Completion Notes P1.5; смягчено тем, что #19/#20 пинят его closure-отчёт и
  extension map, а Implementation Rules требуют green P1.5 явно.

### Проверено без находок (с доказательствами)

- **D40–D44 — воспроизведены независимо** (собственный скрипт, не скрипт `findings/12`):
  20 worst-case, 23/23 enabled, 16 root↔installed + 1 installed↔installed, 14 уникальных
  root-carriers, 30 каталогов `.agents/skills`, 13 `.claude/skills`. Расхождений с
  `findings/12` нет ни в одном имени.
- **Owner-map полон для root↔installed:** 6 core-root'ов = ровно 6 путей `(delete)` в Files
  P1.2 (`phases/P1.md:61`); 6 task-root'ов = ровно 6 путей `(delete)` в Files P1.3
  (`phases/P1.md:80`); 4 `architect`-root'а = ровно 4 пути `(delete)` в Files P1.5
  (`phases/P1.md:99`). Ни одной измеренной root↔installed коллизии без owner-item.
- **D41 (порядок P1.5 → P1.4) объявлен во всех носителях:** §3 Routing
  (`plan.md:165-166`), Phase Status (`phases/P1.md:21-32`), Title item'а
  (`phases/P1.md:91`), Карта roadmap (`roadmap.md:66-67`), Phase Handoff
  (`phases/P1.md:133`), carrier P1.5 и carrier P1.4 (`roadmap.md:253,274`); fail-closed
  вход P1.4 — `phases/P1.md:117,120`.
- **D45:** производитель — P0.1 (Scope `phases/P0.md:30`, Files `:33`, Implementation Rules
  `:35` с идемпотентной валидацией 40-hex/`cat-file -t`/ancestor, Validation `:37`,
  Deliverables `:38`, Pending Work `:40`); потребитель — P3.4 (Inputs, Required Read #4,
  Implementation Rules с ancestor-валидацией **до** `git worktree add`, аргумент
  `--pre-plan-sha` в Validation). Изобретение ref'а запрещено дословно.
- **D46:** `phases/P3.md` Code Guidance несёт `--effort high` в Claude-форме,
  `model_reasoning_effort="high"` в Codex-форме, запись фактического effort в
  `canary-manifest` и fail-closed на `unknown`. Флаг подтверждён локально (CLI 2.1.220).
- **D47:** `python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY`
  присутствует в Validation P2.2 (`phases/P2.md:59`); правило self-conformance с владельцем
  правки внутри P2.2 и разграничением provenance/execution input — `phases/P2.md:57-58`;
  foreign-commit атрибуция — `plan.md:125-130` (§2), `phases/P1.md:44` (реализация +
  негативные фикстуры), `plan.md:325` (§9). Cross-plan сцепка сверена с
  `plans/2026.07.25-ECO-OPT/plan.md:49-50` и его D9/D10 — совпадает.
- **D48:** `phases/P2.md:109,113` — «task-specific temporary roots», явный запрет
  `HOME`/`CODEX_HOME` и записи в user-owned глобальное состояние; формулировка совпадает с
  `phases/P1.md:120` и `phases/P3.md` Code Guidance. Делегирование мысли `brief/02` в
  ECO-OPT зафиксировано D48 с честным `[UNVERIFIED]` на RAG-утверждении brief/02.
- **D49:** A2 RED зафиксирован без переписывания истории — §1 (`plan.md:69-77`), D49,
  §10 (`plan.md:339-345`), `roadmap.md:18-23,556`, `index.md:35`, `handoff.md:5-7,93-96`.
  `findings/07`–`findings/09` не изменены (git status), вердикты RED не переименованы.
- **Owner boundary:** §10 — A0, A1, A2 и authority D все CONSUMED; `G-EXEC` не выдан;
  все 22 items `⬜`; ни один носитель не разрешает P0.1. Гейт P0.1 больше не ссылается на
  исчерпанный слот (`phases/P0.md:14`, `roadmap.md:59,106,554-557`) — F3 отчёта A1 закрыт.
- **Дизайн-бюджет:** Meta `Design Passes: 5/5`; в §6 Update Log пять различимых «Design
  pass» (1/3, 2/3, 3/3, 4/4, 5/5); `Last Updated` (2026-07-25) не старше последней строки
  Update Log (2026-07-25). Ремонт корректно не увеличил счётчик (D39).
- **Структура и DoR:** 22/22 items несут все 16 полей; 0 `[NEEDS CLARIFICATION]`; wildcard
  в `Files` нет; §4 Phase Index 0/22 сходится с Phase Status всех пяти фаз.
- **Контракты фаз связны:** «Потребляет» P1/P2/P3/P4 производится предыдущими фазами;
  §7 Exported содержит `risk-review-loop-budget-v1` (F6 A1 закрыт) и три cross-plan строки
  с потребителем ECO-OPT (F7 A1 закрыт); потребители `semantic-identity-ownership-v1` и
  `generated-artifact-version-v1` дополнены P1.5.
- **Покрытие брифа:** все пять входов `brief/00` имеют носитель (`findings/00–05`, P1);
  «SSOT для skills/tasks/hooks/instructions» покрыт P1 (skills/tasks) + P0.4 (hooks) +
  D48-делегированием (instructions); «Не входит» соблюдён (FOREMAN/fleet/consumers —
  read-only во всех Execution Rules).
- **Границы записи:** `plan.md:101-102`, `phases/P3.md` (disposable worktree, non-force
  cleanup, запрет `reset --hard`/stash/cherry-pick), `phases/P4.md` (P4.2 no-write proof).

### Известный долг (не находки этого захода)

Три находки A2 (`findings/11`): порядок capture `base-sha` по D36 против канонического
порядка `plan-exec`/`plan-run` — новый P1.5 сознательно повторяет общий паттерн фазы;
отсутствие workflow-carrier у заявленной автономной цепочки; `research/01–03` без ссылок на
слой 1 и без маркера enum §7. A1 F11 (нет готового launch-block'а для acting provider вне
Codex-проекций; неидемпотентность шага (0) описана только через D36). Зеркальная
`Consumed`-строка в `plans/2026.07.25-ECO-OPT`. Claude-проекция `workflow-craft` (нужен
`skiller budget --first-turn`). Claude enabled-set = `unknown`. `findings/P1.5-collision-
closure.md` вне Required Reads P2.1/P2.5/P3.4. Перечислено как контекст; в вердикт не входит.

### Что запускать

Вердикт RED на шестом заходе → **решение владельца** (`AUDIT-CAP`). Команду ниже НЕ запускать
без явного нового bounded-repair гранта: ни RED, ни этот заход ремонта не выдают. Варианты
владельца: (а) грант на bounded repair F1–F4 + новый audit-слот; (б) `G-EXEC` под НАЗВАННЫЙ
долг — но F1/F2/F4 делают P1.4, P2.2 и P4.3 неисполнимыми, поэтому этот вариант означает
старт плана с тремя заведомо падающими items; (в) остановка плана.

| Model | Thinking | Context | Суть |
|:--|:--|:--|:--|
| Claude opus (frontier) | high | `NEW SESSION — шаг-не-item` | Bounded repair F1–F4 под новой authority владельца: объявить состав фикстуры P1.4, свести downstream-литералы `repository-bootstrap`, починить арифметику 29/30, закоммитить ремонт вместе с `findings/11–13` |

````
# НЕ раньше: явный Owner grant новой bounded repair authority — иначе не запускать
/task:plan-design 2026.07.24-AGENT-RELIABILITY P1

РЕЖИМ: реопен по §3 (4 шага) — bounded repair четырёх находок A3, НЕ детализация, НЕ exec, НЕ новый design pass
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/findings/13-design-audit-a3.md — прочитать ПЕРВЫМ; затем phases/P1.md P1.4/P1.5, phases/P2.md P2.2, phases/P4.md P4.3, plan.md §§5(D40–D49),8,10, roadmap.md (carrier P1.4)
СКОУП: 1) F1 — объявить в ТЗ P1.4 и в его carrier'е ТОЧНОЕ множество units позитивной фикстуры (declared literal) и записать D#, что core↔donor коллизии (9 шт.) и `workflow-craft`↔`unit:general` — не гейт, а диагностика D42; иначе дать им owner-item; 2) F2 — свести `repository-bootstrap@0.1.0`/26 к `0.2.0`/27 в phases/P2.md:57 и phases/P4.md:72 (либо явно пометить «состояние до P1.5»); 3) F3 — заменить «29 exactly-once IDs» на 30 в phases/P1.md:123 либо вывести число формулой; 4) F4 — закоммитить ремонт v1.9.0 вместе с findings/10–13 одним bookkeeping-коммитом и проставить его хеш в handoff.md вместо «committed post-repair tree»; попутно F6 (добавить P1.5 Completion Notes в Required Reads P1.4) и решить по F5 (квалификатор метрики §8 или Owner-гейт на enabled-множество)
НЕ ТРОГАТЬ: ТЗ/Scope/Files/Validation остальных 18 items; findings/07–12 и все исторические вердикты RED (факты, не переименовывать); artifacts/source-evidence/** (immutable); packages/** и runtime (design-only); исторические Codex-блоки roadmap как projections; plans/2026.07.18-FOREMAN; чужой незакоммиченный дифф в рабочем дереве (архив-переносы + tmp/)
````
