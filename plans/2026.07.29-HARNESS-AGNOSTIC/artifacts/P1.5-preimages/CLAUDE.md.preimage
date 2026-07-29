# CLAUDE.md — academici (монорепо)

Гид для агентов по корню монорепо. Это **зонтик экосистемы academici**: один репозиторий —
несколько независимых пакетов и плагинов под общей крышей (имя `swissknifeman` = контейнер-«швейцарский
нож», НЕ один из инструментов). Каждый пакет — самостоятельный CLI (`skiller`, `harness`, `maind`);
над ними — тонкий **корневой управляющий слой** `swissknifeman` (`bin/swissknifeman`):
router к пакетам + кросс-пакетный `setup` (онбординг). Зонтик = единое управление, пакеты = возможности.

## Раскладка

```
<monorepo>/                     # репо `swissknifeman` (зонтик-контейнер)
├── install.sh                 # зонтичный установщик (делегирует install.sh пакетов)
├── core/                      # общий stdlib-only пакет `core` (дословные дубли: Env/term/text)
├── packages/
│   ├── skiller/               # реестр AI-скиллов (skills/, skm/, generate-skill/, lib/, bin/) — CLI skiller
│   ├── harness/               # настройка окружения Claude Code (configs/, lib/, bin/, commands/) — CLI harness
│   ├── maind/                 # хаб памяти/графа/координации (lib/, bin/, commands/) — CLI maind
│   ├── analyst/               # continuous learning: захват уроков из прогонов (lib/, bin/, commands/) — CLI analyst
│   └── task/                  # интент-команды + plan-протокол (commands/, lib/, tests/) — без CLI, только plugin
├── .claude-plugin/
│   └── marketplace.json       # ЕДИНЫЙ marketplace репо (генерируется), ~50 плагинов
└── docs/                      # зонтичный VitePress: общее (index/routing/roadmap) + агрегат
                               # per-package доков (источник — packages/<pkg>/docs,
                               # scripts/docs-sync.sh копирует в docs/<pkg>/, gitignored)
```

> **Имена ≠ роли.** Репо/marketplace/`~/.swissknifeman/` state — это зонтик `swissknifeman`
> (бренд экосистемы, не переименовываем). Инструмент управления скиллами — пакет/CLI `skiller`
> (бывш. inner `swissknifeman`; алиас `swissknifeman` сохранён в PATH). «hub/хаб» — только роль
> центрального узла mAInd в прозе, не имя сервера.

## Пакеты (у каждого свой CLAUDE.md — читай его при работе внутри)

| Пакет | Роль | CLI | Деталь |
|:--|:--|:--|:--|
| [`packages/skiller`](packages/skiller/CLAUDE.md) | реестр скиллов (раздаёт навыки в проекты) | `skiller` (алиас `swissknifeman`) | source истины скиллов; 2 канала connect/vendor |
| [`packages/harness`](packages/harness/CLAUDE.md) | настройка окружения Claude Code | `harness` | пресеты permissions, auto-approve/bypass, MCP-серверы, хуки (memory/notify). Source истины — `configs/claude-code/`. skiller делегирует сюда через subprocess |
| [`packages/maind`](packages/maind/CLAUDE.md) | память + граф + координация (хаб/шина) | `maind` | MCP-хаб, namespace-память, федерация графа. **Единый** — память (`agentmemory`) и graphify (граф кода) уже отдельные MCP-серверы; дробить maind не нужно |
| [`packages/analyst`](packages/analyst/CLAUDE.md) | continuous learning (захват уроков из прогонов) | `analyst` | детерминированный (stdlib, on-demand — без демона) слой-1: `digest` (run-report → кандидаты) · `review`/`promote` с **человеком в гейте** (авто-запись запрещена) · провенанс/audit · curated всплывает в память mAInd. P1 (MVP); cross-project scan + confidence-lifecycle — P2/P3 |
| [`packages/task`](packages/task/CLAUDE.md) | интент-команды постановки задач + plan-протокол | нет (plugin-only, без `bin/`) | `/task:design\|dev\|review\|research\|fix` + `/task:plan-design\|plan-exec\|plan-close\|plan-audit` (исполняемые мастер-планы в `plans/`); каждая команда пинит модель/effort/workflow per-команда, перебивая настройки сессии |

