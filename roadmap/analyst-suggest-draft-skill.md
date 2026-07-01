# Roadmap / Design: `analyst suggest` — cross-project паттерн → ЧЕРНОВИК скилла

**Пакет:** `packages/analyst` · **Фаза:** P4 · **Статус:** спроектировано, не реализовано
(кода нет — этот документ ведёт `/task:dev`). **Критерий внедрения:** появились накопленные
cross-project паттерны (`analyst scan` даёт непустой `index/by_pattern/`) И ручное оформление
черновика скилла «с нуля» стало повторяющимся трением.

> Прародитель этого направления — [`self-learning-memory.md`](self-learning-memory.md)
> («промо в скилл — только через человека»). `analyst suggest` — последний недостающий шаг
> цикла: детерминированный мост **паттерн → staged-черновик `SKILL.ru.md`**, который человек
> дорабатывает и промоутит. `analyst-capture` (P5, PostToolUse-поток) — ВНЕ scope этого документа.

---

## 1. Проблема

`analyst scan` (P2) находит межпроектные паттерны уроков и останавливается на
`suggestions/<id>.md` — **человекочитаемом draft-МД, но НЕ скилле**
([`scan.py:133-152` `_suggestion_md`](../packages/analyst/lib/analyst/scan.py)). Между «нашли
повторяющийся паттерн в ≥N проектах» и «есть переиспользуемый скилл в бакете» — ручная работа
с нуля: создать каталог, написать `SKILL.ru.md`, заполнить frontmatter, перенести провенанс.
Нужен детерминированный мост, **не нарушающий инвариант** «авто-запись в скиллы запрещена»
([`analyst/CLAUDE.md:18`](../packages/analyst/CLAUDE.md), `promote.py`).

**Что строим:** `analyst suggest` читает `index/by_pattern/<id>.json`, генерирует **staged-черновик**
`SKILL.ru.md` + провенанс-паспорт в `~/.swissknifeman/analyst/drafts/<pattern_id>/` (НЕ в `skills/`),
печатает точную инструкцию промоута. Человек дорабатывает и вносит в бакет своими руками.

---

## 2. Поток данных (вход → выход)

```
scan (P2)                      suggest (P4, ЭТОТ документ)              человек (гейт)
─────────                      ────────────────────────────            ──────────────
index/by_pattern/<id>.json ──▶ читает ТОЛЬКО индекс (не raw-уроки) ──▶  дорабатывает SKILL.ru.md
  {pattern_id, namespace,        pattern→draft (чистый генератор)         ↓
   projects[], weight,           ↓                                        cp -r в skills/<bucket>/<name>/
   lessons, representative,      drafts/<pattern_id>/                     ↓
   members[], generated_at}        ├ SKILL.ru.md   (RU-источник-заготовка) генерит SKILL.md (промт)
                                   └ draft.meta.json (провенанс+seed-hash)  ↓ check-translations → validate → registry
```

**Ключевой приватностный факт:** индекс `by_pattern/` — это уже *абстрагированная проекция*
(scan сохраняет только `trigger`/`action`/`kind`, не сырьё; сырьё — LOCAL-only per-project,
[`analyst/CLAUDE.md:55-56`](../packages/analyst/CLAUDE.md)). `suggest` читает **только индекс** и
никогда не трогает per-project `lessons/*.json` → приватность наследуется **структурно**, а не
дисциплиной. (См. инвариант-таблицу §7.)

---

## 3. Решения (D1–D7)

### D1 — Вход: pattern-first. **Вердикт: только паттерн из `index/by_pattern/`.**

- `analyst suggest <pattern_id>` — один паттерн; `--all` — по всем паттернам индекса.
- **Одиночный curated-урок как вход — НЕТ.** Обоснование: `scan` уже отобрал повторяемость
  (паттерн = кластер в ≥`min_projects` проектах, дефолт 3 —
  [`scan.py`](../packages/analyst/lib/analyst/scan.py)); «достойно скилла» = межпроектный сигнал.
  Одиночный урок такого сигнала не несёт и завалил бы staging шумом. Путь «урок → скилл» — это
  территория `analyst-capture` (P5), не suggest.
- Вход строго из `env.state_dir/index/by_pattern/` (cross-project слой), namespace уже вшит в
  поле индекса → изоляция наследуется без доп. логики.

### D2 — Где живут черновики: каталог, не файл. **Вердикт: `~/.swissknifeman/analyst/drafts/<pattern_id>/`.**

