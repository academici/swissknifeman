# Разведка поверхностей фазы P5 + RAG по supply-chain скану скиллов (слой 1)

**Слой 1 (сырьё).** Прямые проверки автора плана + RAG-ступень `perplexity-web`, 2026-07-31,
дерево `main` (чисто). Все репо-числа — с якорями `file:line`; все внешние факты — с URL,
датой и вердиктом. Потребитель: фаза **P5** (все девять items).

> Дисциплина: это сырьё. Синтез — `research/05-p5-hygiene-model.md`, решения — D-лог.

---

## 1. RAG: supply-chain скан сторонних скиллов — класс угрозы и метод (вход P5.1)

**Запрос 1** (2026-07-31, `perplexity-web/search_advanced`, sources=web): «supply chain security
scanning of third-party AI agent skills / MCP servers 2026: prompt injection detection in markdown
skill files, IOC scanning, published methods and tools».

**Запрос 2** (2026-07-31, тот же канал): «Does Anthropic ship a first-party skill scanner? What
does its Agent Skills security guidance mandate? What did CSA research say about skill scanner
bypass?».

### 1.1 Классы угрозы (внешний факт, верифицирован)

RAG:✅ 2026-07-31 <https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills>
+ <https://www.heeler.com/resource/introducing-agent-skills-security-identify-and-prevent-risk-in-the-ai-agent-supply-chain>
— заявляемые в 2026 классы для пакета «SKILL.md + вложенные файлы/скрипты/ресурсы»:

1. **prompt injection** (в т. ч. «skill-based prompt injection» — payload внутри доверенного
   артефакта, спрятанный в прозе, комментариях, фенсах);
2. **data exfiltration** (webhook/remote endpoints, сбор env-переменных);
3. **malicious code execution** (shell/python/js-пути, subprocess-цепочки, base64-обфускация);
4. **over-permissive tool use** (скилл требует прав шире своего назначения).

### 1.2 Официальная позиция Anthropic (внешний факт, верифицирован)

RAG:✅ 2026-07-31 (тот же engineering-пост + platform-доки Agent Skills, §Security considerations):
**первопартийного сканера НЕТ.** Предписание — «install only from trusted sources; если источник
менее доверенный — **thoroughly audit it before use**»: читать содержимое ВСЕХ файлов бандла
(скрипты, зависимости, изображения, ресурсы), особо отмечая инструкции/код, обращающиеся к
внешним сетевым источникам, и «unusual patterns — unexpected network calls, file access patterns,
operations that do not match the skill's stated purpose».

**Следствие для плана:** модель проверки, которую предписывает апстрим, — **человеческий аудит
бандла**, а не сканер. Сканер может быть только вспомогательным триажем.

### 1.3 Сканер НЕ является границей безопасности (внешний факт, верифицирован)

RAG:✅ 2026-07-31 <https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/>
(CSA research note по данным Trail of Bits, июнь 2026): «AI Agent Skill Scanners: Bypassed Across
the Board» — обойдены сканеры **ClawHub, Cisco, skills.sh** простыми приёмами: whitespace
inflation, precompiled bytecode hiding, archive indirection, prompt-style social engineering для
LLM-as-judge ступени. Вывод CSA дословно: **«Don't outsource trust to a scanner»**; рекомендация —
считать marketplace-скиллы недоверенным кодом, **пиновать версии** и добавлять runtime-контроль,
а не полагаться на pre-install скан.

### 1.4 Существующий open-source ориентир (внешний факт, верифицирован)

RAG:✅ 2026-07-31 <https://github.com/cisco-ai-defense/skill-scanner> — комбинирует YAML/YARA-сигнатуры,
поведенческий dataflow-анализ, LLM-as-a-judge и опциональные облачные интеграции; собственная
документация подчёркивает: «no findings ≠ safe». Пригоден как **источник паттернов**, но не как
зависимость: `root.engineering-invariants` (`packages/harness/configs/common/instructions/root/common.md:19`)
запрещает pip/npm runtime-зависимости и предписывает «take external code as a pattern and rewrite
it, never as a runtime dependency».

### 1.5 `[UNVERIFIED]`-границы

- Публичного списка IOC именно по кампаниям вредоносных **Agent Skills** (а не MCP-серверов)
  автор плана не нашёл; «известные IOC-листы» в источниках упоминаются обобщённо. Значит, наш
  первый набор правил будет **паттерновым** (сеть/шелл/обфускация/инструкции-перехваты), а не
  IOC-листовым; заявлять «IOC-скан» без списка — самообман.
