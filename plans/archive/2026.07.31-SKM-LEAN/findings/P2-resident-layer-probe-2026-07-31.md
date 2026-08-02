# Замер резидентного слоя 2026-07-31 (слой 1) — вход P2

**Слой 1 (сырьё).** Живые прогоны автора плана + RAG-выжимки с URL, 2026-07-31.
Дерево swissknifeman `ebd42655` (`main`; рабочее дерево несёт только файлы этого плана).
Клиент: **Claude Code 2.1.220** (`claude --version`). Измеритель: `packages/skiller/bin/skiller
budget --first-turn` (модель источников — `budget.py:516–523`).

> Дисциплина: это сырьё. Синтез и целевая конструкция — `research/02-p2-resident-model.md`,
> решения — `plan.md` §5.

## 1. Разложение first-turn по четырём проектам (живой прогон)

| Проект | skills meta | `.claude/agents` | `CLAUDE.md` + rules | SessionStart-хуки | MCP tool-defs | Итого | Вердикт |
|:--|--:|--:|--:|--:|--:|--:|:--|
| swissknifeman (umbrella) | 2 559 (37 скиллов) | 567 (6) | **2 381** | 0 (1 хук) | **5 250** (3 сервера) | 10 757 | WARN |
| agelto | 5 630 (86) | 930 (10) | **14 959** | 142 (2) | **10 950** (6) | 32 611 | WARN |
| flexcrm | 5 630 (86) | 940 (10) | **15 141** | 143 (2) | 7 500 (4) | 29 354 | WARN |
| vintera/cms | 5 630 (86) | 694 (8) | **11 512** | 0 (1) | 6 000 (4) | 23 836 | WARN |

Два верхних потребителя резидента везде одни и те же: **`CLAUDE.md` (46–52 % у флота)** и
**MCP tool-defs (23–34 %)**. У umbrella пропорция иная: MCP 49 %, `CLAUDE.md` 22 %.

Цифры agelto/flexcrm совпадают с затравкой брифа (32 611 / 29 354) — эти два числа брифа
воспроизводятся на дереве `ebd42655` побайтово.

## 2. `CLAUDE.md`: сколько из него генерирует САМ swissknifeman

Разбор по маркерам `<!-- swissknifeman:hub:start … end -->` (генератор —
`packages/skiller/scripts/generate-hub.sh`, вызов — `packages/skiller/lib/skiller/hub.py:13`),
оценка тем же `estimate_tokens`, что и у измерителя:

| Проект | `CLAUDE.md` всего | хаб-блок | доля хаба | строк всего / хаб |
|:--|--:|--:|--:|--:|
| agelto | 14 203 | **10 319** | **72 %** | 403 / 237 |
| flexcrm | 15 014 | **9 989** | **66 %** | 599 / 219 |
| dterema/app | 13 535 | **7 007** | **51 %** | 504 / 162 |
| vintera/cms | 11 387 | 0 | 0 % | 780 / — |
| sibintek-insiders | 8 605 | 0 | 0 % | 527 / — |
| diabox | 7 187 | 0 | 0 % | 462 / — |

**Содержимое хаб-блока** — приоритеты чтения источников (~15 строк) + **перечисление
установленных скиллов с описаниями** (у agelto: заголовок `## Установленные скиллы (128)`,
200 строк из 237) + правила поиска скилла.

Внутри блока — управляющие комментарии генератора
(`<!-- swissknifeman:registry sha=f8176958025c skills=229 -->`, «НЕ редактируйте вручную»).
Рядом отдельный managed-блок maind: `<!-- maind:healthcheck hash=… -->` (~209 ток).

**Проектное содержимое agelto без обоих managed-блоков — 153 строки** (то есть авторская
часть `CLAUDE.md` уже укладывается в апстрим-рекомендацию ≤ 200 строк; за порог её выводит
генерируемый индекс).

