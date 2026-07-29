# Effective-collision remeasure (F1 A1) — 2026.07.24-AGENT-RELIABILITY

**Дата:** 2026-07-25 · **Слой:** 1 (сырьё/измерение, без проектных выводов)
**Исполнитель:** Claude Opus 5 / high (bounded repair, Owner authority D — D39)
**Повод:** `findings/10-design-audit-a1-attempt-4.md` F1 — замороженное «12 коллизий»
опровергается фактическим runtime; «остальные root-адаптеры уникальны» ложно.
**Якорь:** дерево `916acdb5` (`codex/provider-project-sync`), plan.md v1.8.0.
Чужой незакоммиченный дифф (архив-переносы + `tmp/`) в измерение не входит.

## Метод (детерминированный, воспроизводимый)

Два независимых прохода, оба read-only:

1. **Repo-derived (authoritative, worst case).** Для каждой publishable unit из
   `.agents/plugins/marketplace.json` (51 запись: бакеты + курируемый `core` +
   `skm` + `task` + `generate-skill`) собраны identity-записи по frontmatter
   `name:` всех `SKILL.md` внутри `source` (для записи с полем `skills[]` —
   только по перечисленным путям). Плюс identity-записи root-адаптеров
   `.agents/skills/*/SKILL.md`. Коллизия = identity с ≥2 носителями.
   Не требует профиля/кэша — считается из репозитория холодным.
2. **Observed (evidence, необязательно для гейта).** Enabled-множество взято
   одной read-only командой `codex plugin list --json` (cwd = корень репо,
   2026-07-25); отфильтровано `marketplaceName == "swissknifeman"`.

Скрипт измерения (stdlib-only, воспроизводит обе таблицы) приложен ниже дословно.

## Observed runtime (2026-07-25)

| Факт | Значение |
|:--|:--|
| installed `@swissknifeman` units | **23** |
| из них enabled | **23** (все) |
| enabled имена | `architect`, `axioma`, `core`, `creative`, `devops`, `finance`, `founder`, `laravel-auth`, `laravel-data-layer`, `laravel-testing`, `legal`, `marketing`, `operator`, `php`, `php-packages`, `pm`, `quality`, `research`, `roles`, `sales`, `skm`, `system`, `task` |
| каталогов в `.agents/skills/` | **30** (все hand-written, git-tracked) |
| каталогов в `.claude/skills/` | **13** (ровно repository-bootstrap набор) |

`core` unit (физические копии в `packages/skiller/adapters/codex/core/skills/`)
несёт 9 identity: `anti-drift`, `compact-responses`, `context-economy`,
`gh-review`, `mcp-advisor`, `plan-protocol`, `query-craft`, `session-handoff`,
`verify-claims`. `task` unit несёт 11 identity (6 из них дублированы в root).

## Коллизии в фактическом effective-каталоге Codex (enabled-множество)

**16 identity, все root↔installed. Из них 1 дополнительно installed↔installed.**

| # | Identity | Носители | Класс | Уже в scope плана (D28) |
|:--|:--|:--|:--|:--|
| 1 | `anti-drift` | `unit:core` + `root:.agents/skills/anti-drift` | root↔installed | ✅ (6 core) |
| 2 | `context-economy` | `unit:core` + root | root↔installed | ✅ |
| 3 | `plan-protocol` | `unit:core` + root | root↔installed | ✅ |
| 4 | `session-handoff` | `unit:core` + root | root↔installed | ✅ |
| 5 | `verify-claims` | `unit:core` + root | root↔installed | ✅ |
| 6 | `query-craft` | `unit:core` + **`unit:research`** + root | root↔installed **и** installed↔installed | ⚠️ частично (root — да, core↔research — нет) |
| 7 | `task-design` | `unit:task` + root | root↔installed | ✅ (6 task) |
| 8 | `task-plan-audit` | `unit:task` + root | root↔installed | ✅ |
| 9 | `task-plan-close` | `unit:task` + root | root↔installed | ✅ |
| 10 | `task-plan-design` | `unit:task` + root | root↔installed | ✅ |
| 11 | `task-plan-exec` | `unit:task` + root | root↔installed | ✅ |
| 12 | `task-plan-run` | `unit:task` + root | root↔installed | ✅ |
| 13 | `architecture` | **`unit:architect`** + root | root↔installed | ❌ **НЕ в scope** |
| 14 | `codebase-design` | **`unit:architect`** + root | root↔installed | ❌ **НЕ в scope** |
| 15 | `domain-modeling` | **`unit:architect`** + root | root↔installed | ❌ **НЕ в scope** |
| 16 | `package-contribution-protocol` | **`unit:architect`** + root | root↔installed | ❌ **НЕ в scope** |

Итог против премиссы D28: **16 root↔installed вместо 12**, плюс **1
installed↔installed** (`query-craft`: курируемый `core` и его донорский бакет
`research` включены одновременно).

## Root-адаптеры без enabled-носителя (уникальные bootstrap-carriers)