- Влияние обхода-техник Trail of Bits (whitespace inflation, bytecode) на НАШУ раскладку
  (markdown + опциональные `snippets/`) не измерялось.

---

## 2. Вендоренные скиллы и существующая сверка (вход P5.1)

- **56** файлов `upstream.json` (не 54 из оценки брифа) — `findings/repo-recon-2026-07-31.md` §5.
- Схема (живой пример): `schema_version`, `source`, `repo`, `strategy`, `license`, `files[]{path,
  url, sha256, fetched_at}`, опц. `body_path`, `notes`.
- **Стратегии — четыре, не три:** `--help` `packages/skiller/scripts/update-upstreams.sh:33–43`
  перечисляет `replace` · `notify` · `fork` · **`merge`** (у `fork`/`merge` есть состояние
  `review_pending` + `last_review`, снимается режимом `--resolve`).
- **Режимы:** `--check` (дефолт, read-only) · `--apply` · **`--resolve`**; коды выхода
  `:14–19`: `0` ок · `1` usage/битый json · `2` fetch-сбои · **`10`** — найден update/notify/conflict.
- Флаги: `--skill PATH` (повторяемый), `--force`, **`--json`** (машинный вывод в stdout, человеческий
  в stderr), `--timeout SEC`.
- **Чего НЕТ:** любой проверки СОДЕРЖИМОГО — только целостность байтов против апстрима.
- Потребители провенанса: `packages/skiller/lib/skiller/registry.py:66–85` (битый JSON → `die` `:74`),
  `common.py:41` (`SKILL_IGNORE` — `upstream.json` не копируется в проект),
  `vendor.py:214,291`, `packages/skiller/lib/skiller/quality/eval.py:973,978`,
  `packages/skiller/scripts/check-translations.sh:75`
  (внешние освобождены от RU-паритета).

**Ключевое наблюдение.** `--check` ловит **дрейф** (апстрим изменился), но НЕ ловит того, что
вендорилось изначально: первичный контент никем содержательно не читался. Это и есть «Пробел Б»
аудита в точной формулировке.

---

## 3. `configs/provider-capabilities.json` — почему провенанс нельзя положить в сам файл (вход P5.2)

- Подтверждено повторно: генератора нет, файл рукописный; `scripts/provider-docs.py` генерирует
  доки **ИЗ** него (`GUIDE_PATH = ROOT / "docs/provider-support.md"` `:23`, режимы `--write` `:323` /
  `--check` `:324`, `expected_outputs()` `:276`, цели — `README.md`-блок + `docs/provider-support.md` `:297`).
- Топ-уровневые ключи ровно пять: `capabilities`, `catalog_version`, `contract_version`,
  `native_extensions`, `providers`.
- **Схема СТРОГАЯ по неизвестным ключам:** `core/provider_manifest.py:536–541` `_exact_keys(...)`
  выдаёт `MANIFEST_SCHEMA_INVALID … "unknown field"` на любой ключ вне ожидаемого набора.
  ⇒ Добавить `_provenance`/`_comment` внутрь манифеста **нельзя** без правки парсера в `core/`
  (а `core/**` — поверхность P6, и это замороженный контракт).
- Каталога `configs/` кроме этого файла нет (`ls configs/` → один файл, README отсутствует).
- Генерируемый гайд уже несёт строку-провенанс о СЕБЕ: `scripts/provider-docs.py:179`
  — «> Generated by `python3 scripts/provider-docs.py --write`; do not edit manually».
  Про сам МАНИФЕСТ такой строки нет нигде.
- Канон, к которому файл ошибочно применяют: `root.generated-artifacts`
  (`packages/harness/configs/common/instructions/root/common.md:46–47`; запись каталога —
  `catalog.json:480–500`, `obligations[0].object = "root.generated-artifacts.requirements"`).

---

## 4. `*.env.ini` — это НЕ разрозненные локальные конфиги (вход P5.3)

Инвентаризация (`find . -name "*.env.ini"`), 2026-07-31:

