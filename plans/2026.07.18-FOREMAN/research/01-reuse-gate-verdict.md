---
type: research
plan: 2026.07.18-FOREMAN
item: P0.1
title: "Reuse-гейт вердикт — Artifex (супервизор unattended-исполнения планов)"
created: 2026-07-18
skills_run: [axioma:axioma-doctrine, architect:ecosystem-reuse-gate, axioma:axioma-stack]
radar: 02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md
supersedes: none
extends: D2
---

# Reuse-гейт: Artifex (пакет-супервизор unattended-исполнения мастер-планов)

Формальный прогон `axioma-doctrine` → `axioma-stack` → `ecosystem-reuse-gate`
против живого `02-Knowledge/00-Strategy/Ecosystem_Tech_Radar.md` (прочитан как
live-файл, не по памяти) для подтверждения предварительного вердикта D2
(build-new поверх нативного `claude -p`). Гейт прогоняется **per-unit по 6
функциям** Foreman/Artifex (нумерация — `findings/owner-deep-audit-skills-2026-07-18.md`
§Контекст) + мета-вердикт по пакету в целом.

## 0. Doctrine-прогон (axioma-doctrine, 5 столпов)

| Столп | Применимость к Artifex | Вывод |
|:--|:--|:--|
| 1. Горизонтальное ядро → вертикали | Artifex — не вертикальный продукт и не форк ядра; это **инфра-инструмент dev-цикла** экосистемы (как task/skiller/maind). Живёт в SKM, не в CoreX/AxiomaErpSdk. | Столп не диктует форк ядра — greenfield-инструмент |
| 2. Vendor-vs-build, reuse by default | Ядро гейта — см. §1–§3 ниже. Из 6 функций **3 переиспользуют** существующие механизмы экосистемы (auto-approve, run-report, agent-packs), build-new — только где сработало явное правило. | Reuse-дисциплина соблюдена |
| 3. AI-native / MCP-first | Artifex сам оркеструет AI-сессии (`claude -p`); LLM-доступ — через нативный CLI (провайдер-абстракция на уровне Claude Code), не прямой вызов вендора. Layer 3 inbox (P4.3) — MCP-канал отдельным процессом (D31). | Согласуется |
| 4. Offline-first + RU compliance | Не точка физического присутствия (не касса/ресторан); фискалка неприменима. Каналы эскалации (TG/MAX) учитывают RU-реалии (D12), но это не 54-ФЗ-констрейнт. | Неприменимо (нет физ-присутствия) |
| 5. Дистрибуция расширений через RegHub | Artifex раскатывается как **CC agent-pack** (harness-механизм, D40), НЕ через RegHub: RegHub = marketplace PHP/Dart-модулей продуктов, а не CC-хуков/скиллов dev-тулинга. Разные каналы, разные артефакты. | RegHub неприменим — иной класс артефакта |

**Doctrine-итог:** ни один столп не отменяет build-new; столп 2 (reuse-default) —
удовлетворён распределением 3 reuse / 3 build-new ниже.

## 1. Матч юнита против радара (axioma-stack §2)

Юнит «супервизор unattended-исполнения мастер-планов / headless-драйвер
CC-сессий» **в карте радара §2 отсутствует** (exact/close-match: not found).
Ближайшие по названию — и почему НЕ покрывают:

- `Маркетплейс/дистрибуция модулей → RegHub` (§2, строка 164) — дистрибуция
  бизнес-модулей продуктов, не исполнение планов и не CC-тулинг.
- `MCP-сервер/AI-tools → axioma_mcp / laravel/mcp` (§2, строка 152) — экспозиция
  инструментов агенту, не оркестрация dev-сессий.
- В §3 Gap-roadmap юнит **не значится** — экосистема дублирование ещё не
  фиксировала (Artifex — первый супервизор dev-цикла).

→ Записано «not found» (не silent-skip). Переход к per-unit прогону 7 правил.
Радар обновлять P0.1 **не обязан** (Scope: reuse-вердикт, не правка радара) —
внесение Artifex в радар как нового standalone-юнита = кандидат для отдельного
захода (Pending, см. §4).

## 2. Per-unit вердикты (6 функций, 7 if-then правил)

Каждый вердикт: юнит → verdict (сработавшее правило) — обоснование + цитата
радара/провенанс-реестра. Вердикты по КОНКРЕТНЫМ внешним репам НЕ дублируются из
`owner-deep-audit` (adopt/adapt/reference там) — здесь только гейт-класс
reuse/build-new и что доктрина/радар его не отменяют.

