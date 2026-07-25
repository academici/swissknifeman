# 2026.07.24-AGENT-RELIABILITY — надёжное исполнение, SSOT и замкнутая обратная связь

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.24-AGENT-RELIABILITY |
| Title | Надёжное исполнение: checked task contract, единственный runtime source, bounded review и измеримая обратная связь |
| Version | 1.12.7 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | Codex gpt-5.6-sol/high; Owner-override Pass 4 — gpt-5.6-sol/xhigh; historical authority-C repair — Claude Fable 5/high; bounded redesign Pass 5 — Codex gpt-5.6-sol/high; bounded A1 repair (authority D, D39) — Claude Opus 5/high; bounded A3 repair (authority E, D50) — Claude Opus 5/high |
| Last Updated | 2026-07-25 (P1.2 закрыт 🟠: 13 приватных root-bootstrap identities канонизированы, 26 тонких проекций + lock, skiller/core/skm 0.4.1, шесть root core-коллизий удалены) |
| Repository | swissknifeman |
| Related Packages | task, skiller, harness, analyst, maind |
| Execution Mode | reliability-first · evidence-before-mutation · phase-bounded |
| Target Operator Models | neutral Routing §3 is SSOT; provider renderer selected and verified at execution; current next audit recovery renderer — Codex `gpt-5.6-sol/xhigh` |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| Paused By | 2026.07.25-ECO-OPT, 2026-07-25 (D56: ACTIVE ушёл на design pass 2 ECO-OPT — этап A программы; план спроектирован полностью и ждёт этапов B/C) |
| Design Passes | 5/5 — исчерпан. Passes 1–5 и шесть literal RED design-вердиктов сохранены как история (`findings/07`–`findings/13`). Bounded repairs A1 (authority D, D39) и A3 (authority E, D50) — **не design passes**: счётчик не растёт. Персональное рационирование audit-слотов снято D50; действует канон plan-protocol «два аудита на фазу, третий → решение». `G-EXEC` для self-host P0–P3 выдан authority E; за владельцем остаётся только G1 |

## 1. Context

За 2026-07-20…24 крупные планы в `swissknifeman`, `azguard`, `insiders` и
`dterema` повторно теряли требования владельца, без нужды останавливались,
спрашивали уже данное согласование и возвращались в audit/fix loops.
Одновременно короткий `HONEST-HTTP-ERRORS` является clean counterexample.

Canonical controls уже содержали product-vs-bookkeeping verdict, two-audit
cap и `same-session — item`, но полевая работа им не соответствовала.
Поэтому план не объявляет причиной «отсутствующие правила». Он проверяет
falsifiable hypothesis: declarative controls не компилировались/не
проверялись на transition, pre-mutation, pre-final и public-acceptance
границах либо runtime выбирал stale/duplicate carrier. Duplicate identities
и session fragmentation остаются недоказанными усилителями до P0 traces.

Committed snapshot Perplexity-аудита в `artifacts/source-evidence/`
используется как hash-pinned hypothesis source, а не backlog. Там же лежат
lossless journal snapshots, sanitized selected session evidence и
precomputed corpus/baseline. План сначала проверяет self-contained bundle,
Task Contract и Acceptance bank; только затем меняет hooks/runtime.
P1 устраняет доказанные delivery/discovery collisions, P2 добавляет
enforcement существующих rules, P3 связывает traces/evals и выполняет
изолированный self-host canary. P4 не реализует speculative refactor:
он выносит code-grounded verdict, узкий operator doctor и Owner packet.

`plans/2026.07.24-AGENT-RELIABILITY/root/` — repo-relative canonical
artifact directory из plan-protocol, не системный `/root`. Плановые
contracts/commands одинаково видимы Claude и Codex; provider-specific
adapters и native launch blocks являются projections, а не скрытым SSOT.

Исторические design audits 1–4 оставлены literal RED. Attempt 2/2 —
`findings/08-design-audit-red-attempt-2.md`; exceptional attempt 3 —
`findings/09-design-audit-exceptional-attempt-3.md`; authority-C A1 —
`findings/10-design-audit-a1-attempt-4.md` (audited pre-redesign `fe3e1646`,
RED). Owner option B разрешил Pass 5 только по трём blockers `findings/09`.
Затем Owner authority D (D39) разрешила bounded repair ровно десяти находок
A1 (F1–F10) без нового design pass и без `G-EXEC`; её измерение — слой 1
`findings/12-effective-collision-remeasure.md`. Пятая находка A1 класса Nit
(F11) оставлена названным долгом, не ремонтом.

Ремонт A1 изменил несущее: фактические effective-коллизии Codex — **16
root↔installed плюс одна installed↔installed**, а уникальных root-carriers
**14** (13 repository-bootstrap + `workflow-craft`), поэтому newly measured
остаток получил собственного владельца — item **P1.5**, исполняемый ПЕРЕД
терминальным гейтом P1.4.

Параллельно с этим ремонтом отдельная сессия исполнила слот A2 на committed
`916acdb5` (до ремонта) и вернула **RED** — `findings/11-design-audit-owner-b-a2.md`
(D49): два Blocker (порядок capture `base-sha` по D36 против канонического
порядка `plan-exec`/`plan-run`; заявленная автономная multi-session цепочка без
workflow-carrier) и один Major (три research-файла без ссылок на слой 1 и без
RAG-маркера). Эти находки ВНЕ скоупа authority D и там не ремонтированы — они
остаются названным долгом.

Шестой design-аудит A3 (`findings/13-design-audit-a3.md`, 2026-07-25) вернул
**RED**: три Blocker (гейт P1.4 неисполним, пока не объявлен состав каталога
фикстуры; stale литералы `repository-bootstrap@0.1.0`/26 в P2.2 и P4.3; весь
ремонт v1.9.0 и `findings/10–13` не закоммичены), Major 29 vs 30, Minor по
метрике §8, Nit по Required Reads P1.4. Владелец ответил **authority E** (D50):
разработку пакета ведёт ИИ, участие владельца минимально — развилки, скоуп и
пороги агент закрывает сам записью, а не вопросом. Отсюда три следствия:
персональные audit-слоты A0–A3 становятся историей, а действует канон «два
аудита на фазу» (шесть RED при нуле исполненных items — это ровно тот
audit/fix-loop без продукта, который план создан лечить); `G-EXEC` считается
выданным для self-host P0–P3; за владельцем остаётся только необратимое и
наружу — G1 (tag/push/release, fleet, consumer-репозитории, FOREMAN). Ремонт A3
(F1–F6, D50–D55) закрыл названные Blocker'ы, и выход плана
`2026.07.19-DUAL-PROVIDER` переклассифицирован в low-trust вход (D54).

## 2. Execution Rules

- **Принципы кросс-плановой работы — `plans/README.md` § «Принципы кросс-плановой работы»
  (12 инвариантов И1–И12, решение владельца 2026-07-25).** Носитель ОДИН, здесь только ссылка.
  Обязательны для каждого item'а: **И1–И3** — каждая формулировка запрета (`запрещено`,
  `не трогаем`, `чужая поверхность`, `заморожено`) несёт владельца, причину и **ПРОХОД**
  (эскалация → D#), а «чужая поверхность» называет план И item, а не только пакет; **И4–И6** —
  у общей поверхности владелец и порядок, записанные в ТЗ ОБОИХ концов, корневые файлы
  (`CLAUDE.md`/`AGENTS.md`/`CHANGELOG.md`) машинному гейту невидимы и сверяются чтением;
  **И7–И9** — RAG-маркеры, премиса проверяется числом ДО закрытия вопроса, гейт диагностичен;
  **И10–И12** — расширение аддитивно (не ломает артефакты живых планов флота), механизм,
  повторённый ≥3 раза дисциплиной, — кандидат в канон, у каждой хеш-записи назван потребитель.
  Нарушение = находка кросс-планового аудита этапа C.
- `G-EXEC` выдан Owner authority E (D50) для self-host работы: P0–P3 исполняются
  без отдельного человеческого гейта. **Но над ним стоит программный гейт
  design-first (D56):** исполнение начинается только после этапов A–C программы
  (`plans/README.md` § «Программа: этапы A–D»). Первый item плана не стартует,
  пока этап B не показал 0 живых пересечений без владельца. Персональное рационирование audit-слотов
  (A0–A3) снято — это история, не действующий механизм; действует канон
  plan-protocol «два аудита на фазу, третий → решение», и вердикт аудита фазы
  выносит агент. Шесть исторических design-вердиктов остаются literal RED и не
  переименовываются.
- G0 (заморозка Acceptance после P0.3) агент принимает сам и фиксирует
  D-записью. За владельцем остаётся ровно G1 в P4.3: tag/push/release, fleet,
  раскатка на подключённые проекты, запись в consumer-репозитории, продолжение
  `2026.07.18-FOREMAN`. Граница — «нельзя откатить / видно снаружи», не граница
  компетенции.
- P0.1–P0.3 только фиксируют evidence/contracts. Любая behavior mutation,
  включая hooks, начинается не раньше зафиксированного D-записью P0.3 bank
  freeze (G0 принимает агент, D50) — порядок «заморозка до мутации» сохранён,
  сменился только субъект решения.
- Latest explicit owner instruction действует только в своём scope; нижний
  carrier может сузить safety, но не расширить authority.
- Routine implementation/tests/close/следующий ready item не требуют Owner
  Approval. Единственный реальный Owner gate — G1 в P4.3
  (fleet/consumers/FOREMAN/tag/push/release); P0.3 acceptance/bank freeze —
  внутренний гейт агента с обязательной D-записью.
- Existing audit cap/product distinction/same-session semantics не
  копируются новой прозой: P2 реализует единственный compiler/enforcement
  seam и conformance tests.
- Product, evidence и process findings имеют разные states. Evidence repair
  не переоткрывает доказанно green product; третий same-finding event
  создаёт incident, а не четвёртый fix loop.
- `azguard`, `insiders`, `dterema`, FOREMAN и fleet — read-only evidence.
  Writes разрешены только в self-host repo и disposable P3.4 worktree.
- `.agents/skills` и `.claude/skills` содержат только generated thin
  root-bootstrap projections для identities, не обслуживаемых enabled
  authoritative installed unit. Класс A — 13 identities без канона в бакетах:
  их sources живут только в private/source-only
  `packages/skiller/skills/repository-bootstrap/` (normal
  bucket/core/marketplace publication запрещена). Класс B (D43) — identity с
  каноном в публичном бакете, чей unit не включён: сейчас ровно
  `workflow-craft`. Хендмейд root-адаптеров не остаётся: после P1.5 root-набор
  каждого провайдера равен ровно declared target set (undeclared каталог —
  ошибка гейта, а не «уникальный carrier»).
- Фактически измеренная (D40, `findings/12`) collision-поверхность Codex:
  **16 root↔installed** (6 core + 6 task + 4 `architect`) и **1
  installed↔installed** (`query-craft`: `core` и донорский `research`
  включены одновременно). 12 из 16 удаляются в P1.2/P1.3; остальные 4 плюс
  `workflow-craft` ownership плюс детектор core↔donor-bucket — в P1.5.
  Task commands остаются только в `packages/task/commands`.
- Курируемый unit `core` и его донорские бакеты (`general`, `research`,
  `oss-dev`) взаимоисключающи по построению (D42). План не меняет
  user-owned enabled-множество: нарушение — машинный диагностический вывод с
  названной Owner-действием, никогда не тихая правка профиля.
- Item, доказывающий свойство МНОЖЕСТВА (uniqueness, closure, покрытие), обязан
  объявить это множество declared literal'ом в собственном ТЗ и материализовать
  его артефактом (D51). «Всё, что найдётся» и молчаливое сужение исполнителем —
  отказ item'а. Позитивная фикстура P1.4 — все units репозиторного marketplace
  минус ровно три донорских бакета; девять пар `core`↔донор и
  `workflow-craft`↔`unit:general` — предмет негативного прогона и диагностики
  D42, а не гейта.
- Выход плана `2026.07.19-DUAL-PROVIDER` — **low-trust вход** (D54): терминальный
  статус 🟠 и Codex-авторство не дают презумпции корректности. Items, опирающиеся
  на произведённые им seam'ы (`publication.py`, `registry.py`, `command_render.py`,
  Codex-адаптеры, root-поверхность `.agents/skills`), доказывают поведение тестом
  на месте.