**14, а не 13.** 13 = запечатанный repository-bootstrap набор плана; **14-й —
`workflow-craft`**, у которого есть канонический источник в публичном бакете
(`packages/skiller/skills/general/workflow-craft`), но бакет-unit `general`
**не включён**, поэтому идентичность сейчас уникальна и обслуживается
рукописным root-адаптером без owner/provenance/hash.

`cross-project-optimizer`, `decision-verification`, `docs-maintenance`,
`ecosystem-integration`, `ecosystem-mcp`, `ecosystem-setup`,
`field-feedback-loop`, `harness-operations`, `maind-overview`,
`package-architecture`, `project-tooling-runbook`, `release-discipline`,
`skill-authoring` (13 — есть только root-копии, канона в бакетах нет) +
**`workflow-craft`** (канон в `general`, unit выключен).

## Worst case (repo-derived, игнорируя enabled) — 20 коллизий

Дополнительно к 16 выше (минус ни одна) появляются:

| Identity | Носители | Почему важно |
|:--|:--|:--|
| `compact-responses` | `unit:core` + `unit:general` | курируемый `core` физически копирует скиллы из донорских бакетов |
| `mcp-advisor` | `unit:core` + `unit:general` | то же |
| `gh-review` | `unit:core` + `unit:oss-dev` | то же |
| `workflow-craft` | `unit:general` + root | root-адаптер станет дублем при включении `general` |
| (уже в 16) `anti-drift`, `context-economy`, `plan-protocol`, `session-handoff`, `verify-claims` | `unit:core` + `unit:general` + root | тройной носитель при включении `general` |

Следствие: `core`↔донорские бакеты (`general`, `research`, `oss-dev`) —
взаимоисключающие публикации по построению (CLAUDE.md: курируемый `core` —
«лёгкая замена бакетам general+oss-dev»), но ничем не проверяются; сейчас
`core` и `research` включены одновременно → живой дубль `query-craft`.

## Второй слой F1 — committed before-state не машинно-сравним

`artifacts/source-evidence/runtime/effective-runtime-inventory.json` (immutable,
886 байт) не содержит ни одной identity-записи, ни списка плагинов, ни версий:

```
$ python3 -c "import json;d=json.load(open('.../effective-runtime-inventory.json'));print(sorted(d))"
```
ключи верхнего уровня — прозаические `green`/`not_green`/`redactions` (проверено
чтением файла в A1, `findings/10` F1 второй слой). Диффать против него
детекцию коллизий структурно невозможно → число «12» было
`pinned-not-recomputable`, но использовалось как замороженный exact scope удалений.

## Скрипт измерения (дословно; stdlib-only, read-only)

```python
import json, os, re, glob, collections
def ident(p):
    t = open(p, encoding="utf-8").read(4000)
    m = re.search(r'^name:\s*(.+)$', t, re.M)
    return m.group(1).strip().strip('"\'') if m else None
mk = json.load(open(".agents/plugins/marketplace.json"))
unit_ids = {}
for p in mk.get("plugins", mk):
    src = (p.get("source") or "").lstrip("./"); ids = set()
    paths = [os.path.normpath(os.path.join(src, s.lstrip("./"))) for s in p.get("skills", [])] or [src]
    for sp in paths:
        for f in glob.glob(os.path.join(sp, "SKILL.md")) + glob.glob(os.path.join(sp, "**", "SKILL.md"), recursive=True):
            i = ident(f)
            if i: ids.add(i)
    unit_ids[p["name"]] = ids
root_ids = {d: ident(os.path.join(".agents/skills", d, "SKILL.md")) for d in sorted(os.listdir(".agents/skills"))}
enabled = {p["name"] for p in json.load(open("codex-plugins.json"))["installed"]
           if p.get("marketplaceName") == "swissknifeman" and p.get("enabled")}
own = collections.defaultdict(list)
for u, ids in unit_ids.items():
    for i in ids:
        if u in enabled: own[i].append("unit:" + u)
for d, i in root_ids.items():
    if i: own[i].append("root:" + d)
print({k: v for k, v in own.items() if len(v) > 1})
```

Провенанс observed-входа: `codex plugin list --json > codex-plugins.json`
(read-only, cwd = корень репо, 2026-07-25). Абсолютные пути кэша плагинов в
записях — provenance-строки, в план не переносятся.

## Что этим доказано / не доказано

- **Доказано (repo-grounded + observed):** 16 root↔installed, 1
  installed↔installed, 14 уникальных root-carriers, 20 worst-case.
- **Доказано:** committed before-state не несёт identity-записей.
- **Не доказано и не заявляется:** состояние Claude-провайдера как enabled-набора
  (для Claude read-only эквивалент enabled-списка не запускался; `.claude/skills`
  = ровно 13, коллизий root↔root нет). Класс — `unknown`, не «зелёное».
- **Не измерялось:** effective-каталог вне self-host репо (fleet/consumers) —
  вне границ плана.
