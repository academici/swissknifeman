# P7 — факты по Codex-делегированию (слой 1, 2026-07-25)

Захват в день получения (§16 immediate-capture). Дисциплина D19 FOREMAN: метаданные/состав
репозитория — только GitHub API и прямое чтение raw-файлов; поведение Codex CLI — first-party
дока + исходник; полевая практика и методология замера — perplexity-web. Карта факт-классов,
написанная ДО поиска, — `research/15-P7-fact-classes.md`.

---

## §1. `openai/codex-plugin-cc` — состояние на 2026-07-25 (GitHub API + raw)

**Метаданные** (`api.github.com/repos/openai/codex-plugin-cc`, 2026-07-25):

| Поле | Значение |
|:--|:--|
| description | «Use Codex from Claude Code to review code or delegate tasks.» |
| stargazers_count | 29 895 |
| open_issues_count | **372** |
| language / license | JavaScript / Apache-2.0 |
| created_at | 2026-03-30 |
| pushed_at | **2026-07-08** (17 дней до даты захвата) |
| archived / disabled | **false / false** |

Вердикт по классу «жив ли»: **жив, но не в горячей разработке** — последний push 17 дней назад
при 372 открытых issues. Расхождение с нашими прежними записями: `roadmap/codex-subagent-offload.md`
(2026-07-18) писал 29.2k★, `findings/rag-2026-07-25.md` §1 — 29 882★; сегодня 29 895★. Порядок
величины подтверждён, точные числа устаревают — в ТЗ items ссылаться на класс, не на число.

### 1.1 Что плагин РЕАЛЬНО ставит (дерево репозитория, GitHub API `git/trees?recursive=1`)

`plugins/codex/`:
- **`commands/` — 8 файлов**: `review.md`, `adversarial-review.md`, `rescue.md`, `transfer.md`,
  `status.md`, `result.md`, `cancel.md`, `setup.md`.
- **`agents/` — 1**: `codex-rescue.md` (субагент `codex:codex-rescue`).
- **`hooks/hooks.json` — есть** (+ `scripts/session-lifecycle-hook.mjs`,
  `scripts/stop-review-gate-hook.mjs`).
- **`skills/` — 3**: `codex-cli-runtime/`, `codex-result-handling/`, `gpt-5-4-prompting/`.
- `prompts/` (2), `schemas/review-output.schema.json`, `scripts/` (17+, включая
  `codex-companion.mjs`, `app-server-broker.mjs`, `lib/{codex,git,render,job-control}.mjs`),
  `tests/` (8 файлов).

> **Следствие для рамки CLAUDE.md.** Установка добавляет как минимум описание **1 субагента**,
> **3 скиллов** и регистрацию **хуков** — три из пяти источников, которые считает
> `skiller budget --first-turn` (`skills`/`agents`/`hooks`). То есть это **новый always-on
> инжект**, и гейт обязателен по рамке, а не «на всякий случай». В отличие от P6.1 (D54, где
> ожидаемый ответ гейта — ноль) здесь ожидаемая дельта **строго положительна**, и её величина
> заранее неизвестна.

### 1.2 Установка и требования (README, raw.githubusercontent, main)

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```
Опционально: `npm install -g @openai/codex`; вход — `codex login`.
Требования дословно: «ChatGPT subscription (incl. Free) or OpenAI API key», «Node.js 18.18 or
later». **Требования к версии `codex` CLI README не называет**, но оговаривает: «Older Codex
versions lacking session import must be upgraded for `/codex:transfer` functionality».

### 1.3 Предупреждения самого README

- «Code review especially for multi-file changes might take a long time.»
- «The review gate can create a long-running Claude/Codex loop and **may drain usage limits
  quickly**.» (review-gate включается/выключается флагами `--enable-review-gate` /
  `--disable-review-gate` у `/codex:setup`).

### 1.4 Как именно запускается делегат (прямое чтение `plugins/codex/scripts/lib/codex.mjs`)

Плагин **не спавнит `codex` с флагами**, а говорит с демоном `codex app-server` по JSON-RPC.
Параметры запроса (дословно из модуля):

```
{ cwd, model: options.model ?? null, approvalPolicy: options.approvalPolicy ?? "never",
  sandbox: options.sandbox ?? "read-only", serviceName: SERVICE_NAME,
  ephemeral: options.ephemeral ?? true }
