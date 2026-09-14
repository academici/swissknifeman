# Индекс плана — `plans/<PLAN-ID>/index.md`

<!-- Карта ФАЙЛОВ плана + провенанс-связи (root/contracts/plan-index-schema.md, P1.2
     sealed v1). НЕ носитель статуса (Status Board/phases/Pn.md) и НЕ носитель "куда
     дальше" (handoff.md) — соблазн внести то или другое сюда = второй носитель факта,
     стоп (§3 plan-protocol). Опционален: план без index.md валиден. Три секции строго
     в этом порядке; отсутствующие в плане узлы карты директорий — опускаются. -->

**Обновлён:** <YYYY-MM-DD>

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | stable core: Meta, Context, Rules, §3 Routing, §7 Contracts |
| `status.md` | generated status projection |
| `phases/<Pn>/<Pn>.md` | stable Phase Context + item index |
| `phases/<Pn>/<Pn.m>.md` | stable item specification |
| `phases/<Pn>/<Pn.m>.state.md` | generated volatile item state |
| `phases/<Pn>/<Pn>.closed.md` | generated terminal phase contract/result |
| `bundles/<Pn.m>.json` | ordered digest-qualified executor inputs |
| `decisions/` | append-only decisions + generated current/archive/index views |
| `handoff.md` | rolling-указатель «где мы» (перезаписывается) |
| `roadmap.md` | исполнительская карта: батчи/workflow/гейты |
| `journal.jsonl` | append-only история запусков `task:plan-*` |
| `brief/` | слой 0 «вход»: бриф владельца + уточнения |
| `findings/` | слой 1 «сырьё»: RAG-выжимки, recon |
| `research/` | слой 2 «синтез»: авторские design-документы |
| `root/` | долгоживущий материал (контракты и т.п. — см. секцию ниже) |
| `open-questions.md` | спорное/нерешённое |

## Провенанс

<!-- Единственная содержательная секция — связи "источник → фаза-потребитель".
     If-then (анти-дубль, §3 контракта): если ПОЛНОСТЬЮ выводима из Inputs/Required
     Reads items — сузить индекс до карты директорий + эскалировать ценность секции
     владельцу, не плодить дубль. -->

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `findings/<slug>.md` | findings | `<Pn>` | 1 строка: что даёт |
| `research/<NN>-<slug>.md` | research | `<Pn.m>` | 1 строка: что даёт |

## Ключевые артефакты `root/`

<!-- Опционально. Статус ЗДЕСЬ — про зрелость КОНТРАКТА-артефакта (sealed/draft), не
     про item плана: это не второй носитель статуса item (§3 граница соблюдена). -->

| Артефакт | Суть | Статус |
|:--|:--|:--|
| `root/contracts/<name>.md` | 1 строка | sealed vN (`<Pn.m>`) \| draft |
