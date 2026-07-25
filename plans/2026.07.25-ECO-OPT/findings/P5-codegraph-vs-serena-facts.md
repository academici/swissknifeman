# P5 — фактический вход пилота code-review-graph vs Serena (слой 1, 2026-07-25)

Захват в день получения (§16 immediate-capture). Дисциплина: метаданные репо — GitHub API;
содержимое репо — `raw.githubusercontent.com` (дословные цитаты); поведение Claude Code —
first-party дока; полевая практика — perplexity-web. Классы фактов заданы ДО поиска —
`research/07-P5-fact-classes.md`.

---

## §1. Метаданные и зрелость репозитория (GitHub API, 2026-07-25)

```
full_name        tirth8205/code-review-graph
description      Local-first code intelligence graph for MCP and CLI…
stars            26 300      forks 2 458      open_issues 116
language         Python      license MIT
created_at       2026-02-26  pushed_at 2026-07-25  archived false
homepage         https://code-review-graph.com
size             12 327 KB   default_branch main
```

Релизы (последние 5): `v2.3.7` (2026-07-18) · `v2.3.6` (2026-06-10) · `v2.3.5` (2026-05-25) ·
`v2.3.4` (2026-05-25) · `v2.3.3` (2026-05-08). Теги SemVer есть — **версия пиннуема**
(важно: наш Serena так и пиннована, `SERENA_SRC = git+…@v1.5.3`).

Возраст на дату захвата — **5 месяцев** (создан 2026-02-26). 116 открытых issues;
внутренний документ `docs/MAINTAINER_RECONCILIATION_2026-07-17.md` описывает разбор
«104 открытых PR / 84 открытых issues / 29 обсуждений» и прямо называет ветку
«deliberately narrow reconciliation … not a release branch»: поток контрибуций
превышает пропускную способность мейнтейнера — это риск-класс «молодой популярный
проект», а не «стабильная инфраструктура».

## §2. Рантайм, установка, операционная цена (pyproject.toml v2.3.7 + README)

- `requires-python = ">=3.10"`; классификаторы 3.10–3.13; `Development Status :: 4 - Beta`.
- Обязательные зависимости: `mcp>=1.0.0,<2`, `fastmcp>=3.2.4,<4`, `tree-sitter>=0.23.0,<1`,
  `tree-sitter-language-pack>=0.3.0,<1`, `pyyaml`, `networkx>=3.2,<4`, `watchdog>=4.0.0,<7`
  (+`tomli` для 3.10). Опциональные экстры: `embeddings` (sentence-transformers+numpy),
  `google-embeddings`, `communities` (igraph), `eval` (matplotlib), `wiki` (ollama).
- Комментарий в самом `pyproject.toml`: `fastmcp>=3.2.4` требуется в том числе ради
  «CVE-2025-62800/62801/66416 fixes», а верхняя граница `<4` — «prevents the next major
  release from breaking the server the way fastmcp 3.0 did». То есть у зависимости уже была
  ломающая мажорка и были CVE.
- Установка: `pip install code-review-graph` / `pipx install` / `uvx` (README «Quick Start»):
  «Requires Python 3.10+. For the best experience, install uv … the MCP config will use `uvx`
  if available».
- Точки входа: `code-review-graph` (CLI+MCP `serve`) и `crg-daemon` (мульти-репо watcher).
- Хранилище: «SQLite file in `.code-review-graph/`. Core graph storage needs no external
  database or cloud service»; в git-репо индексируются только tracked-файлы (`git ls-files`),
  исключения — `.code-review-graphignore`.
- Производительность (README): начальный build «~10 seconds for a 500-file project»;
  инкремент «A 2,900-file project re-indexes in under 2 seconds» через SHA-256 diff.
- **`code-review-graph install` — не только `.mcp.json`.** README: «installs platform-native
  hooks/skills where supported, and **injects graph-aware instructions into your platform
  rules**». Для Claude Code это означает запись хуков, скиллов (`skills/` в репо — 7 штук:
  build-graph · debug-issue · explore-codebase · refactor-safely · review-changes ·
  review-delta · review-pr) и правку правил проекта — то есть **новый always-on инжект**
  в терминах нашей рамки (CLAUDE.md § «Рамки»: гейт `skiller budget --first-turn`).
- Симметричный `uninstall` есть, с `--dry-run`, атомарной заменой и обещанием не трогать
  чужие MCP-серверы/хуки/скиллы.
- Телеметрии нет: «No. There is zero telemetry… The streamable-HTTP MCP transport binds to
  localhost by default». Сеть только opt-in: локальные эмбеддинги тянут модель с HuggingFace;
  облачные эмбеддинги отправляют «currently function signatures» провайдеру, с egress-предупреждением
  и `CRG_ACCEPT_CLOUD_EMBEDDINGS=1`. (`docs/FAQ.md` § «Does it phone home?»)

