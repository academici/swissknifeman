# Снимок флота «ДО» (P5.1)

Снят ДО merge (P5.2), ПРЕЖНИМ контуром (без префикса PATH к изолированному
`~/.local/bin-skm-next`) — доказательство ниже. Переснятие после merge запрещено (R5,
`plan-protocol` §8): дельта против этого снимка публикуется в P5.3 как
`artifacts/P5.3-fleet-delta.md`.

- **Дата:** 2026-07-30 (UTC 17:08:37Z).
- **SHA дерева изоляции** (ветка `next/harness-agnostic`, на которой закоммичен этот
  артефакт): `fab160fc0dc453e5042e3bda9aac9026bbc4cddb`.
- **SHA основного дерева** (`main`, не тронуто на момент снимка): `8e16a811`.
- **Доказательство контура** — `readlink -f "$(command -v swissknifeman)"` →
  `/home/vostrikov/projects/packages/swissknifeman/bin/swissknifeman` (резолвится в ОСНОВНОЕ
  дерево, не в `swissknifeman-next`) — команды сняты старым контуром, тем же, которым
  пользуется флот.

## Команды (дословно)

```
swissknifeman doctor                        > doctor-before.txt
maind projects status --json                > projects-status-before.json
harness doctor --provider-audit --json      > provider-audit-before.json
```

Без префикса PATH, из произвольного рабочего каталога — три команды резолвятся через
`~/.local/bin/{swissknifeman,maind,harness}` → основное дерево (проверено выше).

## Что в файлах

- `doctor-before.txt` — «Проблем: 2» у skiller (устаревшие `projects.json`-записи,
  протухшие хабы проектов — оба факта существовали ДО этого плана, не регрессия);
  harness/analyst — чисто; maind — «Все проверки пройдены» с двумя known warn (дрейф
  managed-скиллов 18 проектов, дубль-канал 5 проектов).
- `projects-status-before.json` — `hub.memory.running: false`, `hub.graph`: federation,
  296 узлов/1020 рёбер, список всех проектов флота со статусами.
- `provider-audit-before.json` — `green`, диагностик 0, полный `evidence`/`rows`/
  `surface_map` слепок provider-audit харнеса.

## Волатильные поля (исключены из дельты P5.3, D44)

`hub.memory.running`/`hub.memory.url`, `hub.graph.nodes`/`hub.graph.edges`, счётчики уроков
analyst, любые тайминги. Всё прочее в трёх файлах обязано совпасть в P5.3 — расхождение вне
этого перечня либо объяснено фактом плана, либо это находка.
