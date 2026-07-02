# Changelog

## [Unreleased]

### Added (SKM-MASTER-002, волна 2 — каталог патологий · стек-пак laravel-package + пилоты)

- **Каталог патологий (фаза C):** `core/pathology.py` — чистый защитный детектор workflow-патологий
  (`detect(run_report) → findings {code, severity: info|attention, metric, threshold, evidence}`),
  10 детекторов: file-reread, tool-error-loop, no-op-run, no-verify (+`no-verify-devloop`),
  cache-miss, overthinking, retrieval-stuffing, protected-write, static-context, fanout; пороги —
  константы с честной пометкой «эвристики, не откалиброваны» (36 тестов). Маршрутизация строго
  Detect ≠ Gate: `maind analyze` — `pathology_slice` (attention → reasons/ATTENTION, info → секция
  «Эффективность»; RED от патологий невозможен, инвариант в докстрингах); `analyst digest` —
  извлекатель `extract_pathologies` с правилом рецидива (окно 5 последних run-report'ов, урок
  только при ≥2 попаданиях кода; разовая патология — сигнал analyze, не урок), в уроки идут только
  4 кода с готовой ремедиацией. Каталог-док `packages/analyst/docs/guide/pathologies.md`
  (все классы, формулы/пороги = константы кода, remediation, честная колонка «детектируемо/добор»).
- **Стек-пак `laravel-package` 0.1.0 (фаза F):** отдельный пак для Laravel-ПАКЕТОВ
  (composer library / монорепо пакетов) — reviewer с центром «публичный контракт» (Public API/
  BC-SemVer + roave/bc-check, register-vs-boot, publishables, `env()` вне config → HIGH,
  composer-констрейнты, Testbench, multi-version matrix), slice-builder («фича пакета»,
  @internal/final), test-writer (Testbench + version_compare-ветки), новый recon `api-surface`,
  4 rules, dev-loop-форк (risk-adaptive сохранён, +public-api маркер, preflight
  `composer validate --strict`). Анти-дубль двумя слоями: движковый **`src_pack`** в files[]
  (review-gate.sh/env.ini/settings.fragment — байт-в-байт из backend-laravel без копий) +
  **parity-тест shared-блоков** `test_agentpacks_shared.py` (6 блоков прозы reviewer'а размечены
  `<!-- shared:X -->` в обоих паках, дрейф = красный тест). Новая команда **`harness agent-packs
  remove`** (чистые файлы удаляются, modified/user_owned/merge остаются с warn, lock атомарно).
  `backend-laravel` 0.11.2 — shared-разметка + фикс `app/Repositories` → `{{ACCESS_ROOT}}/…`.
  Профиль `php-package` получил `agent_pack: ["laravel-package", "_common"]`; roadmap
  `php-package-stack-pack.md` → «реализовано»; доки harness + docs/reference.md (roave — adopt;
  spec-kit/beads/planning-with-files — reference).
- **Пилоты (фаза F, rendered в рабочих деревьях azguard/chatom, там не коммитим):** azguard —
  remove backend-laravel → render laravel-package чисто + 4 доменных оси в
  `.claude/rules/azguard-reviewer-overrides.md` (panel_id isolation, epoch-invalidation,
  wildcard semantics, extension API idempotency) + path-scoped `azguard-domain.md`; chatom
  (монорепо `packages/*/src`) — та же миграция с `HAS_MIGRATIONS=true`/Pest. Acceptance-грепы
  app-канона по обоим — 0 попаданий; `doctor --drift` чисто. Регрессия непилотных (F-8):
  upgrade-канал 0.11.0→0.11.1 (worktree-эмуляция «до headers») — 0 conflict; dry-run на живом
  app-проекте — conflict'ы только от реальных ручных правок generated-core (ровно тот паттерн,
  который теперь ловит ось `generated-core-edited`).

### Fixed (полевые находки пилотов волны 2 — движок agent-packs)

- **`_probe_allowed` резал детект-пробы по `;` без понимания кавычек** — проба
  `PACKAGE_NAMESPACE` (php -r) тихо skip'алась при `shell_policy=safe` и переменная
  оставалась пустой; проба переписана одним PHP-выражением без `;` (терминатор `?>`),
  плюс фолбэк на `packages/*/composer.json` с кратчайшим psr-4 (монорепо-кейс).
- **`categorize_file_change`: файл пака в lock, но отсутствующий на диске**, при upgrade
  давал бесполезный `conflict`/`*.pack-new` вместо простой установки → теперь `new`/
  `new-optional` (missing + base-unchanged остаётся `nochange`). +2 теста.
- **`do_render` не переписывал lock при `changed=False`**, даже если у файла реально
  сменился флаг `local_modified` (внешняя реконсиляция файла к базе пака) — `doctor`
  вечно показывал протухший `modified: true` → lock пишется при отличии свежей записи
  от сохранённой. +1 тест.

### Added (SKM-MASTER-002, волна 1 — plan-протокол · токен-телеметрия SCHEMA=2 · защита generated-ассетов)

Мастер-план `plans/SKM-MASTER-002` (операционная система планов): сильная модель проектирует,
дешёвая исполняет, телеметрия делает утечки токенов видимыми, generated-ассеты защищены.

- **Plan-протокол (фаза A):** скилл `general/plan-protocol` (SSOT: схемы `plans/<ID>/{plan.md,
  phases/Pn.md,handoff.md}`, 6 канонических статусов, rolling handoff, routing-матрица
  model/effort, эскалация с greppable-артефактами) + snippets-шаблоны; 4 команды
  `/task:plan-{design,exec,close,audit}` с пинами (opus/high · sonnet/medium · sonnet/low ·
  opus/xhigh); детерминированный `plan-lint` (`packages/task/lib/task/plan_lint.py` + тонкий
  `scripts/plan-lint.py`, 45 тестов) и первый `validate.sh` пакета task; сам мастер-план
  транскрибирован в `plans/SKM-MASTER-002` (dogfooding, lint зелёный).
- **Токен-телеметрия end-to-end (фаза B):** `core/usage.py` — единый самодостаточный
  транскрипт-парсер usage (вендорится байт-в-байт в хук как `_usage.py`; `sync-usage.sh` +
  cmp-гейт в validate.sh harness — дрейф копии валит валидацию); run-report **SCHEMA=2**
  (only-additive: `usage` per-agent включая sidecar-субагентов, `reads`, `error_loops`,
  `retrieval`, `protected_writes`); тренд `.claude/analyze/usage-trend.ndjson` (~200 байт/сессия,
  ретеншн 4000→2000); `skiller analyze-run` переведён на `core.usage` (суммы идентичны,
  регресс-фикстура); `maind analyze` — блок tokens (сессия vs медиана K=20/p90 тренда + pinned
  `baseline.json`), регрессия токенов → ATTENTION (RED от токенов невозможен); `harness doctor`
  детектит протухший установленный хук. USD сознательно не считаем — сырые токены model-keyed.
- **Защита generated-ассетов (фаза E):** детерминированный provenance-header
  `swissknifeman:generated` (Pack@version/Template/Edit-policy/Extension-points, БЕЗ timestamp —
  хеш вместе с header, матрица `_decide`/`categorize_file_change` не тронута) во всех rendered
  файлах паков; `user_owned` в lock (schema 1, аддитивно); `harness agent-packs doctor --drift
  [--strict]` + самодостаточный `pack_drift` в `maind analyze` → ATTENTION при локальной правке
  generated-файла; overlay-модель расширения (`.claude/rules/<prefix>-reviewer-overrides.md`,
  user_owned, `role:override`) во всех стек-паках + правило `_common/rules/generated-assets.md`
  + ось `generated-core-edited` (HIGH) в reviewer'ах + HARD_GATES в dev-loop. Бампы паков:
  `_common` 0.4.0, `backend-laravel` 0.11.1, `node-frontend`/`python-backend`/`dart-flutter`
  0.4.1, role-паки +0.0.1.

### Added (output-style=lean + skills-catalog — автоматическая раздача на все проекты)

- **`skiller integrate` ставит `output-style lean` во ВСЕХ бандлах** (`minimal`/`recommended`/
  `full`/`custom`, дефолт `True`) — новый блок `_block_output_style` делегирует `harness hooks
  --output-style lean` (по образцу `_block_autoapprove`/`_block_memory`). Раньше терсе-голос
  агента был чисто ручной операцией (`harness hooks --output-style lean`), ни одна из точек
  входа (`maind onboard`, `skiller integrate`) его не вызывала — capability `env:hooks` в
  `orchestrate.py` не имела ни одного вызывающего. Токен-экономия нужна «для всех проектов»
  независимо от объёма остальной автоматизации бандла — единственный пункт, включённый и в
  `minimal`.
- **`maind sync` — два новых провиженера** для уже онбордженных проектов (закрывают
  тот же разрыв ретроактивно, без полного re-onboard): `output-style` (тот же `env:hooks
  --output-style lean`, опт-аут per-project `project.output_style: "off"` — иначе регулярный
  `maind sync --all` затирал бы локально выбранный стиль) и `skills-catalog` (`skiller update`
  — пере-резолв buckets/exclude с диска, поэтому новый скилл уже выбранного бакета, например
  `php/pao`, доезжает до давно онбордженных PHP-проектов без ручного `skiller update`/`connect`/
  `vendor`). Оба — в дефолтном наборе `--all`.
- **`skm:update` добавлен в `orchestrate.DRY_CAPABLE`** — `skiller update` умеет свой честный
  `--dry-run`, теперь `maind sync --dry-run` даёт реальный превью для `skills-catalog`, а не
  fake print+rc0 (та же ловушка, которую `DRY_CAPABLE` уже чинил для `agent-pack`).
- Контекст: `php/pao` (агентно-оптимизированный вывод PHPUnit/Pest/PHPStan для PHP-проектов) уже
  входил в дефолтный профиль `php-package`/`laravel-project` и доезжал на новых онбордингах;
  реальный `composer require laravel/pao --dev` **сознательно не автоматизирован** нигде (мутация
  `composer.json`/`composer.lock` без подтверждения человека) — агент выполняет его сам по
  инструкции скилла, когда реально начинает гонять тесты («skill-on-demand»).

### Fixed (пакет `skiller` — аудит registry/budget/vendor/connect: дублирование, ложно-зелёные гейты, надёжность)

По итогам `research/Глубокий аудит пакета skiller (registry-budget-vendor-connect).md` (22 находки,
все закрыты — код-фикс либо документированный осознанный отказ от фикса, если он ломал существующий
инвариант).

- **R-1 [CRITICAL] — токен-экономия `connect` подтверждена, не предположена.** Комментарий в
  `registry.py` утверждал «подтверждено докой Claude Code v2.1.x» без реальной проверки. RAG
  (perplexity-web + прямая цитата `code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries`):
  для marketplace-записи, чей `source` резолвится в корень marketplace, явный `skills[]`
  **заменяет** дефолтный скан, а не дополняет его — риска резидентной загрузки всех 219 SKILL.md
  репозитория нет. Комментарий переписан с точной цитатой и датой проверки.
- **V-2/V-3 [HIGH] — ложно-зелёные install/lock (`vendor.py`, `skillset.py`).** `safe_copy_skill`
  мог вернуть `False` (containment-стоп/TOCTOU-гонка) — пропуск тихо проглатывался, `sync`/`vendor`
  рапортовали план как факт. Теперь считаем и печатаем ФАКТ (`plan['installed']`/`skip_copy`).
  Структурно битый `skills-lock.json` (не путать с легитимно пустым после ручной чистки — тест
  `test_manual_lock_cleanup_*` остался зелёным) восстанавливает managed-набор из манифеста, а не
  обнуляет его.
- **V-1 [HIGH] — дубль резолва `requires`.** `skillset._pull_requires`/`vendor.resolve_requires`
  были независимыми, уже разошедшимися BFS (RU/EN тексты warn) — сведены к общему
  `common.resolve_requires_bfs` с адаптером источника узла (FS-кортеж / registry-entry).
- **V-4/V-5 [MEDIUM] — дубли writer'а манифеста и сбора бакетов.** Единый
  `common.write_skill_manifest` (было два независимых писателя с разной схемой: date-only без
  `version` у vendor, `now_iso`+`version` у skillset). Сбор бакетов (FS-rglob vs registry) оставлен
  архитектурно раздельным (осознанно — принудительное слияние ввело бы жёсткую зависимость `vendor`
  от прогнанного `skiller registry`), но добавлен golden-тест паритета (`test_channel_parity.py`),
  ловящий будущий дрейф каналов.
- **B-1/B-2 [MEDIUM] — калибровка токен-оценки + недобор в `--check-core`.** Константы
  `CHARS_PER_TOKEN_CYR/LAT` (2.2/4.0) откалиброваны по RAG (perplexity, 3 источника: ~2.9 для
  кириллицы, ~3.4 компромисс EN-прозы/кода) — старые занижали RU-токены и завышали code-heavy тела.
  `budget --check-core --strict` теперь фейлит и на НЕДОБОРЕ CORE-скиллов (переехавший/опечатанный
  путь раньше молча УМЕНЬШАЛ резидент, гейт «зеленел» вместо ошибки). Пересчёт по калиброванным
  константам вскрыл реальный факт: резидент CORE (8 скиллов) — 696 ток, что честно превышает старый
  target 600. `resident_budget_target` поднят до 750 в `configs/core-policy.json` (осознанное
  решение, не откат калибровки).
- **R-2 [MEDIUM] — drift-гейт не видел `graph.md`/`budget.md`.** `scripts/generate-graph.sh` (bash+
  heredoc) портирован в `registry.render_graph`/`write_graph` (in-process, без subprocess) — теперь
  `registry.check_drift` сравнивает оба артефакта, а не только `skills.json`/`_index.md`/манифесты.
  Старый shell-скрипт оставлен в дереве с deprecation-шапкой (`rm` заблокирован политикой окружения
  сессии — безопасно удалить вручную: `git rm packages/skiller/scripts/generate-graph.sh`).
- **V-6 [MEDIUM] — диагностируемость частичной копии при краше.** Конфликт с sha256, совпадающим с
  реестром (похоже на прерванный sync), теперь получает отдельное сообщение с явной подсказкой
  «`--force` безопасно» вместо пугающего «занят чужим скиллом». Авто-усыновление НЕ включено —
  сломало бы тестируемый инвариант «ручная чистка lock требует `--force`».
- **C-1/C-3 [MEDIUM/LOW] — `connect.py`.** Пропуск CORE-плагина при необъявленном marketplace
  (`--no-core` не задан) теперь явный `warn`, не тишина. `DEFAULT_COMMAND_PLUGINS` покрыт тестом.
- **U-1 [MEDIUM] — `update --all` не падает на битом манифесте.** Необёрнутый `json.loads` ронял
  необработанным исключением весь батч на первом же проекте с битым `.swissknifeman-manifest.json`
  (не ловится `except SystemExit`). Тот же класс дефекта найден и починен в `vendor.load_manifest`
  (регрессия всплыла через тест на `update --all`).
- **Doc-1/Doc-2 [MEDIUM/LOW] — `doctor.py` не диагностировал harness.** Добавлена проверка
  `harness_bin` + лёгкий `harness --help`-пробинг: отсутствие — не FAIL (опциональная зависимость),
  поломка — FAIL. Schema-check в doctor раньше сверял только имена ключей (`⇄ ключи`), теперь и типы
  (`⇄ типы`) — паритет с `test_schema.py`.
- **Т-2 [MEDIUM] — устаревшая цифра CORE («7 ≈ 480 ток») везде.** Синхронизировано (`connect.py`,
  `config.py`, `CLAUDE.md`, `docs/guide/{archetypes,skills-architecture}.md`) на актуальный факт
  (8 скиллов) без хардкода нового снапшота — указывает на `skiller budget --check-core` как источник
  истины, чтобы не протухнуть повторно.
- **V-8/V-9 [LOW] — надёжность.** Битый `boost.json` в `lock._boost_skills` теперь warn, не тихий
  `[]`. Смена `skills_path` в конфиге больше не оставляет осиротевшую копию по старому пути (новый
  проход prune по `installed_path` из lock).
- **B-3/B-4/R-3/R-4 [LOW] — точечные.** Детектор кириллицы расширен на Cyrillic Supplement
  (U+0500–052F). `_split_frontmatter`/дубль-«мёртвая» ветка имени в `registry.py` — документированы
  как осознанные, не слиты/не удалены (реальной пользы от слияния не было, риск — был).
- **Тесты:** +18 unit-тестов (233 всего, было бы больше номинально — часть находок покрыта
  расширением существующих ассертов), включая новый `test_channel_parity.py`. `validate.sh` зелёный
  (`skiller registry` перегенерирован, `registry --check` чист).

### Changed (дисциплина: RAG-делегирование + подробность плана/хендоффа)

- **RAG-ступень не делегируется тул-бедному субагенту** (канон `general/verify-claims` — новый
  подраздел «Делегирование: не ронять ступень»; указатель в root-скилле `decision-verification`;
  клауза в `CLAUDE.md` «Методология решений»). Первопричина: верификация внешнего факта была
  делегирована субагенту `claude-code-guide` (тулсет без `perplexity-web`) → лестница молча
  просела до `WebSearch`. Правило: RAG-ступень исполняется там, где доступен приоритетный движок;
  делегируешь — делегат обязан нести `perplexity-web`/`context7`, иначе держи проверку в основном
  контексте (делегировать МОЖНО, ронять ступень молча — нельзя). **Регресс-гарант** — новый
  pressure-кейс в `verify-claims/evals/pressure.json` (ловит соблазн через `skiller eval`).
- **Контракт `task`-пакета: план максимально подробный, хендофф короткий** (`task/design.md`,
  `task/dev.md`). План — самодостаточный (всё для исполнения В ФАЙЛЕ, переживает падение сессии),
  не «коротко по фазам»; спорное → отдельный блок `## Обсуждение` в плане (плюсы/минусы + явная
  рекомендация), а не popup; хендофф на `/task:dev` — короткая ссылка на план, не бриф на 2 страницы;
  `AskUserQuestion` — крайний случай и всегда с рекомендованным вариантом.

### Added (пакет `analyst` — P4: cross-project паттерн → ЧЕРНОВИК скилла)

- **`analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]`**
  — детерминированный (stdlib, on-demand) мост `scan` → переиспользуемый скилл: читает **только**
  абстрагированный индекс `index/by_pattern/<id>.json` и генерит staged-ЧЕРНОВИК
  `~/.swissknifeman/analyst/drafts/<pattern_id>/` = `SKILL.ru.md` (RU-источник-заготовка с
  frontmatter-скелетом + инертный провенанс-штамп) + `draft.meta.json` (паспорт + `seed_sha256`).
  **Инвариант удержан:** НЕ пишет в `skills/`, НЕ генерит EN-канон, НЕ регистрирует, НЕ раскрывает
  raw/секреты (приватность СТРУКТУРНА — индекс уже абстрагирован). Промоут в бакет — человек; вывод
  печатает **точную** repo-grounded последовательность skiller (mkdir → `claude-canon-from-ru.md` →
  `check-translations.sh --stamp` → `validate.sh` → `skiller registry`).
- **Edit-safety (идемпотентность):** ре-suggest не затирает ручные правки — `seed_sha256`-детект
  (тело == последнего сгенерённого → перегенерим; правлено руками → тело не трогаем, освежаем лишь
  провенанс meta; `--force` перезаписывает). Осиротевшие черновики (паттерн исчез) — **WARN, не
  delete** (≠ scan-prune: черновик человеко-редактируем).
- **Гейты:** `name`-кандидат по офиц. правилам скиллов (≤64, `[a-z0-9-]`, без ведущих/хвостовых
  дефисов и reserved `claude`/`anthropic`; кириллица не образует name → латинский токен/`skill`,
  финализирует человек); `--min-weight` (индекс не несёт confidence → `--min-tier` отложен, D7).
  Чистые генераторы (`build_skill_ru`/`build_meta`/`_slug_name`) + writer с I/O в `cmd_suggest`;
  +13 offline-тестов. Дизайн: [`roadmap/analyst-suggest-draft-skill.md`](roadmap/analyst-suggest-draft-skill.md).
  Заодно исправлены устаревшие указатели «промоут = `skiller integrate`» в `scan.py`/CHANGELOG
  (integrate вшивает скиллы В проект, не регистрирует новый).
- **Документация пакета `analyst`** — добавлен `packages/analyst/docs/` (VitePress: index + guide
  cli/lifecycle/suggest + architecture + roadmap) и линковка в зонтичный сайт (`scripts/docs-sync.sh`,
  корневой `docs/.vitepress/config.mts` nav+sidebar+Пакеты, `docs/routing.md` слой «Обучение»,
  `.gitignore`). Standalone и агрегатный build зелёные. Раньше analyst был единственным пакетом без
  своих доков.

### Added (пакет `analyst` — P1 MVP + P2 scan: continuous learning, слой-1)

Новый четвёртый пакет монорепо **`analyst`** (CLI `analyst`, плагин-только-команды) — детерминированный
(stdlib-only, **on-demand, без демона**) слой захвата «выстраданных уроков» из прогонов Claude Code с
**человеком в гейте** (авто-запись в скиллы запрещена). Реализует P1 контура continuous learning:

- **`analyst digest`** — детерминированно извлекает КАНДИДАТ-уроки из свежего `run-report` прогона по
  высокоточным сигналам (resolved-failure «сработало после N попыток»; явные dev-loop workarounds) →
  `.claude/analyst/lessons/ephemeral/` (LOCAL). Не «угадывает инсайты» — осознанная граница MVP.
- **`analyst review`** — уроки по состояниям (ephemeral/candidate/curated/deprecated) + structured diff
  против активных (Jaccard, stdlib). Read-only.
- **`analyst promote <id>` / `deprecate <id>`** — конвейер `ephemeral→candidate→curated` с **человеко-гейтом**
  (переход в curated — только явное согласие: confirm на tty либо `--yes`); curated всплывает в память
  mAInd (`maind memory remember`, graceful — демон лёг → урок на диске, повторим позже). Soft-деприкейт.
- **Провенанс:** каждый урок несёт `source`/`session_id`/`scope`/`evidence`; каждый переход — запись в
  append-only `.claude/analyst/audit.ndjson`.
- **`analyst scan` (P2)** — cross-project агрегатор: пакет сам обходит реестр `config.json:projects[]`,
  читает per-project уроки, greedy-Jaccard-кластеризует и детектит паттерны, повторяющиеся в **≥N
  проектах** (по умолчанию 3) → draft-**предложения** (не скиллы!) в `~/.swissknifeman/analyst/suggestions/`
  + индекс `index/by_pattern/`. **Namespace-изоляция** (наследуется от maind): уроки кластеризуются
  только среди проектов, делящих namespace — паттерн из `ns:axioma` не течёт в чужой. Детерминизм
  (сортировка по id). Черновик скилла из предложения — `analyst suggest` (P4); промоут в бакет — человек.
- **Обвязка:** root-router `swissknifeman analyst …` + `doctor` fan-out; зонтичный `install.sh`;
  marketplace-запись (авто-подхват `skiller registry`). `Env(BaseEnv)`, atomic JSON, тесты offline (37).
- **Реконсиляция `analyst scan` (P2-долг закрыт)** — после записи артефактов детерминированный прун
  осиротевших `index/by_pattern/<id>.json` + `suggestions/<id>.md` (паттерн исчез: проект disabled/удалён,
  урок deprecated, кластер упал ниже порога). Прун СТРОГО в scope прогона: `scanned_namespaces` =
  `{--namespace}` если задан, иначе union namespace всех enabled-проектов; чужой namespace не рескан →
  его файлы не трогаются (классификация — из ПОЛЯ `namespace` индекса, не из имени файла; битый индекс →
  SKIP, не удаляем и не роняем scan). Флаги: `--no-prune` (прун по умолчанию ВКЛ), `--dry-run` (только
  would-prune, ничего не удаляет); `pruned:[…]` в `--json`, «снято сирот: N» в human. Нестандартные
  `--min-projects/--threshold` авто-прун пропускают (защита от churn). Чистые `stale_pattern_ids` (тесты
  без I/O) + `list_existing_patterns`/`prune_artifacts`; +11 offline-тестов (adversarial S2).
- Отложено на P5 (по дизайну, не долг): скилл `analyst-capture` + `observe.sh` PostToolUse-поток.

### Added (пакет `analyst` — P3: confidence-жизненный цикл)

Реализует **P3** контура continuous learning: детерминированный,
**восстановимый-из-логов** пересчёт уверенности урока + **числовая** state-machine, **без демона**
(on-demand) и **без нарушения инварианта** «`candidate→curated` — только человек».

- **`events.ndjson`** (новый append-only поток сигналов, рядом с `audit.ndjson`) — `digest`/`promote`
  дописывают скаляры наблюдений (`sessions_total/success`, `tests_total/passed`). Источник истины
  пересчёта: снапшот воспроизводим только из этого лога.
- **`confidence.py`** — ЧИСТАЯ арифметика (stdlib, без I/O/часов, тестируемая по точкам): Beta-среднее
  `p=(S+α)/(N+α+β)` × volume `(1−e^{−N/k})` × time-decay `λ^days`; тиры применения
  `0.3` tentative · `0.5` moderate · `0.7` strong · `0.9` core. Константы (`α=β=1`, `k=20`, `λ=0.95`
  ≈ полураспад 14 дн, bucket=1 день) — **тюнинг-параметры модуля** (калибруются по false-positive rate).
