# 2026.07.18-FOREMAN — Artifex: супервизор unattended-исполнения мастер-планов

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.18-FOREMAN |
| Title | Artifex (раб./legacy PLAN-ID FOREMAN) — пакет-супервизор unattended-исполнения мастер-планов (CLI-драйвер + скилл + хуки + раскатка через skm) |
| Version | 0.22.1 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | fable (design pass 1 + P0 + P5); opus (детализация P1–P7; P1 reconcile + foreman→artifex пропагация) |
| Last Updated | 2026-07-25 (P1.4 закрыт 🟠 по git-фактам; открыт P1.5 re-пин; план поставлен в очередь за 2026.07.24-AGENT-RELIABILITY, D49) |
| Repository | swissknifeman |
| Related Packages | task (plan-protocol — потребляемый контракт), skiller (раскатка bucket), harness (agent-packs), maind (репортинг прогонов), botkit (референс TG-бота) |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · opus (design/контракты) |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman (исправлено 2026-07-25: копии в vault Brain нет — `plans/` валта содержит только 2026.07.17-AXIOMA-ORCHESTRA; репо-копия единственная) |
| Paused By | 2026.07.29-HARNESS-AGNOSTIC, 2026-07-29 (ПОГЛОЩЕНИЕ, не пауза: тот план объявил этот `supersedes` — sealed-контракты P0/P1 переиспользуются, пере-скоуп P2–P7 исполняется его фазой P4, архивация — его item P0.3; исторически — 2026.07.24-AGENT-RELIABILITY, 2026-07-25, D49, тот план закрыт 🟠 2026-07-26; ранее — 2026.07.19-DUAL-PROVIDER, 2026-07-19, терминален 🟠) |
| Design Passes | 2/2 — N сокращён 3→2 (D44): прогон 1 = скелеты+контракты+findings; прогон 2 = детализация всех 8 фаз до DoR (форкаст 2–3 сошёлся в один расширенный прогон) + finish. Все 8 фаз детализированы, roadmap собран, дыр finish не выявил |

## 1. Context

Владелец ведёт многофазные мастер-планы в 5+ проектах; исполнение требует почти
круглосуточных ручных подтверждений, хотя 99% ответов — «да». Длинные Workflow-марафоны
(FLEX-2) переполняют контекст оркестратора → остановлены. Решение: **Artifex** — пакет в
SKM: CLI-драйвер гоняет каждый item плана свежей headless-сессией
(`claude -p "/task:plan-exec Pn.m" --output-format json`), парсит handoff/JSON,
решает next/retry/escalate; спорное → Telegram; философия владельца — в декларативном
policy-файле per project (он же opt-in маркер). Верифицировано (RAG:✅ 2026-07-18,
`findings/headless-claude-code-factsheet-2026-07-18.md`): `-p` грузит скиллы/хуки/CLAUDE.md
как интерактив — тулинг владельца работает; AskUserQuestion в headless denied → эскалация
только через handoff. Утверждение планов (design) остаётся человеческим — автоматизируется
exec-волна после «Утверждено». Artifex ≠ maind: execution vs память/граф, но прогоны
репортятся в память mAInd.

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
- Дом плана — vault SKM (`Home: brain`), синк с репо — штатный `brain sync`; код пакета —
  `~/projects/packages/swissknifeman/packages/artifex/` (имя подтверждается P0.1).
- Детализация фаз (design pass 2) — в сессиях из репо SKM, по одной фазе на заход
  (`/task:plan-design 2026.07.18-FOREMAN Pn`).
- **Модель design-заходов:** дефолт команды — Opus/high; для несущих заходов владелец
  запускает сессию-оператора под **Fable** (прецедент fable-window): P0 (контракты),
  P5 (прогресс-движок/rulebook), P7.3 (стратегический канон), `finish`; P1–P4, P6 —
  Opus достаточно. Фактическую модель захода фиксировать в Meta `Authoring Model`.
- Перед кодом драйвера — контракты P0 закрыты (contract-first, фазы P1–P4 их потребляют).
- Внешние факты о CC (флаги, хуки, режимы) — только RAG:✅ по first-party доке; факт-лист
  в findings первичен, при конфликте — перепроверка, не память модели.
- **Perplexity-факты не финальны (D19).** Прецедент 2026-07-18: Perplexity ложно отрицал
  существование 3 из 4 реальных реп (gstack 122k★, last30days 52k★, codex-plugin-cc —
  официальный OpenAI). Правило детализации: ЛЮБОЙ Perplexity-факт, влияющий на контракт/
  код/вердикт, перед запечатыванием перепроверяется первоисточником: существование и
  метаданные реп — ТОЛЬКО GitHub API (`api.github.com/repos/...`), поведение CC — только
  first-party дока, README/код — прямым чтением. Неперепроверенный Perplexity-факт в
  несущей позиции = `[UNVERIFIED]` и не может закрывать item.
- Драйвер не редактирует планы содержательно — это делают воркеры по план-протоколу;
  драйвер только читает статусы/handoff и пишет свой журнал прогона.
- Секреты (TG token) — только env, не в конфиги/settings.

## 3. Routing