- Рядом с `suggestions/` (тот же `state_dir`), **НЕ в `skills/`** (инвариант «не писать в скиллы»).
- **Каталог, а не одиночный файл** — потому что целевая форма скилла и есть каталог
  (`skills/<bucket>/<name>/` = `SKILL.ru.md` + `SKILL.md` + `snippets/` + `evals/`, подтверждено
  раскладкой skiller). Staging-каталог **зеркалит целевую форму** → человек кладёт рядом `snippets/`
  и делает `cp -r drafts/<id>/. skills/<bucket>/<name>/` одной командой. Одиночный файл не вместил бы
  провенанс-сайдкар чисто и сломал бы этот перенос.
- Состав каталога:
  ```
  ~/.swissknifeman/analyst/drafts/<pattern_id>/
    ├── SKILL.ru.md       # RU-источник-заготовка (см. §5) — человек правит
    └── draft.meta.json   # провенанс + seed_sha256 (детект ручных правок) — генерится
  ```

### D3 — Формат черновика: только `SKILL.ru.md` + заготовка frontmatter. **Вердикт ниже.**

- Генерим **только `SKILL.ru.md`** (RU — SSOT-источник, его правит человек). **EN `SKILL.md` НЕ
  генерим** — это делает человек промтом `claude-canon-from-ru.md` ПОСЛЕ доработки (см. §6). suggest,
  сгенерив EN, нарушил бы двуязычную модель (EN-канон должен вытекать из финального RU, не из
  сырой заготовки).
- **frontmatter — ЗАГОТОВКА** с полями skiller
  (`name·bucket·version·description·risk·persona·tags·requires·produces_for·outputs`,
  [`skiller/CLAUDE.md`](../packages/skiller/CLAUDE.md)):
  - `name` — kebab-slug из `representative` **без хэша** (candidate; человек финализирует так, чтобы
    == имя финального каталога). Лимит `≤64`, только lowercase/цифры/дефисы, **не начинается и не
    заканчивается дефисом**, без reserved `claude`/`anthropic` (офиц. спека, §Проверка) → генератор
    slug'а обязан тримить ведущие/хвостовые дефисы.
  - `bucket` — **`TODO`-плейсхолдер** (или значение `--bucket`). **namespace→bucket авто-маппинга НЕТ**:
    namespace (`axioma`/`swissknifeman`) — группа изоляции, bucket (`general`/`php`/`architect`…) —
    тема; это ортогональные оси, авто-угадывать нельзя. suggest **печатает список доступных бакетов**
    (из `skiller buckets.json`, если достижим) как подсказку — **выбирает человек**.
  - `description` — draft из `representative.action`/`trigger`, **мягкий таргет ≤150 симв**
    (резидентный tier-0; НЕ хард-лимит — см. §Проверка: skiller warn ≤450, офиц. спека ≤1024).
  - `risk` — консервативный дефолт `read` + `# TODO: уточни (read|draft|write|external)`.
  - `version` — `0.1.0`; остальные (`persona`/`tags`/`requires`/`produces_for`/`outputs`) — пустые.
- **Тело** (RU) — из индекса, **АБСТРАГИРОВАННО** (без raw/session-evidence/секретов — их в индексе
  и нет):
  - блок «Контекст»: `representative` trigger→action + «повторился в N проектах namespace <ns>: X,Y,Z»;
  - «Наблюдённые экземпляры»: `members[]` как `проект → trigger` (абстрагированные строки);
  - «Алгоритм»/«Чеклист» — `TODO`-скелет (человек оформляет action в переиспользуемые шаги).

### D4 — Провенанс: сайдкар `draft.meta.json` + инертный штамп в теле. **Вердикт ниже.**

- Внутренний источник (не вендоринг) → `upstream.json` **НЕ нужен** (он для внешних скиллов).
- **Паспорт черновика — `draft.meta.json`** (atomic JSON, house-паттерн `core.atomic_write_json`):
  ```json
  {
    "schema_version": 1,
    "generated_by": "analyst suggest",
    "pattern_id": "<id>",
    "namespace": "<ns>",
    "projects": ["X", "Y", "Z"],
    "weight": 3,
    "lessons": 5,
    "source_index": "index/by_pattern/<id>.json",   // относительно state_dir
    "seed_sha256": "<sha256 сгенерированного тела SKILL.ru.md>",
    "generated_at": "<ISO, core.now_iso>"
  }
  ```
  `seed_sha256` — служит детекту ручных правок (см. D6, идемпотентность); `source_index` — обратный
  указатель на паттерн.
