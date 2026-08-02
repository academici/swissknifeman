# P5.1 — Человеческий аудит 56 вендоренных бандлов + провенанс правил триажа

**Дата аудита:** 2026-08-01 · **Дерево:** `packages/skiller/skills` на item-коммите P5.1 ·
**Исполнитель:** `plan-run`, opus/high · **Плановый адрес:** `2026.07.31-SKM-LEAN` P5.1.

Отчёт — ВХОД для гейта владельца **OQ-6** и провенанс набора правил триаж-ступени
(`packages/skiller/scripts/update-upstreams.sh --check`). Правила выведены ИЗ этой таблицы,
а не придуманы до чтения (Implementation Rule 6 item'а).

> **Дословно и обязательно к цитированию вместе с любым числом ниже:**
> **no findings ≠ safe.** Триаж-ступень — паттерновый скан, а НЕ граница доверия.
> RAG:✅ 2026-06 CSA/Trail of Bits, «AI Agent Skill Scanners: Bypassed Across the Board»
> (<https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/>):
> ClawHub, Cisco и skills.sh обойдены whitespace inflation, precompiled bytecode hiding,
> archive indirection и prompt-style social engineering LLM-ступени; вывод дословно
> «Don't outsource trust to a scanner». Первопартийного сканера Anthropic не поставляет и
> предписывает человеческий аудит бандла
> (<https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills>).
> Формулировка «находок нет, скиллы безопасны» в этом отчёте ЗАПРЕЩЕНА и нигде не употребляется.

---

## 1. Числа с якорем

| Число | Значение | Команда воспроизведения |
|:--|--:|:--|
| Бандлов (`upstream.json`) | **56** | `find packages/skiller/skills -name upstream.json \| wc -l` |
| Строк таблицы §4 | **56** | `grep -c "^| [0-9]" plans/2026.07.31-SKM-LEAN/findings/P5-vendored-audit.md` |
| Файлов в бандлах (без `upstream.json`) | **599** | `find packages/skiller/skills -name upstream.json \| xargs -n1 dirname \| while read d; do find "$d" -type f ! -name upstream.json; done \| wc -l` |
| Байт в бандлах | **3 070 592** | та же выборка, `-exec cat {} + \| wc -c` |
| Из них отслеживается `files[]`/`origins[]` | **2 537 197** | см. §5, скрипт провенанса |
| Файлов с исполняемым содержимым | **27** | `… ! -name '*.md' \| wc -l` (0 из них с executable-битом) |
| Вердиктов `clean` / `attention` / `risk` | **50 / 6 / 0** | `grep -c '\*\*clean\*\*'` / `'\*\*attention\*\*'` / `'\*\*risk\*\*'` по §4 |
| Находок триажа на живом реестре | **8** в **2** бандлах | `bash packages/skiller/scripts/update-upstreams.sh --check --json`, ключ `triage` |

Числа получены на дереве item-коммита; после `--apply` апстримов они меняются — это ожидаемо
и ровно то, что ловит отметка «вердикт протух» (§6).

## 2. Метод и его ГРАНИЦЫ (читать до таблицы)

Аудит двухслойный. Оба слоя названы честно, включая то, чего они НЕ покрывают.

**Слой A — сплошное машинное покрытие 100 % байтов (599/599 файлов).** По каждому файлу
извлечены и прочитаны ГЛАЗАМИ ЦЕЛИКОМ, без сэмплирования:

- все хосты/URL (агрегат по бандлам) — вектор data exfiltration;
- все HTML-комментарии (94 шт.) — носитель инструкции, невидимой в рендере;
- все код-фенсы, содержащие сеть/шелл/exec/base64/env (102 шт., ~2 800 строк) — вектор code execution;
- все строки-императивы, адресованные агенту (19 шт.) — вектор prompt injection;
- все объявления инструментов/прав во frontmatter (10 шт.) — вектор over-permissive tool use;
- сплошной неякорный поиск по 13 идиомам перехвата (`ignore previous`, `disregard`,
  `you are now`, `do not tell the user`, `system prompt`, …) — 21 попадание, все в одном файле (§3.2);
- детекторы обфускации: невидимые/форматирующие символы Unicode (Cf/Co/Cs), base64-подобные
  блобы ≥ 200 симв., строки > 400 симв., пробельные прогоны ≥ 40.

**Слой B — полное чтение глазами.** Прочитаны целиком: все **56** `SKILL.md` (291 КБ — тело,
которое агент реально грузит) и все **27** неразметочных файлов (68 КБ: 2 `.py`, 1 `.sh`,
5 `.ts`, 4 `.php`, 12 `.json`, `.xml`, `.txt`, LICENSE) — то есть весь исполняемый контур.

**ГРАНИЦА ПОКРЫТИЯ (named, не сымитирована).** Справочные корпуса — `references/**`,
`snippets/**.md`, `reference/**`, `workflows/**` (≈ 2,4 МБ, 447 файлов, из них 269 в одном
`vueuse-functions`) — **построчно глазами не читались**. Они покрыты Слоем A сплошь и точечным
чтением каждого попадания в контексте. Строгая формулировка вердикта для этих бандлов:
«по четырём заявленным классам угрозы и детекторам обфускации находок нет», а НЕ «файлы прочитаны
целиком». Кто захочет буквального 100 %-чтения — это отдельная работа объёмом ~750 тыс. токенов.

**Что метод не ловит в принципе** (плюс к обходам из CSA): семантически вредный, но синтаксически
безобидный совет; логическую бомбу в прозе; вредоносность, возникающую только от КОМБИНАЦИИ
скиллов; изменение содержимого по URL уже после аудита (это ловит не аудит, а `--check` + §6).

## 3. Находки

Ни одной находки класса **`risk`** (активный exfil-паттерн, исполняемый код с сетью, скрытая
инструкция-перехват) не обнаружено. Шесть находок класса **`attention`** — ниже поимённо.

### 3.1 `frontend/web-design-guidelines` — исполняемые инструкции подтягиваются из сети

`SKILL.md:16,23,29` (и `SKILL.ru.md:31`): «Fetch fresh guidelines before each review» →
`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`, далее
дословно «The fetched content contains all the rules **and output format instructions**» и
«Apply all rules from the fetched guidelines».

Почему это `attention`, а не `clean`: правила, которым агент следует, живут ВНЕ бандла;
`files[]` покрывает sha256 только самого `SKILL.md` (1 231 б), ссылка ведёт на ветку `main`
(не на коммит), содержимое может смениться в любой момент без всякого дрейфа у нас. Это
буквально rug-pull-класс из чек-листа `security/security` («Does the skill's behavior depend on
remote configuration?») и ровно то, против чего CSA рекомендует **пиновать версии**.

Почему не `risk`: источник — `vercel-labs`, признаков компрометации нет; сам бандл инертен.

Ремедиация НЕ выполняется этим item'ом: и «пиновать URL на коммит», и «вендорить payload в
`references/`», и «форкнуть», и «убрать» — правки содержимого вендоренного скилла, прямо
запрещённые Scope Excluded и Implementation Rules 7–8. Это **вход гейта владельца OQ-6**.

### 3.2 `security/security` — корпус атакующих строк по назначению

`references/full.md` даёт **все 8** находок триажа половины реестра: `INJ_IGNORE` ×4,
`INJ_DISREGARD` ×1, `INJ_ROLE_OVERRIDE` ×2, `EXF_ENV_DUMP` ×1, `EXE_PIPE_TO_SHELL` ×5,
`EXE_B64_EXEC` ×3. Все — внутри блоков «RED FLAG patterns», чек-листов детекта и примера
скрипта `scan_mcp_tools.sh`. Содержимое инертно (markdown, ничего не исполняется).

Правило НЕ ослаблялось под этот бандл (Code Guidance, анти-подгонка): срабатывание разобрано и
принято здесь. Следствие, которое надо знать оператору: **любой** паттерновый скан будет гореть
на этом бандле всегда; «зелёный триаж по реестру» недостижим по конструкции, пока скилл в реестре.

### 3.3 `ai/mcp-builder` — единственный бандл с исполняемым кодом

`scripts/connections.py` (4 875 б) и `scripts/evaluation.py` (12 579 б) прочитаны построчно:
это официальный eval-харнес MCP (Apache-2.0, `LICENSE.txt` на месте), вредоносного нет.
`attention` за профиль требований, а не за содержимое: запуск требует pip-пакетов
(`anthropic>=0.39.0`, `mcp>=1.1.0` — `scripts/requirements.txt`), сети и `ANTHROPIC_API_KEY`.
Плюс `SKILL.md:62,66,213,214` предписывают WebFetch README SDK с ветки `main` — тот же класс
непиновки, что §3.1, но payload здесь документация, а не правила поведения.

### 3.4 `architect/codebase-design` — CDN в генерируемом артефакте

`snippets/HTML-REPORT.md:13` `<script src="https://cdn.tailwindcss.com">`, `:15` импорт
`mermaid` с `cdn.jsdelivr.net`. Скилл сам ничего не тянет — тянет ОТЧЁТ, который он предлагает
сгенерировать пользователю. Класс: сторонний код исполняется в браузере пользователя, версия
`mermaid` пинована по мажору (`@11`), Tailwind — нет.

### 3.5 `creative/content-creative` — тот же класс в шаблонах web-артефактов

`references/full.md:2465` — шаблон p5.js-артефакта с `cdnjs.cloudflare.com`; `:545` — ссылка на
shadcn-доки. Тот же разбор, что §3.4.

### 3.6 `voice-ai/voice-ai` — в классе «56 вендоренных» лишний, и он же ронял `--check`

`upstream.json` несёт пять записей `files[]` с **пустыми** `path` и `sha256`: это
провенанс-ССЫЛКИ на внешние спеки (OpenAI Realtime, Pipecat, LiveKit, RFC 8825, Yandex
SpeechKit), чужой код не вендорился, `SKILL.md` написан у нас. Два следствия:

1. **Класс «56 вендоренных бандлов» неоднороден** — как минимум один из 56 ничего не вендорит,
   и целостность его содержимого не покрыта ничем (единственный такой бандл в реестре: проверка —
   скрипт §5). Знаменатель 56 остаётся верным для `upstream.json`, но не для «внешнего кода».
2. **Живой дефект, найденный аудитом и починенный этим item'ом:** `skill_dir / ""` резолвился
   в САМ каталог скилла, и `local_path.read_bytes()` ронял ВЕСЬ прогон `--check`
   `IsADirectoryError`-ом (воспроизведение до фикса:
   `bash packages/skiller/scripts/update-upstreams.sh --check --skill voice-ai/voice-ai`).
   То есть сверка целостности всего реестра была неработоспособна — «гейт, который не горел
   никогда, потому что падал раньше». Регресс закрыт тестом
   `test_reference_only_entry_does_not_crash_the_run`.

## 4. Таблица 56 вердиктов

`audited_at` — короткий sha256 провенансной базы бандла: детерминированная свёртка
пар `path:sha256` из `files[]`/`origins[]` НА МОМЕНТ АУДИТА. Именно против этих байтов вынесен
вердикт; их дрейф = протухший вердикт (§6). Скрипт вычисления — §5.

| # | Бандл | Стратегия | Отслеж./всего файлов | Байт | `audited_at` | Вердикт | Основание |
|--:|:--|:--|--:|--:|:--|:--|:--|
| 1 | `ai/ai-agents` | fork | 1/3 | 99 288 | `bb30f388386f` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 2 | `ai/mcp-builder` | replace | 9/10 | 121 756 | `eee57c3b23fd` | **attention** | единственный бандл с ИСПОЛНЯЕМЫМ кодом (`scripts/connections.py`, `scripts/evaluation.py` — требуют pip `anthropic`/`mcp`, сеть и `ANTHROPIC_API_KEY`); `SKILL.md` предписывает WebFetch README SDK с ветки `main` (не пиновано). Код прочитан целиком: вредоносного нет |
| 3 | `ai/performance` | notify | 1/2 | 14 265 | `57c3a0552e23` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 4 | `architect/codebase-design` | notify | 4/6 | 34 485 | `453162dea2a1` | **attention** | `snippets/HTML-REPORT.md:13,15` — генерируемый отчёт тянет `cdn.tailwindcss.com` и `cdn.jsdelivr.net` в артефакт пользователя |
| 5 | `architect/domain-modeling` | notify | 3/5 | 27 888 | `376760cee9f2` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 6 | `architect/engineering` | notify | 1/3 | 88 229 | `78749e899d39` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 7 | `creative/content-creative` | notify | 1/3 | 96 636 | `99b2a1a05df2` | **attention** | `references/full.md:2465` — шаблон web-артефакта тянет `cdnjs.cloudflare.com` (p5.js); `:545` — ссылка на shadcn CDN |
| 8 | `devops/docker` | notify | 1/4 | 18 556 | `598ecd5043eb` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 9 | `finance/finance` | notify | 1/3 | 80 200 | `72c36c05389e` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 10 | `frontend/document-writer` | notify | 3/4 | 19 895 | `64b3861b32f0` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 11 | `frontend/web-design-guidelines` | notify | 1/3 | 3 635 | `bb9c0f46dfaa` | **attention** | скилл предписывает WebFetch правил с `raw.githubusercontent.com/vercel-labs/…/main/command.md` и «apply all rules from the fetched guidelines» — канал инструкций живёт ВНЕ бандла; sha256 его не покрывает; версия не пинована |
| 12 | `frontend-animations/motion` | notify | 4/5 | 26 112 | `0a30433d4a5a` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 13 | `frontend-linting/antfu` | notify | 6/7 | 27 095 | `7af74e846013` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 14 | `frontend-linting/js-code-style` | notify | 1/5 | 14 140 | `b82877bd948b` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 15 | `frontend-linting/ts-library` | notify | 11/21 | 82 125 | `ad5b441e2a29` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 16 | `frontend-nuxt/nuxt` | notify | 8/9 | 56 991 | `e57401acb011` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 17 | `frontend-nuxt/nuxt-modules` | notify | 4/5 | 25 873 | `2ce4868e7579` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 18 | `frontend-nuxt/nuxt-seo` | notify | 6/7 | 23 084 | `57ea987cd590` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 19 | `frontend-vite/vite` | notify | 7/9 | 25 244 | `023304761d21` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 20 | `frontend-vite/vitepress` | notify | 15/17 | 68 119 | `95add341bb74` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 21 | `frontend-vue/pinia` | notify | 10/12 | 35 754 | `781bce2f90c9` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 22 | `frontend-vue/vitest-vue` | notify | 17/19 | 75 967 | `f9d47ee6bbae` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 23 | `frontend-vue/vue` | notify | 4/6 | 23 400 | `f9eed49447c7` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 24 | `frontend-vue/vue-best-practices` | notify | 23/26 | 129 700 | `d23c6d14e109` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 25 | `frontend-vue/vue-router-best-practices` | notify | 9/14 | 77 735 | `be7747b4ebca` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 26 | `frontend-vue/vue-testing-best-practices` | notify | 12/17 | 90 195 | `7be4d83c9900` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 27 | `frontend-vue/vueuse-functions` | notify | 266/269 | 694 589 | `e833f5878020` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 28 | `general/git-safety` | notify | 1/2 | 6 640 | `aaf010e7ec41` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 29 | `general/grill-with-docs` | notify | 1/2 | 11 023 | `26923e5ebf07` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 30 | `general/implement` | notify | 1/2 | 5 902 | `da6573ef9cca` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 31 | `laravel-data-layer/laravel-broadcasting` | notify | 1/7 | 22 708 | `c8dc5204622b` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 32 | `laravel-extras/pennant-development` | notify | 1/2 | 5 602 | `94ceca56fec4` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 33 | `laravel-filament/filament` | notify | 1/7 | 32 910 | `d78c204a3a72` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 34 | `legal/legal` | notify | 1/3 | 106 408 | `a4db6cbc7e8b` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 35 | `marketing/marketing` | notify | 1/3 | 63 894 | `90292b12cd72` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 36 | `operator/operations-cx` | notify | 1/3 | 83 122 | `7e7eedaf342c` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 37 | `oss-dev/issue-triage` | notify | 3/5 | 35 613 | `0adb1d9356a4` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 38 | `oss-dev/resolving-merge-conflicts` | notify | 1/2 | 4 986 | `b6483441a034` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 39 | `oss-dev/to-issues` | notify | 1/2 | 13 092 | `3b78611de842` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 40 | `php/code-style-spatie` | notify | 1/3 | 20 577 | `b202cb682b61` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 41 | `php/laravel-best-practices` | notify | 21/22 | 70 992 | `b7a8e40bee6b` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 42 | `php-packages/laravel-package-compatibility` | notify | 1/2 | 5 568 | `73e96600161c` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 43 | `php-packages/laravel-package-docs` | notify | 1/2 | 8 377 | `e967a0b2bf07` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 44 | `php-packages/laravel-package-expressive` | notify | 1/2 | 7 263 | `b128e79a9a02` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 45 | `php-packages/laravel-package-generate-skill` | notify | 1/2 | 9 233 | `facf598d58d4` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 46 | `php-packages/laravel-package-release` | notify | 1/2 | 4 835 | `46da648cd2db` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 47 | `php-packages/laravel-package-scaffold` | notify | 1/2 | 7 730 | `658179a21430` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 48 | `php-packages/laravel-package-service-provider` | notify | 1/2 | 6 236 | `92ebc041b22c` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 49 | `php-packages/laravel-package-testing` | notify | 1/2 | 6 429 | `a332fe240a53` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 50 | `pm/product` | notify | 1/3 | 85 980 | `7cdbbfbd4956` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 51 | `quality/diagnosing-bugs` | notify | 2/4 | 28 612 | `4cea46427484` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 52 | `quality/tdd-discipline` | notify | 3/6 | 19 967 | `f21b1850f049` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 53 | `research/research` | notify | 1/3 | 76 884 | `6fff1cc03ea9` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 54 | `sales/sales` | notify | 1/3 | 98 694 | `d957c0bf9c62` | **clean** | паттернов четырёх классов не найдено; сеть — только доки / `example.com` / `localhost`; исполняемого кода нет |
| 55 | `security/security` | notify | 1/3 | 110 715 | `a8d1efe0351c` | **attention** | справочник по защите: корпус атакующих строк (`ignore previous instructions`, `curl \| bash`, примеры эксфильтрации) — по назначению, инертный markdown; любой паттерновый скан будет срабатывать здесь ВСЕГДА |
| 56 | `voice-ai/voice-ai` | notify | 5/2 | 29 644 | `— (sha не записан)` | **attention** | НЕ вендоренный бандл: `files[].path` и `sha256` пусты — провенанс-ссылки на спеки, чужой код не вендорился; целостность не покрыта НИЧЕМ. Носитель дефекта `IsADirectoryError` (починен этим item'ом) |

## 5. Воспроизведение `audited_at` и знаменателей

```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path
ROOT = Path("packages/skiller/skills")
for cfg in sorted(ROOT.glob("**/upstream.json")):
    d = json.loads(cfg.read_text(encoding="utf-8"))
    files = list(d.get("files", [])) + list(d.get("origins", []))
    base = "".join(f"{f.get('path','')}:{f.get('sha256','')}\n"
                   for f in sorted(files, key=lambda x: x.get("path", "")))
    audited = hashlib.sha256(base.encode()).hexdigest()[:12] if any(
        f.get("sha256") for f in files) else "— (sha не записан)"
    print(f"{cfg.parent.relative_to(ROOT)}\t{audited}")
PY
```

## 6. Как вердикт протухает

Разовый аудит без срока годности бессмысленен: он описывает БАЙТЫ, а байты обновляются.
Поэтому `--check` при дрейфе относительно записанного sha (= `audited_at`) печатает отдельную
строку `[stale] <бандл> (verdict)` и кладёт запись в `stale_verdicts` JSON-канала — «человеческий
вердикт бандла ПРОТУХ, перечитай бандл». Тест: `test_drift_marks_the_human_verdict_stale`.

**Граница, названная явно.** После `--apply` свежий sha записывается в `upstream.json`, дрейф
исчезает — и отметка вместе с ним, хотя человеческий вердикт в этой таблице остался протухшим.
Скрипт не читает эту таблицу намеренно: она живёт в плане и доках, а кросс-пакетной связи
«скрипт `skiller` читает файл плана» быть не должно. Рабочая процедура: `--check` **до**
`--apply` → перечитать помеченные бандлы → обновить строку таблицы.

## 7. Провенанс правил триажа

13 правил в `update-upstreams.sh` (+ `BIN_UNREADABLE`) выведены из находок выше:

| Класс угрозы | Правила | Откуда взялось |
|:--|:--|:--|
| prompt injection | `INJ_IGNORE`, `INJ_DISREGARD`, `INJ_HIDE_FROM_USER`, `INJ_ROLE_OVERRIDE`, `INJ_INVISIBLE_CHAR` | идиомы §3.2 + детектор невидимых символов из слоя A |
| data exfiltration | `EXF_SUSPECT_HOST`, `EXF_CRED_TO_NET`, `EXF_ENV_DUMP` | список стоков и конъюнктивная форма («секрет И сеть в одной строке») — иначе `.env` в доках даёт шум, а не сигнал |
| code execution | `EXE_PIPE_TO_SHELL`, `EXE_B64_EXEC`, `EXE_OBFUSC_BLOB` | образцы §3.2 + детектор base64-блобов |
| over-permissive tools | `PRM_TOOL_WILDCARD`, `PRM_PERMISSION_BYPASS`, `PRM_REMOTE_INSTRUCTIONS` | последнее правило существует ровно потому, что аудит нашёл живой носитель §3.1 |
| нечитаемость | `BIN_UNREADABLE` | «не смогли прочитать» ≠ «чисто» |

Правила англоязычные с RU-веткой только у `PRM_REMOTE_INSTRUCTIONS`: рядом с 55 из 56 бандлов
лежит переведённый `SKILL.ru.md`, и без RU-ветки гейт рапортовал бы чистоту на половине
раздаваемой поверхности. Остальные правила на RU-переводах **не покрыты** — названная граница,
кандидат в follow-up.

Механизм подавления/allowlist сознательно **не заведён**: он и есть решение о политике доверия
(что считать принятым исключением), то есть предмет OQ-6, а не item'а. Следствие: на живом
реестре `--check` возвращает **11** постоянно, пока `security/security` и
`frontend/web-design-guidelines` в нём есть.

## 8. Вход для гейта владельца OQ-6

Ветки вопроса и что о них говорит аудит:

- **(A) статус-кво + триаж-скан.** Триаж-ступень теперь есть, но §3.1 остаётся открытым:
  бандл продолжает исполнять инструкции из непинованного удалённого источника.
- **(B) разовый человеческий аудит всех 56 + запрет вендоренья без аудита.** Аудит выполнен
  (эта таблица, с названными границами §2). Запрет — правило процесса, его вводит владелец;
  носитель — `packages/skiller/docs/guide/vendored-skills.md`.
- **(C) сокращение поверхности.** Данных по usage этот item не собирал (вне Scope);
  из аудита кандидатов на удаление НЕ следует — `risk` не найден ни у одного бандла.

**Решения нет.** Ремедиация §3.1 требует правки/замены/пиновки вендоренного бандла, что
Scope Excluded item'а запрещает, а Implementation Rule 12 (D65) предписывает в этом случае
`🔴 Blocked` вместо `🟠`: находка обязана остаться на доске, а не уехать в закрытый item.