## §3. Заявка «медиана ~82×» — что именно измерено (README § Benchmarks + docs/REPRODUCING.md)

Дословно README:

> **Headline number: the median per-question token reduction across the 6 repos is ~82x**
> (whole-corpus baseline vs graph query). The frequently quoted **528x is the maximum** —
> a single best-case repo (fastapi) — not the typical result.

Таблица (6 репо, пиннованные SHA, 5 вопросов на репо):

| Repo | naive_corpus_tokens | avg graph_tokens | Reduction |
|:--|--:|--:|--:|
| fastapi | 951 071 | 2 169 | 528.4× |
| code-review-graph | 208 821 | 2 495 | 93.0× |
| gin | 166 868 | 1 990 | 91.8× |
| flask | 125 022 | 1 986 | 71.4× |
| express | 135 955 | 3 465 | 40.6× |
| httpx | 89 492 | 2 438 | 38.0× |

**Метод назван автором и им же дисквалифицирован как реалистичный baseline:**

> The whole-corpus baseline above is an upper bound no real agent pays: a competent agent
> greps for identifiers and reads only the best-matching files.

В репо **четыре разных «токен-бенчмарка»**, отвечающих на разные вопросы
(`docs/REPRODUCING.md` § «Which benchmark measures what»):

| Бенчмарк | Baseline | Цена графа | Вопрос |
|:--|:--|:--|:--|
| `eval/benchmarks/token_efficiency.py` | контент изменённых файлов коммита | полный `get_review_context()` JSON | дешевле ли графа, чем прочитать дифф |
| `eval/benchmarks/agent_baseline.py` | **grep top-3 файла** по идентификаторам вопроса | 5 search-хитов + до 5 соседних рёбер | дешевле ли графа, чем реалистичный grep-агент |
| `eval/token_benchmark.py` | нет — абсолютная цена | сумма 5 MCP-ответов | сколько стоит полный workflow |
| `token_benchmark.py` (standalone) | **все исходники репо** | те же 5+5 | дешевле ли, чем прочитать весь репо |

Ключевые следствия, зафиксированные автором:

> The `eval/benchmarks/token_efficiency.py` numbers can be **less than 1.0×** for small commits
> (`get_review_context` carries impact-radius metadata and source snippets, which outweigh a
> tiny changed-file set).

> No canonical capture exists yet [для `agent_baseline`]; numbers will be added to the canonical
> block above once captured — they are not quoted before being measured.

То есть **реалистичного baseline-числа (grep-агент) в публикации НЕТ** — есть только код
бенчмарка и обещание. Заявка 82× относится к baseline «прочитать весь репозиторий целиком».

Воспроизведение — команда есть:
`uv run code-review-graph eval --benchmark token_efficiency,impact_accuracy,agent_baseline,multi_hop_retrieval`
(«roughly 8–15 minutes for the build phase» на M1/M2). Детерминизм заявлен: пиннованные SHA,
фиксированный seed Leiden, CPU-эмбеддинги. Есть еженедельный report-only CI на двух самых
маленьких конфигах. Отдельно задокументированы два исторических бага, при которых **упавший
вызов выглядел как победа** (`graph_tokens=0` → ratio `naive/1`; упавший `analyze_changes`
давал `predicted = changed` и recall 1.0) — сейчас исправлены, есть регресс-тесты.

Оценка `context_savings` в ответах инструментов (с v2.3.4) и панель `Token Savings` в CLI
(v2.3.5) сверяются флагом `--verify` с `cl100k_base` (**токенайзер GPT-4, не Claude**);
заявленная точность — «within ~1% of real GPT-4 tokens in aggregate across 222 sample files».

## §4. Точность против LSP и multi-hop (README § Limitations + docs/FAQ.md)

Impact-accuracy (13 коммитов, 6 репо): **avg F1 0.714, avg precision 0.578, recall 1.000**.
Recall дисквалифицирован автором дословно:

> Blast-radius analysis recovers every file in the ground truth on all 13 evaluation commits —
> **but read that as an upper bound, not as "100% recall"**: in this mode the ground truth
> (changed files + files with call/import edges into them) is derived from the same graph the
> predictor traverses, so it is circular by construction.

Честный режим (`co-change`: сверка с файлами, реально изменёнными в том же коммите) в коде
есть, колонка `ground_truth_mode` в CSV есть, **но чисел нет**: «Co-change numbers will be
added … once captured by the eval runner; we do not quote them before measuring», и ожидание
автора — «expect those numbers to be substantially lower».