- **`analyst recompute [--now ISO] [--dry-run] [--json]`** — читает `events.ndjson` → decay по времени →
  агрегат `S/N` (+ `S_decayed`/`N_decayed`) → `confidence` → числовая state-machine → **атомарный** снапшот
  в урок (аддитивные поля, P1-схема не ломается). Детерминирован и восстановим (при фикс. `--now`). Гейты:
  `ephemeral→candidate` — **авто** при `N≥15 && conf≥0.6 && tests_total≥1`; `candidate→curated` — **всегда
  человек** (числа лишь помечают «готов», авто-переход запрещён — инвариант P1); просадка `conf<0.6` →
  **soft-deprecate** (файл не удаляется).
- **mem0-консолидация в human-gate** — `review`/`promote` считают таксономию **ADD/UPDATE/NOOP/CONFLICT**
  (Jaccard по trigger/action, stdlib) против активных. Противоречие (та же ситуация, иное действие) →
  **flag-and-ask** (промоут блокируется до явного `--supersedes ID` | `--force`, авто-резолва нет).
  `--supersedes` — **soft-invalidate** замещаемого (`supersedes`/`superseded_by`+timestamp, move в
  deprecated, файл сохранён).
- **Обвязка:** `recompute` в `cli.py`/`bin/analyst`/`commands/analyst.md`; тесты offline (+33 = 70).
  Демона нет. Реальный round-trip surfacing в память mAInd — проверен ещё в P1.

### Docs (аналитика и continuous-learning в витрине README + раннбуке)

Витрина не упоминала аналитику/самообучение, хотя реальный слой уже есть, а полный контур —
спроектирован и в roadmap. Отражено честно (real vs roadmap):

- **README** — строка «📈 Аналитика и обучение»: реальное (захват `run-report` → `maind analyze`
  с метриками памяти/графа; экспериментальный `session-observer`; петля `field-feedback-loop` с
  ручным промо) + кросс-проектный **Continuous Learning** помечен как спроектированный/roadmap
  (ссылки на `roadmap/self-learning-memory.md` и дизайн `research/analyst-package-design.md`).
- **`docs/develop.md` §9** — блок «Самообучение — контур и статус»: ручная петля с человеком в гейте
  сейчас; автоматический кросс-проектный контур — отложен (confidence + ручное промо как guardrail).

### Added (developer-раннбук + витрина README + наблюдаемость памяти/графа)

Документация процесса разработки отставала, а память/граф mAInd были «чёрным ящиком» (пишет ли,
читает ли, помогает ли — померить нечем). Разобрано чтением кода + RAG-верификацией внешних фактов
(нативная авто-память Claude Code и семантика `/compact` — офиц. доки; Serena-инструменты — context7).

- **`docs/develop.md`** — единый operator-раннбук «Разработка с Claude Code + swissknifeman»: фазы
  плана, `/compact` vs новая сессия (канон по офиц. докам), task-плагин, роли/agent-packs, токен-рычаги,
  **демистификация памяти** (два слоя: agentmemory-демон vs нативная память Claude Code) и **графа**
  (ручной скан + pull-модель), измерение эффективности, RAG-лестница, сценарии-FAQ. Спина-коннектор —
  ссылается на глубокие доки, не дублирует. Врезан в VitePress (nav + sidebar `/develop`).
- **README → витрина** — feature-обзор «что даёт» (плагины+скиллы, роли+workflow, токен-рычаги,
  задачи, память+граф, окружение, RAG) вместо повтора CLAUDE.md; заметная ссылка на раннбук.
- **Наблюдаемость памяти/графа** (отвечает на «работает ли или просто жрёт токены»):
  - run-report (`_lib.py`) считает вызовы `maind_memory_*`/`maind_graph_*` из транскрипта (матч по
    хвосту после `__` — переживает `mcp__maind__`/`mcp__plugin_core_maind__`) + найдено фактов/соседей →
    аддитивный ключ `maind` (SCHEMA не бампан, back-compat со старым `analyze`).
  - `maind analyze` показывает `память: recall×N→M · граф: query×K` и подсвечивает **«код-граф не
    использовался при тяжёлом сканировании»** (косвенная эвристика: много Read/Grep/Glob при графе ×0).
  - `maind memory count [--project]` — сколько фактов в памяти по scope (по scope-маркеру, не весь пул).
- **graph-first nudge** — скилл `ecosystem-mcp` (maind) теперь явно советует граф/Serena
  `find_symbol`/`get_symbols_overview` перед широким `grep` (с оговоркой про ручной скан/устаревание);
  кросс-ref из `context-economy` (лестница рычагов).

### Added (token-economy — base deny-rules для крупных артефактов; трек A план-A ROI-1)

Токен-экономия (аудит `research/swissknifeman-token-audit.md`): большие низкоценные файлы не должны
попадать в контекст через случайный `Read`/glob. Расширен `permissions.deny` в
`configs/claude-code/settings.base.json` (был только `.env`/keys/ssh/sudo): добавлены
`Read(**/CHANGELOG.md)`, `Read(**/skills.json)`, `Read(**/package-lock.json)`,
`Read(**/composer.lock)`, `Read(**/*.lock)` — анкорены `**/` (матч на любой глубине downstream).
- **Behavior change:** `**/*.lock` теперь запрещён на уровне base (subsumes laravel-пресетный дубль;
  merge аддитивен и дедуплит точные совпадения). Пресеты стеков без изменений.

### Added (maind analyze — пост-ран разбор прогона «всё ли сработало» + SessionEnd-хук run-report)