Режимы записи генератора (`generate-hub.sh:10–18`): проект с Laravel Boost →
`.ai/guidelines/swissknifeman-hub.md` (Boost сам вставляет фрагмент в `CLAUDE.md`); проект без
Boost → managed-блок прямо в `CLAUDE.md`; `--root-files A,B` → тот же блок дополнительно в
`AGENTS.md`/`GEMINI.md`.

## 3. `CLAUDE.md` по всему реестру (строки)

Реестр `config.json` `projects[]`, 26 записей (`enabled` у всех):

| Строк | Проекты |
|:--|:--|
| > 400 | cms 779 · flexcrm 598 · sibintek-insiders 527 · dterema-app 503 · diabox 461 · agelto 402 |
| 200–400 | vintera 390 · brain 365 · loqum 252 |
| < 200 | memster 194 · edufy 179 · chatom 157 · axiomaerpsdk 130 · corex 99 · swissknifeman 88 · azguard 77 · botkit 75 · perplexity-web-mcp 74 · vaulter 15 |
| нет файла | axiomastudio · dterema · agentools · 4 × `local-repo` (`/tmp/**`, stale registry entry) |

**Umbrella `CLAUDE.md` — 88 строк / 2 381 ток**, то есть цель брифа «≤ 200 строк» на umbrella
**уже выполнена**; за неё выходят проекты флота. Пер-пакетные `CLAUDE.md` (40–52 строки) в
корневой сессии не резидентны — измеритель считает только корневой файл (`budget.py:378–400`).

## 4. `.claude/rules`: что уже есть

- **Источники agent-pack'ов** (`packages/harness/configs/claude-code/agent-packs/*/rules/`):
  23 файла, из них **18 несут `paths:`**, 5 — нет, и все пять это `reviewer-overrides.md`
  (по одному на пак `_common`/`backend-laravel`/`dart-flutter`/`laravel-package`/
  `node-frontend`/`python-backend`).
- **На флоте** (выборка agelto/flexcrm/botkit): раскатанные правила path-scoped, кроме
  одного резидентного `<project>-reviewer-overrides.md` на проект (11–40 строк).
- **В самом swissknifeman каталога `.claude/rules/` нет вовсе** (подтверждает
  `repo-recon-2026-07-31.md` §9).
- Измеритель считает `.claude/rules/*.md` **без** `paths:` и пропускает файлы **с** `paths:`
  (`budget.py:399–400`); подкаталоги `.claude/rules/**` он **не обходит** —
  `rules_dir.glob("*.md")`, только верхний уровень.

## 5. MCP: состав и модель стоимости

- Оценка измерителя — статическая: `KNOWN_MCP_TOOLS` (11 серверов) × `TOKENS_PER_MCP_TOOL =
  150`, неизвестный сервер → `FALLBACK_MCP_TOOLS = 5` (`budget.py:200–206`); живых схем не
  читает (`:479–480`).
- Umbrella `.mcp.json`: `maind` (11 инструментов), `perplexity-web` (4), `serena` (20) →
  35 × 150 = **5 250 ток**.
- agelto: `context7`, `laravel-boost`, `maind`, `perplexity-web`, `playwright`, `serena` →
  10 950. vintera/cms несёт сервер с именем `boost` (не `laravel-boost`) → он **неизвестен**
  таблице и оценён fallback'ом 5 × 150 = 750.

### 5.1 Tool search — включён по умолчанию (внешний факт, верифицирован дважды)

RAG:✅ 2026-07-31, `https://code.claude.com/docs/en/context-window` §«MCP tools (deferred)»:
имена MCP-инструментов перечисляются, **полные схемы по умолчанию отложены** и подгружаются
по требованию через tool search; `ENABLE_TOOL_SEARCH=auto` грузит схемы вперёд, если они
влезают в 10 % контекстного окна; `ENABLE_TOOL_SEARCH=false` грузит всё.