Прочие названные слабости (README § Limitations and known weaknesses):
- «**Small single-file changes:** Graph context can exceed naive file reads for trivial edits».
- «**Search quality (MRR 0.35):** … ranking needs improvement. Express queries return 0 hits
  due to module-pattern naming».
- «**Flow detection (33% recall):** … strongest for Python and PHP/Laravel. JavaScript and Go
  flow detection needs work».
- «**Precision vs recall trade-off:** Impact analysis is deliberately conservative».

Multi-hop-бенчмарк (`eval/benchmarks/multi_hop_retrieval.py`): **0.909 на 11 hand-curated
задачах, 6 репо, 10/11 pass** — но задачи курировал сам автор, и в том же документе описано,
как «score went from 0.545 to 0.909 (the same-day fix)».

**Прямое сравнение с LSP — словами автора** (`docs/FAQ.md` § «How is this different from LSP»):

> If you need a *provably complete* reference list for one symbol in one language, an LSP
> server is the gold standard and CRG does not try to replace it.
> …
> **The honest trade-off:** CRG's call resolution is AST-level and heuristic, not
> compiler-backed. Dynamic dispatch, metaprogramming, and duck typing can produce inferred or
> ambiguous edges — which is exactly why every edge carries a confidence tier
> (`EXTRACTED` / `INFERRED` / `AMBIGUOUS`). LSP is more precise per symbol; CRG is broader,
> persistent, and cheaper to query across the whole repo.

Про Serena отдельной строкой (§ «How does it compare to Serena, codegraph, claude-context,
repomix»): Serena — «LSP-backed symbol retrieval and editing tools over MCP», «General coding-agent
toolkit, not review-specific»; рекомендация автора: «if you want symbol-precise *editing* tools,
Serena's LSP approach is a better fit».

Где граф выигрывает по его же формулировке — **многошаговые структурные вопросы**: impact
radius, callers-of-callers, `tests_for`, affected flows («has no grep equivalent at all»).
Где НЕ стоит применять (§ «When should I not use it?»): репо меньше нескольких сотен файлов;
тривиальные однофайловые правки; разовые вопросы к репо, куда не вернёшься; flow-detection на
JS/Go. Порог полезности: «A few hundred to a few thousand files: this is where the benchmarks
live»; «Multi-thousand-file repos and monorepos: the strongest case». Второй ось — частота
multi-file вопросов: «A 300-file repo you review daily benefits more than a 3,000-file repo
you touch once».

## §5. PHP/Laravel-покрытие (README § Features)

> PHP projects additionally get repository-bounded Composer PSR-4 resolution, Blade template
> references, and Laravel Route/Eloquent semantic edges …
> **evidence-gated** Laravel Route-to-controller and Eloquent relationship edges

Flow detection «strongest for Python and PHP/Laravel». Языковое покрытие — ~35 языков + ноутбуки;
Vue/Svelte SFC и Astro — через TS-парсер. Кастомный язык добавляется `languages.toml` в
`.code-review-graph/` без форка.

Слово **evidence-gated** означает включение Laravel-семантики только при доказуемых признаках
фреймворка; динамическая магия (фасады, `resolve()`, макросы) под это описание не подпадает —
это вывод из формулировки, не утверждение автора: `[UNVERIFIED]` до пилотного замера на нашем
laravel-проекте.

## §6. Цена резидентного MCP в Claude Code — first-party (code.claude.com/docs/en/mcp, 2026-07-25)

Премиса «+1 резидентный MCP = +30 схем инструментов в каждом запросе» **опровергнута дословно**:

> **Tool search keeps MCP context usage low by deferring tool definitions until Claude needs
> them. Only tool names and server instructions load at session start**, so adding more MCP
> servers has minimal impact on your context window. Claude Code doesn't impose a fixed
> per-server tool cap; the practical limit is your context window budget.

> Tool search is **enabled by default**. MCP tools are deferred rather than loaded into context
> upfront… **Only the tools Claude actually uses enter context.**

Сопутствующие факты того же раздела:
- Обрезка: «Claude Code truncates **tool descriptions and server instructions at 2KB each**».
- Режимы `ENABLE_TOOL_SEARCH`: `(unset)`=всё отложено · `true` · `auto` (грузить сразу, если
  влезает в 10% контекста) · `auto:N` · `false` (всё сразу).
- Отключается принудительно `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` (и `ENABLE_TOOL_SEARCH`
  это не перебивает); выключен по умолчанию на Google Cloud Agent Platform и при
  `ANTHROPIC_BASE_URL` на не-first-party хост.
- Требует модель с поддержкой `tool_reference` (Sonnet 4.5 / Haiku 4.5 / Opus 4.5 и новее).
- `alwaysLoad: true` у сервера — исключение из отложенной загрузки: «Every tool from that server
  then loads into context at session start… **each upfront tool consumes context**»; плюс
  «Setting `alwaysLoad: true` also blocks startup until the server connects, capped at the
  standard 5-second connect timeout».
