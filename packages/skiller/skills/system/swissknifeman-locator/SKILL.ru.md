---
name: swissknifeman-locator
bucket: system
version: 0.1.0
description: Из внешнего репо дойти до swissknifeman (узел скиллов) — нехардкод-резолюция пути, корневой config.json как реестр связанных проектов, схема связи проект↔хаб
risk: read
persona: architect
tags: [swissknifeman, skills, registry, navigation, locator, ecosystem]
requires: [local-topology]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Swissknifeman Locator (дойти до управляющего монорепо)

Применять когда: агент во **внешнем репозитории** хочет найти управляющий
монорепо экосистемы (**swissknifeman**, узел `skills-hub`), понять через его
корневой `config.json`, **какие проекты в экосистеме и как они связаны**, либо
опознать, чем текущий проект связан с хабом. Это drill-down в один узел из карты
`local-topology` — с резолюцией пути, которая работает без конфига топологии.

swissknifeman несёт реестр AI-скиллов + раздачу их в проекты + бинари экосистемы
(`maind` — память/граф/MCP, `skiller` — скиллы, `harness` — окружение).

---

## Резолюция пути к swissknifeman (нехардкодно)

Путь машинно-специфичен — **резолвить, не хардкодить**. Лестница:

```bash
# A. Явный env-override
SKM="$SWISSKNIFEMAN_ROOT"

# B. Через установленный бинарь экосистемы (якорь): readlink до реального файла в репо,
#    подъём bin → пакет → packages → корень (3 уровня)
if [ -z "$SKM" ]; then
  BIN="$(command -v maind || command -v skiller)"
  [ -n "$BIN" ] && SKM="$(cd "$(dirname "$(readlink -f "$BIN")")/../../.." && pwd)"
fi

# C. Кандидаты от $HOME (первый существующий); канонический — projects/packages/swissknifeman
if [ -z "$SKM" ] || [ ! -f "$SKM/config.json" ]; then
  for c in "$HOME/projects/packages/swissknifeman" "$HOME/projects/swissknifeman" "$HOME/swissknifeman"; do
    [ -f "$c/config.json" ] && SKM="$c" && break
  done
fi

# Признак корня: config.json + packages/skiller + packages/maind
[ -n "$SKM" ] && [ -f "$SKM/config.json" ] && [ -d "$SKM/packages/skiller" ] \
  && cd "$SKM" || echo "swissknifeman не найден: задайте \$SWISSKNIFEMAN_ROOT"
```

Если ничего не подошло — **сказать пользователю**, попросить
`$SWISSKNIFEMAN_ROOT`; не угадывать.

---

## Корневой `config.json` = реестр связанных проектов (двусторонняя связь)

В корне `config.json` — `projects[]` со всей экосистемой:
`{id, name, local_path, vault_path, type, namespaces, docs_folders, dependencies,
mcp, roles}`. Это реестр тулинга (импортирует каталог Brain, добавляет
namespaces/type/graph/mcp).

```bash
# проекты экосистемы: id, тип, путь, namespaces
jq -r '.projects[]|"\(.id)\t\(.type)\t\(.local_path)\tns=\(.namespaces//[]|join(","))"' "$SKM/config.json"

# namespaces (группы изоляции памяти/графа)
jq -r '.namespaces|to_entries[]|"\(.key): \(.value.name) — \(.value.description)"' "$SKM/config.json"

# граф зависимостей пакетов
jq -r '.projects[]|select((.dependencies//[])|length>0)|"\(.id) → \(.dependencies|join(","))"' "$SKM/config.json"

# мост к docs-узлу Brain
jq -r '.integrations.brain.path' "$SKM/config.json"   # путь к .projects.json волта (см. brain-locator)
```

**Двусторонность:** проект ссылается на swissknifeman (через свои артефакты —
ниже), а `config.json.projects[]` перечисляет проект. Две стороны одной связи.

---

## Схема связи проект↔swissknifeman (как опознать)

В корне внешнего проекта связь видна по артефактам:

- **`.swissknifeman/config.json`** (`mode:"vendor"`, `buckets`/`exclude`) — канал
  **vendor**: физкопии скиллов в `.claude/skills/`.
- **`skills-lock.json`** (`skills:{<name>:{source, managed, bucket, installed_path}}`)
  — карта установленных скиллов; `source:"swissknifeman"` + `managed:true` =
  вендорено из хаба.
- **`.claude/settings.local.json` → `enabledPlugins` + `extraKnownMarketplaces`** —
  канал **connect**: плагины-бакеты, marketplace указывает на локальный путь к
  swissknifeman (файлы скиллов НЕ копируются).
- **`.mcp.json` → сервер `maind`** — проект подключён к хабу памяти/графа.

Глубже (как ставить/менять/синкать скиллы двумя каналами, doc-sync) —
раннбук `project-tooling-runbook`; онбординг в хаб — `ecosystem-integration`;
окружение (permissions/MCP/хуки/agent-packs) — `harness-operations`. Локатор лишь
даёт **опознать** связь и дойти до узла, не дублируя их процедуры.

---

## Принципы

- **Read-only ориентир.** Скилл находит узел и читает `config.json`; правки
  экосистемы — через `skiller`/`maind`/`harness`, не вручную.
- **Резолвить, не хардкодить.** Корень — из бинаря/env/`$HOME`-кандидатов.
- **Не дублировать раннбуки.** Команды установки/синка — в профильных скиллах,
  сюда не копировать.

---

## Чеклист

- [ ] Корень резолвлен через бинарь/env/`$HOME`, не захардкожен
- [ ] Для обзора экосистемы читал `config.json.projects[]`/`namespaces`
- [ ] Связь проекта опознал по `.swissknifeman/config.json`/`skills-lock.json`/`enabledPlugins`
- [ ] Глубину делегировал в `project-tooling-runbook`/`ecosystem-integration`

---

## Ссылки

- `local-topology` (бакет system) — корневая карта трёх узлов; swissknifeman = узел `skills-hub`.
- `brain-locator` (бакет system) — парный локатор узла `docs-hub`; мост через `integrations.brain.path`.
- `project-tooling-runbook`, `ecosystem-integration`, `harness-operations` — операционная глубина (если доступны).