| Items | Model/effort | Exec | Почему |
|:--|:--|:--|:--|
| P0.1–P0.4 | opus/high | manual | контракты/схемы/research — design-работа |
| P0.5 | sonnet/medium (экстракция fan-out haiku/sonnet, синтез opus) | manual | майнинг истории дешёвыми моделями по директиве владельца; синтез/классификация — старшей; финал — утверждение владельцем |
| P0.6 | opus/high | manual | схема run-folder/мандата — контрактная design-работа |
| P1.1–P1.2 | opus/high | manual | схемы журнала/индекса — правка канона плановой системы |
| P1.3–P1.4 | sonnet/high | manual | contribution в пакет task (скиллы команд + plan-lint) — нужен обзор владельца |
| P1.5 | sonnet/high | manual | re-пин parse-контракта P0.2 + построчная сверка четырёх якорей §1–§4; вердикт breaking/non-breaking не выводится дешёвой моделью |
| P2.1 | sonnet/medium | plan-exec | механический каркас пакета |
| P2.2–P2.5 | sonnet/high | manual | ядро драйвера: state machine, defensive parsing, crash recovery — нужен обзор владельца |
| P3.1–P3.2 | sonnet/medium | plan-exec | шаблоны settings/hooks по готовой схеме P0 |
| P3.3 | opus/high | manual | авторинг скилла supervisor-protocol — несущие директивы |
| P4.1–P4.2, P4.4 | sonnet/medium | plan-exec | хук-скрипты + репортинг по контрактам |
| P4.3 | opus/high | manual | Layer 3 remote-approve — security-поверхность |
| P5.1–P5.4 | opus/high | manual | модель прогресса/rulebook — несущий дизайн, наращивается с владельцем |
| P6.1 | sonnet/high | manual | пак в harness agent-packs + профиль skiller — contribution в чужой пакет + config-home fork (OQ-6), обзор владельца |
| P6.2 | sonnet/medium | plan-exec | доки пакета по готовым контрактам/механизмам |
| P6.3 | opus/high | manual | боевой unattended-пилот + синтез вердикта/экономики — оценка + гейт владельца (аудит decision-лога) |
| P7.1–P7.2 | sonnet/medium (fan-out дешёвыми, синтез opus) | manual | аудит/анализ практики — сессии BRAIN, не SKM |
| P7.3–P7.4 | opus/high | manual | стратегический канон + скиллы хаба — несущий контент, утверждает владелец |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Контракты и дизайн-основа | 6/6 | 🟢 Done |
| P1 | Журнал исполнения плана + корневой индекс (расширение plan-protocol) | 3/5 | 🟡 In progress |
| P2 | CLI-драйвер (fresh-session цикл) | 0/5 | ⬜ Not started |
| P3 | Unattended-профиль (permissions + скилл) | 0/3 | ⬜ Not started |
| P4 | Эскалация и наблюдаемость (TG + mAInd) | 0/4 | ⬜ Not started |
| P5 | Прогресс-движок и решения супервизора | 0/4 | ⬜ Not started |
| P6 | Раскатка и пилот | 0/3 | ⬜ Not started |
| P7 | Стратегический канон Brain (самодостаточная читаемость хаба) | 0/4 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-18 | Межфазный драйв — супервизор + fresh `claude -p` per item; Workflow остаётся только для fan-out внутри одной стадии | Опыт FLEX-2 (стоп марафона по утечке токенов, память mAInd) + консенсус-паттерн «externalize state, minimize session reuse» (RAG:✅ 2026-07-18, `findings/perplexity-supervisor-patterns-2026-07-18.md`) |
| D2 | 2026-07-18 | Reuse-гейт: Cowork (скрин-скрейпинг TUI) и Claude Coder (cloud, не видит локальные скиллы/хуки) отвергнуты; нативные `--bg`/`/goal`/routines — недостаточны (не читают handoff план-протокола, routines без локальных хуков) → build-new оправдан; драйвер СТРОИТСЯ поверх нативного `claude -p` | `-p` грузит скиллы/хуки/CLAUDE.md как интерактив (RAG:✅ 2026-07-18, факт-лист §1, §6); формальный прогон ecosystem-reuse-gate — P0.1 |
| D3 | 2026-07-18 | «99% да» решается политикой, не человеком: allowlist + permission-mode + PreToolUse `permissionDecision:allow`; AskUserQuestion в headless denied → канал эскалации воркера = handoff (ATTENTION/Escalation Needed) | RAG:✅ 2026-07-18, факт-лист §2–3 |
| D4 | 2026-07-18 | Граница: Artifex = execution-оркестрация, mAInd = память/граф; каждый прогон Artifex репортит факты (фаза закрыта, стоимость, ATTENTION) в память mAInd | Директива владельца (бриф §Решение) + канон «связь с mAInd — приоритет №1» (repo-grounded: CLAUDE.md Brain, RAG:— (repo-grounded: CLAUDE.md §⚠ ПРИОРИТЕТ №1)) |
| D5 | 2026-07-18 | Opt-in = наличие policy-файла проекта (схема — P0.3); философия владельца («чисто, breaking ok, спорное → ATTENTION») — в policy/скилле, не в коде драйвера | Бриф: выборочное использование; один драйвер — разные политики |
| D6 | 2026-07-18 | TG-эскалация: MVP = Layer 1 notify-only (Stop/Notification/SessionEnd + сообщения драйвера); Layer 3 (TG command inbox + PermissionRequest `defer` + Agent SDK resume) — отдельный опциональный item P4.3 с sender allowlist / audit log | Remote control = admin surface (RAG:✅ 2026-07-18, `findings/perplexity-telegram-hooks-2026-07-18.md`) |
| D7 | 2026-07-18 (финализирован P0.4) | **ПЕРЕВЁРНУТ:** `--max-turns` СУЩЕСТВУЕТ и работает (2.1.214, live exec exit 0/num_turns:1) + `--max-budget-usd` — драйвер лимитит ходы/стоимость штатными флагами `claude -p` (P2 worker-запуск, P5 cost-aware), а `timeout`/retry-лимиты — сверху. Прежний вывод «считать несуществующим» отменён (промах grep help, не отсутствие флага) | P0.4: локальный exec 2.1.214 (session eda9aad3) + cli-reference.md Resource&Turn Limits; findings/headless-uncertainties-resolved §4 |
| D8 | 2026-07-18 | Журнал исполнения — ОТДЕЛЬНЫЙ append-only файл per plan (+ корневой индекс плана), НЕ handoff: handoff остаётся перезаписываемым снапшотом «куда дальше», журнал — неизменяемой историей «что запускалось, с какими трениями, с каким результатом»; запись всеми запусками /task:plan-*, не только Artifex | Уточнение владельца 2026-07-18 (`brief/01-refinements.md` §1): сессии CC не сопоставимы с планом; разные файлы — разный анализ; решение о разделении делегировано и принято |
| D9 | 2026-07-18 | Фазы перенумерованы (все были скелетами): журнал+индекс = P1 (ДО драйвера — драйвер его потребляет); прогресс-движок + лог решений супервизора = P5; старые P1–P4 → P2–P4, P6. Расширение канона плановой системы — через package-contribution-protocol в пакет task | Уточнение владельца (`brief/01-refinements.md`); contract-first: производитель раньше потребителя |
| D10 | 2026-07-18 | Решения самого супервизора логируются (P5.4: сигналы → правила → вердикт → обоснование); правила прогресс-оценки — наращиваемый rulebook с утверждением новых правил владельцем (P5.3); стартовая политика консервативна: сомнение → эскалация | Уточнение владельца (`brief/01-refinements.md` §2): супервизор должен быть проверяем, иначе сам чёрный ящик |
| D11 | 2026-07-18 | Иерархия супервизоров — как РЕКУРСИЯ одного Artifex, не отдельная сущность: корневой инстанс (Brain) гоняет оркестр-план экосистемы (сингтон AXIOMA-ORCHESTRA), item «проект X до стадии Y» = запуск дочернего Artifex на плане проекта; «доклад» = журнал+handoff ребёнка, читаемые тем же контрактом P0.2. Требование композируемости — в контракты СЕЙЧАС (P0.2: схема читаема на любом уровне); включение корневого уровня — v2 ПОСЛЕ пилота P6.3 | Уточнение владельца (`brief/01-refinements.md` §3); каскадная автономия умножает ошибки/стоимость — сначала доверие на одном проекте; инфраструктура (журнал per plan, граф mAInd) уже композитна |
| D12 | 2026-07-18 | Каналы эскалации — канал-агностик слой (интерфейс notify+inbox, адаптеры), MAX first-class наравне с TG; несколько активных каналов параллельно → единый inbox с дедупликацией ответов; блокирующий Q&A «100% понимание»: выжимка конфликта → полный ответ владельца (супервизор вправе доспросить) → только затем резюм; ответ фиксируется в артефактах плана | RAG:✅ 2026-07-18 `findings/perplexity-max-messenger-channels-2026-07-18.md`: MAX Bot API официально есть, НО iOS-пуши MAX сломаны (делистинг App Store), а TG в РФ замедляется/идёт к блокировке — ни один канал не надёжен, абстракция обязательна |
| D13 | 2026-07-18 | Стартовые правила супервизора НЕ декларируются — добываются майнингом истории планов (P0.5, дешёвые модели-экстракторы + opus-синтез): каталог принципов с классификацией «межпроектное/концептуальное (FlexCRM↔CoreX-класс, нестабильные контракты) → согласование» vs «внутрипакетное чистое улучшение (fluent API, расширяемость, конфигурируемость, надёжность) → свободно»; мета-принцип владельца: идеальные системы — главный козырь, улучшение качества не блокируется; каталог утверждает владелец, затем он — seed P0.3/P3.3/P5.3 | Уточнение владельца (`brief/01-refinements.md` §5); граница пакет↔экосистема опирается на package-contribution-protocol, майнинг калибрует пороги практикой |
| D14 | 2026-07-18 | Стратегический канон экосистемы — отдельная фаза P7 в Brain (хаб): аудит читаемости → описание фактической практики разработки → самодостаточный канон в 02-Knowledge/00-Strategy (философия, взаимосвязи, вектор, принципы; glossary/tech radar связываются, не дублируются) → Brain-скиллы доступа (указатель-паттерн ecosystem-map). Потребители: корневой супервизор (контекст для D11) И прямые CC-сессии; исполняется в сессиях Brain, а не SKM; локальные планы остаются в проектах | Уточнение владельца (`brief/01-refinements.md` §6): Brain = узловой хаб стратегии, существующие артефакты недостаточно самодостаточны |
| D15 | 2026-07-18 | Принят консолидированный Deep Research аудит владельца (3 стадии, `findings/owner-deep-audit-skills-2026-07-18.md`, RAG:✅ 2026-07-18) — обязательный Input детализации фаз. Несущие вердикты: (а) драйвер P2 — ADAPT ralph-orchestrator (внешний демон с персистентным состоянием) + claude-session-driver (JSONL event-log, таймаут-деградация), reuse harness run-report `_lib.py`/`_usage.py` («1 сессия = 1 item = 1 run-report» решает привязку), парсер формата плана — с нуля; (б) КРИТИЧНО: upstream-баги CC #49525/#39973 — permission-mode НЕ переключать хуком, только флагом `--permission-mode` при запуске + проверка версии CLI; модель/effort изнутри сессии не переключаются (first-party); (в) P3 — harness auto-approve РАСШИРЯТЬ, не заменять; defrex/permission-policy ВЗЯТЬ после code-audit (3★); таймаут-деградация по severity из policy (критичное — вечная блокировка, рутина — safe-действие); (г) P4 — MAVII-RU/max-messenger-plugin (MIT) ВЗЯТЬ как MAX-канал, blocking-паттерн из claude-tg headless-адаптацией, единый escalation envelope (plan_id/item_id/severity/options/timeout_action) поверх каналов; (д) P5 — детекция как машина состояний переходов mem0-таксономии (ADD/UPDATE/NOOP/CONFLICT за N итераций) + дуальное exit-условие ralph-claude-code + cost-aware сигнал `_usage.py` + двухступенчатая проверка plan-audit-loop; (е) P1/P6 — журнал: референсы beads (DAG/gate) + event-JSONL; раскатка = оформить Artifex как agent-pack существующего harness-механизма (upgrade-drift бесплатно); (ж) soft/hard эскалация по DAG-зависимостям items; policy-версия синхронно с версией плана | Аудит владельца по промпту сессии; согласуется с pre-audit; остаточные проверки (LICENSE claudewatch, code-audit defrex, детали MAX API) — точечно в заходах детализации фаз через context7/github/perplexity |
| D16 | 2026-07-18 | Run-folder канон запусков супервизора (по аналогии с plans/): каждый запуск = `runs/<ГГГГ.ММ.ДД-КОД>/` с `brief/00-mandate.md` (мандат владельца: скоуп фаз «P1» / «P1–P5», права, ограничения — подробный промпт делегирования, записанный В ЗАПУСК), `state.json` (на каком item/этапе, счётчики попыток), `journal.jsonl` (append-only событийный лог прогона), отчёты. Resume — командой «продолжай <ПАПКА>» по папке, НЕ по session id (сессии эфемерны, папка durable, переживает ребут). Разграничение хранилищ: сиюминутный state прогона — ТОЛЬКО run-folder; mAInd — только итоговые факты (фаза закрыта, стоимость, ATTENTION), уточняет D4. Разграничение скоупов: policy-файл = per project (постоянная политика), мандат = per запуск (временная зона ответственности); мандат не может расширять policy, только сужать | Уточнение владельца (`brief/01-refinements.md` §7); RAG:✅ 2026-07-18 `findings/perplexity-supervisor-runtimes-2026-07-18.md` — паттерн подтверждён индустрией (Ralph workspace-state, Gas Town beads/hooks resume не по сессии) |
| D17 | 2026-07-18 | Готовые куски для супервизор-рантайма: (а) layout Ralph orchestrator (`events-*.jsonl`, `tasks.jsonl`, termination-контур) — ШАБЛОН структуры run-folder; его эвристика «output similarity ≥90% = разрыв цикла» — в P5.1; (б) Gas Town (MIT, ~15k★) — референс иерархии ролей/зон (Witness ≈ проектный Artifex, Deacon ≈ корневой) для D11, целиком НЕ брать (свой тяжёлый мир, у нас SSOT = plan-protocol); (в) Claude Code Tasks (first-party): `~/.claude/tasks` durable, DAG «blocked by», `CLAUDE_CODE_TASK_LIST_ID` шарит список между сессиями — кандидат на очередь items драйвера, проверка формата/стабильности по first-party доке в P0.4; готовой связки «resume-by-folder + декларативный мандат» нет ни у кого — строим свою (P0.6 схема, P2.5 реализация) | RAG:✅ 2026-07-18 `findings/perplexity-supervisor-runtimes-2026-07-18.md`; детали (лицензия Ralph, формат tasks) — first-party перепроверка в P0.4 |
| D18 | 2026-07-18 | Quota-resilience: исчерпание лимита учётки — ТРЕТИЙ класс сбоя (quota ≠ transport ≠ semantic) со своей веткой: детект limit-ошибки → graceful-пауза очереди (state в run-folder, ничего не падает) → классификация типа лимита: 5-часовое окно → ЖДАТЬ (таймер до сброса, авто-резюм, учётку не менять — директива владельца) / недельный или неизвестный → URGENT-эскалация во все каналы (MAX/TG, «ночной» приоритет — будить) с пошаговой инструкцией смены учётки (браузер: logout → login следующей; CLI подхватывает после перезапуска); после перелогина — «продолжай <папка>», прерванный item свежей сессией. Смена учёток — вручную (v1); квота-события пишутся в journal + учёт какая учётка активна (если детектируемо). Формат limit-ошибок в `-p` (как отличить 5h от weekly, есть ли reset-timestamp) — `[UNVERIFIED]`, снять в P0.4 | Уточнение владельца (`brief/01-refinements.md` §8): 2–3 учётки Max 20x, исчерпание за 2–3 дня длинных задач; ночные уведомления обязательны |
| D19 | 2026-07-18 | Дисциплина верификации Perplexity: каждый Perplexity-факт в несущей позиции перед запечатыванием контракта/вердикта подтверждается первоисточником (репы — только GitHub API, поведение CC — только first-party дока, код — прямое чтение README/файлов); неподтверждённый = `[UNVERIFIED]`, item не закрывается. Действующие findings с Perplexity-происхождением (supervisor-patterns, telegram-hooks, max-messenger-channels, supervisor-runtimes, части owner-deep-audit) при детализации СВОЕЙ фазы проходят точечную first-party сверку несущих утверждений | Прецедент владельца 2026-07-18: Perplexity ложно отрицал существование 3 из 4 реальных реп (gstack 122k★, last30days 52k★, официальный openai/codex-plugin-cc) — галлюцинации возможны в обе стороны («есть» и «нет») |
| D20 | 2026-07-18 | Формат пер-планового журнала (P1.1) — `plans/<ID>/journal.jsonl` (append-only NDJSON) как канонический машинный формат; человекочитаемый вид генерируется по запросу (`plan-lint`/хелпер), НЕ хранится отдельным файлом. Отвергнуто: MD-таблица (плохо парсится супервизором, merge-конфликты при append из параллельных сессий), NDJSON+хранимый MD (двойной носитель факта → дрейф, запрет §3). Выбор обоснован reuse-мандатом (run-report JSON, `_lib.py` парсит JSONL) + согласованностью с run-folder `journal.jsonl` P0.6 | RAG:— (repo-grounded: harness run-report README I/O-контракт + P0.6 контракт run-folder); брифо-уточнение §1 (журнал ≠ handoff, отдельный анализ) |
| D21 | 2026-07-18 | Механизм записи журнала (P1.3) — ПЕРВИЧНО инструкция в close-протоколе команд `/task:plan-*` (детерминированная точка: bookkeeping-коммит уже пишет файлы плана — запись журнала туда же), через хелпер `lib/task/journal.py` (schema-корректный append, не сырой JSONL моделью). Хук SessionEnd — BACKSTOP для не-само-закрывающихся/упавших прогонов (owner-review в P1.3, MVP работает и без него). Отвергнуто: hook-only (plan_id/item_id из транскрипта — эвристика, ненадёжно), instruction-only без хелпера (модель пишет битый JSONL) | RAG:— (repo-grounded: plan-exec.md close-протокол пишет bookkeeping + task CLAUDE.md stdlib-хелперы) |
| D22 | 2026-07-18 | Lint-гейт журнала (P1.4) — WARNING для всех существующих/legacy планов, ERROR ТОЛЬКО для новых датовых планов от cutoff-даты (паттерн бриф-гейта 2026.07.16): жёсткий гейт сразу сломал бы все in-flight планы флота (FLEX-2, COREX-CORE, EDUFY). Bootstrapping: сам план 2026.07.18-FOREMAN бэкфиллит свой journal.jsonl ДО перевода гейта в ERROR | RAG:— (repo-grounded: plan_lint.py brief-гейт по дате + task CLAUDE.md «plan_lint = SSOT схемы»); pre-mortem P1 риск №2 (canon-fleet breakage) |
| D23 | 2026-07-18 | Корневой индекс плана (P1.2) — `plans/<ID>/index.md`, карта ФАЙЛОВ и провенанс-связей (какие findings/research питают какую фазу), НЕ носитель статуса/контента (статус — Status Board, «где мы» — handoff): анти-второй-носитель (§3). Рекомендация — авто-генерируемый из дерева файлов + frontmatter (устраняет дрейф). Отвергнуто: hand-maintained индекс, дублирующий Status Board (гарантированный рассинхрон) | RAG:— (repo-grounded: plan-protocol §3 запрет второго носителя факта); бриф-уточнение §1 п.17 |
| D24 | 2026-07-18 | Контракт согласования журналов: пер-плановый `journal.jsonl` (P1.1) и run-folder `journal.jsonl` (P0.6) делят общие поля (ts, plan_id, item_id, command, result, session_id, run_id) — run-folder = сырой событийный лог ОДНОГО прогона супервизора, пер-плановый = консолидированная история ПЛАНА (одна запись на исполнение item, из всех сессий, ручных и Artifex). Artifex-прогон пишет в ОБА (свой run-folder + append в пер-плановый); ручной `/task:plan-*` — только в пер-плановый. Связь через plan_id+run_id+session_id | RAG:— (repo-grounded: P0.6 контракт run-folder journal + D8); reconcile contract-first (§5) P1↔P0.6 |
| D25 | 2026-07-18 | Язык драйвера — **Python stdlib**, раскладка пакета — зеркало `skiller` (`bin/artifex` bash-лаунчер → `python3 -m artifex` + `lib/artifex/` + `scripts/validate.sh` + `tests/` + `.claude-plugin/plugin.json` + `CLAUDE.md`). Отвергнуто: Rust (как ralph-orchestrator). Причина reuse: cost/turns из `_usage.py`, форензика транскрипта из `_lib.py` — обе Python (порт на Rust против reuse-гейта); конвенция SKM — все пакеты (task/skiller/maind) stdlib-only. ralph-orchestrator (Rust) — АРХИТЕКТУРНЫЙ референс (внешний демон + персистентный state), не донор кода | RAG:— (repo-grounded: `packages/harness/.../run-report/_usage.py`+`_lib.py` Python; `packages/task/scripts/validate.sh` stdlib; `packages/skiller/bin/skiller`+`lib/skiller/` — образец CLI-пакета); reuse-мандат D15а |
| D26 | 2026-07-18 | Владение записью журнала (reconcile D24): пер-плановый `journal.jsonl` пишет **воркер** (close-протокол plan-exec, хелпер `lib/task/journal.py`, P1.3) — одна запись на исполнение item; run-folder `journal.jsonl` пишет **драйвер** (событийно, P0.6). Линковка: драйвер инъектит `run_id` в env воркера (`ARTIFEX_RUN_ID`) → воркерская запись несёт run_id (P1.1 поле nullable: ручной → null, Artifex-порождённый → set). Драйвер БЭКФИЛЛИТ пер-плановую запись ТОЛЬКО когда воркер упал до close-протокола (crash/timeout/quota-abort → result=blocked/escalated), чтобы история плана не имела дыр — единственный случай прямой записи драйвером в пер-плановый (роль backstop-хука D21, исполняемая супервизором). Так D24 «пишет в оба» соблюдается без двойной записи одной строки | RAG:— (repo-grounded: research/01-p2-driver-architecture.md §2 + P1.1 run_id nullable + P1.3 close-протокол); reconcile contract-first (§5) P2↔P1.1/D24 |
| D27 | 2026-07-18 | Скоуп авто-драйва MVP: драйвер авто-ведёт ТОЛЬКО формы `**Next:**` `/task:plan-exec` (DRIVE) и `/task:plan-close` (механический self-contained close); `/task:plan-run`, `/task:plan-audit`, `/task:plan-design`, «ЗАПУСК ВРУЧНУЮ» → пауза+эскалация владельцу; «ОЖИДАНИЕ» → таймер до условия; «план закрыт» → done. Скоуп-гейт мандата: Next в фазе вне мандата → стоп («мандат исчерпан»). Soft/hard-параллелизм по DAG (idea #1 owner-deep-audit) — P5, не MVP; набор авто-драйв-форм конфигурируем через policy P0.3, дефолт консервативен | RAG:— (repo-grounded: research/01 §3 решающая таблица + D10 «сомнение → эскалация»); supervisor-patterns §Двухуровневый retry |
| D28 | 2026-07-18 | Permission-mode unattended-профиля (P3.1) задаётся ФЛАГОМ `--permission-mode` при запуске `claude -p` (worker P2.2), НЕ хук-переключением; baseline = `acceptEdits` (edit-capable для plan-exec/plan-close; авто-approve правок+безопасных fs, сеть/прочий Bash → PreToolUse-хук P3.2), read-only ветви лестницы (tier2 анализ, dry-run) → `plan`; bypassPermissions НЕ дефолт ни в одном профиле. Отвергнуто: dontAsk+широкий allowlist (allowlist растёт неконтролируемо), bypassPermissions (circuit breaker + баг #49525 молча деградирует, security-дыра unattended) | Upstream-баги CC #49525 (`bypassPermissions` в ответе хука молча отбрасывается с 2.1.110+ → acceptEdits) / #39973 (ExitPlanMode сбрасывает режим) — RAG:✅ 2026-07-18 (findings/owner-deep-audit §2.1); воспроизводимость на текущем CLI — снимается P0.4 |
| D29 | 2026-07-18 | PreToolUse policy-хук (P3.2) РАСШИРЯЕТ harness auto-approve (AST-разбор компаунд-команд oryband: каждая под-команда `$(...)`/subshell отдельно), НЕ заменяет/дублирует; решение ДЕТЕРМИНИРОВАННОЕ — БЕЗ AI-гейткипера (конвенция SKM: harness сознательно отклонил froggeric stage-2 AI); вне явного правила policy → deny/ask (эскалация P4), НИКОГДА silent allow; defrex/permission-policy — паттерн декларативности ВЗЯТЬ после code-audit+LICENSE (P0.4), не код при несовместимости | D15в (harness extend, defrex после аудита); детерминизм — RAG:— (repo-grounded: harness auto-approve CREDITS отклонил stage-2 AI); fail-safe security (unattended-агент) |
| D30 | 2026-07-18 | Reconcile P3↔P0.3 (contract-first §5): permission-mode-per-тип-запуска (P3.1) и severity-теги правил (P3.2) — artifex-shipped дефолты; policy P0.3 может override тем же механизмом, что model routing overrides. P0.3-схема не перечисляет эти поля явно → при exec/детализации P0.3 добавить опциональные `permission_mode override` + `rule severity`; расхождение фиксируется reconcile-ожиданием, НЕ молчаливой подгонкой одной из схем | P3 потребляет P0.3, но override-поля в P0.3 Scope явно не названы; RAG:— (repo-grounded: P0.3 «model routing overrides» — тот же override-механизм; §5 reconcile contract-first) |
| D31 | 2026-07-18 | Канал-агностик слой notify (P4.1) — Python stdlib HTTP-адаптеры (`urllib`, POST `sendMessage`) для TG и MAX; MAVII-RU/max-messenger-plugin (TS/Bun MCP, MIT) и claude-tg — референсы для P4.3 inbox (Layer 3), НЕ импортируются в stdlib-пакет; при заимствовании MAX-inbox как MCP-канала он ОТДЕЛЬНЫЙ процесс, не код пакета. Отвергнуто: тащить TS-плагин в Layer 1 (нарушает stdlib-конвенцию D25, добавляет Bun-зависимость ради notify, который тривиален на `urllib`) | Layer 1 notify — HTTP `sendMessage` (RAG:✅ 2026-07-18, findings/perplexity-max-messenger §MAX + perplexity-telegram-hooks §Layer 1); конвенция пакета stdlib-only (RAG:— repo-grounded: D25); плагин ценен интерактивным inbox (P4.3), не notify |
| D32 | 2026-07-18 | Единый escalation envelope (P4.1 `channels/envelope.py`) поверх всех каналов: `plan_id`, `item_id`, `session_id`, `severity`, `kind`, `text`, `options[]`, `timeout_action`, `context{plan_title,cost_usd,reason,resume_cmd}`; адаптеры TG/MAX — transferers конверта (рендер под транспорт), НЕ своя семантика вопроса на канал. Потребители: P4.2 (драйверная эскалация), P4.3 (inbox). Отвергнуто: формат вопроса на каждый канал (дублирование логики эскалации) | RAG:✅ 2026-07-18 (findings/owner-deep-audit §Часть4 идея 2/D15г: единый JSON-конверт вместо логики-на-канал — прямое расширение MCP-паттерна MAX + hook-контракта claude-tg) |
| D33 | 2026-07-18 | Эскалация драйвера MVP (P4.2) — ОДНОУРОВНЕВАЯ пауза очереди на эскалацию (ATTENTION/RED/retry-исчерпан/URGENT → notify + пауза state + резюм по `artifex continue`); soft/hard-параллелизм эскалаций по DAG (owner-deep-audit идея 1) — P5, НЕ MVP (D27). Severity→таймаут-деградация — из policy P0.3 (критичное → `timeout_action=block` навсегда до ответа; рутина → короткий таймаут → безопасное действие skip/retry, НИКОГДА `allow`); severity-теги — artifex-дефолты, policy override (D30) | RAG:✅ 2026-07-18 (findings/owner-deep-audit §Часть4 идея 3/D15в: таймаут функцией severity, критичное = блок навсегда, рутина = safe-action не allow); MVP одноуровневый — RAG:— (repo-grounded: D27 soft/hard = P5) |
| D34 | 2026-07-18 | OQ-5 resolved: доставка эскалаций = fan-out во все активные каналы в порядке из policy (P0.3); best-effort (падение канала → следующий); при ПОЛНОЙ недоставке во все каналы → пауза очереди + сохранение state (fail-safe: unattended НЕ продолжает следующий item, если владелец не оповещён); web-push/email — будущие резервные адаптеры (интерфейс `Channel` их допускает, MVP — TG+MAX) | RAG:✅ 2026-07-18 (findings/perplexity-max-messenger §Проекция: оба канала ненадёжны по-своему → канал-агностик слой + резерв; D12); fail-safe при недоставке — RAG:— (repo-grounded: D6 «спорное решает человек» — без оповещения не ехать) |
| D35 | 2026-07-18 | Репортинг прогонов в mAInd (P4.4) — драйвер публикует ТОЛЬКО итог-факты (item/фаза закрыт, 🟢/всего, стоимость из журнала P1.1, ATTENTION) через канон shared-memory (демон mAInd `maind memory store`/MCP), scope проекта-полигона; сиюминутный state (счётчики попыток, пауза) остаётся в run-folder (D4/D16 разграничение). Источник факта — журнал P1.1 (SSOT истории), не повторный парсинг plan.md; идемпотентность (dedup plan_id+item/фаза); недоступность демона → лог+Pending, не падение item'а; maind не правится | RAG:— (repo-grounded: D4 execution-vs-память + CLAUDE.md §⚠ ПРИОРИТЕТ №1; D16 итоги→mAInd/эфемерное→run-folder; скилл system:shared-memory — swappable backend, канон store) |
| D36 | 2026-07-18 | Модель прогресса (P5.1) — МНОГОСЛОЙНАЯ детекция, не одна эвристика: слой A машина состояний mem0-таксономии (каждая итерация → ADD/UPDATE/NOOP/CONFLICT по дельте friction/result журнала P1.1; вердикт по ПАТТЕРНУ переходов за N итераций в кольцевом буфере, не по единичной метке) + слой B cost-aware (рост cost_usd по попыткам = патология, независим от контента, reuse `_usage.py`) + слой C output-similarity (схожесть текстов handoff ≥ порога → цикл; порог tunable, `[UNVERIFIED]` до калибровки P6.3) + слой D дуальное exit-условие (финал требует сходимости A И терминального статуса 🟢/🟠). Двухступенчатость: дешёвый детерминированный скан (A/B/C без модели) → дорогой вердикт только при stalling/unclear. Вердикт enum {progressing, stalling, unclear} | RAG:✅ 2026-07-18 (findings/owner-deep-audit-skills §Функция2 идеи 4/5 + §Часть4 п.3/4: mem0 машина состояний, cost-aware `_usage.py`, дуальное exit ralph-claude-code, двухступенчатость plan-audit-loop); слой A над журналом — RAG:— (repo-grounded: research/02-p5-progress-engine.md §1 + P1.1 поля) |
| D37 | 2026-07-18 | Граница retry.py (P2.3) ↔ прогресс-движок (P5): retry = ИСХОД одного прогона (transport/semantic/quota), движок = ТРЕНД серии прогонов item/фазы (attempt/friction-история); движок НАД retry-петлёй, ловит stalling там, где каждый прогон «успешен» как run, но фаза не сходится (цепочка RED-аудитов). Решающая логика P5.2: progressing→continue (в пределах attempt-cap policy); stalling→**point-fix = эскалация-с-предложением** (envelope несёт КОНКРЕТНОЕ: сузить scope/сплит/стоп) + пауза, применяет владелец/plan-design; unclear→escalate (D10). point-fix в MVP НЕ автономная правка (инвариант P2: драйвер только читает; автономный plan-design на правку — v2 после пилота, D27 «plan-design→escalate»). Пороги — из policy P0.3 | RAG:— (repo-grounded: research/02-p5-progress-engine.md §2 + P2.3 retry классы + инвариант P2 read-only + D27/D33 MVP одноуровневая эскалация) |
| D38 | 2026-07-18 | Rulebook (P5.3) — наращиваемый ДЕКЛАРАТИВНЫЙ артефакт, не хардкод в progress.py: формат правила (id, condition над сигналами P5.1, verdict/action, severity для P4.2, provenance принцип-P0.5/инцидент, version); дом как severity (D30) — artifex-shipped baseline (`packages/artifex/rulebook/`) + per-project override через policy P0.3; стартовый набор КОНСЕРВАТИВЕН (сомнение→эскалация), СИД из утверждённого каталога P0.5; процесс пополнения — кандидат из разбора инцидента (maind:analyze/session-observer) → ГЕЙТ владельца → в набор; движок ЧИТАЕТ rulebook (правил в коде нет). Правило без provenance — валидатор отклоняет | RAG:— (repo-grounded: research/02-p5-progress-engine.md §3 + D30 override-механизм + P0.5 каталог + скилл package-contribution-protocol бинарная граница); источники кандидатов — repo-grounded (скиллы maind:analyze, system:session-observer) |
| D39 | 2026-07-18 | Лог решений супервизора (P5.4) — обогащённое `decision`-СОБЫТИЕ run-folder journal (P0.6), НЕ третий файл: поля signals (метрики P5.1) / applied_rules (id P5.3) / verdict / rationale поверх общих P0.6 (ts/plan_id/item_id); пишется через `run_folder.append_event` (reuse P2.4). Отвергнуто: (а) отдельный per-plan файл (решения привязаны к ПРОГОНУ, не к плану); (б) отдельный `decisions.jsonl` в run-folder (дублирует событийный носитель P0.6 → дрейф, §3). Аудируемость: run-folder durable (D16). §7 Exported-строка decision-лога = decision-подмножество run-folder journal + прогресс-поля; reconcile с P0.6 (supersedes при расхождении) | RAG:— (repo-grounded: research/02-p5-progress-engine.md §4 + P0.6 событийная схема несёт `decision` + D16 run-folder durable + §3 анти-второй-носитель) |
| D40 | 2026-07-18 | Раскатка Artifex (P6.1) — РЕЮЗ зрелого механизма `harness agent-packs`, без своего версионирования: (а) новый пак `artifex` в `packages/harness/configs/claude-code/agent-packs/artifex/` (pack.json + шаблоны хуков P3.2/P4.1 + settings-фрагмент P3.1 + CHANGELOG; provenance-header, lock `.claude/agent-pack.lock.json`, upgrade/drift/remove — даром); (б) скилл `supervisor-protocol` (P3.3) раскатывается СВОИМ каналом skiller (bucket general) — НЕ дублируется в пак (§3 один носитель артефакта); (в) skiller-профиль `artifex.json` (`agent_pack: ["artifex"]` + скилл) связывает оба → `maind onboard`/`sync`/`skiller integrate` доставляют вместе (паттерн php-package.json). opt-in-гейт (драйвер в рантайме, D5 = наличие policy-файла) ОРТОГОНАЛЕН установке пака: установлен пак ≠ проект ведётся. Отвергнуто: своя система версионирования хуков (ECC-стиль) — против reuse-мандата; смешивать скилл в пак — второй носитель. Дом rollout-конфигов (artifex/configs P3/P4 vs пак в harness) — открытый под-вопрос OQ-6, решается с владельцем в P6.1 | RAG:✅ 2026-07-18 (findings/owner-deep-audit-skills §Функция6 идея 7 / D15е: agent-packs lock зрелый, upgrade-drift бесплатно); структура пака/профиля — RAG:— (repo-grounded: packages/harness/docs/configs/agent-packs.md + packages/skiller/profiles/php-package.json) |
| D41 | 2026-07-18 | Рубрика вердикта пилота (P6.3): метрики — (1) стоимость/item из журнала P1.1 против baseline Workflow-марафона (гипотеза брифа §2, референс-точка FLEX-2 если доступна); (2) число эскалаций; (3) доля ложных ATTENTION; (4) качество решений прогресс-движка — владелец ЧИТАЕТ decision-лог P5.4 (item НЕ 🟢 без owner-sign-off: супервизор аудируем — смысл брифа); (5) обработка quota-события если случилось (D18). Вердикт `GREEN|ATTENTION` литералом в findings-отчёт; пилот РЕШАЕТ OQ-2 (Layer 3 go/no-go), КАЛИБРУЕТ similarity-порог P5.1 (снимает [UNVERIFIED]), СИДит решение OQ-4 (корневой супервизор v2). Дефект драйвера в прогоне → вердикт ATTENTION + C3/D6 fix-proposal (не GREEN-washing, не inline-патч). Массовая раскатка на 5 проектов — ПОСЛЕ вердикта (Scope Excluded фазы) | RAG:— (repo-grounded: brief/00-brief.md §Что хочет п.1 экономия fresh-session vs марафон + D36 similarity [UNVERIFIED] + D18 quota + D35 mAInd-репорт + скилл founder:adversarial-check честность пилота) |
| D42 | 2026-07-18 | P7 исполняется в сессиях BRAIN (объект — vault-хаб, не репо SKM); артефакты аудита читаемости (P7.1) и практики (P7.2) → `research/03`/`research/04` (слой 2 синтеза плана); финальный канон (P7.3) правится IN-PLACE в vault `02-Knowledge/00-Strategy/` — НЕ в plan `root/`: в отличие от код-планов (root/→docs), канон ЕСТЬ vault-контент, его дом — сам vault-хаб; glossary/tech-radar связываются ссылками, не дублируются. Валидация P7 — АБСОЛЮТНЫМ путём `plan-lint` + vault-путь плана (сессии BRAIN, не SKM-относительный путь P0–P6) | brief §6 (D14) + user-intent #28–31; RAG:— (repo-grounded: .ai/guidelines/obsidian.md wiki-link/_index + скилл axioma:axioma-stack «механизм в SKM, содержимое в Brain» анти-дубль) |
| D43 | 2026-07-18 | Brain-скиллы доступа к канону (P7.4) — указатель-паттерн `axioma:ecosystem-map` (триггеры → чтение канон-страниц P7.3, содержимое НЕ копируется); дом = vault `.ai/skills/<bucket>/`, конкретный bucket (рек. `architect` vs новый `strategy`) + опц. раскатка ссылочного скилла в проекты через skiller — гейт владельца (OQ-7, P7.4). Отвергнуто: копия канона в скилл (drift, §3 анти-второй-носитель); хардкод раскатки без решения владельца | brief §6 (D14 «скиллы в Brain, при необходимости раскатка»); RAG:— (repo-grounded: скилл axioma:ecosystem-map указатель-паттерн + формат .ai/skills/*.md) |
| D45 | 2026-07-18 | **Имя пакета = Artifex** (P0.1 owner-гейт, OQ-1 resolved; сверх Foreman/Overseer). **Формальный reuse-вердикт (дополняет D2, не отменяет):** прогон axioma-doctrine → axioma-stack → ecosystem-reuse-gate против живого `Ecosystem_Tech_Radar.md` — юнит «супервизор unattended-исполнения планов» в §2 карте отсутствует (not found), в §3 Gap не значится → build-new STANDALONE-пакет (правило 7, прецеденты AzGuard/Chatom), дом SKM как task/skiller/maind. Per-unit 6 функций: Ф1 драйвер+парсер build-new (пр.4+3, тонкий над `claude -p`), Ф2 progress build-new (пр.3, mem0-таксономия), **Ф3 auto-approve reuse-extend harness (пр.2, D29)**, Ф4 эскалация build-new тонкий hub (пр.3), Ф5 журнал build-new тонкий слой + reuse run-report `_lib.py`/`_usage.py` (пр.4, канон→пакет task), **Ф6 раскатка reuse harness agent-packs (пр.2, D40)**. Reuse-дисциплина: 3/6 функций переиспользуют механизмы экосистемы, build-new только где сработало правило. D2 подтверждён формально. Legacy PLAN-ID FOREMAN не трогается | P0.1: constitution-гейт нового пакета Axioma ДО фиксации архитектуры/стека (CLAUDE.md §Architect); reuse-отчёт — research/01-reuse-gate-verdict.md; RAG:— (repo-grounded: live-радар §2/§3/§4 + owner-deep-audit §Часть1/§2/§Функции-без-решений) |
| D46 | 2026-07-18 | **Reconcile P1↔P0 (contract-first §5, при детализации P1 после закрытия P0):** P0.2/P0.6 draft→**sealed** в контракт-блоке P1 (пины v2.8.0@2cf26e8 / run-folder v1). Вердикт сверки полей журнала (research/03-p1-p0-reconcile.md): байт-идентичны с P0.6 §3 ТОЛЬКО 6 линковочных ключей (`ts, plan_id, item_id, command, session_id, run_id`); поле `result` — общее **по маппингу, не по идентичности**: P1.1.`result` = enum-исход, ПРОИЗВОДНЫЙ от P0.6 `item_result`(`result`+`terminal_status`+`is_error`), НЕ тёзка сырого `result`-текста JSON-конверта P0.2 §2. Исправляет прежнее утверждение P1.1 «result … байт-в-байт». P0.6/P0.2 **НЕ правятся** (sealed; расхождение разрешено документацией на стороне P1.1, как предписывает §6 P0.6/P0.2 — reconcile-D#, не reopen P0). Снимает reconcile-долг P0.2 §6 + P0.6 §6 (handoff after P0.3) | §5 «Reconcile at detailing» (skill plan-protocol): сверить `Потребляет` с `Производит` закрытых фаз; RAG:— (repo-grounded: root/contracts/artifex-run-folder.md §3/§6 + driver-plan-protocol.md §2/§6 + research/03-p1-p0-reconcile.md) |
| D47 | 2026-07-18 | Канон-версия P1.4 конкретизирована: P0.2 sealed на plan-protocol **v2.8.0 @ 2cf26e8**; внесение journal/index в §2 Раскладку — **non-breaking** для parse-контракта P0.2 (не трогает якоря §1–§4 breaking-детекта: статусы/handoff/Next-enum/Status Board/JSON-конверт) → P1.4 бампает канон **v2.8.0→v2.9.0** (minor) + re-пинит P0.2 контракт на v2.9.0 БЕЗ breaking-стопа драйвера. Снимает If-then P1.4 «если P0.2 не исполнен — не выдумывать версию» (P0.2 исполнен) | research/03-p1-p0-reconcile.md §3; RAG:— (repo-grounded: driver-plan-protocol.md §4 закрытый перечень breaking-якорей + P0.2 пин v2.8.0@2cf26e8) |
| D48 | 2026-07-18 | **Пропагация имени foreman→artifex выполнена (owner-директива OQ-1, исполнение O15 «move-only» из Pending P0.1).** Во ВСЕХ файлах плана переименован ПРОДУКТ: `Foreman`→`Artifex`, `foreman`→`artifex` (пути `packages/artifex/`, `lib/artifex/`, `bin/artifex`, `python3 -m artifex`; профиль `artifex.json`; пак `agent-packs/artifex/`; env `FOREMAN_RUN_ID`→`ARTIFEX_RUN_ID`; команда `artifex continue`; тип мандата `artifex-mandate`; контракт-файлы `git mv foreman-run-folder.md→artifex-run-folder.md`, `foreman-policy-schema.md→artifex-policy-schema.md` + будущие `artifex-progress-model/decision-log/rulebook`). **Сохранено (НЕ переименовано):** legacy PLAN-ID `2026.07.18-FOREMAN` и все пути `…-FOREMAN/…` (D45, all-caps); workflow-codename `wf-foreman-principles-mining.js`/`foreman-principles-mining` (D28 codename = ID-часть после даты); провенанс решения имени (`Foreman/Overseer`, `Foreman/Artifex`, `FOREMAN/Artifex`, `foreman/artifex`). Переименование sealed-контрактов P0.6/P0.3 — move-only (метка продукта, семантика неизменна) → БЕЗ reopen P0. Верификация: 0 остаточных product-токенов, plan-ID 79 цел, ARTIFEX_RUN_ID 9 | Owner-директива 2026-07-18 (mid-turn: «до сих пор много где встречается foreman, нужно везде заменить»); RAG:— (repo-grounded: D45 legacy-ID keep + D28 codename-канон + grep-верификация rename) |
| D49 | 2026-07-25 | **Очередь экосистемы и владение поверхностями (межплановое решение владельца, сессия 2026-07-25).** Этот план идёт ПОСЛЕ `2026.07.24-AGENT-RELIABILITY` (`Paused By` обновлён; исторический pause на терминальный 🟠 `2026.07.19-DUAL-PROVIDER` снят как мёртвый гейт). Причины repo-grounded, а не календарные: (1) `packages/task` канон и скилл `plan-protocol` — единоличная собственность P2.2 того плана (бамп `2.11.0→2.12.0` + переписывание пяти команд), поэтому пин P0.2 здесь чинится ОДИН раз после его терминальной P2 (новый item P1.5, а не хвост P1.4); (2) фаза P5 этого плана (прогресс-движок/rulebook) и его P2.2/P2.3/P3.1 строят ОДНУ функцию — супервизор исполнения; владелец выбрал вариант «Artifex = тонкая обвязка над контрактами AGENT-RELIABILITY (`execution-state-machine-v1`, `risk-review-loop-budget-v1`, `unified-agent-trace-v1`), а не собственный движок решений» — пере-скоуп P2/P5 выполняется отдельным design-заходом на входе в волну 3, когда те контракты заморожены; (3) P6 (раскатка bucket через skiller) ждёт терминальную P1 того плана, которая чинит публикацию/marketplace. Регистр очереди и владения поверхностями — `plans/README.md` § «Очередь планов и владение поверхностями». | RAG:— (owner-grounded: директива 2026-07-25 «выстроить глобальный план разработки» + выбор варианта «тонкая обвязка»; repo-grounded: `plans/2026.07.24-AGENT-RELIABILITY/plan.md` §7 Exported и `phases/P2.md` P2.2 Implementation Rules; `root/contracts/driver-plan-protocol.md:7`). |
| D50 | 2026-07-25 | **P1.4 закрыт 🟠 по git-фактам, ремонт досок вместо переисполнения.** Работа item'а выполнена 2026-07-19 (`c37b3379` + bootstrap-журнал `9844f499`) и осталась незакрытой из-за перехвата ACTIVE планом DUAL-PROVIDER; проверка дерева 2026-07-25 подтвердила все пять Deliverables (канон 2.11.0 с journal/index, snippets зарегистрированы, lint-правило живо, 168 тестов `test_plan_lint.py` зелёные, journal.jsonl — 15 реальных записей). Единственное невыполненное — re-пин P0.2, вынесен в собственный item P1.5 по правилу plan-protocol «тайм-гейтовый Deliverable — отдельный item, а не хвост в Pending Work» (доска обязана показывать зависимость открытой). Переисполнение P1.4 отклонено: переписало бы уже поставленный канон. | RAG:— (repo-grounded: `git log` `c37b3379`/`9844f499`; прогон `python3 -m unittest ... test_plan_lint.py` → 168 OK; `check-translations.sh --strict` → зелёный; `plan-lint plans/2026.07.18-FOREMAN` → 0 ERROR). |
| D51 | 2026-07-25 | **Пере-скоуп P2/P5 отложен по зависимости, фазы помечены «подлежит пере-скоупу».** Программа владельца (design-first, `plans/README.md` § «Программа: этапы A–D») требует полной проектировки до исполнения, но пере-скоуп Artifex в тонкую обвязку (D49) проектируется ПРОТИВ контрактов `execution-state-machine-v1`, `risk-review-loop-budget-v1`, `unified-agent-trace-v1`, а те производятся `2026.07.24-AGENT-RELIABILITY` P2.1/P3.1 — за его терминальными P0 и P1, то есть внутри этапа D. Проектировать сейчас = проектировать против несуществующих входов. Решение: текущий дизайн P2 и P5 НЕ удаляется и НЕ переписывается, но несёт маркер «подлежит пере-скоупу» в Phase Context; против него ничего не строится; после AR P2.1 выполняется отложенный design-заход (fable-window по §2 Execution Rules) и повторный прогон межпланового гейта `plans/cross-plan-files.py` на этих двух фазах. Ограничение записано явно, чтобы «полная проектировка до исполнения» не читалась как достигнутая на 100%. | RAG:— (owner-grounded: директива 2026-07-25; repo-grounded: `plans/2026.07.24-AGENT-RELIABILITY/plan.md` §7 Exported — контракты `planned P2.1`/`planned P3.1`; `phases/P1.md` P1.1 Inputs «terminal P0»). |
| D44 | 2026-07-18 | Гейт дизайн-бюджета (finish, шаг 0): N сокращён 3→2. Форкаст 3 прогонов (Meta) исходил из ожидания, что детализация 8 фаз займёт 2–3 сессии; фактически вся пофазная детализация P0–P7 сошлась до DoR за один расширенный прогон (Update Log: 8 строк детализации, каждая фаза с контракт-блоком + D-записями). Дизайн-РАБОТА бюджета (скелеты→детализация) завершена: скелет-маркеров нет, DoR всех фаз закрыт, coupling §5 покрыт, 38/38 мыслей брифа трассированы (research/00-user-intent), roadmap собран. Авторизация недобора N — вызов владельцем `/task:plan-design 2026.07.18-FOREMAN finish` (roadmap сам флагует развилку «shrink N→2 либо fresh-пасс 3»; finish = выбор shrink). Счётчик → 2/2, finish дыр не выявил → следующий шаг plan-audit design | Гейт finish §0 (plan-protocol): «finish при недоборе прогонов — только по явной директиве владельца»; владелец вызвал finish, детализация верифицированно полна (repo-grounded: roadmap.md гейт-нота + Update Log 8 фаз до DoR + отсутствие скелет-маркеров) |

Coupling-поверхность (файлы/канон, трогаемые ≥2 фазами): контракт handoff/статусов
plan-protocol (P0.2 → P1, P2, P4, P5); схема журнала+индекса (P1.1–P1.2 → P2.3, P3.3,
P4, P5 — самый горячий hotspot); схема policy-файла (P0.3 → P2, P3, P5.2, P6); скилл
supervisor-protocol (P3.3 → P2-промпты воркеров, P4-эскалация, P5-директивы);
unattended-профиль permissions (P3.1–P3.2 → P2.5, P6.3 пилоты); канал-агностик слой +
escalation envelope (P4.1 → P4.2, P4.3 — внутрифазовый hotspot P4); схема run-folder/мандата
(P0.6 → P2.4, P4, P5.4 decision-события, иерархия D11); модель прогресса P5.1 (→ P5.2
решающая логика, P5.3 rulebook condition, P5.4 signals-лог); rulebook P5.3 (→ progress.py
загрузчик, policy P0.3 override, скилл P3.3 философия); граница retry↔движок (P2.3 ↔ P5.2 —
не задваивать эскалацию); канон плановой системы
в пакете task (P1.3–P1.4 — единственная фаза, правящая чужой пакет); config-home
rollout-артефактов (P3.1 settings-фрагмент / P3.2 policy-хук / P4.1 notify-хуки в
`packages/artifex/configs/` ↔ P6.1 упаковка в harness-пак `artifex/` — OQ-6, reconcile
Files при решении дома); сырьё майнинга
истории (P0.5 → P7.2) и стратегический канон Brain (P7.3 → контекст корневого
супервизора D11, скиллы P7.4).

| D52 | 2026-07-25 | **Четыре принципа владельца приняты как ОБЩИЕ для трёх живых планов и переведены в 12 проверяемых инвариантов; носитель — `plans/README.md` § «Принципы кросс-плановой работы», этот план ССЫЛАЕТСЯ из §2 и текст не копирует.** Чтение принципа «нет неприкасаемого кода» зафиксировано владельцем как **«граница обоснована, названа и ПРОХОДИМА»** (вариант «снять заморозки как класс» отклонён — он развернул бы закрытые решения трёх планов и back-compat флота). **Для этого плана инварианты бьют в конкретное место:** фазы **P2 и P5** несут маркер «подлежит пере-скоупу» (D51) — по **И1/И2** такой маркер легален ровно потому, что называет причину (дизайн написан до переопределения Artifex в тонкую обвязку), владельца контрактов (`2026.07.24-AGENT-RELIABILITY` P2.1/P3.1) и **проход** (отложенный design-заход после заморозки контрактов); по **И2** он обязан оставаться «заморожено ДО X», где X назван, а не «заморожено». **Consequences:** (1) маркер P2/P5 обязан пережить кросс-плановый аудит этапа C как НАЗВАННЫЙ пробел, а не находка — но только пока условие снятия остаётся проверяемым (терминальная AR P2.1); (2) items P2/P5 при пере-скоупе обязаны получить владельца и порядок в ТЗ ОБОИХ концов (И4), потому что они потребляют чужие контракты; (3) появляется внешняя зависимость от `plans/README.md` — ссылка идёт с именем секции, не с номером строки. | RAG:— (owner-grounded: решение 2026-07-25; repo-grounded: `plans/README.md` § «Принципы кросс-плановой работы» И1–И12; `phases/P5.md` и `phases/P2.md` — маркер «⚠ ПОДЛЕЖИТ ПЕРЕ-СКОУПУ (D51)»; `plan.md` §5 D51). |

| D59 | 2026-07-25 | **Payload C (аудит этапа C, Ф4/Ф6): условие снятия маркера P2/P5 канонизировано — терминальные AR P2.1 И P3.1.** D51/D52 и это README называли «после AR P2.1»; `handoff.md` называл «после P2/P3.1» — разноголосица (Ф4). Канон: обвязка потребляет ТРИ контракта AR (`execution-state-machine-v1`, `risk-review-loop-budget-v1`, `unified-agent-trace-v1`); первые два производит P2.1, третий — **P3.1**; маркер снимается только когда терминальны ОБЕ (это ровно то, что уже строит `plans/README.md` § «Кросс-плановая последовательность» шагом 60). Формулировка маркера в `phases/P2.md`/`phases/P5.md` поправлена на «терминальные P2.1 И P3.1». Заодно снят Ф6 (stale pointer): шапка `roadmap.md` указывала на `plan.md` v0.19.0 при живом v0.22.0+, статус-блок называл «следующий шаг — exec P1.1» вместо фактического Next = P1.5 — обе поправлены. | RAG:— (repo-grounded: `plans/README.md` § «Аудит этапа C — 2026-07-25» Ф4/Ф6; `plan.md` §5 D51/D52; `phases/P2.md`/`phases/P5.md` маркер; `handoff.md`; `roadmap.md` шапка). |

## 6. Update Log

| Дата | Кто | Что |
|:--|:--|:--|
| 2026-07-18 | fable | План создан (design pass 1): brief, 3 findings (headless факт-лист + 2 Perplexity), research/00-user-intent, скелеты фаз, контракты-черновики §7. ACTIVE перехвачен у 2026.07.15-TOKEN-ECON-P6 (Paused By проставлен) |
| 2026-07-18 | fable | Расширение по уточнению владельца (brief/01-refinements.md): +P1 журнал исполнения per plan + индекс (D8, канон через task), +P5 прогресс-движок + лог решений супервизора (D10); фазы перенумерованы (D9), 7 фаз / 26 items; Design Passes → 1/3; v0.1.0→0.2.0. Фокус pass 2: детализация с P0 из SKM |
| 2026-07-18 | fable | Второе уточнение владельца: иерархия супервизоров → D11 (рекурсивный Artifex, композируемость в P0.2, корень = v2, OQ-4); мульти-канальный блокирующий Q&A → D12 + finding MAX/TG (RAG) + P4.1–P4.3 канал-агностик + OQ-5. v0.2.0→0.3.0 |
| 2026-07-18 | fable | Третье уточнение владельца: +P0.5 майнинг принципов из истории планов (дешёвые модели, каталог «согласование vs свободно», утверждение владельцем) → D13, seed для P0.3/P3.3/P5.3; 27 items. v0.3.0→0.4.0 |
| 2026-07-18 | fable | +промпт Deep Research для владельца (research/deep-audit-prompt-skills-ecosystem.md) + pre-audit OSS-скиллов (findings/perplexity-skills-ecosystem-preaudit): greenfield-зоны подтверждены. Разбор полного аудита — P0.4/P0.5 |
| 2026-07-18 | fable | Четвёртое уточнение владельца: +P7 стратегический канон Brain (аудит читаемости хаба → практика разработки → самодостаточный 00-Strategy канон → Brain-скиллы доступа) → D14; 8 фаз / 31 item. v0.4.0→0.5.0 |
| 2026-07-18 | fable | Принят Deep Research аудит владельца → findings/owner-deep-audit-skills-2026-07-18.md (перенесён из AXIOMA-ORCHESTRA/research), вердикты в D15, Inputs фаз P1–P6 прошиты, pre-audit помечен superseded, P0.4 дополнен остаточными проверками. v0.5.0→0.6.0 |
| 2026-07-18 | fable | Пятое уточнение владельца: мандат делегирования + run-folder запусков → D16–D17 (+finding supervisor-runtimes: Ralph/Gas Town/CC Tasks), +P0.6 схема, +P2.4 реализация resume-by-folder (dry-run → P2.5); контракт run-folder в §7; 33 items. v0.6.0→0.7.0 |
| 2026-07-18 | fable | Шестое уточнение владельца: quota-resilience → D18 (quota = третий класс сбоя: 5h-окно ждать / weekly URGENT-будить с инструкцией смены учётки), P2.3 tier3, P4.2 тип URGENT, P0.4 детект-проверки. v0.7.0→0.8.0 |
| 2026-07-18 | fable | Седьмое уточнение владельца: дисциплина 100%-верификации Perplexity-фактов первоисточниками → D19 + правило в Execution Rules (прецедент: ложное отрицание 3 реальных реп). Структура плана зафиксирована, передача в проработку P0 (NEW SESSION). v0.8.0→0.9.0 |
| 2026-07-18 | fable | Детализация P0 до DoR (design pass 2, фаза 1/8): 6 items, workflow P0.5 создан, §7 остаётся draft (запечатывается в P0-exec) — детали см. phases/P0.md. v0.9.0→0.10.0 |
| 2026-07-18 | opus | Детализация P1 до DoR (фаза 2/8, ядро экосистемы — pre-mortem проведён): 4 items, D20–D24 (формат journal.jsonl / механизм записи / soft-lint-гейт / индекс / reconcile с run-folder P0.6), контракт-блок фазы обновлён. §7 draft. v0.10.0→0.11.0 |
| 2026-07-18 | opus | Детализация P2 до DoR (фаза 3/8, ядро драйвера): 5 items, D25 (язык Python stdlib + раскладка skiller), D26 (владение журналом — reconcile D24), D27 (скоуп авто-драйва) + research/01-p2-driver-architecture.md — детали см. phases/P2.md. §7 draft. v0.11.0→0.12.0 |
| 2026-07-18 | opus | Детализация P3 до DoR (фаза 4/8, security-sensitive): 3 items, D28 (mode флагом+acceptEdits, bypass не дефолт), D29 (PreToolUse extend harness, детерминизм), D30 (reconcile P3↔P0.3) — детали см. phases/P3.md. v0.12.0→0.13.0 |
| 2026-07-18 | opus | Детализация P4 до DoR (фаза 5/8, эскалация+наблюдаемость): 4 items, D31–D35 (адаптеры stdlib HTTP; единый escalation envelope; MVP одноуровневая пауза+severity-таймаут; OQ-5 resolved→D34; репортинг в mAInd); OQ-5→Resolved — детали см. phases/P4.md. v0.13.0→0.14.0 |
| 2026-07-18 | fable | Детализация P5 до DoR (фаза 6/8, прогресс-движок): 4 items, D36–D39 (многослойная детекция; граница retry↔тренд; rulebook; decision-лог) + research/02-p5-progress-engine.md — детали см. phases/P5.md. v0.14.0→0.15.0 |
| 2026-07-18 | opus | Детализация P6 до DoR (фаза 7/8, раскатка+пилот): 3 items, D40 (rollout=harness agent-pack + skiller-профиль, reuse), D41 (рубрика вердикта пилота); Routing P6.1–P6.3 расщеплён; config-home fork → OQ-6 — детали см. phases/P6.md. v0.15.0→0.16.0 |
| 2026-07-18 | opus | Детализация P7 до DoR (фаза 8/8, последняя, канон Brain): 4 items, D42 (P7 в BRAIN; канон → vault 00-Strategy in-place), D43 (P7.4 скилл-указатель + OQ-7) — детали phases/P7.md. Все 8 фаз детализированы; roadmap.md собран. v0.16.0→0.17.0 |
| 2026-07-18 | fable | Finish: гейты скелет-маркеров/reconcile/DoR-свип 8 фаз/бриф-трассировка 38/38 — пройдены, дыр НЕ выявлено; Design Passes реконсилён 1/3→2/2 (D44). Следующий шаг — plan-audit design. v0.17.0→0.18.0 |
| 2026-07-18 | opus/high | P0.1 закрыт 🟢: имя пакета = **Artifex** (D45, OQ-1 resolved); формальный reuse-гейт подтвердил D2 (build-new standalone, правило 7; 3/6 функций reuse-extend harness) — детали см. phases/P0.md P0.1 Completion Notes |
| 2026-07-18 | opus/high | P0.2 закрыт 🟢: parse-контракт драйвер↔plan-protocol запечатан (root/contracts/driver-plan-protocol.md), пин SSOT v2.8.0@2cf26e8, §7 Consumed — детали см. phases/P0.md P0.2 Completion Notes |
| 2026-07-18 | opus/high | P0.6 закрыт 🟢: запечатан контракт run-folder+мандат (`root/contracts/artifex-run-folder.md` v1), §7 Exported→sealed — детали см. phases/P0.md P0.6 Completion Notes |
| 2026-07-18 | opus/high | P0.4 закрыт 🟢: сняты 9 неопределённостей headless — D7 перевёрнут (`--max-turns` работает), баги #49525/#39973 НЕ пофикшены (mode флагом, D28), OQ-3 Resolved, quota/MAX/Ralph-MIT сняты; defer+CC-Tasks остались [UNVERIFIED] (фазы без них) — детали см. phases/P0.md P0.4 Completion Notes |
| 2026-07-18 | opus/high (plan-run) | P0.5 закрыт 🟢: каталог принципов владельца (майнинг wf 52→43: 9 согласование/2 свободно/0 гипотез/29 вне-бинаря = D13-находка), гейт владельца — на утверждение — детали см. phases/P0.md P0.5 Completion Notes |
| 2026-07-18 | opus/high (plan-run) | P0.3 закрыт 🟢: schema policy-файла v1 (`root/contracts/artifex-policy-schema.md`, формат TOML/`.artifex/policy.toml`), §7 Exported→sealed; философия=бинарь-СТРУКТУРА (значения досеваются P0.5), D13-находка owner-gated; **P0 6/6 — терминальна** — детали см. phases/P0.md P0.3 Completion Notes |
| 2026-07-18 | opus/high | P1 reconcile после закрытия P0: P0.2/P0.6 draft→sealed; D46 (журнал — 6 ключей байт-идентичны, `result` по маппингу) + D47 (канон-бамп v2.8.0→v2.9.0 non-breaking) — детали phases/P1.md P1.1/P1.4 + research/03. v0.18.0→0.19.0 |
| 2026-07-18 | opus/high | Owner-директива OQ-1: пропагация foreman→artifex во всех файлах плана (D48, move-only) — имя/пути/env/git mv 2 контрактов; legacy PLAN-ID + workflow-codename сохранены. OQ-3 подтверждён (Resolved→P0.4) |
| 2026-07-18 | opus/high | P1.1 закрыт 🟢: запечатана схема пер-планового `journal.jsonl` (root/contracts/plan-journal-schema.md sealed v1) + §7 Exported журнал draft→sealed — детали см. phases/P1.md P1.1 Completion Notes. Фаза P1 1/4 🟡 |
| 2026-07-18 | opus/high (plan-run) | P1.2 закрыт 🟢: запечатана схема корневого индекса `plans/<ID>/index.md` (root/contracts/plan-index-schema.md sealed v1) + §7 Exported индекс draft→sealed — детали см. phases/P1.md P1.2 Completion Notes. Фаза P1 2/4 🟡 |
| 2026-07-18 | sonnet/high (plan-run) | P1.3 закрыт 🟢: `lib/task/journal.py` (append+валидация P1.1+CLI) + запись журнала врезана в close-протокол 5 команд `plan-{exec,run,close,audit,design}.md` (D21) — детали см. phases/P1.md P1.3 Completion Notes. Фаза P1 3/4 🟡 |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | План поставлен на паузу новым ACTIVE `2026.07.19-DUAL-PROVIDER`; продолжение с P1.4 запрещено до release gate P7.4 и reconcile provider-neutral runner contract. |
| 2026-07-25 | plan-design/Claude Opus 5/high (межплановая очередь) | P1.4 закрыт 🟠 по git-фактам, открыт P1.5 (re-пин P0.2) — детали см. phases/P1.md P1.4 Completion Notes. D49/D50; `Paused By` → `2026.07.24-AGENT-RELIABILITY`, `Home` исправлен на repo. v0.20.0. |
| 2026-07-25 | plan-design/Claude Opus 5/high (программный гейт) | D51: фазы P2/P5 помечены «подлежит пере-скоупу», заход отложен до контрактов AR P2.1. v0.21.0. |
| 2026-07-25 | plan-design/Claude Opus 5/high (принципы) | D52: четыре принципа владельца → 12 инвариантов И1–И12 в `plans/README.md`; §2 несёт ссылку; маркер P2/P5 признан легальным по И1/И2. Version 0.21.0 → 0.22.0. |
| 2026-07-29 | plan-design/Claude Opus 5/high (поглощение) | План поглощён новым ACTIVE `2026.07.29-HARNESS-AGNOSTIC` (решение владельца 2026-07-29): тот план несёт `supersedes: 2026.07.18-FOREMAN`, переиспользует sealed-контракты P0/P1, исполняет отложенный пере-скоуп P2/P5 своей фазой P4 (условие снятия маркера D59 выполнено — `2026.07.24-AGENT-RELIABILITY` закрыт 🟠 2026-07-26) и архивирует этот план своим item P0.3. Содержательных правок здесь не делается. |
| 2026-07-25 | bookkeeping/Claude Sonnet 5/high (payload C, аудит этапа C Ф4/Ф6) | D59: условие снятия маркера P2/P5 канонизировано — терминальные AR P2.1 И P3.1; маркер поправлен в `phases/P2.md`/`phases/P5.md`; шапка `roadmap.md` актуализирована (версия соответствия, статус-блок — Next = P1.5). Version 0.22.0 → 0.22.1. |

## 7. Contracts

Статус: контракты P0 **sealed** (Consumed plan-protocol v2.8.0@2cf26e8; Exported policy v1,
run-folder v1); журнал P1.1 **sealed v1**; индекс P1.2 **sealed v1**; decision-лог P5.4 —
**draft** (запечатывается своей фазой).

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| plan-protocol handoff/status schema (драйвер парсит `handoff.md`: заголовок `after Pn[.m]`, Next/launch-block; Status Board `plan.md`; 6 канонических статусов; поля Escalation Needed/Pending Work; JSON-конверт `--output-format json`) — parse-контракт `root/contracts/driver-plan-protocol.md` (P0.2) | скилл `core:plan-protocol` (SSOT, вне планов) | **v2.8.0 @ swissknifeman commit `2cf26e8`** (2026-07-18) | — | смена схемы протокола без синхронного bump'а контракта = breaking → стоп драйвера + эскалация владельцу (breaking-перечень — §4 контракта) |

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| artifex policy file (per project): opt-in маркер + декларативная политика (retry-лимиты, model routing overrides, каналы+severity-таймаут, quota-ветка, auto-drive-скоуп, permission-override D30, пороги-плейсхолдер P5, философия-директивы бинарь) — формат **TOML** (stdlib, D25), место `.artifex/policy.toml`; контракт `root/contracts/artifex-policy-schema.md` (P0.3) | **v1** (semver `meta.version` в файле; философия-ЗНАЧЕНИЯ досеваются из каталога P0.5 после «Утверждено») | **sealed** | проекты-подписчики Artifex (пилот — P6.3) | владелец (P0.3) |
| plan execution journal (per plan, append-only): `plans/<ID>/journal.jsonl` NDJSON — одна запись на исполнение item любым `/task:plan-*` (поля: `ts,plan_id,item_id,command,session_id,run_id,attempt,actor,friction[],result`-enum`,cost_usd,num_turns,duration_ms,note`); append-only, durable/git-tracked; контракт `root/contracts/plan-journal-schema.md` (P1.1); пишется ВСЕМИ запусками (D8) | **v1** (формат sealed P1.1; канон plan-protocol — P1.4 через contribution в task, бамп v2.8.0→v2.9.0 D47) | **sealed** | драйвер P2.3, скилл P3.3, эскалация P4, прогресс-движок P5, все планы экосистемы после P1.4 | P1.1 (внутриплановые потребители P2–P5) |
| корневой индекс плана: `plans/<ID>/index.md` — карта ФАЙЛОВ плана + провенанс-связи (findings/research→фаза), НЕ носитель статуса (D23); контракт `root/contracts/plan-index-schema.md` (P1.2); 3 секции (директорная карта / провенанс / артефакты root); опционален, генерация из дерева+frontmatter рекомендована | **v1** (формат sealed P1.2; канон — P1.4 через contribution в task) | **sealed** | навигация человеком+супервизором, все планы экосистемы после P1.4 | P1.2 (навигация; канон-потребители — P1.4) |
| supervisor decision log: обогащённое `decision`-событие run-folder journal P0.6 (signals метрик P5.1 / applied_rules P5.3 / verdict / rationale), append-only, НЕ отдельный файл (D39) | draft (запечатывает P5.4; формат = decision-подмножество run-folder journal) | draft | владелец (аудит супервизора, P6.3) | — |
| artifex run-folder + мандат запуска: `runs/<дата-код>/` (brief/00-mandate.md — скоуп фаз и права делегирования; state.json; journal.jsonl; resume-by-folder), мандат сужает policy — контракт `root/contracts/artifex-run-folder.md` (P0.6) | **v1** (semver во frontmatter контракта; дом `runs/` рядом с `plans/`, 2026-07-18) | **sealed** | драйвер P2.4, эскалация P4 (пауза/резюм), P5.4 decision-события, иерархия D11 (дочерний run-folder ссылается на родительский), владелец (команда «продолжай <папка>») | владелец (P0.6) |

## Обсуждение

### Имя пакета
**Статус:** Resolved → D45 (P0.1). Владелец выбрал **Artifex** (сверх
Foreman/Overseer). Префикс путей пакета — `packages/artifex/`, `bin/artifex`,
пак `artifex`, профиль `artifex.json`. Legacy PLAN-ID `2026.07.18-FOREMAN` НЕ
переименовывается (Scope Excluded P0.1). Пропагация имени в path-референсы фаз
P2/P3/P6 (`packages/artifex/*` → `packages/artifex/*`) — Pending, при детализации/
exec этих фаз.

### Layer 3 remote-approve (TG-команды approve/deny)
**Статус:** Exploration — делать ли вообще; MVP живёт без него (D6); решение после
пилота P6.3 (см. `open-questions.md` OQ-2).

### Формат пер-планового журнала (P1.1)
- **(рекоменд.) Вариант A. `journal.jsonl` (append-only NDJSON).** Плюсы: машинно-парсим
  супервизором, reuse `_lib.py`/`_usage.py`, согласован с run-folder journal.jsonl (P0.6),
  append без merge-конфликтов. Минусы: не читается человеком напрямую (нужен генератор вида).
- **Вариант B. MD-таблица.** Плюсы: человекочитаема. Минусы: плохо парсится, merge-конфликты
  при append из параллельных сессий, рассинхрон с run-folder-схемой.
- **Вариант C. NDJSON + хранимый MD-дайджест.** Минусы: двойной носитель факта → дрейф (§3).
**Статус:** Resolved → D20 (человекочитаемый вид — генерируемый, не хранимый).

### Механизм записи журнала (P1.3)
- **(рекоменд.) Вариант A. Инструкция в close-протоколе + хелпер `lib/task/journal.py`,
  хук SessionEnd как backstop.** Плюсы: детерминированная точка (bookkeeping-коммит),
  schema-корректный append, backstop ловит упавшие прогоны. Минусы: две поверхности.
- **Вариант B. Только хук.** Минусы: plan_id/item_id из транскрипта — эвристика.
- **Вариант C. Только инструкция.** Минусы: упавший прогон не оставляет записи; сырой JSONL
  моделью → битые строки.
**Статус:** Resolved → D21 (backstop-хук — owner-review в P1.3; MVP без него).

### Корневой индекс плана (P1.2)
- **(рекоменд.) Вариант A. `index.md` — авто-генерируемая карта файлов + провенанс.** Плюсы:
  устраняет дрейф, не дублирует Status Board. Минусы: нужен генератор.
- **Вариант B. Hand-maintained индекс.** Минусы: второй носитель статуса → рассинхрон (§3).
**Статус:** Resolved → D23.

### Канал-адаптеры эскалации: stdlib HTTP vs MCP-плагин MAX (P4.1)
- **(рекоменд.) Вариант A. stdlib `urllib` HTTP-адаптеры (TG+MAX `sendMessage`).** Плюсы:
  конвенция пакета stdlib-only (D25); notify тривиален; без Bun/Node-зависимости; тесты на моке.
  Минусы: интерактивный inbox (Layer 3) придётся строить отдельно.
- **Вариант B. MAVII-RU/max-messenger-plugin (TS/Bun MCP) как есть.** Плюсы: готовый MAX-канал
  с inbox. Минусы: TS/Bun-зависимость в Python-пакете; для Layer 1 notify избыточно.
**Статус:** Resolved → D31 (stdlib для Layer 1/2; плагин — референс P4.3 inbox, отдельный процесс).

### Доставка эскалаций при деградации обоих каналов (P4.2, OQ-5)
- **(рекоменд.) Вариант A. Fan-out по порядку policy + пауза при полной недоставке.** Плюсы:
  fail-safe (unattended не едет без оповещения владельца); резерв web-push/email допущен интерфейсом.
  Минусы: при полной недоставке прогон встаёт (но это и есть желаемое поведение).
- **Вариант B. Продолжать при недоставке, писать только в журнал.** Минусы: спорный item уедет
  без владельца — против D6 «спорное решает человек».
**Статус:** Resolved → D34 (fan-out + полная недоставка → пауза+state).

### Baseline permission-mode unattended-профиля (P3.1)
- **(рекоменд.) Вариант A. `acceptEdits` (флагом) + PreToolUse policy-хук поверх.** Плюсы:
  авто-approve правок без bypass; Bash/сеть под явной policy; fail-safe; mode устойчив к
  багам #49525/#39973 (задаётся флагом при запуске). Минусы: две поверхности (mode-флаг + хук).
- **Вариант B. `dontAsk` + широкий allowlist.** Минусы: allowlist растёт неконтролируемо;
  AskUserQuestion всё равно denied.
- **Вариант C. `bypassPermissions`.** Минусы: circuit breaker; баг #49525 молча деградирует
  в acceptEdits; security-дыра для unattended-агента.
**Статус:** Resolved → D28.

### Хранилище лога решений супервизора (P5.4)
- **(рекоменд.) Вариант A. Обогащённое `decision`-событие run-folder journal (P0.6).** Плюсы:
  P0.6 уже несёт тип `decision`; reuse `append_event` (P2.4); один событийный носитель прогона;
  run-folder durable → аудируемость. Минусы: расширение P0.6-схемы (reconcile D#).
- **Вариант B. Отдельный per-plan файл решений.** Минусы: решения привязаны к ПРОГОНУ, не к
  плану (план исполняют и вручную, без супервизора) — семантически неверный дом.
- **Вариант C. Отдельный `decisions.jsonl` в run-folder.** Минусы: дублирует событийный носитель
  P0.6 → третий журнал → дрейф (§3 анти-второй-носитель).
**Статус:** Resolved → D39.

### Семантика point-fix при stalling (P5.2)
- **(рекоменд.) Вариант A. Эскалация-с-предложением + пауза.** Плюсы: инвариант драйвер-read-only
  сохранён (правки — воркеры/владелец); конкретное предложение (сузить scope/сплит/стоп) в
  envelope; консервативно. Минусы: не полностью автономно (владелец применяет правку).
- **Вариант B. Автономная правка плана драйвером (сузить scope/сплит item).** Минусы: нарушает
  инвариант P2 (драйвер только читает); каскад ошибок без владельца; против D6/D10.
**Статус:** Resolved → D37 (автономный plan-design на правку — v2 после пилота P6.3).

### Дом rulebook правил (P5.3)
- **(рекоменд.) Вариант A. artifex-shipped baseline + per-project policy override (как severity D30).**
  Плюсы: единый override-механизм экосистемы; project-специфика без форка движка; СИД из P0.5.
  Минусы: два места чтения (baseline+policy) — но merge, не два SSOT.
- **Вариант B. Правила только в policy проекта.** Минусы: нет общего консервативного дефолта;
  каждый проект заводит правила с нуля.
- **Вариант C. Хардкод правил в progress.py.** Минусы: «наращивание по опыту» требует
  переписывания движка — против брифа §2.
**Статус:** Resolved → D38.

### Дом rollout-конфигов Artifex (P6.1, OQ-6)
Механизм раскатки — harness agent-pack (D40, не оспаривается). Открыт физический ДОМ
хук/settings-шаблонов, которые P3/P4 авторят в `packages/artifex/configs/`, а пак ждёт под
`packages/harness/.../agent-packs/artifex/`:
- **(рекоменд.) Вариант A. Пак в harness = единственный дом; `artifex/configs` ретайрится,
  Files P3.1/P3.2/P4.1 переезжают в пак (reconcile).** Плюсы: один SSOT, нет дрейфа; прямой
  паттерн существующих паков. Минусы: хуки тестируются пакетом artifex — тесты ссылаются в
  чужой пакет harness (кросс-пакетная связь в CI).
- **Вариант B. `artifex/configs` = SSOT (тестируется в artifex), P6.1 РЕНДЕРИТ копии в пак +
  байт-валидатор синхронности** (паттерн `test_agentpacks_shared.py`). Плюсы: тесты хуков
  остаются в artifex; направление зависимостей чище. Минусы: два физических места + валидатор.
- **Вариант C. Держать оба, sha-check красит расхождение.** Минусы: два носителя явно (§3).
**Статус:** Decision pending — решает владелец в P6.1 (manual, обзор contribution в harness);
`open-questions.md` OQ-6.

### Дом Brain-скилла доступа к канону (P7.4, OQ-7)
Механизм — указатель-паттерн `axioma:ecosystem-map` (D43, не оспаривается). Открыт физический
ДОМ скилла-указателя в vault:
- **(рекоменд.) Вариант A. Скилл в vault `.ai/skills/architect/ecosystem-strategy.md`** (стратегия
  релевантна Architect-персоне) + опц. skiller-раскатка в проекты. Плюсы: Brain=хаб (brief §6),
  скилл рядом с каноном, персона Architect уже несёт стратегические скиллы. Минусы: bucket-выбор
  за владельцем; «стратегия» шире Architect.
- **Вариант B. Новый bucket `.ai/skills/strategy/`.** Плюсы: чистое место под стратегию-канон.
  Минусы: новая персона/bucket ради 1 скилла (over-engineering до P7.4).
- **Вариант C. Скилл в swissknifeman skiller-бакете (общий канал).** Минусы: канон живёт в Brain —
  указатель ближе к канону в Brain; кросс-репо связь скилл↔канон.
**Статус:** Decision pending — владелец решает bucket + раскатку в P7.4 (manual, opus/high);
`open-questions.md` OQ-7.