Field-feedback: после задачи-с-планом (напр. на azguard) нужно через логи проверить, всё ли отработало,
но источники исхода читались по отдельности — единой команды не было. Верификация механизма захвата —
целиком через `perplexity-web` (нашла 2 ошибки первого черновика: транскрипт — first-class артефакт,
парс поддерживаем; SessionEnd-хук может писать отчёт generic'ом → правка `dev-loop.js`/паков НЕ нужна).

- **Хук `run-report` (SessionEnd, harness)** — `configs/claude-code/hooks/run-report/`
  (`run-report.py` + `_lib.py`): строчно (без слурпа) и защитно парсит транскрипт → пишет
  `<project>/.claude/runs/<sid>.json` (тесты/линт с `ok` из `is_error`, изменённые файлы, tool-провалы,
  воркфлоу, best-effort dev-loop `tool_failures`/`deferred`/`workarounds`). Generic — любая задача, не
  только dev-loop. Никогда не барьер (ошибка/битый stdin → exit 0). Ретеншн `RUNS_KEEP`.
- **`harness hooks --run-report on|off`** (`block_run_report`) — env.ini (ENABLED/RUNS_KEEP) + merge-only
  регистрация SessionEnd. `apply-permissions.sh --global` копирует `run-report/` в `~/.claude/hooks`.
- **`maind analyze [--project|--cwd] [--session] [--base] [--json] [--no-health]`** (новый
  `lib/maind/analyze.py` + `cli.py` + `bin/maind` whitelist + `commands/analyze.md`): агрегирует
  run-report (первично) + bash-лог (форензика, БЕЗ кодов возврата — честно) + observer + git + health →
  вердикт **GREEN/ATTENTION/RED** (+`confidence` low, если run-report нет). Смычка с RAG: dev-loop
  `tool_failures` → блок «**Непроверено → ПОВТОРНЫЙ ПРОХОД**». RED → exit 1 (гейт для скриптов).
- Тесты: `harness/tests/test_run_report.py` (+12: парсер, поведение хука, ретеншн, block_run_report),
  `maind/tests/test_analyze.py` (+11: вердикт, поиск run-report, форензика, сборка+JSON).
  **Честные лимиты:** схема транскрипта не заморожена → парс защитный; bash-лог без pass/fail;
  SessionEnd = 1 запись/сессия; `devloop`/observer — best-effort.

### Added (intent-router — свободный текст → оптимальная команда; активация roadmap-хука)

Field-feedback: владелец забывает ставить задачи через `/task:*` (замеренный мисроут → триггер
активации отложенного `roadmap/agent-command-router-hook.md`). Верификация капабилити — целиком через
`perplexity-web` (нашла 2 ошибки в исходном плане: auto-run первоклассный через `SlashCommand`;
SessionStart-политику слать через `additionalContext`, не `systemMessage`).

- **Пара Python-хуков `agent-router`** (первый Python-хук репо):
  `configs/claude-code/hooks/agent-router/` — `session-policy.py` (SessionStart инжектит статическую
  политику роутинга через `additionalContext`) + `router.py` (UserPromptSubmit: keyword-прескор →
  крошечная idempotent-подсказка при score≥THRESHOLD, иначе тишина; escape-hatch `~`). Гибрид:
  прескор — bias, финальную классификацию (вопрос vs задача) делает модель. Никогда не барьер.
- **`harness hooks --router propose|auto_dispatch|off`** (`block_router`) — включает пару хуков
  per-project (env.ini + merge-only регистрация UserPromptSubmit+SessionStart).
- **`harness router --generate --target P`** (новый модуль `lib/harness/router.py` + `cli.py`) —
  генерит `.claude/agent-router.config.json` из `/task:*` + `.claude/agents/*.md` + локальных
  `.claude/skills/*/SKILL.md` (низкий вес — бэкстоп). Зонтичный `swissknifeman env router` даром.
- **maind:** `env:router` capability + провиженер `router-config` в `maind sync` (opt-in: генерит
  каталог только для проектов с включённым хуком; идёт после `agent-pack`).
- **Глобальная раздача:** `apply-permissions.sh --global` копирует `agent-router/` в `~/.claude/hooks`
  (env.ini не затирает). `validate.sh` получил py_compile-шаг для Python-хуков конфигов.
- Тесты: `harness/tests/test_router.py` (+10: block_router, --generate, поведенческие хуков),
  `maind` `TestRouterConfigProvisioner` (+4). roadmap помечен активированным + исправлен устаревший
  тезис про авто-активацию команд. **Честный лимит:** хук команду не запускает; `auto_dispatch`
  может оверфайрить → дефолт `propose`; marketplace-команды пакетов — follow-up (в README).

### Added (RAG-дисциплина формирования плана — агрессивный perplexity-web + footer «Проверка» + честность)

Field-feedback: агенты неохотно жмут RAG при формировании плана, хотя план 100% должен стоять на свежих
данных; отказ движка (perplexity-web залочен/timeout, MCP лёг) не выносился на повторный проход; не было
клаузы честности «костыль называть костылём». Scope: CORE-скиллы + CLAUDE.md + docs + агент-паки (зубы).

- **CORE-скилл `verify-claims` 0.2.0** (раздаётся в каждый проект): лестница — токен-экономия
  (`perplexity-web` flat-rate → **агрессивный дефолт**; на промах context7 фолбэк на perplexity-web, НЕ на
  WebSearch); новый **footer «Проверка»** (RAG · непроверенное→**ПОВТОРНЫЙ ПРОХОД** · обходки-`[POSSIBLE-DEFECT]`);
  клауза честности «не правки ради правок, костыль называть костылём». RU-источник правлен → EN-канон регенерён.
- **CORE-скилл `query-craft`**: нота токен-экономии (жать `perplexity-web` агрессивно) + как записать отказ
  движка в footer «Проверка» (кросс-реф на `verify-claims`).
- **Root `CLAUDE.md`**: «Методология решений» переписана под агрессивный perplexity-web + footer «Проверка»;
  новый тезис философии **«RAG-делегирование (токен-экономия)»**.
- **Root-скилл `decision-verification`**: триггер «формирование плана» + footer «Проверка» + честность.
- **Агент-паки (зубы): `_common` 0.3.0** — `orchestrator.md` получил RAG-правило плана + выходной блок
  `VERIFICATION`; **`backend-laravel` 0.10.0** — `dev-loop.js` `SLICE_RESULT_SCHEMA` получил опциональный
  `tool_failures[]` (движок недоступен → повторный проход, не маскировать).
- Провенанс — `docs/reference.md` (industry prompt-engineering RAG-forcing/verification-footer, верифиц.
  `perplexity-web` 2026-07-01). **Честное ограничение:** интерактивный plan mode не хардгейтится (нет хука) —
  фикс поведенческий; зубы только в workflow-слое `dev-loop.js`.

### Added/Changed (harness — agent-pack мигратор: монорепо-детект + анти-false-green)

- **Движок `agentpacks.py` — пост-рендер валидация путей (`expect_globs`).** Новое поле
  манифеста пака: список single-brace-глобов критичных путей; `render`/`upgrade` после
  рендера проверяют `target.glob(...)` и **печатают WARN на 0 совпадений** —
  детерминированная сеть безопасности против **ложно-зелёного** access-layer (когда
  захардкоженные пути не матчат раскладку проекта), независимо от detect-проб.
- **Движок — итоговая сводка conflict/.pack-new в `do_upgrade`** (`⚠ N conflict → ручной
  мерж: …`) — повышает видимость незаехавших правок (был только per-файловый warn).
- **Движок — условие `<!-- pack:ifnot KEY -->…<!-- pack:endif -->`** (зеркало `pack:if`,
  «иначе»-ветка; из PR #96) — нужно для двух-режимных блоков (`SCAFFOLDS_SCHEMA`).
- **`backend-laravel` 0.9.0** (детали — в его CHANGELOG, **supersedes PR #96**): `ACCESS_ROOT`
  авто-детект (`app`/`src`/`packages/*/src`) — вытеснил `IS_LARAVEL_PACKAGE` (тот не умел
  монорепо) + layout-aware пути (дроп `/Api`-сегмента) + `expect_globs`; **сохранён
  `SCAFFOLDS_SCHEMA`** из #96 (ортогональная ось: scaffold vs готовая схема, `pack:if/ifnot`).
  **Монорепо Laravel-пакетов рендерится верно на автомате** (пилот chatom вскрыл пробел).
  Принцип: каждая ручная итерация апгрейда флота дорабатывает базовый мигратор.

### Added (harness — авто-allow инструментов оркестрации `Workflow`/`Agent`/`TodoWrite`)

- **Пресеты `base` и `global` теперь авто-разрешают `Workflow`, `Agent`, `TodoWrite`.** Это
  универсальные (вне-стековые) инструменты оркестрации, поэтому добавлены в оба общих слоя:
  `settings.base.json` (накатывается в `.claude/settings.local.json` каждого проекта) и
  `settings.global.json` (машинный `~/.claude/settings.json` — действует во всех проектах сразу).
  Первопричина: запуск `Workflow` на каждой фазе спавнит субагентов (`Agent`) и ведёт план
  (`TodoWrite`), и без правил Claude Code просил подтверждение **после каждой стадии** —
  многофазный воркфлоу превращался в череду промптов. Безопасность не страдает: разрешён лишь
  сам вызов инструмента, субагент исполняет свои Bash/Read/Edit через тот же permission-слой.
  Затронуты `packages/harness/configs/claude-code/settings.{base,global}.json`, доки
  `docs/configs/claude-permissions.md` и `docs/setup/claude.md`.
### Added (skiller — пост-ран наблюдаемость: `skiller analyze-run`)

- **`skiller analyze-run`** (`lib/skiller/analyze.py` + `cli.py`) — детерминированный
  разбор прогона по JSONL-логам Claude Code, **без запуска агентов/трат токенов**.
  По агентам: факт-токены `in/out`, **cache-hit%** (из поля `usage`), модель,
  wall-clock, инструменты, ретраи, tool-ошибки. Скиллы: активный набор
  (`resolve_active_set`/`budget_for_set`) × реально загруженные (`Skill`-вызовы) →
  **эффективные / DEAD** (в наборе, 0 загрузок → чинить триггеры/снять) / вне набора.
  Плюс скан рантайм-отказов (`Rate limited`/`SingletonLock`/…, эвристика).
  Флаги `--last|--session|--project|--json|--store` (`--store` → JSON в
  `.claude/analyze/`, задел под кросс-сессионный тренд). Закрывает разрыв
  «budget (теория) ↔ eval (синтетика) ↔ реальный прогон». Дополняет качественный
  скилл `system/session-observer` (числа vs «почему»). +14 офлайн-тестов
  (`tests/test_analyze.py`); гайд `docs/guide/analyze-run.md`. Честное ограничение:
  детект загрузки скиллов частичный (только `Skill`-tool; нативный `skills:`-preload
  не виден).

### Added/Changed (harness — токен-экономия: downstream `deny` + agent-pack backend-laravel 0.5.0)

> План: `~/.claude/plans/idempotent-snacking-nest.md` (свод ретроспективы chatom + ответа Perplexity +
> токен-аудита; верифицировано RAG). Это P0-волна (publish-surface + workflow).

- **Downstream `permissions.deny`-пресеты (publish-surface, самый дешёвый ROI).** `deny` — реальный
  токен-барьер (на встроенные Read/Edit и на `cat/head/tail/sed`), `.claudeignore` не официальна.
  `settings.laravel.json` += `storage/framework/**`, `bootstrap/cache/**`, `**/node_modules/**`,
  `vendor/bin/**` (НЕ `vendor/**` целиком — vendor-исходники нужны для сверки реального API),
  `**/package-lock.json`, `**/.phpunit.cache/**`, `**/*.sqlite[3]`. `settings.base.json` += `~/.claude/logs/**`
  (лог-файлы хуков). `settings.python.json` получил deny-набор (`__pycache__`/`.venv`/`.mypy_cache`/
  `.pytest_cache`/`.ruff_cache`/`*.egg-info`/`dist`/`build`). Логи целиком НЕ денаим — чтобы не ломать
  `tail`-slice (selective-input).
- **agent-pack `backend-laravel` 0.5.0** (детали — в его CHANGELOG): risk-адаптивный review-gate
  (severity-enum, adversarial на HIGH, config-honesty, fresh-context), Lean-tiered model/effort-лейны,
  честность тестов `[POSSIBLE-DEFECT]`, env-preflight в Setup, layout-agnostic globs правил + per-layer
  risk-аннотации; фикс ложного «проект НЕ на Pest» (chatom F2) → `{{TEST_FRAMEWORK}}`, хардкод pint →
  `{{CHECK_CMD}}`.
- **Миграция: `agent-packs upgrade` теперь ставит НОВЫЕ файлы версии** (не только safe-apply/conflict). Файлы,
  добавленные в новой версии пака (recon-агенты 0.6.0), доезжают до онбордженных проектов на `upgrade` (а не
  только на полном `render`) — цель не существует, запись безопасна; явно удалённые optional (`removed_optional`)
  не возвращаются; локальные правки существующих файлов по-прежнему не затираются (`conflict`→`.pack-new`). Важно,
  т.к. `maind sync` зовёт именно `upgrade`. +unit-тест. Гайд пака дополнен разделом «Как ставятся задачи» +
  **mermaid-диаграммой** процесса dev-loop.

### Added/Changed (skiller — токен-экономия: плагин `task` + docker-router + context-economy/session-handoff)

- **Новый плагин `task`** (`packages/task/`, commands-only, авто-регистрация в marketplace, 51 плагин):
  интент-команды `/task:design|dev|review|research|fix`. Имя плагина `task` + файлы `commands/dev.md`
  и т.д. дают ровно `/task:<verb>` (Claude Code именует команды плагина как `<plugin>:<file>`; вариант
  `tasks`+`task-dev.md` дал бы `/tasks:task-dev` — исправлено). Каждая пинит `model:`+`effort:` (frontmatter) под
  профиль, перебивая настройки сессии — закрывает «забыл переключить модель/effort/режим». dev→Opus/high
  (планирование) + Lean-tiered субагенты по риску; fix→Sonnet/medium single-agent; review→Opus/xhigh adversarial;
  design/research→Opus/high + research-fanout.
- **`task` — default-on в КАЖДОМ проекте** (`skiller.config.DEFAULT_COMMAND_PLUGINS = ["task"]`): connect
  включает плагин `task` автоматически (как курируемый `core`) — marketplace-guarded (на старом
  marketplace / в тест-реестре тихо пропускается), `--no-core` его НЕ трогает, точечный opt-out —
  `enabledPlugins["task@swissknifeman"]=false`. Новые онбордженные проекты получают `/task:*` без ручной
  правки. Резидентного tier-0 налога нет (описания команд не инжектятся в каждый запрос).
- **Доктор фиксирует пропуск** (`maind doctor --audit core`): дименсия `core` теперь помимо CORE-скиллов
  проверяет и командные плагины по умолчанию — `cmd⚠(нет: /task:*)` на проектах без `task`. Чеклист
  интеграции (`integration-checklist.md`) дополнен пунктом про `core`/`task` в connect.
- **`devops/docker` → тонкий router-скилл** (v0.2.0, `risk: read`): description-триггер + маршрутная таблица по
  всем 6 под-скиллам (docker-php/postgres/dev-prod/services/vite/makefile) + порядок сборки (DAG в
  requires/produces_for); глубокая экспертиза — в `snippets/docker-expert.md` on-demand (progressive disclosure).
  «Фоновый» кластер: резидентно только router-описание, специалисты грузятся по нужде.
- **`general/context-economy` v1.2.0**: §8 — recon-субагенты (тяжёлое чтение в изолированном окне, наверх только
  сводка), selective-input (срез вместо файла целиком; `tail`/`grep`/`git diff`; нюанс: `deny` блокирует и
  `tail`), видимость стоимости (`/usage`, не `/cost`); back-ref на плагин `tasks`.
- **`general/session-handoff`**: `outputs: []`→`[".claude/handoffs/*.md"]` + стандартный путь
  `.claude/handoffs/YYYY-MM-DD-<topic>.md` (индексируется maind). RU→EN перестамплены, `skiller registry` прогнан.
  Аудит рекомендовал `risk:draft→stable` — **отклонено** по верификации (`stable` не в
  `RISK_VALUES={read,draft,write,external}` → сломал бы validate; зрелость — отдельное поле `level`, не `risk`).
- **F8 budget-governance — `skiller budget --check-core`** (+ `--strict` для CI) и константа
  `RESIDENT_BUDGET_TARGET=600` (config.py): гейт резидентного ⊕ tier-0-бюджета `CORE_SKILLS` (грузится в КАЖДЫЙ
  запрос) против таргета; выведен в хвост `validate.sh` (информационно). Замер вскрыл: резидент CORE сейчас
  **592/600 ток** — у потолка (комментарий обещал ~480), так что гейт против тихого роста ядра предметен.
- **D4 — 5 новых production-readiness-скиллов** (из ретроспективы chatom; локальные, двуязычные RU→EN, 205 скиллов):
  `php:transactional-outbox-relay` (persist+outbox в одной tx, единственный владелец retry, идемпотентность,
  after-commit), `php:production-readiness-checklist` (атомарность/гонки/config-honesty/cursor/queue-семантика —
  класс дефектов, который маскируют зелёные тесты), `php:cursor-pagination-design` (keyset по non-nullable ключу,
  composite-tiebreak), `php:namespace-refactor-safety` (трёхфаза alias→use→rename, префиксные ловушки, контракт-seam),
  `laravel-architecture:config-driven-abstraction` (Registry+Builder, config:cache-safe, per-variant ≠ runtime `$table`).
  Ретроспективные #5 (state-machine-race) и #6 (env-driven-test) **свёрнуты** в production-readiness-checklist +
  dev-loop env-preflight (анти-bloat: не дублировать существующие `enum-state-machine`/`db-test-preflight`).
- **F2 — `skiller doctor --downstream`** (аудит publish-surface онбордженных проектов — там основной runtime-расход
  токенов, не в реестре): per-project гигиена always-loaded слоя — `CLAUDE.md` ≤200 строк, scoped vs unscoped
  `.claude/rules`, наличие `permissions.deny`-пресета. Замер по реальным проектам вскрыл over-budget CLAUDE.md
  (sova 1214, cms 813, flexcrm 738 строк, …) против здоровых (chatom 123, corex 169) — операционализирует
  ключевой тезис аудита (мерять сгенерированный артефакт, не шаблоны). +unit-тест (202 теста).
- **A2/A3 — thin-orchestrator + skill-on-demand задокументированы/проброшены:** `docs/guide/skill-taxonomy.md`
  получил раздел «Router-скилл» (тонкий оркестратор фонового кластера — образец docker); orchestrator-агент паков
  (`_common/orchestrator.md`) — поля `risk:`+`skills:` в PLAN (минимальный набор под тип задачи + risk→модель/
  effort/глубина ревью), вместо полного preload. (C — durable per-phase handover: реализован «лёгкой» версией —
  компактные сводки в брифах + plan-file-primary + нативный resume воркфлоу; on-disk-дубль избыточен, не вводим.)

### Changed (skiller — `perplexity-web-mcp` v1.3.0: демон-конкурентность в скиллах)

- **`research/query-craft`**: раздел «Надёжность keyless-моста» (lock/сериализация, запрет
  «не параллелить») переписан в «Конкурентность и устойчивость `perplexity-web` (демон v1.3.0)».
  Параллель разрешена до `maxConcurrency` (дефолт 3); пулы (`--pool`) как конфиг MCP; таблица кодов
  ошибок (`BROWSER_BUSY`/`TIMEOUT`/`LOGIN_REQUIRED`/`PROTOCOL_MISMATCH`); не-контрактные обрывы
  (`ECONNRESET`/«connection closed» → недокачанный Chromium → `npx playwright install`); `search_deep`
  до ~10 мин и не блокирует параллельные `search`; чеклист обновлён. Прежний обход «не параллелить»
  снят как legacy.
- **`general/mcp-advisor`**: пул-нота к keyless `perplexity-web` (демон v1.3.0, изоляция через
  `--pool=<проект>`).
- **`docs/reference.md`**: строка про integration-note `perplexity-web-mcp` v1.3.0 (вердикт **adopt**).
- RU→EN регенерирован + `check-translations.sh --stamp`; `skiller registry` (`skills.json`, `budget.md`).
  Контракт сверен end-to-end вживую: 3 параллельных `search` изолированы (no cross-read), фикс
  анти-троттлинга фоновых вкладок подтверждён.

### Changed (maind — переименование проекта экосистемы DocVault → Vaulter)

- **Проект `docvault` переименован в `vaulter`** (продукт DocVault → Vaulter). `derive.py`:
  `FIRST_PARTY_VENDORS` `docvault`→`vaulter`; `DOC_ALIASES` — новый канон `vaulter`,
  плюс **back-compat алиас `docvault` → `vaulter`** (старые doc-backlinks Brain резолвятся).
  Примеры/комментарии (`namespaces.py`, `design-notes.md`, скилл `cross-project-optimizer`)
  обновлены. Хаб-состояние (`config.json` id/scope/path, граф, `.mcp.json` scope `project:vaulter`,
  память, agent-pack `vaulter-*`) перекатано вне VCS; потребитель `flexcrm` и сам пакет —
  отдельными репозиториями/PR.

### Added (maind — opt-in эмит `.mcp.json.example` + гигиена `.gitignore`)

- **`maind deploy`/`sync` при `mcp.emit_example: true`** эмитит рядом с реальным `.mcp.json`
  портируемый `.mcp.json.example`: machine-specific абс. пути → плейсхолдеры (`<ABS_PATH_TO_PROJECT>`,
  `<HOME>`), индирекция `${MAIND_BIN:-maind}` сохранена. Один генератор → два выхода из одного `data`
  (`mcpconfig.write_example`) — расхождение real↔.example невозможно by design.
- **Гигиена `.gitignore`** (`reconcile_gitignore`): реальный конфиг → в `.gitignore` (append-if-absent),
  его `.example` → вне (remove-if-present, чтобы шаблон коммитился); идемпотентно; warn, если реальный
  файл уже трекается git. **Opt-in** (по умолчанию выключено — не трогаем чужие репо без флага).
  Закрывает машинно-специфичный серена-путь `--project <abs>`, который индирекция `maind` (PR #94) не
  решала. +тесты `test_mcpconfig`; статус `roadmap/mcp-config-example-emit.md` → реализовано (opt-in).

### Fixed (skiller — ложный `[ПЕРЕЕХАЛ]` в `skiller status` на монорепо-реестре)

- **`skiller status` сравнивал источник marketplace с `env.root` (каталог пакета), а не с корнем
  монорепо.** В монорепо `marketplace.json` лежит в КОРНЕ (туда же `connect`/`update` пишут
  `source` через `find_repo_root`), поэтому сравнение с `env.root` (`packages/skiller`) давало
  вечный ложный флаг `[ПЕРЕЕХАЛ — починить: skiller update]`, который `skiller update` физически
  не способен погасить (он пишет корректный корень репо). Теперь `status` резолвит ожидаемый
  источник так же — `find_repo_root(env.root) or env.root`. Затронут `lib/skiller/status.py`.

### Added (skiller — CORE-скилл `research/query-craft`: дисциплина формулировки поисковых запросов)

- **Новый скилл `research/query-craft`** — как ФОРМУЛИРОВАТЬ запрос к поисковому/доковому движку
  (Perplexity Web · WebSearch · context7): железное правило «никогда не голый запрос по библиотеке
  без версии+контекста» (анти-паттерн «Laravel как сделать X?» → «Laravel 11: … на 2025»); 5 слотов
  запроса (глагол · субъект+версия · контекст · конкретика · формат/лимит); выбор движка и режима
  Perplexity (`search`/`search_advanced`/`search_deep`, `sources` web/academic/social); раздел
  «Надёжность keyless-моста» (lock/таймаут на тяжёлых запросах → не параллелить, дробить, эскалация
  на WebSearch/context7, системно — API-key вариант).
- **Завершает RAG-дисциплину-трио в `CORE_SKILLS`** (раздаётся в каждый проект, on-trigger):
  `mcp-advisor` (что подключить) · `verify-claims` (когда/что верифицировать) · `query-craft` (как
  спросить). Скилл физически в бакете `research`, в CORE — по ссылке. `verify-claims`/`mcp-advisor`
  получили back-reference на него, роли разрезаны (verify-claims = «когда», query-craft = «как»).
- Двуязычный (RU-источник → EN-канон); факт-основа — официальный Perplexity Prompt Guide,
  верифицирована RAG (WebSearch+WebFetch) 2026-06-29 (см. `docs/reference.md`). 200 unit-тестов OK,
  `validate.sh` зелёный (201 скилл).

### Added (skiller — локаторы экосистемы: навигация агента к узлам Brain/swissknifeman)

- **Два скилла-локатора** в бакете `system` (on-trigger, НЕ в CORE — резидентный токен-бюджет не растёт):
  `system/brain-locator` (из любого проекта дойти до Brain-волта) и `system/swissknifeman-locator`
  (из внешнего репо дойти до управляющего монорепо). Цель — агент больше не угадывает, где узлы экосистемы.
- **Нехардкод-резолюция пути.** brain-locator повторяет канон `maind` (`projects.py::brain_path`):
  `integrations.brain.path` → проект `id==brain` → `$MAIND_BRAIN_VAULT` → кандидаты от `$HOME`
  (`~/Vaults/Brain` первым); swissknifeman-locator — через установленный бинарь (`readlink` до репо) →
  `$SWISSKNIFEMAN_ROOT` → `$HOME`-кандидаты. У каждого готовая `cd`-команда и проверка-признак узла.
- **Тезисы связи.** brain-locator несёт маркер «скилл подключён → проект синхронен на Brain», объясняет
  каталог `.projects.json` / control-ноты / `CLAUDE.md` / wikilinks; swissknifeman-locator — `config.json`
  как реестр связанных проектов (двусторонность) и опознание связи по
  `.swissknifeman/config.json` / `skills-lock.json` / `enabledPlugins`.
- **Связаны с картой.** `requires: [local-topology]`; `local-topology` получил их в `produces_for` +
  заметку про fallback-резолюцию узла без `~/.swissknifeman/topology.json`.

### Added (maind — синк-защита visibility + явная модель владения каталогом)

- **`sync_from_brain` предупреждает о смене visibility** doc-папки существующего проекта
  (`_warn_visibility_changes`) — частый признак протухшего brain `.projects.json` (его надо
  регенерировать из frontmatter перед синком). brain по-прежнему «выигрывает» (поле затирается):
  источник истины каталога/visibility — frontmatter control-нот → `.projects.json` → `config.json`.
- **Явная модель «три слоя + владелец факта»** в `docs/guide/config.md`: frontmatter Brain (источник)
  → `.projects.json` (gitignored кэш) → `config.json` (импорт + maind-поля). Разведена семантика
  `repo` (GitHub-slug) ≠ `local_path` (путь к коду) и инверсия brain-схемы (`repo` = путь → `local_path`
  при импорте). `config.example.json` — каноничный `docs_folders` `{id,vault,repo,visibility}`.

### Changed (maind — индирекция бинарника в `.mcp.json` вместо абсолютного пути)

- **`deploy.py::_maind_entry` пишет `"${MAIND_BIN:-maind}"`** вместо `<abs>/packages/maind/bin/maind`.
  Claude Code раскрывает индирекцию из окружения процесса (дефолт `maind` по PATH — `~/.local/bin`
  от `install.sh`); тот же `MAIND_BIN`, что у health-хуков. Переносимо на другую машину/CI и при
  переносе репо — в `.mcp.json` больше нет захардкоженного `/home/...`. Тест-замок на `command`
  (`test_deploy.py`), пример в `docs/guide/mcp.md` обновлён.
- Уже онбордженные проекты мигрируются идемпотентно: `maind sync --only mcp --all` (недеструктивный
  merge + `.bak`). Серена-путь `--project <abs>` остаётся машинно-специфичным — отдельная фаза
  (`roadmap/mcp-config-example-emit.md`).
- Гайды приведены в соответствие реальности: `project-tooling-runbook` §«Гигиена» (нюанс
  `${VAR:-default}` — Claude Code раскрывает из окружения процесса, не из проектного `.env`; maind-путь
  индиректирован, остаётся серена-путь) и `roadmap/mcp-config-example-emit.md` (проблема сужена до серена-пути).

### Added

- **`laravel-architecture/eloquent-accessors`** (новый скилл) — канон современных Eloquent
  accessors/mutators через `Attribute::make(get:, set:)` вместо legacy `getXxxAttribute()`:
  синтаксис/именование/видимость/типизация, размещение в классе (после relations, перед scopes),
  миграция legacy, граница с `casts()`. Сниппет `accessor.php` (getter, getter+setter с
  нормализацией, многострочный, миграция). Промоут project-local скилла из проекта agelto
  (анонимизирован, поднят в реестр по правилу универсальности) через `field-feedback-loop`.

### Changed

- **`project-tooling-runbook`** — новая секция «Гигиена machine-specific конфигов»: конфиг с
  абсолютными локальными путями или секретами (`.mcp.json` любого провайдера, `.cursor/.vscode/mcp.json`,
  `.claude/*`) не коммитить как есть. Двухуровневое правило: индирекция через `.env` (предпочтительно,
  конфиг остаётся портируемым) либо gitignore реального + **синхронный** `.example` с плейсхолдерами
  (как `.env`↔`.env.example`). Кросс-ссылка из `ecosystem-integration` (шаг deploy: `.mcp.json` несёт
  абс.пути maind/Serena). Триггеры обоих скиллов расширены.

- **`harness` agent-pack `backend-laravel` 0.2.0 → 0.3.0** — деуниверсализация шаблонов: убрана
  зашитая среда одного проекта (machine-specific `php8.5`/`pgsql`/`Postgres`/`/usr/bin/php8.4` и ложные
  для большинства «phpstan не установлен», «миграции не добавлять — схема полная»). Тест-фреймворк
  теперь параметричен (`{{TEST_FRAMEWORK}}` — раньше интервью-переменная игнорировалась, хардкод
  «PHPUnit-native, НЕ Pest»); идентичность slice-builder смягчена до «Laravel/REST API **или пакет**».
  Поймано на полевом онбординге azguard (Pest+Testbench-пакет) → `field-feedback-loop` путь 1 (фикс
  генератора, не артефакта). Затронуты agents/rules/workflow/docs пака.

- **Doc-папки: имя ↔ видимость развязаны (Brain doc-sync + maind + core).** Раньше «публичность»
  папки кодировалась её именем (хардкод `docs-public`), имена сторон vault/repo были жёстко
  симметричны. Теперь — единая модель папки `{id, vault, repo, visibility}`: имена сторон могут
  отличаться (в валте `docs-public` ↔ в репо `docs`), статус `public|private` независим от имени,
  wikilink-гейт публикации — по `visibility`. Дефолт видимости **по типу проекта**
  (`core.docs_visibility_for`): пакет/библиотека → `docs` public, продукт → private. Источник
  истины — frontmatter control-ноты Brain; maind кэширует `docs_folders` (нормализация плоского
  legacy-списка на лету, полная back-compat). Поймано на онбординге пакета chatom →
  `field-feedback-loop`. Затронуты `core/project.py`, `maind/{config,onboard,common}`, Brain
  `lib/brain/{folders,engine,config,status,listing,syncing,watch,discovery}` + доки/тесты.

- **`harness` agent-pack `backend-laravel` 0.3.0 → 0.4.0** + `python-backend`/`node-frontend`/
  `dart-flutter` 0.1.0 → 0.2.0 — **AI-гайд `subagents-and-workflows.md` переехал из публичного
  `docs/05_AI/guidelines/` в `.claude/guidelines/`** (дефолт `DOCS_DIR`). Это внутренний артефакт
  для агентов, не публичная VitePress-документация пакета (иначе утекал в публикацию и в Brain-валт).
  Из шаблона backend-laravel убран ошибочный Brain-frontmatter (`parent: [[05_AI]]`) и вики-ссылка.
  Миграция установленных проектов: новый гайд в `.claude/guidelines/`, старый путь удалить вручную.

### Roadmap

- **`roadmap/mcp-config-example-emit.md`** — отложено: научить `maind deploy/sync` самому эмитить
  `.mcp.json.example` (плейсхолдеры) + вести `.gitignore` (механизм вместо дисциплины агента).
  Критерий внедрения — повторная утечка абс.путей/секретов или невозможность поднять MCP без `.example`.
  Маршрутизировано через `field-feedback-loop` из полевого кейса agelto (настройка playwright-MCP).

### Added (аудит волна 3 — docs, эргономика, дедуп)

- **`analyst status` / `analyst compact`** (S16). `status [--json]` — read-only сводка стора:
  счётчики по состояниям, `curated-ready`, `promote_failed`, число событий, даты последнего
  `digest`/`recompute`. `compact [--before ISO] [--dry-run]` — детерминированно сводит старые
  события `events.ndjson` в один snapshot-event на урок; суммы (S/N/tests) и возраст последнего
  события сохраняются, поэтому `recompute` до и после даёт **ту же** confidence (проверено e2e:
  0.7968 → 0.7968). Провенанс операции — в `audit.ndjson`. Новый модуль `analyst/status.py` (+10 тестов).
- **`packages/analyst/docs/guide/tuning.md`** (S13) — единый справочник всех порогов (confidence-
  арифметика, тиры, state-machine, Jaccard-дедуп/консолидация): параметр · файл · значение ·
  эффект↑/↓ · метод калибровки. Линкован в сайдбаре (standalone + зонтичный агрегат) и из
  `lifecycle.md`.
- **`core.paths.state_dir(home, app=None)`** (S15) — единый источник литерала `.swissknifeman`
  для зонтичного state (корень `~/.swissknifeman` — skiller; подкаталог `~/.swissknifeman/analyst`).
  `maind` намеренно НЕ входит (его state `~/.maind` — отдельный node-state, документировано). +3 теста.

### Changed (честность + провенанс)

- **Коммент `analyst/confidence.py` — честный** (S13, D3-дисциплина): убрано ложное «verified
  perplexity, tune by false-positive rate» → «эвристики, подобранные по форме кривой, НЕ
  откалибровано по FP-rate» (реальной калибровки не проводилось — отдельная research-задача).
- **`docs/reference.md`: карточка mem0** (S17, провенанс F-RAG-2) — таксономия консолидации mem0
  = ADD/UPDATE/DELETE/NOOP; `analyst` адаптирует как **ADD/UPDATE/NOOP/CONFLICT** (`CONFLICT`
  вместо `DELETE` — авто-удаление нарушило бы инвариант «человек в гейте»). Строка в таблице
  уточнена + отдельная карточка.

## [0.7.1] - 2026-06-28

### Added

- **`founder/idea-audit`** — сквозной деструктивный аудит идеи / концепта / готового ТЗ: First-Principles
  Decomposition → рыночный скептицизм (5 векторов) → архитектурный pre-mortem (вкл. AI-specific) →
  Kill-or-Build Scoring + вердикт. Мост idea→architecture между `idea-discovery` и `brd`/`architecture`.
  Двуязычно (SKILL.ru.md → SKILL.md). Внешние факты выверены через RAG (Founder's Playbook — реальн.;
  CB Insights ~42% — классика, 2026 ~43% PMF); провенанс — `docs/reference.md`.
- **`provider-skills/` — SSOT навыков-капабилити для внешних агентов (paste-in).** Текст, который
  человек копирует в UI провайдера (Perplexity → My Skills), а не доставляет реестром connect/vendor;
  канон versioned здесь, потребители (Brain) держат provenance-linked копию. Первый навык —
  `perplexity/idea-architect.md` (режимы Idea/Spec/Architecture). Реестр учитывает их как `references`.
- **Внутренний скилл `field-feedback-loop`** (`.claude/skills/`, не экспортируется) — петля обратной
  связи из полевой работы: отклонение тулинга/раннбука от обещанного при внедрении/синхронизации
  проекта маршрутизируется в очевидный-баг→фикс-сразу либо новое/сомнительное→предложение
  (`roadmap/`/issue + захват в память), а не глотается. Механизм принципа «по факту измеренной
  проблемы» (`roadmap/README.md`); связан с `release-discipline`/`decision-verification`.

### Changed

- **`pm/requirement-critic`** — режим Spec Audit: Optimism Bias Detector, `[UNVERIFIED]`-метки для цифр без
  источника, чеклист полноты для продукта/стартап-ТЗ (target customer, kill-criteria, метрика PMF).
- **`founder/adversarial-check`** — секция **stage-context** (idea→рынок, mvp→retention, launch→CAC/LTV).
- **`founder/idea-discovery`** — **falsification signals** (измеримый порог) к каждому kill-criterion.
- **`architect/architecture`** — обязательное поле **`business_rationale`** в каждом Options-блоке.
- **`founder/startup-lifecycle`** — гейт доказательности: **≥1 внешний сигнал** на каждый exit-criterion.
- **`founder/risk-assessment`** — 6-я категория рисков **AI/Agentic** (hallucination/drift/injection/cost
  creep/eval-gaps/single-provider); тег `agentic`.

## [0.7.0] - 2026-06-28

### Added

- **Единый control-surface проектов (4 слоя, строго + машиночитаемо).** Одной командой — полный
  инвентарь проекта/флота по слоям *скиллы · роли/agent-packs · MCP · память-граф* с drift→fix
  подсказками; точечный re-sync уже даёт `maind sync --only <cap>`.
  - `maind projects status` теперь инвентаризует **слой ролей** (`probe_project` читает
    `.claude/agent-pack.lock.json` → поле `agent_packs`) и печатает **drift→fix** (`probe.drift_hints`:
    `{layer, issue, fix}` — напр. «профиль ожидает пак X → `maind sync --only agent-pack`»). `--json`
    несёт `agent_packs` + `fixes` по каждому проекту.
  - **`swissknifeman status [<id>|--all] [--json]`** — зонтичный фасад единого 4-слойного статуса
    (→ `maind projects status`); bare/`--target` → `skiller status` (back-compat сохранён).
  - **`--json`** добавлен в `skiller status` (каналы/профиль/бюджет/overlap) и
    `harness agent-packs doctor` (каталог паков + установленные) — машиночитаемо для агента.

### Docs

- **Корневой `CLAUDE.md` — раздел «Философия и рамки»:** разрозненные по тексту принципы сведены в
  явные **тезисы** (зонтик≠инструмент, единый источник истины, stdlib-only, детерминированная
  доставка, faithful-first+провенанс, изоляция namespace, спекулятивное→`roadmap/`) и жёсткие
  **рамки** («за них не выходим»: pip/JS-рантайм, дубли примитивов, переименование зонтика/префиксы
  плагинов, ломать пути `maind`, Proprietary-вендоринг, утверждать внешние факты по памяти).
- **Раздел «Референсы и провенанс»:** `CLAUDE.md` теперь указывает на каталог провенанса
  [`docs/reference.md`](docs/reference.md) (изученные внешние источники: вердикт adopt/reference/skip
  + что взято) и per-skill паспорта `upstream.json`, с правилом «использовал внешний ресурс — отметь».
- **Раннбук `project-tooling-runbook` — раздел «Агенты/роли (agent-packs)»:** настройка проекта
  теперь явно = скиллы **И** agent-packs (роли/агенты — отдельная подсистема `harness agent-packs`:
  субагенты + workflow + review-gate). В «Порядок „дать проекту всё“» добавлен шаг agent-packs;
  зафиксирован авто-путь (`maind onboard`/`setup` с типом проекта ставит пак из `profiles/<type>.json`)
  и причина пропуска при ручном `connect`/нетипизированной записи. Закрывает пробел «у проекта нет
  ролей/код-ревью при большой задаче».
- **Новая умбрелла-страница [`docs/control-surface.md`](docs/control-surface.md):** таблица
  «слой → статус-команда → fix/re-sync → lock» + операционный цикл `status --json → fixes[] →
  maind sync --only <cap>`. Раннбук `project-tooling-runbook` дополнен секцией «Control-surface»,
  явными шагами MCP/память/граф, а «Проверка» сведена к `swissknifeman status <id>`.

## [0.6.0] - 2026-06-27

**Аудит репозитория (многоагентный, 122 подтверждённые находки) → ремедиация в 7 фаз.**
Headline — **умное подключение**: connect раздаёт курируемый плагин `core` (РОВНО 7 `CORE_SKILLS`
по ссылкам, без копий) вместо целых бакетов general+oss-dev → резидентный ⊕ tier-0 **~1956 → ~480
ток/проект** на каждый запрос; budget-aware connect показывает цену набора; кириллица убрана из
EN-описаний (−643 ток) + CI-гейт. Плюс: надёжность логики подключения (TOCTOU, валидация lock,
действенный дрейф пути), кросс-пакетный дедуп примитивов в `core`, изоляция maind (scope-маркеры,
recall-crowding, рабочий graph-namespace), +18 тестов и ruff на `tests/`, доки приведены в
соответствие коду. Совместимость сохранена (онбордженным проектам — миграц.-подсказка, merge-only).

### Docs (аудит 2026-06 — Phase 7: точность доков и DX)

- **Доки больше не врут про CORE-политику.** `skiller/CLAUDE.md`, `docs/guide/skills-architecture.md`,
  `docs/guide/archetypes.md` и корневой `CLAUDE.md` обновлены под умное подключение: connect раздаёт
  курируемый плагин `core` (а НЕ бакеты general+oss-dev). Счётчик плагинов marketplace ~50.
- **Задокументирована команда `harness agent-packs`** (`list|render|upgrade|doctor` + флаги) в
  `harness/CLAUDE.md` — раньше отсутствовала в справке CLI.
- **`research/README.md`** (новый): индекс рабочих записей с явной пометкой «НЕ канон» и указателем
  на источники истины (docs/CHANGELOG/CLAUDE.md) + напоминание методологии (до-проверять аудиты).

### Added (аудит 2026-06 — Phase 6: тесты и CI)

- **Юнит-тесты на новое поведение:** `core.load_json_db` (missing/corrupt-backup/version-die),
  `core.is_within`/`is_within_lexical` (traversal), `core.atomic_write_*` mode=0600;
  `maind.split_scope` (strip-all маркеров, неподделываемый владелец); `harness.categorize_file_change`
  (матрица new/user-owned/conflict/safe-apply/nochange); skiller registry эмитит курируемый `core`-плагин;
  connect пушит `core` (не бакеты), `--no-core`, graceful-skip без core в marketplace. (+18 тестов.)
- **CI ruff теперь линтует и `tests/`** (раньше — только `lib/`, в тестах копился мусор: F401/F841).
  Прежний долг вычищен; планка теперь едина для тестового кода.

### Fixed (аудит 2026-06 — Phase 5: корректность и изоляция maind)

- **`memory.split_scope` — больше не утекают marker-артефакты:** снимаем ВСЕ ведущие `[[s:…]]`
  (на случай вложенных/повторных в контенте), владелец scope = первый маркер (подделать нельзя).
- **`memory` RECALL_LIMIT 50 → 200 + предупреждение о насыщении:** пул общий на все проекты
  экосистемы, узкое окно вытесняло релевантные факты scope чужими (crowding). При насыщении
  (демон вернул весь пул) — `warn`, что факты scope могли не влезть.
- **MCP `maind_graph_query`/`neighbors`: параметр `namespace` ТЕПЕРЬ работает** — раньше был
  объявлен в схеме, но молча игнорировался, и обход федерировал ВСЕ проекты (узлы чужих namespace
  утекали на depth>1). Теперь сужает union; стартовый узел по-прежнему под `_project_blocked`.
- Проверено и НЕ менялось (находки переоценены/уже закрыты): `cmd_sync` уже fail-soft с ненулевым
  rc и видимостью провалов (per-project `failed`); `deploy` уже health-WARN'ит (блокировать нельзя —
  `.mcp.json` статичен и валиден независимо от демона); абсолютные пути в `.mcp.json` —
  намеренны (CLAUDE.md «не ломать», 17 проектов), env-индирекция — отдельный аддитивный PR.

### Changed (аудит 2026-06 — Phase 4: кросс-пакетный дедуп → core)

- **`core.paths`** (новый): `is_within`/`is_within_lexical` — единый containment-примитив
  (был только в `skiller.common`, дублировал паттерн в connect/vendor/skillset/eval). Экспортирован
  из `core`; `skiller.common` реэкспортит для back-compat.
- **`core.io.load_json_db`** (новый): JSON-БД с восстановлением (битый → бэкап `.corrupt.<date>` +
  warn; version > max → die). Свёл дословные копии `skiller.state.load_db` и
  `maind.common.load_json_db` (расходились в имени бэкапа/тексте) к одному источнику.
- **`skiller.common.safe_copy_skill`** (новый): единый безопасный copy скилла (containment +
  снятие symlink/файла/каталога + TOCTOU-перепроверка + `SKILL_IGNORE`) — общий для
  `vendor.copy_skill` и `skillset.sync_skillset` (раньше дублировались, расходясь в безопасности;
  TOCTOU-фикс Phase 3 теперь и в vendor). Legacy `vendor` re-copy стал clean-replace (как skillset).
- Осознанно НЕ тронуто: `apply_permissions` (skiller→harness — это граница делегирования через
  subprocess, не дубль); консолидация 3 валидаторов конфигов (schema-расходящиеся — отдельный
  риск/PR).

### Fixed (аудит 2026-06 — Phase 3: надёжность логики подключения)

- **TOCTOU в `skillset.sync_skillset`:** между удалением `dst` и `copytree` чужой процесс мог
  пересоздать путь симлинком наружу (copytree пошёл бы по нему). Добавлена пере-проверка после
  удаления: `dst` существует → гонка, пропуск (fail-closed).
- **Валидация `skills-lock.json` (`load_lock`):** битый/неструктурный lock больше не трактуется
  МОЛЧА как пустой (это вело к перекопированию всех managed-скиллов). Теперь `warn` + пересборка
  из конфига; проверяется наличие dict `skills`.
- **`connect`: дрейф пути marketplace — действенная подсказка.** Directory-источник с ДРУГИМ путём
  (репозиторий переехал → плагины не грузятся) теперь даёт `⚠` с командой `--fix-path`/`update`,
  а не молчаливый «keeping it». Иной тип источника (github/…) оставляем как осознанный выбор.
- **`apply_permissions`: видимость провала.** Ненулевой rc harness с ПУСТЫМ stderr раньше молчал
  (пресеты deny/allow не легли незаметно) — теперь `warn` всегда, с командой перезапуска.
- **Порядок lock→manifest задокументирован как намеренный** (lock — источник истины детекта
  `plan_sync`, пишется авторитетно; manifest — производная): защита от «починки наоборот».

### Added (аудит 2026-06 — Phase 2: умное подключение, экономия токенов)

- **Курируемый лёгкий `core`-плагин (connect-канал).** CORE-политика `connect` теперь раздаёт в
  каждый проект ОДИН лёгкий плагин `core` (== `CORE_SKILLS`, 7 скиллов) ВМЕСТО целых бакетов
  `general`(19)+`oss-dev`(10). marketplace-запись `source:"./"` + явный `skills[]` грузит РОВНО
  эти 7 скиллов (скиллы физически остаются в своих бакетах — без копий/симлинков; механизм
  подтверждён докой Claude Code). **Экономия резидентного ⊕ tier-0: 1956 → 476 ток ≈ −1480
  ток/проект на КАЖДЫЙ запрос.** `--no-core` отключает; `registry.py` эмитит плагин, `validate.sh`
  гейтит (skills-пути существуют). Миграция: онбордженным проектам со старыми `general/oss-dev`
  `connect` подсказывает снять их (merge-only, сами не трогаем).
- **Budget-aware connect.** `connect` печатает строку `Резидент: ~N ток ⊕ tier-0 (M скиллов)` —
  цена набора видна ДО записи (источник математики — единый `budget.skill_budget`). «Умное
  подключение»: меньше плагинов / `--no-core` → дешевле.
- **Кириллица убрана из 21 EN-описания** (резидентный tier-0): 20 скиллов + `generate-skill`
  переведены на английский канон (RU-источник остаётся в `SKILL.ru.md`), триггеры активации
  сохранены. tier-0 по всем 195: 12375 → 11732 ток (−643). EN дешевле RU у токенайзера.
- **CI-гейт описаний** (`validate.sh`): кириллица в `description`/`name` SKILL.md → ERROR
  (SKILL.md — EN-канон, резидентный tier-0); `description` > 450 симв → WARN (раздутый налог).
  Предотвращает регресс — экономия закрепляется.

### Fixed (аудит 2026-06 — Phase 1: quick wins)

- **Коллизия имён скиллов устранена:** `php/naming-conventions` → frontmatter `name:
  php-naming-conventions`. Реестровая by-name карта (`lock._registry_map`,
  `vendor.build_requires_index` через `setdefault`) молча роняла один из двух скиллов с именем
  `naming-conventions` (general+php). Обновлена ссылка в агенте `php/agents/laravel-implementer`,
  реестр перегенерён, EN-маркер перештампован.
- **Валидация `project.id` (maind):** id ограничен `[A-Za-z0-9._-]` (`config.PROJECT_ID_RE`) —
  он идёт в scope-маркер памяти `[[s:project:<id>]]` и namespace; спецсимволы (`]`, пробел,
  перевод строки) ломали парсинг scope при recall/forget и могли подменить чужой scope.
- **`config.json` пишется с правами `0o600`** (секреты узла): `core.atomic_write_text/json`
  получили опц. `mode=` (chmod на `.tmp` ДО `os.replace` — без окна world-readable);
  `projects.write_config` применяет `0o600`.
- **eval-ассершены `file_exists`/`file_absent` защищены от traversal** (`is_within`): `value`
  из `evals.json` (в т.ч. внешних скиллов) не вырвется за каталог прогона (fail-closed).
- **MCP-обработчик ошибок логирует КЛЮЧИ аргументов** инструмента (не значения — память/секреты)
  для диагностики; голые `except: pass` в `probe`/`memory` снабжены поясняющими комментариями.
- **`agentpacks.do_upgrade`:** логика категоризации файла вынесена в чистую `categorize_file_change`
  (тестируемая матрица new/user-owned/conflict/safe-apply/nochange).
- **Маркер ручных счётчиков** в `docs/index.md` («195/45» — сверять с `skiller registry`).

### Fixed (skiller — drift-устойчивость путей и корень marketplace)

- **`connect`: source marketplace указывает на КОРЕНЬ монорепо**, а не на каталог пакета
  (`env.root`). `marketplace.json` генерируется в корне репо с относительными `source`-путями;
  раньше `connect` объявлял marketplace под `packages/skiller`, где Claude Code не находил
  `.claude-plugin/marketplace.json` и плагины не подключались. Добавлен флаг `--fix-path` для
  обновления протухшего пути в существующих настройках.
- **`resolve_skillset`/`_match`: drift-устойчивость после раскола бакетов** — старый путь
  `oldbucket/skill` (напр. `frontend/vue` → `frontend-vue/vue`) больше не теряется молча: при
  промахе по полному ключу токен-путь добивается по базовому имени, а вызывающий печатает
  migration-warning со старым→новым путём (`обновите .swissknifeman/config.json`). Регресс-тест.

### Changed (аудит — добивка отложенного: super-skill + Serena-пин)

- **3 vendored super-skill демотированы в «навигаторы»** (`pm/product`, `architect/engineering`,
  `operator/operations-cx`) — они дублировали зрелые гранулярные нативные скиллы (9/13/5) и
  перехватывали весь бакет over-broad триггером («any … work»). `description` сужен до «обзор
  бакета; для конкретной задачи → granular skill», в тело добавлен блок обратных ссылок на
  гранулярные. Конфликт триггеров устранён, провенанс (upstream `notify`) сохранён.
- **Односторонние границы Group B закрыты:** `research/research`→`general/verify-claims` (RAG),
  `legal/legal`→`architect/legal-compliance`, `security/security`→`architect/security-design`
  (run-time ↔ design-time). 7 super-skill-only бакетов (creative/finance/legal/…) оставлены —
  они единственное покрытие домена.
- **Serena запиннована на тег релиза** (`constants.SERENA_SRC = git+…/oraios/serena@v1.5.3`,
  было bare-main) — breaking-изменение в main не сломает код-граф у всех проектов внезапно. Один
  bump-пойнт. Версия **верифицирована через RAG** (последний релиз v1.5.3, 2026-05-26;
  `@agentmemory/agentmemory ^0.9.26` и jscpd-`npx --yes` проверены — актуальны, действий не нужно).

## [0.5.0] - 2026-06-26

### Fixed (аудит — устойчивость фан-аута, гейты CI, хвосты)

- **maind sync — fail-soft фан-аут** (`sync.run_sync`): падение одного провиженера больше НЕ валит всю
  раскатку — остальные отрабатывают, упавший помечается `status=failed` per-project (виден в выводе,
  код возврата `cmd_sync` ненулевой). `_agent_pack_run`: `rc!=0` → `failed` (был `skip` — провал
  рендера пака был невидим); `harness недоступен` остаётся graceful `skip`.
- **validate.sh: гейт двуязычной свежести** (секция 14) — `check-translations.sh --strict`: правленый
  `SKILL.ru.md` без регенерации `SKILL.md` (или без `ru-source-sha256`) теперь падает в CI, а не молчит.
- **bin/swissknifeman:** убран мёртвый алиас `validate` (skiller-команды такой нет — роутинг давал
  «Неизвестная команда»).
- _Проверено, НЕ баг:_ `config.example.json` `type=node-package` + `code_language=python` — намеренная
  демонстрация override смешанного репо (есть `_comment_code_graph`), не дефект.
- _Отложено (tracked):_ RAG-верификация актуальности внешних пинов (`@agentmemory/agentmemory ^0.9.26`,
  Serena git-pin, jscpd, ruff) — по методологии `decision-verification` делается ПЕРЕД bump'ом
  зависимости; bump'а здесь нет. Аудит upstream-super-skill (name=dir, обратные ссылки) — отдельный
  per-skill пасс.

### Added (аудит — покрытие локальных скиллов + сценарные рецепты архетипов)

- **Новый governance-скилл `harness-operations`** (`.claude/skills/`) — у пакета `harness` не было ни
  одного операционного скилла. Карта команд (`permissions`/`mcp`/`hooks`/`agent-packs`/`doctor`),
  каталог пресетов (`settings.*` по стекам, `mcp/<name>.json`, режимы auto-approve), и недокументированная
  подсистема **agent-packs** (4 стек- + 4 роль-пака с `pack:if`-шаблонизацией). Чтобы агент не гадал
  при задаче на окружение Claude Code.
- **`maind-overview` расширен:** `maind verify` (пруф-оф-лайф vs `health`), команды реестров/оркестрации
  (`projects`/`agents`/`namespaces`/`workspace`/`run`/`fleet`/`migrate`/`deploy`), таблица 11 MCP-инструментов
  с заметкой об изоляции scope (per-project сервер ограничен своим проектом).
- **Архетип Blender** — был пробел: `.blend`/`bpy`-проект детектился как `standalone`. Добавлены
  `blender` в `core.PROJECT_TYPES`/`LANGUAGE_BY_TYPE` (python) + детект (`*.blend`/`blender_manifest.toml`/
  `import bpy`, раньше python-backend) + `profiles/blender.json` (бакеты blender/blender-modeling/python/
  quality). Тесты — `core/tests/test_core.py` (+3).
- **`docs/guide/archetypes.md`** — рецепты 9 архетипов (детект → бакеты/MCP/пресеты/agent-pack) +
  **неочевидные развилки** (connect vs vendor, CORE, память, namespace, Serena, Nuxt-vs-Vue-SPA) — чтобы
  онбординг типового проекта не порождал вопросов. В nav skiller-доков.
- **Сценарные тексто-кейсы (eval-харнес)** заведены для CORE-скилла `general/compact-responses`
  (`evals/{evals,pressure,triggers}.json` — типовые задачи + соблазны + точность триггера). Покрытие
  `evals/` 3→4; механизм и расширение задокументированы в `archetypes.md`.

### Fixed (аудит — свод дрейфа документации после раскола бакетов php/frontend)

- **862 протухших ссылки `php/<skill>` / `frontend/<skill>` переписаны** на актуальные бакеты по
  `skills.json` (`laravel-*`/`frontend-*`/`php-packages`/`azguard`/`botkit`/`general`) — после раскола
  ядер `php`/`frontend` на тонкие бакеты сотни кросс-ссылок в `routing.md`, `boost-compatibility.md`,
  `guide/*`, телах скиллов и `snippets/`/`references/` указывали в несуществующие пути. Свод name-driven
  (только известные скиллы, словные границы → без ложных замен), бакеты — соседние каталоги, поэтому
  относительные ссылки переписываются корректно. SKILL.ru.md правились синхронно с SKILL.md,
  ru-source-sha256 перепроставлен (`check-translations` чист). **Регресс-гейт** в `validate.sh` (секция
  13): протухшие `php/<skill>`/`frontend/<skill>` в `skills/`+`docs/` пакета → ошибка.
- **Счётчики и hero-ссылки выправлены:** корневой `CLAUDE.md` «20 плагинов» → «49»; `docs/index.md`
  hero `/guide/`→`/skiller/guide/` (был 404), «65+ скиллов в 10 bucket-ах» → «195 скиллов в 45».
- **skiller `CLAUDE.md`:** добавлен модуль `skillset.py` (vendor-канал `sync`/`do_sync`), исправлена
  атрибуция `sync` (была `update.py`/`vendor.py` — реально `skillset.py`), CORE-список vendor доведён
  до 7 (== `CORE_SKILLS`: добавлены `mcp-advisor`, `verify-claims`).
- **Governance-скиллы (always-loaded):** `ecosystem-integration` — починен битый канонический линк на
  `onboarding-decision-tree.md` (`../../../packages/maind/docs/guide/`); `release-discipline` — `./scripts/
  validate.sh` (в корне нет) → пер-пакетный `packages/<пакет>/scripts/validate.sh`.

### Changed (аудит — дедуп реестра: token-efficient вне CORE)

- **`general/performance` (`token-efficient`) перенесён `general` → `ai`** (`skills/ai/performance/`).
  Это Perplexity-environment super-skill (get-zeked, `notify`), дублирующий нативный
  `general/compact-responses` и сидевший в бакете `general` = CORE → раздавался плагином в КАЖДЫЙ
  connect-проект. `general` обязан быть минимальным/кросс-стек (skill-taxonomy); среда-специфичный
  дубль там не место. Перенос непокусочный (провенанс `upstream.json` сохранён, путь относительный),
  `presets/agent-context.json` перенаправлен на `ai/performance`, реестр перегенерирован
  (`skills.json`/`_index.md`/`graph.md`/`budget.md`).
- _Отложено отдельным upstream-проходом:_ 10 vendored super-skill имеют `name != каталог`
  (`pm-super-skill` vs `pm/product` и пр.) и не линкуются на гранулярные нативные скиллы. Правка
  затрагивает upstream-канон + провенанс каждого — это аккуратный per-skill пасс (и, возможно,
  отдельное решение, нужны ли эти композитные super-skill в реестре наряду с гранулярными), а не
  быстрый свод. `reka-ui-cva` уже `requires: [tailwind-conventions]` (находка аудита неактуальна).

### Fixed (аудит — логика раздачи скиллов: requires / update / CORE)

- **`sync` теперь резолвит транзитивные `requires`** (`skillset.resolve_skillset`). Skill-granular
  `include` молча терял зависимости (64/195 скиллов их объявляют): `include: [api-design]` копировал
  api-design, но не его `requires: [data-schema]`. Добавлен транзитивный обход (паритет с
  `vendor.resolve_requires`): `exclude` по-прежнему побеждает зависимость с warning. Регрессия —
  `test_skillset.py::{test_sync_pulls_transitive_requires,test_sync_exclude_beats_requires}`.
- **`skiller update` распознаёт sync-канал** (`update.update_one`). sync и legacy-vendor пишут
  ОДИН `.swissknifeman-manifest.json`, поэтому на sync-проекте `update` уходил в legacy `do_vendor`
  (bucket-granular из `.swissknife.json`/профиля), игнорируя skill-granular `.swissknifeman/config.json`.
  Теперь при наличии sync-конфига `update` пере-применяет его через `do_sync` (как уже делает
  `integrate`). Регрессия — `test_update.py::test_update_routes_sync_config_to_sync`.
- **CORE-фолбэк канал-независим** — `MINIMAL_BUCKETS` (набор для нераспознанного типа проекта) втягивал
  бакет `system` целиком, включая `system/{shared-memory,cross-project-coordinator}` — ровно дубли
  хаба maind, что CORE-политика гонит через `DEFAULT_EXCLUDE`. Теперь `MINIMAL_BUCKETS == CORE_BUCKETS`
  (general+oss-dev) — фолбэк не противоречит политике.
- **Зарезервированные ключи `.swissknife.json` честно помечены** (`config.validate_config`) — `shape`/
  `stacks`/`coordinator_ignore`/`presets` валидировались, но не читались connect/vendor; теперь
  предупреждают «зарезервирован/не действует» (как `skills_map`), а не молчат. Удаление ключей не
  делаем (валидация строгая — сломало бы существующие конфиги); `memory_brain` реально потребляется
  (integrate↔harness) и не трогается.

### Fixed (аудит — фундамент-дедуп раздачи скиллов: единые примитивы)

- **Утечка `SKILL.ru.md` (русский SSOT) в downstream-проекты через `sync`** — канонический
  Claude-канал `skillset.sync_skillset` копировал каталог скилла, исключая лишь
  `upstream.json`/`.claude-plugin`, но НЕ `SKILL.*.md`/`evals/` (в отличие от `vendor.copy_skill`).
  Полный русский источник и поведенческие тесты ехали в каждый из 195 скиллов потребляющего
  проекта. Введён ЕДИНЫЙ `common.SKILL_IGNORE = (upstream.json, .claude-plugin, SKILL.*.md, evals)`
  — `vendor` и `sync` теперь игнорируют один список (раньше дублировали и разъехались). Регрессия —
  `tests/test_skillset.py::test_sync_excludes_ru_source_and_evals`.
- **Дедуп containment-хелпера** — `connect`/`vendor`/`skillset`/`doctor` дублировали
  `str(p.resolve()).startswith(str(root.resolve()) + os.sep)`. Сведено к `common.is_within`
  (резолвит symlink — для prune) и `common.is_within_lexical` (без резолва финального symlink —
  для install-гейта против traversal через `../` в имени скилла). `vendor.copy_skill` теперь снимает
  symlink на месте назначения до `copytree` (иначе писал бы сквозь него в чужую цель).
- **Атомарная запись JSON** — `vendor.write_manifest` писал манифест сырым `write_text` (краш
  оставлял битый файл, ломающий `update`/`connect`/`status`); `skillset.write_lock`/`lock.cmd_lock`/
  `topology.save_topology` вручную дублировали `tmp+os.replace` без подчистки `.tmp`. Все переведены
  на `core.io.atomic_write_json`. `harness/apply-permissions.sh` пишет settings атомарно (tmp+`mv -f`)
  и падает с русской ошибкой (а не traceback) на битом входном JSON.

### Security (аудит — закрыты 2 бреши: RCE и обход namespace-изоляции памяти)

- **maind MCP: серверный энфорс изоляции namespace** (`lib/maind/mcp.py`, `memory.py`). Раньше
  `scope = args.get("scope") or default_scope` отдавал приоритет КЛИЕНТУ: агент проекта A,
  передав `{"scope":"project:B"}`, читал/писал/удалял приватную память проекта B (а графовые
  инструменты — топологию по произвольным `from`/`project`), хотя сервер раскатан запинненным к
  своему проекту (`maind mcp --scope project:<id>`). Теперь сервер, запинненный к проекту,
  ограничен бакетами СВОЕГО проекта (`recall_scopes`: приватный + `ns:<его группы>` + `global`);
  графовые инструменты режут доступ к проектам, не делящим namespace (`namespaces.shares`);
  `forget` подтверждает владение фактом по маркеру `[[s:<scope>]]` до удаления (memoryId глобален).
  Хаб-режим (`default_scope=global`) и явный `MAIND_MCP_ALLOW_CROSS_SCOPE=1` — без ограничений
  (back-compat/админ). Регрессия — `tests/test_mcp.py::TestScopeIsolation` (+9).
- **harness review-gate: устранён RCE при открытии чужого репо** (`configs/claude-code/hooks/review-gate/review-gate.sh`).
  Хук на `SubagentStop` (ставится глобально) исполнял `check_command` из project-local
  `.claude/review-gate.config.json` через `bash -c` — любой посторонний репозиторий получал
  произвольное исполнение кода. Теперь `check_command` берётся ТОЛЬКО из machine-owned
  `$HOOK_DIR/config.json`; project-local конфиг честно исполняется лишь при явном opt-in владельца
  машины (`ALLOW_PROJECT_CONFIG=1` в `$HOOK_DIR/env.ini`).
- **harness auto-approve strict: интерпретаторы и awk/sed больше не авто-одобряются**
  (`configs/claude-code/hooks/auto-approve/config.json`). `_normalize` вырезает тело в кавычках,
  поэтому `python -c "<код>"` / `awk 'BEGIN{system(…)}'` виден анализатору лишь головой команды —
  одобрять её = одобрять произвольный код. `trust_inline_interpreters` → `false` по умолчанию;
  `awk`/`sed` убраны из `allow` (включение inline-интерпретаторов — осознанный per-project выбор).
  Регрессия — `harness/tests/test_security_hooks.py` (+5, реальные хуки через subprocess).

### Added (skiller — eval-харнес скиллов + composite-upstream `merge`)

- **`skiller eval <bucket>/<name>`** (`lib/skiller/eval.py`) — поведенческое тестирование скиллов,
  которого не было (валидация была только структурной). Формат `evals/`: `evals.json` (кейсы +
  **детерминированные** ассершены `contains`/`not_contains`/`regex`/`not_regex`/`file_exists`/
  `file_absent`/`min_words`), `pressure.json` (сценарии-соблазны «пропустить скилл» — TDD для
  документации), `triggers.json` (точность срабатывания `description`). Прогон with-skill vs
  `--baseline` через `claude -p` → `benchmark.json` (pass-rate, токены/тайминги mean±stddev, Δ);
  `--static` пишет HTML-отчёт; `--scaffold` создаёт стабы; `--triggers` — оптимизация описания
  (≤150 симв., правка через `SKILL.ru.md`→EN). Адаптировано (методология, не код) из Anthropic
  `skill-creator` + obra/superpowers `writing-skills`. **CI офлайн:** нет `claude` → мягкая деградация.
- **Гейт и покрытие в `validate.sh`** — жёсткая валидация формата заведённых `evals/*.json` + сводка
  `evals coverage: X/Y` одной строкой (без per-skill шума). `generate-skill` и root-скилл
  `skill-authoring` переведены на **eval-first**. `evals/` НЕ вендорится (`vendor.copy_skill`) и
  исключён из `skill_content_hash`. Сиды: `general/verify-claims`, `general/anti-drift`,
  `quality/code-review`. Юнит-тесты — `tests/test_eval.py` (офлайн).
- **upstream.json `strategy: merge`** — скилл, собранный из **нескольких внешних источников**:
  `origins[]` с ролями (ровно один `base` + ≥1 `supplement`/«suggest», с подсказкой `note`/`suggest`
  чем дополнил). Синк **ручной под управлением агента**: на дрейфе любого origin
  `merge.review_pending=true` блокирует `validate.sh`/`registry`/релиз до ручного пере-merge
  (как гейт `fork`), авто-overwrite запрещён. Валидация в `validate.sh`; DX-схемы
  `schema/{evals,upstream}.schema.json`; доки `docs/guide/evals.md` + `upstream-sync.md`.

> Контекст: рецензия трёх внешних skill-репозиториев (anthropics/skills, obra/superpowers,
> affaan-m/ECC) — закрыт крупнейший пробел реестра (поведенческое тестирование скиллов) и добавлен
> провенанс composite-скиллов из нескольких источников с ручным agent-merge.

### Added (verify-claims — RAG-верификация внешних фактов в ревью и планировании)

- **Скилл `general/verify-claims`** (CORE, двуязычный RU→EN) — эпистемический гейт против решений по
  устаревшему знанию. Классифицирует заявление: **repo/code-grounded** (читаю код — без проверки) ·
  **стабильное общее знание** (без проверки) · **внешнее + staleness-чувствительное** (версии/API,
  «ещё актуально», best practice, рынок, возможности чужого сервиса/MCP, цены) → **верифицировать через
  RAG**. Лестница движков (дешёвый первым): **context7** (доки библиотек) → **Perplexity** (native MCP при
  `PERPLEXITY_API_KEY`, иначе keyless `perplexity-web`) → **WebSearch/WebFetch** → эскалация в `research/research`.
  Цитата + confidence (high/medium/low). Спец-клауза: при разборе чужого аудита внешне-мировые вердикты
  до-проверять **даже если аудит «полный»**. Добавлен в `CORE_SKILLS`.
- **`general/mcp-advisor`**: строка `perplexity` в карте серверов + кросс-ссылка на `verify-claims`
  (комплементарны: *что подключить* ↔ *когда/как доставать факт*).
- **Каталог harness**: `configs/claude-code/mcp/perplexity.json` (`@perplexity-ai/mcp-server` + env
  `PERPLEXITY_API_KEY`). Имя пакета **верифицировано через RAG** (текущий официальный `@perplexity-ai/mcp-server`,
  не legacy `server-perplexity-ask` — ровно та staleness, что ловит `verify-claims`).
- **Цепочки планирования**: `verify-claims` `produces_for: [architecture, tech-stack-selection]` (граф-рёбра) +
  house-style запрет «фиксировать внешние факты по памяти — сначала `verify-claims`» в `architect/architecture`
  и `architect/tech-stack-selection`.

> Контекст: запрос — встроить проверку внешних фактов через RAG (знание модели имеет порог, бывает неполным/
> ошибочным) в **ревью аудитов** и **большое планирование**. Repo-grounded вердикты (чтение кода) безопасны;
> внешние факты — верифицировать движком по лестнице. Дисциплина зафиксирована скиллом и применяется в процессе.

### Added (skiller — рецензия плана Perplexity: mcp-advisor, github-ops, слои)

- **Скилл `general/mcp-advisor`** (CORE, двуязычный RU-источник→EN-канон) — чеклист **подбора
  MCP-серверов под проект** при онбординге/синке. Закрывает пробел: профили/онбординг прикручивают
  MCP статично (почти всем — только `context7`), без предложений что подключать. Меню = каталог
  harness (context7/playwright/github/fetch/sequential-thinking/filesystem) + хаб `maind`; по каждому —
  когда нужен/не нужен и цена (схема в каждом запросе + permissions + Node/uvx-деп). Правила: память/граф
  через `maind` (не generic `memory`-MCP), рутинный GitHub-review через `gh` CLI (не тяжёлый `github` MCP).
  Добавлен в `CORE_SKILLS`; кросс-ссылка с `context-economy` (подбор ↔ обрезка).
- **Пресет `github-ops`** — бандл разбросанного GitHub-набора: `roles/open-source-maintainer` +
  `oss-dev/{github-flow,gh-review,issue-triage,release-engineering,oss-governance}` + `devops/ci-cd`.
  Единственный реальный пробел из «Этапа 3» плана (скиллы были, единого пресета — нет).
- **Доки**: `routing.md` — секция «Архитектурные слои: что куда» (4-слойное правило-стоп на реальном
  3-пакетном сплите skiller/maind/harness, ссылки на канон пакетов); `skiller/docs/guide/upstream-sync.md`
  — кросс-ссылка на каталог источников `references/README.md` (дискаверабилити каталога из сайта доков).

> Контекст: рецензия `research/swissknifeman_final_plan.md` (внешний аудит Perplexity). Большинство
> «этапов» оказались уже сделаны (MCP-façade `maind` 11 tools, профили/пресеты, upstream-каталог, качество
> кода `cde47b8`) или переосмыслены на 3-пакетный сплит; форма-дубликаты (`config.engines/packs`, `swiss.*`
> переименование MCP, ручной `capability-matrix`, `docs/upstream/`) **отклонены** как параллельные реестры.
> Взяты только не-дублирующие слайсы (этот блок). Полный разбор с фаворитами —
> `research/swissknifeman_final_plan_review.md`.

### Added (skiller — рецензия аудита архитектуры: init, JSON-схемы, level, доки-истина)

- **`skiller init`** — новая команда: создаёт `.swissknifeman/config.json` (vendor) из
  автодетекта типа проекта + профиля, **без** копирования скиллов (это делает `sync`).
  Идемпотентна (существующий конфиг не перетирается без `--force`), `--dry-run`. Логика —
  общий хелпер `materialize_skillset_config` (вынесен из `do_sync`, чтобы init и sync не
  разъезжались). Зарегистрирована в `cli.py` + лаунчерах `bin/skiller`/`bin/swissknifeman`.
- **JSON-схемы конфигов** (`schema/swissknife.schema.json`, `schema/swissknifeman-config.schema.json`)
  — DX/IntelliSense через `$schema`. Рантайм-валидация остаётся ручной и **stdlib-only** (без
  pip `jsonschema`); синхрон схемы↔код держат гейт `tests/test_schema.py` (гоняется в `validate.sh`)
  и две проверки `skiller doctor`. Валидаторы конфигов теперь пропускают ключи на `_`/`$`.
- **Опц. поле фронтматтера `level`** (`core|foundation|extension`) — само-документирование слоя
  иерархии; пишется в `skills.json` (omit-when-empty), enum-гейт в `validate.sh`, tally-потребитель
  в `skiller registry`, добавлено в preserve-list генератора канона и `SKILL_TEMPLATE.md`. Opt-in:
  ни один скилл пока не помечен (нулевой churn sha256 у потребителей).
- **`content_sha256` — дрейф-хеш по всему каталогу скилла** (`common.skill_content_hash`,
  пишется в `skills.json` рядом с `sha256`). Закрывает дыру: инкрементальный `sync` детектил
  дрейф только по `SKILL.md` и **пропускал** правки в `snippets/`/`references/`. Теперь `plan_sync`
  ловит их и обновляет скилл. Игноры — как у vendor (`upstream.json`/`SKILL.*.md`/`.claude-plugin`),
  хешируется ИСТОЧНИК (копия отличается игнорами). Старые локи без `content_sha256` деградируют
  корректно (дрейф по `SKILL.md`), поле доpopulated при следующем sync **без** перекопирования.
  Единственный принятый пункт из аудита `research/skiller_delivery_modes_and_manifest.md`.
- **Документация-истина**: новый канон `docs/guide/skills-architecture.md` («реальное состояние»,
  читается первым — против straw-man) + запись в навигацию (standalone + зонтичный VitePress).
  Truth-up локальных скиллов `package-architecture`/`project-tooling-runbook` (два конфига; тела
  скиллов читает Claude Code, не Python). Decision-record в шапках обоих research-доков аудита
  (были помечены «Готов к реализации» — теперь «отрецензировано, НЕ как есть»).

### Rejected (рецензия аудита — обоснованные отказы)

- **3-уровневый рефакторинг скиллов** (core/foundation/extension) — отклонён: иерархия/зависимости/
  уровни уже есть; «бери подскиллы» решено skill-granular vendor; цена churn (193 двуязычные пары,
  49 плагинов, локи) несоразмерна. Выгода взята дёшево полем `level`.
- **Подсистема кэширования** (`SkillMemoryCache`/disk-cache/команды `cache`) — отклонена: нет
  вызывающего (тела скиллов читает Claude Code, не Python; `load_skill` не существует). Prompt
  caching у Claude Code автоматический. Микро-мемоизация парса фронтматтера тоже не внедрена
  (конфликт с конвенцией «без модульных глобалей», выигрыш ниже порога восприятия).

### Added (skiller — двуязычные скиллы: компактный EN-канон + полный RU-источник)

- **193 скилла переведены в двуязычную модель.** Локальные (139): `SKILL.ru.md` — полный русский
  ИСТОЧНИК (его правит человек, SSOT), `SKILL.md` — компактный английский канон (генерируется из RU,
  грузит только его агент; русский в контекст не попадает). Внешние (54): EN-канон от upstream не
  тронут, добавлена `SKILL.ru.md`-справка. Все 139 EN-канонов прошли adversarial-верификацию фиделити
  (ни одно правило/условие/порог/код/путь не потеряно, ничего не добавлено).
- **Экономия ~32% токенов** на телах локальных скиллов (≈268K→182K ток): английский у токенайзера
  Claude плотнее кириллицы. `budget.py` — языко-зависимая оценка (кириллица ~2.2 / латиница ~4.0
  chars/tok); карта `docs/guide/budget.md` показывает эффект.
- Поток правок: правишь `SKILL.ru.md` → регенеришь `SKILL.md` (`prompts/generate/claude-canon-from-ru.md`)
  → `check-translations.sh --stamp`. Когерентность канона метит `<!-- ru-source-sha256 -->`.
- `*.ru.md` НЕ вендорятся в проекты (едет только EN-канон); генерация выполнена многоагентным Workflow.

### Added (skiller — внедрение mattpocock/skills: инженерная методология + встраивание в цепочку)

- **9 импортированных скиллов** из [mattpocock/skills](https://github.com/mattpocock/skills) (MIT),
  fold-in в существующие бакеты (без нового бакета), `strategy: notify`:
  `quality/diagnosing-bugs` (6-фазная отладка: feedback-loop до гипотез, тег `[DEBUG-xxxx]`),
  `quality/tdd-discipline` (red-green-refactor вертикальными срезами, не горизонтально),
  `architect/codebase-design` (глубокие модули Ousterhout/Feathers: depth/seam/deletion-test;
  свёрнут HTML-report из improve-codebase-architecture),
  `architect/domain-modeling` (глоссарий `CONTEXT.md` + ADR инлайн, мульти-контекст),
  `general/implement` (цепочка implement→tdd→review, **user-invoked**),
  `oss-dev/to-issues` (план→issue вертикальными срезами + поля Affected projects/Environment, **user-invoked**),
  `oss-dev/issue-triage` (стейт-машина триажа + роль `needs-device-access` для железа, **user-invoked**),
  `oss-dev/resolving-merge-conflicts`, и центральный `general/grill-with-docs` (грилинг + доменная
  модель против внешних API/RFC-спек, **user-invoked**).
- **Уровень + условия активации на каждый скилл** (ответ на «не папки, а в цепочку»): компактный
  `description`-роутер (ярус-0 always), lean-тело (ярус-1 on-trigger), под-файлы mattpocock →
  `snippets/` (ярус-2 on-demand); сайд-эффектные (implement/to-issues/issue-triage/grill-with-docs) —
  `disable-model-invocation: true`; `general/git-safety` — `lifecycle: init`. НЕ в CORE — opt-in.
- **Встроены в цепочку рёбрами `requires/produces_for`**: grill-with-docs→{spec-interview,domain-modeling};
  to-issues→github-flow, produces_for→implement; implement→{tdd-discipline,code-review};
  diagnosing-bugs→code-review; codebase-design→{refactoring-plan,architecture};
  domain-modeling→{architecture,api-design,data-schema}; resolving-merge-conflicts→git-commit-rules.
  Плюс секции «Связанные скиллы» в каждом теле.
- **Раздача через presets** — новый `presets/engineering-workflow.json` (сквозной конвейер) +
  расширены `agent-tasks` (grill-with-docs/implement/to-issues), `code-quality` (tdd-discipline/
  diagnosing-bugs), `system-design` (codebase-design/domain-modeling).
- **Расширен `general/spec-interview`** (наш грилинг) — ссылки на `grill-with-docs`/`to-issues`/`implement`.
- **git-guardrails → harness, не скилл** (поправка к аудиту): PreToolUse-хук
  `block-dangerous-git.sh` (+`force-with-lease`/`rebase --onto`) в
  `packages/harness/configs/claude-code/hooks/git-guardrails/`, обёртка-скилл `general/git-safety`.
- **Агенты грузят новые скиллы через `skills:`**: `issue-triager`←`issue-triage`,
  `sprint-planner`←`to-issues`, `review-gatekeeper`←`diagnosing-bugs`/`tdd-discipline`
  (harness agent-packs `role-maintainer`/`role-tech-lead` → 0.2.0).
- **Провенанс**: источник зарегистрирован в
  [references/mattpocock-skills.md](packages/skiller/references/mattpocock-skills.md) (`imported`) +
  per-skill `upstream.json` (sha256/fetched_at, HEAD `5d78bd09`).

### Added (skiller — токеновый бюджет + карта-диаграмма + промты + задел переводов)

- **Команда `skiller budget`** — трёхъярусная модель раскрытия контекста: **⊕ always**
  (`name`+`description`, резидентно в каждом запросе — постоянный «налог»), **↻ on-trigger**
  (тело `SKILL.md`), **⌥ on-demand** (сниппеты). Режимы: `--config F.json`, `--compare a,b`,
  `--json`, `--profile/--buckets/--exclude`, `--no-core`, `--write-map`. Модуль
  [budget.py](packages/skiller/lib/skiller/budget.py) — **единый источник** токен-математики
  (переиспользует `resolve_selection`/`collect_skills`/`resolve_requires`, без дублирования
  выборки). +9 unit-тестов (`tests/test_budget.py`).
- **Карта токенового бюджета** — сгенерированная mermaid-страница
  [docs/guide/budget.md](packages/skiller/docs/guide/budget.md): узел на скилл (по бакетам),
  heat-цвет по ⊕ always, рёбра `requires` = транзитивный налог, таблицы по бакетам и топам.
  Регенерится `skiller registry` (in-process, после графа); пункт в VitePress sidebar.
- **Строка бюджета в `skiller status`** — ⊕ always/↻ bodies набора проекта + топ-3 описаний.
- **Промт-библиотека** [prompts/](packages/skiller/prompts/) (audit/review/generate) — шаблоны
  для сопровождения реестра (то, что `validate.sh` не ловит: пересечения, водность, дубли).
- **Задел переводов** — `SKILL.<lang>.md` gitignored (агент грузит только `SKILL.md`); чекер
  покрытия [check-translations.sh](packages/skiller/scripts/check-translations.sh) (`--lang`,
  `--generate-stubs`).
- *Из аудита Perplexity — отклонено как дубль:* `generate-graph.ts` (= существующий
  `generate-graph.sh`) и `drift-check.ts` (= `validate.sh`); токен-модель аудита исправлена
  (тело ≠ «всегда загружено» → трёхъярусная).

### Added (skiller — пресеты/кластеры скиллов + тонкие бакеты для конфиг-управляемого per-project sync)

- **Слой пресетов** — `presets/<name>.json` (`{name, description, extends?, buckets?, include?}`):
  именованные кластеры скиллов для vendor-выборки. Раскрываются в `resolve_skillset`
  ([skillset.py](packages/skiller/lib/skiller/skillset.py)) ДО формулы **`(presets ∪ buckets ∪ include) − exclude`**,
  с рекурсивным `extends`. Конфиг проекта `.swissknifeman/config.json` ссылается на `presets: [...]`
  (+ `include`/`exclude` оверрайды) → `skiller sync` → `.claude/skills/` + `skills-lock.json`. Только vendor
  (connect бакет-атомарен). Валидация в [validate.sh](packages/skiller/scripts/validate.sh) (refs резолвятся,
  ацикл `extends`); +5 unit-тестов (`tests/test_skillset.py::TestPresets`). `presets`-ключ в `SKILLSET_KEYS`/`CONFIG_KEYS`.
- **Тонкие бакеты вместо монолитного `php`** (44→13 core): `php` стал линяным ядром (laravel, structure,
  conventions, DI, database, repositories, patterns, static-analysis), а feature-области вынесены в отдельные
  бакеты-плагины — `laravel-testing`, `laravel-filament`, `laravel-livewire`, `laravel-data-layer`,
  `laravel-auth`, `laravel-architecture`, `laravel-extras`. Filament/Livewire больше **не тянутся по умолчанию**
  (включаешь точечно). `php-packages` — разработка Laravel-пакетов (9 скиллов). `azguard`/`botkit` — отдельные
  одиночные бакеты (под будущий перенос скилла внутрь самого пакета).
- **Тонкие бакеты вместо монолитного `frontend`** (35→3 core): ядро `frontend` (web-design-guidelines,
  document-writer, filepond-upload) + feature-бакеты `frontend-{vue,nuxt,tailwind,naive-ui,reka,vite,linting,
  animations,figma,wayfinder,backend}`. Nuxt/Naive-UI/Figma и пр. — отдельные плагины, не по умолчанию.
- **19 пресетов** (сквозные стеки): php — `laravel-admin`/`laravel-enterprise`/`laravel-inertia`/`laravel-livewire-stack`;
  frontend — `vue-spa`/`figma-to-frontend`; + кластеры `architect`/`pm`/`general`/`quality`.
- **Профили** под линяный дефолт: `laravel-project` = ядро + `laravel-testing`/`laravel-auth`/`laravel-data-layer`;
  `node-frontend` = ядро + `frontend-vue`/`frontend-vite`/`frontend-linting`/`frontend-tailwind`;
  `php-package` += `php-packages`/`laravel-testing`. Feature-бакеты (Filament/Livewire/Nuxt/…) — opt-in.
- **buckets.json** +21 бакет; **docs**: новый `docs/guide/presets.md`, обновлены `vendor-mode.md`/`profiles.md`/
  `skill-anatomy.md` + раннбук `project-tooling-runbook`. Регенерация `skiller registry` (49 плагинов).
- *Отклонено (Perplexity, с аргументацией):* skiller как PHP-приложение (`src/*.php`) и `.swissknife.yml`/`.lock`
  с нуля — механизм уже есть (Python + JSON); мерж `laravel-package-*` — это upstream-скиллы (мерж рвёт трекинг);
  новые домен-скиллы (fintech/fiscal) — project-local.

### Added (skiller — `strategy: fork`: сопровождение доработанных вендорных скиллов)

- **Новая стратегия `upstream.json` — `fork`** (помимо `replace`/`notify`): внешний скилл с нашими
  правками, который **нельзя автообновлять**. `files[].path` указывает на **pristine-зеркало**
  (напр. `references/source.md`), правки живут в тонкой обёртке `SKILL.md`; на дрейфе апстрима
  ставится `review_pending: true`. Эскалация `replace` (зеркало) → `notify` (сообщить) → `fork`
  (правки + базлайн + ручной перенос + жёсткий гейт).
- **`validate.sh`**: enum стратегий расширен `fork`; **гейт** — `review_pending: true` → ERROR
  (блокирует `skiller registry`/релиз, пока дрейф не перенесён вручную). Проверка bool/`last_review`.
- **`update-upstreams.sh`**: ветка `fork` — `--check` сообщает о дрейфе (exit 10), `--apply`
  стейджит свежий апстрим в `upstream/<name>.incoming.md` и поднимает `review_pending` (зеркало и
  `SKILL.md` НЕ трогаются); новый режим **`--resolve`** — после ручного переноса продвигает incoming
  в зеркало, обновляет `sha256`/`fetched_at`/`last_review`, снимает флаг (работает оффлайн).
- **`ai/ai-agents` переведён `notify` → `fork`**: монолит (2722 стр. в `SKILL.md`) → тонкая
  обёртка-навигатор `SKILL.md` (грузится при активации) + полный апстрим в `references/source.md`
  (грузится по требованию). Закрывает обе оси: context-economy (lazy-load) и трекинг (1 файл ↔ 1 url,
  тривиальный перенос диффа). Блокировка дрейфа — **только в реестре**; в проекты по-прежнему
  вендорится чистая копия (`upstream.json` вырезается). +1 тест (provenance fork через путь
  `references/source.md`, fallback `files[0]`); `*.incoming.md` в `.gitignore`. Доки:
  `upstream-sync.md` (раздел fork), `creating-skills.md`.

### Fixed (skiller — мелочь по аудиту)

- **`context-economy`**: перекрёстная ссылка на скилл `pao` приведена к стандартному формату
  (`` `pao` (bucket: php) `` вместо нестандартного `laravel/pao`).

### Added (skiller — vendor-канал «опубликовать скиллы в репо» на онбординге)

- **`integrate --skills-channel connect|vendor|skip`** + интерактивный вопрос канала (TTY). Канал
  `vendor` для Claude-проекта теперь роутится в **современный `sync`** (`skillset.do_sync`):
  `integrate` материализует `.swissknifeman/config.json` из профиля проекта и применяет `sync` —
  физ. копии скиллов в `.claude/skills/` + `skills-lock.json` (`managed`). Закрывает кейс
  **внешних разработчиков**: проект отдают в команду без доступа к реестру swissknifeman, скиллы
  едут файлами в самом репо (у `connect` marketplace указывает на локальный путь к реестру → у
  чужого разработчика плагины не подключатся). Legacy `do_vendor` (`.ai/.cursor`) остаётся только
  для `--agent cursor|generic`. Выбор канала касается **только скиллов** — память/граф/MCP хаба не
  затрагиваются. +6 тестов (do_sync: материализация конфига / уважение курированного / dry-run;
  integrate: vendor→sync, skip, невалидный канал).
- **`maind onboard --skills-channel` / `swissknifeman setup --skills-channel`** — проброс канала в
  `skiller integrate`; `onboard` интерактивно спрашивает канал (как и механизм памяти), флаг — для
  неинтерактива (дефолт `connect`).
- **Гигиена каналов в `skiller status`**: предупреждение `ДУБЛЬ КАНАЛОВ`, если один бакет активен
  ОДНОВРЕМЕННО как плагин (connect) и вендорен (vendor) — скиллы раздавались бы дважды. Проверка
  (`channel_overlap`) живёт ТОЛЬКО в skiller (владелец скиллов) и доступна из зонтика через
  `swissknifeman skills status` — не дублируется по пакетам. +4 теста.
- **Тесты гигиены `skills-lock.json`** (managed vs чужое): запись, добавленная в lock вручную
  (свой скилл / другой хаб, `managed!=true`), переживает `sync` и не удаляется даже при пустом
  конфиге; ручная чистка managed-записи при живой папке → без `--force` путь считается чужим
  (пропуск), с `--force` скилл чисто пере-усыновляется (одна managed-запись, без хвостов/дублей).
  +3 теста. Закрепляет инвариант «синхронизируем только своё (`managed: true`)».

### Security / Fixed (maind — портабельность генерируемых хуков, без утечки пути)

- **Хук-скрипты maind больше не зашивают абсолютный путь к лаунчеру.** Шаблоны
  `templates/health/*.sh` (memory-digest · session-start · feature-log) резолвят `maind` в рантайме
  (`env MAIND_BIN → command -v maind`), а не подставляют машинно-специфичный
  `<…>/packages/maind/bin/maind` через `_maind_bin` (удалён). Генерируемый артефакт теперь одинаков
  на любой машине; лаунчер не найден → тихий no-op (как при лёгшем демоне). Конфигурируется через
  env `MAIND_BIN` (можно из `.claude/*.env.ini`). Бэк-совместимо: уже раскатанные хуки работают,
  `command -v maind` резолвит тот же `~/.local/bin/maind`. +3 теста (нет abs-пути, есть env→PATH).
- **`.claude/maind-*.sh` (+ `.maind-feature-log.last`, `scheduled_tasks.lock`) в `.gitignore`** —
  генерируемые per-project хуки/рантайм-state не попадают в репо, как `.mcp.json`. Закрывает утечку
  абсолютного пути автора при `git add .claude/`.
- **Аудит MCP** (без изменений — уже чисто): пресеты `packages/harness/configs/claude-code/mcp/*.json`
  портабельны (`npx`/`uvx`/`http`, без abs-путей); `.mcp.json` (с abs-путём maind) уже gitignored,
  шаблон — `.mcp.json.example` с `{{REPO_ROOT}}`, реальный файл генерит `maind` на деплое.

### Fixed (третий аудит skiller — харденинг тихих отказов)

- **`_registry_index` больше не теряет скиллы молча**: запись в `skills.json` без `name`/`path` и дубль
  короткого имени между бакетами теперь логируются `warn` — раньше немой `continue`/`setdefault` ронял скилл
  из синка без следа (по полному пути `bucket/rel` дубль доступен, по короткому имени — первый). +тесты.
- **subprocess в harness с таймаутом** (`common.apply_permissions`, `integrate._run_harness`): `timeout=30`
  + stderr в `warn` — зависший harness (NFS/сеть) больше не морозит `skiller sync` молча; stdout оставлен
  живым (прогресс harness виден). Дополняет returncode-проверку из прошлого аудита.
- **манифест атомарен и трассируем** (`skillset._write_manifest`): запись через `core.io.atomic_write_json`
  (tmp+`os.replace` вместо raw `write_text` — нет полузаписанного файла при крахе) + `installed_at` через
  `now_iso()` (время, не голая дата) + `version` схемы. +тест.
- **frontmatter читает YAML-блок-скаляры** (`common.parse_frontmatter`): `description: |`/`>` (многострочные)
  больше не теряются молча — stdlib-разбор без `pyyaml`, с защитой от значений, начинающихся с `|`/`>`. +тесты.
- **`skills_map` не молчит** (`config.validate_config`): зарезервированный, но нереализованный ключ
  помечается `warn` вместо тихого игнора.

> Отклонено как ложное (проверено по исходнику): path-traversal в `contained()` — код уже добавляет
> `+ os.sep`, пример `/skills_extra` не проходит против `/skills/`; «обрезанная `parse_inline_list`» — функция
> целая; «ввести профили как first-class» — 8 профилей + флаг `--profile` уже есть; рекурсивный `_dir_sha256`
> — намеренно зеркалит per-file хеш реестра (рекурсия рассинхронит lock с `skills.json`); `import yaml` —
> нарушает stdlib-only, заменён stdlib-хендлером.

### Fixed (второй аудит skiller — реальные баги)

- **`integrate` больше не глушит ошибки harness**: `_run_harness` проверяет returncode и `warn`-ит при
  ненулевом — раньше визард молча рапортовал «готово», даже если блок не применился. Graceful
  degradation сохранена (визард не падает).
- **frontmatter устойчив к BOM** (`common.parse_frontmatter`): чтение `SKILL.md` через `utf-8-sig` —
  файл с BOM больше не игнорируется молча. +тест.
- **`projects.json` без дублей**: `upsert_project`/`db_records` нормализуют путь через `Path.resolve()`
  (раньше разные repr одного каталога — `./`, `..`, симлинк — плодили дубли). +тест.
- **`boost.json::skills` сортируется целиком** (`sorted(existing + added)`, не только `added`) —
  детерминированный порядок.

> Отклонено как ложное/over-engineering для Linux-only single-user (с обоснованием в плане): «double-nesting
> `extraKnownMarketplaces`» — это корректная схема Claude Code (подтверждено реальными конфигами);
> frontmatter «режет на `:`» (там `split(":",1)`); TOCTOU/атомарность `copy_skill`; Windows-пути; mmap/
> чтение-частями мелких файлов; ротация `.bak`; `deque` вместо `pop(0)`.

### Security / Fixed (аудит репозитория — зонтик, core, CI)

- **`.mcp.json` выведен из-под git** (`git rm --cached` + `.gitignore`): машинно-специфичный файл
  с абсолютными путями к `maind` (утечка пути автора + ломал клон у других). Шаблон —
  `.mcp.json.example` (плейсхолдер `{{REPO_ROOT}}`); реальный файл генерит `maind` (sync/deploy).
- **`core.atomic_write_text`**: при ошибке записи/`os.replace` подчищает осиротевший `.tmp`
  (`try/except → unlink`) — иначе мусор копился в долгоживущих процессах (напр. `No space left`). +тест.
- **`bin/swissknifeman doctor`**: больше не прерывается на первом отсутствующем лаунчере
  (`need()` бил `exit 1`) — fan-out на все три пакета с агрегацией итогового exit-кода.
- **`install.sh`**: собирает упавшие пакетные установки и завершает `exit 1` со списком — раньше
  печатал «Готово» и выходил 0 даже если пакеты не установились.
- **`scanner-pr.yml`**: имя ветки берётся из репозитория (`git rev-parse --abbrev-ref HEAD`), а не из
  продублированной формулы `$(date +%Y%m%d)` (гонка на границе суток); снят `|| true` с `git push`
  (реальный сбой push больше не маскируется перед `gh pr create`).
- **`core/env.py`**: `BaseEnv.home` default_factory зовёт `Path.home()` при создании (а не модульный
  снимок) — подменённый `$HOME` подхватывается в тестах. Глобал `HOME` сохранён (публичный API). +тест.

### Changed (документация и CI — аудит)

- **README**: добавлен пакет `harness` (таблица + CLI) и корневой роутер `swissknifeman`/`setup`;
  убрана устаревшая фраза «единой консоли-обёртки нет».
- **`CONTRIBUTING.md`** (корневой) — новый: раскладка, dev-установка (stdlib-only/без pip, IDE
  extraPaths вместо pip), тесты/валидация, конвенции, релизная дисциплина.
- **CI `test.yml`**: матрица Python расширена 3.9–3.12 → 3.9–3.13.
- **`MERGE-PLAN.md`** удалён (рабочий артефакт процесса слияния, ценности для пользователя нет).

### Added / Tooling (follow-up аудита — улучшенные варианты)

- **`pyrightconfig.json`**: Pylance/pyright резолвят `from core import …` и межпакетные импорты
  из коробки (`extraPaths`: корень `.` + `packages/*/lib`, `typeCheckingMode: off`) — IDE-DX без pip,
  stdlib-only цел. PyCharm — Sources Root (см. `CONTRIBUTING.md`).
- **`swissknifeman --version` / `-V`**: версия монорепо из `git describe` (фолбэк «dev»). Заодно
  убран висячий `version` из роутера — он делегировал в `skiller version`, которой не существует.
- **Линтер ruff в CI** (job `lint`): `pipx run ruff==0.15.19 check` — эфемерно, ruff НЕ зависимость
  репо; конфиг `ruff.toml`, набор `F,B`, `target-version=py39` (B905 не конфликтует с 3.9). Разовая
  зачистка: 6 неиспользуемых импортов, 8 пустых f-строк, 9 unused loop-vars, 1 broad-except в тесте.
- **Per-project `code_language(s)`** (maind/codegraph): override языка код-графа (str|список) поверх
  `language_by_type` — смешанный репо (python-код + TS-доки при `type:node-package`) граф­ится верно
  без правки общих констант; swissknifeman → `python`. `render_project_yaml` рендерит и список
  (мульти-язык). +тесты.

### Added (harness — режим памяти `maind`)

- **Хук памяти получил режим `MODE=maind`** (`hooks/memory/modes/maind.sh`): делегирует
  `remember`/`recall` в `maind memory` (демон :4111 + изоляция по scope на стороне maind).
  brain игнорируется, scope берётся из проекта (`CLAUDE_PROJECT_DIR` → `match_cwd`). Чинит
  раскол «хук пишет в файлы `core`, MCP читает пустой scope демона»: теперь оба пути идут
  в один стор. Рекомендуется для прикладных проектов; глобальный дефолт пока `federation`.

### Changed (session-observer 0.3.0 — авто-включение логгера)

- **`/observe on` теперь полный чеклист**, который Claude выполняет автоматически:
  установка хука глобально → проводка пресета `observer` в проект → `ENABLED=true`
  → gitignore `.claude/observer/` → напоминание про рестарт сессии. Раньше скилл
  подразумевал только `ENABLED=true`, чего недостаточно для активации логгера.
  Добавлен `/observe off`.

### Docs (мультипровайдерная раздача — dev-план)

- **`skiller/docs/multi-provider-distribution.md`** — dev-план: увести раздачу
  локального `.ai/` контента (CLAUDE.md/AGENTS.md/Cursor) из Laravel Boost в skiller
  (Boost → только MCP). Фиксирует гэп (`vendor.py`/`skillset.py` резолвят реестр, не
  локальный `.ai/`), целевой дизайн и reference-пилот `sibintek-insiders`. Кросс-ссылки
  из `boost-compatibility.md` и `index.md`; пункт в сайдбаре VitePress.

### Added (Observer capture-слой — план agent-skill-binding, Stage D)

- **`harness` observer-хук** (PreToolUse/PostToolUse/Stop), ЭКСПЕРИМЕНТАЛЬНО,
  per-project (`.claude/observer.env.ini` → `ENABLED`, дефолт `false`): пишет
  компактный project-local `.claude/observer/runtime.jsonl` + алерт `LOOP`
  (3+ ошибки подряд), архивирует на `Stop`. **Никогда не блокирует** (наблюдатель,
  не гейт). Проводка — opt-in пресет `settings.observer.json` (`harness hooks
  --preset observer`), не глобально. Разбор — скилл `system/session-observer`.
- **`system/session-observer` 0.2.0** — добавлен `runtime.jsonl`/`archive` в
  источники данных + как включить capture-слой.

### Added (детерминированная привязка скиллов к агентам)

- **Поле `skills:` во frontmatter агентов бакетов** (`skills/<bucket>/agents/*.md`) —
  нативный preload Claude Code (v2.0.43+): полный контент перечисленных скиллов
  инжектится в субагента на старте, без надежды на model-invocation. Привязаны
  `php/laravel-implementer`, `laravel-reviewer`, `laravel-test-writer`. Закрывает
  корень сбоя «агент проигнорировал скилл» (6/7 пропустили `repositories`).
- **Валидация (`scripts/validate.sh`, 10c):** каждый `skills:`-элемент агента обязан
  резолвиться в реальный скилл реестра (`bucket:name`); ненеймспейснутый — warning.
- **`php/laravel-implementer`:** прозовый «ПЕРВЫЙ ШАГ — load via Skill» заменён на
  декларативное поле `skills:`; жёсткие правила оставлены L4-страховкой.

### Added (гейт принуждения + Observer — план agent-skill-binding, Stage B–D)

- **`harness` review-gate** — детерминированный гейт архитектуры на `SubagentStop`
  (`off|warn|strict`, дефолт `warn`): прогоняет настроенную проектом проверку
  (`check_command`), `warn` → подсказка в `additionalContext`, `strict` → блок
  субагента. Без проверки — no-op. L5-рубеж под `skills:`-preload. (Stage B)
- **`system/session-observer`** (skiller, ЭКСПЕРИМЕНТАЛЬНО, per-project toggle
  `.claude/observer.env.ini`) — пост-фактум разбор сессии по JSONL-логам с
  3-осевой аналитикой слабых мест: **агенты** (skill-skip/drift/циклы), **скиллы**
  (gap/thin/dead/correction-after-load), **настройки** (хуки/права). Находки →
  learnings через memory-хук, промоция человеком; замкнутый цикл самопочинки.
  Сниппет `analyze-session.md` (jq/grep-рецепты). Read-only по коду, не live. (Stage C–D)

### Changed (валидация: строгий frontmatter + битые ссылки)

- **`validate.sh` ужесточён** (секция 1a) — раньше проверялось только *наличие*
  обязательных полей; теперь:
  - `risk` ∈ {read, draft, write, external}; `adapters` ⊆ {claude, cursor, fable};
  - `version` — semver (`\d+.\d+.\d+`); frontmatter `bucket` == каталог бакета (для локальных);
  - объявленные в frontmatter `snippets:` обязаны существовать на диске;
  - **внутрискилловые ссылки** `snippets/…` / `references/…` в теле SKILL.md обязаны
    резолвиться (битая ссылка → error).
- Намеренно НЕ проверяем: равенство frontmatter `snippets:` ↔ `index.json` (принятая
  конвенция — index.json самодостаточен, frontmatter-список опционален; 34 скилла),
  и общие `../`/`.agents`-ссылки (раскладка проекта-потребителя у upstream/imported —
  ложные срабатывания). Все новые проверки дают 0 нарушений на текущем реестре.

### Changed (core: дедупликация + защищённый subprocess)

- **`parse_flags`/`parse_args` сведены в `core/cli.py`** — раньше `parse_flags`
  дублировался в skiller и harness байт-в-байт, `parse_args` (надмножество с
  позиционными) жил в maind. Теперь один источник истины, пакеты реэкспортируют из
  своих `common.py` (импорты `from .common import parse_flags|parse_args` не тронуты).
- **`core.cli.run_cmd`** — защищённый запуск подпроцесса (argv-список, без shell):
  `FileNotFoundError`/`TimeoutExpired`/ненулевой код → чистый `die` вместо
  трейсбэка. Применён к `registry`/`hub` (вызовы `generate-*.sh` с `check=True`
  больше не падают трейсбэком).
- **`core.io.safe_load_json`** — единый graceful-ридер JSON (битый/отсутствующий →
  default, опц. `on_error`). Для БД с бэкапом битого файла остаётся доменный
  `maind.common.load_json_db`.
- **Сплит `maind/common.py`**: HTTP-клиент (`http_get_json`/`http_post_json`/`ping`)
  → `maind/http.py`, управляемый markdown-блок (`managed_block`/`upsert_block`/
  `content_hash`) → `maind/blocks.py`. Реэкспорт из `common.py` — импорты
  `from .common import ...` не тронуты (non-breaking).
- Аудит subprocess-вызовов: остальные уже защищены (`shutil.which`-гварды,
  `try/except OSError`, health-poll демона памяти с детектом раннего выхода) —
  не трогали (рекомендация аудита про `shlex.quote` оказалась ложной: argv-списки
  не инъектируемы шеллом).
- **Тесты:** core 12→28 (parse_flags/parse_args/run_cmd/safe_load_json), harness
  14→28 (новое покрытие `doctor`/`settings`/`cli`-диспетчер).

### Added (скиллы дисциплины именования)

- **`general/naming-conventions`** (бакет `general` — CORE-connect, авто-раздаётся в каждый
  проект) — язык-агностичные правила: имя раскрывает намерение, борьба с шумовыми словами
  (`Manager`/`Helper`/`data`/`process`) и комбинаторным взрывом методов (`findByX…OrFail`/
  `…OrNull`). Сниппет `naming-gallery.md` (плохо → хорошо).
- **`php/naming-conventions`** (бакет `php`) — Laravel-конкретика: именование Action/Repository/
  DTO/VO/Enum/Event/Job, таблиц/колонок, разбор анти-паттерна `findByCodeOrFail`-взрыва
  (→ route binding / model scopes по намерению / критерий / один канонический `findByIdOrFail`).
  Сниппеты `naming-antipatterns.php`, `repository-method-naming.php`. Перекрёстные ссылки в
  `repositories`, `code-style-spatie`, `named-arguments`; уточнён чеклист `repositories`
  (единственный канонический lookup, не плодить метод-на-поле).
- Имя `naming-conventions` намеренно живёт в двух бакетах (`general` + `php`): legal под
  plugin-namespaces (connect), в vendor-режиме flat-имена разводятся префиксом бакета.

### Changed

- **Бакет `blender` разрезан на два плагина:** `blender` (универсальный bpy+MCP —
  `version-gotchas`, `mcp-blender`) и `blender-modeling` (параметрический CAD под
  FDM/SLA — `parametric-config`, `threading`, `model-rules`, `config-conventions`,
  `scene-conventions`, `build-loop`). Раньше один бакет смешивал универсальный
  Blender, методологию CAD и приватный workflow проекта DiaBox; диабокс-специфика
  (слой C) вырезана из плагина. Имена деталей в скиллах обезличены
  (`lens/glass/rocket → part/insert/model`). `blender-modeling` зависит от `blender`
  (`mcp-blender` от B не зависит); потребителям модельных скиллов подключать оба плагина.

### Added (agent-framework — каркас агент-практик + continuous-audit)

- **Документация каркаса агентов** (`docs/skiller/agent-framework/`): обзор,
  `framework-overview` (текущее состояние — вход аудита), `decisions-ledger`
  (принято/отклонено + проверенные факты Claude Code), `roles`,
  `skills-index-and-hub`, `post-integration-checklist`. Стойка: **данные + скилл,
  не движок-генератор**.
- **Переиспользуемый аудит-промт** `docs/skiller/workflows/framework-audit.md` —
  периодическая ревизия каркаса через Perplexity (вход: overview + ledger; выход:
  строгие дельта-таблицы); самоякорящаяся петля, не перепредлагает готовое.
- **Архив аудитов** `docs/skiller/audits/` (raw verbatim + триаж двух прогонов
  2026-06-23: universal-framework, agent-teams+ponytail) + ledger
  `references/framework-audits.md`. Sidebar обновлён (standalone + агрегат).

### Changed (hub — видимость агентов и скиллов, Фаза 1)

- **`generate-hub.sh`**: в хаб добавлен срез **«Агенты проекта»** (таблица из
  `.claude/agents/*.md`: роль → назначение → преднагруженные `skills:`) — роли и их
  скиллы теперь видны оркестратору. Каждое имя в `skills:` сверяется с реестром;
  неизвестное помечается `⚠` (preload молча no-op) + WARNING в stderr. Добавлен
  **freshness-штамп** `<!-- swissknifeman:registry sha=… skills=N -->` для сверки
  дрейфа «реестр изменился — хаб не перегенерён» (doctor — Фаза 5). Парс блок-списка
  `skills:` — инлайн в скрипте; общий хелпер в common.py придёт с валидатором (Фаза 3).

### Added (agent-packs — версионируемая pack-система, Фаза 2)

- **Скилл `system/agent-packs`** — playbook установки и версионного апгрейда паков в
  проект-потребитель: детект стека → интервью → рендер+копия → lock; upgrade по
  CHANGELOG-дельте с 3-way reasoning через sha256 в lock (без diff-движка). Стойка:
  агент-driven, не движок-генератор.
- **Пак `backend-laravel` v0.1.0** (`harness/configs/claude-code/agent-packs/`):
  агенты slice-builder/test-writer/reviewer + workflow dev-loop + review-gate хук +
  settings-фрагмент + guideline; обобщены плейсхолдерами (`{{PACK_PREFIX}}`,
  `{{PHP_RUNNER}}`, `{{TEST_RUNNER_CMD}}`, `{{TEST_DB}}`, `{{CHECK_CMD}}`,
  `{{PROJECT_DIR}}`). `pack.json` (manifest) + per-pack `CHANGELOG.md` + README паков.
- **Lock-схема** `.claude/agent-pack.lock.json` (версия + ответы интервью + per-file
  `base_sha256` отрендеренного) — основа upgrade без diff-движка.

### Added (Фаза 3 — роли, path-scoped rules, ponytail-дисциплина)

- **Роль `spec-writer`** (опц.) в паке `backend-laravel` — пишет `docs/specs/<feature>.md`
  (tech-spec) на крупные фичи, НЕ глобальный гейт. Path-scoped `rules/{api-controllers,
  migrations,tests}.md` — нативная авто-загрузка `.claude/rules/` по путям; тонкие
  триггеры, ссылаются на скиллы (без дублирования текста).
- **ponytail-дисциплина впитана в `quality/code-simplifier`** (0.2.0→0.3.0): лесенка
  YAGNI до кода (7 ступеней) + delete-list формат (теги `delete:`/`stdlib:`/`native:`/
  `yagni:`/`shrink:`). Внешний плагин ponytail НЕ подключаем (конфликт с boost).
  Reviewer-роль пака ссылается на over-engineering-проход.
- **`.swissknife.json` схема** (`CONFIG_KEYS`): `shape`/`stacks`/`skills_map` — данные
  профиля для универсальности back/front/fullstack (не движок).
- Сверка имён `skills:` у агентов уже покрыта hub-проверкой (Фаза 1) — отдельная
  команда `validate-agents` не понадобилась.

### Added (Фаза 5 — doctor freshness-дрейф)

- **`skiller doctor`** сверяет штамп `swissknifeman:registry sha=…` в хабе каждого
  зарегистрированного проекта с текущим sha реестра → флагит устаревшие хабы («реестр
  изменился — хаб не перегенерён»). Проекты без штампа (старый хаб) пропускаются.
  Замыкает continuous-audit петлю на детект дрейфа.

### Added (Фаза 6 — Agent Teams, опц.)

- **Пресет `settings.agent-teams.json`** (harness) — opt-in включение экспериментальных
  Agent Teams: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + `teammateMode` (merge-only,
  сосуществует с auto-approve/review-gate). Предпосылка: Claude Code ≥2.1.178; конфиг
  форвард-совместим.
- **Doc `agent-framework/agent-teams`** — когда брать Teams vs субагенты, spawn-шаблоны
  (full-stack фича, параллельный дебаг), module-boundaries (зоны путей под роли, БЕЗ
  file-lock), опц. quality-gate хуки `TeammateIdle`/`TaskCompleted` (переиспользуют
  review-gate). Роли каркаса годятся как teammates. Sidebar обновлён.

## [0.4.0] - 2026-06-22

> **Зонтичная единая версия монорепо.** Накопленное с `v0.3.0`: выделение пакета
> `harness` (окружение Claude Code), корневой управляющий слой `swissknifeman`,
> доки по пакетам + зонтичный агрегат, гранулярная оркестрация окружения и
> standalone-сборка доков пакетов. Тег `vX.Y.Z` — единый маркер всего репозитория;
> версии плагинов Claude Code резолвятся в git SHA и от тега не зависят, per-package
> `plugin.json` (harness 0.1.0 · maind 0.2.1 · skm 0.3.0) — информативны.

### Added (Фаза 3 — гранулярная оркестрация окружения)

- **Capability `env:mcp` / `env:hooks`** в `maind/orchestrate.py` рядом с `env:apply` —
  точечная раскатка MCP-серверов / хуков через пакет `harness` (`maind run <project>
  env:mcp|env:hooks`, router `swissknifeman env mcp|hooks` — полный passthrough в
  harness). Раньше окружение настраивалось только цельным шагом (`skiller integrate`
  или `env:apply` для permissions); теперь «зонтик = единое управление» покрывает и
  MCP/хуки гранулярно. Whitelist `CAPABILITIES` расширен, тесты orchestrate дополнены
  (sibling=harness, подкоманда, `{path}`-подстановка).

### Changed (Фаза 3 — standalone-сборка доков пакетов)

- **Доки skiller/harness собираются и standalone, и в агрегате** (как уже умеет
  maind). У каждого пакета — своя `docs/.vitepress/config.mts` (base `/skiller/`,
  `/harness/`); зонтичный `scripts/docs-sync.sh` по-прежнему отбрасывает per-package
  `.vitepress` и собирает единый сайт. Внутренние ссылки доков переведены на
  **относительные** (`./`, `../`, без `/skiller/`·`/harness/`-префикса) — один
  источник валиден в обеих сборках; кросс-пакетные ссылки skiller→harness/`/routing`
  резолвятся только в агрегате и в standalone помечены `ignoreDeadLinks`. `harness`
  получил `package.json` (docs-скрипты), skiller — `docs:standalone:*`. Проверено:
  агрегат + оба standalone-сайта собираются без dead links.

### Changed (docs: maind влит в единый сайт)

- **maind-доки вошли в зонтичный VitePress** — `scripts/docs-sync.sh` теперь
  агрегирует и `packages/maind/docs`; в меню «Память и граф» ведёт внутрь сайта
  (`/maind/…`), не наружу. Внутренние ссылки maind-доков переведены с абсолютных
  (база `/maind/`) на **относительные** — пакет собирается и standalone (свой
  `.vitepress`), и в агрегате (общая база `/swissknifeman/`). Единый сайт зелёный
  (`vitepress build`, без dead links); standalone-сборка maind тоже зелёная.

### Added (корневой управляющий слой `swissknifeman`)

- **`bin/swissknifeman`** — тонкий router + setup-фасад над тремя пакетами (зонтик =
  единое управление, пакеты = возможности): `swissknifeman skills|env|maind …` →
  skiller/harness/maind; `swissknifeman setup <project>` → `maind onboard` (полный
  онбординг: скиллы+окружение+память+граф); `swissknifeman doctor` → fan-out трёх.
  Логику не реализует — делегирует; цепочка онбординга одна (`maind/onboard.py`).
- **Back-compat алиаса**: исторические `swissknifeman <cmd>` (connect/vendor/integrate/
  update/sync/lock/status/list/registry/topology/validate/version) router проксирует в
  `skiller` — онбордженные проекты и привычка не ломаются.
- **Владение алиасом перешло зонтику**: `swissknifeman`→`bin/swissknifeman` ставит
  зонтичный `install.sh` ПОСЛЕ пакетов; из `packages/skiller/install.sh` установка
  алиаса убрана (иначе re-run skiller install затирал бы router). Standalone-skiller
  без зонтика — только `skiller` (алиаса нет).
- **maind**: capability `env:apply` (sibling `harness`) — прямое применение окружения
  (`maind run <p> env:apply`, router `swissknifeman env`); `onboard --skip-skills` теперь
  всё равно настраивает окружение через harness (раньше оно шло только внутри
  `skiller integrate`).

### Added (пакет `harness` — настройка окружения Claude Code)

- **Новый пакет `packages/harness`** (CLI `harness`): настройка харнеса Claude Code —
  пресеты permissions, режимы auto-approve/bypass, MCP-серверы, хуки (memory/notify/log).
  Выделен из `skiller`, потому что к управлению скиллами не относится. `git mv`
  `configs/claude-code/` и `scripts/apply-permissions.sh` из skiller → harness (история
  сохранена). Команды: `harness permissions|mcp|hooks|doctor`. Пакет stateless
  (пишет в `.claude/` целей и `~/.claude/hooks/`); зонтичный `install.sh` ставит
  `skiller · harness · maind`.
- **skiller делегирует окружение в harness через subprocess** (как maind → skiller):
  `apply_permissions` и env-блоки `integrate` (permissions/MCP/auto-approve/memory)
  зовут `harness …`; резолв лаунчера — `SKM_HARNESS_BIN` →
  `<монорепо>/packages/harness/bin/harness`. Сигнатура `apply_permissions` не менялась —
  `connect`/`vendor` не трогались; harness не установлен → graceful skip (как раньше при
  отсутствии скрипта). Политика выбора MCP (`_default_mcp`/dev-гейт) осталась в integrate.
- **marketplace: поле провенанса `package`** у каждой записи плагина (`skiller`/`harness`/
  `maind`) — `skiller registry` проставляет автоматически; harness подхватывается как
  соседний пакет (плагин `harness@swissknifeman`, только команды `/harness:*`). Имена
  плагинов и имя marketplace НЕ менялись (back-compat: `<plugin>@swissknifeman`).
- **PR-шаблон** переписан под монорепо (затронутые пакеты skiller/harness/maind/core,
  per-package validate, regenerate-marketplace, docs). Память хуков делит state со skiller
  (`~/.swissknifeman/`) — пути в установленных хуках не менялись.

### Changed (модель имён и топология MCP)

- **Пакет `packages/swissknifeman` → `packages/skiller`** (CLI `skiller`). Репо/зонтик остаётся
  `swissknifeman` (= контейнер-«швейцарский нож»); имя пакета теперь явно про управление СКИЛЛАМИ
  и не путается с репозиторием. `git mv` каталога + `lib/swissknifeman`→`lib/skiller` (импорты
  пакета относительные — менялись только absolute-импорты в `tests/`) + `bin/swissknifeman`→
  `bin/skiller` (`python3 -m skiller`). `install.sh` ставит `skiller` **и back-compat алиас
  `swissknifeman`** в PATH — доки/привычка/онбордженные проекты не ломаются. **НЕ менялись**
  (бренд зонтика): имя marketplace `swissknifeman`, state-каталог `~/.swissknifeman/`,
  `.swissknifeman-manifest.json`, `.swissknife.json`, репо-URL; `skm`-плагин и `/skm:*`.
  `orchestrate.py` (maind): путь sibling-лаунчера → `packages/skiller/bin/skiller`.
- **Плагин `maind` → только команды (`/maind:*`), без MCP-сервера.** Снято поле `mcpServers`
  из `plugin.json`, удалён `packages/maind/.mcp.json` (сервер `maind-hub --scope global`). Раньше
  user-global плагин тащил `maind-hub` в КАЖДУЮ сессию поверх per-project сервера `maind` — две
  одинаковые `maind`-строки в `/mcp` с разными scope (промах «пишем в global вместо project»).
  Теперь MCP-инструменты хаба даёт только per-project сервер `maind` из `.mcp.json` проекта;
  граф/`projects_*`/`links` scope-независимы, ecosystem-факт пишется явным `scope:"global"`.
- **maind MCP: дефолт-scope из cwd, а не глухой `global`.** При запуске без `--scope`/`MAIND_SCOPE`
  сервер определяет `project:<id>` по текущему каталогу (резолвер общий с `health --cwd`), падая
  в `global` только вне известного проекта — argless-сервер пишет в бакет своего проекта.
- **Дедуп включения плагина в `~/.claude/settings.json`** (user-config): снят дубль
  `maind@academici` (+ stale marketplace `academici`, указывавший на pre-monorepo standalone-клон);
  оставлен единый `maind@swissknifeman`.
- **Решение: maind остаётся единым** (память+граф связаны namespace-моделью; memory `agentmemory`
  и graphify уже отдельные MCP-серверы — дробить нечего). Зафиксировано в CLAUDE.md.

### Added

- **Аудит практик round-2 + 4 дельты реестра скиллов.** Продолжение
  `docs/research/practices-audit-2026-06.md` — новый док `practices-audit-2026-06-r2.md`
  (карта покрыто/частично/гэп/отклонено + бэклог, Dart отложен как 1 проект). Заавторены:
  - **NEW `php/enum-state-machine`** — граф переходов доменного статуса единым источником
    (`transitionDefinitions()` на enum) + рантайм-реестр (`allowedFrom`/`canTransition`) +
    исполнение перехода в Action под `DB::transaction()` с событием `ShouldDispatchAfterCommit`.
    Гэп: `enum-attributes` исключает state-machine, `ticket-workflow` проектно-специфичен.
  - **EXTEND `devops/ci-cd` 0.3.0 → 0.4.0** — coverage-gate отдельным CI-job (GitHub Actions
    + GitLab `.php-base`/`php-coverage`); парсер/конфиг переиспользованы из `php/laravel-testing`,
    не дублируются. Сниппет `github-actions-coverage-gate.yml`.
  - **EXTEND `quality/test-strategy` 0.1.0 → 0.2.0** — композиция именованных тест-сюитов
    (Arch/Unit/Feature/Context) + архитектурные тесты Pest Arch. Сниппеты `pest-arch-test.php`,
    `phpunit-testsuites.xml`.
  - **EXTEND `php/spatie-settings` 0.1.0 → 0.2.0** — паттерн «рантайм-инфраконфиг (websocket/
    Reverb) из админки → во фронт публичным DTO», граница секретов.

### Changed

- **Конфиг узла: `.maind.json` → `config.json` в корне монорепо (общий).** Конфиг переехал
  из пакета в корень монорепо и переименован (шаблон — `config.example.json`). Резолвер
  `Env.default_config` ищет `config.json` вверх по дереву (до каталога с `packages/`), с
  обратной совместимостью на legacy `.maind.json`. Добавлена лёгкая обёртка `Config`
  (подкласс dict: `Config.load(env)`/`.save(env)`/`.projects`/`.project(id)` — единая точка
  логики конфига; старый доступ `cfg["projects"]` сохранён). `config.json` — gitignored,
  `0600`. Резолв brain в оркестрации сделан консистентным с синком (через
  `integrations.brain.path` → vault → дефолт `~/Vaults/Brain`, нормализация к каталогу) —
  `maind run brain:*` работает без записи проекта brain. Документация и сообщения обновлены.

- **Плагин maind 0.2.0 → 0.2.1.** Bump версии, чтобы Claude Code перекэшировал плагин со
  свежим кодом (исправленный `.mcp.json` → `maind` из PATH, `from core`); кэш по прежней
  версии не перестраивался. `package.json` синхронизирован.

### Removed

- **Убрана консоль-обёртка `bin/academici`.** Зонтичный роутер `academici maind/skm <cmd>`
  удалён — остаются два независимых CLI в PATH (`swissknifeman`, `maind`). Зонтичный
  `install.sh` теперь только делегирует установку пакетным `install.sh`; CLAUDE.md/README
  описывают два CLI без обёртки. (Имя экосистемы «academici» как бренд сохранено.)

### Changed

- **Общий core: `academici_core` → пакет `core`.** Убрано слово `academici` из путей/имён.
  Каталог `core/` сам стал python-пакетом (`core/__init__.py`, `core/env.py`, …); импорт
  `from core import ...`. PYTHONPATH теперь указывает на корень монорепо (где лежит `core/`),
  а не на сам `core/` — обновлены лаунчеры, `test.sh`, `validate.sh` обоих пакетов и
  real-spawn тест maind (`CORE_DIR` → `MONOREPO_ROOT`).

### Fixed

- **Валидный формат `plugin.json` для установки из marketplace.** Текущий Claude Code
  ужесточил схему — старый формат не ставился (`commands: Invalid input,
  mcpServers: Invalid input`): `commands` теперь массив путей (`["./commands"]`),
  `mcpServers` — путь с `./` (`"./.mcp.json"`). Битый YAML-frontmatter команд (`description`
  с двоеточием `academici: …` парсился как вложенный ключ) обёрнут в кавычки. Затронуты оба
  командных плагина (maind, skm) — проходят `claude plugin validate`. Тест `test_plugin.py`
  ловит эти дефекты до установки.

### Changed

- **Монорепо academici: верификация + массовый re-deploy потребителей (этап 7).** MCP-конфиги
  проектов перенацелены на новый путь хаба: `maind deploy` прогнан по 15 проектам реестра —
  14 обновлены (corex/azguard/edufy/memster/vintera/… → `packages/swissknifeman/packages/maind/`),
  1 пропущен (agelto: предсуществующий битый `.cursor/mcp.json` с дублем JSON — не трогаем).
  `swissknifeman update --all` обновил скиллы потребителей. Проверка `maind health` на проекте:
  статус `connected`. Доделаны хвосты этапа 4: тест `test_plugin.py` и `validate.sh` maind
  больше не требуют собственный marketplace.json пакета (он в корне репо).

### Added

- **Монорепо academici: зонтичная навигация (этап 6).** Корневой `CLAUDE.md` (карта
  монорепо: пакеты, консоль, core, marketplace) и корневой `README.md` зонтика. README
  swissknifeman перенесён в `packages/swissknifeman/README.md`. `docs:*`-скрипты
  swissknifeman нацелены на корневой `docs/` (`../../docs`). docs/ пакетов и два VitePress
  оставлены на местах (полное слияние сайтов — отдельная задача).

- **Монорепо academici: единая консоль `bin/academici` + зонтичный `install.sh` (этап 5).**
  `academici` — тонкий bash-роутер: `academici maind <cmd>` / `academici skm <cmd>` →
  под-бинарник пакета; уникальные команды авто-роутятся без префикса; конфликтные имена
  (`status`/`doctor`) дают сводку по обоим пакетам, `sync` требует домен. Под-бинарники
  `maind`/`swissknifeman` остаются самостоятельными (не ломаем `.mcp.json` и мышечную память).
  Зонтичный `install.sh` ставит `academici` и делегирует установку пакетных CLI их
  собственным `install.sh` (с пакетной пост-настройкой). Все три симлинка указывают в монорепо.

### Changed

- **Монорепо academici: единый marketplace + плагин maind под зонтиком (этап 4).** Корневой
  `.claude-plugin/marketplace.json` теперь объявляет 19 плагинов — 18 swissknifeman
  (бакеты + generate-skill + skm) и `maind` (`source: ./packages/maind`). Генератор
  `registry.py` сканирует соседние пакеты `packages/<name>/.claude-plugin/plugin.json`
  (источник истины — их манифест) и добавляет их в marketplace; `validate.sh` учитывает
  sibling-плагины в match-проверке. Собственный `packages/maind/.claude-plugin/marketplace.json`
  удалён (его роль берёт корневой). Плагин maind (`commands/` + `.mcp.json` с
  `${CLAUDE_PLUGIN_ROOT}`) переносим без правок. Миграция кэша Claude Code
  (`maind@maind` → `maind@swissknifeman`) — вручную в панели `/plugin`.

- **Монорепо academici: общий `core/academici_core` (этап 3).** Дословные дубли,
  исторически копировавшиеся между swissknifeman/maind/brain байт-в-байт, вынесены в
  общий stdlib-only пакет: `die/warn/now_iso/confirm` (`term`), `sanitize` (`text`),
  базовый `BaseEnv` (ядро root/cmd/home + `__post_init__`, `env`). `Env` каждого пакета
  теперь наследует `BaseEnv` и добавляет только свои path-property. Подключение — через
  PYTHONPATH (без pip): лаунчеры, `test.sh`, `validate.sh` добавляют `<repo>/core`
  (опционально — fallback на standalone-раскладку). `parse_args`/`parse_flags`, atomic
  JSON, HTTP, frontmatter, managed-block остаются в `common.py` пакетов (расходятся по
  контракту — не дословны). 5 smoke-тестов core; 113 (skm) + 235 (maind) зелёные.

- **Монорепо academici: maind внесён в `packages/maind/` (через `git subtree`, история
  сохранена).** Хаб памяти/графа теперь живёт под зонтиком рядом с реестром скиллов.
  `node_modules` (демон `@agentmemory/agentmemory`) переустановлен в новом месте (`npm ci`);
  systemd unit `maind-memory.service` перегенерён на новый путь (`maind service install`),
  демон памяти жив (порты 4111/4112). `.maind.json` (конфиг узла, `0600`) перенесён в пакет.
  `orchestrate.py`: путь к лаунчеру swissknifeman обновлён на `packages/swissknifeman/bin/...`
  (local_path остаётся корнем репо). `maind doctor` и 235 тестов зелёные из нового места.
  Re-deploy `.mcp.json` потребителей (≈18 проектов держат старый абсолютный путь) — этап 7.
- **Монорепо academici: переезд в `packages/swissknifeman/`.** Репозиторий становится
  зонтиком экосистемы — содержимое реестра (`lib/`, `bin/`, `skills/`, `skm/`,
  `generate-skill/`, `scripts/`, `configs/`, `buckets.json` …) переехало в
  `packages/swissknifeman/`; в корне остаются зонтичные артефакты (`.claude-plugin/`,
  `docs/`, `README`, `LICENSE`, `CHANGELOG`). Один `marketplace.json` в корне репо теперь
  объявляет плагины с `source: ./packages/swissknifeman/...` (генератор `registry.py`
  разводит корень-пакета vs корень-репо через поиск `.git`; `validate.sh` и
  `generate-graph.sh` адаптированы). `bin/swissknifeman` больше не требует marketplace.json
  в корне пакета. Симлинк переустанавливается `install.sh` из нового пути. Готовит почву
  для пакета `packages/maind/` под тем же зонтиком.

- **Ревью внешнего аудита: дизамбигуация overlap-кластеров + CI security-гейты.**
  По разбору `Audit.md` (вердикт — `docs/research/audit-2026-06-review.md`): из
  всех рекомендаций реальны 3 (остальное — already-done/дубли/вне scope/против
  stdlib-only инварианта). `frontend/vue-composition-api` (0.2.0) обрезан до дельты
  (ref-first + composables), базовый синтаксис отдан upstream `vue`/`vue-best-practices`
  (не удалён — служит якорем «паттерн composable» для ≈13 frontend-скиллов).
  `php/laravel-permissions` (0.3.1) и `frontend/vitest` (0.1.1) — острые
  description-триггеры против путаницы роутинга (vs `azguard`/`attribute-authorization`
  и vs `vitest-vue`). `devops/ci-cd` (0.3.0) — секция «Security gates» (SAST/PHPStan-taint,
  `composer`/`npm audit`+Dependabot, Trivy скан образа) + сниппет `github-actions-security.yml`.
- **Анти-bloat в существующих скиллах (вместо новых дублей).** `anti-drift`
  (0.2.0) — секция «Граница зависимого пакета: спроси перед расширением» +
  обновлён сниппет CLAUDE.md; `code-simplifier` (0.2.0) — чеклист
  speculative-generality (YAGNI) по свежему диффу; `api-design` (0.1.1) —
  cross-ref на эволюцию контракта пакета; внутренний `skill-authoring` —
  стандарт ревью скилла (универсальность, без имён проектов/пакетов).
  `CLAUDE.md`/`CONTRIBUTING.md` — указатели на методологию и анти-bloat гейты.

### Fixed

- **auto-approve: ложные `deny_hard` на `git rm` и `*-init`** — общий токен `rm`
  ловил `git rm` (обратим, файлы в индексе/истории), а токен `init` — `git init`/
  `npm init`/`composer init`/`swissknifeman topology init`. Теперь `analyze.sh`
  маскирует `git rm` перед deny_hard-проверкой (голый `rm`/`xargs rm`/`rm -rf`
  по-прежнему блокируются; `git rm` идёт как мутация — промпт в strict/permissive,
  разрешён в bypass), а `init` убран из общего списка и заменён точечным паттерном
  рантлевела (`telinit`/`init [0-6sS]`). `git rm` добавлен в `deny_block_approve`.
  Файлы хука обновляются `apply-permissions.sh --global` (для `config.json` —
  перезалить вручную, т.к. он не перезатирается)

### Added

- **Каталог интеграций `docs/integrations/` + курированные MCP-пресеты.** По разбору
  внешнего аудита (`CLAUDE_INTEGRATION_TASK.md`): новый раздел VitePress «Интеграции» —
  индекс + 11 страниц (context7, playwright, filesystem, fetch, memory,
  sequential-thinking, github, task-master, spec-kit, claude-code-router), приведённых к
  реальности хаба (remote-HTTP context7, механизм пресет→`integrate`, актуальные пакеты:
  fetch — `uvx mcp-server-fetch`, github — remote `api.githubcopilot.com/mcp/`; без
  устаревших model-id и выдуманных схем). Курированный сабсет пресетов в
  `configs/claude-code/mcp/` (`playwright`/`filesystem`/`fetch`/`memory`/
  `sequential-thinking`/`github`) — **opt-in** через новый флаг `swissknifeman integrate
  --mcp <a,b>` (в интерактиве — отдельный вопрос); `DEV_MCP` по умолчанию не расширен.
  `claude-code-router` — страница «инструмент есть, но под сомнением». **Скиллы из аудита
  сознательно не созданы** (анти-bloat): `playwright-e2e-tester` дублирует
  `quality/playwright-e2e`, `git-flow-ru` — `git-commit-rules`+`github-flow`+`writing-style`,
  а `context7-dart-flutter`/`fintech-api-context`/`pos-fiscal-assistant` нарушают запрет на
  имена конкретных продуктов в теле скилла и попали бы в CORE-бакет `general` — их место в
  `.ai/skills/` конкретных проектов.
- **`integrate`: MCP-серверы в среды разработки (context7).** Новый блок визарда
  `_block_mcp` вливает пресеты MCP-серверов в `<project>/.mcp.json` (merge-only,
  чужие серверы целы, бэкап `*.bak`, `--dry-run`). Пресеты —
  `configs/claude-code/mcp/<name>.json`; первый — `context7` (remote HTTP
  `mcp.context7.com/mcp`, up-to-date docs библиотек). Гейт «среда разработки»:
  раздаётся во всё, кроме `obsidian-vault`. Бандлы `recommended`/`full` включают
  по умолчанию, `minimal` — нет, `custom` — спрашивает.
- **Семантика loop'ов поверх скиллов (без отдельного реестра `loops/`).** По
  аудиту [loops.elorm.xyz](https://loops.elorm.xyz/loops): страница
  `docs/guide/loop-semantics.md` (VitePress, в сайдбаре «Гайд») — модель loop'а
  (Goal/Run mode/Max iterations/Between-check/Exit condition + anti-gaming
  guardrails), маппинг фаз на существующие скиллы и граница «скилл даёт гейты,
  раннер встроен (`/loop`, `/schedule`)». Скилл `task-brief-template` (0.4.0):
  поля `Loop verifier`/`Exit condition`/`Hard stop trigger` в шаблоне + сниппет
  `loop-kickoff.md` (стартовый шаблон итеративной задачи для `.claude/commands/`).
  Сознательно без дублей: iteration/stop уже в `anti-drift`, session-split — в
  `context-economy`, shared-code gate — в `package-contribution-protocol`.
- **`swissknifeman sync` догнал `vendor`/`connect`: манифест, CORE-политика и
  индекс скиллов.** Раньше `sync` только копировал скиллы и писал
  `skills-lock.json` — без `.swissknifeman-manifest.json` (контракт переустановки
  и источник для `generate-hub.sh`), без CORE-скиллов и без обновления
  managed-блока в корне проекта. Теперь `sync`: (1) пишет манифест в `skills_path`
  (`layout: flat`, `flat_name`/`source_path`); (2) раздаёт `CORE_SKILLS` по
  умолчанию и применяет `DEFAULT_EXCLUDE` (флаг `--no-core` отключает), как
  остальные каналы; (3) обновляет индекс скиллов (managed-блок `CLAUDE.md` /
  `.ai/guidelines/swissknifeman-hub.md`), если он уже есть в проекте или передан
  `--hub` (`--no-hub` отключает). `generate-hub.sh` дополнительно ищет манифест в
  `skills_path` из конфига (находит нестандартные раскладки вроде `.agents/skills`).
- **Методология против раздувания кода + скилл `architect/package-contribution-protocol`.**
  По аудиту практик разработки экосистемы «проект ↔ зависимый пакет» добавлен
  generic-гейт против Speculative Generality: главный вопрос (Rule of Three +
  YAGNI), принцип «остановись и спроси / субагент go/no-go перед расширением
  пакета», двухступенчатый gate (proposal → ADR), таблица «что НЕ идёт в пакет»,
  направление зависимостей и SemVer контрактов. Сниппеты: `proposal-issue.md`,
  `adr-template.md`, `claude-md-priority.md` (ручной «первый приоритет» в
  CLAUDE.md потребителя), `permissions-deny.md`. Скилл **opt-in** (бакет
  `architect`), без имён конкретных проектов/пакетов. Базовый рефлекс «спроси
  перед расширением» — в CORE-скилле `anti-drift` (едет во все проекты);
  глубокий протокол подключается выборочно (гибридная раздача).
- **Permissions-пресет `product-boundary`** (`configs/claude-code/settings.product-boundary.json`):
  deny на запись в зависимый пакет (`Write/Edit(vendor/**)`); вариант для
  path-репо (`packages/**`) — в сниппете скилла. Opt-in (не в автодетекте),
  применяется через `apply-permissions.sh --preset product-boundary`.
- **Страница `docs/guide/methodology.md`** (VitePress, в сайдбаре «Гайд») —
  методология анти-bloat с картой «принцип → скилл/конфиг» и гибридной раздачей.
- **Figma MCP-скиллы + новый бакет `mobile`.** Три скилла прокачивают работу
  агента с подключённым Figma Dev Mode MCP: `architect/figma-mcp-core` —
  фреймворк-агностичная дисциплина (реальные инструменты `get_metadata`/
  `get_variable_defs`/`get_code`/`get_code_connect_map`/`get_screenshot`/
  `search_design_system`, запрет извлечения значений из скриншотов,
  selection-driven алгоритм, W3C `tokens.json`, аудит design-system);
  `frontend/figma-to-vue` — маппинг в Vue + Tailwind v4 (`@theme`, cva, `.dark`);
  `mobile/figma-to-flutter` — маппинг в Flutter (`ThemeData`, Row/Column/Expanded,
  Stack/Positioned). Новый бакет `mobile` (Flutter) в `buckets.json`.
- **Vendor-режим `swissknifeman sync` — физический перенос скиллов по единому
  конфигу.** `.swissknifeman/config.json` — источник истины (правила:
  `include` конкретных скиллов + `buckets` целиком − `exclude`); `sync`
  разворачивает их в плоский набор по `skills.json`, копирует файлы в
  `skills_path` (по умолчанию `.claude/skills`) и пишет производный
  `skills-lock.json` с пометкой `managed`. Безопасный prune: удаляются только
  `managed=true` записи, исчезнувшие из конфига — чужой/ручной вендоринг
  (наследие Boost, другой хаб) не трогается. Конфиг распознаётся как маркер
  корня проекта; пример — `.swissknifeman.example/config.json`; доки —
  `docs/guide/vendor-mode.md`. Read-only композитор `lock` остаётся для
  проектов без vendor-режима.
- **Management-плагин `skm@swissknifeman`** — командное лицо CLI: каталог
  `skm/` со статичным `plugin.json` + slash-команды (`skm`, `skills`,
  `integrate`, `status`, `doctor`). Не бакет скиллов — `registry` добавляет
  запись в `marketplace.json` синхронно, `validate.sh` проверяет как обычный
  плагин. Install `skm@swissknifeman` даёт команды управления скиллами проекта.
- **Реализация бэклога аудита — ещё 14 универсальных скиллов + 1 расширение
  (batch-2).** Добиты все отложенные §5 кандидаты из
  `docs/research/practices-audit-2026-06.md`; всё обобщено (проект — только
  эвиденс, в скилл идёт переносимый паттерн + анонимизированные снипеты).
  **Фронтенд (7):** `frontend/reka-ui-cva` (headless-примитивы Reka UI + cva),
  `frontend/dark-mode` (composable light/dark/system, без вспышки, SSR-cookie),
  `frontend/naive-ui-theming` (GlobalThemeOverrides), `frontend/laravel-echo-client`
  (Echo/Reverb composable, X-Socket-ID), `frontend/filepond-upload` (vue-filepond
  + rahulhaque/laravel-filepond), `frontend/vue-dynamic-icons` (динамическая иконка
  по имени), `frontend/pinia-stores` (setup-сторы, композиция). **PHP (4):**
  `php/livewire-blade-attributes` (дельта-гочизы к Boost livewire),
  `php/spatie-settings`, `php/health-checks` (spatie/laravel-health),
  `php/laravel-data` (spatie/laravel-data DTO + `#[TypeScript]`). **Quality (2):**
  `quality/playwright-e2e`, `quality/mutation-testing` (Infection). **Blender (1):**
  `blender/parametric-config` (config-dataclass → profile/check без bpy).
  **Расширен** `php/laravel-testing` (Pest-композиция: трейты + fake/freeze/dataset).
  `skills.json` 138 → 152; Boost-границы соблюдены (complementary: `laravel-data`,
  `spatie-settings`, `livewire-blade-attributes`); `boost-compatibility.md` обновлён;
  `validate.sh` зелёный (0 warnings, 76 tests).
- **Скиллы из практик констелляции (аудит + 10 скиллов, фокус — фронтенд).**
  Read-only аудит всех проектов из `~/Vaults/Brain/.projects.json` + `unbox`,
  `art-kombinat/frontend`, `sova` (6 Explore-агентов, сверка кандидатов с живым
  реестром, чтобы отсечь вендоренные копии). Разбор — в
  `docs/research/practices-audit-2026-06.md` (стек-фингерпринты, поправка
  vendored-vs-local, авторённое, отложенный бэклог, вне охвата). **7 новых
  скиллов:** `frontend/tailwind-conventions` (Tailwind v4: CSS-first `@theme`,
  токены, тёмная тема, `cn()`, prettier-plugin-tailwindcss), `frontend/backend-type-sync`
  (`spatie/laravel-typescript-transformer` + `#[TypeScript]` → `App.Enums.*`/`App.Data.*`,
  в паре с `wayfinder`), `frontend/eslint-flat-config` (ESLint 9 flat для Vue/TS:
  `@stylistic`, границы импортов, цепочка Prettier), `php/test-isolation-guard`
  (bootstrap-страж против тестов по боевой БД/медиа-диску), `php/attribute-authorization`
  (`#[CheckPermission]` + reflection-middleware поверх Gate), `general/writing-style`
  (тон/язык комментариев, коммитов, описаний тестов — расширенная версия, объединена
  с одноимённым скиллом из flexcrm-экстракции ниже), `devops/db-test-preflight`
  (пре-флайт Postgres-БД перед тестами — аналог `node-pnpm-preflight`). **3 расширены:**
  `frontend/inertia-vue` (доменные срезы `features/<домен>/` + границы импортов, →0.3.0),
  `php/enum-attributes` (секция `#[TypeScript]` + экспорт типов, →0.2.0),
  `php/modular-architecture` (реализация на `nwidart/laravel-modules` + Filament discovery, →0.3.0).
  Снипеты анонимизированы; `validate.sh` зелёный (0 warnings).
- **Экстракция универсальных скиллов из flexcrm** (источник: local, авторские):
  `quality/testing-safety-report` (отчёт безопасности после миграций/рефакторинга),
  `php/php-upgrade-checklist` (чеклист апгрейда версии PHP — образ/CI, composer,
  phpstan-baseline, rector, RFC), `general/writing-style` (живой язык комментариев
  и текстов коммитов, дополняет `git-commit-rules`). Boost-владения (tailwind/mcp/
  pest) и уже существующее в реестре не дублировались; `fortify-development` оставлен
  локальным в проекте по решению владельца
- **Док-предупреждение про чистую переустановку** (`docs/guide/cli.md`): `vendor`/
  `update` удаляют ранее вендоренные скиллы, выпавшие из набора реестра, включая
  **незакоммиченные** локальные копии — проектные скиллы держать в git; превью
  удаляемого — `--dry-run`. (Острый угол, всплывший при онбординге flexcrm)
- **Визард интеграции `swissknifeman integrate`** (`lib/swissknifeman/integrate.py`)
  + [чеклист](docs/guide/integration-checklist.md) — единая точка входа: проходит
  чеклист «выбери, что хочешь из максимального функционала» и применяет выбранное,
  переиспользуя `do_connect`/`do_vendor` (скиллы), `apply-permissions.sh` (permissions),
  `generate_hub` (hub) + пишет per-project hook-JSON (auto-approve на PreToolUse
  Bash/ExitPlanMode) и `.swissknife.json:memory_brain` (членство в memory-brain).
  Бандлы `minimal|recommended|full|custom`; безопасно — `--dry-run`, merge-only с
  бэкапами `*.bak`, идемпотентно, пререквизиты (`topology init`, `--global`) только
  с подтверждением. Зарегистрирован в `cli.py`/лаунчере; тесты `tests/test_integrate.py`.
  В `CONFIG_KEYS` добавлены `memory_brain`/`coordinator_ignore` (валидны в `.swissknife.json`)

- **Гибкая «единая память» констелляции** — самодостаточная папка-хук
  `configs/claude-code/hooks/memory/` по образцу auto-approve: переключатель
  `memory.sh` (remember/recall/members/status/sync), режим в `env.ini`
  (`MODE=file|federation|agentmemory|off`), группы и участники в `config.json`,
  бэкенды в `modes/`. **Membership:** общий «мозг» (brain) видят только участники
  из его `members` (резолв узлов/проектов через топологию). Режимы взаимозаменяемы
  (file/federation на markdown без демона; agentmemory — прокси к стороннему
  демону на Brain, деградирует при недоступности), конфиг переопределяется
  per-project (`<project>/.claude/memory.{env.ini,config.json}` + `.swissknife.json:
  memory_brain`). Схема факта совместима с нативной памятью Claude Code, поэтому
  `federation` читает и `~/.claude/projects/<slug>/memory/` участников. Агент-обвязка —
  скилл `system/shared-memory`; установка через `apply-permissions.sh --global`.
  `validate.sh` теперь `bash -n`-ит все хук-скрипты `configs/claude-code/hooks/`
- **Межпроектный координатор кода** — `system/cross-project-coordinator` (скилл) +
  агент `system/agents/code-coordinator` (read-only). Поверх топологии обходит
  связанные проекты, перечисляя только git-отслеживаемые файлы (`git ls-files` —
  уважает `.gitignore`/`.git/info/exclude`, секреты и вендор/генерёжку не читает),
  и ищет по семи критериям: дубли между репо, расходящиеся реализации одного
  концепта, дрейф от реестра скиллов, копия-вместо-зависимости, расхождение
  конвенций/документации/зависимостей. Критерии переиспользуют `quality/`-скиллы
  (tech-debt-audit, refactoring-plan, code-simplifier, code-review). Выдаёт
  приоритизированный (impact×effort) отчёт с `file:line` по проектам и named
  extraction target; правок/PR не делает. `requires: local-topology`
- **Топология локальной среды** — корневой узел системы. Новый бакет `system`
  со скиллом `local-topology` (раздаётся всем проектам: добавлен в профили
  laravel-project/php-package/obsidian-vault), команда `swissknifeman topology
  [init|show]` (`lib/swissknifeman/topology.py`) и глобальный конфиг
  `~/.swissknifeman/topology.json` (version 1): три узла-хаба
  Brain-волт/swissknifeman/база-проектов (роли docs-hub/skills-hub/workspace).
  `init` — интерактивный сбор с авто-детектом дефолтов, атомарная запись с
  бэкапом `.bak`, сохранение `created_at`; предлагается при `install.sh` (TTY).
  Скилл объясняет схему и резолвит узлы по конфигу — любой агент в любом проекте
  видит, где лежат узлы, и доходит до кода/документации соседних проектов.
  Тесты `tests/test_topology.py` (+10). Roadmap: межпроектный агент-оптимизатор
- **Notification-hook `configs/claude-code/hooks/notify/notify.sh`** — ОС-уведомление,
  когда Claude Code ждёт человека: запрос разрешения на инструмент, утверждение
  плана (ExitPlanMode) или простой промпта дольше ~60 сек. Кросс-платформенно
  (Linux `notify-send`, macOS `terminal-notifier`/`osascript`, WSL/Windows toast).
  Регистрируется пресетом `global`, ставится через `apply-permissions.sh --global`,
  никогда не блокирует (`exit 0`)

### Added (продуктовая готовность)

- **`LICENSE` (MIT)** + поле `license` в `package.json` — юридическая основа для
  распространения; внешние (imported) скиллы сохраняют лицензии источников
  (`upstream.json`)
- **`SECURITY.md`** — порядок раскрытия уязвимостей, модель доверия импортируемых
  скиллов (sha256 в `upstream.json`, стратегии `notify`/`replace`), правило
  «нет секретов в snippets», приоритет «проект > источник > реестр»
- **`.github/workflows/test.yml`** — отдельный CI с матрицей Python 3.9–3.12
  (раньше тесты гонялись только хвостом `validate.sh` на одной версии)
- **Покрытие ядра CLI тестами** (38 → 57): `registry` (`build_registry`,
  `write_plugin_manifests`, provenance внешних скиллов, die без `buckets.json`),
  `state` (CRUD `projects.json`, сохранение `first_connected_at`, атомарность),
  `doctor`, `status`, `update` (реплей выбора, идемпотентность) — теперь у каждой
  команды есть прямой тест; хелпер `write_upstream` в `tests/fixtures.py`
- **`docs/guide/troubleshooting.md`** — диагностика (`command not found`, Claude
  Code не видит скиллы, конфликт `settings.json`, коллизии вендоринга, битый
  `projects.json`) и обновление (реестр, vendor `update`/`--all`, смена схемы);
  добавлена в sidebar
- **Бейджи в README** (Tests / Validate / Docs / License) + разделы
  «Безопасность» и «Лицензия»

### Changed (рефакторинг CLI: lib/ + тесты)

- **`bin/swissknifeman` → тонкий лаунчер**: вся Python-логика (раньше — heredoc
  на 1300 строк внутри bash) вынесена в пакет `lib/swissknifeman/` и разложена
  по модулям (`common`, `config`, `state`, `connect`, `vendor`, `update`,
  `status`, `listing`, `registry`, `doctor`, `boost`, `hub`, `cli`). Бинарник
  делает preflight-проверки и `exec python3 -m swissknifeman <root> <cmd>`.
  Поведение байт-в-байт прежнее (`registry` даёт идентичные `skills.json` и
  манифесты); установщик и симлинк не затронуты. Модульные глобали
  `root`/`cmd`/`argv` заменены явным `Env` — функции стали импортируемыми

### Added (тесты CLI)

- **`tests/` (stdlib unittest, без зависимостей)**: 27 юнит-тестов
  (frontmatter, парсинг флагов, sanitize, autodetect, precedence
  `resolve_selection`, транзитивный `requires`, коллизии flat-имён) и
  11 интеграционных — фейковый Laravel-проект в tmpdir, кейсы `connect`/`vendor`
  (autodetect, явные плагины, сохранение `false`, dry-run, bucket/flat-layout,
  pull `requires`, `--exclude`, синк `boost.json`, чистая переустановка).
  Синтетический реестр (`tests/fixtures.py`) — тесты не зависят от контента
  скиллов
- **`scripts/test.sh`** — раннер тестов (`-v` для подробного вывода), встроен в
  `scripts/validate.sh` (группа 12: импорт пакета + прогон сьюта). Тот же
  скрипт гоняет CI

### Added (gh-driven ревью и экономия контекста)

- **`oss-dev/gh-review` (0.1.0)**: ревью и хендофф изменений через GitHub CLI
  с экономией контекста — `gh pr diff/view/comment/review` отдают точечный срез
  (дифф, треды), `gh api .../contents` тянет один файл вместо загрузки целиком.
  Чёткая граница: локальный VCS (commit/branch/diff/log/rebase) — за `git`,
  платформа (PR/issue/release/api) — за `gh`. `requires: context-economy`,
  `produces_for: github-flow`; snippet-шпаргалка команд
- **`scripts/update-upstreams.sh` — канал `gh api`**: для GitHub raw-URL и при
  наличии `gh` файл тянется через `gh api repos/{o}/{r}/contents/{path}?ref=...`
  (авто-аутентификация из `gh auth`, rate-limit, один файл). Тихий откат на
  `urllib`+`GITHUB_TOKEN`, если `gh` недоступен; отключение — `UPSTREAM_NO_GH=1`.
  Касается импортируемых скиллов (`source: github`)

### Changed

- **`general/context-economy` 1.0.0 → 1.1.0**: раздел «Платформенный слой —
  через `gh`, не файлами» (`gh` дополняет `git`, не заменяет; экономия на
  точечном срезе) + пункт чеклиста; ссылка на `oss-dev/gh-review`
- **`oss-dev/github-flow` 0.1.0 → 0.2.0**: шаг Review ссылается на `gh-review`
  (`requires += gh-review`); ревью PR — через `gh`, не загрузкой файлов
- **Документация**: этап «dev-review через gh» в межсистемной цепочке
  (`docs/workflows/index.md`), канал `gh api → urllib` в
  `docs/guide/upstream-sync.md`

### Added (интеграция с Laravel Boost — совместимое ядро)

- **`php/named-arguments` (0.1.0)**: правило обязательных именованных аргументов
  в PHP-вызовах с границами применения и исключениями (один аргумент, встроенные
  функции, splat). Извлечено и де-агельтизировано из проектного скилла;
  `source: local`. Дополняет, а не дублирует — реестр раньше только *использовал*
  именованные аргументы в примерах, отдельного правила не было
- **`php/pennant-development` (0.1.0)**: feature-флаги Laravel Pennant
  (`define`/`active`/`for`-scope, директива `@feature`, активация/раскатки).
  Извлечено из `laravel/boost` (`upstream.json` strategy=notify) — единственный
  чистый static-`.md` generic-кандидат без версионной развилки; Blade-скиллы
  Boost (`folio`/`volt`/`mcp`) остаются за Boost (нужен render-контекст)
- **`php/laravel` → `eloquent-model.md`**: секция «Accessors и mutators» дополнена
  правилами `Attribute::make()` (видимость `protected`, camelCase→snake_case,
  позиция в классе, миграция с legacy-аксессоров) — слито из проектного
  `laravel-attributes` вместо создания дубля

### Added (CLI и хаб — установка в Boost-проекты)

- **Boost-aware `vendor`/`update`**: при наличии `boost.json` в целевом проекте
  CLI (1) автоматически использует **flat-раскладку** `.ai/skills/<name>/SKILL.md`
  — Boost обнаруживает user-скиллы через `glob('.ai/skills/*')` на один уровень,
  bucket-подпапки он бы не нашёл; (2) идемпотентно дозаписывает вендоренные
  скиллы в `boost.json::skills` (по frontmatter-`name`) и подсказывает
  `php artisan boost:update`. Скиллы автоматически расходятся по всем агентам
  Boost из единого источника `.ai/skills/`
- **`generate-hub.sh --root-files A,B`**: managed-блок хаба (между маркерами
  `swissknifeman:hub:start/end`) дополнительно пишется в указанные корневые файлы
  (`AGENTS.md`, `GEMINI.md`, …) для тулз вне Boost; контент вне маркеров не
  трогается

### Fixed

- **Рассинхрон маркера хаба**: `bin/swissknifeman` искал
  `<!-- swissknifeman:hub:begin -->`, тогда как `generate-hub.sh` пишет
  `:start`/`:end`. Из-за этого `hub_artifacts_exist()` не находил managed-блок в
  `CLAUDE.md`, и `update`/повторный `connect` не понимали, что хаб уже стоит.
  Приведено к единому `hub:start`

### Changed (документация концепции ядра)

- **Политика совместимого ядра** зафиксирована явно: `docs/guide/index.md`
  (принцип №6 «Совместимое ядро» + таблица прецедентов), `README.md`,
  `references/laravel-boost.md` (критерий извлечения static/версионность/generic,
  что извлечено, что нет и почему), `docs/guide/installation.md` (раздел
  «Проект с Laravel Boost»). Поток обновлений инвертирован: generic-скиллы
  внешнего источника обновляются сначала в реестре, затем подтягиваются в проекты

### Added (субагенты Laravel)

- **`php/agents/` — первые агент-определения в плагине**: бакет-плагин теперь
  несёт каталог `agents/` (Claude Code обнаруживает его в корне плагина
  автоматически; реестр и валидатор каталоги без SKILL.md игнорируют;
  доступно только в plugin-канале — `vendor` агентов не копирует).
  Агенты: `laravel-reviewer` (read-only ревью свежим контекстом:
  PHPStan/Pint/целевые Pest, Laravel-критерии, структурированные находки без
  правок) и `laravel-test-writer` (Pest-тесты по готовому коду в стиле
  существующих тестов проекта; прикладной код не меняет — расхождения
  репортит)
- **`php/laravel-subagents` (0.1.0)**: протокол оркестрации субагентов на
  крупных Laravel-задачах — порог срабатывания (≥3 слоёв/доменов или целая
  фича; мелкое/среднее — напрямую, явный анти-триггер), исследование через
  Explore-агентов, архитектурный код пишет оркестратор, параллель только для
  независимых подзадач (иначе worktree), `laravel-reviewer` после каждой
  единицы, `laravel-test-writer` по готовому коду, анти-паттерны конвейера
  ролевых агентов

### Added (github-flow)

- **`oss-dev/github-flow` (0.1.0)**: процессная цепочка Issue → Branch → PR →
  Merge → Tag → Release на GitHub — naming Issue/веток/PR, labels, SemVer-оракул
  по типам коммитов, контрольные точки с обязательными вопросами агента;
  PHP/Packagist-гейт в `references/php-package-gate.md`; snippets с шаблонами
  PR/Issue; `requires: git-commit-rules, release-engineering` (формат коммитов
  и changelog/pipeline не дублируются)

### Changed (github-flow)

- **`general/git-commit-rules` 0.1.0 → 0.2.0**: расширен список типов
  (`perf`, `style`, `build`, `ci`, `revert`), раздел «Conventional Commits:
  scopes и breaking changes» (источник scope — commitlint, footer
  `BREAKING CHANGE` / `!` после типа), ссылка на SemVer-оракул github-flow

### Added (CLI swissknifeman + внутренние скиллы)

- **CLI `bin/swissknifeman`**: единая точка входа — `connect` (marketplace
  Claude Code), `vendor` (вендоринг), `update [--all]` (детект каналов по
  маркерам диска, adopt незарегистрированных проектов, починка path-drift
  marketplace при переезде реестра), `status`, `list [--prune]`, `registry`
  (бывший `sync.sh --update-registry`), `validate`, `doctor`, `version`.
  Корень проекта ищется вверх от CWD (`.swissknife.json` → `.claude/` →
  `.git`) — флаг `--target` больше не нужен
- **Карта проектов `~/.swissknifeman/projects.json`** (schema v1, ключ
  path+channel): пополняется автоматически при connect/vendor/update; явный
  выбор (`--profile`/`--plugins`/`--buckets`) воспроизводится при `update`,
  автодетект пере-резолвится с диска; атомарная запись, самовосстановление
  adopt-ом после потери файла
- **Внутренние скиллы `.claude/skills/`** (не экспортируются): полная карта
  пакета (`package-architecture`), процедура авторинга скиллов с проверкой
  пересечений и обязательным upstream.json для внешних (`skill-authoring`),
  дисциплина завершения изменений (`release-discipline`), решение об
  обновлении docs/ после задач (`docs-maintenance`)
- **validate.sh секции 10–11**: мягкий линт внутренних скиллов
  (name+description, kebab-case == каталог, warning при коллизии с реестром);
  `bash -n` всех скриптов + исполняемость CLI
- **`docs/guide/cli.md`**: справочник команд CLI, схема projects.json,
  поиск корня проекта, troubleshooting

### Changed (CLI swissknifeman)

- **`install.sh` перепрофилирован в установщик CLI** (симлинк
  `~/.local/bin/swissknifeman` → `bin/swissknifeman`, идемпотентен,
  PATH-подсказка под шелл); **breaking**: legacy-вендоринг
  `./install.sh <dir> <bucket>` удалён — `swissknifeman vendor`
- `scripts/connect-claude.sh` и `./sync.sh --update-registry` —
  deprecation-wrapper'ы на один релиз, переадресуют в CLI
- `docs/guide/installation.md` переписан под двухшаговую установку
  (CLI один раз → `connect`/`vendor` из проекта); README и остальные
  страницы docs переведены на команды CLI

### Removed (CLI swissknifeman)

- **Brain-sync** (`sync_to_brain`, `BRAIN_PATH`, workflow
  `.github/workflows/sync-to-brain.yml`): зеркалирования в brain больше нет —
  brain подключается как обычный проект
  (`cd <brain> && swissknifeman vendor`, дальше `swissknifeman update`)

### Added (improvement report v2: граф зависимостей + методология)

- **Dependency resolution в install.sh**: frontmatter `requires` разрешается
  транзитивно при выборочной установке (`--buckets`/`--exclude`), в том числе
  кросс-бакетно; `--exclude` побеждает зависимость с предупреждением; дотянутые
  скиллы помечаются в `--list`/`--dry-run` как `(dependency of <skill>)`
- **Валидация графа в validate.sh** (секция 9): существование имён в
  `requires`/`produces_for`, self-reference, циклы по `requires` (DFS);
  warning на не-inline списки
- **`scripts/generate-graph.sh`**: Mermaid-граф зависимостей →
  `docs/guide/graph.md` (subgraph на бакет, только связные узлы, изолированные —
  таблицей); вызывается из `sync.sh --update-registry`; в VitePress подключён
  `vitepress-plugin-mermaid`
- **Реестр skills.json v5**: поля `tags`, `requires`, `produces_for`
  в записях скиллов (опциональны, опускаются если пусты)
- **`general/anti-drift` (0.1.0)**: методология Karpathy (think-before-coding,
  simplicity-first, surgical-changes, goal-driven) + circuit-breaker пороги;
  сниппет-блок для CLAUDE.md целевого проекта
- **`general/spec-interview` (0.1.0)**: grill-me-style интервью перед кодом —
  вопросы по одному, агент сам читает кодовую базу, рекомендованный ответ
  к каждому вопросу; итог — заполненный task-brief-template
- **`general/session-handoff` (0.1.0)**: протокол передачи контекста между
  сессиями/агентами; сниппет handoff-template.md
- **`quality/code-simplifier` (0.1.0)**: упрощение свежего диффа без изменения
  поведения; сниппет GitHub Actions `simplify-on-push.yml`
- **`php/laravel-security-audit` (0.1.0)**: sharp-edges-аудит Laravel
  (raw-запросы, mass assignment, XSS в Blade, CSRF/redirect,
  сериализация/авторизация) с references/ по каждой грани; сниппет
  GitHub Actions `security-audit-scheduled.yml`; requires: static-analysis
- **`docs/workflows/background-agents.md`**: фоновые агенты в CI — шаблоны,
  требования, ограничение стоимости, анти-дрифт правила

### Changed (improvement report v2)

- `general/task-brief-template` 0.2.0 → 0.3.0: секции «Явные предположения»,
  «Out of Scope», «Definition of Done» в шаблоне ТЗ
- `oss-dev/dependency-audit` 0.1.0 → 0.2.0: `references/composer.md` —
  composer-специфика аудита (composer audit/outdated/licenses,
  roave/security-advisories, reproducible installs, composer-грабли, SBOM)
- `php/filament`: `produces_for: [backend-dev, fullstack-dev]` → `[]` — таких
  скиллов не существует (поймано новой валидацией графа)
- `docs/boost-compatibility.md`: ссылка на карточку laravel-boost ведёт на
  GitHub (относительный путь вне docs-корня ломал сборку VitePress)

### Rejected (improvement report v2, по итогам анализа)

- `registry.json` — уже существует как `skills.json` (богаче: sha256,
  provenance, upstream)
- Tier-система (0–4) во фронтматтере — дублирует ось бакеты+профили+requires
- `caveman`-скилл — покрыт `general/compact-responses`
- `composer-audit` как отдельный скилл — расширение `dependency-audit`
- Фоновые workflow в самом реестре — только шаблоны для целевых проектов

### Added (token optimization wave)

- **`php/pao` (1.0.0)**: скилл по laravel/pao — агентно-оптимизированный вывод
  PHPUnit/Pest/PHPStan/Rector/Artisan (~20 токенов JSON вместо тысяч);
  установка, проверка, ограничения
- **`general/context-economy` (1.0.0)**: экономия контекста Claude Code —
  CLAUDE.md ≤200 строк, path-scoped `.claude/rules/` с `paths:`, /compact vs
  /clear, Plan→Clear→Execute, аудит MCP, нативная маршрутизация моделей;
  сниппеты: шаблон правила, команды /prime //plan //execute, чеклист аудита
  CLAUDE.md
- deny-блок «токен-шума» в пресетах `configs/claude-code/settings.laravel.json`
  и `settings.node.json` (`storage/logs`, `node_modules`, `*.lock`, кэши,
  бандлы); `vendor/` сознательно не блокируется — там Boost-гайдлайны

### Changed

- **`php/filament` 0.2.0 → 1.0.0**: переписан с v3 на Filament v5 — структура
  v5-генератора (Schemas/ + Tables/), таблица корректных namespaces
  (`Filament\Actions\*`, `Filament\Schemas\Components\*`), CLI-справочник
  `make:filament-*`, union-типы свойств, типичные ошибки из официальных
  Boost-гайдлайнов; snippets обновлены под v5 + новый
  `forms-tables-reference.md`; upstream.json отслеживает
  filamentphp/filament `boost/guidelines/core.blade.php` (strategy=notify)
- `general/compact-responses` 0.1.0 → 0.2.0: поведенческие шаблоны цикла
  разработки (`✓ tests passed (N)`, только упавший тест при ошибке) и формат
  единственного развёрнутого финального отчёта
- `general/task-brief-template`: раздел Plan→Clear→Execute (план и выполнение —
  раздельные сессии)

### Rejected (по итогам фактчека отчётов Perplexity)

- `.claudeignore` — не существует в Claude Code (рабочий механизм —
  `permissions.deny: Read(...)`)
- `paths:` frontmatter для SKILL.md — `paths:` работает только в
  `.claude/rules/`; скиллы и так загружаются лениво
- claude-code-router — сторонний прокси; нативный `/model` достаточен
- waaseyaa/agent-output как стандарт — перекрывается laravel/pao
- `deny Read(vendor/**)` — ломает чтение Boost-гайдлайнов

## [0.3.0] - 2026-06-11

### Added

- **Нативный plugin marketplace Claude Code**: `.claude-plugin/marketplace.json`
  + `plugin.json` на каждый bucket (генерируются `sync.sh --update-registry`,
  метаданные в `buckets.json`); плагин = bucket, скиллы с неймспейсом
  `<bucket>:<skill>`, версия плагина = git SHA
- **`scripts/connect-claude.sh`**: подключение проекта к marketplace —
  автодетект профиля, идемпотентный merge `extraKnownMarketplaces` +
  `enabledPlugins` в `.claude/settings.local.json`, `--dry-run`/`--list`,
  миграция со старого вендоринга (`--cleanup-vendored` удаляет только
  манифестные копии)
- **`buckets.json`**: description/category/tags на bucket; описания попадают
  в plugin-манифесты и skills.json (registry v4)
- **Схема-валидация `.swissknife.json`** в install.sh и connect-claude.sh:
  неизвестный ключ/тип → ошибка с подсказкой (`did you mean 'buckets'?`)
- **Манифест и коллизии в bucket-режиме install.sh**: `.swissknifeman-manifest.json`
  теперь пишется и в generic/cursor-режиме (чистая переустановка), существующие
  чужие папки — ошибка-коллизия, перезапись только с `--force`
- validate.sh: проверки buckets.json, свежести plugin-манифестов,
  уникальности имён скиллов

### Changed

- `generate-skill/` реструктурирован в layout плагина
  (`generate-skill/generate-skill/SKILL.md`)
- `--agent claude` в install.sh — deprecated (предпочтителен marketplace);
  `.claude-plugin/` исключён из вендоринга и brain-sync
- Документация: адаптер Claude Code переписан вокруг marketplace,
  гайд установки разделён на каналы Claude Code / Cursor-generic
- Ссылки на `references/` в `oss-dev/oss-development` исправлены на
  относительные к скиллу (`../references/...`)

### Added (docs & configs wave)

- **Документация на VitePress** (`docs/`): гайд (принципы, установка, профили,
  анатомия скилла, upstream-sync, реестр, сканер, CI), конфиги, адаптеры,
  примеры, roadmap; деплой на GitHub Pages (`docs.yml`)
- **Пресеты permissions для Claude Code** (`configs/claude-code/`):
  base/laravel/php-package/node/python/docker/yolo +
  `scripts/apply-permissions.sh` (merge в settings.local.json, автодетект стека,
  dry-run, бэкап)
- **Vendor-skills**: универсальный механизм публикации скиллов из Composer-пакета
  потребителю через `vendor:publish` — док-страница + переработанный скилл
  `php/laravel-packages` (v0.3.0) со сниппетом `boost-skill-publisher.php`
- **Спецификация адаптерных дельт**: формат `Override:`/`Additional:`,
  pre-flight хуки, критерии «когда дельта нужна»
- Критерии качества сниппетов для сканера (порог 60/100) в документации
- Roadmap: ближайшие фазы + стратегические/технические/экспериментальные идеи
  (перенесено из tmp-черновиков master-plan v3, черновики удалены)

## [0.2.0] - 2026-06-11

### Added

- **Upstream-sync система**: per-skill `upstream.json` (source, strategy replace/notify,
  sha256, fetched_at), `scripts/update-upstreams.sh` (--check/--apply/--force, exit-коды
  для CI), еженедельный workflow `upstream-sync.yml` с PR-ревью
- `upstream.json` + baseline для всех 12 `skills/imported/*` (get-zeked super-skills)
- **Контекстная установка**: `install.sh` v2 — автодетект типа проекта, `profiles/*.json`
  (obsidian-vault, laravel-project, php-package, standalone), `.swissknife.json` override,
  `--agent claude` с плоской раскладкой под `.claude/skills/` и manifest-cleanup
- **`references/`** — каталог 15 внешних источников с принципом выборочного отбора
- `scripts/validate.sh` — единая валидация (frontmatter, upstream.json, profiles,
  реестр, snippet-манифесты) локально и в CI
- Provenance в `skills.json`: `source: local|github|http`, `upstream`, `fetched_at`
- `.swissknife.example.json`

### Fixed

- `validate.yml`: glob `skills/**` не работал в bash без globstar — CI фактически
  не валидировал скиллы
- `sync.sh`: name/description парсились по всему файлу, а не только из frontmatter
- `skills/pm/prd-from-brd`: отсутствовало поле `version` во frontmatter

## [0.1.0] - 2026-06-11

### Added

- Skills registry v3 with 65 skills across 10 buckets
- Migration of 36 skills from `academici/brain`
- New buckets: devops, php, roles, imported
- 12 perplexity super-skills in `skills/imported/`
- PHP skills: laravel, laravel-permissions (with AzGuard patterns), laravel-testing, laravel-packages, php-patterns, botkit, filament
- DevOps skills: docker (php, vite, postgres, dev-prod), ci-cd, gitops
- Roles: startup-cto, tech-lead, open-source-maintainer, solo-founder
- `install.sh`, `sync.sh`, scanner pipeline
- CI: validate, sha256-update, sync-to-brain, scanner-pr
- Adapters: cursor, claude-code, perplexity
- `generate-skill/` meta-skill
