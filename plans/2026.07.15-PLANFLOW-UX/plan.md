# 2026.07.15-PLANFLOW-UX — Надёжность и UX плановой/workflow-системы

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.15-PLANFLOW-UX |
| Title | Надёжность и UX плановой/workflow-системы (launch-block · workflow-авторинг · дизайн-флоу) |
| Version | 0.4.0 |
| Status | 🟡 In progress (design) |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-07-16 (P4.1 закрыт 🟠) |
| Repository | swissknifeman |
| Related Packages | task (plan-protocol/workflow-craft скиллы, команды plan-*/make-workflow/review), skiller (реестр скиллов, budget), harness (agent-packs dev-loop, run-report) |
| Execution Mode | phase-first |
| Target Operator Models | opus (recon/design/audit) · sonnet (exec) · fable/haiku (mechanical) |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| Paused By | — |

## 1. Context

Ежедневная работа с плановой/workflow-системой буксует по 5 кластерам (запрос Owner, 2026-07-15):
**(1) Handoff «что дальше»** — выхлоп не копипастится, приходится переспрашивать *реальный*
промпт/команду; иногда предлагается невыполнимое. **(2) Workflow-авторинг** — свежие workflow
(dterema/chatom/corex/themeon/vaulter, design-time скан: 65 `.js` по экосистеме + Brain)
разношёрстные и багованные; скилл `workflow-craft` не виден/соблюдается криво; базовые dev-шаблоны
мёртвые (фазы динамические). **(3) Скорость** — переревью на каждом шаге, долго; мелкие подфазы
не батчатся. **(4) Дизайн-флоу** — детализируем одну фазу → сразу пилим; нет режима «спроектировать
все фазы, утвердить бесконфликтную схему → потом исполнять» + глобального exec-плана с батчами.
**(5) Итеративный дизайн клинит** — plan-design гоняется 4–5 раз (фикс одного ломает другое); ошибки
при исполнении фазы репортятся «готов к следующей, ноут: были ошибки» вместо «сразу предложить фикс».
**Ключевой диагноз (гипотеза → верифицируется P1):** launch-block (plan-protocol §8) и статич-ревьюер
`make-workflow` УЖЕ в спеке → корень скорее **конформанс + дыры вне `plan-*`-команд + качество
самих скиллов/шаблонов**, а не отсутствие шаблона. Поэтому план начинается с **recon-доказбазы**
(P1), фиксы гейтятся на фактах (как TELEMETRY-OPT из telemetry-baseline). Cross-plan: план правит
те же скиллы, что TELEMETRY-OPT P1/P2/P4 → его **exec gated на терминальности TELEMETRY-OPT** (§7).

## 2. Execution Rules

- Один item за раз; статусы — 6 канонических строк байт-в-байт (plan-protocol §5).
- **stdlib-only** во всех python-правках; скиллы: `SKILL.ru.md` → регенерация `SKILL.md` →
  `check-translations.sh --stamp` → `skiller registry`.
- **Философия «результат > экономии» (D6, жёстко):** оптимизация, ведущая к деградации итогового
  результата (плохой план/ревью/workflow) — ЗАПРЕЩЕНА, даже если дешевле по токенам. Экономим там,
  где это не бьёт по качеству. При любой развилке исполнитель выдаёт **рекомендацию с причиной**
  (к чему склоняется и почему), а не голый вопрос Owner.
- **Cross-plan gate (§7 Contracts):** exec любой фазы PLANFLOW-UX НЕ стартует, пока TELEMETRY-OPT
  не терминален по P4+P5 (правит общие скиллы `workflow-craft`/`anti-drift`) — иначе конфликт правок.
  Дизайн (эта фаза и детализация) — можно параллельно.
- **ACTIVE.md не трогаем** (D3): активен TELEMETRY-OPT (в исполнении); PLANFLOW-UX — в дизайне.
- План разошёлся с кодом → не импровизировать, эскалировать (plan-protocol §10).
- После закрытия item/фазы — перезаписать `handoff.md`; после правок скиллов — `skiller registry`.

## 3. Routing