Это **один монорепозиторий, не «соседние пакеты»**: maind координирует skiller через
`subprocess` (см. `packages/maind/lib/maind/orchestrate.py`); skiller так же делегирует окружение
в harness (`apply_permissions`/integrate → `harness permissions|mcp|hooks`). Все используют `core/`.

## CLI: корневой router + пакеты

```bash
swissknifeman <group> …    # корневой управляющий слой (bin/swissknifeman): router + setup-фасад
  swissknifeman skills …   #   → skiller   (connect, vendor, registry, …)
  swissknifeman env …      #   → harness   (permissions, mcp, hooks, …)
  swissknifeman maind …    #   → maind     (memory, graph, onboard, deploy, …)
  swissknifeman analyst …  #   → analyst   (digest, scan, review, promote, deprecate, doctor)
  swissknifeman setup <p>  #   → maind onboard (скиллы+окружение+память+граф одной командой)
  swissknifeman doctor     #   диагностика всех пакетов (fan-out)
# back-compat: swissknifeman <skiller-cmd> (connect/vendor/integrate/…) → skiller (старый алиас)

skiller <cmd>              # реестр скиллов: connect, vendor, integrate, registry, status, …
harness <cmd>              # окружение Claude Code: permissions, mcp, hooks, doctor
maind <cmd>                # хаб: memory, graph, onboard, deploy, sync, health, doctor, …
analyst <cmd>              # continuous learning: digest, scan, review, promote, deprecate, doctor
# task — сознательно БЕЗ строки в `swissknifeman <group>`: у пакета нет bin/CLI, только
# slash-команды плагина (/task:*, см. таблицу «Пакеты»); роутить через swissknifeman нечего
```

Корневой `swissknifeman` — тонкий диспетчер: логику не реализует, делегирует пакетам;
кросс-пакетный онбординг живёт ОДИН — в `maind/onboard.py` (его зовёт `swissknifeman setup`).
Установка: зонтичный `install.sh` ставит `skiller`/`harness`/`maind`/`analyst` (их `install.sh`) + симлинк
`swissknifeman`→`bin/swissknifeman`; **алиасом `swissknifeman` владеет зонтик** (не skiller — иначе
re-run skiller install затирал бы router). Пути maind зашиты в `.mcp.json` онбордженных — не ломать.

## Общий пакет `core`

**Дословные дубли** + **примитивы, которые оба пакета успели скопировать независимо** (сведены
к одному источнику истины): `core.term` (die/warn/now_iso/confirm), `core.text` (sanitize),
`core.env` (BaseEnv — ядро root/cmd/home), `core.io` (atomic_write_text/json — атомарная запись
tmp+`os.replace`), `core.repo` (find_repo_root/find_monorepo_root — единый поиск корня вместо
расходившихся копий). `Env` каждого пакета наследует `BaseEnv`, импорт — `from core import ...`.
Подключается через PYTHONPATH (без pip): лаунчеры/`test.sh`/`validate.sh` добавляют **корень
монорепо** (где лежит `core/`) опционально (fallback на standalone-раскладку пакета). stdlib-only.
Bash-лаунчеры и heredoc в `validate.sh` определяют корень своим способом (фикс. `../..` / поиск
`.git`) — осознанный дубль: `core` ещё не на PYTHONPATH в момент их работы.

## Единый marketplace

