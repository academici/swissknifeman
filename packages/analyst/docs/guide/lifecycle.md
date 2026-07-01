# Жизненный цикл урока

Урок проходит детерминированный конвейер состояний, с человеком в гейте на входе в переиспользуемое
знание. Всё — append-only и восстановимо из логов.

## Состояния

```
ephemeral ──promote──▶ candidate ──promote(человек)──▶ curated
    │                      │                               │
    └──────── deprecate (soft, не удаляется — аудит) ◀──────┘
```

| Состояние | Смысл | Как попадает |
|:--|:--|:--|
| `ephemeral` | сырой кандидат из прогона | `digest` |
| `candidate` | подтверждён (наблюдался/сработал) | `promote` или авто из `recompute` (P3) |
| `curated` | доверенное знание, всплывает в память mAInd | **только человек** (`promote --to curated`) |
| `deprecated` | демоутнут (soft) | `deprecate`, `--supersedes`, просадка confidence |

Раскладка данных (per-project, **LOCAL**):

```
<project>/.claude/analyst/
  lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
  audit.ndjson     # append-only провенанс переходов
  events.ndjson    # append-only поток сигналов confidence (P3)
```

## Провенанс и аудит

Каждый урок несёт `source` / `session_id` / `scope` / `evidence`; каждый переход — запись в
append-only `audit.ndjson` (кто, откуда-куда, согласие). Переход — через ре-райт + unlink (урок не
двоится между каталогами).

## Confidence (P3)

`recompute` пересчитывает уверенность **чистой** арифметикой (stdlib, без I/O/часов):

```
p          = (S + α) / (N + α + β)      # Beta-среднее доли успеха
volume     = 1 − e^(−N / k)             # штраф за малый объём
decay      = λ ^ days                    # затухание по времени
confidence = p × volume × decay          # ∈ [0, 1)
```

Тиры применения: `tentative` 0.3 · `moderate` 0.5 · `strong` 0.7 · `core` 0.9 (ниже 0.3 — `none`).
Источник истины — `events.ndjson`; снапшот воспроизводим при фиксированном `--now`. Числовая
state-machine: авто `ephemeral→candidate`, `curated` — только человек, просадка → soft-deprecate.

## Consolidation (mem0-таксономия)

При `promote`/`review` урок сверяется с активными (Jaccard) и классифицируется:
`ADD` (новый) · `UPDATE` (уточняет) · `NOOP` (дубль) · `CONFLICT` (противоречит). **Конфликт →
flag-and-ask**: авто-резолв запрещён, человек решает `--supersedes ID` (soft-деприкейт старого) или
`--force`.

## Cross-project scan (P2)

`scan` поднимается над одним проектом: обходит реестр `config.json:projects[]`, собирает уроки из
всех, кластеризует по Jaccard и детектит паттерны в **≥N проектах** — **namespace-изолированно**
(наследуется от [mAInd](/maind/guide/namespaces): паттерн из `ns:axioma` не течёт в чужой namespace;
проект без namespace изолирован). Результат — `index/by_pattern/<id>.json` (абстрагированная проекция:
`representative{trigger,action,kind}`, `members`, `weight`, `projects`) + человекочитаемый
`suggestions/<id>.md`.

**Реконсиляция** после записи: осиротевшие артефакты (паттерн исчез — проект disabled, урок
deprecated, кластер упал ниже порога) снимаются **строго в scope прогона** (`scanned_namespaces` =
`{--namespace}` если задан, иначе union namespace всех enabled-проектов). Чужой namespace не рескан →
его файлы не трогаются. Битый индекс → SKIP (не удаляем неклассифицированное). Нестандартные
`--min-projects/--threshold` пропускают авто-прун (защита от churn).

Дальше: индекс паттернов — вход для [suggest →](./suggest).