| Items | Model/effort | Exec | Почему |
|:--|:--|:--|:--|
| P1.1 | opus/high + perplexity-web | manual | оценочный recon 65 workflow + кросс-файловый синтез паттернов + архитектурная критика скиллов + RAG на best-practices оркестрации; синтез > fan-out (паттерн-инсайт теряется на дроблении); effort high+ MANDATORY |

| P2.1 | opus/high | manual | public-contract-change: 9-я форма enum `Next` + правка линтера с back-compat флота (recon §2.2 D20/D28 — канон-правки рябят) + реестр литералов/i18n-гейт; §9 «public contract/SemVer → high+ MANDATORY»; opus — субтильный back-compat/инвариант, не механика; effort>medium → manual |
| P2.2 | sonnet/high | manual | авторинг правила-дисциплины в канон §8 + `plan-exec.md` (без линтера/парсера/литерала — ниже back-compat-риск P2.1); точность прозы, читаемой флотом → high; effort>medium → manual |

| P3.1 | sonnet/high | manual | канон-когерентность 3 файлов (`make-workflow.md`↔README§3↔`workflow-craft`§3) — снять 3 ложных-RED без снятия детекции; §9 «канон, за которым следует флот → high MANDATORY»; effort>medium → manual; sonnet — рекалибровка по recon-целям, не новая архитектура |
| P3.2 | sonnet/high | manual | хардненинг 4 канон-шаблонов (safeAgent/REPO-guard/guarded-args/cache-bust) + §2.1 — аддитив к живой оркестрации, не ломать циклы; правит канон+SKILL → high; effort>medium → manual; исполнять ПОСЛЕ P3.1 (общий README) |
| P3.3 | sonnet/medium | plan-exec | детерминированный чек `plan_lint` (имя/место workflow) + TDD-тесты; независимый scope (python), Validation = unittest; дефолт-деривация (model≤sonnet ∧ effort≤medium → plan-exec) |
| P3.4 | sonnet/medium | plan-exec | механический guard args-строки в 5 dev-loop (harness); независимый scope, Validation = `node --check` + пак-валидация; дефолт-деривация → plan-exec |
| P3.5 | opus/high | manual | analysis+рекомендация (budget-квантификация + канал доставки + OQ-3) — judgment Owner-facing, не код; decision-item → manual явно; opus — критика-рекомендация с budget-tradeoff |

| P4.1 | opus/high | manual | новая методология contract-first в ядро-канон `plan-protocol` (§3/§5 + `plan-design` + snippet) — субтильный fleet-facing дизайн-флоу, не механика; §9 «декомпозиция/методология → high+ MANDATORY»; effort>medium → manual; opus — новая архитектура дизайн-флоу |
| P4.2 | sonnet/high | manual | канон-схема §3 Routing (+`Batch`/`Review` колонки) + семантика батчинга по резолву OQ-1/D12 — канон-когерентность, читаемая флотом → high; effort>medium → manual; sonnet — расширение схемы, не новая архитектура; ПОСЛЕ P4.1 (общий `SKILL.ru.md`) |
| P4.3 | sonnet/high | manual | классификация риска среза → глубина ревью (наполняет `Review` enum из P4.2) + D6-инвариант — канон, fleet-facing → high; effort>medium → manual; ПОСЛЕ P4.2 (колонка существует) |