- **Плюс инертный штамп** в самом `SKILL.ru.md` — HTML-комментарий (зеркалит идиому skiller
  `<!-- ru-source-sha256: … -->`), чтобы провенанс путешествовал с файлом даже без сайдкара, но не
  попадал в тело скилла:
  ```
  <!-- analyst-provenance: сгенерировано `analyst suggest` из pattern <id> · ns <ns> ·
       N проектов (X,Y,Z) · M уроков · <generated_at>. Источник: index/by_pattern/<id>.json.
       УДАЛИ этот блок перед промоутом. -->
  ```
  SSOT провенанса — `draft.meta.json`; штамп — переносимая копия, человек снимает на финализации.

### D5 — Human-гейт / handoff: suggest НЕ трогает реестр и `skills/`. **Вердикт: точный стык ниже.**

`suggest` печатает **repo-grounded** инструкцию (не угадывает). Проверено чтением
`packages/skiller`:

> **⚠ Корректировка существующего кода:** `scan.py:139` (`_suggestion_md`) указывает
> «Промоут в скилл — человек (`skiller integrate`, фаза P4)». Это **неточно**:
> `cmd_integrate` ([`skiller/lib/skiller/integrate.py:365`](../packages/skiller/lib/skiller/integrate.py))
> — визард, который **вшивает скиллы В проект** (connect/vendor), а НЕ регистрирует новый скилл в
> реестре. `suggest` печатает **правильную** последовательность (ниже), и P4 должен заодно
> поправить строку `scan.py:139`. → [POSSIBLE-DEFECT #1].

**Точная последовательность промоута черновика (repo-grounded):**

1. `mkdir -p skills/<bucket>/<name>/snippets` и перенести туда доработанный `SKILL.ru.md`
   (имя каталога `<name>` == `frontmatter.name`, kebab-case).
2. Сгенерировать EN-канон: прогнать промт
   [`packages/skiller/prompts/generate/claude-canon-from-ru.md`](../packages/skiller/prompts/generate/claude-canon-from-ru.md)
   над `SKILL.ru.md` → получить `SKILL.md`. **Это агент/человек, CLI-автогенерации НЕТ.**
3. `bash packages/skiller/scripts/check-translations.sh --stamp` — проставить
   `<!-- ru-source-sha256 -->` (когерентность RU↔EN).
4. `bash packages/skiller/scripts/validate.sh` — гейт frontmatter/схемы.
5. (опц.) `skiller eval <bucket>/<name> --scaffold` — evals.
6. `skiller registry` — регенерит `skills.json` / `_index.md` / `marketplace.json` / графы.
7. Коммит + PR (Conventional Commits).

suggest выводит эти шаги дословно (с подставленными `<bucket>`/`<name>`), плюс путь
`drafts/<pattern_id>/` как источник. **Ни один шаг suggest не выполняет сам.**

### D6 — Идемпотентность / reconcile: перезапись безопасна к правкам; прун — warn, не delete. **Вердикт ниже.**

- **Re-suggest (идемпотентность с защитой правок):** ключевое отличие от `suggestions/*.md` (P2 их
  безопасно перегенерит/прунит, т.к. они — чисто-производные, руками не правятся). Черновик
  `SKILL.ru.md` — **рабочая копия человека**; слепая перезапись = потеря труда. Механизм (зеркалит
  sha256-маркер skiller):
  - каталога нет → создать `SKILL.ru.md` + `draft.meta.json` (`seed_sha256 = hash(тела)`);
  - каталог есть → сравнить `hash(SKILL.ru.md на диске)` с `draft.meta.json.seed_sha256`:
    - **равны** (не правили) → безопасно перегенерить тело, обновить `seed_sha256`;
    - **различны** (правили руками) → тело **НЕ перезаписывать**; обновить лишь провенанс-поля
      meta (projects/weight/lessons могли измениться) + `warn`: «черновик правился вручную — тело не
      тронуто; `--force` чтобы пересеять».
  - `--force` → перезаписать безусловно.
- **Reconcile осиротевших черновиков — WARN, НЕ авто-delete.** Осиротевший черновик = `drafts/<id>/`,
  чьего паттерна больше нет в индексе. В отличие от P2 scoped-prune (`scan.py`
  `stale_pattern_ids`/`prune_artifacts`, который **удаляет** чисто-производные `suggestions`/`index`),
  черновики — человеко-редактируемы → авто-удаление нарушает least-surprise. Решение: при `--all`
  suggest **сверяет `drafts/` c текущим индексом и печатает WARN** со списком осиротевших (+ подсказку
  удалить вручную), но **не удаляет**. Согласованность-по-духу с P2 (scoped, namespace-aware)
  сохранена, но действие понижено delete→warn. Явный opt-in cleanup (`--prune-drafts`) — отложен.
  → [ADR-1] (спорно против симметрии с P2).

### D7 — Числовые гейты (связь с P3): default = все, opt-in `--min-weight`. **Вердикт ниже.**

- По умолчанию suggest работает по **всем** паттернам, что дал scan (они уже прошли `min_projects≥3`).
- Опц. `--min-weight N` поднимает планку по полю `weight` (= число проектов, present в индексе).
- **`--min-tier` — ОТЛОЖЕН (repo-grounded причина).** Индекс паттерна **не несёт confidence/tier**:
  `by_pattern/<id>.json` имеет `weight`/`lessons`, а `members[]` — только `{project, id, trigger}`
  (подтверждено `scan.py` `detect_patterns`). Confidence живёт per-lesson (P3,
  [`confidence.py`](../packages/analyst/lib/analyst/confidence.py), тиры 0.3/0.5/0.7/0.9). `--min-tier`
  потребовал бы обратного чтения member-уроков из per-project стора — а это ломает инвариант «suggest
  читает только индекс» (§2, приватность/простота). → [POSSIBLE-DEFECT #2]: когда P3 начнёт штамповать
  агрегат-confidence в индекс паттерна, `--min-tier` станет дешёвым — тогда добавить.
- **Churn-осторожность (как в P2):** при `--all` печатать число черновиков к записи и уважать
  `--dry-run` (ничего не пишем, только отчёт).

---

## 4. CLI-контракт

Мирроит стиль `cmd_scan`/`cmd_digest`/`cmd_promote` (`parse_args` из `core`, `opts["help"]`-гейт,
positional через `max_pos`, `--json`/`--dry-run`, русские сообщения, `die`→exit 1):

```
analyst suggest [<pattern_id>] [--all] [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
```

| Аргумент | Тип | Смысл |
|:--|:--|:--|
| `<pattern_id>` | positional (`max_pos=1`) | один паттерн из `index/by_pattern/`; взаимоисключим с `--all` |
| `--all` | bool | по всем паттернам индекса (+ warn об осиротевших черновиках, D6) |
| `--bucket B` | str | подставить bucket в заготовку frontmatter (иначе `TODO` + подсказка) |
| `--min-weight N` | str→int | только паттерны с `weight ≥ N` (D7) |
| `--dry-run` | bool | отчёт без записи (churn-safety) |
| `--json` | bool | машиночитаемый вывод (как `scan`) |
| `--force` | bool | перезаписать тело даже если черновик правился вручную (D6) |

**Скелет обработчика** (форма, не итоговый код — его пишет `/task:dev`):

```python
def cmd_suggest(env, argv):
    opts, pos = parse_args(argv, {"--all": "bool", "--bucket": "str", "--min-weight": "str",
                                  "--dry-run": "bool", "--json": "bool", "--force": "bool"},
                           max_pos=1)
    if opts["help"] or (not pos and not opts["all"]):
        print("analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] "
              "[--dry-run] [--json] [--force]\n"
              "  Cross-project паттерн → ЧЕРНОВИК SKILL.ru.md в ~/.swissknifeman/analyst/drafts/.\n"
              "  НЕ пишет в skills/, НЕ генерит EN, НЕ регистрирует. Промоут — человек.")
        return
    if pos and opts["all"]:
        die("укажи <pattern_id> ЛИБО --all, не оба")
    # 1. читать индекс(ы) из env.state_dir/index/by_pattern (safe_load_json)
    # 2. фильтр по --min-weight
    # 3. ЧИСТЫЙ генератор: pattern(dict) -> (skill_ru_text, meta_dict)   # тестируемо, без I/O
    # 4. если --dry-run/--json: отчёт и выход (ничего не пишем)
    # 5. IO: для каждого паттерна — edit-safe запись (D6) в drafts/<pattern_id>/
    #    atomic_write_text(SKILL.ru.md), atomic_write_json(draft.meta.json)
    # 6. печать handoff-инструкции (D5) + (при --all) warn об осиротевших (D6)
```

Регистрация: `COMMANDS["suggest"] = cmd_suggest` в
[`cli.py`](../packages/analyst/lib/analyst/cli.py); плагин-команда `/analyst:suggest` в
[`commands/analyst.md`](../packages/analyst/commands/analyst.md); строка в `README`/`CHANGELOG`;
после правок плагина — `skiller registry` (analyst подхватывается как соседний пакет).

**Модель кода** (как в пакете): **чистый генератор** `build_draft(pattern) -> (ru_text, meta)`
(без I/O/часов — тестируемо по точкам) + writer в `cmd_suggest` (весь I/O только здесь), ровно как
`digest.extract_candidates` (чистый) ↔ `cmd_digest` (I/O).

---

## 5. Схема draft-артефакта

**`drafts/<pattern_id>/SKILL.ru.md`** (заготовка; `<...>` — подстановки из паттерна):

```markdown
---
name: <kebab-slug из representative, без хэша>   # ≤64, без claude/anthropic; человек финализирует (== имя каталога)
bucket: <--bucket или TODO>                       # namespace≠bucket: выбирает человек (см. подсказку в выводе)
version: 0.1.0
description: "<action> — <trigger> (черновик; ≤150 симв, правит человек)"
risk: read                                        # TODO: уточни (read|draft|write|external)
persona: ""
tags: []
requires: []
produces_for: []
outputs: []
---
<!-- analyst-provenance: сгенерировано `analyst suggest` из pattern <id> · ns <ns> ·
     N проектов (X,Y,Z) · M уроков · <generated_at>. Источник: index/by_pattern/<id>.json.
     УДАЛИ этот блок перед промоутом. -->

# <Название> (черновик)

## Контекст (когда применять)
Паттерн повторился в **N проектах** namespace `<ns>`: X, Y, Z.
- **trigger:** <representative.trigger>
- **action:**  <representative.action>
- **kind:**    <representative.kind>

## Наблюдённые экземпляры (абстрагировано)
- `X` — <trigger>
- `Y` — <trigger>
- `Z` — <trigger>

## Алгоритм
TODO — оформи action в переиспользуемые шаги.

## Чеклист
TODO
```

**`drafts/<pattern_id>/draft.meta.json`** — схема из D4.

---

## 6. Что `suggest` НЕ делает (инвариант-таблица)

| Инвариант | Как удержан |
|:--|:--|
| **Не пишет в `skills/`** | Пишет только в `~/.swissknifeman/analyst/drafts/` (state_dir). Промоут — руки человека (D5). |
| **Не генерит EN `SKILL.md`** | Генерит только RU-источник-заготовку; EN — человек промтом `claude-canon-from-ru.md` после доработки (D3). |
| **Не авто-регистрирует** | Не зовёт `skiller registry`/`integrate`/`connect`/`sync`; не трогает `skills.json`/`marketplace.json` (D5). |
| **Не раскрывает raw/секреты** | Читает ТОЛЬКО `by_pattern/` индекс (уже абстрагированная проекция); per-project raw-уроки не открывает — приватность структурная (§2). |
| **Не перезаписывает правки человека** | seed_sha256-детект: правленое тело не трогаем без `--force` (D6). |
| **Не удаляет черновики авто** | Осиротевшие — warn, не delete (D6, ≠ P2 prune). |
| **Не нарушает namespace-изоляцию** | namespace вшит в поле индекса паттерна; suggest его лишь читает (§2). |

---

## 7. Связи

- **P2 (`scan` reconcile):** suggest **потребляет** артефакты scan (`index/by_pattern/`). Симметрию
  scoped-prune **сознательно не копирует** для черновиков (delete→warn, D6/ADR-1), т.к. черновики
  человеко-редактируемы, а `suggestions`/`index` — чисто-производные.
- **P3 (confidence):** `--min-tier` отложен — индекс паттерна не несёт confidence (D7 / POSSIBLE-DEFECT #2).
  Пока гейт — по `weight` (число проектов).
- **skiller (handoff):** repo-grounded, по коду `integrate.py`/`registry.py`/`prompts/generate/` +
  `check-translations.sh`/`validate.sh` (D5). Правка `scan.py:139` — часть P4 (POSSIBLE-DEFECT #1).

---

## 8. ADR / спорное

### ADR-1: reconcile осиротевших черновиков — warn, не auto-delete

- **Контекст:** P2 scan прунит осиротевшие `suggestions`/`index` scoped-удалением. Симметрия
  требовала бы того же для `drafts/`.
- **Решение:** для `drafts/` — **warn-only** (delete отложен в opt-in `--prune-drafts`).
- **Альтернативы:** (A) scoped auto-delete как P2 — **отклонено**: черновик правится человеком,
  удаление = потеря труда, least-surprise. (B) не сверять вовсе — **отклонено**: тихое накопление
  мусора; warn дёшев и безопасен.
- **Последствия:** возможен ручной clutter в `drafts/`; лечится будущим `--prune-drafts` по факту
  трения (принцип roadmap: не на упреждение).

### [POSSIBLE-DEFECT] реестр

1. **`scan.py:139`** указывает `skiller integrate` как путь промоута — неверно (integrate вшивает
   скиллы в проект, не регистрирует). P4 печатает корректную последовательность (D5) и правит строку.
2. **`--min-tier` невозможен** без confidence в индексе паттерна (D7). Обходка: гейт по `weight`.
   Настоящий фикс — P3 штампует агрегат-confidence в `by_pattern/<id>.json`, тогда `--min-tier`
   дешёв. Помечено как будущая работа, не костыль.

---

## Рамки (для `/task:dev`)

- **stdlib-only** — генератор `build_draft` без pip (форматирование строк + `hashlib`/`json` stdlib).
- **`Env(BaseEnv)` явно** (frozen), пути через `env.state_dir`; **atomic JSON/text** (`core.io`).
- **Русские сообщения** (`die`/`warn`); чистый генератор ↔ I/O в `cmd_` (как digest/promote).
- **Не нарушать** инвариант «авто-запись в скиллы запрещена» и приватность (raw LOCAL).
- **Не ломать** детерминизм/namespace-изоляцию scan; suggest читает только индекс.
- **DoD-хвост:** `scripts/validate.sh` зелёный; `CHANGELOG [Unreleased]`; `commands/analyst.md`
  + `skiller registry`; тесты (чистый генератор по точкам + edit-safety re-suggest + `--dry-run`
  ничего не пишет + namespace в meta).

---

## Проверка

- **Внешнее (верифицировано RAG — ДВА независимых движка сошлись: `perplexity-web` + `WebSearch` по
  офиц. докам Anthropic Agent Skills, 2026-07):** frontmatter скилла — обязательны
  `name`/`description`; `name` **≤64** симв (только lowercase/цифры/дефисы, **не начинается/не
  заканчивается дефисом**, без reserved `anthropic`/`claude`, == имя каталога); `description`
  **≤1024** симв (3-е лицо, non-empty, без XML). **`≤150` — НЕ офиц. лимит**, а конвенция
  резидентности; в skiller своя планка **warn ≤450**
  ([`validate.sh`](../packages/skiller/scripts/validate.sh)), таргет ~150-400 для tier-0. В дизайне
  `≤150` — мягкий таргет заготовки, не гейт. (Лестница `decision-verification` пройдена корректно:
  `perplexity-web` до `WebSearch`; первичный проход шёл через субагента с одним `WebSearch` —
  ступень perplexity-web добита отдельно, факт подтверждён двумя движками.)
- **Repo-grounded (подтверждено чтением кода):** схема `by_pattern/<id>.json` и
  `_suggestion_md`/`write_artifacts` ([`scan.py`](../packages/analyst/lib/analyst/scan.py));
  идиома `cmd_*`/`parse_args(max_pos)` ([`cli.py`](../packages/analyst/lib/analyst/cli.py),
  [`digest.py`](../packages/analyst/lib/analyst/digest.py), `promote.py`); human-гейт + `_fact_text`
  приватность (`promote.py`); тиры confidence 0.3/0.5/0.7/0.9
  ([`confidence.py`](../packages/analyst/lib/analyst/confidence.py)); `Env.state_dir`
  ([`common.py`](../packages/analyst/lib/analyst/common.py)); frontmatter-поля + двуязычный поток +
  `claude-canon-from-ru.md`/`check-translations.sh`/`registry`/`integrate`
  ([`skiller/CLAUDE.md`](../packages/skiller/CLAUDE.md), `integrate.py`, `registry.py`).
- **Непроверенного, требующего повторного прохода, — нет** (движки были доступны). Спорное вынесено
  в ADR-1; два [POSSIBLE-DEFECT] помечены с планом фикса.