- Generated projection обязана иметь owner, provenance/hash, complete
  dependency closure и одну effective semantic identity.
- Diff-scope guard отделяет свой дифф от чужих коммитов (D47): дрейф пути
  атрибутируется коммитам `$ITEM_BASE_SHA..HEAD`; путь, изменённый только
  чужим коммитом и лежащий вне owner-набора item'а, классифицируется
  `foreign-commit` и не считается undeclared drift; чужой коммит, задевший
  owner-путь, — fail closed с Owner-вопросом. Stash/revert/reset чужих правок
  запрещены (это остаётся правилом коммит-гигиены ниже).
- Canonical execution inputs живут в repo paths и semantic `task:*`
  carriers. Provider invocation рендерится только из checked mapping;
  `.agents` и native Codex blocks не переопределяют canon.
- Execution не читает `tmp/`, profiles, mAInd или foreign repos. Optional
  origin paths остаются provenance; только committed
  `artifacts/source-evidence/` является evidence input.
- Python остаётся stdlib-only. Missing evidence/route/capability остаётся
  unknown/red; ноль и silent skip запрещены.
- Каждый item коммитит только exact `Files`; `git add -A`, `git commit -a`,
  stash/revert чужих правок и staging `tmp/` запрещены.
- Item close следует canonical two-commit topology. Plan files закрываются
  отдельным bookkeeping commit; Pass 5 коммитит только bounded plan redesign.
- Design pass или bounded repair НЕ завершён, пока его результат не в коммите
  (D55): состояние рабочего дерева не является планом для холодного исполнителя.
  Каждый заход закрывается bookkeeping-коммитом ровно своих плановых путей, и
  `handoff.md`, предписывающий следующему шагу committed tree, несёт хеш этого
  коммита, а не плейсхолдер.
- После каждого item — exact focused tests; package validate — перед item
  commit; terminal phase — один bounded independent audit.
- Semantic `task:*` carrier и neutral Routing остаются SSOT. Provider
  renderer проверяется в cold-start preflight. Acting provider ни одной
  authority не назначен: следующий шаг рендерится из §3 Routing через checked
  mapping той сессией, которая его исполняет; 22 native Codex-блока `roadmap.md`
  остаются recovery-проекциями, а не назначением провайдера.
- Каждый item recovery carrier требует `command.subagents`; если cold-start
  preflight не подтверждает capability как `native`/`adapted`, execution
  fail-closed до mutation без silent solo fallback.