RAG:✅ 2026-07-31, `https://code.claude.com/docs/en/mcp` §«Scale with MCP tool search»:
«Tool search is enabled by default»; на старте сессии в контекст попадают **только имена
инструментов и инструкции сервера**; фиксированного капа инструментов на сервер нет —
практический предел это бюджет контекста. То же в
`https://code.claude.com/docs/en/features-overview` §«Understand how features load → MCP
servers» и в `https://code.claude.com/docs/en/agent-sdk/mcp` §«MCP tool search».

RAG:✅ 2026-07-31 (perplexity-web, `web`): подтверждает то же — при включённом tool search
резидентны имена (`mcp__{server}__{tool}`) и инструкции сервера, схемы подгружаются по 3–5
релевантных на запрос и остаются доступны до компакта; канонический переключатель —
переменная окружения `ENABLE_TOOL_SEARCH`, её кладут в `settings.json` → `env`.

**Следствие:** строка «MCP tool-defs» измерителя честна только как **верхняя граница при
выключенном tool search**. На дефолтной конфигурации 5 250 ток umbrella и 10 950 ток agelto —
не резидент, а верхняя оценка отложенного. Это ровно та половина бюджета, из-за которой гейт
красен у всех.

**Замер конфигурации:** `ENABLE_TOOL_SEARCH` не выставлен нигде в репозитории и отсутствует в
`.claude/settings.json` (`env` пуст) — значит на всех проектах флота действует дефолт
(tool search **включён**).

**Репозиторий этот факт уже знает — но не в коде:** скилл `general/mcp-advisor`
(`SKILL.md:113–117`) прямо предупреждает, что оценка «150 ток × схема» честна лишь как верхняя
граница при выключенном tool search; `general/context-economy` (`SKILL.md:89`) держит цифру
«lazy tool-search режет схемы ~84 %». Носителем правды остаётся проза скилла, измеритель
считает по старой модели.

## 6. `.claude/rules` и `CLAUDE.md` — апстрим-канон (внешний факт)

RAG:✅ 2026-07-31, `https://code.claude.com/docs/en/claude-directory` §«Organize rules with
.claude/rules/»: правила **без** `paths:` грузятся на старте сессии наравне с `CLAUDE.md`;
правила **с** `paths:` — только когда Claude читает подходящий файл; подкаталоги внутри
`.claude/rules/` обнаруживаются автоматически; рекомендация — **разносить `CLAUDE.md` по
файлам, когда он приближается к 200 строкам**.

RAG:✅ 2026-07-31, `https://code.claude.com/docs/en/memory` §«Path-specific rules»: `paths:` —
YAML-frontmatter со списком glob'ов; правило срабатывает, **когда Claude читает подходящий
файл**, а не на каждом вызове инструмента; поддерживаются несколько шаблонов и brace-раскрытие.

RAG:✅ 2026-07-31, `https://code.claude.com/docs/en/features-overview` §«Understand how
features load → CLAUDE.md»: `CLAUDE.md` грузится **целиком** на старте (managed/user/project),
вложенные — по мере захода в подкаталоги; рекомендация — держать файлы **под 200 строк**,
справочный материал уводить в скиллы, которые грузятся по требованию.

> Поверхность `paths:` у **правил** и у **скиллов** — разные: у скиллов поле обнаружения
> сломано апстрим-багом #49835 (D11, риск фазы P3), у правил документировано и работает
> штатно. Замер `budget.py:399` стоит именно на правилах.

## 7. `.mcp.json.example` (вход P2.5)

- Флаг `mcp.emit_example`, дефолт `false`: объявление `config.example.json:131` (док `:129`),
  единственное чтение — `packages/maind/lib/maind/provision/deploy.py:294`
  `bool((config.get("mcp") or {}).get("emit_example"))`; **константы-дефолта в схеме нет**.
- Точка эффекта — `deploy.py:344–346`: `write_example(path, data, project_path, dry=dry)` +
  `reconcile_gitignore(project_path, rel, dry=dry)` в цикле по каналам.
