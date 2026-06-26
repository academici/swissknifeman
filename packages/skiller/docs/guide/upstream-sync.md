# Upstream-sync: отслеживание внешних скиллов

Внешние скиллы не должны устаревать незаметно. Каждый импортированный скилл
содержит `upstream.json` рядом со `SKILL.md` — паспорт источника и стратегию
обновления.

## upstream.json

```json
{
  "schema_version": 1,
  "source": "github",
  "repo": "get-zeked/research-knowledge-super-skill",
  "strategy": "notify",
  "files": [
    {
      "path": "SKILL.md",
      "url": "https://raw.githubusercontent.com/.../SKILL.md",
      "sha256": "…",
      "fetched_at": "2026-06-11"
    }
  ]
}
```

## Стратегии

| Состояние | Поведение sync-тулинга |
|---|---|
| Нет `upstream.json` | скилл самописный — не трогается |
| `strategy: replace` | файл зеркалируется как есть, обновления применяются автоматически |
| `strategy: notify` | локальная копия адаптирована; об обновлениях только сообщается, файл не перезаписывается |
| `strategy: fork` | форк с нашими правками: `files[].path` указывает на **pristine-зеркало** (напр. `references/source.md`), правки живут в обёртке `SKILL.md`. На дрейфе ставится `review_pending: true` (блокирует распространение) — ручной перенос, затем `--resolve` |
| `strategy: merge` | **композит из ≥2 источников** (`origins[]`: один `base` + ≥1 `supplement`/«suggest»), слепленный в единый скилл. Синк **ручной под управлением агента**: на дрейфе любого origin `merge.review_pending: true` блокирует распространение — агент пере-мерджит вручную, затем `--resolve`. Авто-overwrite запрещён |

## Команды

```bash
# Отчёт: что устарело (exit-код 10 = есть изменения — удобно для CI)
./scripts/update-upstreams.sh --check

# Применить replace-обновления, записать новые sha; для fork — застейджить
# incoming и поднять review_pending (зеркало/SKILL.md не трогаются)
./scripts/update-upstreams.sh --apply

# Принудительно перезаписать конкретный скилл (разрешение конфликта, replace)
./scripts/update-upstreams.sh --apply --force --skill imported/research

# fork: после ручного переноса правок — продвинуть incoming в зеркало и снять флаг
./scripts/update-upstreams.sh --resolve --skill ai/ai-agents
```

## `fork`: форк с локальными правками

Для большого внешнего скилла, который мы **адаптируем и не хотим обновлять
автоматом** (а context-economy требует не грузить весь файл в контекст). Раскладка:

```
skills/<bucket>/<name>/
├── SKILL.md            # тонкая обёртка-навигатор (наши правки живут здесь)
├── upstream.json       # strategy: fork; files[].path = references/source.md
└── references/
    └── source.md       # pristine-зеркало апстрима = базлайн (грузится по требованию)
```

Зеркало (`references/source.md`) **байт-в-байт** равно тому, что отдаёт `url`, —
поэтому `--check` сравнивает свежий апстрим с записанным `sha256` и видит дрейф.
Наши правки изолированы в обёртке `SKILL.md`, значит зеркало остаётся pristine, а
порт диффа — почти нулевой.

Цикл сопровождения на дрейфе:

1. `--check` → `[notify] … strategy=fork — нужна ручная доработка` (exit 10, CI падает).
2. `--apply` → кладёт свежий апстрим в `upstream/<name>.incoming.md`, ставит
   `review_pending: true`. Зеркало и `SKILL.md` **не трогаются**.
3. **Гейт**: `validate.sh` падает, пока `review_pending: true` — релиз/`registry`
   заблокированы.
4. Агент сверяет `diff references/source.md upstream/<name>.incoming.md`, при
   реструктуре апстрима правит маршрутизацию в обёртке `SKILL.md`.
5. `--resolve` → зеркало := incoming, `sha256`/`fetched_at`/`last_review` обновлены,
   `review_pending: false`, incoming удалён. `validate.sh` снова зелёный.

Блокировка действует **только в реестре**: в проекты-потребители `upstream.json`
не вендорится (как и для replace/notify) — туда уезжает уже выверенная копия
(`SKILL.md` + `references/source.md`).

## `merge`: композит из нескольких источников

Когда скилл фактически **слеплен из двух+ внешних скиллов** в единый целиковый
формат, провенанс с ролями фиксируется в `origins[]`:

