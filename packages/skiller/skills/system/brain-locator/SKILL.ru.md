---
name: brain-locator
bucket: system
version: 0.1.0
description: Из проекта дойти до Brain-волта (Obsidian-доки экосистемы) — нехардкод-резолюция пути (maind/$HOME), свои доки и доки связанных проектов, синк
risk: read
persona: architect
tags: [brain, vault, docs, navigation, locator, obsidian]
requires: [local-topology]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Brain Locator (дойти до волта документации)

Применять когда: агент в **любом проекте** хочет найти базовое хранилище
документации экосистемы (**Brain-волт**, узел `docs-hub`), дойти до **своих**
доков или доков **связанного** проекта, либо понять, синхронен ли проект с
Brain. Это drill-down в один узел из карты `local-topology` — с резолюцией пути,
которая работает даже без конфига топологии.

**Маркер.** Если этот скилл подключён к проекту — проект **участвует в
doc-синхронизации с Brain**: его `docs/`/`docs-public` зеркалятся в волт
двусторонним `brain sync`. Присутствие скилла = проект «на Brain».

---

## Резолюция пути к Brain (нехардкодно)

Путь к волту машинно-специфичен — **резолвить, не хардкодить**. Лестница
приоритетов (повторяет канон `maind`: `integrations.brain.path` → проект
`id==brain` → `$MAIND_BRAIN_VAULT` → `~/Vaults/Brain`):

```bash
# A. Явный env-override (если экосистема его задаёт)
BRAIN="$MAIND_BRAIN_VAULT"

# B. Авторитетный резолвер maind (если установлен): запись brain в реестре проектов
if [ -z "$BRAIN" ] && command -v maind >/dev/null 2>&1; then
  BRAIN="$(maind projects list --json 2>/dev/null \
            | jq -r '.projects[]|select(.id=="brain").vault_path // empty')"
fi

# C. Кандидаты от $HOME (первый существующий); канонический — ~/Vaults/Brain
if [ -z "$BRAIN" ]; then
  for c in "$HOME/Vaults/Brain" "$HOME/Brain" "$HOME/Documents/Brain"; do
    [ -d "$c" ] && BRAIN="$c" && break
  done
fi

# Признак, что это действительно Brain-волт: в корне есть .projects.json и CLAUDE.md
[ -n "$BRAIN" ] && [ -f "$BRAIN/.projects.json" ] && [ -f "$BRAIN/CLAUDE.md" ] \
  && cd "$BRAIN" || echo "Brain-волт не найден: задайте \$MAIND_BRAIN_VAULT или проверьте ~/Vaults/Brain"
```

Если ни один кандидат не подошёл и `maind` нет — **сказать пользователю**, что
волт не найден, и попросить `$MAIND_BRAIN_VAULT`; не угадывать и не хардкодить.

---

## Как Brain связан с другими проектами

Brain — единый Obsidian-волт. Связь с проектами держится на четырёх вещах:

- **`.projects.json`** в корне волта — каталог проектов (генерируемый кэш):
  записи `{name, repo, vault_path, folders}`. Здесь `repo` — **абсолютный путь к
  код-репозиторию**, `vault_path` — папка проекта в волте, `folders`
  (`["docs","docs-public"]`) — синкаемые папки.
- **Control-нота** `05-Projects/<категория>/<Name>/<Name>.md` с frontmatter
  `repo:` (путь к коду) — «control tower» проекта: статус, межпроектные связи
  (`uses:`/`used_by:`), ссылки. Источник истины каталога — именно frontmatter
  этих нот (`.projects.json` из них генерируется).
- **`CLAUDE.md`** волта — человекочитаемая карта всех проектов (продукты/пакеты/
  бизнес) + персоны + триггеры vault-локальных скиллов.
- **Obsidian `[[wikilinks]]`** — связи между проектами по аудитории/данным/общим
  компонентам.

---

## Навигация: свои доки и доки связанных проектов

```bash
# 1) своя запись в каталоге — по repo == абсолютному пути текущего проекта
jq -r --arg r "$(pwd)" '.projects[]|select(.repo==$r)|.vault_path' "$BRAIN/.projects.json"

# 2) свои доки в волте: <vault_path>/docs (+ docs-public); список папок — поле folders
# 3) связанные проекты: control-нота <vault_path>/<Name>.md → frontmatter uses:/used_by:
# 4) обзор всех проектов и их связи с репозиториями
brain list
```

Доки живут **и** в репозитории (`<repo>/docs`, `<repo>/docs-public`), **и**
зеркалом в волте; `brain` держит их синхронными (двусторонний git-merge):

```bash
brain status <project>   # есть ли расхождения docs ↔ репозиторий
brain sync <project>     # синхронизировать
```

---

## Принципы

- **Read-only ориентир.** Скилл объясняет схему и читает каталог; он **не пишет**
  в волт. Изменения доков идут только через `brain sync` (как у `local-topology`).
- **Резолвить, не хардкодить.** Путь к волту — из `maind`/env/`$HOME`-кандидатов,
  никогда не зашитой строкой.
- **Не путать узлы.** Brain (`docs-hub`, Obsidian-доки) — это **не** memory-узел
  maind (демон agent-memory). Доки ≠ память; за памятью — `shared-memory`.
- **Машинно-специфичное в проект не коммитить** (`.projects.json`, абсолютные пути).

---

## Чеклист

- [ ] Путь к Brain резолвлен через `maind`/env/`$HOME`, а не захардкожен
- [ ] Своя запись найдена по `repo == $(pwd)` в `.projects.json`
- [ ] Для синка шёл через `brain status/sync`, не правил зеркала вручную
- [ ] Не перепутал docs-узел Brain с memory-узлом maind

---

## Ссылки

- `local-topology` (бакет system) — корневая карта трёх узлов; Brain = узел `docs-hub`.
- `swissknifeman-locator` (бакет system) — парный локатор узла `skills-hub`.
- `shared-memory` (бакет system) — ДРУГОЙ узел: общая память (agent-memory демон maind), не Obsidian-доки.