| Файл | В git | Кто пишет | Кто читает |
|:--|:--|:--|:--|
| `.claude/auto-approve.env.ini` (`MODE=bypass`) | нет (`.gitignore:14`) | `packages/harness/lib/harness/hooks.py:841` | `configs/claude-code/hooks/auto-approve/lib/common.sh:27–30` |
| `.claude/memory.env.ini` (`MODE=maind`) | нет (`.gitignore:16`) | `packages/harness/lib/harness/hooks.py:864` | `packages/harness/configs/claude-code/hooks/memory/lib/common.sh:21`; `maind/health.py:61–66`; `maind/provision/sync.py:245–258` |
| `.claude/run-report.env.ini` (`ENABLED=on`, `RUNS_KEEP=30`) | **ДА, трекается** | `harness/hooks.py:893–901` | `configs/claude-code/hooks/run-report/run-report.py:31–37` |
| `packages/skiller/.claude/auto-approve.env.ini` | нет | вручную/`hooks.py` | тот же хук, per-project override |
| `configs/claude-code/agent-packs/*/hooks/review-gate.env.ini` ×4 | **ДА** | раздаётся agent-pack'ом | хук пакета |
| `configs/claude-code/hooks/*/env.ini` ×5 (`agent-router`, `auto-approve`, `changelog-gate`, `memory`, `observer`) | **ДА** | шаблон раздачи | те же хуки, как дефолт-слой |
| `.codex/memory.env.ini` | — | `packages/harness/lib/harness/hooks.py:365` | Codex-ветка |

**Вердикт по факту:** это спроектированный носитель **интента хука per-project** с явной
лестницей приоритета (`$CLAUDE_PROJECT_DIR/.claude/<hook>.env.ini` → `<hookdir>/env.ini`,
`auto-approve/lib/common.sh:27–30`), а не «разрозненные локальные конфиги». Предпосылка аудита §6
(«вероятно, локальные незакоммиченные конфиги, дублирующие `~/.swissknifeman/config.json`») —
**неверна**: `~/.swissknifeman/` содержит `projects.json`/`topology.json`/`memory/` (реестр флота),
файла `config.json` там сегодня нет вовсе (`ls ~/.swissknifeman/`), а `config.example.json` в корне
монорепо — шаблон конфига **узла maind** (ключи `node/memory/graph/code_graph/agents/namespaces/
projects/integrations/mcp/observability`), не хуковый интент.

**Реальные находки инвентаризации (а не гипотеза аудита):**

1. **Непоследовательность трекинга:** `run-report.env.ini` закоммичен, `auto-approve`/`memory` —
   в `.gitignore`. Один класс файлов, три разных судьбы.
2. Носитель формата — самописный парсер `KEY=VALUE` в четырёх местах
   (`common.sh` ×2, `run-report.py:31–37`, `health.py:61–66`), схемы нет.

---

## 5. Провенанс модели в плане — что УЖЕ есть (вход P5.4)

Три носителя существуют:

1. `plan.md` `## 0. Meta` → `Authoring Model` (весь план целиком);
2. `plan.md` `## 6. Update Log` → колонка-литерал **`Дата | Кто (role/model) | Что`**
   (`SKILL.ru.md:1400` — `i18n-keep`), то есть провенанс на КАЖДЫЙ заход дизайна;
3. `journal.jsonl` → обязательное поле **`actor`** (`packages/task/lib/task/journal.py:47–50`,
   14 обязательных полей) на каждое исполнение item'а, плюс routing-adherence строка в
   Completion Notes (`plan-protocol` §13, D75).

**Чего нет:** правила В КАНОНЕ, которое бы это требовало, и любого гейта.
`root.plan-lifecycle` (`root/common.md:22–23`) о провенансе модели молчит.

⇒ Предпосылка аудита §5 «каждый план должен фиксировать, какая модель спроектировала часть»
**в основном уже выполнена механикой**, но не заявлена как обязательство.

---

## 6. Видимость служебных файлов сторонним провайдерам (вход P5.4)

- Корневые dot-каталоги существуют: `.agents/{plugins,skills}`, `.claude/`, `.codex/`.
- Канон уже описывает `.agents/skills/*` как тонкие ГЕНЕРИРУЕМЫЕ проекции
  (`root/codex.md:1–3`, `root.codex.bootstrap`), а SSOT — `packages/skiller/skills/` и
  `packages/task/commands/`.
- Codex-ветка канона несёт четыре секции: `bootstrap`, `launch-and-hook-integrity`,
  `fresh-agent-execution`, `package-scope-routing` (`root/codex.md`).
