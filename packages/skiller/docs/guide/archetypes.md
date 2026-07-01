# Архетипы проектов: рецепты и неочевидные развилки

Карта типовых проектов экосистемы: что детектится, какой набор раздаётся (`profiles/<type>.json`)
и какие **неочевидные вопросы** решаются при онбординге. Цель — чтобы агент, получив проект, не
гадал «что подключить». Полное дерево настройки — [onboarding-decision-tree](/maind/guide/onboarding-decision-tree);
выбор канала скиллов (connect/vendor) — всегда **спрашивай у пользователя** (см. project-tooling-runbook).

> Источник истины рецептов — `packages/skiller/profiles/*.json` (детект — `core/project.py`).
> Таблица ниже должна с ними совпадать; при расхождении правь профиль, не таблицу.

## Сквозные неочевидные развилки (для любого архетипа)

| Развилка | По умолчанию | Когда менять |
|:--|:--|:--|
| **Канал скиллов** | спросить | `connect` (плагины, не в репо, нужен доступ к реестру) vs `vendor`/`sync` (физ.копии в репо — для внешних разработчиков). НЕ дефолт — выбор пользователя |
| **CORE-раздача** | вкл (`--no-core` отключает) | connect → курируемый плагин `core` (РОВНО 7 `CORE_SKILLS`, лёгкая замена бакетам general+oss-dev, ~480 vs ~1956 резидентных ток); vendor → те же 7 скиллов (`context-economy`/`anti-drift`/`compact-responses`/`session-handoff`/`mcp-advisor`/`verify-claims`/`gh-review`) пофайлово |
| **Память** | `maind` | `maind` (хаб, общая) / `native` (agentmemory локально) / `off`. См. ecosystem-integration |
| **namespace** | пусто → `default` | задать группы (`["axioma", …]`) для межпроектных связей; `["*"]` — общая инфраструктура |
| **Код-граф (Serena)** | по типу (язык есть) | `--with-code` поднимает per-project `serena` через `uvx`; не для vault/standalone |
| **Нераспознан** | МИНИМАЛЬНЫЙ набор (general+oss-dev), НЕ «всё» | укажи профиль явно или `--profile standalone` («поставь всё») |

## Рецепты по типу

| Тип | Детект (`core/project.py`) | Бакеты | MCP | harness-пресеты | agent-pack |
|:--|:--|:--|:--|:--|:--|
| **laravel-project** | `composer.json` + `artisan` | system, architect, php, laravel-{testing,auth,data-layer}, devops, quality, operator | context7 | base, laravel | backend-laravel |
| **php-package** | `composer.json` (без artisan) | system, oss-dev, php, php-packages, laravel-testing, quality, devops | — | — | — |
| **node-frontend** | `package.json` + UI-фреймворк/сборщик | system, architect, frontend, frontend-{vue,vite,linting,tailwind}, quality, devops | context7, playwright | base, node | node-frontend |
| **node-package** | `package.json` (без UI) | system, oss-dev, quality, devops | context7 | base, node | — |
| **python-backend** | `pyproject.toml`/`requirements.txt`/`setup.py` | system, architect, python, devops, quality, operator | context7 | base, python | python-backend |
| **blender** | `*.blend` / `blender_manifest.toml` / `import bpy` | blender, blender-modeling, python, quality | context7 | base, python | — |
| **dart-flutter** | `pubspec.yaml` | system, architect, mobile, quality | context7 | base | dart-flutter |
| **obsidian-vault** | `.obsidian/` | system, architect, pm, founder, operator, roles, finance, legal, marketing, sales, research, creative | — | — | — |
| **standalone** | дефолт (ничего не совпало явно) | `*` (все — только по явному `--profile standalone`) | — | — | — |

## Неочевидные вопросы по конкретным архетипам

- **node-frontend → какой фронт-стек?** Профиль раздаёт **Vue-SPA** набор (`frontend-vue`/`vite`).
  Для **Nuxt** добавь `frontend-nuxt` (бакет есть, но в профиль не входит — иначе бы тянулся всем
  Vue-проектам); для React/Svelte профиля пока нет — задай бакеты явно. `playwright` MCP включён
  (e2e), `figma` MCP — подключается вручную (нет в каталоге `harness mcp`).
- **blender → addon или моделинг?** `blender` (общее) + `blender-modeling` (параметрика). Код-граф
  Serena — `python`. Среда Blender нестандартна (встроенный python); пресет `python` — отправная
  точка, проверь интерпретатор.
- **obsidian-vault → не dev-проект.** Раздаются роль/доменные бакеты (pm/founder/research/…), НЕ
  dev-стек; код-граф/Serena и dev-пресеты НЕ нужны; память полезна (knowledge base).
- **php-package vs laravel-project.** Пакет (без `artisan`) — `oss-dev`+`php-packages` (разработка
  пакета, релизы), без laravel-app-бакетов. Приложение — полный laravel-стек.
- **standalone (нераспознан).** НЕ «дамп всего»: авто-фолбэк ставит ядро (general+oss-dev). «Всё» —
  только осознанно через `--profile standalone`.

## Сценарные кейсы (тексто-тесты)

Поведение скиллов под типовые задачи проверяется **eval-харнесом** (`skiller eval <bucket>/<name>`):
`evals/evals.json` (типовые задачи + детерминированные ассершены), `pressure.json` (соблазны
пропустить скилл), `triggers.json` (точность срабатывания `description`). Это «мысленный прогон»
типовых задач в дополнение к структурной валидации — заводи `evals/` приоритетным скиллам архетипа
(`skiller eval <skill> --scaffold`). Канон — [evals.md](./evals.md).
