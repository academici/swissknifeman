# CONTEXT-ECONOMY — стабилизация стартового контекста экосистемы → stable v0.9.0

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.12-CONTEXT-ECONOMY |
| Title | Context-economy стабилизация экосистемы → stable release v0.9.0 |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | fable |
| Last Updated | 2026-07-12 |
| Repository | swissknifeman (монорепо academici) |
| Related Packages | maind, harness, skiller, analyst, core |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus/fable (design/review/audit) |
| Approval Owner | Dmitry Vostrikov |

## 1. Context

Аналитика логов сессий (~448 сессий, 4 проекта, июнь–июль 2026): медианный оверхед
первого хода вырос с ~10.7K (W24) до ~31.9K токенов (W28), в agelto — до 84–140K.
Причина — не сложность задач, а рост always-on контекста, раскатанного экосистемой
(maind/harness/skiller) на ~17 проектов. RAG-нормы (RAG:✅ 2026-07-12, выжимка —
`findings/P0-rag-context-economy.md`): стартовый бюджет 3–7K ток; hook
additionalContext ≤500–1500 ток; описание скилла 10–30 ток; CLAUDE.md ≤200 строк.
Виновники (file:line подтверждены разведкой 2026-07-12): (1) harness agent-router
SessionStart-политика 1445 симв ≈ 600–900 ток каждую сессию (e041862, 01.07);
(2) maind memory digest без байт-бюджета + межпроектная утечка через ns:axioma;
(3) второй maind SessionStart-хук (health) печатает статус даже при OK;
(4) skill listing: agelto ~60–80 описаний ≈ 8.5K ток, 134/215 описаний >150 симв;
(5) agent-packs ~2K ток описаний на пак. Цель плана: сжать always-on футпринт до
норм, дать измеримость (footprint-доктор + телеметрия) и выпустить stable v0.9.0.

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (plan-protocol §5).
- План разошёлся с кодом → не импровизировать, эскалировать (§8).
- После закрытия item/фазы — перезаписать `plans/2026.07.12-CONTEXT-ECONOMY/handoff.md`.
- stdlib-only в python-пакетах (жёсткая рамка репо); `Env` явно; atomic JSON.
- Внешние факты — верифицировать RAG (context7 → perplexity-web), не по памяти.
- Коммиты — Conventional Commits на русском, мелкими порциями по смыслу;
  перед коммитом кода validate.sh затронутого пакета зелёный.
- Правки скиллов: SKILL.ru.md (RU-источник) → SKILL.md (EN-канон) →
  `check-translations.sh --stamp` → `skiller registry` (skill-authoring канон).
- Rollout на флот (P6) — только после мержа кода P1–P5; baseline-замер ДО раскатки.
- Грязное рабочее дерево (uncommitted `skills/ai/mcp-builder/` + regen-артефакты)
  закоммитить/запарковать отдельным коммитом ДО старта P1 (гейт P1.1 Inputs).

## 3. Routing

| Items | Model/effort · Tool Capability | Почему |
|:--|:--|:--|
| P2.1 | fable или opus/high | компрессия policy без потери семантики — вердикт-чувствительно |
| P6.3 | sonnet/medium + AskUserQuestion | ревизия бакетов — per-project подтверждение Owner |
| P8.4 | sonnet/low + approve Owner | тег только с явного approve |

