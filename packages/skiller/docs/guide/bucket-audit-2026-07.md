# Bucket-audit — 2026-07 (P7.2, SKM-MASTER-002)

Снимок «до»: прогон `skiller bucket-audit` на живом реестре (206 скиллов / 45 бакетов),
зафиксированный как база для контентных шагов фазы G (P7.3 монолиты →
thin-navigator, P7.4 dead-pass, P7.5 alias-механизм). Все числа ниже — дословно из
вывода команды (не по памяти), см. [«Как воспроизвести»](#как-воспроизвести).

```
skiller bucket-audit --json   # since=30 (default)
```

Дата прогона: 2026-07-02. Скриптовое обеспечение (`audit.py`) — P7.1, уже в рабочей
копии на момент этого прогона.

## Честность usage-окна (прочитать перед вердиктами)

**Реальное окно: 30 дней, и это уже весь доступный горизонт.** `bucket-audit`
считает usage фан-аутом по `~/.swissknifeman/projects.json` (23 зарегистрированных
проекта) → JSONL-транскриптам сессий Claude Code. Проверено эмпирически: прогон с
`--since 3650` (10 лет) даёт **тот же** результат, что и `--since 30` — 21
просканированный проект, идентичные вердикты. Причина — не «телеметрия только
включилась», а то, что более старых логов физически нет: среди 334 файлов сессий 21
проекта самый старый датирован 2026-06-02, самый новый — 2026-07-02 (ровно 30 дней
истории). Так что «окно 30 дней» здесь = «вся история, что есть», а не усечение
искусственным `--since`.

⚠ **[POSSIBLE-DEFECT] расхождение с постановкой задачи.** Задача этого пункта плана
предполагала «телеметрия SCHEMA=2 включена 2026-07-02 — окно ~1 день». Проверено
чтением кода (repo-grounded, не внешний факт): `SCHEMA=2` — это отдельный формат
run-report хука пакета `harness` (`packages/harness/configs/claude-code/hooks/run-report/_lib.py`,
`usage-trend.ndjson`), и его коммит (`070e529`) действительно датирован сегодня. Но
`bucket-audit.collect_usage` **не читает** этот источник — он использует куда более
старый механизм (`analyze.py::agent_stats`, явные вызовы Skill-tool в транскриптах),
который был задолго до SCHEMA=2. Иными словами: посылка про «SCHEMA=2 → окно ~1 день»
не относится к тому usage-сигналу, который реально стоит за вердиктами этого
документа — реальное окно usage-сигнала bucket-audit шире (30 дней = весь горизонт
проекта), но само число «30» ничем не отличается по сути от «1 дня»: оно всё ещё
рано для выводов о смерти скилла (ниже почему). **ESCALATION-REQUIRED**: если у
кого-то в мастер-плане была цель именно свести аудит к данным SCHEMA=2
(`usage-trend.ndjson`) — это отдельная доработка `audit.py` (не входила в P7.1
scope, там явно зафиксировано «usage — фан-аут по projects.json → транскрипты»), не
сделанная здесь; на текущий прогон это не влияет, кроме формулировки причины
короткого окна.

**Вторая, более важная причина не доверять `dead` буквально — структурная, не про
длину окна.** `analyze.py` документирует это прямо: «загрузка скилла детектится
ТОЛЬКО по явным Skill-tool-вызовам; нативный `skills:`-preload субагента и
авто-триггер плагина по description как Skill-вызов НЕ видны → «DEAD» эвристичен».
Эмпирическое подтверждение на этом самом прогоне: CORE-скиллы (`context-economy`,
`anti-drift`, `compact-responses`, `mcp-advisor`, `verify-claims` — раздаются в
**каждый** connect-проект по умолчанию, см. `configs/core-policy.json`) все пятеро
показывают `loaded_count=0` и вердикт `dead`, при том что реально резидентны в
каждом запросе тех проектов (иначе бы CORE-политика не работала). Значит высокая
доля `dead` (180 из 206 = 87%) — это в основном слепая зона детектора
(auto-trigger/preload не логируется как явный `Skill`-вызов), а не 180 реально
неиспользуемых скиллов.

**Практический вывод**: вердикт `dead` в этом отчёте читать РОВНО как
«не поймано явным Skill-tool-вызовом за 30 дней (весь доступный горизонт)» — не
«доказанно мёртв». Действие по нему — **P7.4 (profile-excludes, обратимо)**, и то
не раньше «≥2 недели прод-usage данных после появления телеметрии» по спеке фазы;
твёрдых удалений эта волна не производит нигде.

## Итог одной строкой

Скиллов: **206**. Бакетов: **45**. Просканировано проектов: **21** из 23
зарегистрированных (2 без каталога логов). Overlap-пар: **2** (3 скилла).

| Вердикт | N | Что это |
|---|---|---|
| `dead` | 180 | 0 явных загрузок за окно — см. честность выше, действие = P7.4 (exclude, не удаление) |
| `keep` | 13 | реально пойманы Skill-tool в окне |
| `thin` | 8 | тело-монолит (↻tier1 ≥ 6000 ток) — кандидат thin-navigator (P7.3) |
| `merge` | 3 | overlap с другим скиллом (Jaccard/shingle) — ждёт alias-механизм (P7.5), не исполняется |
| `retrieval-only` | 2 | заметное тело + редкое использование |

## Таблица по бакетам

Сумма ⊕tier0/↻tier1 — совокупный резидентный/on-trigger налог бакета (токены,
`skill_budget`, реюз `budget.py`).

| Бакет | Скиллов | Σ⊕tier0 | Σ↻tier1 | keep | thin | retrieval-only | merge | dead |
|---|---|---|---|---|---|---|---|---|
| ai | 2 | 199 | 2018 | 0 | 0 | 0 | 0 | 2 |
| architect | 14 | 880 | 44597 | 0 | 0 | 0 | 1 | 13 |
| azguard | 1 | 37 | 1679 | 0 | 0 | 0 | 0 | 1 |
| blender | 2 | 140 | 2287 | 0 | 0 | 0 | 0 | 2 |
| blender-modeling | 6 | 506 | 8887 | 0 | 0 | 0 | 0 | 6 |
| botkit | 1 | 29 | 234 | 0 | 0 | 0 | 0 | 1 |
| creative | 1 | 155 | 26240 | 0 | 1 | 0 | 0 | 0 |
| devops | 11 | 548 | 9181 | 2 | 0 | 0 | 0 | 9 |
| finance | 1 | 179 | 21503 | 0 | 1 | 0 | 0 | 0 |
| founder | 10 | 406 | 15188 | 0 | 0 | 0 | 0 | 10 |
| frontend | 3 | 285 | 3795 | 0 | 0 | 0 | 0 | 3 |
| frontend-animations | 1 | 55 | 920 | 0 | 0 | 0 | 0 | 1 |
| frontend-backend | 3 | 288 | 5488 | 0 | 0 | 0 | 0 | 3 |
| frontend-figma | 1 | 99 | 813 | 0 | 0 | 0 | 0 | 1 |
| frontend-linting | 4 | 323 | 5920 | 0 | 0 | 0 | 0 | 4 |
| frontend-naive-ui | 1 | 103 | 2041 | 0 | 0 | 0 | 0 | 1 |
| frontend-nuxt | 3 | 255 | 2564 | 0 | 0 | 0 | 0 | 3 |
| frontend-reka | 1 | 105 | 2007 | 0 | 0 | 0 | 0 | 1 |
| frontend-tailwind | 2 | 240 | 4458 | 0 | 0 | 0 | 0 | 2 |
| frontend-vite | 4 | 180 | 3150 | 0 | 0 | 0 | 0 | 4 |
| frontend-vue | 11 | 854 | 25744 | 0 | 1 | 0 | 0 | 10 |
| frontend-wayfinder | 1 | 48 | 994 | 0 | 0 | 0 | 0 | 1 |
| general | 20 | 1402 | 23319 | 3 | 0 | 0 | 0 | 17 |
| laravel-architecture | 6 | 677 | 9730 | 0 | 0 | 0 | 0 | 6 |
| laravel-auth | 3 | 202 | 3358 | 0 | 0 | 0 | 0 | 3 |
| laravel-data-layer | 2 | 160 | 3314 | 1 | 0 | 0 | 0 | 1 |
| laravel-extras | 3 | 225 | 4257 | 0 | 0 | 0 | 0 | 3 |
| laravel-filament | 1 | 63 | 2374 | 0 | 0 | 1 | 0 | 0 |
| laravel-livewire | 1 | 128 | 1283 | 0 | 0 | 0 | 0 | 1 |
| laravel-testing | 4 | 323 | 7993 | 0 | 0 | 0 | 0 | 4 |
| legal | 1 | 145 | 29249 | 0 | 1 | 0 | 0 | 0 |
| marketing | 1 | 142 | 16617 | 0 | 1 | 0 | 0 | 0 |
| mobile | 1 | 107 | 867 | 0 | 0 | 0 | 0 | 1 |
| operator | 6 | 296 | 31668 | 0 | 0 | 0 | 1 | 5 |
| oss-dev | 10 | 627 | 13978 | 1 | 0 | 0 | 0 | 9 |
| php | 17 | 1122 | 19300 | 4 | 0 | 0 | 0 | 13 |
| php-packages | 9 | 685 | 5417 | 1 | 0 | 0 | 0 | 8 |
| pm | 10 | 438 | 33491 | 0 | 0 | 0 | 1 | 9 |
| python | 2 | 58 | 1163 | 0 | 0 | 0 | 0 | 2 |
| quality | 10 | 738 | 19065 | 1 | 0 | 1 | 0 | 8 |
| research | 2 | 325 | 24400 | 0 | 1 | 0 | 0 | 1 |
| roles | 4 | 80 | 5253 | 0 | 0 | 0 | 0 | 4 |
| sales | 1 | 143 | 25593 | 0 | 1 | 0 | 0 | 0 |
| security | 1 | 184 | 30199 | 0 | 1 | 0 | 0 | 0 |
| system | 7 | 607 | 11012 | 0 | 0 | 0 | 0 | 7 |

Все 45 бакетов покрыты (сумма N = 206).

## Поимённые вердикты

### merge (3) — ждёт alias-механизм P7.5, НЕ исполняется

| Скилл | ↻tier1 | Overlap с | desc Jaccard | body shingle |
|---|---|---|---|---|
| `architect/dev-engineering-super-skill` | 23962 | `operator/operations-cx-super-skill` | 0.412 | 0.001 |
| `operator/operations-cx-super-skill` | 22355 | `architect/dev-engineering-super-skill`, `pm/pm-super-skill` | 0.412 / 0.404 | 0.001 / 0.001 |
| `pm/pm-super-skill` | 23037 | `operator/operations-cx-super-skill` | 0.404 | 0.001 |

См. [спорный случай №1](#1-merge-вердикт-по-3-super-skill-монолитам--вероятный-false-positive)
ниже — overlap здесь почти наверняка ложный сигнал (шаблонная фраза в description,
не содержание).

### thin (8) — тело-монолит (↻tier1 ≥ 6000 ток), кандидат thin-navigator P7.3

| Скилл | ⊕tier0 | ↻tier1 | usage |
|---|---|---|---|
| `security/agent-security-super-skill` | 184 | 30199 | не использовался в окне 30 дней |
| `legal/legal-super-skill` | 145 | 29249 | не использовался в окне 30 дней |
| `creative/content-creative-super-skill` | 155 | 26240 | не использовался в окне 30 дней |
| `sales/sales-super-skill` | 143 | 25593 | не использовался в окне 30 дней |
| `finance/finance-super-skill` | 179 | 21503 | не использовался в окне 30 дней |
| `research/research-knowledge-super-skill` | 195 | 20472 | не использовался в окне 30 дней |
| `marketing/marketing-super-skill` | 142 | 16617 | не использовался в окне 30 дней |
| `frontend-vue/vueuse-functions` | 34 | 10838 | не использовался в окне 30 дней |

Первые 7 — external `*-super-skill` монолиты (см. [раздел монолитов](#10-внешних-монолитов-≥50kb--список-для-p73)).
`vueuse-functions` — тоже монолит по токенам (10838 ток), но тело 36.0KB —
**ниже** порога 50KB из ТЗ P7.3, поэтому не входит в подтверждённый список «10»
(см. карточку [спорный случай №4](#4-vueuse-functions--monolith-по-токенам-но-не-по-заявленному-порогу-p73)).

### retrieval-only (2)

| Скилл | ↻tier1 | Использований |
|---|---|---|
| `quality/playwright-e2e` | 2544 | 1× за 30 дней |
| `laravel-filament/filament` | 2374 | 1× за 30 дней |

### keep (13) — реально пойманы Skill-tool в окне

| Скилл | ↻tier1 | Использований |
|---|---|---|
| `general/git-commit-rules` | 934 | 25× за 30 дней |
| `php/database` | 961 | 5× за 30 дней |
| `php/repositories` | 1563 | 4× за 30 дней |
| `general/complex-task-orchestrator` | 659 | 2× за 30 дней |
| `php/laravel-structure` | 2020 | 2× за 30 дней |
| `quality/code-review` | 1622 | 2× за 30 дней |
| `devops/ci-cd` | 1150 | 1× за 30 дней |
| `devops/db-test-preflight` | 1703 | 1× за 30 дней |
| `general/task-brief-template` | 1253 | 1× за 30 дней |
| `laravel-data-layer/laravel-broadcasting` | 1257 | 1× за 30 дней |
| `oss-dev/resolving-merge-conflicts` | 335 | 1× за 30 дней |
| `php/namespace-refactor-safety` | 365 | 1× за 30 дней |
| `php-packages/laravel-package-compatibility` | 446 | 1× за 30 дней |

### dead (180)

Полный поимённый список — [Приложение A](#приложение-a-полный-вывод-аудита-206-строк)
(таблица покрывает все 206 скиллов, включая все 180 `dead` с их ⊕tier0/↻tier1). По
бакетам — колонка `dead` в [таблице выше](#таблица-по-бакетам). Читать вердикт по
правилам раздела [«Честность usage-окна»](#честность-usage-окна-прочитать-перед-вердиктами):
не «список на удаление», а «список без явного тригера в окне».

## 10 внешних монолитов ≥50KB — список для P7.3

Подтверждено измерением (не по памяти из Phase Context): ровно **10** скиллов с
телом SKILL.md ≥50KB, все external (`upstream.json`, репозитории `get-zeked/*-super-skill`,
MIT, `strategy: notify`). Сумма их ↻tier1 = **239 227 ток** — это и есть «~240K
токенов тел on-trigger» из Phase Context P7 (совпадает с точностью до округления).

| Бакет | Скилл (name) | Каталог | Тело, KB | ↻tier1, ток | Вердикт аудита | Upstream repo |
|---|---|---|---|---|---|---|
| security | agent-security-super-skill | `skills/security/security` | 101.7 | 30199 | thin | get-zeked/agent-security-super-skill |
| legal | legal-super-skill | `skills/legal/legal` | 97.5 | 29249 | thin | get-zeked/legal-super-skill |
| sales | sales-super-skill | `skills/sales/sales` | 89.6 | 25593 | thin | get-zeked/sales-super-skill |
| creative | content-creative-super-skill | `skills/creative/content-creative` | 88.4 | 26240 | thin | get-zeked/content-creative-super-skill |
| architect | dev-engineering-super-skill | `skills/architect/engineering` | 80.0 | 23962 | merge* | get-zeked/dev-engineering-super-skill |
| pm | pm-super-skill | `skills/pm/product` | 77.1 | 23037 | merge* | get-zeked/pm-super-skill |
| operator | operations-cx-super-skill | `skills/operator/operations-cx` | 75.2 | 22355 | merge* | get-zeked/operations-cx-super-skill |
| finance | finance-super-skill | `skills/finance/finance` | 72.1 | 21503 | thin | get-zeked/finance-super-skill |
| research | research-knowledge-super-skill | `skills/research/research` | 68.4 | 20472 | thin | get-zeked/research-knowledge-super-skill |
| marketing | marketing-super-skill | `skills/marketing/marketing` | 55.9 | 16617 | thin | get-zeked/marketing-super-skill |

`*` — 3 монолита несут ОДНОВРЕМЕННО вердикт `merge` (overlap между собой побеждает
`thin` по приоритету сигнала в `verdict()`) и статус «монолит ≥50KB». Для P7.3 это
не блокер: перевод в thin-navigator (P7.3) и решение по alias/merge (P7.5) —
независимые оси; см. [спорный случай №1](#1-merge-вердикт-по-3-super-skill-монолитам--вероятный-false-positive).
Пути — от корня пакета `packages/skiller/`.

## Спорные случаи

### 1. `merge`-вердикт по 3 super-skill монолитам — вероятный false-positive

`architect/dev-engineering-super-skill`, `operator/operations-cx-super-skill`,
`pm/pm-super-skill` дают desc Jaccard 0.40–0.41 (порог 0.4), но body shingle всего
**0.001** (порог 0.3, т.е. содержимого тел они не разделяют вообще). Причина
overlap видна в самих description — они почти дословно шаблонны:

> «Broad **{X}**-bucket navigator (composite of external {X} skills). For specific
> work prefer the granular skill — … Use only for a cross-cutting overview when no
> single skill fits.»

Совпадает вендорский шаблон (`get-zeked/*-super-skill`), а не предметная область
(engineering vs ops vs pm — три разных домена). Практический вывод: `merge` здесь,
скорее всего, ложный сигнал самого Jaccard-порога на шаблонных описаниях, а не
повод сливать три ролевых бакета. Даже когда alias-механизм (P7.5) появится, эти
три пары стоит пересмотреть вручную перед реальным alias — сам факт «description
похож» не значит «слить». Дополнительный нюанс: их собственные description уже
называют их «navigator» — то есть это идеальные и низкорисковые кандидаты для
P7.3 thin-navigator независимо от исхода merge-вопроса.

### 2. CORE-скиллы показывают `dead` при заведомой активности — подтверждает слепую зону детектора

`general/anti-drift`, `general/compact-responses`, `general/context-economy`,
`general/mcp-advisor`, `general/verify-claims` — все 5 из 8 `CORE_SKILLS`
(`configs/core-policy.json`), раздаваемых в каждый connect-проект по умолчанию —
вердикт `dead`, 0 загрузок. Остальные 3 CORE (`session-handoff`, `query-craft`,
`gh-review`) для сверки: `session-handoff` тоже dead, `query-craft` (bucket
`research`) тоже dead, `gh-review` (bucket `oss-dev`) тоже dead. Все 8/8 CORE_SKILLS
— `dead` по этому аудиту. Это не «CORE не работает» (это раздельно проверяется
`skiller budget --check-core`, см. ниже), а прямое эмпирическое подтверждение
ограничения `analyze.py`: авто-триггер плагина по description в транскрипте не
выглядит как явный `Skill`-tool-вызов. Референс: `skiller budget --check-core`
(отдельный от usage-аудита канал) на момент этого прогона показал `CORE резидент
(⊕ tier-0): 662 ток / target 750 — OK (8/8 скиллов)` — то есть все 8 CORE
физически раздаются, просто usage-детектор их не видит. Вывод: `dead`-вердикт
CORE-скиллов **однозначно ложный** — веский аргумент не трогать эти 8 в P7.4
независимо от их usage-строки (в P7.4 они и так вне периметра — CORE явно не
кандидат на exclude).

### 3. `general` — самый крупный dead-бакет (17/20), но 3 живых скилла держат высокий loaded_count

`general` — 20 скиллов, 17 `dead`, но `git-commit-rules` (25× за 30 дней — самый
высокий usage во всём реестре) и `complex-task-orchestrator`/`task-brief-template`
(`keep`) реально используются. Бакет смешивает CORE (auto-trigger, слепая зона
детектора, см. случай №2) и не-CORE general-скиллы, часть из которых (например
`git-commit-rules`) явно вызываются как отдельный Skill. Смешение статистически
«топит» бакет в dead-проценте, хотя внутри — рабочее ядро. Урок для P7.4:
exclude-решения принимать **по скиллу**, не по бакету в целом.

### 4. `vueuse-functions` — monolith по токенам, но не по заявленному порогу P7.3

`frontend-vue/vueuse-functions` — вердикт `thin` (↻tier1=10838 ≥ 6000), но тело
36.0KB < 50KB порога, которым описан периметр P7.3 в Phase Context/этом документе.
Формально это тоже «монолит», просто меньше остальных десяти на порядок ниже
(они 55.9–101.7KB). Решение: **не включать** в подтверждённый список «10» этой
волны (P7.3 привязан к конкретному числу и порогу из плана), оставить как отдельный
`thin`-кандидат для отдельного будущего прохода — тем более он единственный
non-`*-super-skill` (не из `get-zeked`) монолит в реестре, физическая раскладка
навигатора может отличаться.

## Эскиз целевой топологии 45 → ~34 (ТОЛЬКО эскиз, отдельный будущий релиз)

Ниже — иллюстрация, НЕ решение и НЕ план на исполнение в этой волне. Основана на
структурном наблюдении (много одно-/малоскилльных тематически смежных бакетов),
не на overlap-детекторе аудита (у мелких бакетов ниже overlap почти не всплывает —
Jaccard считается по description, у разных инструментов Vue/Nuxt/Tailwind описания
не похожи, хотя домен один). Ждёт alias-механизма (P7.5) для безопасного исполнения
(back-compat D14).

| Группа кандидатов | Сейчас (бакетов / скиллов) | Эскиз-сокращение | Обоснование |
|---|---|---|---|
| `frontend-animations`, `frontend-backend`, `frontend-figma`, `frontend-linting`, `frontend-naive-ui`, `frontend-nuxt`, `frontend-reka`, `frontend-tailwind`, `frontend-vite`, `frontend-wayfinder` | 10 бакетов / 21 скилл | → ~3 (напр. `frontend-tooling`, `frontend-ui`, `frontend-nuxt`-группа) | каждый 1–4 скилла, все под одним доменом (Vue-фронтенд-экосистема), дробление явно избыточно гранулярное |
| `blender` + `blender-modeling` | 2 бакета / 8 скиллов | → 1 (`blender`) | один инструмент, искусственное разделение mcp/modeling |
| `azguard`, `botkit` | 2 бакета / 2 скилла | → 0 (вынос из реестра, не merge) | CLAUDE.md уже помечает их «под перенос внутрь пакетов» — это не bucket-merge, а другой процесс (out of P7 scope) |
| `laravel-livewire` (1 скилл) → `laravel-extras` | 2 бакета / 4 скилла | → 1 | livewire-blade-attributes — единственный скилл бакета, тематически смежен с extras |

Итог эскиза: 45 − 7 (frontend) − 1 (blender) − 2 (azguard/botkit вынос) − 1
(livewire) ≈ **34 бакета**. Ни одна строка этой таблицы не исполняется в P7 —
это вход для будущего отдельного релиза после P7.5.

## Что НЕ делаем в этой волне и почему

- **Не переименовываем и не сливаем бакеты** (в т.ч. те 3 из «спорного случая
  №1» и весь эскиз топологии выше) — решение D14 мастер-плана: 13 проектов сидят
  на marketplace-канале (`enabledPlugins` в `.claude/settings.local.json`),
  переименование/слияние бакета ломает их подключение без миграции. Подтверждено
  прямым подсчётом `~/.swissknifeman/projects.json`: ровно **13** проектов с
  `channel: marketplace` на момент этого прогона (совпадает с цифрой D14).
- **Не режем 10 монолитов на подскиллы** — решение D13: резка растит резидентный
  ⊕tier-0 (у каждого нового скилла своя описание-строка, налог на каждый запрос);
  вместо этого — thin-navigator (SKILL.md-навигатор + `references/full.md`,
  тело остаётся физически одним файлом, просто не грузится целиком on-trigger).
  Это P7.3, отдельный item, не здесь.
- **Не исполняем `merge`-вердикты** — ждут alias-механизма P7.5 (marketplace-запись
  со `skills[]`-списком, прецедент — курируемый плагин `core`). До него слияние
  физически ломает связь «имя бакета → плагин» для потребителей.
- **Не исключаем ни один скилл из профилей (P7.4 здесь не делается)** — условие
  фазы: «≥2 недели прод-usage данных после появления телеметрии»; на 2026-07-02
  реальный горизонт usage-данных — 30 дней, и он и есть всё, что накопилось (см.
  раздел честности окна). P7.4 — отдельный item, после накопления ещё окна.
- **Не правим содержимое upstream-тел монолитов** — faithful-first (CLAUDE.md
  корня): переносимые в P7.3 тела `references/full.md` переносятся дословно,
  без редактирования.

## Поправка канала (P2.2 SKM-MASTER-003) — 2026-07-02

Второй, независимый от транскриптов источник видимости usage закрывает слепую зону,
описанную выше («Честность usage-окна» + Спорный случай №2). Это дополнение, не
переписывание — исходные числа/таблицы этого документа выше остаются как снимок
«до» (P7.2, только transcript-канал).

**Что изменилось (`audit.py`, P2.2):** скилл считается **резидентным**, если он
(1) входит в `CORE_SKILLS` (`configs/core-policy.json`, грузится ярусом-0 в каждый
connect-проект) **или** (2) входит в активный набор (`budget.resolve_active_set` —
профиль/бакеты `.swissknife.json`, тот же путь, что уже использует
`analyze._active_skill_names`) хотя бы одного из проектов, зарегистрированных в
`~/.swissknifeman/projects.json`. Резидентный скилл без единого явного Skill-tool-
вызова в транскрипте **больше не получает вердикт `dead`** — вместо этого `keep` с
usage_note `«резидентный, прямых вызовов не видно (авто-триггер вне детекции)»`.
В JSON/рендере у каждого скилла теперь есть поле `channel: skill-call | resident |
none` — явно видно, КАКОЙ источник видел скилл (`skill-call` — сильнее, побеждает
при совпадении с `resident`).

**Отклонение от постановки item'а (зафиксировано честно).** Формулировка P2.2 в
плане (`Inputs`) предполагала вторым источником SCHEMA=2-тренд/run-reports
(`<проект>/.claude/analyze/usage-trend.ndjson`). Прочитано repo-grounded: формат
строки тренда — `{ts, session, in, out, cache_read, cache_creation, by_model,
tools_total, files_changed, agents, wall_s, retr_chars}` (пишет
`packages/harness/configs/claude-code/hooks/run-report/run-report.py` +
`_lib.py`, докстринг `analyst/token_report.py`) — он несёт токены/тайминги/tool-
счётчики АГРЕГАТНО, но **не несёт per-skill call/load сигнала вообще** (хук не
детектит `Skill`-tool вызовы, только `skills-lock.json`-managed пути для
`protected_writes`). Это ровно тот факт, который уже зафиксирован выше как
ESCALATION-REQUIRED (строки 27–43, прогон P7.2): «SCHEMA=2 → bucket-audit» из
постановки не соответствует реальным данным этого источника. Поэтому вместо чтения
`usage-trend.ndjson` реализован канал `resident` на CORE_SKILLS + активном наборе
профиля/бакетов — он решает ту же задачу (P2.2 Why: «резидентные CORE-скиллы
выглядят dead»), опираясь на уже существующий, протестированный путь `resolve_active_set`
(вместо нового парсера несуществующего сигнала). Это НЕ импровизация мимо плана: пункт
явно предусматривал усечённую слепую зону, а её реальная причина/починка была уже
частично исследована в этом же документе на предыдущем проходе.

**Новые числа dead/keep** (прогон 2026-07-02, `since_days=30`, 21 просканированный
проект, 139 резидентных скиллов из 206):

| Вердикт | N (было*, transcript-only) | N (стало, + канал resident) |
|---|---|---|
| `dead` | 187 | **65** |
| `keep` | 13 | **135** |
| `merge` | 3 | 3 |
| `thin` | 1 | 1 |
| `retrieval-only` | 2 | 2 |

\* «было» реконструировано из текущего прогона (те же 206 скиллов, тот же
transcript-usage): строки с `channel=resident` и `verdict=keep` при `loaded_count=0`
до поправки получали бы `dead` — 122 таких строки. Абсолютные числа этого столбца
отличаются от таблицы «Итог одной строкой» выше (180/13/8/3/2, снимок P7.2) —
разница объясняется естественным дрейфом реестра/контента между прогонами
(P7.3 thin-navigator уже прошёл, `thin` упал 8→1), не поправкой канала; сравнение
«было/стало» в этой таблице — **в рамках одного прогона**, честно изолирует именно
эффект резидент-канала.

Все **8/8 `CORE_SKILLS`** (`context-economy`, `anti-drift`, `compact-responses`,
`session-handoff`, `mcp-advisor`, `verify-claims`, `query-craft`, `gh-review`) теперь
`keep`/`resident` — Спорный случай №2 выше закрыт. Остальные 122 флипнутых скилла —
не CORE, а скиллы бакетов, реально входящих в активный профиль хотя бы одного из 21
зарегистрированного проекта (например `php/*`, `frontend-vue/*`, `devops/*`,
`oss-dev/*`) — они физически раздаются этим проектам через connect/vendor, поэтому
формально резидентны, даже если конкретный проект их триггер ни разу не поймал.

**Что это значит для P7.4 (dead-pass, следующий item, тот же план).** Резидент-канал
снял ложные срабатывания на уровне «раздано, но не поймано транскриптом» — оставшиеся
**65 `dead`** уже НЕ пересекаются ни с CORE, ни с активным набором ни одного из 21
известных проектов: это более узкий, более достоверный кандидат-список для
profile-excludes. Он всё ещё не «доказанная бесполезность» (проекты вне
`~/.swissknifeman/projects.json` не видны обоим каналам; резидентность через
`.swissknife.json` — best-effort снимок текущего состояния конфигов, не история) —
P7.4 остаётся исполнять как обратимый exclude, не удаление, и не раньше «≥2 недели
прод-usage» по своей собственной спеке.

**Как получить актуальные числа заново:**

```bash
cd packages/skiller
PYTHONPATH="$(pwd)/lib:$(cd ../.. && pwd)" python3 -m skiller "$(pwd)" bucket-audit --json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
      from collections import Counter; print(Counter(r['verdict'] for r in d['items'])); \
      print('resident_skills', d['resident_skills'])"
```

## P3.5 приписка — 2026-07-28 (D83): эскиз обновлён под сегодняшние числа, консолидация НЕ исполняется

**Рамка (обязательна к прочтению перед числами ниже).** Мотив этой приписки —
**СОПРОВОЖДЕНИЕ** (46→48 бакетов дорого вести), а НЕ листинговый бюджет: замер
2026-07-25 (D83) опроверг премису раздела «Эскиз целевой топологии» выше —
записи листинга добавляют **скиллы**, а не бакеты; мелкая гранулярность
**экономит** узкому подписчику символы, консолидация их **отнимает бы**.
Продавать обновление ниже как выигрыш бюджета листинга **запрещено** (та же
рамка, что и у раздела выше). Исполнение по-прежнему не производится этим или
любым последующим item'ом текущей волны — решение уходит владельцу как
**OQ-10** (`plans/archive/2026.07.25-ECO-OPT/open-questions.md`), закрыт на `finish`
вариантом **(b)**: консолидация не исполняется вовсе.

**Что изменилось со среза 2026-07-02:** реестр вырос **46 → 48 бакетов**
(канонизация 13 bootstrap-скиллов в новый бакет `repository-bootstrap`,
коммит `589c320e`, вне семейств `frontend*`/`laravel-*` — эскиз ниже их не
касается). Блокер `alias_of` остаётся снятым (P7.5 🟢, архивный
`2026.07.02-SKM-MASTER-002`) — сегодня в реестре алиасов по-прежнему объявлено
ноль, механизм доступен, но не задействован.

**Обязательный расчёт (D83): листинг ДО/ПОСЛЕ у ФАКТИЧЕСКИХ подписчиков по их
`enabledPlugins`**, эталон — `flexcrm` (23 плагина, самый нагруженный
подписчик флота, тот же проект, что и контрольная сверка D83):

| Семейство | Бакетов сейчас | ВКЛЮЧЕНО у `flexcrm` (символов) | НЕ включено (символов) | Листинг ПОСЛЕ гипотетического слияния |
|:--|--:|--:|--:|--:|
| `frontend*` (12 бакетов, эскиз → ~3) | 12 | 7 060 (8 бакетов) | 1 683 (4 бакета: `-animations` 180, `-figma` 323, `-nuxt` 835, `-reka` 345) | **8 743** (слияние — all-or-nothing по мерджнутому бакету, `flexcrm` получил бы обратно исключённые 1 683 симв) |
| `laravel-*` (7 бакетов, эскиз → 6: `-livewire`→`-extras`) | 7 | 4 772 (6 бакетов) | 409 (`laravel-livewire`) | **5 181** |
| **ИТОГО** | 19 | **11 832** | **2 092** | **13 924** |

Метод и числа воспроизводимы (та же команда, что контрольная сверка D83 ниже);
**11 832 / 2 092 симв — байт-в-байт совпадают** с эталоном D83 (замер 2026-07-25),
несмотря на рост реестра — семейства `frontend*`/`laravel-*` сам рост не задел.

Итог эскиза числом бакетов не изменился (46 → ~34 из раздела выше стало 48 → ~36
после роста `repository-bootstrap`, направление то же): **консолидация вернула
бы `flexcrm` 2 092 символа, которые он сегодня НЕ несёт** благодаря гранулярности
— то есть по метрике листингового бюджета эскиз не выигрыш, а **проигрыш**.
Единственный легальный мотив исполнения — сопровождение (48 бакетов дороже вести,
чем ~36), и ТОЛЬКО он идёт в OQ-10.

**Контрольная сверка (воспроизвести):**

```bash
cd <REPO_ROOT>
PYTHONPATH=packages/skiller/lib python3 -c "
from pathlib import Path
from skiller.common import parse_frontmatter
root = Path('packages/skiller/skills')
enabled = {'frontend','frontend-backend','frontend-linting','frontend-naive-ui',
           'frontend-tailwind','frontend-vite','frontend-vue','frontend-wayfinder',
           'laravel-architecture','laravel-auth','laravel-data-layer',
           'laravel-extras','laravel-filament','laravel-testing'}
fam = [d.name for d in root.iterdir() if d.name.startswith('frontend') or d.name.startswith('laravel-')]
inc = exc = 0
for b in fam:
    chars = sum(len(parse_frontmatter(md).get('description','') or '')
                for md in (root/b).rglob('SKILL.md'))
    (globals().__setitem__('inc', inc+chars) if b in enabled else globals().__setitem__('exc', exc+chars))
print('included', inc, 'excluded', exc)
"
```

Источники: `plans/archive/2026.07.25-ECO-OPT/findings/P3.1-listing-diagnosis.md` §0/§3
(корректировка бюджета 30 000/6 000) · `plans/archive/2026.07.25-ECO-OPT/findings/P3.5-listing-hygiene.md`
(полный расчёт этого захода) · `plans/archive/2026.07.25-ECO-OPT/phases/P3.md` D74–D77/D83
(рамка мотива, запрет продавать как выигрыш бюджета) · `open-questions.md` OQ-10.

## Как воспроизвести

```bash
cd packages/skiller
PYTHONPATH="$(pwd)/lib:$(cd ../.. && pwd)" python3 -m skiller "$(pwd)" bucket-audit --json
# человеко-читаемый рендер:
PYTHONPATH="$(pwd)/lib:$(cd ../.. && pwd)" python3 -m skiller "$(pwd)" bucket-audit
# другое окно:
... bucket-audit --since 14 --json
```

> Наблюдение при подготовке этого документа: `bin/skiller` (bash-лаунчер) на момент
> прогона **не знал** команду `bucket-audit` — whitelist команд в `case "$CMD" in
> connect|vendor|…)` (строка ~58 `packages/skiller/bin/skiller`) не был расширен
> вместе с добавлением команды в `lib/skiller/cli.py::COMMANDS` (P7.1). Итог CLI
> дошёл до `python3 -m skiller <repo_root> bucket-audit …` напрямую, обходя
> лаунчер — команда полностью рабочая, но конечный пользователь через `skiller
> bucket-audit` получит `Неизвестная команда: bucket-audit`, пока строка whitelist
> не будет обновлена. Файл `bin/skiller` вне scope этого item (P7.2 Files:
> только этот документ) — фиксирую как находку для P7.1/оркестратора, не правлю
> здесь.

## Приложение A: полный вывод аудита (206 строк)

| Скилл | ⊕tier0 | ↻tier1 | Вердикт | Usage |
|---|---|---|---|---|
| `ai/ai-agents` | 88 | 613 | dead | не использовался в окне 30 дней |
| `ai/token-efficient` | 111 | 1405 | dead | не использовался в окне 30 дней |
| `architect/agent-design` | 25 | 1744 | dead | не использовался в окне 30 дней |
| `architect/api-design` | 26 | 1129 | dead | не использовался в окне 30 дней |
| `architect/architecture` | 27 | 1329 | dead | не использовался в окне 30 дней |
| `architect/codebase-design` | 117 | 1996 | dead | не использовался в окне 30 дней |
| `architect/data-schema` | 28 | 924 | dead | не использовался в окне 30 дней |
| `architect/dev-engineering-super-skill` | 133 | 23962 | merge | не использовался в окне 30 дней |
| `architect/domain-modeling` | 122 | 1261 | dead | не использовался в окне 30 дней |
| `architect/eval-design` | 32 | 1570 | dead | не использовался в окне 30 дней |
| `architect/figma-mcp-core` | 136 | 1629 | dead | не использовался в окне 30 дней |
| `architect/legal-compliance` | 26 | 1841 | dead | не использовался в окне 30 дней |
| `architect/observability-design` | 32 | 1315 | dead | не использовался в окне 30 дней |
| `architect/package-contribution-protocol` | 106 | 1857 | dead | не использовался в окне 30 дней |
| `architect/security-design` | 38 | 2151 | dead | не использовался в окне 30 дней |
| `architect/tech-stack-selection` | 32 | 1889 | dead | не использовался в окне 30 дней |
| `azguard/azguard` | 37 | 1679 | dead | не использовался в окне 30 дней |
| `blender/mcp-blender` | 118 | 1503 | dead | не использовался в окне 30 дней |
| `blender/version-gotchas` | 22 | 784 | dead | не использовался в окне 30 дней |
| `blender-modeling/build-loop` | 128 | 2137 | dead | не использовался в окне 30 дней |
| `blender-modeling/config-conventions` | 114 | 2219 | dead | не использовался в окне 30 дней |
| `blender-modeling/model-rules` | 31 | 761 | dead | не использовался в окне 30 дней |
| `blender-modeling/parametric-config` | 111 | 2196 | dead | не использовался в окне 30 дней |
| `blender-modeling/scene-conventions` | 95 | 914 | dead | не использовался в окне 30 дней |
| `blender-modeling/threading` | 27 | 660 | dead | не использовался в окне 30 дней |
| `botkit/botkit` | 29 | 234 | dead | не использовался в окне 30 дней |
| `creative/content-creative-super-skill` | 155 | 26240 | thin | не использовался в окне 30 дней |
| `devops/ci-cd` | 55 | 1150 | keep | 1× за 30 дней |
| `devops/db-test-preflight` | 104 | 1703 | keep | 1× за 30 дней |
| `devops/docker` | 66 | 400 | dead | не использовался в окне 30 дней |
| `devops/docker-dev-prod` | 42 | 952 | dead | не использовался в окне 30 дней |
| `devops/docker-php` | 40 | 794 | dead | не использовался в окне 30 дней |
| `devops/docker-postgres` | 43 | 834 | dead | не использовался в окне 30 дней |
| `devops/docker-services` | 48 | 885 | dead | не использовался в окне 30 дней |
| `devops/docker-vite` | 39 | 706 | dead | не использовался в окне 30 дней |
| `devops/gitops` | 30 | 743 | dead | не использовался в окне 30 дней |
| `devops/makefile` | 43 | 759 | dead | не использовался в окне 30 дней |
| `devops/node-pnpm-preflight` | 38 | 255 | dead | не использовался в окне 30 дней |
| `finance/finance-super-skill` | 179 | 21503 | thin | не использовался в окне 30 дней |
| `founder/adversarial-check` | 55 | 1162 | dead | не использовался в окне 30 дней |
| `founder/competitive-analysis` | 30 | 1343 | dead | не использовался в окне 30 дней |
| `founder/customer-discovery` | 55 | 1315 | dead | не использовался в окне 30 дней |
| `founder/defensibility` | 42 | 1151 | dead | не использовался в окне 30 дней |
| `founder/idea-audit` | 61 | 2502 | dead | не использовался в окне 30 дней |
| `founder/idea-discovery` | 35 | 1668 | dead | не использовался в окне 30 дней |
| `founder/new-project` | 28 | 1387 | dead | не использовался в окне 30 дней |
| `founder/pitch-deck` | 26 | 1583 | dead | не использовался в окне 30 дней |
| `founder/risk-assessment` | 32 | 1302 | dead | не использовался в окне 30 дней |
| `founder/startup-lifecycle` | 42 | 1775 | dead | не использовался в окне 30 дней |
| `frontend/document-writer` | 88 | 1283 | dead | не использовался в окне 30 дней |
| `frontend/filepond-upload` | 136 | 2242 | dead | не использовался в окне 30 дней |
| `frontend/web-design-guidelines` | 61 | 270 | dead | не использовался в окне 30 дней |
| `frontend-animations/motion` | 55 | 920 | dead | не использовался в окне 30 дней |
| `frontend-backend/backend-type-sync` | 100 | 2075 | dead | не использовался в окне 30 дней |
| `frontend-backend/inertia-vue` | 58 | 1485 | dead | не использовался в окне 30 дней |
| `frontend-backend/laravel-echo-client` | 130 | 1928 | dead | не использовался в окне 30 дней |
| `frontend-figma/figma-to-vue` | 99 | 813 | dead | не использовался в окне 30 дней |
| `frontend-linting/antfu` | 74 | 1282 | dead | не использовался в окне 30 дней |
| `frontend-linting/eslint-flat-config` | 112 | 2411 | dead | не использовался в окне 30 дней |
| `frontend-linting/js-code-style` | 47 | 870 | dead | не использовался в окне 30 дней |
| `frontend-linting/ts-library` | 90 | 1357 | dead | не использовался в окне 30 дней |
| `frontend-naive-ui/naive-ui-theming` | 103 | 2041 | dead | не использовался в окне 30 дней |
| `frontend-nuxt/nuxt` | 80 | 1095 | dead | не использовался в окне 30 дней |
| `frontend-nuxt/nuxt-modules` | 125 | 644 | dead | не использовался в окне 30 дней |
| `frontend-nuxt/nuxt-seo` | 50 | 825 | dead | не использовался в окне 30 дней |
| `frontend-reka/reka-ui-cva` | 105 | 2007 | dead | не использовался в окне 30 дней |
| `frontend-tailwind/dark-mode` | 113 | 2209 | dead | не использовался в окне 30 дней |
| `frontend-tailwind/tailwind-conventions` | 127 | 2249 | dead | не использовался в окне 30 дней |
| `frontend-vite/vite` | 57 | 615 | dead | не использовался в окне 30 дней |
| `frontend-vite/vite-module-loader` | 27 | 692 | dead | не использовался в окне 30 дней |
| `frontend-vite/vite-multi-build` | 47 | 1013 | dead | не использовался в окне 30 дней |
| `frontend-vite/vitepress` | 49 | 830 | dead | не использовался в окне 30 дней |
| `frontend-vue/pinia` | 54 | 691 | dead | не использовался в окне 30 дней |
| `frontend-vue/pinia-stores` | 128 | 1920 | dead | не использовался в окне 30 дней |
| `frontend-vue/vitest` | 47 | 817 | dead | не использовался в окне 30 дней |
| `frontend-vue/vitest-vue` | 55 | 1049 | dead | не использовался в окне 30 дней |
| `frontend-vue/vue` | 63 | 876 | dead | не использовался в окне 30 дней |
| `frontend-vue/vue-best-practices` | 99 | 2560 | dead | не использовался в окне 30 дней |
| `frontend-vue/vue-composition-api` | 80 | 531 | dead | не использовался в окне 30 дней |
| `frontend-vue/vue-dynamic-icons` | 76 | 1303 | dead | не использовался в окне 30 дней |
| `frontend-vue/vue-router-best-practices` | 141 | 2792 | dead | не использовался в окне 30 дней |
| `frontend-vue/vue-testing-best-practices` | 77 | 2367 | dead | не использовался в окне 30 дней |
| `frontend-vue/vueuse-functions` | 34 | 10838 | thin | не использовался в окне 30 дней |
| `frontend-wayfinder/wayfinder` | 48 | 994 | dead | не использовался в окне 30 дней |
| `general/anti-drift` | 43 | 1258 | dead | не использовался в окне 30 дней |
| `general/compact-responses` | 60 | 570 | dead | не использовался в окне 30 дней |
| `general/complex-task-orchestrator` | 44 | 659 | keep | 2× за 30 дней |
| `general/context-economy` | 71 | 2133 | dead | не использовался в окне 30 дней |
| `general/cross-layer-change-checklist` | 37 | 461 | dead | не использовался в окне 30 дней |
| `general/git-commit-rules` | 29 | 934 | keep | 25× за 30 дней |
| `general/git-safety` | 84 | 600 | dead | не использовался в окне 30 дней |
| `general/grill-with-docs` | 98 | 911 | dead | не использовался в окне 30 дней |
| `general/implement` | 88 | 479 | dead | не использовался в окне 30 дней |
| `general/mcp-advisor` | 107 | 1893 | dead | не использовался в окне 30 дней |
| `general/naming-conventions` | 86 | 1564 | dead | не использовался в окне 30 дней |
| `general/packages-stack` | 85 | 530 | dead | не использовался в окне 30 дней |
| `general/plan-protocol` | 43 | 1889 | dead | не использовался в окне 30 дней |
| `general/project-map` | 83 | 645 | dead | не использовался в окне 30 дней |
| `general/session-handoff` | 41 | 618 | dead | не использовался в окне 30 дней |
| `general/skills-ssot` | 35 | 1771 | dead | не использовался в окне 30 дней |
| `general/spec-interview` | 58 | 753 | dead | не использовался в окне 30 дней |
| `general/task-brief-template` | 79 | 1253 | keep | 1× за 30 дней |
| `general/verify-claims` | 133 | 2696 | dead | не использовался в окне 30 дней |
| `general/writing-style` | 98 | 1702 | dead | не использовался в окне 30 дней |
| `laravel-architecture/config-driven-abstraction` | 135 | 487 | dead | не использовался в окне 30 дней |
| `laravel-architecture/eloquent-accessors` | 119 | 1255 | dead | не использовался в окне 30 дней |
| `laravel-architecture/enum-attributes` | 131 | 1977 | dead | не использовался в окне 30 дней |
| `laravel-architecture/enum-state-machine` | 132 | 1585 | dead | не использовался в окне 30 дней |
| `laravel-architecture/laravel-subagents` | 77 | 1287 | dead | не использовался в окне 30 дней |
| `laravel-architecture/modular-architecture` | 83 | 3139 | dead | не использовался в окне 30 дней |
| `laravel-auth/attribute-authorization` | 83 | 2129 | dead | не использовался в окне 30 дней |
| `laravel-auth/laravel-permissions` | 68 | 426 | dead | не использовался в окне 30 дней |
| `laravel-auth/laravel-security-audit` | 51 | 803 | dead | не использовался в окне 30 дней |
| `laravel-data-layer/laravel-broadcasting` | 40 | 1257 | keep | 1× за 30 дней |
| `laravel-data-layer/laravel-data` | 120 | 2057 | dead | не использовался в окне 30 дней |
| `laravel-extras/medialibrary` | 33 | 1048 | dead | не использовался в окне 30 дней |
| `laravel-extras/pennant-development` | 58 | 505 | dead | не использовался в окне 30 дней |
| `laravel-extras/spatie-settings` | 134 | 2704 | dead | не использовался в окне 30 дней |
| `laravel-filament/filament` | 63 | 2374 | retrieval-only | 1× за 30 дней |
| `laravel-livewire/livewire-blade-attributes` | 128 | 1283 | dead | не использовался в окне 30 дней |
| `laravel-testing/health-checks` | 129 | 2325 | dead | не использовался в окне 30 дней |
| `laravel-testing/laravel-dusk` | 34 | 1008 | dead | не использовался в окне 30 дней |
| `laravel-testing/laravel-testing` | 56 | 3061 | dead | не использовался в окне 30 дней |
| `laravel-testing/test-isolation-guard` | 104 | 1599 | dead | не использовался в окне 30 дней |
| `legal/legal-super-skill` | 145 | 29249 | thin | не использовался в окне 30 дней |
| `marketing/marketing-super-skill` | 142 | 16617 | thin | не использовался в окне 30 дней |
| `mobile/figma-to-flutter` | 107 | 867 | dead | не использовался в окне 30 дней |
| `operator/capacity-planning` | 41 | 2083 | dead | не использовался в окне 30 дней |
| `operator/incident-response` | 41 | 1845 | dead | не использовался в окне 30 дней |
| `operator/oncall-rotation` | 37 | 1708 | dead | не использовался в окне 30 дней |
| `operator/operations-cx-super-skill` | 98 | 22355 | merge | не использовался в окне 30 дней |
| `operator/postmortem` | 43 | 1929 | dead | не использовался в окне 30 дней |
| `operator/runbook` | 36 | 1748 | dead | не использовался в окне 30 дней |
| `oss-dev/dependency-audit` | 33 | 1160 | dead | не использовался в окне 30 дней |
| `oss-dev/dx-design` | 31 | 1237 | dead | не использовался в окне 30 дней |
| `oss-dev/gh-review` | 77 | 1162 | dead | не использовался в окне 30 дней |
| `oss-dev/github-flow` | 71 | 2090 | dead | не использовался в окне 30 дней |
| `oss-dev/issue-triage` | 114 | 2163 | dead | не использовался в окне 30 дней |
| `oss-dev/oss-development` | 38 | 1392 | dead | не использовался в окне 30 дней |
| `oss-dev/oss-governance` | 31 | 1595 | dead | не использовался в окне 30 дней |
| `oss-dev/release-engineering` | 37 | 1660 | dead | не использовался в окне 30 дней |
| `oss-dev/resolving-merge-conflicts` | 103 | 335 | keep | 1× за 30 дней |
| `oss-dev/to-issues` | 92 | 1184 | dead | не использовался в окне 30 дней |
| `php/code-style-spatie` | 47 | 1127 | dead | не использовался в окне 30 дней |
| `php/cursor-pagination-design` | 136 | 412 | dead | не использовался в окне 30 дней |
| `php/database` | 51 | 961 | keep | 5× за 30 дней |
| `php/dependency-injection` | 39 | 1285 | dead | не использовался в окне 30 дней |
| `php/laravel` | 21 | 1573 | dead | не использовался в окне 30 дней |
| `php/laravel-best-practices` | 40 | 1727 | dead | не использовался в окне 30 дней |
| `php/laravel-structure` | 44 | 2020 | keep | 2× за 30 дней |
| `php/named-arguments` | 50 | 694 | dead | не использовался в окне 30 дней |
| `php/namespace-refactor-safety` | 131 | 365 | keep | 1× за 30 дней |
| `php/pao` | 59 | 654 | dead | не использовался в окне 30 дней |
| `php/php-naming-conventions` | 80 | 1426 | dead | не использовался в окне 30 дней |
| `php/php-patterns` | 25 | 2538 | dead | не использовался в окне 30 дней |
| `php/php-upgrade-checklist` | 71 | 672 | dead | не использовался в окне 30 дней |
| `php/production-readiness-checklist` | 128 | 575 | dead | не использовался в окне 30 дней |
| `php/repositories` | 31 | 1563 | keep | 4× за 30 дней |
| `php/static-analysis` | 35 | 1123 | dead | не использовался в окне 30 дней |
| `php/transactional-outbox-relay` | 134 | 585 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-compatibility` | 76 | 446 | keep | 1× за 30 дней |
| `php-packages/laravel-package-docs` | 75 | 713 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-expressive` | 114 | 578 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-generate-skill` | 84 | 804 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-release` | 68 | 382 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-scaffold` | 77 | 615 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-service-provider` | 73 | 551 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-package-testing` | 85 | 540 | dead | не использовался в окне 30 дней |
| `php-packages/laravel-packages` | 33 | 788 | dead | не использовался в окне 30 дней |
| `pm/brd` | 28 | 592 | dead | не использовался в окне 30 дней |
| `pm/business-process` | 27 | 572 | dead | не использовался в окне 30 дней |
| `pm/go-to-market` | 26 | 1325 | dead | не использовался в окне 30 дней |
| `pm/monetization-design` | 36 | 1400 | dead | не использовался в окне 30 дней |
| `pm/pm-super-skill` | 120 | 23037 | merge | не использовался в окне 30 дней |
| `pm/pmf-diagnostics` | 53 | 1413 | dead | не использовался в окне 30 дней |
| `pm/prd-from-brd` | 38 | 1441 | dead | не использовался в окне 30 дней |
| `pm/product-roadmap` | 35 | 1266 | dead | не использовался в окне 30 дней |
| `pm/requirement-critic` | 51 | 1606 | dead | не использовался в окне 30 дней |
| `pm/unit-economics` | 24 | 839 | dead | не использовался в окне 30 дней |
| `python/ml-project-structure` | 28 | 614 | dead | не использовался в окне 30 дней |
| `python/venv-dependencies` | 30 | 549 | dead | не использовался в окне 30 дней |
| `quality/code-review` | 36 | 1622 | keep | 2× за 30 дней |
| `quality/code-simplifier` | 68 | 1260 | dead | не использовался в окне 30 дней |
| `quality/diagnosing-bugs` | 106 | 2577 | dead | не использовался в окне 30 дней |
| `quality/mutation-testing` | 106 | 2580 | dead | не использовался в окне 30 дней |
| `quality/playwright-e2e` | 107 | 2544 | retrieval-only | 1× за 30 дней |
| `quality/refactoring-plan` | 33 | 1878 | dead | не использовался в окне 30 дней |
| `quality/tdd-discipline` | 100 | 1374 | dead | не использовался в окне 30 дней |
| `quality/tech-debt-audit` | 44 | 2200 | dead | не использовался в окне 30 дней |
| `quality/test-strategy` | 61 | 2274 | dead | не использовался в окне 30 дней |
| `quality/testing-safety-report` | 77 | 756 | dead | не использовался в окне 30 дней |
| `research/query-craft` | 130 | 3928 | dead | не использовался в окне 30 дней |
| `research/research-knowledge-super-skill` | 195 | 20472 | thin | не использовался в окне 30 дней |
| `roles/open-source-maintainer` | 19 | 1235 | dead | не использовался в окне 30 дней |
| `roles/solo-founder` | 17 | 1188 | dead | не использовался в окне 30 дней |
| `roles/startup-cto` | 23 | 1417 | dead | не использовался в окне 30 дней |
| `roles/tech-lead` | 21 | 1413 | dead | не использовался в окне 30 дней |
| `sales/sales-super-skill` | 143 | 25593 | thin | не использовался в окне 30 дней |
| `security/agent-security-super-skill` | 184 | 30199 | thin | не использовался в окне 30 дней |
| `system/agent-packs` | 120 | 2332 | dead | не использовался в окне 30 дней |
| `system/brain-locator` | 47 | 1337 | dead | не использовался в окне 30 дней |
| `system/cross-project-coordinator` | 83 | 1430 | dead | не использовался в окне 30 дней |
| `system/local-topology` | 62 | 1389 | dead | не использовался в окне 30 дней |
| `system/session-observer` | 117 | 1649 | dead | не использовался в окне 30 дней |
| `system/shared-memory` | 124 | 1450 | dead | не использовался в окне 30 дней |
| `system/swissknifeman-locator` | 54 | 1425 | dead | не использовался в окне 30 дней |
