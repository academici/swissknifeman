---
name: local-topology
bucket: system
version: 0.1.0
description: Корневая карта локальной среды разработки — три узла-хаба (Brain-волт, swissknifeman, база проектов) и навигация между проектами, их кодом и документацией. Читается из ~/.swissknifeman/topology.json
risk: read
persona: architect
tags: [topology, architecture, navigation, meta]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Local Topology (корневая карта среды)

Применять когда: нужно понять, **где** в этой системе лежат узлы, дойти до
**соседнего проекта** (его кода или документации), либо объяснить пользователю
общую схему. Это корневой скилл — точка входа в навигацию по всей локальной
среде. Любой агент в любом подключённом проекте может через него понять, что
где работает.

---

## Топология: три узла-хаба

Локальная среда — это **три ключевых узла**, соединённых по двум линиям
(документация и скиллы/хуки):

| Узел | Роль | Что даёт |
|:---|:---|:---|
| **Brain-волт** (`docs-hub`) | Единая точка документации | Obsidian-волт; CLI `brain` + `docs-watcher` синкают `docs/`/`docs-public` между волтом и репозиториями в обе стороны (git-merge) |
| **swissknifeman** (`skills-hub`) | Единая точка скиллов/хуков | Реестр скиллов; раздаёт их в проекты (marketplace/vendor), несёт глобальные хуки и пресеты permissions |
| **База проектов** (`workspace`) | Где лежит код | Каталог с репозиториями всех проектов (структура произвольная) |

Узлы **не знают друг про друга** напрямую — связующим звеном служит
конфиг топологии (см. ниже). Brain находит проекты по frontmatter `repo:` в
своих заметках; swissknifeman — по `~/.swissknifeman/projects.json`. Карта
топологии даёт верхнеуровневую точку, от которой можно дойти до любого узла.

---

## Резолв узлов: `~/.swissknifeman/topology.json`

Единственный источник истины о расположении узлов — файл
**`~/.swissknifeman/topology.json`**. Схема:

```json
{
  "version": 1,
  "nodes": {
    "brain":         { "path": "/home/<user>/Vaults/Brain",            "role": "docs-hub" },
    "swissknifeman": { "path": "/home/<user>/projects/packages/swissknifeman", "role": "skills-hub" },
    "projects_base": { "path": "/home/<user>/projects",                "role": "workspace" }
  },
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

Прочитать пути (примеры `jq`):

```bash
# все узлы
jq -r '.nodes | to_entries[] | "\(.key)\t\(.value.path)\t(\(.value.role))"' \
  ~/.swissknifeman/topology.json

# отдельный узел
jq -r '.nodes.brain.path'         ~/.swissknifeman/topology.json
jq -r '.nodes.projects_base.path' ~/.swissknifeman/topology.json
```

Или через CLI (человекочитаемо / JSON):

```bash
swissknifeman topology show
swissknifeman topology show --json
```

**Если файла нет** — топология ещё не настроена на этой машине. Создать
интерактивно (спросит пути к Brain-волту, swissknifeman и базе проектов,
с авто-детектом дефолтов):

```bash
swissknifeman topology init
```

---

## Навигация

Имея пути узлов, можно дойти до чего угодно:

**До соседнего проекта (код).** `projects_base` → каталог проекта. Список
проектов, известных swissknifeman:

```bash
jq -r '.projects[].path' ~/.swissknifeman/projects.json   # подключённые к реестру
ls "$(jq -r '.nodes.projects_base.path' ~/.swissknifeman/topology.json)"
```

**До документации любого проекта.** Brain — единая точка. Документация живёт
и в репозитории проекта (`<repo>/docs`, `<repo>/docs-public`), и зеркалом в
волте; `brain` держит их синхронными:

```bash
brain list                  # все проекты волта и их связь с репозиториями
brain status <project>      # есть ли расхождения docs ↔ репозиторий
brain sync <project>        # синхронизировать (двусторонний git-merge)
```

**До скиллов/хуков/конфигов.** Узел swissknifeman:

```bash
swissknifeman list          # какие проекты к чему подключены
swissknifeman status        # состояние текущего проекта
# скиллы — skills/<bucket>/, хуки и пресеты — configs/claude-code/
```

Подключение нового проекта к раздаче скиллов — `swissknifeman connect`
(Claude Code, plugin marketplace) или `swissknifeman vendor` (Cursor и др.).

---

## Принципы

- **Карта — read-only ориентир.** Этот скилл объясняет схему и читает
  `topology.json`; он **не меняет** узлы и не переписывает конфиг. Создание/
  правка конфига — только через `swissknifeman topology init`.
- **Пути машинно-специфичны.** `topology.json` живёт в `$HOME`, не в
  репозитории, и у каждой машины свой — как `.projects.json` у Brain. Не
  коммить его в проекты.
- **Узлы автономны.** Brain и swissknifeman работают и без карты; карта лишь
  даёт агентам общую точку, чтобы видеть всю схему и переходить между узлами.

---

## Roadmap

В планах — **межпроектный агент-оптимизатор**: обходит все связанные через
топологию проекты, ищет общие части (дублирующийся код, расходящиеся реализации
одного и того же), и рекомендует унификацию в общую кодовую базу. Карта
топологии — фундамент для такого обхода. См. `docs/roadmap.md`.

---

## Чеклист

- [ ] Прочитал `~/.swissknifeman/topology.json` (или предложил `topology init`, если его нет)
- [ ] Использовал реальные пути узлов, а не захардкоженные
- [ ] Для документации — шёл через Brain (`brain status/sync`), не правил зеркала вручную
- [ ] Не коммитил `topology.json` в проект