### Функция 1 — CLI-драйвер headless-сессий + парсинг статусов/handoff
**Вердикт: build-new (правило 4 + правило 3).**
Вендор durability/сессионного рантайма = сам `claude -p` (нативный CLI грузит
скиллы/хуки/CLAUDE.md как интерактив — factsheet §1/§6). Нужен доменный слой
ПОВЕРХ: парсер формата плана SKM (D-лог, machine-markers, `Items 🟢/всего`,
handoff/launch-block) + петля next/retry/escalate. Правило 4 («вендор закрывает
инфраструктуру, нужен DSL/контракт поверх → build-new тонкий слой НАД вендором»).
Правило 3 усиливает: `owner-deep-audit` §Функции-без-решений — «ни один внешний
проект не парсит именно этот формат» (нет вендора для домен-специфики) → тонкий
build-new, НЕ переизобретение рантайма. Внешние ralph-orchestrator (Rust,
adapt-архитектура) / claude-session-driver (JSONL-лог, adapt) — **референс
контракта петли**, не донор кода (D25: Python stdlib, не Rust-порт).
Правила 1–2 НЕ сработали: зрелого вендора «парсер плана SKM» нет (пр.1);
существующего пакета экосистемы под эту функцию нет (пр.2).

### Функция 2 — детекция прогресса и зацикливания
**Вердикт: build-new (правило 3).**
Дублирование заявлено (claudewatch / ralph-claude-code), но код не верифицирован
и вендора под «топтание на уровне multi-file diff между итерациями конкретного
плана» нет (`owner-deep-audit` §Функции-без-решений). → build-new на таксономии
mem0 (ADD/UPDATE/NOOP/CONFLICT — adopt-паттерн, §Часть1) + дуальное exit-условие
ralph-claude-code (adapt) + cost-aware сигнал `_usage.py` (reuse, см. функция 5).
Правила 1–2 не сработали (нет вендора/пакета экосистемы под progress-детекцию
плана). Тонкий build-new над сигналами журнала P1.1, не переизобретение AgentOps.

### Функция 3 — политика авто-подтверждения прав (PreToolUse)
**Вердикт: use-package / reuse-extend (правило 2).**
Функция **уже частично покрыта существующим механизмом экосистемы** — harness
`configs/claude-code/hooks/auto-approve/` (интегрированы oryband AST-разбор +
froggeric сегментация + yigitkonur ExitPlanMode; `owner-deep-audit` §2.1) в том
же рантайме (CC-хуки). Правило 2 («тот же тип функционала уже покрыт пакетом
экосистемы в том же кластере → use-package, консолидировать в существующий, не
новый»). → Artifex **РАСШИРЯЕТ** harness auto-approve (severity-теги, policy-хук
поверх), НЕ строит параллельный (D29). Детерминизм без AI-гейткипера (harness
сознательно отклонил froggeric stage-2 — CREDITS). Это ключевой reuse-вердикт:
build-new здесь был бы дублированием, которое гейт ловит.

### Функция 4 — боты-эскалаторы (TG + MAX, блокирующий Q&A, много каналов)
**Вердикт: build-new тонкий адаптер/хаб (правило 3).**
MAX-плагин (MAVII-RU/max-messenger-plugin, MIT) и claude-tg существуют
**раздельно**; единого канал-агностик слоя с общим блокирующим Q&A и envelope
нет ни у кого (`owner-deep-audit` §Функции-без-решений). Вендора под
«интеграционный слой нескольких каналов» нет → build-new тонкий hub
(канал-агностик `Channel` + escalation envelope, D31/D32). Layer 1 notify = stdlib
`urllib sendMessage` (тонкий build-new, D25). MAVII-RU / claude-tg — **референс**
для Layer 3 inbox (P4.3, отдельный процесс), НЕ импорт в stdlib-пакет (D31).
Правило 3, НЕ переизобретение мессенджер-SDK.

### Функция 5 — пер-плановый журнал исполнения
**Вердикт: build-new тонкий слой + reuse библиотеки (правило 4).**
Ближайший существующий механизм — harness `run-report` (`_lib.py` 28 КБ защитный
парсер транскрипта + `_usage.py` cost/usage; `owner-deep-audit` §2.2), покрывает
парсинг/durability. Нужен доменный слой поверх: маппинг `session_id ↔ plan_id +
item_id` (нативно CC сессии с планами НЕ связаны — факт архитектуры CLI, не пробел
инструмента) + пер-плановый append-only `journal.jsonl` (D20). Правило 4 (build-new
тонкий слой НАД вендором-механизмом, reuse `_lib.py`/`_usage.py` как библиотеки,
не переписывать парсер). Дом канона журнала — contribution в пакет `task` (P1.3–P1.4,
package-contribution-protocol), не в Artifex. «1 сессия = 1 item = 1 run-report»
(D15а) естественно решает схлопывание записей run-report.