Один `.claude-plugin/marketplace.json` в корне репо объявляет все плагины (бакеты скиллов +
курируемый `core` + `skm` + `generate-skill` + `harness` + `maind`). Генерируется `skiller registry`:
бакеты — из `skills/**/SKILL.md`; курируемый `core` — `source:"./"` + `skills[]` из `CORE_SKILLS`
(7 скиллов из разных бакетов по ссылкам, без своего каталога — «умное подключение», лёгкая замена
бакетам general+oss-dev); соседние пакеты (`harness`, `maind`) — из их `packages/<name>/.claude-plugin/plugin.json`.
`source`-пути относительны корня репо (`./packages/...`). Имя marketplace — `swissknifeman` (= зонтик).
У каждой записи плагина есть поле **`package`** (провенанс: `skiller`/`harness`/`maind`) — имена
плагинов НЕ префиксуются (back-compat: плагины подключены как `<plugin>@swissknifeman`).
Плагины `harness`/`maind` — **только команды** (`/harness:*`, `/maind:*`), MCP-сервера в них нет;
MCP-инструменты хаба приходят в проект per-project сервером `maind` из его `.mcp.json`.

## Философия и рамки

**Тезисы** (почему репо устроен именно так):
- **Зонтик ≠ инструмент, имена ≠ роли.** Контейнер `swissknifeman` управляет; возможности дают
  самостоятельные пакеты (`skiller`/`harness`/`maind`). Бренд/marketplace/state — не переименовываем.
- **Единый источник истины > копий.** Дубль примитива → в `core/`; один marketplace, один онбординг
  (`maind/onboard.py`), один каталог провенанса. Дедуп, а не параллельные реализации.
- **stdlib-only, без рантайма.** Python — только стандартная библиотека, без pip/JS. Внешний код
  берём как **паттерн** и переписываем, а не тащим зависимостью.
- **RAG-делегирование (токен-экономия).** Retrieval+синтез внешних фактов выгружаем на flat-rate
  `perplexity-web` (keyless-мост по подписке, компактный синтез вместо сырья в контекст) — **агрессивно, по
  максимуму**: дешевле по контекст-токенам, чем WebSearch/WebFetch. В русле `context-economy`. context7 —
  для точного API библиотек; на его промах фолбэк на perplexity-web, не на WebSearch.
- **Детерминированная доставка.** skiller доставляет навыки, а не «угадывает»; провижининг
  `maind`/`harness` воспроизводим; манифесты генерируются (`skiller registry`), не правятся руками.
- **Faithful-first + провенанс.** Внешнее вендорим близко к источнику и обязательно с паспортом
  (`upstream.json`); значимое — в каталог референсов (см. ниже).
- **Изоляция по namespace.** Память/граф общие внутри namespace и изолированы между (scope-маркеры).
- **Спекулятивное — в `roadmap/`.** Фичу внедряем по факту измеренной проблемы, не на упреждение.

**Рамки — за них не выходим:**
- Не добавляем pip/npm-рантайм в python-пакеты (**stdlib-only** — жёстко).
- Не дублируем примитивы между пакетами — общее живёт в `core/`.
- Не переименовываем зонтик/marketplace/`~/.swissknifeman/` state и не префиксуем имена плагинов
  (back-compat).
- Не ломаем зашитые пути `maind` в `.mcp.json` онбордженных проектов.
- Не вендорим Proprietary-источники (напр. `docx/pdf/pptx` из `anthropics/skills`) и не вендорим
  без `upstream.json`.
- Не утверждаем внешние факты по памяти — верифицируем (RAG, см. «Методология решений»).
- Не раскатываем новый always-on инжект (hook additionalContext, description скилла/агента/
  команды, CLAUDE.md-блок, MCP-сервер) без прогона `skiller budget --first-turn` — вписался
  в бюджет (target 3–7K, warn 10K) или нет, решает Owner; marketplace-плагины Claude Code этот
  измеритель не видит структурно (ставятся вне `<target>/.claude/**`) — их always-on цену даёт
  второй инструмент, `claude plugin details <plugin>`, и вход к владельцу обязателен, только
  если сумма (`--first-turn` до установки + цена плагина) переводит проект ЧЕРЕЗ порог 10K, а
  не при любом её значении; нарушение — блокер ревью.

## Документация и планы