<P5 — скелет; routing проставится при детализации фазы (`/task:plan-design <ID> Pn`).>

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Recon: доказбаза (workflow-авторинг · plan-design клинчи · handoff-конформанс) | 1/1 | 🟢 Done |
| P2 | Launch-block энфорсмент + ошибка→сразу-фикс | 1/2 | 🟠 Done with deviations |
| P3 | Workflow-авторинг + авто-ревью (make-workflow ревьюер · base-шаблоны · видимость скилла) | 2/5 | 🟠 Done with deviations |
| P4 | Contract-first дизайн-флоу + глобальный exec-план + батчинг + адаптивная глубина ревью | 0/3 | 🟡 In progress |
| P5 | Fix-стратегия plan-design + архитектурный апгрейд скиллов/сниппетов | 0/2 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-15 | Контейнер — **отдельный план** (не фаза TELEMETRY-OPT); дизайн сейчас, **exec после TELEMETRY-OPT P4/P5** (cross-plan gate §7). Owner-подтверждено (AskUserQuestion Q1) | Другой класс задачи (UX/надёжность плановой системы vs измеренный токен-cut); размер (5+ фаз); правит общие скиллы, что TELEMETRY-OPT ещё не закрыл → развести планы. RAG:— (repo-grounded: Owner-выбор в сессии + темы двух планов) |
| D2 | 2026-07-15 | **Recon-first** (P1 — гейт всего): пофайловый разбор workflow с лупой **2×2 «навыки были в проекте? × качество good/bad»** → бакеты: (a) нет-скиллов+плохо = onboarding-дыра; (b) скиллы-есть+плохо = **конкретный дефект авторинга/скилла** (несущий бакет); (c) скиллы-есть+хорошо = baseline. Плюс оценка адекватности САМИХ скиллов/сниппетов/шаблонов (архитектура), не только их наличия. Scope — все недавно-активные проекты + Brain-вэлт (design-time: 65 `.js`). Owner-уточнено (Q2) | Фиксы на falsified-гипотезе жечь нельзя (CLAUDE.md методология); 2×2 отделяет «проект без скиллов» от «скилл/авторинг дефектен» — разные ремедиации (deploy vs правка скилла). RAG:— (repo-grounded: Owner-уточнение Q2 + design-time скан 65 файлов) |
| D3 | 2026-07-15 | **ACTIVE.md НЕ переkey'ится** — TELEMETRY-OPT остаётся активным (он в исполнении); PLANFLOW-UX в статусе дизайна, exec gated. Отклонение от дефолта plan-design-`new` (seiz'ит ACTIVE + Paused By) — осознанное | Seiz'нуть ACTIVE = поставить TELEMETRY-OPT на паузу, но его P4/P5 должны закрыться ПЕРВЫМИ (D1 gate). Дизайн ahead активности не требует. RAG:— (repo-grounded: plan-protocol §2 ACTIVE + §4 Paused By) |
| D4 | 2026-07-15 | **Диагноз-гипотеза:** launch-block (§8) и статич-ревьюер `make-workflow` УЖЕ в спеке → корень 5 кластеров скорее **конформанс/дыры/качество**, не отсутствие шаблона. Статус — ГИПОТЕЗА, верифицируется P1 recon (не презумпция) | Меняет стратегию фиксов: энфорсмент + закрытие дыр + апгрейд качества скиллов вместо «рисовать новые шаблоны». RAG:— (repo-grounded: plan-protocol §8 launch-block/cold-start/ЗАПУСК-ВРУЧНУЮ + skill `task:make-workflow` desc «статич.выходной ревьюер RED блокирует») |
| D5 | 2026-07-15 | **Дизайн-философия плана = contract-first гибрид:** P2–P5 запечатаны как скелеты со scope/границами СЕЙЧАС (cross-phase конфликты видны заранее — запрос Owner «спроектировать все фазы»), item-детали — **just-in-time после P1 recon** (грунтовка на фактах — запрос Owner «recon»). Синтез двух требований Owner | «Всё детализировать вперёд» конфликтует с «грунтовать на recon» (детали до фактов = спекуляция); contract-first снимает cross-phase конфликты без полной верхней цены. RAG:— (repo-grounded: plan-protocol §3 canonical root arc42 + §11 cross-phase контракты + twin-запрос Owner) |
| D6 | 2026-07-15 | **Философия «результат > экономии»** вшита в Execution Rules как жёсткое правило + требование «рекомендация с причиной при любой развилке» (Owner: не в ущерб результату; всегда предлагай, не спрашивай голо) | Прямой запрос Owner: экономия, выливающаяся в проблемы, недопустима; переспросы без рекомендации — фрикция. RAG:— (repo-grounded: запрос Owner в сессии) |
| D7 | 2026-07-15 | **Scope P2 сужен до recon-доказанного C1/C2/C3** (форма `Next` «ОЖИДАНИЕ» + lint-детект прозы + миграция своего handoff + дисциплина ошибка→фикс). Обещанный скелетом «launch-block вне `plan-*` (`dev.md`/`fix.md`/ad-hoc)» вынесен из P2 → **OQ-2** (рекомендация: `dev.md` — да при всплытии боли, `fix.md` — терминальная микроправка, exempt) | recon (P1) falsified «вне plan-*» как измеренный корень: канон §8 работает где применён (25/30), измеренная боль — дыра enum (time-gate-проза), сконцентрирована в plan-handoff'ах; `dev.md`/`fix.md`-launch-block реально отсутствует (grep), но НЕ доказан как боль → не жечь фиксы на недоказанном (D2/CLAUDE.md методология). RAG:— (repo-grounded: findings §3/§5 + grep `dev.md`/`fix.md` в дизайне) |
| D8 | 2026-07-15 | **Форма `Next` «ОЖИДАНИЕ: <условие> → <целевая форма>»** — 9-я в enum §8: условие = дата/гейт (структурно), launch-block несёт целевую команду с guard-строкой `# НЕ раньше:`, резолв `plan_lint` `waiting` ДО `exec`, C2-детектор прозы = WARNING. Альтернативы — Обсуждение №3 | enum §8 не имел формы под «заблокировано/time-gate/делать-нечего» → проза в `Next` (recon §3.2, живой `SKM-MASTER-002`); отдельная СТРУКТУРНАЯ форма закрывает «невыполнимое/не копипастится», отличаясь от `🔴 Blocked` (дефект) и «план закрыт» (терминал). Аддитив + WARNING-гейты — back-compat флота (recon §2.2). RAG:— (repo-grounded: findings §3.2/§5-C1 + plan_lint.py:829 `_resolve_next_form`) |
| D9 | 2026-07-15 | **P3 разложена на 5 items = recon A1–A5** (findings §5-P3), не 2 скелетных: P3.1 рекалибровка ревьюера (A2), P3.2 хардненинг шаблонов+§2.1 (A3), P3.3 `plan-lint` имя/место (A4), P3.4 harness dev-loop guard (A5), P3.5 доставка-гейта analysis (A1). Скелетные «имена/крэш» покрыты (A4/A3/A5) | recon дал 5 адресных рычагов оси A; дробить по файловой когерентности (ревьюер vs шаблоны vs линтер vs harness vs доставка) — независимая Validation, честная доска; D6 «результат > экономии» — не ронять несущие фиксы в 2 item'а. RAG:— (repo-grounded: findings §5-P3 A1–A5) |
| D10 | 2026-07-15 | **A2 = канон-когерентность, не «усиление»:** 3 ложных-RED ревьюера (schema-на-каждом-`agent()`, top-level-`return`, SLOT-обязателен) откалибрены под эталоны СИНХРОННО в 3 файлах (`make-workflow.md` ↔ README §3 ↔ `workflow-craft` §3); РЕАЛЬНЫЕ детекторы (относит.пути, audit-read-only, форк) сохранены | ревьюер строже собственных эталонов → ложные RED → подрыв гейта (findings §1.4); `make-workflow` сам декларирует «дрейф от README = дефект» → правка во все 3 источника. RAG:✅ (P1 §6 perplexity-web 2026-07: schema на control-flow, проза локально — CONFIRMED) |
| D11 | 2026-07-15 | **A1 (⭐ доставка гейта) = analysis+рекомендация (P3.5) + OQ-3, НЕ rollout кодом.** budget-квантификация резидента + рекомендация канала (CORE vs onboard-required); фактический rollout делегирован skiller/maind пост-Owner-approval | контракт фазы «доставка не кодом в этой фазе (deleg)»; CLAUDE.md-гейт «новый always-on inject → `budget --first-turn`, Owner решает»; главный рычаг нельзя ни уронить (D6), ни раскатать без Owner/budget. RAG:— (repo-grounded: findings §5-A1 + CLAUDE.md budget-гейт + Phase Context контракт) |
| D12 | 2026-07-15 | **OQ-1 разрешён → вариант B: расширить `## 3. Routing` колонками `Batch`+`Review`** (НЕ новый `exec-plan.md` = вариант A, НЕ Status Board = C). Owner отказался от вопроса («не тупи, проектируй») → designer берёт рекомендацию с обоснованием. Alternatives — Обсуждение №2 | Протокол сам предостерегает «второй носитель факта = рассинхрон» (§3): отдельный `exec-plan.md` дублировал бы routing/статус items → анти-паттерн. §3 УЖЕ несёт per-item Model/effort/Exec → 2 непересекающиеся колонки = минимум механизма, ноль дублей; Status Board фазового уровня (неверная гранулярность подфаз). RAG:— (repo-grounded: SKILL.ru.md §3 «второй носитель» + §9 форма §3 Routing) |
| D13 | 2026-07-15 | **Граница P4/P5:** P4.1 кодифицирует FORWARD contract-first флоу + превентивное перечисление coupling-поверхности; RECOVERY (fix-стратегия когда refine клинчит) + верификация достаточности plan-protocol 2.7/D44 → **P5.1**. Alternatives (всё в P4 vs разнести) — Обсуждение №6 | recon §5 B1 назначил recovery+sufficiency-check на P5; contract-first дизайн-флоу (превенция ripple §2.2) — структурный кластер P4. Разнос убирает overlap, держит фазы независимыми. RAG:— (repo-grounded: findings/P1-recon.md §5 B1 + P4/P5 Phase Context) |
| D14 | 2026-07-15 | **Адаптивная глубина ревью = ПРИНЦИП, не форс** (recon: уже практика dev-loop, D6-легитимно): консервативная классификация (дефолт `full`, `light`/`none` с обоснованием, сомнение → `full` fail-safe); батч наследует МАКСИМУМ риска участников (D6-инвариант, связка P4.2↔P4.3) | Владелец: «переревью долго» (кластер 3), но D6 запрещает ронять качество; recon подтвердил risk-adaptive как best-practice, не «ревью везде». Fail-safe как routing-гейт §9 (цена ложного none = RED в проде). RAG:✅ (P1 §6 perplexity-web 2026-07: judge-panel high-stakes only, risk-adaptive review — CONFIRMED) |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-15 | plan-design/opus | План создан из запроса Owner (5 кластеров UX/надёжности плановой системы); P1 (recon) детализирован, P2–P5 скелеты; D1–D6; cross-plan gate §7 к TELEMETRY-OPT. ACTIVE не тронут (D3) |
| 2026-07-15 | plan-exec(manual)/opus/high | P1.1 закрыт 🟢, фаза P1 терминальна: recon `findings/P1-recon.md`; D4 верифицирован A✅/B🟡/C✅; скелеты P2–P5 подтверждены; гейт TELEMETRY-OPT снят — детали см. phases/P1.md P1.1 Completion Notes |
| 2026-07-15 | plan-design/opus | P2 детализирована (2 item'а): P2.1 форма `Next` «ОЖИДАНИЕ» + lint-детект прозы + миграция SKM-MASTER-002 (opus/high manual); P2.2 дисциплина ошибка→фикс (sonnet/high manual). D7 (scope-сужение вне-plan-*→OQ-2), D8 (форма «ОЖИДАНИЕ»); Обсуждение №3/№4; v0.1.0→0.2.0 |
| 2026-07-15 | plan-run(manual)/opus/high | P2.1 закрыт 🟠 (dev outside Files): 9-я форма `Next` «ОЖИДАНИЕ» (SKILL §8 RU+EN + 2 сниппета), `plan_lint` резолв `waiting`+C2-WARNING, миграция SKM-MASTER-002; deviation — регенерённые skills.json/budget.md вне Files — детали см. phases/P2.md P2.1 Completion Notes |
| 2026-07-15 | plan-run(manual)/sonnet/high | P2.2 закрыт 🟢, фаза P2 терминальна (🟠 — P2.1 деviation): дисциплина «ошибка→фикс-предложение» C3/D6 в SKILL §8 (RU+EN, ≤8 строк) + зеркало `plan-exec.md` §6/§8 — детали см. phases/P2.md P2.2 Completion Notes |
| 2026-07-15 | plan-close(manual)/sonnet/low | Фаза P2 закрыта: Phase Handoff заполнен (агрегат Known Deviations из P2.1/P2.2), handoff.md перезаписан (after P2), lint прогнан |
| 2026-07-15 | plan-design/opus | P3 детализирована (5 items = recon A1–A5, ось A) — ТЗ см. phases/P3.md P3.1–P3.5. D9–D11; OQ-3 (канал доставки гейта); Обсуждение №5 (pre-mortem рекалибровки); v0.2.0→0.3.0 |
| 2026-07-15 | remediation(bookkeeping)/sonnet/low | Ремедиация: `skiller registry` (дрейф skills.json/budget.md устранён, validate.sh зелёный); §7 Consumed — TELEMETRY-OPT терминален+архивирован, гейт снят |
| 2026-07-15 | plan-run(manual)/sonnet/high | P3.1 закрыт 🟠 (registry-артефакты вне Files, паттерн P2.1): 3 ложных-RED сняты в make-workflow.md/README/workflow-craft — детали см. phases/P3.md P3.1 Completion Notes |
| 2026-07-15 | plan-run(manual)/sonnet/high | P3.2 закрыт 🟠 (registry-артефакты вне Files, паттерн P2.1/P3.1 3-й раз): хардненинг 4 шаблонов + workflow-craft §2.1 — детали см. phases/P3.md P3.2 Completion Notes |
| 2026-07-15 | plan-exec/sonnet/medium | P3.3 закрыт 🟢: чек места/имени workflow оказался уже реализован (D24/D27/D28), добавлен недостающий `dev-loop.js` exempt — детали см. phases/P3.md P3.3 Completion Notes |
| 2026-07-15 | plan-exec/sonnet/medium | P3.4 закрыт 🟠 (Validation `node --check` структурно не проходит из-за санкционированного P3.1/D10 top-level `return`, предсуществующее): guard args-строки + STOP-сообщение в 5 `dev-loop.js` — детали см. phases/P3.md P3.4 Completion Notes |
| 2026-07-15 | plan-run(manual)/opus/high | P3.5 закрыт 🟢, фаза P3 терминальна (🟠 — P3.1/P3.2/P3.4 deviations): budget-квантификация доставки `workflow-craft` (tier-0=48 ток, CORE 694→742/750 OK), рекомендация канала A=CORE_SKILLS (D6), OQ-3 обновлён — детали см. phases/P3.md P3.5 Completion Notes |
| 2026-07-15 | plan-close(manual)/sonnet/low | Фаза P3 закрыта: Phase Handoff заполнен (агрегат Known Deviations P3.1/P3.2/P3.3/P3.4/P3.5), handoff.md перезаписан (after P3), lint прогнан |
| 2026-07-15 | plan-design/opus | P4 детализирована (3 items = 3 механизма кластеров 3/4) — ТЗ см. phases/P4.md P4.1–P4.3. D12 (OQ-1→вариант B, §3 Routing +Batch/+Review), D13 (граница P4/P5), D14 (адаптивная глубина ревью = принцип); OQ-1 закрыт (снят из open-questions); Обсуждение №2 Resolved, №6 pre-mortem; v0.3.0→0.4.0 |
| 2026-07-16 | plan-run(manual)/opus/high | P4.1 закрыт 🟠 (регенерённые skills.json/budget.md вне Files, паттерн P2.1/P3.1/P3.2): подраздел «Contract-first дизайн-флоу» в plan-protocol §5 (RU+EN) + опц. контракт-блок phase-template + заметки new/Pn plan-design — детали см. phases/P4.md P4.1 Completion Notes |

## 7. Contracts

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| Терминальность TELEMETRY-OPT P4 (правки `anti-drift`) | 2026.07.15-TELEMETRY-OPT (архив) | P4 🟢 | План терминален целиком, архивирован (`plans/archive/2026.07.15-TELEMETRY-OPT`) | Гейт снят — exec PLANFLOW-UX не блокирован |
| Терминальность TELEMETRY-OPT P1.3 (правки `workflow-craft`) | 2026.07.15-TELEMETRY-OPT (архив) | P1.3 🟠 | `workflow-craft` §4.1 (анти-релонч) уже добавлен | P3 здесь строит ПОВЕРХ, не откатывает |

> Гейт снят (донор терминален и архивирован). Был односторонним (§11): PLANFLOW-UX читал
> TELEMETRY-OPT, не правил его.

## Обсуждение

### 1 — Дизайн-флоу: «все фазы вперёд» vs текущий phase-first skeleton

- **(рекоменд.) Вариант A — contract-first гибрид.** Запечатать интерфейсы/контракты между всеми
  фазами вперёд (что каждая потребляет/производит), item-детали — just-in-time. Плюсы: cross-phase
  конфликты видны заранее (запрос Owner), без полной верхней цены дизайна. Минусы: не «100% всё
  детализировано вперёд», как буквально просил Owner.
- **Вариант B — полный upfront-дизайн всех item'ов.** Плюсы: буквально бесконфликтная утверждённая
  схема до старта. Минусы: жжём дизайн на item'ы, что поменяются от ранних фаз; конфликт с recon-грунтовкой.
- **Вариант C — статус-кво (skeleton, детализируем по одной фазе → сразу exec).** Минусы: ровно то,
  на что жалуется Owner (нет общей утверждённой схемы, конфликты всплывают поздно).

**Статус:** Resolved → D5 (Вариант A — contract-first). Механику «глобального exec-плана» проектирует P4.

### 2 — Где живёт «глобальный exec-план с батчами» (артефакт)

- **(рекоменд.) Вариант B — расширить `## 3. Routing`** колонками `Batch`+`Review` (§3 уже несёт
  per-item Items·Model/effort·Exec). Плюсы: минимум механизма, ноль дублей SSOT, §3 = естественный
  «пульт» подфаз; opt-in (легаси-форма валидна). Минусы: §3 из «только отклонения» → «полная доска»,
  многословнее для больших планов. *(Третий вариант, вскрытый при дизайне — не было в исходном OQ-1.)*
- **Вариант A — новый артефакт** `plans/<ID>/exec-plan.md` (таблица: батч · подфазы · команда · модель ·
  effort · ревью-глубина). Плюсы: явный отдельный «пульт». Минусы: дублирует routing/статус items →
  анти-паттерн «второй носитель факта» (§3), риск рассинхрона со Status Board/§3.
- **Вариант C — расширить Status Board / handoff** (колонки батч/команда прямо там). Плюсы: один
  источник. Минусы: Status Board фазового уровня — неверная гранулярность для батчинга подфаз; перегруз.

**Статус:** Resolved → D12 (Вариант B — расширить §3 Routing колонками `Batch`+`Review`). Owner
отказался от вопроса («проектируй, не тупи») → designer взял рекомендацию с обоснованием (D6).

### 3 — Форма `Next` под «заблокировано / time-gate / делать-нечего» (P2.1)

- **(рекоменд.) Вариант A — отдельная структурная форма «ОЖИДАНИЕ: <условие> → <целевая форма>».**
  Условие структурно (дата/гейт), launch-block несёт целевую команду с guard-строкой `# НЕ раньше:`.
  Плюсы: копипастится, честно показывает неисполнимость сейчас, отличима от `🔴 Blocked` (дефект) и
  «план закрыт» (терминал); `plan_lint` резолвит `waiting` + WARNING на прозу-оговорку. Минусы: +1
  форма в enum и +1 канон-литерал (i18n/реестр).
- **Вариант B — переиспользовать `🔴 Blocked` / эскалацию §10.** Плюсы: без новой формы. Минусы:
  семантически неверно — `🔴`/эскалация = ДЕФЕКТ плана (нужен ре-дизайн), а time-gate — здоровое
  ожидание внешнего времени; смешение зашумит доску ложными «блокерами».
- **Вариант C — оставить прозу, только WARNING на неё.** Плюсы: минимум правок. Минусы: не даёт
  копипастящейся альтернативы — автор всё равно пишет прозу, WARNING нечем закрыть (ровно жалоба Owner).

**Статус:** Resolved → D8 (Вариант A). **Pre-mortem (ядро экосистемы):** «через 6–12 мес форма
сломала флот» → причина-1 неаддитивная правка резолва (митигируется правилом «8 форм байт-в-байт
неизменны + waiting ДО exec», Implementation Rules P2.1); причина-2 ложные WARNING C2 на флоте
(митигируется «стем-лист УЗКИЙ + финал по дельте флота §8 D53»); причина-3 RU→EN дрейф литерала
(митигируется i18n-keep + T2, зеркало D28).

### 4 — Launch-block вне `plan-*` (`dev.md`/`fix.md`/ad-hoc) — в scope P2?

- **(рекоменд.) Вариант A — сузить P2 до recon-доказанного (C1/C2/C3), вне-plan-* → OQ-2.** Плюсы:
  не жжём фиксы на недоказанной боли (D2/CLAUDE.md методология); recon показал корень в enum §8, не
  в dev/fix. Минусы: буквальная формулировка скелета «не только из plan-*» сужена (запись — D7).
- **Вариант B — сразу добавить launch-block-финал в `dev.md` (и/или `fix.md`).** Плюсы: закрывает
  буквальную формулировку скелета. Минусы: `dev.md` handoff'ит телеметрией (run-report), `fix.md` —
  терминальная микроправка (launch-block избыточен); боль не измерена recon'ом → спекуляция.

**Статус:** Resolved → D7 (Вариант A — сузить). Часть про `dev.md`/`fix.md` живёт как **OQ-2**
(рекомендация исполнителю: `dev.md` — да при всплытии боли; `fix.md` — exempt как терминал).

### 5 — Pre-mortem рекалибровки ревьюера (P3.1, ядро экосистемы)

Канон workflow-авторинга — ядро экосистемы (весь флот следует ему). «Через 6–12 мес рекалибровка
провалилась» → независимые причины:
- **Причина-1: пере-ослабили — гейт стал беззубым**, плохие workflow проходят (обратка жалобы
  Owner). Митигация: рекалибровка = точечное СУЖЕНИЕ 3 ложных-RED, детекторы относит.путей/read-only/
  форк остаются байт-в-байт (Scope Excluded P3.1); Validation требует RED на синтетике с
  относит.путём / пишущим-аудитом.
- **Причина-2: рассинхрон 3 файлов-канона** (правка в `make-workflow.md`, забыли README/
  `workflow-craft`) → `make-workflow` сам ловит «дрейф от README = дефект». Митигация: Implementation
  Rules «одна формулировка во все 3 источника» + `check-translations` гейт.
- **Причина-3: гейт так и не доставлен** (P3.5 → OQ-3 не резолвится) → рекалибровка академична.
  Митигация: P3.5 квантифицирует + рекомендует, OQ-3 эскалирует Owner'у; доска честно держит A1
  открытым до резолва.

**Статус:** Resolved → митигации в Implementation Rules/Validation P3.1/P3.5 + OQ-3.

### 6 — Pre-mortem P4 (ядро экосистемы: `plan-protocol` ведёт весь флот)

«Через 6–12 мес contract-first/батчинг/адаптивное-ревью сломали флот» → независимые причины:
- **Причина-1: батчинг стал предлогом пропускать ревью на correctness-critical** → плохой код
  проходит (обратка D6). Митигация: D6-инвариант дословно в каноне P4.2/P4.3 — батч наследует
  МАКСИМУМ риска; `full`-классы (correctness/public-contract/tenant/фискалка/канон-флота) НЕ
  сливаются под «пропуск подтверждения» (Implementation Rules P4.2/P4.3).
- **Причина-2: запечатали все фазы → ранняя меняет контракт, поздние скелеты устарели**, никто
  не реопенит (у скелета нет терминального статуса). Митигация: reconcile-правило P4.1 — при
  детализации Pn сверить `Потребляет` с `Производит` закрытых фаз, дрейф → обновить блок + D#
  (дёшево, скелет не терминален).
- **Причина-3: §3 Routing как полная доска раздувается / рассинхрон с items** (item добавили в
  `phases/`, забыли в §3). Митигация: §3-доска — OPT-IN (не обязательна); сверку §3↔items держит
  чеклист `plan-audit`, не машинный ERROR (back-compat §9, `plan-lint` §3 не парсит).
- **Причина-4: риск среза классифицировали неверно** (correctness-баг помечен `none`). Митигация:
  консервативная классификация P4.3 — дефолт `full`, сомнение → `full` (fail-safe как §9);
  `light`/`none` требует явного обоснования в `Почему`.

**Статус:** Resolved → митигации в Implementation Rules/Code Guidance P4.1/P4.2/P4.3 + D12–D14.