```json
{
  "schema_version": 1,
  "source": "github",
  "strategy": "merge",
  "origins": [
    {"repo": "antfu/skills",      "role": "base",       "url": "…", "ref": "main",
     "sha256": "…", "fetched_at": "2026-06-26", "note": "взята структура и ядро"},
    {"repo": "onmax/nuxt-skills", "role": "supplement", "url": "…",
     "sha256": "…", "fetched_at": "2026-06-26", "suggest": "добавлены разделы SEO/модули"}
  ],
  "merge": { "review_pending": false, "last_review": "2026-06-26" },
  "files": [ { "path": "references/base.md", "url": "…", "sha256": "…", "fetched_at": "2026-06-26" } ]
}
```

- **Роли.** Ровно один `base` (взят за основу) + ≥1 `supplement` — дополняющий
  источник-«suggest» (чем именно дополнил — поле `note`/`suggest`). Так видно, кто
  «фундамент», а кто пришёл в дополнение.
- **Синк только ручной, под управлением агента.** Авто-overwrite для композита
  бессмысленен (его собрал человек/агент из кусков). На дрейфе любого `origin`
  ставится `merge.review_pending: true` — **гейт**: `validate.sh`/`registry`/релиз
  заблокированы, пока агент не сверит свежие источники, не пере-мерджит их в
  `SKILL.md` и не снимет флаг.

Цикл сопровождения:

1. `--check` → дрейф одного из `origins` (свежий sha ≠ записанному) → exit 10.
2. `--apply` → кладёт свежие версии источников в `upstream/<name>.<repo>.incoming.md`,
   ставит `merge.review_pending: true`. `SKILL.md` **не трогается**.
3. **Гейт**: `validate.sh` падает (как у fork), пока `review_pending: true`.
4. Агент сверяет инкаминги с текущим композитом и **пере-мерджит** руками: какие
   изменения из `base`, какие из `supplement` перенести в единый `SKILL.md`.
5. `--resolve` → обновляет `sha256`/`fetched_at` всех origin, `merge.last_review`,
   снимает `review_pending`. `validate.sh` снова зелёный.

Как и для остальных стратегий, `upstream.json` и `origins`-зеркала **не вендорятся**
в проекты — туда уезжает выверенный `SKILL.md`.

## Канал загрузки: gh api → urllib

Для GitHub raw-URL (`raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}`)
и при наличии **GitHub CLI** скрипт тянет файл точечно через
`gh api repos/{owner}/{repo}/contents/{path}?ref={ref}`:

- авто-аутентификация из `gh auth` — не нужно прокидывать `GITHUB_TOKEN`;
- уважает rate-limit GitHub API;
- один файл вместо полной загрузки — экономия трафика/контекста (тот же
  принцип, что в скилле `oss-dev/gh-review`).

Если `gh` недоступен или вызов упал — **тихий откат** на `urllib`
(с `GITHUB_TOKEN` из окружения, если задан). Принудительно отключить gh-путь:
`UPSTREAM_NO_GH=1`. Поведение и формат `upstream.json` при этом не меняются.

## Еженедельный CI

GitHub Action `upstream-sync.yml` раз в неделю проверяет все апстримы и — если
есть изменения — открывает PR с диффом. Изменения чужих репозиториев попадают
в `main` **только после ревью**: ни один внешний коммит не вливается автоматически.

## Как выбрать стратегию

- **`replace`** — когда апстрим качественный и его формат совместим напрямую:
  валидный frontmatter (`name`, `description`), нет нужды адаптировать.
  Вы получаете обновления бесплатно.
- **`notify`** — когда вы переписали frontmatter, перевели, сократили или
  иначе адаптировали скилл. Апстрим остаётся ориентиром: CI сообщит, что
  источник изменился, а решение о портировании правок — за вами.
- **`fork`** — когда внешний скилл большой и вы оборачиваете его тонким
  навигатором (контент в `references/source.md`, правки в обёртке) и/или хотите
  жёсткий гейт: дрейф апстрима **блокирует распространение** до ручного переноса.
  Сильнее `notify` (которое лишь сообщает): добавляет pristine-зеркало для диффа,
  флаг `review_pending` и шаг `--resolve`.
- **`merge`** — когда скилл собран **из нескольких источников** (`base` +
  `supplement`). Как fork по гейту (`review_pending` + `--resolve`), но с
  мульти-источниковым провенансом `origins[]` и **обязательно ручным** пере-merge
  агентом (авто-overwrite запрещён — композит нельзя зеркалировать одним файлом).

## Каталог источников (что взято, что отклонено)

Решения «взять / адаптировать / отклонить / доверять апстриму» по каждому внешнему
репозиторию-источнику ведутся в каталоге
[`packages/skiller/references/README.md`](https://github.com/academici/swissknifeman/blob/main/packages/skiller/references/README.md)
(таблица `Источник | Ценность | Статус`). Это источник истины по отбору; per-skill
паспорта — в `upstream.json` рядом с каждым импортированным `SKILL.md`.