Дом исполнимого плана — репо проекта (`plans/<ID>/`, рядом с `docs/`); в vault Brain остаётся
только программный/межпроектный план (deliverables размазаны по многим репо) + линк control
tower на репо-план. Схема «где что лежит» (docs↔vault sync, план↔control tower,
findings/artifacts) — скилл-карта `axioma/ecosystem-map` (указатель, не копия); канон плановой
системы (Meta/статусы/DoR/команды `/task:plan-*`) — скилл `general/plan-protocol`.

## Разработка

```bash
# тесты/валидация — по пакету (каждый знает свой core через PYTHONPATH):
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
PYTHONPATH=. python3 -m unittest discover -s core/tests       # smoke-тесты пакета core
```

Конвенции пакетов — в их CLAUDE.md. Общее: **stdlib-only** в python, `Env` явно, atomic JSON,
сообщения на русском. Коммиты — Conventional Commits на русском.

**Ссылки на планы из кода (D3):** только полный `<PLAN-ID> Pn.m` (напр. `2026.07.25-ECO-OPT
P1.2`), не голое `Pn.m` — при нескольких активных планах голый номер коллизирует; планы не
удаляются (архивируются), поэтому полный ID остаётся grep-адресным и после архивации.

## Референсы и провенанс

Чем пользовались при разработке (внешние фреймворки, каталоги агентов Claude Code, чужие
skill-репо, спеки) — собрано в одном месте, чтобы возвращаться адресно:

- **[docs/reference.md](docs/reference.md)** — единый каталог изученных внешних источников: что это,
  зрелость, **плюсы/минусы**, вердикт (**adopt** / **reference** / **skip**) и **что именно взято**
  в swissknifeman; карточки по значимым источникам + итог «как это легло в архитектуру».
- **`upstream.json`** рядом со `SKILL.md` — per-skill паспорт вендоринга (`source`/`repo`/`license`/
  `sha256`, `strategy` = `replace` | `notify` | `fork` | `merge`). Источник истины провенанса
  конкретного скилла.
- **[docs/rejected-optimizations.md](docs/rejected-optimizations.md)** — идеи, рассмотренные и
  осознанно **отклонённые** (не «отложено», как `roadmap/` — «нет, и почему», пока не поменялись
  сами рамки репо). Сверяться до повторного изобретения того же предложения.

> **Правило:** использовал внешний ресурс (репо, фреймворк, чужой скилл, статью, спек) при
> проектировании — **отметь** его в `docs/reference.md` (строка в таблице, при значимости — карточка).
> Отклонил нетривиальное предложение, которое может всплыть повторно — строка в
> `docs/rejected-optimizations.md`. Оба каталога не должны отставать от реально решённого.

## Методология решений (always-on)

Решения/вердикты на **внешних** фактах (версии/API библиотек, «ещё актуально», рынок, возможности чужого
сервиса/MCP, какой пакет/команда актуальны) — **верифицировать через RAG** до фиксации; **repo-grounded**
факты — подтверждать чтением кода. Лестница: `context7` (точный API библиотек) → на промах context7 или для
всего вне доков — **агрессивно `perplexity-web`** (flat-rate, токен-дёшево; жать по максимуму) → `WebSearch`
последним фолбэком (RAG-ступень выполняй там, где доступен `perplexity-web` — **не делегируй её тул-бедному
субагенту**: тот молча роняет лестницу до WebSearch). **Формирование плана 100% стоит на свежих данных** и завершается footer'ом «Проверка»
(что проверено · **непроверенное → ПОВТОРНЫЙ ПРОХОД**, если движок был недоступен · обходки-`[POSSIBLE-DEFECT]`);
честность — не правки ради правок, костыль называть костылём, а не выдавать за решение. Канон: root-скилл
`decision-verification` → реестровый `general/verify-claims`. Особенно при разборе аудитов в `research/`:
даже «полный» аудит — внешние вердикты до-проверять, а не отклонять по устаревшему знанию.
**Покрытие множества, не только глубина одного факта:** перед фиксацией плана/фазы/вердикта перечисли
ВСЕ внешние факт-классы, на которых он стоит, — включая те, ответ на которые кажется уже известным;
сводка тул-бедного делегата — черновик для сверки первоисточником, а не исчерпывающий перечень.
