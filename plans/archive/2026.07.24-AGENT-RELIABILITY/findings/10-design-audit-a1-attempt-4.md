# Design audit A1 (Owner authority C, D32) — 2026.07.24-AGENT-RELIABILITY

**Дата:** 2026-07-25 · **Режим:** pre-exec design audit всего плана (cold context, adversarial)
**Исполнитель:** Claude Opus 5 / xhigh (frontier/xhigh по §3 Routing)

## Audit design — 2026-07-25

**Вердикт: RED**

`AUDIT-CAP: design-аудит — 4-й заход` (историч. cap 2/2 исчерпан RED'ами, exceptional slot B
1/1 исчерпан RED'ом attempt 3, authority-C слот A1 `0/1` израсходован этим отчётом).
Реопен/новый ремонт я не назначаю: по D29/D32 любой вердикт завершает audit-сессию, non-GREEN
возвращает решение владельцу. P0.1 не авторизован; `G-EXEC` не наступил.

### Якорь и детерминированные проверки

Всё ниже — на дереве `fe3e1646` (`codex/provider-project-sync`), рабочее дерево несёт чужой
незакоммиченный дифф (архив-переносы старых планов + `tmp/`) — не трогал, в проверки не входит.

- `python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY` →
  **0 ERROR / 0 WARN** (`OK (1 план(ов))`) (на `fe3e1646`).
- `bash packages/<pkg>/scripts/validate.sh`: **task 228 · skiller 418 · harness 412 ·
  analyst 211** тестов, все `validate: OK` (на `fe3e1646`).
- `check-translations` (внутри skiller validate): локальных 160, EN протух/без маркера **0**,
  осиротевших 0; CORE резидент **663 ток / target 750 — OK (9/9)**.
- Структурный свип 21/21 item: все **16** обязательных полей присутствуют (0 пропусков).
- **F2 attempt 3 закрыт:** ни один Required Read не является артефактом того же item'а без
  раннего производителя (машинная сверка Required Reads ↔ Files ↔ порядок items).
- **F1 attempt 3 закрыт для 4 названных мест:** все 4 употребления `$ITEM_BASE_SHA`
  (`phases/P1.md:57,76`, `phases/P2.md:59,78`) определены `base-sha.txt` того же item'а,
  файл в `Files` каждого из P1.2/P1.3/P2.2/P2.3.
- **F3 attempt 3 закрыт:** `--check-bootstrap-map` присутствует и в Code Guidance
  (`phases/P1.md:37`), и в Validation (`phases/P1.md:38`).
- D33 (repo-grounded) подтверждён: `packages/task/configs/command-routing.json` →
  `mappings.claude-code.capability_bindings["command.subagents"] = "native"`,
  `class_selectors: implementation→sonnet, frontier→opus`, effort `low/medium/high/xhigh`,
  `invocation_binding.template = "/{command_id} {arguments}"` — таблица renderer'а
  `roadmap.md:34-41` ей соответствует.
- Read-only факт окружения: `codex plugin list --json` (2026-07-25, cwd = корень репо) →
  **23** включённых плагина `@swissknifeman`, не два; `~/.codex/config.toml` (mtime
  2026-07-24 20:41) содержит `[plugins."architect@swissknifeman"] enabled = true` и
  `[plugins."research@swissknifeman"] enabled = true`.
- `claude --version` → **2.1.220**; `claude --help` → флаг **`--effort <level>`** существует.

Средовых блокеров, влияющих на вердикт, не было.

### Findings

#### F1 — Замороженный scope «12 коллизий» опровергается фактическим runtime; «остальные root-адаптеры уникальны» ложно

- **Severity:** Blocker · **Label:** issue
- **Items:** P1.1, P1.2, P1.3, P1.4 (D28, D31, Execution Rules `plan.md:85-91`)
- **Evidence:**
  - `plan.md:183` (D28) и `findings/03-ssot-runtime-inventory.md:19-24`: премисса —
    «установленные `core@0.4.0` + `task@0.3.0` добавляют 20; пересечение — 12».
  - Факт (read-only, тот же самый источник, что цитирует D28): включены 23 плагина
    `@swissknifeman`, среди них `architect@0.4.0` (15 скиллов, в т.ч. `architecture`,
    `codebase-design`, `domain-modeling`, `package-contribution-protocol`) и
    `research@0.4.0` (`query-craft`, `research`).
  - `.agents/skills/` содержит ровно те же идентичности как root-адаптеры:
    `.agents/skills/{architecture,codebase-design,domain-modeling,package-contribution-protocol}/SKILL.md`
    (`name:` совпадает с `packages/skiller/skills/architect/<name>/SKILL.md`).
  - `query-craft` имеет **два installed-носителя**: физическая копия
    `packages/skiller/adapters/codex/core/skills/research/query-craft/` в `core@0.4.0` и
    канон в `research@0.4.0` — плюс root-адаптер `.agents/skills/query-craft/`.
  - `Execution Rules` (`plan.md:85-88`) утверждает, что `.agents/skills`/`.claude/skills`
    содержат **только** generated thin repository-bootstrap projections для идентичностей,
    не обслуживаемых installed bundle, и что их canonical sources — ровно 13.
- **Failure scenario:** после P1.2/P1.3 (удалены ровно 12 каталогов) в `.agents/skills`
  остаются 5 рукописных thin-адаптеров, из которых **4 дублируют включённый
  `architect@0.4.0`**; `query-craft` остаётся дублированным между двумя installed-плагинами.
  P1.4 гейт «identity uniqueness … in each provider's own effective catalog … invalid
  carriers 0» тогда либо (а) падает без owning-item ремедиации — уже ПОСЛЕ обеих мутаций
  P1.2/P1.3, либо (б) проверяет только перечисленные 25 ID и выдаёт зелёный при живых
  коллизиях — то есть ровно «suppression, not ownership», прямо запрещённый D28.
  Фактическое число root↔installed коллизий — **16**, плюс одна installed↔installed.
- **Второй слой того же дефекта (evidence):** `artifacts/source-evidence/runtime/
  effective-runtime-inventory.json` — 886 байт прозы (`green`/`not_green`/`redactions`), в
  нём **нет ни одной identity-записи**, ни списка плагинов, ни версий. При этом P1.1
  Implementation Rules (`phases/P1.md:36`) требует «Reproduce the before-state from the
  committed runtime inventory … **never scan a live profile/cache**», а Validation
  (`phases/P1.md:38`) передаёт этот файл как `--before-state`. Следствие: исполнитель P1.1
  не может ни воспроизвести «12», ни обнаружить недостающие 4 — детекция коллизий
  структурно недоступна изнутри разрешённых входов, а число 12 фактически
  `pinned-not-recomputable`, но используется как замороженный exact scope удалений.
- **PROMOTE-CANDIDATE:** «before-state как проза вместо машинных записей» — прецедент для
  правила: если item обязан диффать состояние против committed before-state, before-state
  обязан быть машинно-сравнимым (records, не bullets), иначе гейт вырождается.

#### F2 — `PRE_PLAN_SHA` для rollback-репетиции P3.4 не определён ничем (класс F1 attempt 3 не закрыт)

- **Severity:** Blocker · **Label:** issue
- **Item:** P3.4
- **Evidence:** `phases/P3.md:88` (Scope: «candidate/pre-plan SHAs»), `phases/P3.md:90`
  (Inputs: «P0 baseline `pre_plan_sha`»), `phases/P3.md:93` («freeze `CANDIDATE_SHA` and
  `PRE_PLAN_SHA` … Rollback switches cleanly to `"$PRE_PLAN_SHA"`»). Грепом по всему
  каталогу плана `pre_plan|PRE_PLAN|pre-plan` встречается ТОЛЬКО в `phases/P3.md`.
  В committed `artifacts/source-evidence/precomputed/baseline.json` ключей sha нет вовсе
  (полный обход ключей: `schema_version`, `method`, `period`, `projects/*`,
  `dedup_correction/*`, `journals/*`, `limitations`). P0.3 (`phases/P0.md:71-75`) не
  производит такого поля, `run_canary.py` объявлен с `--repo/--candidate-sha/--baseline/
  --cases/--out-dir` (`phases/P3.md:95`) — аргумента pre-plan нет.
- **Failure scenario:** единственный item, который делает реальные git-мутации, обязан
  отрепетировать rollback на коммит, который никто не фиксирует и не передаёт. Холодный
  исполнитель либо изобретает «pre-plan» коммит сам (невоспроизводимо, риск переключения
  worktree на произвольный ref), либо не выполняет rollback-часть Validation и закрывает
  item без доказанного откатного пути — при том что `Pending Work` P3.5 прямо ссылается на
  «rehearsed pre-plan path» как на путь ROLLBACK всей фазы.
- **PROMOTE-CANDIDATE:** ремонт attempt 3 закрыл 4 названных употребления `ITEM_BASE_SHA`,
  но не КЛАСС «load-bearing идентификатор без объявленного производителя». Правило-кандидат:
  `plan-lint`/`plan-design` — гейт «каждая ссылка `$VAR`/`` `key` `` в Inputs/Rules/Validation
  имеет объявленного производителя (файл+item) или inline-определение в том же блоке».

#### F3 — Гейт запуска P0.1 ссылается на исчерпанный слот A0/D29 вместо A1/D32

- **Severity:** Major · **Label:** issue
- **Items:** P0.1 (гейт фазы), roadmap
- **Evidence:** `phases/P0.md:14` — «Потребляет: … literal GREEN exceptional design audit
  **under D29** + отдельный explicit Owner execution approval `G-EXEC`»;
  `roadmap.md:530` — таблица гейтов: строка **A0** «единственный exceptional independent
  design audit under D29», строка `G-EXEC` — «после **A0** GREEN»; строки **A1 в таблице
  нет**; `roadmap.md:55` — гейт P0.1 «**A0** literal GREEN + … `G-EXEC`»;
  `roadmap.md:103` (P0.1 carrier) — «Verify … the sole exceptional design audit **under D29**
  has literal GREEN». При этом `plan.md:270-276` фиксирует: **A0 — CONSUMED (RED)**, а
  действующий слот — **A1 (D32)**.
- **Failure scenario:** холодный исполнитель P0.1 проверяет гейт буквально по phases/P0.md и
  roadmap: «GREEN аудита под D29». Такого артефакта не будет никогда (слот закрыт RED'ом,
  `findings/09`). Либо fail-closed на неисполнимом условии (лучший случай — плановый item не
  стартует даже после реального `G-EXEC`), либо исполнитель «дочитывает» условие как
  выполненное историческим аудитом и стартует мутации без действующего гейта. Единственное
  место с правильным гейтом (`plan.md` §10) конфликтует с тремя носителями, а канон требует
  ровно одну эффективную формулировку гейта.

#### F4 — Claude-трейл canary не может запинить effort по написанному (флаг существует, но не назван)

- **Severity:** Major · **Label:** issue
- **Item:** P3.4
- **Evidence:** `phases/P3.md:94` — «Invoke the acting provider's headless CLI … with the
  routed **model/effort pinned explicitly** (Claude: `claude -p` … with
  `--model`/`--permission-mode` per unattended profile; Codex historical form: … exact `-m`,
  `model_reasoning_effort`, …)». Для Codex effort назван, для Claude — нет; фактически
  `claude --help` (CLI 2.1.220) содержит `--effort <level>`, а roadmap-таблица
  (`roadmap.md:38`) требует «exact `low/medium/high/xhigh`».
- **Failure scenario:** шесть canary-кейсов выполняются на effort по умолчанию сессии/профиля,
  а не на `implementation/high` из §3 Routing. Дальше: (а) P2.4 route-evidence фиксирует
  `actual effort = unknown` и по своему же правилу «unknown fails a route-required dispatch»
  роняет диспатч, либо (б) paired canary-метрики приписываются маршруту, который не
  применялся, — и P3.5 сравнивает несопоставимые прогоны, считая это доказательством.

#### F5 — P2.2 переписывает `plan_lint`/канон-команды, которые гейтят закрытия ЭТОГО плана, без self-conformance проверки

- **Severity:** Major · **Label:** issue
- **Items:** P2.2 (и производно P2.3–P4.3)
- **Evidence:** `phases/P2.md:55` — Files включают `packages/task/lib/task/plan_lint.py` и
  все пять `packages/task/commands/plan-*.md`; `phases/P2.md:57` — «`plan_lint` **rejects**
  a high-risk/multi-session/handoff/audit plan whose execution input is neither a committed
  repo path nor an exact predecessor-produced path, and rejects external
  host/chat/mAInd/`tmp`/foreign paths used as execution inputs»; `phases/P2.md:59` —
  Validation НЕ содержит `plan-lint plans/2026.07.24-AGENT-RELIABILITY` (сравн. P0.1, P0.4,
  P1.1, P1.4, P3.5, P4.3 — там он есть). Сам план — high-risk/multi-session/audit, и
  `brief/00-brief.md:42-43` содержит ссылку на `tmp/swissknifeman-audit.md`.
- **Failure scenario:** новые tier-правила применяются к активному плану впервые на шаге 4
  ритуала закрытия (`plan-lint` после handoff) — то есть ПОСЛЕ того, как P2.2 уже изменил
  канон, команды и сгенерированные деревья. Если план не удовлетворяет собственному новому
  правилу (например, `tmp/`-ссылка в brief трактуется как execution input), гейт закрытия
  `K = 0` не берётся, а владельца правила (item, который обязан починить план или правило)
  нет: P2.3 прямо запрещено править канон-команды второй раз. Классический
  bootstrapping-тупик посреди фазы с уже раскатанными мутациями.

#### F6 — `risk-review-loop-budget-v1` производится P2.1, но отсутствует в §7 Exported

- **Severity:** Minor · **Label:** issue
- **Items:** P2.1 (донор), P2.3/P3.1/P2.5 (потребители)
- **Evidence:** `phases/P2.md:36` — Files P2.1 содержат
  `root/contracts/risk-review-loop-budget-v1.md`; читают его `phases/P2.md:75` (P2.3 RR#2),
  `phases/P3.md:35` (P3.1 RR#3), `phases/P2.md:113` (P2.5 RR#8), `phases/P4.md:71` (P4.3
  RR#18). В таблице `plan.md:210-219` (§7 Exported) контракта нет — там 8 записей без него.
- **Failure scenario:** у контракта нет строки владельца/версии/потребителей → изменение его
  формы не запускает ни cross-plan уведомление (§11), ни pinned-consumer сверку; при drift
  четыре потребителя расходятся молча.

#### F7 — Cross-plan сцепка с 2026.07.25-ECO-OPT объявлена только со стороны потребителя

- **Severity:** Minor · **Label:** issue
- **Items:** P2.2 (донор бампов), §7, §9 Risks
- **Evidence:** `plans/2026.07.25-ECO-OPT/plan.md` §2: «Coupling с AGENT-RELIABILITY: его
  P2.2 бампает plan-protocol/task-команды — items P2.2 и P7.1 этого плана НЕ стартуют, пока
  фаза P2 AGENT-RELIABILITY не терминальна»; D10 там же: «ECO-OPT (P1/P4 могут идти
  **параллельно**)». В этом плане ни §7 Exported/Consumed, ни §9 Risks, ни Execution Rules
  не упоминают ECO-OPT; `plan-protocol@2.12.0`, `skiller@0.5.0`, `task@0.4.0` (бампы P2.2)
  вообще не заведены как Exported-контракты с потребителями-планами.
- **Failure scenario:** (1) §11-уведомление не сработает: исполнитель P2.2 не знает, что у
  бампа есть план-потребитель; (2) параллельные коммиты ECO-OPT P1/P4 попадают в интервал
  между `base-sha.txt` item'а и его Validation, а `assert_generated_scope.py --baseline
  $ITEM_BASE_SHA` не имеет правила исключения чужих диффов — гейт «undeclared generated
  drift» падает ложно, и исполнитель не может отличить свою регрессию от чужого коммита.

#### F8 — Протухшая бухгалтерия: §1 Context, Meta `Design Passes`, контракт фазы P0, index.md

- **Severity:** Minor · **Label:** issue
- **Evidence:** `plan.md:53-59` — §1 описывает состояние «attempt 2/2 RED → Pass 4 (v1.6.0)»
  и ничего не знает про RED attempt 3, authority C и v1.7.0; `plan.md:21` — Meta
  `Design Passes` завершается «Следующий шаг — единственный exceptional fresh independent
  design audit (`0/1` использован до старта)», т.е. описывает уже израсходованный слот A0, а
  не A1; `phases/P0.md:14` — «Потребляет: brief + findings **00–08**» (findings/09 —
  несущий вход ремонта D34 — не назван); `index.md:3` — «Обновлён: 2026-07-24», в Evidence
  routing нет строк findings/08 и findings/09, а roadmap описан как «21 native Codex
  recovery carriers» (после D33 они historical projections).
- **Failure scenario:** cold-start читает §1/Meta/index как текущее состояние и получает
  прошлую картину авторитетов и слоёв знаний (в т.ч. «следующий шаг — A0»), что усиливает F3.

#### F9 — P2.5 Scope сохраняет «isolated provider homes», запрещённые уточнением владельца

- **Severity:** Minor · **Label:** issue
- **Item:** P2.5
- **Evidence:** `phases/P2.md:109` — «Scope Included: **isolated provider homes**; …»;
  `brief/01-refinements.md:29-30` — «удалить любую P1.4 isolation через `HOME`/`CODEX_HOME`;
  использовать только task-specific temporary roots»; ср. `phases/P1.md:93` («does not
  modify process home-directory environment») и `phases/P3.md:94` («do not set or repurpose
  `HOME`, `CODEX_HOME`») — у P2.5 такого запрета нет.
- **Failure scenario:** исполнитель P2.5 выполняет «изоляцию домов» через подмену
  `HOME`/`CODEX_HOME` (буквальное чтение своего Scope) — техника, отклонённая владельцем;
  побочно затрагивается user-owned глобальное состояние провайдеров вне репо.

#### F10 — Мысль владельца из brief/02 (инструкционный контекст / спецнастройка провайдера) без носителя и без D-отклонения

- **Severity:** Minor · **Label:** issue
- **Evidence:** `brief/02-claude-takeover.md:7-12` — «возможно, SKM-окружение влияет на
  Codex и ему нужна сильно специфичная настройка (проверено RAG: монолитный/перегруженный
  инструкционный контекст действительно деградирует Codex; слоёная структура —
  рекомендация; **плюс** 12 duplicate-identity коллизий…)». В плане покрыта только вторая
  половина (коллизии → P1). Ни item, ни D-запись не адресуют слоение/вес инструкционного
  контекста и не передают мысль другому носителю, хотя фактически её ведёт другой план
  (`plans/2026.07.25-ECO-OPT/plan.md` D9 + P7.2 «Codex-профиль (тонкий AGENTS.md слой)»).
  Дополнительно: RAG-утверждение в brief/02 не имеет ни маркера из enum §7, ни файла в
  `findings/`.
- **Failure scenario:** при закрытии плана мысль считается покрытой (или молча потерянной);
  ссылки между планами нет, поэтому после G1 владелец не увидит, кто отвечает за
  инструкционный слой. Дешёвый фикс — одна D-запись «делегировано ECO-OPT D9/P7» (ремонт
  scope authority C её не покрывал).

#### F11 — Для acting provider нет готового launch-block'а; шаг (0) base-sha не идемпотентен

- **Severity:** Nit · **Label:** suggestion
- **Evidence:** `roadmap.md:77-83` — все 21 блок помечены «исторические Codex-projections …
  их НЕ копировать», Claude-запуск задан рецептом («`/model` + `/effort` → `/task:plan-*`»),
  готового copy-paste блока нет ни одного; при этом полезная нагрузка блоков (что именно
  проверить на входе, границы, «не мутировать X») живёт только внутри этих
  «не копировать» блоков. Отдельно: `phases/P1.md:55`, `phases/P1.md:74`, `phases/P2.md:57`,
  `phases/P2.md:76` — шаг (0) «`git rev-parse HEAD > base-sha.txt` первым действием» не
  описывает поведение при возобновлении прерванного item'а (перезапись существующего файла).
- **Failure scenario:** при cold-start владелец собирает запуск руками и теряет
  item-специфичные границы (они не продублированы вне Codex-блоков); при resume второй
  прогон шага (0) может переписать baseline и обнулить смысл diff-scope гейта.

### Проверено без находок (с доказательствами)

- **Слои знаний (§16):** `brief/` непуст (3 файла), `findings/` 00–09, `research/` 01–03,
  `artifacts/source-evidence/` с верификатором; несущие внешние факты имеют `RAG:✅` с датой
  и ссылкой на `findings/05-external-practices.md` (D5, D10, D11, D15), остальные D — `RAG:—`
  с repo/plan-grounded ссылкой; маркер есть у 34/34 D-записей и у Intent/Why/Implementation
  Rules всех 21 items.
- **F1/F2/F3 attempt 3** — закрыты (см. «Якорь»): baseline-файлы, снятые self-produced
  Required Reads с явной пометкой, детерминированный `--check-bootstrap-map`.
- **Контракты фаз связны:** «Потребляет» P1/P2/P3/P4 производится предыдущими фазами
  (`phases/P1.md:15`, `phases/P2.md:16`, `phases/P3.md:14`, `phases/P4.md:14`); порядок
  строго P0→P4 (D17), 21 item, 21 строка §3 Routing, 21 строка Карты roadmap, 21 carrier.
- **Routing ↔ roadmap:** класс/effort совпадают построчно; `Exec = manual` → `task:plan-run`,
  `Exec = plan-exec` → `task:plan-exec` (21/21); `Plan context = same-session — item` и
  `Context = NEW SESSION` разделены корректно (канон `SKILL.md:763-788`).
- **Дизайн-бюджет:** Meta `Design Passes: 4/4`, в §6 Update Log четыре строки «Design pass»
  (1/3, 2/3, 3/3, 4/4) + отдельная строка ремонта под D32 — недобора нет; `Last Updated`
  (2026-07-25) не старше последней строки Update Log (2026-07-25).
- **Roadmap исполним по остальному:** все items solo, у каждого названа причина «нельзя
  объединить», гейты владельца стоят только там, где решение реально его (A0/G-EXEC/G0/G1),
  §3 Routing не противоречит Карте.
- **Развилки:** секции `## Обсуждение` в плане нет, нерешённых `[NEEDS CLARIFICATION]` в
  items нет (греп 0) — DoR по этому пункту чист.
- **Границы записи:** Execution Rules запрещают писать в `azguard`/`insiders`/`dterema`/
  FOREMAN/fleet (`plan.md:83-84`), P3.4 изолирован disposable worktree (`phases/P3.md:93`),
  P4.2 доказывает no-write сравнением `git status --porcelain=v1` (`phases/P4.md:55`).
- **stdlib-only и immutability бандла** соблюдены в спецификациях: P0.1 запрещает записи ниже
  `artifacts/source-evidence/` и проверяет `git diff --exit-code` по нему (`phases/P0.md:36-37`).

### Что запускать

Вердикт RED при исчерпанных слотах аудита → **решение владельца**. Команду ниже НЕ запускать
без явного нового bounded-repair гранта (authority D): по D29/D32 non-GREEN не даёт
автоматического ремонта или ещё одного аудита. Варианты владельца: (а) выдать authority D на
ремонт F1–F5 + один новый independent audit; (б) сдать план как есть с НАЗВАННЫМ долгом
(F1–F5 в Pending Work) и решать `G-EXEC` под этот долг; (в) остановить план.

| Model | Thinking | Context | Суть |
|:--|:--|:--|:--|
| Claude opus (frontier) | high | `cold-start — plan-step` | Ремонт F1–F5 под новой bounded authority владельца; A1 израсходован, четвёртый заход аудита без гранта не назначается |

````
# НЕ раньше: явный Owner grant новой bounded repair authority (D35) — иначе не запускать
/task:plan-design 2026.07.24-AGENT-RELIABILITY P1

РЕЖИМ: реопен по §3 (4 шага) — bounded repair пяти находок A1, НЕ детализация, НЕ exec, НЕ новый design pass
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/findings/10-design-audit-a1-attempt-4.md — прочитать ПЕРВЫМ; затем plan.md §§1,7,10, phases/P0.md P0.1, phases/P1.md P1.1/P1.4, phases/P2.md P2.2/P2.5, phases/P3.md P3.4, roadmap.md (таблица гейтов + Карта), index.md
СКОУП: 1) F1 — перезамерить effective-коллизии по фактическому runtime (23 включённых плагина, не 2), расширить D28/D31 scope и remediation-map, добавить machine-readable before-state (identity-записи) вместо прозы, назвать владельца дубля core↔research `query-craft`; 2) F2 — определить производителя и путь `PRE_PLAN_SHA` (файл + item + аргумент `run_canary.py`) либо снять rollback-репетицию из P3.4 с D-записью; 3) F3 — заменить A0/D29 на A1/D32 в phases/P0.md:14, roadmap.md:55, roadmap.md:530-531 и в P0.1-carrier; 4) F4 — назвать `--effort` в Claude-форме P3.4; 5) F5 — добавить `plan-lint plans/2026.07.24-AGENT-RELIABILITY` в Validation P2.2 и правило «план обязан удовлетворять собственным новым tier-правилам»; попутно F6–F10 (Exported-строка risk-review-loop-budget-v1, cross-plan ECO-OPT, §1/Meta/index staleness, P2.5 provider homes, D-запись про brief/02 → ECO-OPT)
НЕ ТРОГАТЬ: ТЗ/Scope/Files/Validation остальных 16 items; закрытые слоты аудитов A0/B и их findings 07–09 (исторические факты, не переименовывать); artifacts/source-evidence/** (immutable); packages/** и runtime (design-only); исторические Codex-блоки roadmap как projections; plans/2026.07.18-FOREMAN; чужой незакоммиченный дифф в рабочем дереве (архив-переносы + tmp/)
````