### Функция 6 — упаковка и версионируемая раскатка скиллов/хуков
**Вердикт: use-package / reuse (правило 2).**
Версионируемая раскатка **уже решена зрелым механизмом экосистемы** — harness
`agent-packs` (render/upgrade/remove/lock `.claude/agent-pack.lock.json`,
upgrade-категории new/safe-apply/conflict/user-owned; `owner-deep-audit` §Часть3/Ф6).
Правило 2 → Artifex оформляется как **новый пак `artifex`** в существующем
механизме (D40), upgrade-drift получает даром; скилл `supervisor-protocol`
раскатывается своим каналом skiller (bucket general), профиль `artifex.json`
связывает оба. НЕ строить своё версионирование (ECC-стиль отвергнут, D40).
Правило 7-адаптеры (RegHub) неприменимы — иной класс артефакта (§0 столп 5).

## 3. Мета-вердикт по пакету в целом + сверка D2

**Юнит «Artifex как таковой» → build-new STANDALONE-пакет (правило 7).**
«Мощный cross-ecosystem концерн, потребляемый несколькими рантаймами/продуктами
за пределами одного ядра, крупный для отдельного проекта → standalone-пакет со
своим репо/философией, НЕ модуль ядра `corex/*`». Цитата радара §4 правило 7
(строка 226): *«Мощный cross-ecosystem концерн … → standalone-пакет со своим
репо/философией, НЕ модуль ядра `corex/*`; сам владеет своей vendor-стратегией»*;
прецеденты — [[AzGuard]], [[Chatom]]. Artifex потребляется **всей экосистемой**
(любой проект с мастер-планами: Brain, SKM, FlexCRM, EDUFY, …; Dart- и
PHP-контуры равно — оркеструет сессии CC, не код продукта) → тот же класс, что
task/skiller/maind (dev-тулинг SKM), а не corex/*-модуль.

**Сверка предварительного D2 против живого радара:**
- D2 (Cowork/Coder отвергнуты, нативные `--bg`/`/goal`/routines недостаточны,
  build-new поверх `claude -p`) — **радар не отменяет**: юнит в §2 отсутствует,
  в §3 Gap не значится, ни один существующий пакет/вендор экосистемы не покрывает
  unattended-исполнение планов.
- Reuse-дисциплина доктрины (столп 2) удовлетворена: **3 из 6 функций —
  reuse-extend существующих механизмов** (Ф3 auto-approve, Ф5 run-report, Ф6
  agent-packs); build-new — только Ф1/Ф2/Ф4, где сработали правила 3/4 (нет
  вендора под домен-специфику формата плана / progress-детекции / канал-хаба).
- Нет юнита, покрываемого существующим пакетом экосистемы (не внешним репо),
  который Artifex бы дублировал → эскалация к владельцу (Code Guidance) НЕ
  требуется: гейт не выявил внутриэкосистемного дубля.

**Итог: D2 подтверждён формально.** Vendor-vs-build reuse-default соблюдён;
`build-new` per-unit несёт ссылку на сработавшее правило; ни один build-new не
выдан без прохода правил 1–2 (запрещённый shortcut скилла не допущен).

## 4. Сводная таблица (grep-anchor: reuse / adapt / build-new)

| # | Функция | Verdict | Правило | Reuse-донор экосистемы |
|:--|:--|:--|:--|:--|
| 1 | CLI-драйвер headless + парсер плана | build-new (тонкий над `claude -p`) | 4 (+3) | нативный CLI; adapt ralph-orchestrator/claude-session-driver |
| 2 | Детекция прогресса/зацикливания | build-new | 3 | adopt mem0; adapt ralph-claude-code; reuse `_usage.py` |
| 3 | Авто-подтверждение прав | reuse-extend (use-package) | 2 | harness auto-approve (расширить, D29) |
| 4 | Боты-эскалаторы (TG+MAX, Q&A) | build-new (тонкий hub) | 3 | reference MAVII-RU/claude-tg (Layer 3) |
| 5 | Пер-плановый журнал | build-new тонкий слой | 4 | reuse run-report `_lib.py`/`_usage.py`; канон → пакет task |
| 6 | Упаковка/раскатка | reuse (use-package) | 2 | harness agent-packs + skiller (D40) |
| — | **Artifex (пакет)** | **build-new standalone** | **7** | дом SKM (как task/skiller/maind) |

Pending (вне Scope P0.1, не блокирует закрытие): внесение Artifex как нового
standalone-юнита в `Ecosystem_Tech_Radar.md` §2 (карта) — отдельный vault-заход,
чтобы будущие проекты видели его в реестре.