- `plans/2026.07.18-FOREMAN`: G1 покрывает ровно его наружные, необратимые
  части — fleet-раскатку и массовость пилота (D58, сужение по Ф1). Внутренний
  bookkeeping и дизайн-заходы (включая P1.5) идут по регистру очереди
  `plans/README.md` § «Кросс-плановая последовательность» — терминальные AR
  P1/P2 открывают CP-гейты — без отдельного G1-решения, если владелец явно не
  решит иначе. Bookkeeping-синхронизация его доски разрешена явным
  Owner-решением от 2026-07-25 и уже выполнена (его D49/D50: P1.4 закрыт по
  git-фактам, открыт P1.5 re-пин, `Paused By` → этот план); ни один его item
  не исполнялся. Межплановая очередь и владение поверхностями —
  `plans/README.md` § «Очередь планов и владение поверхностями».

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
|  | P0.1 | implementation/medium | plan-exec | full | deterministic committed-bundle verifier/normalizer, baseline load-bearing |
|  | P0.2 | frontier/high | manual | full | frozen Task Contract с открытыми design decisions; full-класс не батчится |
|  | P0.3 | frontier/high | manual | full | Acceptance/bank freeze и G0-решение агента (D50); full-класс не батчится |
|  | P0.4 | implementation/high | manual | full | hook lifecycle high-risk, реализация против frozen P0 contracts |
|  | P1.1 | frontier/high | manual | full | freeze cross-package identity/ownership semantics |
|  | P1.2 | implementation/high | manual | full | skiller/root/core publication correctness; full-класс не батчится |
|  | P1.3 | implementation/high | manual | full | task/harness effective catalog repair after P1.2; full-класс не батчится |
|  | P1.5 | implementation/high | manual | full | newly measured collision closure: root deletions + root-bootstrap class B + core↔donor detector; publication mutation, correctness-critical (исполняется ПЕРЕД P1.4) |
|  | P1.4 | implementation/medium | plan-exec | full | deterministic terminal conformance against frozen P1.1 (последний item фазы: требует green P1.5) |
|  | P2.1 | frontier/high | manual | full | freeze state/authority semantics before code |
|  | P2.2 | implementation/high | manual | full | shared task compiler/enforcement seam, correctness-critical |
|  | P2.3 | implementation/high | manual | full | audit/review transition enforcement, correctness-critical |
|  | P2.4 | implementation/high | manual | full | route evidence and fail-closed compliance |
|  | P2.5 | implementation/medium | plan-exec | full | deterministic end-to-end bank after P2 implementation |
|  | P3.1 | implementation/high | manual | full | versioned cross-provider trace schema and adapters |
|  | P3.2 | implementation/high | manual | full | metric arithmetic/provenance against frozen trace |
|  | P3.3 | implementation/high | manual | full | system behavioral eval release gate |
|  | P3.4 | implementation/high | manual | full | disposable-worktree canary, rollback and real mutations |
|  | P3.5 | frontier/xhigh | manual | full | fresh terminal adversarial verdict; no self-certification |
|  | P4.1 | frontier/high | manual | full | falsify architecture hypotheses; any accepted refactor becomes a new plan |
|  | P4.2 | implementation/medium | plan-exec | light | bounded read-only doctor over frozen P1/P3 contracts |
|  | P4.3 | frontier/high | manual | full | final measured-scope synthesis and real Owner rollout/release gate |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Evidence, contracts и acceptance-before-mutation | 3/4 | 🟡 In progress |
| P1 | Единственный semantic source и runtime uniqueness | 1/5 | 🟡 In progress |
| P2 | Checked outcome execution и bounded review | 0/5 | ⬜ Not started |
| P3 | Unified traces, evals и isolated self-host canary | 0/5 | ⬜ Not started |
| P4 | Hypothesis verdict, operator doctor и Owner packet | 0/3 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-24 | `control-plane enforcement failure` — falsifiable working hypothesis, не установленная root cause. | RAG:— (repo-grounded: `findings/07-design-audit-red-attempt-1.md`, `research/01-root-cause-analysis.md`). |
| D2 | 2026-07-24 | Existing product/bookkeeping, two-audit cap и same-session rules считаются declarative inputs; план не дублирует их как новое решение. | RAG:— (repo-grounded: `packages/task/commands/plan-audit.md:45`, `packages/skiller/skills/general/plan-protocol/SKILL.md:759`). |
| D3 | 2026-07-24 | P0.1 обязан различить carrier availability, selection, check execution и failing transition для каждого critical case. | RAG:— (plan-grounded: falsification requirement D1). |
| D4 | 2026-07-24 | Perplexity-аудит hash-pinned и используется только как claim inventory; speculative refactor не входит в critical path. | RAG:— (repo-grounded: `findings/00-source-evidence-manifest.md`, `findings/01-perplexity-audit-assessment.md`). |
| D5 | 2026-07-24 | Task Contract v1 содержит Goal, Must/Never, Done/Public Acceptance, Authority, Next, Route, Evidence, Portability, Conflicts и Version/Supersedes. | RAG:✅ 2026-07-24 OpenAI Codex best-practice check (`findings/05-external-practices.md`); extended by D26. |
| D6 | 2026-07-24 | Один semantic workflow имеет один canonical owner и одну effective runtime identity. | RAG:— (repo-grounded: `findings/03-ssot-runtime-inventory.md`). |
| D7 | 2026-07-24 | Provider projection публикуется только при complete references, capability coverage и immutable `(name,version)→tree hash`; иначе fail-closed. | RAG:— (repo-grounded: P1 observed incomplete same-version cache and invalid carriers). |
| D8 | 2026-07-24 | P2 implements enforcement at transitions/pre-mutation/pre-final/public acceptance through one compiler/state seam; prose-only repetition запрещено. | RAG:— (repo-grounded: D2 controls existed while field outcomes diverged). |
| D9 | 2026-07-24 | Product/evidence/process findings и stable `finding_id/reopen_of` — machine fields; third same-finding event enters INCIDENT. | RAG:— (plan-grounded: bounded remediation requirement and existing two-audit cap). |
| D10 | 2026-07-24 | Regression bank starts from 20–50 real failure/control cases and grades transcript actions plus public outcome. | RAG:✅ 2026-07-24 Anthropic agent eval method (`findings/05-external-practices.md`). |
| D11 | 2026-07-24 | Unified trace links session/task/run/requirement/route/finding/outcome and carries completeness flags; no external telemetry dependency. | RAG:✅ 2026-07-24 OTel GenAI vocabulary (`findings/05-external-practices.md`). |
| D12 | 2026-07-24 | Neutral Routing is SSOT; native Codex selectors live only in ready roadmap launch blocks. | RAG:— (repo-grounded: canonical plan-protocol §9 and root AGENTS launch requirement). |
| D13 | 2026-07-24 | P0–P3 writes stay inside self-host/disposable fixtures; consumers, fleet and FOREMAN remain read-only. | RAG:— (repo-grounded: root `AGENTS.md`). |
| D14 | 2026-07-24 | P4 structural audit can end accept/reject/unknown, but accepted refactor is a separate future plan, not dynamic Files in this plan. | RAG:— (plan-grounded: executable Files/DoR requirement). |
| D15 | 2026-07-24 | Exact performance floors and grader/corpus hashes freeze in P0.3 before any behavior mutation; later change requires Owner D#. | RAG:✅ 2026-07-24 static paired eval practice (`findings/05-external-practices.md`). |
| D16 | 2026-07-24 | P0.4 is first behavior mutation and is blocked on P0.3 Owner Approval. | RAG:— (plan-grounded: evidence-before-mutation safety boundary). |
| D17 | 2026-07-24 | Phase ordering is strictly P0→P1→P2→P3→P4; no cross-phase parallel execution. | RAG:— (plan-grounded: explicit producer/consumer contracts in phase contexts). |
| D18 | 2026-07-24 | Design accounting is corrected to Pass 2/3; each pass is a fresh session and next step is Pass 3, not P0 execution. | RAG:— (repo-grounded: plan-protocol design budget; supersedes withdrawn draft pass-count claim). |
| D19 | 2026-07-24 | Roadmap stores a ready native Codex `NEW SESSION` carrier for every solo/batch group; predecessor close may refresh hash/input refs but may not omit the group carrier. | RAG:— (repo-grounded: plan-protocol roadmap requirement; supersedes withdrawn draft D19). |
| D20 | 2026-07-24 | Raw sessions are consumed only through a selected exact path/hash manifest generated once by the P0.1 stdlib extractor; repeat runs read that manifest. | RAG:— (plan-grounded: cold-start reproducibility requirement). |
| D21 | 2026-07-24 | P3.4 runs in one disposable detached git worktree; every canary case is committed, inspected, returned to candidate by clean detach, and cleanup refuses dirty state. | RAG:— (repo-grounded: user-change preservation and canary rollback boundary). |
| D22 | 2026-07-24 | Root supervisory session persists and dispatches each executable item to a fresh subagent grounded from committed plan/handoff; roadmap records canonical `Plan context=same-session — item` and native recovery `Context=NEW SESSION` separately. Every item carrier requires `command.subagents`; preflight verifies the Codex mapping is `native` and live `multi_agent` is enabled, otherwise fails closed. | RAG:— (repo-grounded: root `AGENTS.md`; `packages/task/configs/command-routing.json` Codex capability binding; `codex doctor --json` at Pass 3 reports `multi_agent` enabled). |
| D23 | 2026-07-24 | Shared-package/public-contract items consume `package-contribution-protocol`: reuse-survey and Rule of Three first; a new public seam requires pinned consumers, ≥2 alternatives, proposal/ADR decision and explicit SemVer. Unfrozen scope escalates rather than expanding inline. | RAG:— (repo-grounded: `packages/skiller/skills/architect/package-contribution-protocol/SKILL.md`; applies to P0.4, P1.1–P1.3, P2.1–P2.4, P3.1–P3.3 and P4.2). |
| D24 | 2026-07-24 | Provider-portable SSOT is the committed plan/canonical repo sources plus semantic `task:*` carrier. `plans/<ID>/root/` is relative, not OS `/root`; `.agents` and native blocks are projections. P0.1 raw evidence is intentionally host-bound and non-portable until exact manifests/corpus/baseline are committed; absence/hash drift fails closed. | RAG:— (repo-grounded: plan-protocol §3; `packages/task/configs/command-routing.json`; commit `454ea86d` migrated one archived plan's absent `root/` checklist and did not change the active-plan canon). |
| D25 | 2026-07-24 | Owner decision: execution evidence is fully self-contained before audit. `artifacts/source-evidence/` carries full audit snapshot, seven lossless journals, sanitized selected session incidents, manifests, precomputed corpus/baseline and deterministic verifier. External origins are optional provenance only; P0.1 verifies/normalizes the committed bundle. Supersedes D20 and D24 only where they allowed host-bound execution inputs. | RAG:— (owner refinement captured in `brief/01-refinements.md`; repo-grounded portability contract and privacy boundary). |
| D26 | 2026-07-24 | Self-contained planning becomes a compiled package capability, not plan-local prose. Canon defines tiers: simple low-risk/single-session plans may use committed brief+acceptance; multi-session, high-risk, handoff and audit plans require committed execution inputs or exact predecessor-produced paths. Host/chat/mAInd/`tmp`/foreign references are provenance/advisory only; evidence bundles are minimized, exclude secrets/chain-of-thought/raw bulk, carry deterministic manifest/verifier, and use one provider-neutral semantic carrier with provider renderers. P2.2 enforces this in Task Contract/plan-design/plan-lint; P2.5/P3.3 prove it; P4.3 documents it. | RAG:— (explicit Owner refinement; local D25 bundle is the first acceptance fixture, not the only implementation). |
| D27 | 2026-07-24 | Every canonical/package publication change is version-first and generator-closed: one owner item bumps its exact package/plugin/publication-unit version, regenerates the full declared tree/locks/marketplaces, proves a read-only second check, and passes an exact diff-scope guard. `packages/skiller/configs/publication-versions.json` separates package API SemVer from finite unit versions so unaffected bucket manifests remain byte-identical. Reusing `(name,version)` for different tree bytes is forbidden. P1.1 freezes candidate versions; P1.2/P1.3/P2.2/P2.3 publish them; P4.3 is read-only and reopens the owner on drift. | RAG:— (repo-grounded: `skiller validate` includes `registry --check`; registry currently derives all bucket versions from one package version; generated Codex/task locks encode version/tree). |
| D28 | 2026-07-24 | Resolve all 12 native Codex collisions by ownership, not suppression: installed generated `core` and `task` bundles are authoritative; delete the six exact root core and six exact root task auto-discovered adapter directories only after repository-marketplace/generated-bundle proof. Remaining root adapters are unique bootstrap-only carriers. P1.4 cold-installs from explicit fixture roots and requires each of the 12 semantic IDs exactly once. | RAG:— (repo-grounded: committed effective inventory and read-only `codex plugin list --json` confirm enabled `core@0.4.0` and `task@0.3.0`; root adapters duplicate their semantic IDs). |
| D29 | 2026-07-25 | Owner chose capped option B: preserve the two historical RED verdicts and exhausted design cap `2/2`, authorize exactly one redesigned executable contract (Pass 4/4) and exactly one later fresh independent exceptional design audit (`0/1` before launch). This authority does not include P0.1. Literal GREEN is necessary but routes only to separate Owner gate `G-EXEC`; any verdict ends the audit session, and non-GREEN grants no implicit repair/audit authority. | RAG:— (owner-grounded: `brief/01-refinements.md`, Owner override B). |
| D30 | 2026-07-25 | F1 repair: immutable `artifacts/source-evidence/verify_source_bundle.py` owns only its actual byte/schema/pinned-constant checks and remains unchanged. P0.1 owns `root/contracts/source-evidence-verification-v1.md`, a machine contract, semantic verifier, focused tests and report outside the bundle. Recomputed/cross-checked facts are distinct from `pinned-not-recomputable`/`unknown`; excluded raw-session dedup and an uncommitted lifecycle classifier can never be reported as semantically verified. | RAG:— (repo-grounded: `findings/08-design-audit-red-attempt-2.md` F1 and `artifacts/source-evidence/verify_source_bundle.py:26-111`). |
| D31 | 2026-07-25 | F2 repair, supersedes D27/D28 only for the 13 remaining root bootstrap identities: canonical bilingual sources are exact `packages/skiller/skills/repository-bootstrap/<name>/{SKILL.ru.md,SKILL.md}` records in a private/source-only bucket. `build_registry` indexes them, but publication catalog excludes the bucket from normal Claude/Codex bucket, core and marketplace units; consumer vendor/connect selection also rejects these source-only records. `registry.py` invokes the sole `publication.py` root-bootstrap renderer from `configs/repository-bootstrap-skills.json`; it emits only thin `.claude/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md` projections plus one version/tree lock. `skillset.py` may enforce consumer exclusion but is never this self-host producer. | RAG:— (repo-grounded: `findings/08-design-audit-red-attempt-2.md` F2; current `registry.py:18-24,398-430`; `publication.py:131-177,293-367`; `skillset.py:60-101,223-287,767-853`). |
| D32 | 2026-07-25 | Owner authority C (директива владельца 2026-07-25, `brief/02-claude-takeover.md`): план сохраняется (не kill); bounded repair = ровно три находки attempt 3 (F1 `ITEM_BASE_SHA`, F2 same-item Required Reads, F3 bootstrap-map validation) + смена acting provider на Claude; разрешён ровно один новый independent design audit (`0/1`) после repair; `G-EXEC`/G0/G1 не затронуты, P0.1 этой authority не разрешён. | RAG:— (owner-grounded: `brief/02-claude-takeover.md`; supersedes D29 в части исчерпанного exceptional slot). |
| D33 | 2026-07-25 | Acting provider — Claude Code: frontier→Opus 5, implementation→Sonnet (renderer-таблица roadmap — SSOT mapping); root supervisory session = Claude main loop, `command.subagents` = native (Agent tool), Codex `multi_agent` preflight D22 заменён Claude-эквивалентом (Agent tool доступен = native); native Codex blocks в roadmap понижены до historical projections. Supersedes D19 (native-Codex-carrier mandate) и провайдер-привязку D22. | RAG:— (repo-grounded: roadmap.md renderer-таблица уже содержит Claude-колонку; `packages/task/configs/command-routing.json`). |
| D34 | 2026-07-25 | F1 fix канон: item baseline = `artifacts/<Pn.m>/base-sha.txt`, записываемый `git rev-parse HEAD` ПЕРВЫМ действием item'а до любой мутации, коммитится с item; Validation читает `ITEM_BASE_SHA` только из этого файла. F3 fix: `build_effective_inventory.py --check-bootstrap-map` — детерминированный read-only acceptance-гейт P1.1. | RAG:— (plan-grounded: `findings/09-design-audit-exceptional-attempt-3.md` F1/F3). |
| D35 | 2026-07-25 | Latest Owner option B после authority-C A1 RED на pre-redesign `fe3e1646`: разрешены ровно этот bounded Pass 5 по `findings/09` F1–F3 и один последующий fresh independent audit A2 (`0/1`). Supersedes D32 audit authority и D33 acting-provider assignment, не меняя их исторический факт. A2 GREEN останавливается на `G-EXEC`; non-GREEN возвращается Owner. | RAG:— (owner-grounded: latest appended block in `brief/01-refinements.md`; historical authority-C carrier and concurrent pre-redesign A1 verdict preserved separately). |
| D36 | 2026-07-25 | Supersedes D34 baseline semantics. P1.1 produces and freezes the only baseline helper/contract. For P1.2/P1.3/P2.2/P2.3 the item-owned `artifacts/<item>/base-sha.txt` is created after Required Reads but before any other item-owned write from exact current `HEAD`; on resume it is validated and reused byte-for-byte, never recomputed. Missing carrier with dirty owner paths, malformed/non-commit/non-ancestor SHA, owner mismatch or overwrite attempt fails closed. The validated file is the sole producer of `ITEM_BASE_SHA`; generated-scope assertions remain unchanged in strength. | RAG:— (repo-grounded: `findings/09-design-audit-exceptional-attempt-3.md` F1; cold-start/item order from plan-protocol). |
| D37 | 2026-07-25 | P2.3 `review_policy.py`/`test_review_policy.py` and P3.4 `canary-cases.json` are same-item Files/Deliverables only, never Required Reads. Their predecessor inputs and authoring rules are complete before mutation. | RAG:— (repo-grounded: `findings/09-design-audit-exceptional-attempt-3.md` F2). |
| D38 | 2026-07-25 | P1.1 bootstrap map acceptance is exact set equality, not key-presence: schema v1, exactly the frozen 13 sorted identities, exact per-record shape, both pinned seed path/hash records, canonical bilingual target formulas, two unique provider projections per identity and exact 26-target set, version/unit/generator/lock literals, plus explicit resolution for differing seeds. Focused mutation tests gate every dimension before P1.2. | RAG:— (repo-grounded: `findings/09-design-audit-exceptional-attempt-3.md` F3). |
| D39 | 2026-07-25 | Owner authority D: формула «нельзя запускать такой план» = грант на проработку, НЕ на исполнение. Разрешён ровно один bounded repair десяти находок A1 (`findings/10`, F1–F10) в режиме реопена P1 — без нового design pass (`Design Passes` не растёт), без исполнения P0.1, без расхода audit-слота этим ремонтом (слот A2 израсходован независимо — параллельная A2-сессия, D49). Guard-строка «НЕ раньше: Owner grant» в launch-block'е `findings/10` снята этой authority. Следующий гейт (новый independent audit ИЛИ `G-EXEC` под названный долг F11 + остаточные debts) выбирает владелец; заход его не выбирает. Нумерация: директива называла запись «D35» по состоянию pre-redesign `fe3e1646`, где D34 была последней; фактическая — D39, смысл не изменён. Реопен-ритуал §3 выполнен так: (2) version bump 1.8.0→1.9.0, (3) эта запись, (4) `Phase Handoff` P1 не инвалидируется маркером «УСТАРЕЛ» — фаза никогда не была терминальной (её блок дословно «Фаза P1 не закрыта»), маркер применим только к закрытому блоку; (1) статус фазы НЕ переведён в 🟡 сознательно: все 22 items `⬜`, исполнение запрещено до `G-EXEC`, а 🟡 у фазы 0/5 сообщил бы холодному исполнителю «работа идёт» — приоритет отдан безопасности сигнала, отклонение названо здесь, а не скрыто. | RAG:— (owner-grounded: `brief/01-refinements.md` § «Owner authority D», 2026-07-25). |
| D40 | 2026-07-25 | F1 repair, supersedes D28 в части замороженного числа: exact collision scope больше не литерал «12». Измерено (23 enabled `@swissknifeman` units, cwd репо, 2026-07-25): **16 root↔installed** (6 core + 6 task + **4 `architect`**: `architecture`, `codebase-design`, `domain-modeling`, `package-contribution-protocol`) и **1 installed↔installed** (`query-craft` core↔research); уникальных root-carriers **14**, не 13 (14-й — `workflow-craft`). Плановый инвариант — ownership, а не число: authoritative носитель = enabled installed unit; root-projection существует только пока identity не обслуживается enabled unit; после ремедиации root-набор провайдера равен ровно declared target set. Owner-путь остатка (4 + `workflow-craft` + core↔donor детектор) — новый item P1.5 (D41). | RAG:— (repo-grounded: `findings/12-effective-collision-remeasure.md`; `findings/10` F1; `.agents/plugins/marketplace.json`; `packages/skiller/adapters/codex/core/skills/**`). |
| D41 | 2026-07-25 | Newly measured остаток получает собственный item **P1.5**, исполняемый ПОСЛЕ P1.3 и ПЕРЕД терминальным гейтом P1.4 (порядок объявлен в Routing, Phase Status, Title item'а и Карте roadmap; P1.4 Inputs требуют green P1.5 → ранний запуск fail-closed). Альтернатива «дописать 4 удаления в Files P1.2/P1.3» отклонена: Owner boundary authority D запрещает править ТЗ/Scope/Files/Validation items вне названного скоупа. Альтернатива «сделать P1.5 терминальным после P1.4» отклонена: тогда потребляемый downstream `findings/P1.4-effective-runtime-proof.md` фиксировал бы catalog-wide uniqueness при живых 4 коллизиях. Номер P1.4 сохранён, потому что его артефакт запинен в Required Reads P2.1/P2.5/P3.4. | RAG:— (plan-grounded: Owner authority D boundary; repo-grounded: `phases/P2.md:37,113`, `phases/P3.md:92` пинят `findings/P1.4-effective-runtime-proof.md`). |
| D42 | 2026-07-25 | `query-craft` installed↔installed решается инвариантом взаимного исключения, а не публикационной хирургией: курируемый unit `core` физически копирует identities донорских бакетов (`general`, `research`, `oss-dev`), поэтому одновременное включение `core` и донора создаёт дубль. План НЕ меняет user-owned enabled-множество и НЕ переписывает публикацию бакетов (обе альтернативы — «`core` публикует по ссылкам» и «донорский бакет исключает CORE identities» — записаны как отклонённые: первая невозможна в формате Codex-плагина, вторая перепубликовала бы ≥3 бакета вне скоупа). P1.5 реализует детектор+диагностику (owner, enabled-пара, безопасное действие), инвариант живёт в Identity/Ownership v1, живая правка профиля — Owner-действие. | RAG:— (repo-grounded: `packages/skiller/adapters/codex/core/skills/research/query-craft/` vs `packages/skiller/skills/research/query-craft/`; CLAUDE.md «курируемый core — лёгкая замена бакетам general+oss-dev»; `findings/12`). |
| D43 | 2026-07-25 | Root-bootstrap получает второй класс записей (extends D31/D38, не отменяя их): класс A — 13 private-source identities (P1.2, `repository-bootstrap@0.1.0`, exact 26 projections, acceptance D38 без изменений); класс B — identity с каноном в публичном бакете, чей unit не включён, сейчас ровно `workflow-craft` (P1.5, `repository-bootstrap@0.2.0`, +1 projection). Класс B у `workflow-craft` — Codex-only и осознанно асимметричен: Claude root его сегодня не несёт, а добавление Claude-проекции меняет first-turn budget и требует `skiller budget --first-turn` (CLAUDE.md), что вне этого ремонта. Асимметрия обязана быть объявлена в записи и проверена parity-тестом как declared, а не случайная. Удаление `.agents/skills/workflow-craft` отклонено: единственный легальный путь восстановления (включить `general`) запрещён инвариантом D42. | RAG:— (repo-grounded: `packages/skiller/skills/general/workflow-craft/SKILL.md`; `findings/12` § уникальные carriers; CLAUDE.md правило first-turn budget). |
| D44 | 2026-07-25 | F1 второй слой: детекция коллизий больше не диффается против прозаического immutable before-state. Authoritative вход гейта — repo-derived worst-case множество (каждая publishable unit — потенциальный носитель; fail-closed, считается холодно, без профиля/кэша). Машинно-сравнимый observed before-state — P1.1-owned `artifacts/P1.1/effective-runtime-before-state.json` (identity-записи), созданный ОДНИМ named read-only capture-режимом с провенансом команды/времени и sanitized путями; он корроборирует, но никогда не требуется для вердикта и не может погасить коллизию. Immutable `artifacts/source-evidence/runtime/effective-runtime-inventory.json` остаётся provenance: его прозаические счётчики сверяются где парсимы, иначе `pinned-not-recomputable`. | RAG:— (repo-grounded: `findings/10` F1 второй слой; `findings/12` § второй слой; immutable bundle неизменяем по D30). |
| D45 | 2026-07-25 | F2 repair: производитель `PRE_PLAN_SHA` — **P0.1**, файл `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/pre-plan-sha.txt` (`git rev-parse HEAD` первым действием item'а, до любой другой owned-записи; идемпотентно на resume — валидация 40-hex/commit/ancestor и побайтное переиспользование без перезаписи). P3.4 читает только этот путь, валидирует ancestor-of-`CANDIDATE_SHA` ДО создания worktree и передаёт значение как `--pre-plan-sha`; отсутствие/невалидность — fail closed без изобретения ref. Rollback-репетиция сохранена (альтернатива «снять репетицию» отклонена: `P3.5 Pending Work` называет rehearsed pre-plan path единственным ROLLBACK-путём фазы). | RAG:— (repo-grounded: `findings/10` F2; `artifacts/source-evidence/precomputed/baseline.json` не содержит sha-ключей; `phases/P3.md:117`). |
| D46 | 2026-07-25 | F4 repair: canary-инвокация рендерится из §3 Routing через checked mapping, а не из провайдер-привычки. Claude-форма обязана нести `--effort <low\|medium\|high\|xhigh>` рядом с `--model`/`--permission-mode`; Codex-форма — `-m` + `model_reasoning_effort`. Провайдер, у которого routed effort нельзя запинить флагом, даёт `actual effort = unknown` → fail-closed dispatch, а не прогон на session default. | RAG:✅ 2026-07-25 локальная проверка CLI: `claude --version` → 2.1.220, `claude --help` содержит `--effort <level>` (и `--model`, `--permission-mode`). |
| D47 | 2026-07-25 | F5+F7 repair: P2.2 обязан прогнать `plan-lint plans/2026.07.24-AGENT-RELIABILITY` в собственной Validation и удовлетворить план собственным новым tier-правилам ДО закрытия. Правило tier'а обязано отличать provenance-упоминание от execution input: `tmp/`-ссылки в `brief/00-brief.md:42-43` — provenance и обязаны проходить, что закрепляется fixture'ой на этом самом плане. Если план не удовлетворяет новому правилу, владелец правки — тот же P2.2 (правит план ИЛИ правило с D#), а не следующий item. Cross-plan: `plan-protocol@2.12.0`, `skiller@0.5.0`, `task@0.4.0` объявлены Exported с потребителем-планом `2026.07.25-ECO-OPT` (его P2.2/P7.1 ждут терминальную P2); зеркальная `Consumed`-строка на стороне ECO-OPT — Owner-facing долг. Параллельные чужие коммиты обрабатывает foreign-commit атрибуция diff-scope guard (§2). | RAG:— (repo-grounded: `findings/10` F5/F7; `plans/2026.07.25-ECO-OPT/plan.md` §2 coupling + D10; `phases/P2.md:55-59`). |
| D48 | 2026-07-25 | F9+F10 repair: P2.5 Scope больше не говорит «isolated provider homes» — только task-specific temporary roots с явным запретом `HOME`/`CODEX_HOME` (единая формулировка с P1.4/P3.4). Мысль владельца из `brief/02-claude-takeover.md` про инструкционный слой (монолитный контекст деградирует Codex → слоёная структура/спецнастройка провайдера) НЕ покрывается этим планом и делегирована плану `2026.07.25-ECO-OPT` (его D9 + P7.2 «Codex-профиль, тонкий AGENTS.md слой»); в этом плане она закрыта как delegated, а не потерянная. Само RAG-утверждение brief/02 в этом плане несущим не является и остаётся `[UNVERIFIED]` здесь: файла слоя 1 под него нет, верификация — обязанность приёмника. | RAG:— (owner-grounded: `brief/01-refinements.md` (запрет HOME-изоляции), `brief/02-claude-takeover.md:7-12`; repo-grounded: `plans/2026.07.25-ECO-OPT/plan.md` D9/P7). |
| D49 | 2026-07-25 | Исторический факт, зафиксированный этим заходом без переписывания: слот A2 под option B израсходован ПАРАЛЛЕЛЬНОЙ сессией на committed `916acdb5` (до ремонта A1) и вернул literal **RED** — `findings/11-design-audit-owner-b-a2.md`. Его находки (Blocker: порядок capture `base-sha` по D36 конфликтует с каноническим порядком `plan-exec`/`plan-run`, где status/journal-записи идут до Implementation Rules; Blocker: заявленная автономная multi-session цепочка не имеет workflow-carrier, требуемого plan-protocol при длинной автономной цепочке; Major: `research/01–03` без прямых ссылок на слой 1 и без маркера из enum §7) **вне скоупа authority D** и здесь НЕ ремонтированы: authority D назвала ровно F1–F10 из `findings/10`. Они переходят владельцу как названный долг. Следствие для этого ремонта, названное явно: новый item P1.5 повторяет тот же шаг (0) `baseline --capture-or-verify`, что и P1.2/P1.3/P2.2/P2.3, поэтому он унаследует любой ремонт D36-порядка — расходиться с общим паттерном внутри bounded repair было бы хуже (два противоречивых порядка в одной фазе). Свободных audit-слотов после D49 нет. | RAG:— (repo-grounded: `findings/11-design-audit-owner-b-a2.md`; `journal.jsonl` строка `audit-red` от 2026-07-25T06:18:29Z; `packages/task/commands/plan-exec.md:16-23,53-63`). |
| D50 | 2026-07-25 | **Owner authority E, supersedes audit-экономику D29/D32/D35/D39 (исторические факты сохраняются).** Владелец: «пакет полностью разрабатывается ИИ для ИИ, моё участие минимальное; если бо́льшую часть сам можешь разрулить — разруливай». Это стоячая делегация: проектные развилки, скоуп ремонта и приёмочные пороги агент закрывает записью, а не вопросом. Следствия: (1) персональные слоты A0–A3 — история, не механизм; действует канон plan-protocol «два аудита на фазу, третий → решение»; шесть RED-вердиктов остаются literal RED; (2) `G-EXEC` считается выданным для self-host P0–P3 — отдельного человеческого гейта перед P0.1 нет; (3) G0 агент принимает сам с D-записью; (4) за владельцем ровно G1 (tag/push/release, fleet, consumer-репо, FOREMAN) — граница «необратимо/видно снаружи». Обоснование снятия рационирования: шесть design-аудитов и пять design pass при НУЛЕ исполненных items — воспроизведение на самом плане того failure mode (audit/fix-loop без продукта), который план создан лечить. Принятый риск назван явно: ремонт A3 уходит в исполнение без независимого седьмого design-аудита; первая независимая проверка — канонический аудит фазы P0. | RAG:— (owner-grounded: `brief/01-refinements.md` § «Owner authority E»; repo-grounded: `journal.jsonl` — 6 строк `plan-audit`, `plan.md` §4 Status Board 0/22). |
| D51 | 2026-07-25 | **F1 A3 repair.** Item, доказывающий свойство множества, обязан объявить множество declared literal'ом. Позитивная фикстура P1.4 = все publishable units репозиторного marketplace провайдера МИНУС ровно три донорских бакета (`general`, `research`, `oss-dev`) — D42-конформная сторона с курируемым `core`; материализуется как `artifacts/P1.4/fixture-unit-set.json` с машинной сверкой состава. Девять пар `core`↔донор (`anti-drift`, `compact-responses`, `context-economy`, `mcp-advisor`, `plan-protocol`, `session-handoff`, `verify-claims`, `gh-review`, `query-craft`) и `workflow-craft`↔`unit:general` — **диагностика D42, а не гейт**: они существуют по построению курируемого `core`, план их не чинит, поэтому доказываются ОТДЕЛЬНЫМ негативным прогоном (9 записей с непустым `safe_owner_action` + precondition-ошибка class B). Альтернативы отклонены: «все units» — гейт падает по построению без owning item'а; `{core, task, architect}` — необъявленное сужение до трёх units, ~198 identity остаются непроверенными; «все минус `core`» — теряет 6 core identity и ломает precondition class B. Карта identity строится из сгенерированного publication catalog/lock, не рекурсивным обходом `source` (глубина вложения различается по формату unit'а). | RAG:— (repo-grounded: `findings/13-design-audit-a3.md` F1; `findings/12-effective-collision-remeasure.md`; синтез и собственный перезамер — `research/04-p1.4-fixture-composition.md`). |
| D52 | 2026-07-25 | **F2+F3 A3 repair.** Downstream-литералы сведены к состоянию после P1.5: `phases/P2.md` P2.2 и `phases/P4.md` P4.3 читают `repository-bootstrap@0.2.0` и **27** root-проекций (26 class-A + class-B `workflow-craft`) вместо `0.1.0`/26; упоминания `0.1.0`/26 остаются только там, где описывают состояние ДО P1.5 (P1.1 ledger, P1.2 ТЗ, P1.5 Inputs). Deliverables P1.4 несёт **30** exactly-once IDs и обязан выводить число формулой `13 class-A + 1 class-B + 6 core + 6 task + 4 architect`, а тест — падать при расхождении формулы с фактическим каталогом. Правило на будущее: добавление item'а внутри bounded repair тянет свип литералов версии/числа целей по ВСЕМ фазам, а не только по фазе реопена (кандидат в `plan-lint`, зафиксирован как PROMOTE-CANDIDATE отчёта A3). | RAG:— (repo-grounded: `findings/13-design-audit-a3.md` F2/F3; свип `grep repository-bootstrap` по `phases/**`, `roadmap.md`). |
| D53 | 2026-07-25 | **F5 A3, решено агентом по D50 (владельцу не выносится).** Метрика §8 «Effective semantic identity collisions» получает квалификатор **«0 в объявленной фикстуре P1.4 (D51)»**; живой хост, где `core` и `research` включены одновременно, даёт не floor, а строку диагностики D42 с названным безопасным Owner-действием. Альтернатива «выдать Owner-гейт на правку enabled-множества» отклонена: правка user-owned профиля — живая мутация вне границ плана (D42, §2), а authority E оставляет владельцу только необратимое/наружное. Так floor остаётся достижимым и не превращается ни в RED по неремонтируемой метрике, ни в тихое переопределение на шаге измерения (риск «Self-host GREEN is called fleet GREEN» внутри self-host). | RAG:— (repo-grounded: `findings/13-design-audit-a3.md` F5; `plan.md` D42; `phases/P1.md` P1.5 Pending Work). |
| D54 | 2026-07-25 | **Провенанс dual-provider.** Строка §7 Consumed «provider publication/artifact contract | 2026.07.19-DUAL-PROVIDER» переклассифицирована в **low-trust / verify-before-use**: план-донор написан Codex, терминален со статусом 🟠 (не 🟢), его historical P7.4 остаётся literal `ATTENTION`, и именно он одним коммитом `e8f5b477` внёс все 30 рукописных root-адаптеров мимо генератора, без provenance/hash — источник 16 коллизий `findings/12`. Поэтому P1.2/P1.3/P1.5 обязаны доказывать поведение затронутых seam'ов характеризационным тестом на месте, а не наследовать «зелёное» от 🟠-плана. Это НЕ приказ переписывать DUAL-PROVIDER (терминален, не исполняется) — это снятие презумпции корректности с его артефактов. | RAG:— (owner-grounded: `brief/01-refinements.md` § «Owner authority E» п.2; repo-grounded: `plans/2026.07.19-DUAL-PROVIDER/plan.md` Meta/статус, коммиты `302a5f0a`, `04be7d9e`, `e8f5b477`). |
| D55 | 2026-07-25 | **F4 A3 repair.** Bounded repair и design pass считаются завершёнными только после bookkeeping-коммита своих плановых путей: рабочее дерево планом для холодного исполнителя не является. Ремонт v1.9.0 вместе с `findings/10`–`findings/13` и ремонт A3 (v1.10.0) закоммичены одним bookkeeping-коммитом плановых путей; `handoff.md` несёт его хеш отдельным стамп-коммитом (хеш собственного коммита в него не вписать физически — это единственная причина второго коммита, и он трогает ровно один файл). Правило-кандидат в `plan-protocol` §8: handoff, предписывающий следующему шагу «committed tree», обязан нести хеш этого дерева; плейсхолдер = ERROR линтера. | RAG:— (repo-grounded: `findings/13-design-audit-a3.md` F4; `git status --porcelain plans/2026.07.24-AGENT-RELIABILITY` до ремонта — 10 `M` + 4 `??`). |
| D56 | 2026-07-25 | **Программный гейт: design-first по всей экосистеме (директива владельца 2026-07-25).** Исполнение ЭТОГО плана не начинается сразу после `G-EXEC`: сначала этап A (полная проектировка и актуализация всех живых планов), затем этап B (сверка точной последовательности по фактическим `Files` и допиливание межплановых конфликтов), затем этап C (финальный программный аудит под Fable), и только затем этап D (исполнение). `G-EXEC` (D50) не отзывается — над ним появился программный гейт более высокого уровня. Основание — измерение, а не осторожность: карта владения поверхностями была выведена из заголовков фаз и строк Routing, а `plans/cross-plan-files.py` на фактических `Files` сразу нашёл живое пересечение (`packages/harness/configs/claude-code/hooks/run-report/_lib.py` — P0.4 этого плана против ECO-OPT P1.2) при слепой зоне в 15 недетализированных items ECO-OPT. Принятый риск назван: программа откладывает первый исполненный item ещё на несколько заходов — это ровно тот failure mode, который план лечит; смягчение — этап A конечен (6 фаз ECO-OPT), состоит из проектирования нового, а не из повторного аудита уже спроектированного, и его выход машинно проверяем. ACTIVE передан ECO-OPT, `Paused By` проставлен. | RAG:— (owner-grounded: директива 2026-07-25 «сначала полная проектировка и актуализация всех планов, потом сверка в точную последовательность, финальный аудит из-под Fable»; repo-grounded: прогон `plans/cross-plan-files.py` 2026-07-25). |

| D57 | 2026-07-25 | **Четыре принципа владельца (нет неприкасаемого кода · выверено и обосновано · никто никому не мешает · легко расширять и изменять) приняты как ОБЩИЕ для трёх живых планов и переведены в 12 проверяемых инвариантов; носитель — `plans/README.md` § «Принципы кросс-плановой работы», этот план на него ССЫЛАЕТСЯ из §2 и текст не копирует.** Основание формы: копия принципа в трёх планах немедленно разошлась бы с оригиналом (рамка репо «единый источник истины > копий»), а интенция без перевода в инвариант аудитом не проверяется. Ключевое разграничение, зафиксированное владельцем в том же диалоге: принцип «нет неприкасаемого кода» читается как **«граница обоснована, названа и ПРОХОДИМА»**, а НЕ как «снять заморозки как класс» — второй вариант владелец отклонил, потому что он развернул бы закрытые решения трёх планов (у нас — D42/D43/D44 про аддитивность и замороженный инструкционный каталог) и сломал back-compat флота из 17 проектов. Практическое следствие для этого плана: каждая формулировка запрета в ТЗ обязана нести владельца, причину и проход (эскалация → D#), а «чужая поверхность» — называть план И item, а не только пакет. **Consequences:** (1) принципы НЕ отменяют ни одной закрытой D-записи сами по себе — они меняют то, что ПРОВЕРЯЕТ аудит, и инвариант, столкнувшийся с закрытым решением, идёт находкой владельцу, а не тихой правкой; (2) появляется внешняя зависимость плана от файла вне его каталога (`plans/README.md`) — при его переезде ссылка рвётся, поэтому ссылка идёт с именем секции, а не с номером строки; (3) этап C программы становится аудитом ПО ИНВАРИАНТАМ: каждая находка обязана называть номер И#, что делает отчёт сверяемым, но и повышает планку к самому аудиту; (4) `plan-audit design` по отдельным планам этапом C поглощается — гонять его до принципов значит проверять план против устаревшего критерия. | RAG:— (owner-grounded: решение 2026-07-25 и выбор чтения принципа «граница проходима, а не заморозок нет»; repo-grounded: `plans/README.md` § «Принципы кросс-плановой работы» И1–И12, § «Программа: этапы A–D»; `plans/2026.07.25-ECO-OPT/plan.md` §5 D42/D43/D44 — прецеденты отклонения ради аддитивности). |

| D58 | 2026-07-25 | **Payload A (аудит этапа C, Ф1/Ф3/Ф8): G1-формулировка о FOREMAN сужена до наружных частей; долг D47 «зеркальная Consumed-строка ECO» снят.** (1) G1 покрывает ровно наружные, необратимые части `2026.07.18-FOREMAN` — fleet-раскатку и массовость пилота; внутриплановый bookkeeping и дизайн-заходы (включая FM P1.5) идут по регистру очереди `plans/README.md` § «Кросс-плановая последовательность» (терминальные AR P1/P2 открывают CP-гейты) без отдельного G1-решения, если владелец явно не решит иначе. Снимает противоречие Ф1: FM P1.5 открывается терминальной AR P2 без G1 — это и есть регистр очереди, а не нарушение G1. (2) Долг D47 «зеркальная `Consumed`-строка на стороне `2026.07.25-ECO-OPT`» снимается: ECO на `finish` решил `Consumed` для трёх бампов (`plan-protocol@2.12.0`/`skiller@0.5.0`/`task@0.4.0`) не заводить (его D85) — обоснование D85 покрывает ровно три execution-контракта этого плана, пин без реагирующего item'а был бы декоративным. AR работает по фактическому канону экосистемы после CP-P2 без пина этих трёх версий; при появлении item'а, реагирующего на будущий бамп, вопрос переоткрывается адресной D-записью, а не тихим восстановлением строки. | RAG:— (repo-grounded: `plans/README.md` § «Аудит этапа C — 2026-07-25» Ф1/Ф3/Ф8; §2 FOREMAN-строка и §10 G1 этого плана; `plans/2026.07.25-ECO-OPT/plan.md` §5 D52/D85). |

| D59 | 2026-07-25 | **G0 — заморозка Acceptance v1 и банка принята агентом (D50), P0.4 разблокирован.** Заморожено на item-коммите `f405017a`: `root/contracts/reliability-acceptance-v1.md` + банк `artifacts/reliability-bank-v1/` (31 кейс = 25 critical + 6 control, 88 ассершенов, 48 проб, 26 семейств, 14 floors, seed `reliability-bank-v1/2026-07-25`), хеши — `bank-manifest.json` `content_hash=82d1e6a9997dc8de…`, `cases.json`/`graders.json`/`baseline-results.json`/`run_bank.py` запинены там же вместе с `corpus.json`, `baseline.json`, `verification-report.json`. **Четыре решения, принятые записью, а не вопросом (D50):** (1) **два слоя baseline.** Layer-1 — детерминированная оценка ОБЪЯВЛЕННОГО доремонтного поведения, чьё провенанс-заявление исполняемо (48 проб по байтам репозитория; `baseline` отказывается работать, если заявленное отсутствие перестало держаться). Layer-2 — живой парный прогон тех же кейсов/грейдеров на `pre-plan-sha` (D45), производитель P3.3. Альтернативы отклонены: «только объявленный baseline» выдал бы декларацию за измерение, «ждать живого парного прогона» отложил бы заморозку ЗА первую мутацию и сломал бы D15/D16. (2) **Ни один floor не опирается на pinned-not-recomputable величину** — F9 (контекст) и F10 (owner intervention) берут знаменатель у layer-2, а не у `dedup_correction` (135 110 000) и не у `journals.outcomes`; F6 — у контролируемого банка, а не у исторической completeness от 550 classified events. Правило исполняемое: `run_bank.py` отклоняет floor с `pinned_inputs` или с `evidence_refs` в класс `pinned-not-recomputable` отчёта P0.1 (оба зонда дают exit 1). (3) **F14 `false_block_rate == 0` добавлен СВЕРХ §8**: §8 не содержит защиты от лечения через тотальную блокировку — без него максимально консервативная реализация зеленела бы по всем тринадцати остальным строкам. (4) **`routing_compliance` сообщается без floor'а**: §8 порога не содержит, а назначение порога на шаге заморозки было бы ровно тем candidate-side тюнингом, который D15 запрещает. Floors §8 перенесены дословно с квалификатором D53 (F4 — «0 в объявленной фикстуре P1.4»), строка живого хоста `core`+донор осталась диагностикой D42, а не floor'ом. Процедура коррекции (D15) машинно поддержана: `candidate` отказывается писать в замороженный `baseline-results.json` и отказывается от частичного прогона. Принятая и названная граница: layer-1 не является измерением живых прогонов модели, а контрольные кейсы на нём проходят дёшево (блокирующего слоя ещё нет) — их различающая сила на кандидатской стороне, и именно её ловит F14. | RAG:— (repo-grounded: собственные прогоны `run_bank.py baseline/verify/candidate/sample` и пять зондов на временных копиях, `findings/P0.3-acceptance-freeze.md`; plan-grounded: D10/D15/D16/D30/D50/D53). |

| D60 | 2026-07-25 | **Дефект ТЗ P0.3 исправлен записью (D50), а не эскалацией.** Команда Validation №4 `PYTHONPATH=packages/skiller/lib python3 -m unittest discover -s packages/skiller/tests -p 'test_eval.py'` невыполнима по построению: `packages/skiller/tests/test_eval.py:15` импортирует `tests.fixtures`, поэтому на `PYTHONPATH` обязан быть корень пакета, а не только `lib` — исходная форма даёт `ModuleNotFoundError: No module named 'tests'` независимо от работы item'а (канонический `packages/skiller/scripts/test.sh:20` кладёт в `PYTHONPATH` и `lib`, и корень). Синхронизировано: строка Validation P0.3 читает `PYTHONPATH=packages/skiller/lib:packages/skiller …` → `Ran 32 tests OK`; закрытие идёт по обновлённому ТЗ (🟢 + запись в Known Deviations, канон `plan-exec` §7). Эскалация в `plan-design` ради опечатки в `PYTHONPATH` воспроизвела бы ровно тот audit/fix-loop без продукта, который план создан лечить (D50). Правило на будущее (кандидат в `plan-lint`): команда Validation, ссылающаяся на `unittest discover` в пакете с `tests/`-пакетными импортами, обязана нести корень пакета в `PYTHONPATH`. | RAG:— (repo-grounded: `packages/skiller/tests/test_eval.py:15`, `packages/skiller/scripts/test.sh:20`, собственный прогон обеих форм команды). |
| D61 | 2026-07-25 | **P0.4 закрыт с process-отклонениями (agent, D50): три ТЗ/repo-drift синхронизации.** (1) `Files` P0.4 не называл `.codex/hooks/lifecycle.py` и `.swissknifeman/provider-artifacts.lock.json` — прямые обязательные спутники регистрации `.codex/hooks.json` (без хендлера хук даёт exit 127; без лока артефакт вечно `ownership-conflict`); добавлены в `Files` item'а. (2) Validation-команда `test_hooks.py` (`PYTHONPATH=packages/harness/lib …`) не импортировала `tests.fixtures` — тот же класс дефекта, что D60: нужен корень пакета на `PYTHONPATH`; синхронизирована на каноническую форму `packages/harness/scripts/test.sh`. (3) `packages/harness/lib/harness/instructions.py:241` (`contract_path()`, вне `Files` P0.4 — принадлежит D86 instruction-projection seam) нёс путь до архивации `2026.07.19-DUAL-PROVIDER` (коммит `5b79f926` перенёс план в `plans/archive/`), ломая `test_provider_instructions.py`, `test_instruction_compatibility.py` и `packages/harness/scripts/validate.sh` целиком независимо от работы этого item'а; путь синхронизирован (тем же исправлением — один захардкоженный путь в `test_provider_conformance.py:170`). Item-коммит несёт дифф вне буквальных `Files` (`instructions.py`) → статус item'а `🟠 Done with deviations` обязателен по status-rule, независимо от корректности самого диффа. Полная диагностика и восстановление self-host hook lifecycle — `findings/P0.4-hook-integrity.md`. | RAG:— (repo-grounded: собственные прогоны `test_hooks.py`/`test_provider_conformance.py`/`test_provider_instructions.py`/`packages/harness/scripts/validate.sh` до и после правки; `git log` коммита `5b79f926`; `findings/04-runtime-preflight.md`). |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 1/3: initial audit/telemetry/SSOT synthesis and 5-phase draft; design audit attempt 1 returned RED — `findings/07-design-audit-red-attempt-1.md`. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 2/3: full plan sweep corrected RCA, evidence manifests, neutral routing, exact phase specs, roadmap carriers and canary topology; Pass 3 remains. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 3/3: fresh full-plan DoR/brief/RCA/dependency/routing/CLI sweep; exact reads, contribution gates, semantic+native recovery carriers and safe temp/worktree contracts reconciled; next — separate audit-design. |
| 2026-07-24 | Owner refinement / plan-design | D25 removes host-bound execution evidence. The materialized bundle passed four verifier modes: 20 manifest entries, 7 journals, 5 sanitized cases, corrected denominators/control and 8 claim ranges. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 3/3 final reconciliation: downstream items, findings, roadmap and handoff consume only the source bundle; version 1.4.0 is ready for separate fresh audit-design. P0 remains unexecuted. |
| 2026-07-24 | Owner refinement / plan-design | D26 promotes self-contained planning into the canonical package contract without adding a phase/item: P0.2/P0.3 freeze fields/cases; P2.1/P2.2 define and enforce tiers in Task Contract, plan-design and plan-lint; P2.5/P3.3 run conformance; P4.3 publishes docs. Version 1.4.0 remains 21 items. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Audit attempt 2 stopped pre-verdict on SSOT gaps. Reopened Pass 3 added D27 version/generated-tree closure and D28 exact 12-collision removal plus P1.4 cold discovery. Version 1.5.0; 21 items; P0 unexecuted. |
| 2026-07-25 | Owner override B / plan-design Codex gpt-5.6-sol/xhigh | Design pass 4/4: preserved audit RED 2/2, redesigned F1 as immutable-integrity + item-owned semantic verification and F2 as private 13-source + one generated root-bootstrap unit. Version 1.6.0; 21 items; P0 unexecuted; next is the sole exceptional audit `0/1`. |
| 2026-07-25 | root review / plan-design Codex gpt-5.6-sol/xhigh | Authority correction: option B grants redesign + one audit only. Version 1.6.1 adds `G-EXEC`; even literal GREEN stops at Owner and cannot auto-launch P0.1. |
| 2026-07-25 | plan-design / Claude Fable 5 (Owner authority C) | Repair F1–F3 attempt 3 (D34: base-sha baseline; F2 Required Reads; F3 bootstrap-map gate) + acting provider → Claude (D32/D33). Version 1.7.0; 21 items; P0 unexecuted; next — A1 audit. |
| 2026-07-25 | plan-design/Codex gpt-5.6-sol/high | Design pass 5/5: D36–D38 close only `findings/09` F1–F3; 21-item sweep complete. v1.8.0; P0 unexecuted; pre-redesign A1 RED is historical; next exactly A2 audit `0/1`. |
| 2026-07-25 | plan-design/Claude Opus 5/high (Owner authority D) | Bounded repair A1 F1–F10 → D39–D48 (коллизии 16+1, item P1.5 перед P1.4, `PRE_PLAN_SHA`, `--effort`, self-conformance P2.2, cross-plan ECO-OPT). v1.9.0; 22 items; P0 unexecuted. D49 фиксирует параллельный A2 RED — его 3 находки вне скоупа, долг владельцу. |
| 2026-07-25 | plan-design/Claude Opus 5/high (Owner authority E) | Bounded repair A3 F1–F6 → D50–D55; §10 переписана: слоты A0–A3 → история, `G-EXEC` выдан для self-host, за владельцем только G1. v1.10.0; 22 items; старт P0 разрешён. |
| 2026-07-25 | plan-design/Claude Opus 5/high (программный гейт) | D56: design-first по экосистеме — исполнение после этапов A–C; ACTIVE передан ECO-OPT, `Paused By` проставлен. v1.11.0. |
| 2026-07-25 | plan-design/Claude Opus 5/high (принципы) | D57: четыре принципа владельца → 12 инвариантов И1–И12 в `plans/README.md`; §2 несёт ссылку. Version 1.11.0 → 1.12.0. |
| 2026-07-25 | bookkeeping/Claude Sonnet 5/high (payload A, аудит этапа C Ф1/Ф3/Ф8) | D58: G1-формулировка о FOREMAN сужена до наружных частей (§2/§10 правлены); долг D47 «зеркальная Consumed-строка ECO» снят; предстартовые строки добавлены в ТЗ P3.3 (`phases/P3.md`) и P4.3 (`phases/P4.md`). Version 1.12.0 → 1.12.1. |
| 2026-07-25 | plan-exec/Claude Sonnet 5/medium | P0.1 закрыт: item-owned semantic verification contract/verifier/tests/report над immutable bundle (F1 gap, D30) — 16/16 assertions, 15/15 tests, `pre-plan-sha.txt` (D45). Детали — `phases/P0.md` P0.1 Completion Notes. Version 1.12.1 → 1.12.2. |
| 2026-07-25 | plan-run/Claude Opus 5/high | P0.2 закрыт: Task Contract v1 запечатан — схема, precedence, два предиката с 16 типизированными кодами, 23 проверенных кейса, 4/4 критических кейса корпуса P0.1 связаны с полем и проверкой — детали см. phases/P0.md P0.2 Completion Notes. Version 1.12.2 → 1.12.3. |
| 2026-07-25 | plan-run/Claude Opus 5/high | P0.3 закрыт: Acceptance v1 и fixed bank заморожены (31 кейс, детерминированные грейдеры, два слоя baseline, 14 floors), G0 принят агентом записью D59, дефект ТЗ Validation исправлен D60 — детали см. phases/P0.md P0.3 Completion Notes. Version 1.12.3 → 1.12.4. |
| 2026-07-25 | plan-run/Claude Sonnet 5/high | P0.4 закрыт 🟠: self-host Codex hook lifecycle восстановлен через существующий D104 bootstrap-transfer (maind), три ТЗ/repo-drift дефекта синхронизированы записью D61 — детали см. phases/P0.md P0.4 Completion Notes/Known Deviations, findings/P0.4-hook-integrity.md. Version 1.12.4 → 1.12.5. |
| 2026-07-25 | plan-run/Claude Opus 5/high | P1.1 закрыт 🟢: Identity/Ownership v1 и Generated Artifact Version v1 заморожены (детекция repo-derived, owner-map всех 29 коллизий, class-A 13/26) — детали см. phases/P1.md P1.1 Completion Notes. Version 1.12.5 → 1.12.6. |
| 2026-07-25 | plan-run/Claude Sonnet 5/high | P1.2 закрыт 🟠: 13 приватных root-bootstrap identities канонизированы (26 тонких проекций + lock), skiller/core/skm 0.4.1, шесть root core-коллизий удалены — детали см. phases/P1.md P1.2 Completion Notes/Known Deviations. Version 1.12.6 → 1.12.7. |

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| `root/contracts/source-evidence-verification-v1.md` | v1 | committed P0.1 | P0.2, P0.3, P3.2, P3.5 | task, skiller, analyst |
| `root/contracts/task-contract-v1.md` | v1 | committed P0.2 | P0.3, P2, P3 | task, skiller, harness |
| `root/contracts/reliability-acceptance-v1.md` | v1 | committed P0.3 (G0 — агент, D59) | P0.4–P3 | skiller, task, analyst, harness |
| `root/contracts/semantic-identity-ownership-v1.md` | v1 | committed P1.1 (`628092b3`) | P1.2, P1.3, P1.5, P1.4 | skiller, task, harness |
| `root/contracts/generated-artifact-version-v1.md` | v1 | committed P1.1 (`628092b3`) | P1.2, P1.3, P1.5, P2.2, P2.3, P4.3 | skiller, task, harness |
| `root/contracts/execution-state-machine-v1.md` | v1 | planned P2.1 | P2.2–P3 | task, analyst |
| `root/contracts/risk-review-loop-budget-v1.md` | v1 | planned P2.1 | P2.3, P2.5, P3.1, P4.3 | task, analyst |
| `root/contracts/plan-portability-v1.md` | v1 | planned P2.1 | P2.2, P2.5, P3.3, P4.3 | task, skiller |
| `root/contracts/unified-agent-trace-v1.md` | v1 | planned P3.1 | P3.2–P4 | analyst, harness, task |
| `plan-protocol` skill canon | v2.12.0 | planned P2.2 | план `2026.07.25-ECO-OPT` (его P2.2, P7.1) | skiller; ECO-OPT — Owner-facing долг зеркальной `Consumed`-строки |
| `skiller` package API + `general`/`core` units | v0.5.0 | planned P2.2 | план `2026.07.25-ECO-OPT` (его P2.2) | skiller; ECO-OPT — тот же долг |
| `task` plugin/routing (`plugin_version`) | v0.4.0 | planned P2.2 (далее v0.5.0 в P2.3) | план `2026.07.25-ECO-OPT` (его P2.2, P7.1) | task; ECO-OPT — тот же долг |

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| plan-protocol | repository canonical source | `2.11.0` at Pass 2 | P0/P2/P4 | re-read exact source before each plan item |
| provider publication/artifact contract — **low-trust / verify-before-use (D54)** | 2026.07.19-DUAL-PROVIDER (Codex-авторство, терминал 🟠, P7.4 `ATTENTION`) | execution commit at P1 start | P1: 30 root-адаптеров внесены мимо генератора коммитом `e8f5b477` → 16 коллизий `findings/12` | презумпция корректности снята: P1.2/P1.3/P1.5 доказывают поведение затронутых seam'ов характеризационным тестом на месте; Claude compatibility и managed generation — требование, а не унаследованный факт |
| Codex hook/plugin/skill behavior | official docs snapshot | reverify at P0.4/P1/P3 | external capability drift | fail closed, update `findings/` first |

## 8. Acceptance proposal for the P0.3 freeze (G0 — агент, D50)

| Метрика | Proposed floor |
|:--|:--|
| Critical requirement retention | 100% critical bank |
| Premature stop / redundant approval | 0 critical bank |
| Effective semantic identity collisions | 0 в объявленной фикстуре P1.4 (D51/D53) |
| Живой хост: `core` + донорский бакет включены одновременно | диагностика D42 с непустым `safe_owner_action` (не floor: план не правит user-owned enabled-множество) |
| Hook/reference/provider resolution | 100% controlled fixtures |
| Required trace completeness | ≥99% controlled bank |
| Overall first-pass success | ≥95% and ≥30 percentage points over paired baseline |
| Context input per successful outcome | ≤50% paired baseline |
| Owner intervention | ≤25% paired baseline |
| Same-finding loop depth | median ≤1, p95 ≤2 |
| Critical regression escape | 0 |

**ЗАМОРОЖЕНО D59 (G0 — агент, D50), 2026-07-25.** Строки выше перестали быть
предложением: их исполнимая форма — 14 floors в
`root/contracts/reliability-acceptance-v1.md` и `artifacts/reliability-bank-v1/bank-manifest.json`
(`content_hash=82d1e6a9997dc8de…`, item-коммит `f405017a`), где у каждой названы
measurement owner и слой baseline. Добавлена одна строка сверх таблицы —
**F14 `false_block_rate == 0` на контрольных кейсах** (защита от лечения через
тотальную блокировку, обоснование в D59). Две строки таблицы резолвятся ТОЛЬКО
против живого парного прогона layer-2 (P3.3) и не берут знаменатель у запиненных
величин бандла: «Context input per successful outcome» и «Owner intervention»
(D30/D59). Baseline/corpus/grader hashes и точные floors заморожены вместе.
Candidate-only threshold changes are forbidden; a grader correction versions the
bank and reruns both sides.

## 9. Risks and Boundaries

| Risk | Control |
|:--|:--|
| RCA again hardens a correlation into cause | P0.1 per-case falsification table; `unknown` allowed |
| Plan adds another prose control | P2 one compiler/state seam + conformance tests |
| Source evidence disappears/drifts | committed `artifacts/source-evidence/` with per-file hashes and deterministic verifier; external origins are optional |
| Immutable integrity verifier again accepted as semantic proof | D30 two-layer contract: all four immutable modes run, then P0.1-owned semantic tests/report classify every claim by proof class; bundle diff must remain empty |
| Claude/new clone cannot see Codex-host raw evidence | no execution dependency remains: full audit/journals and sanitized selected incidents are committed; raw rollouts are intentionally excluded |
| Future plans repeat host-bound evidence | D26 compiled portability tiers + plan-design/plan-lint gates + P2.5/P3.3 conformance; not a prose-only reminder |
| `root/` mistaken for OS `/root` or removed after archived-plan migration | D24 + plan-protocol §3: it is a repo-relative plan artifact directory; `454ea86d` is not a canon change |
| Hook repair invalidates baseline | P0.3 freeze before P0.4 mutation |
| Runtime dedup breaks Claude | provider goldens + effective installed-runtime fixtures |
| Registry package bump rewrites unrelated bucket manifests | D27 per-publication-unit version map + exact diff-scope guard + no-op second check |
| Collision gate merely suppresses duplicate adapters | D40 ownership-инвариант вместо литерала: 16+1 измеренных коллизий с owner-item каждой (P1.2/P1.3/P1.5) + P1.5 «root-набор = declared target set» + P1.4 cold install/discovery exactly-once proof |
| Frozen collision count снова расходится с runtime | D44 repo-derived worst-case как authoritative вход гейта (считается холодно, fail-closed) + machine-readable observed capture с провенансом; прозаический счётчик — `pinned-not-recomputable`, не scope |
| `core` и донорский бакет включены одновременно → живой дубль | D42 инвариант взаимного исключения в Identity/Ownership v1 + детектор P1.5 с диагностикой; user-owned enabled-множество план не меняет |
| Параллельные коммиты чужого плана (`2026.07.25-ECO-OPT` P1/P4) ломают diff-scope guard | D47 foreign-commit атрибуция: чужой дифф вне owner-набора → `foreign-commit`, чужой коммит в owner-пути → fail closed с Owner-вопросом; stash/revert запрещены |
| Rollback-путь фазы P3 репетируется на неопределённый ref | D45 единственный производитель `PRE_PLAN_SHA` — P0.1-owned committed файл + ancestor-валидация до создания worktree |
| Private 13-skill canon leaks into a normal bucket/plugin/consumer vendor channel or root copies drift | D31 source-only publication and vendor/connect exclusion, bilingual source hashes, one `registry.py`→`publication.py` generator, 26 thin projections + version/tree lock and P1.4 exactly-once/provenance checks |
| Canary touches user work | detached disposable worktree; clean-state cleanup guard |
| Self-host GREEN is called fleet GREEN | P3.5 scope literal; P4.3 explicit Owner gate |
| Гейт «catalog-wide» зеленеет по необъявленному сужению каталога | D51 declared literal `artifacts/P1.4/fixture-unit-set.json` + машинная сверка состава + обязательный негативный D42-прогон по ИМЕНАМ девяти пар |
| Ремонт A3 уходит в исполнение без седьмого независимого design-аудита | принятый риск D50: рационирование слотов снято сознательно; первая независимая проверка — канонический аудит фазы P0 («два аудита на фазу»), а не ещё один design-заход |
| Артефакты `2026.07.19-DUAL-PROVIDER` принимаются как доказанные | D54 low-trust: характеризационный тест на месте в P1.2/P1.3/P1.5; терминальный 🟠 донора не является зелёным входом |
| P4 dynamic hypothesis causes wildcard scope | accepted structural refactor leaves this plan as a new proposal |

## 10. Owner Approval Boundaries

**Действующая граница — Owner authority E (D50).** Владелец делегировал агенту
проектные и приёмочные решения; за ним остаётся только необратимое и наружное.

- **G1 at P4.3 — ЕДИНСТВЕННЫЙ действующий Owner-гейт.** Отдельно решается любая
  запись наружу: fleet и 17 подключённых проектов, consumer-репозитории, tag,
  push, release, наружные части `plans/2026.07.18-FOREMAN` (fleet-раскатка,
  массовость пилота — D58). Внутренний bookkeeping/дизайн FOREMAN, включая
  P1.5, идёт по регистру очереди `plans/README.md` § «Кросс-плановая
  последовательность», не по G1. P4.3 только собирает packet и может
  рекомендовать hold. Граница — «нельзя откатить / видно снаружи», а не
  граница компетенции.
- **G-EXEC — выдан authority E (D50).** Self-host P0–P3 исполняются без
  отдельного человеческого гейта; P0.1 стартует по `handoff.md`.
- **G0 after P0.3 — принят агентом 2026-07-25 записью D59**: exact Acceptance v1,
  bank/grader hashes и floors (§8 с квалификатором D53) зафиксированы, P0.4
  разблокирован. Отдельной остановки на владельце не было и не требовалось.
- **Аудиты — по канону, не по личным слотам (D50).** Действует
  plan-protocol «два аудита на фазу, третий → решение»; вердикт выносит агент.
  Отдельный седьмой design-аудит не назначается — принятый риск назван в §9.
- **Исторические факты (не действующий механизм, не переименовывать):**
  A0 exceptional audit — RED (`findings/09`); A1 authority-C — RED на
  pre-redesign `fe3e1646` (`findings/10`); A2 option-B (D35) — RED на committed
  `916acdb5` (`findings/11`, D49); A3 — RED (`findings/13`); плюс два
  исторических вердикта cap 2/2 (`findings/07`, `findings/08`). Authority C (D32),
  option B (D35) и authority D (D39) — CONSUMED; их скоупы закрыты.
- **Открытый названный долг (не блокирует старт, ведётся в `handoff.md`):** три
  находки A2 (порядок capture `base-sha` по D36; отсутствие workflow-carrier у
  заявленной автономной цепочки; `research/01–03` без ссылок на слой 1 и
  RAG-маркеров); A1 F11; Claude-проекция `workflow-craft`; read-only измерение
  Claude enabled-set. Долг «зеркальная `Consumed`-строка в `2026.07.25-ECO-OPT`»
  снят D58 (ECO решил `Consumed` не заводить, его D85).
- Новая внешняя authority, деструктивная операция или изменение замороженного
  контракта вне точного Scope item'а по-прежнему останавливаются на явном
  вопросе владельцу.