```

Прямой вызов CLI используется только для проверки доступности: `binaryAvailable("codex",
["--version"])` и `binaryAvailable("codex", ["app-server","--help"])`. `CODEX_HOME` по умолчанию
`~/.codex`.

Несущие следствия:
1. **`cwd` = чекаут репозитория** ⇒ делегат подпадает под обычный механизм обнаружения
   `AGENTS.md` (см. §2) — наш инструкционный слой ему виден.
2. **Дефолт `sandbox: "read-only"`, `approvalPolicy: "never"`** — ревью-дорожки безопасны
   по построению; какой sandbox получает пишущая дорожка `/codex:rescue`, **дока не называет**
   (`commands/rescue.md` про sandbox/approval молчит) ⇒ это проверяется эмпирически в пилоте,
   а не предполагается.
3. **`model`/`effort` по умолчанию `null`** ⇒ применяются дефолты `~/.codex/config.toml`.
   На этой машине там `model = "gpt-5.6-sol"`, `model_reasoning_effort = "xhigh"` — то есть
   «лёгкая задача» уедет на **xhigh** флагманской модели, если пин не задан явно. `rescue.md`
   при этом инструктирует: «Leave `--effort` unset unless the user explicitly asks…», «Leave
   the model unset unless the user explicitly asks for one» — то есть без нашей явной подачи
   дешёвого пина экономика делегирования разрушается на старте.
4. Работа идёт через **демон app-server**, а не одноразовый процесс ⇒ состояние (в т.ч.
   зарегистрированные хуки `~/.codex/hooks.json`) переживает вызовы; `ephemeral: true` относится
   к треду, не к демону.

### 1.5 Что говорит скилл `codex-cli-runtime` самого плагина

Про sandbox/approval/cwd — **не говорит ничего**; про AGENTS.md и конкурентность — тоже.
Явно задаёт роль субагента: «forwarder, not an orchestrator», один вызов helper'а, stdout
возвращается дословно; запрещает изнутри rescue звать `setup/review/adversarial-review/
status/result/cancel`. То есть ревью результата — обязанность вызывающей стороны, плагин её
не встраивает.

---

## §2. Codex CLI: семантика слоёв `AGENTS.md` (first-party дока + исходник)

Источники: `learn.chatgpt.com/docs/agent-configuration/agents-md` (редирект с
`developers.openai.com/codex/guides/agents-md`, 308) + исходник `codex-rs/core/src/agents_md.rs`
через context7 `/openai/codex`.

**Порядок чтения:**
1. Глобальный: `~/.codex/AGENTS.override.md`, иначе `~/.codex/AGENTS.md`.
2. Проектный: от корня проекта **вниз до текущего рабочего каталога включительно**; в каждом
   каталоге — `AGENTS.override.md`, затем `AGENTS.md`, затем `project_doc_fallback_filenames`.

**Корень проекта** определяется подъёмом до маркера `project_root_markers` (дефолт — `.git`);
выше корня обход не идёт. Дословно из исходника: «We include the concatenation of all files
found along the path from the project root to the current working directory», «We do **not**
walk past the project root».

**Склейка:** все файлы грузятся сразу (не лениво), «concatenates files from the root down,
joining them with blank lines»; более глубокий файл имеет приоритет при конфликте («More deeply
nested AGENTS.md files take precedence»), но прямые system/developer/user-инструкции промпта
перебивают любой AGENTS.md.

**Лимит:** суммарный размер ограничен `project_doc_max_bytes`, **дефолт 32 768 байт (32 KiB)**;
при достижении лимита Codex перестаёт добавлять файлы, **усечение молчаливое** («Truncation
occurs silently, so critical guidance should be placed in nested directories closest to where
it's needed»); `project_doc_max_bytes = 0` полностью отключает загрузку.

**Резидентность:** «The contents of AGENTS.md files at the repo root and up to the CWD are
included **with the developer message** and do not need re-reading» — то есть для Codex это
такой же always-on инжект, как CLAUDE.md для Claude Code, и его цена платится каждый ход.

> **Несущее следствие, меняющее постановку P7.2** (сверено с деревом репозитория):
> вложенные `packages/<pkg>/AGENTS.md`, объявленные в замороженном каталоге
> `lib/harness/instructions.py` (`TARGETS[...]["codex"]`), **при нашем каноническом запуске
> не читаются вовсе** — канонический launch-блок корневого `AGENTS.md` фиксирует
> `codex -C /home/vostrikov/projects/packages/swissknifeman`, то есть cwd = корень репо, а Codex
> склеивает путь **корень→cwd**, а не корень→вниз по дереву. Файлы ниже cwd подтягиваются, только
> если агент сам их прочитает (дока прямо говорит: «The agent should check for applicable
> AGENTS.md files when working in subdirectories») либо если Codex запущен с `-C` внутри пакета.
> Для Claude Code симметричной проблемы нет: у него per-package `CLAUDE.md` подхватывается при
> работе с файлами пакета.

**Локальное состояние (repo/machine-grounded, для сверки):** `~/.codex/AGENTS.md` — **0 байт**;
`project_doc_max_bytes` в `~/.codex/config.toml` не задан ⇒ действует 32 KiB; корневой
`AGENTS.md` репо — 63 строки / 4 946 байт (≈15% лимита); `packages/*/AGENTS.md` в дереве
отсутствуют; в `~/.codex/config.toml` заданы `model = "gpt-5.6-sol"`,
`model_reasoning_effort = "xhigh"`, `approval_policy = "never"`, `sandbox_mode = "workspace-write"`.

---

## §3. Лимиты Codex и наблюдаемость расхода (perplexity-web, 2026-07-25)

- Расход Codex трактуется как **общий agentic-лимит**: разные поверхности (CLI, web/app,
  сопутствующие потоки) черпают из одного плана/allowance, изолированных пулов не описано ⇒
  **делегирование не «бесплатно из другого кармана» в пределах одной подписки OpenAI**, оно
  просто не тратит лимит Claude.
- Исчерпание: при достижении лимита **внутри активного хода** Codex может доработать ход, далее —
  баннер/страница usage; варианты — ждать сброса, докупить кредиты, апгрейд. Сообщества
  описывают скользящее **5-часовое** окно и в ряде случаев недельный потолок.
- Наблюдаемость: официально — Codex Settings → Usage; в CLI сообществом описывается **`/status`**
  (текущее использование/лимиты в сессии), плюс статус-строка с 5-часовым и недельным метрами.

**Класс корроборации: средний** (докстраница по прямому URL rate-limits отдала 404; синтез
опирается на help-доку и сообщества). Для ТЗ это означает: ось «лимиты» в пилоте меряется тем,
что реально доступно неинтерактивно, а если такого канала нет — фиксируется как
`baseline_pending` с причиной, а не выдумывается.

---

## §4. Полевая практика делегирования второму провайдеру (perplexity-web, web+social)

Сходятся на одном: делегирование работает, но ломается там, где контекст проекта неявен,
конвенции живут в головах, и два агента правят одно дерево.

**Названные режимы отказа:**
1. **Потеря контекста** — забываются архитектурные решения и состояние репо на длинных сессиях
   ⇒ дрейф и выдуманные допущения.
2. **Дрейф конвенций** — локально правдоподобный код, несовместимый с паттернами репо, если
   правила не записаны и не поддерживаются в файлах.
3. **Ревью-оверхед** — узкое место переезжает с написания на верификацию; описан «velocity trap»:
   сэкономленное на генерации теряется на отладке и проверке.
4. **Конкурентные правки** — общий рабочий каталог: один агент молча обесценивает допущения
   другого; безопаснее **отдельные git worktree** на параллельные сессии; агенты путаются в
   git-состоянии, когда сами создают worktree ⇒ рабочее пространство готовит вызывающая сторона.

**Что снижает урон:** правила проекта — в файлах репо (`CLAUDE.md`/`AGENTS.md`/handoff),
а не в истории чата; worktree на параллельность; компактный handoff (что изменено, что
протестировано, что осталось, какие допущения); **узкие задачи** — отчёты заметно позитивнее
на изолированных фиксах, тестах и узких рефакторингах, чем на широких конвенционно-чувствительных
переписываниях. Операционное правило источника: «delegate execution, not memory».

**Класс корроборации: средний** (источники — практические разборы/видео, не измерения).

---

## §5. Чем меряют «получилось ли» у делегирования (perplexity-web, web+academic)

**Метрики (определения дословно по смыслу источников):**
- **accepted-without-edit rate** — доля задач, слитых без единой человеческой правки кода.
- **rework rate** — принятое, но потребовавшее содержательной правки позже (первый проход и
  «в итоге» разделяются намеренно).
- **review-overhead ratio** — время человека на ревью+исправление / время самостоятельной
  реализации. **Устойчиво > 1 ⇒ делегирование стоит дороже, чем экономит.**
- **cost per accepted task** — расход инструмента + время ревью по ставке / число принятых.
- **wall-clock** — от постановки до мержа, включая ожидание и переделки.

**Размер выборки** (сходящееся правило источников): **10** задач — поймать очевидные поломки
процесса; **30–50** — первая устойчивая оценка приёмки/ревью; **100+** — сравнение категорий
задач/моделей. При неоднородном миксе **стратифицировать, а не пулить**: документация, рефакторинг,
багфикс и фича ведут себя по-разному.

**Ловушки замера:** черри-пик лёгких задач (доля приёмки завышается и не обобщается) ·
смещение ревьюера · vanity-метрики (строки, число PR, токены) · игнор микса задач ·
**first-draft bias** (мерить «время до первого коммита» — прятать стоимость правок).

**Класс корроборации: высокий** (в источниках — две arxiv-работы + практические гайды по оценке
кодовых агентов в проде).

---

## §6. Аддитивно ли кросс-модельное ревью (perplexity-web, web+academic)

Кейс-стади 2026 (33 артефакта, 294 подтверждённых дефекта, human-reconciled answer key):
- **56,8%** подтверждённых дефектов найдены **ровно одной** моделью (167 из 294);
- медианное попарное перекрытие (Jaccard) ≈ **0,29**;
- ни одна крупная модель не превысила **≈61% recall** на коде;
- добавление **второго независимого** ревьюера подняло покрытие внутри артефакта с **≈47% до
  ≈72%**; третий и далее — заметно убывающая отдача.

**Как правильно мерить ценность ревью:** gold-set подтверждённых проблем с человеческим
арбитражем, затем recall/precision/uniq-finding/дубли по нему; сравнение «один ревьюер против
двух» на одном наборе артефактов. **Число комментариев — слабая метрика**; рост объёма ревью без
роста подтверждённых находок = шум, а не ценность («finding inflation» — реальный режим отказа,
свидетельство по нему косвенное).

**Класс корроборации: высокий по аддитивности** (одна сильная работа с ключом-эталоном),
**низкий по false-positive rate** — источники сами называют этот срез слабо стандартизованным.

---

## §7. Что из этого НЕ проверено и остаётся риском

| Пробел | Почему не закрыт | Как обходим |
|:--|:--|:--|
| Какой sandbox получает пишущая дорожка `/codex:rescue` | ни README, ни `commands/rescue.md`, ни скилл рантайма не называют | **эмпирическая проверка первым шагом пилота** (пробная задача + `git status`), а не допущение |
| Точный неинтерактивный канал чтения остатка лимита Codex | док-страница rate-limits по прямому URL — 404; `/status` описан сообществом как интерактивная команда | ось «лимиты» меряется доступным каналом; нет канала ⇒ запись `baseline_pending` с причиной |
| False-positive rate кросс-модельного ревью | срез слабо стандартизован в источниках | в правило вердикта входит **uniq-confirmed**, а не «сколько замечаний»; шум ловится долей неподтверждённых |
| Совместимость плагина с нашей раскладкой хуков Codex | плагин регистрирует свои хуки; в `~/.codex/hooks.json` уже живут наши (`log-bash-command`, `block-daemon-ops`, `review-gate`) | проверка целостности хуков — обязательный шаг пилота (перекликается с `AGENT-RELIABILITY` P0.4) |