- Лимиты вывода (совпадает с §3 findings P3): warning >10 000 токенов, дефолт 25 000
  (`MAX_MCP_OUTPUT_TOKENS`), per-tool `anthropic/maxResultSizeChars`.

**Следствие для замера P5.1:** резидентная цена сервера при дефолтных настройках — имена
инструментов + server instructions (≤2KB), а не 30 полных схем; зато появляется цена
**ToolSearch-раунда** и цена ответов инструментов внутри задачи. Наш измеритель
`skiller budget --first-turn` (`_measure_mcp`) считает EAGER-потолок — это верхняя граница,
а не факт резидента (это уже зафиксировано в скилле `mcp-advisor` § «Прополка», п. 3).

## §7. Полевая практика: как честно мерить (perplexity web+social, 2026-07-25)

Консенсус практики 2026 по замеру graph-MCP:
1. **Baseline — не «голый grep», а grep+read** (реальная альтернатива агента); сравнивать
   при фиксированных модели, промпте, наборе задач и версиях инструментов, меняя ТОЛЬКО
   провайдер контекста.
2. **Считать per-task, а не per-question**: полная стоимость задачи от старта до ответа,
   включая tool calls, повторные чтения и неудачные ходы. Per-question годится только для
   локальной диагностики интерфейса инструмента.
3. **Стратифицировать задачи**: точечный lookup · структурный graph-query · hard
   impact/disambiguation. Усреднение по простым вопросам маскирует эффект (и наоборот).
4. **Рядом с токенами мерить качество**: точность финального ответа по эталону, completion
   rate, F1 для set-задач (полнота+шум), отдельно состав impact radius. «Граф может быть очень
   дешёвым, но если он возвращает многословный контекст или ведёт агента не туда, экономия
   токенов не означает пользы».
5. Наблюдаемая картина: на простых вопросах разница по качеству почти нулевая (решает цена и
   число вызовов); LSP выигрывает на symbol-precise доступе и правках; граф — на «что сломается,
   если я изменю это» и на снижении числа round-trip'ов.

**Независимых полевых отчётов и сторонних бенчмарков по code-review-graph не найдено** —
поиск возвращает сам репозиторий и его документацию. Для проекта возрастом 5 месяцев это
ожидаемо, но означает: ВСЕ публичные числа — самозамер автора, и вердикт P5.2 обязан
опираться на наш собственный замер, а не на README.

## §8. Альтернативы того же класса (perplexity + FAQ автора, 2026-07-25)

Названные соседи: **Serena** (LSP-backed, наш текущий канон), **codegraph** (AST/call-graph
индексация над MCP; имя носят несколько разных проектов), **claude-context** (chunk+embed
семантический поиск, требует вектор-БД и провайдера эмбеддингов), **repomix** (упаковка репо
в один файл, Node.js, без структурных запросов). Отдельного независимого лидера класса
«graph-retrieval MCP под ревью» в выдаче нет — рынок не консолидирован.
Вывод для P5.2: вердикт формулируется как «CRG vs Serena vs комбинация vs ничего», и ложной
дихотомии «или CRG, или Serena» в D-логе быть не должно, но **разведка новых кандидатов —
не скоуп этой фазы** (репо названы, чтобы вердикт их не игнорировал).

---

## Сводка: что разведка изменила в постановке P5

1. **82× нельзя использовать как ожидание.** Автор сам называет baseline «upper bound no real
   agent pays», а реалистичный `agent_baseline` **не опубликован числами**. Ожидание пилота —
   не «×82», а «сколько-то на multi-hop и, возможно, <1× на мелких диффах».
2. **Премиса «дорогой резидент» опровергнута first-party.** Tool search включён по умолчанию,
   резидентны только имена + server instructions ≤2KB. Значит замер «а» контракт-блока
   (`budget --first-turn` до/после) меряет ВЕРХНЮЮ границу, а не факт; настоящая цена
   переезжает в per-task стоимость и ToolSearch-раунды.
3. **Реальный always-on риск — не тулы, а `install`:** он пишет хуки, 7 скиллов и правит
   правила платформы. Вот это и обязано проходить наш гейт `skiller budget --first-turn`.
4. **Точность: LSP строго точнее per-symbol по признанию автора**, граф выигрывает на
   impact/multi-hop; F1 0.71 круговой, co-change-чисел нет. Значит «заменить Serena» — не
   рассматриваемый вариант; рассматриваются combine и skip.
5. **Наш флот попадает в «слабую» зону по размеру.** Порог пользы по автору — от нескольких
   сотен файлов и частые multi-file вопросы; часть наших пакетов заметно меньше.