Остальное — дефолты SSOT-матрицы plan-protocol §7.

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | maind: тощий старт сессии (digest-бюджет + тихий health) | 3/3 | 🟢 Done |
| P2 | harness: диета agent-router (policy v2) | 1/1 | 🟢 Done |
| P3 | skiller: рэтчет описаний скиллов | 2/2 | 🟢 Done |
| P4 | agent-packs: диета описаний субагентов | 1/2 | 🟡 In progress |
| P5 | Footprint-доктор + телеметрия | 0/4 | ⬜ Not started |
| P6 | Rollout на флот + замер до/после | 0/4 | ⬜ Not started |
| P7 | Машинный bootstrap (новая машина / команда) | 0/2 | ⬜ Not started |
| P8 | Доктрина + скиллы/доки + релиз v0.9.0 | 0/4 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-12 | Источник — черновик plan mode `~/.claude/plans/linked-nibbling-bachman.md` (одобрен Owner) | bootstrap-транскрипция одобренного черновика plan mode; черновик вне repo-`plans/`, файл оставлен harness'у (правило удаления касается repo-черновиков) |
| D2 | 2026-07-12 | Plan ID `2026.07.12-CONTEXT-ECONOMY` задан Owner в вызове plan-design | датовый канон D16 плана SKM-ROADMAP-005; подтверждение ID человеком выполнено самим вызовом |
| D3 | 2026-07-12 | Resync router-артефактов (черновик «P2.2») консолидирован в P6.2 — P2 меняет только source-конфиг | rollout весь живёт в P6; двойной resync = двойная работа и рассинхрон baseline-замера |
| D4 | 2026-07-12 | Router: сжать ≤400 ток, остаётся always-on (вариант A); выключение по умолчанию отклонено | решение Owner (AskUserQuestion 2026-07-12) |
| D5 | 2026-07-12 | Digest: приват-приоритет + cap shared 2–3 (вариант «кап», не «только project-scope») | решение Owner (AskUserQuestion 2026-07-12) |
| D6 | 2026-07-12 | Skill diet: описания + ревизия бакетов по проектам (не только описания) | решение Owner (AskUserQuestion 2026-07-12) |
| D7 | 2026-07-12 | OTEL-пресет (P5.4) — опциональный: при давлении объёма релиза допускается ⛔ Skipped by decision с переносом в roadmap/ | приоритет — свои данные (run-report+analyst); OTEL требует внешнего коллектора |
| D8 | 2026-07-12 | Смена Active: — → 2026.07.12-CONTEXT-ECONOMY | новый план создан; прежний ACTIVE пуст (SKM-AUDIT-004 закрыт) |
| D9 | 2026-07-12 | Версии: maind 0.2.1→0.3.0 · skiller 0.3.0→0.4.0 · harness 0.1.0→0.2.0; тег монорепо v0.9.0; v1.0.0 — только при объявлении Owner API freeze | semver: minor-фичи (digest-бюджет, first-turn, doctor --context) без breaking |
| D10 | 2026-07-12 | **Supersede D5**: digest project-only по умолчанию (shared_max=0); shared-факты ns/global — только по прямому запросу (recall/--shared-max); namespaces сохраняются для recall и графа | уточнение Owner: межпроектная память нужна лишь при явной кросс-проектной задаче; от общего namespace в digest «один негатив»; полный отказ от namespaces не нужен — негатив давал только digest |
| D11 | 2026-07-12 | Добавлена фаза P7 (машинный bootstrap, dotfiles-паттерн: идемпотентный скрипт + dry-run + merge-not-overwrite + per-user манифест проектов); релиз сдвинут в P8 | запрос Owner (вторая машина/переустановка ОС/команда); паттерн RAG:✅ 2026-07-12 findings/P0-rag-bootstrap-memory-sync.md; bootstrap должен войти в stable-тег |
| D12 | 2026-07-12 | Межкомпьютерная синхронизация памяти — НЕ в релиз; roadmap-стаб `roadmap/cross-machine-memory.md` (варианты: демон на одном хосте через Tailscale/LAN; export/import событий); shared-папка для бинарного state_store.db — явный запрет | RAG:✅ 2026-07-12: file-sync живого бинарного стора = порча при конкурентной записи; критерий Owner «сложно — не стоит»; качество кода не зависит, теряется только исторический контекст |
| D13 | 2026-07-12 | Валидация доработок не только кодом: новые items P1.3 (гайдлайн межпроектной памяти в скиллах/доках, источник — шаблоны maind) и P8.2 (синхронизация локальных скиллов и доков с философией/возможностями релиза) | требование Owner: скиллы — интерфейс знания агентов; без них агенты работают по устаревшей модели |
| D14 | 2026-07-12 | Общий workflow-исполнитель плана `workflows/wf-context-economy-exec.js` (scriptPath-запуск, per-item модель/effort из Routing): автономно ведёт P1→P5 и P7; останавливается перед Owner-гейтами (P6 — baseline/раскатка/бакеты/живые сессии; P8.4 — approve тега). Локальное исключение phase-first: P7 (код в репо) разрешён до закрытия P6 (rollout с человеком) | запрос Owner «workflow до самого конца с моделью на каждую фазу»; прецедент — wf-skm-roadmap-005-rest-exec.js; P6 требует человека по построению (baseline из живых сессий, per-project подтверждения) — честнее объявить паузу, чем имитировать |
| D15 | 2026-07-12 | P6.2 (sync-волны): Brain (`/home/vostrikov/Vaults/Brain`) — первый проект в каждой волне, приоритетнее остального флота; продолжение по остальным ~16 проектам — только после его подтверждённого успеха | запрос Owner |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-12 | plan-design/fable | План создан from-draft (7 фаз, 18 items), ACTIVE → 2026.07.12-CONTEXT-ECONOMY |
| 2026-07-12 | plan-design/fable | Дополнение Owner: D10 (digest project-only, supersede D5), новая фаза P7 bootstrap (D11), память между машинами → roadmap (D12); релиз перенумерован P7→P8. Итог: 8 фаз, 20 items |
| 2026-07-12 | plan-design/fable | Дополнение Owner-2: P1.3 + P8.2 — скиллы/доки как обязательный слой валидации (D13); общий workflow-исполнитель wf-context-economy-exec.js с per-item роутингом моделей (D14). Итог: 8 фаз, 22 items |
| 2026-07-12 | plan-exec/sonnet | P1.1 закрыт: select_digest_items (байт-бюджет + project-only shared_max=0, D10) + config/CLI-флаги + 9 тестов; validate.sh 397 OK |
| 2026-07-12 | plan-exec/sonnet | P1.2 закрыт: session-start-hook.sh тихий при OK (`--strict` rc-гейт), memory-digest-hook.sh — бамп-комментарий шапки (stale для sync); 5 новых тестов (статика + функциональные); validate.sh 402 OK |
| 2026-07-12 | plan-exec/sonnet | P1.3 закрыт (фаза P1 3/3 🟢): ecosystem-mcp (источник) + 3 локальных скилла + docs/guide/{memory,namespaces}.md — гайдлайн «межпроектная задача» (graph → recall --scope ns:<имя> → remember --scope ns:<имя>, D10) и оговорка digest project-only; команды сверены с --help; 9 тестов; validate.sh 411 OK |
| 2026-07-12 | plan-exec/opus | P2.1 закрыт (фаза P2 1/1 🟢): policy config.json → терс-EN 1186 симв ≈296 ток (было 1445 симв RU), version 1→2, auto_suffix EN; семантический инвариант (6 пунктов) сохранён полностью, эскалация не потребовалась; test_router_config (4 теста) + validate.sh зелёный |
| 2026-07-12 | plan-exec/sonnet | P3.1 закрыт (фаза P3 1/2 🟡): 0/8 описаний >450 (мандаторный минимум); 24 скилла укорочены (SKILL.md+SKILL.ru.md), 3 из 8 мандаторных ≤300; check-translations --stamp + registry идемпотентен + validate.sh 366 тестов + budget --check-core --strict зелёные; новый test_desc_diet.py (скан реального реестра); остаток 64 >300 — вход в burn-down P3.2 |
| 2026-07-12 | plan-exec/sonnet | P3.2 закрыт (фаза P3 2/2 🟢): validate.sh — DESC_WARN_MAX 450→300, новый DESC_ERROR_MAX=450 hard (burn-down не спасает); bootstrap scripts/desc-burndown.txt (64 скилла, ключ по пути bucket/name); one-way протухшая-запись warn; 4 негативных прогона на HEAD подтверждены (лог в Completion Notes P3.2) + новый test_desc_burndown_gate.py (6 тестов); validate.sh 372 теста, exit 0 |
| 2026-07-12 | plan-exec/sonnet | P4.1 закрыт (фаза P4 1/2 🟡): диета description всех 44 агентов 10 паков (1 example вместо 2-3 + анти-триггер одной фразой) — все ≤600B, backend-laravel сумма 9.2KB→3.4KB (≤3.5KB); patch-бамп версий + CHANGELOG во всех 10 pack.json; рендер-смоук всех 10 паков (`--dry-run`, rc=0) после правки; validate.sh 311 тестов OK |