- `root.codex.package-scope-routing`: «Project docs are read root→cwd and never past the
  repository root» — то есть **чтение доков ограничено деревом**, служебные каталоги ПЛАНА
  (`plans/<ID>/{root,brief,findings,research}`) под это правило не подпадают и в каноне не
  названы ни разу.
- `AGENTS.md` корня несёт `root.plan-lifecycle` (`AGENTS.md:41–43`) — но он говорит только
  «плану жить в `plans/<ID>/`», не о слоях знаний.
- **Живой Codex CLI доступен:** `codex-cli 0.146.0` (`command -v codex` → `~/.local/bin/codex`)
  ⇒ измерение видимости холодной Codex-сессией выполнимо в этом репозитории, а не гипотетично.

---

## 7. Playwright MCP — точная точка правки (вход P5.6)

Три носителя аргументов, все с `@latest` и без `--output-dir`:

- `packages/harness/configs/claude-code/mcp/playwright.json:3` — `"args": ["@playwright/mcp@latest", "--headless"]`
- `packages/harness/configs/claude-code/mcp/bindings.json:13` — `{"command": "npx", "args": ["@playwright/mcp@latest", "--headless"]}`
- `packages/harness/configs/codex/mcp/bindings.json:13` — то же самое для Codex

Каталог: `packages/harness/configs/common/mcp/catalog.json:10` —
`{"id": "playwright", "transport": "stdio", "capability_id": "mcp.catalog", "secret_refs": []}`.
Дополнительно `packages/harness/configs/claude-code/settings.global.json:50` — `mcp__playwright` в permissions.

⇒ Правка ОДНОЙ строки шаблона, как обещал roadmap, — неточность: строк **три** (два провайдера),
и паритет провайдеров обязателен (`root.provider-parity`, `root/common.md:34–35`).

---

## 8. `apply_instructions` — точные якоря на живом дереве (вход P5.7)

Перепроверено 2026-07-31 (roadmap-запись писалась на другом дереве, номера строк сместились):

- `apply_instructions` — `packages/harness/lib/harness/instructions.py:402–421`;
  позиционная сверка — **`:414`**: `tuple(action.target_path for action in writable) !=
  request.authorized_target_paths`;
- отказ — **`:415`**: `_write_refusal(request, fresh, "authorized missing/create or
  stale-source/update targets")` (текст НЕ называет ожидаемый порядок);
- соседняя сверка МНОЖЕСТВОМ в `adopt_instructions` — **`:477–480`**: `conflicts = {...}`;
  условие `not request.authorized_target_paths or len(set(...)) != len(...) or any(path not in
  conflicts ...)` → порядок не важен, дубли ловятся;
- код отказа `INSTRUCTION_WRITE_FORBIDDEN` объявлен `:101`; прочие вызовы `_write_refusal` —
  `:421,439,446,450,470,480,484,486`.

Порядок, которого требует `:414`, — порядок `fresh.artifact_plan.actions`, на практике
**алфавитный по `target_path`** (два воспроизведения — `roadmap/instruction-authorize-order.md`
§«Почему больно»; авторитетная формулировка — D84 плана `2026.07.29-HARNESS-AGNOSTIC`).

---

## 9. Launch-block: что именно гейтит линтер сегодня (вход P5.8)

- Регекс строки таблицы — `packages/task/lib/task/plan_lint.py:174–175`:
  `LAUNCH_TABLE_ROW_RE = re.compile(r"^\|\s*Model(?:\s+class)?\s*\|")` (принимает и `| Model |`,
  и `| Model class |`).
- Гейт `handoff.Next` — `:2068–2091`: требует **И** таблицу (`has_table`), **И** code-fence
  (`has_fence`); severity — ERROR для датовых планов от `BRIEF_CANON_DATE`, иначе WARNING;
  снимается литералом «план закрыт» (`:2078`).
- Гейт scope-payload в блоках `## Audit Pn` — `:1014–1052`: та же таблица + четыре строки
  `РЕЖИМ:/ВХОД:/СКОУП:/НЕ ТРОГАТЬ:` (`SCOPE_PAYLOAD_MARKERS`, `:817–845`).
- Носители канона: `packages/skiller/skills/general/plan-protocol/snippets/launch-block-template.md`
  (форма) + `SKILL.ru.md` §8 → генерируемый `SKILL.md` §8.