- `reconcile_gitignore` (`mcpconfig.py:120–147`): реальный файл — append-if-absent в
  `.gitignore`, его `.example` — remove-if-present; идемпотентно; если реальный файл уже
  трекается git — только `warn`, `git rm --cached` оставлен человеку.
- `check_hygiene` (`mcpconfig.py:150–168`): read-only снимок, диагнозы `tracked-in-git` /
  `missing-example`, только claude-канал.
- Umbrella-состояние: `.mcp.json`, `.mcp.json.example` (плейсхолдеры `<HOME>`,
  `<ABS_PATH_TO_PROJECT>`) и `.mcp.json.bak` присутствуют — то есть эмиссия здесь уже
  выполнялась вручную/при включённом флаге.

## 8. Границы этого замера (что НЕ проверено)

- Резидентная цена tool-search-режима **не измерена изнутри клиента**: агент не видит
  `/context` (пользовательская команда), поэтому фактическая стоимость «имена + инструкции
  сервера» здесь взята из документации, а не с прибора. Калибровка — предмет item'а P2.3.
- Замер сделан по четырём проектам, не по всему флоту (полный обход — обязательство P1.2).
- Разбор хаб-блока сделан по трём проектам с блоком и трём без него; почему у cms/insiders/
  diabox блока нет (не раскатывали / Boost-режим / ручное удаление) — **не выяснено**.
- `estimate_tokens` (`budget.py:54–64`) — эвристика (кириллица ~2.9 симв/ток, латиница ~3.4),
  а не токенайзер клиента; все числа выше сопоставимы между собой, но не равны биллингу.

## 9. Пере-проверка соседних допущений измерителя (после находки §5.1)

Находка про tool search — это класс ошибки «статическая модель поведения клиента устарела».
Соседние допущения `budget.py` перепроверены тем же способом:

- **Модель листинга скиллов — подтверждена.** RAG:✅ 2026-07-31
  `https://code.claude.com/docs/en/skills` §Troubleshooting «Skill descriptions are cut short»:
  клиент режет описания под символьный бюджет листинга, бюджет **масштабируется от
  контекстного окна модели**, описания отбрасываются начиная с реже вызываемых. Совпадает с
  `_listing_entry_tokens` (кап 1 536) + `min(raw, context_window × fraction)` (`budget.py:243,
  349–351`). Второй источник (perplexity-web, 2026-07-31) даёт те же имена параметров
  (`skillListingMaxDescChars` 1 536, `skillListingBudgetFraction` дефолт 0.01).
- **Нативный листинг покрывает и проектные, и плагинные скиллы.** RAG:✅ 2026-07-31
  `https://code.claude.com/docs/en/features-overview` §«Skills» + perplexity-web: имя+описание
  каждого доступного скилла резидентны на старте, тело — по вызову; `disable-model-invocation:
  true` даёт нулевую резидентную цену. **Это основание вывода §2**: перечисление скиллов
  внутри `CLAUDE.md` — второй платный экземпляр того, что клиент уже показывает сам.
- **Официальное подтверждение отложенности MCP** (третий источник к §5.1): та же страница
  §«Context cost by feature» — «MCP servers load tool names at session start and full schemas
  on demand».
- **У клиента есть собственный оценщик контекста** — `/doctor` (RAG:✅ 2026-07-31, там же,
  §«Skill descriptions are cut short»: «estimate the context cost and identify major
  contributors using `/doctor`»), а предупреждения о превышении бюджета листинга пишутся в
  debug-лог при `--debug`. Это пользовательская команда (агенту не видна), но она —
  доступный владельцу **прибор для калибровки** наших оценок.
- **Не перепроверено внешне** (осталось допущением кода): цена `.claude/agents` (только
  `name`+`description`, `budget.py:361`) и то, что `SessionStart`-хуки резидентны ровно своим
  stdout (`:458`).