- Зеркала и фикстуры, которые придётся двигать синхронно: `packages/task/commands/plan-{design,exec,
  run,close,audit}.md` (5 файлов) · `packages/task/adapters/codex/skills/task-plan-*/` (5 из 11) ·
  golden-фикстуры `packages/task/tests/fixtures_data/claude-command-golden/commands/*.md` (11 файлов) ·
  `packages/skiller/adapters/codex/core/skills/general/plan-protocol/`.
- Двуязычный гейт: `packages/skiller/scripts/check-translations.sh --strict` уже стоит в
  `packages/skiller/scripts/validate.sh:1277`.

---

## 10. `plan-lint --conflicts`: что уже покрыто, а что нет (вход P5.9)

Roadmap просит «сверку трёх SSOT (`SKILL.ru.md` ↔ `SKILL.md` ↔ `plan_lint.py`)». Разложение по факту:

| Нога сверки | Покрыта? | Чем |
|:--|:--|:--|
| `SKILL.ru.md` ↔ `SKILL.md` (свежесть перевода) | **ДА** | `check-translations.sh` штамп `ru-source-sha256`, в `validate.sh:1277` |
| Непереводимые литералы (`i18n-keep`) — присутствие в EN **и** в теле RU | **ДА** (двусторонний с 2026-07-17) | `check-translations.sh:50,104,110,116` |
| Канон (`SKILL.ru.md`) ↔ реализация (`plan_lint.py`) — enum'ы и литералы | **НЕТ** | — |
| `--conflicts` как флаг CLI | **НЕТ** | `main()` `:2338–2352` знает только `path`, `--json`, `--baseline`, `--gate {all,new}` |

Реестры-константы, которые сегодня НЕ сверяются с каноном ни одним гейтом:
`STATUSES` `:52` · `TERMINAL_STATUSES` `:66` · `REQUIRED_ITEM_FIELDS` `:75` ·
формы `Next` `:128–142` (`NEXT_FORMS_HELP`) · `C2_RUNNABLE_KINDS` `:869` ·
`PHASE_HANDOFF_CLOSURE_LITERALS` `:238` · `PHASE_HANDOFF_NEGATION_LITERALS` `:249` ·
`CONSEQUENCES_LITERAL` `:640` · `LAUNCH_TABLE_ROW_RE` `:175`.
Директивы `i18n-keep` в `SKILL.ru.md:1397–1401` объявляют пять литералов —
`Поле | Значение`, `Items 🟢/всего`, `D# | Дата | Решение | Почему`,
`Дата | Кто (role/model) | Что`, `Контракт | Версия | Статус | Потребители | Уведомлены`,
плюс `Closure Protocol` `:836`.

**Прецедент, обосновывающий третью ногу** (репо знает его дословно): `check-translations.sh:16–21`
— «`<!-- i18n-keep: Вердикт: -->` объявлен, гейт plan-lint по нему реализован, RU литерал не
спелил — правило прожило до ближайшей регенерации, которая штатно и молча его удалила».

---

## 11. Codex publication — состояние гейта (вход P5.5)

- Рендереры: `packages/skiller/lib/skiller/publication.py` — `build_publication_catalog` `:137`,
  `render_claude_publication` `:221`, `render_codex_publication` `:327`,
  `validate_publication_capabilities` `:41`.
- Тесты, которые ЕСТЬ: `packages/skiller/tests/test_publication.py`,
  `test_codex_publication.py`, `test_provider_publication_parity.py` — статические сверки схемы.
- Гейт корневого marketplace в `packages/skiller/scripts/validate.sh:974–999`: наличие
  `.claude-plugin/marketplace.json`, `name == 'swissknifeman'`, `owner.name`, отсутствие дублей,
  соответствие плагинов каталогам на диске.
- **Чего НЕТ:** изолированного `CODEX_HOME`-прогона, install/cache-инвентаря, clean-consumer
  сессии — то есть ровно того, что перечисляет `roadmap/codex-publication-consumer-acceptance.md`
  §«Минимальный объём» пп. 3–4 и §7 (round-trip живым CLI).
- **Живой `codex` доступен:** `codex-cli 0.146.0` ⇒ п. 7 roadmap («round-trip живым прогоном
  второго провайдера») выполним локально; в CI — вопрос доступности бинаря, а не конструкции.
