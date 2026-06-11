# Contributing

## Adding a Local Skill

1. Copy `SKILL_TEMPLATE.md` → `skills/{bucket}/{name}/SKILL.md`
2. Add `snippets/` with `index.json` manifest
3. Run `./scripts/validate.sh`
4. Run `./sync.sh --update-registry` — обновляет skills.json **и генерирует
   манифесты плагинов** (`.claude-plugin/marketplace.json`,
   `skills/*/.claude-plugin/plugin.json`); обязательно после
   добавления/перемещения/удаления скилла
5. Open PR — CI runs the same validation

## Adding an External (Upstream-Tracked) Skill

Внешние скиллы берём **выборочно** — только то, что реально подходит. Кандидаты
и анализ источников — в [references/](references/README.md).

1. `mkdir -p skills/{bucket}/{name}`
2. Создать `upstream.json` (sha256/fetched_at оставить пустыми):
   ```json
   {
     "schema_version": 1,
     "source": "github",
     "repo": "owner/repo",
     "strategy": "replace",
     "files": [
       { "path": "SKILL.md",
         "url": "https://raw.githubusercontent.com/owner/repo/main/SKILL.md",
         "sha256": "", "fetched_at": "" }
     ]
   }
   ```
3. `./scripts/update-upstreams.sh --apply --skill {bucket}/{name}` — скачает файл и запишет sha
4. Выбрать strategy:
   - `replace` — файл зеркалируется как есть; у апстрима должен быть пригодный
     frontmatter (`name` + `description`), иначе валидатор не пропустит
   - `notify` — вы адаптируете локальную копию (свой frontmatter, правки);
     об обновлениях апстрима только сообщается
5. `./sync.sh --update-registry` → PR
6. Обновить статус источника в `references/{source}.md` на `imported`

## references/ Lifecycle

Один md-файл на источник: URL, что это, «брать выборочно» / «не брать», целевые
bucket-ы, статус `planned` → `imported` / `rejected`. При фактическом импорте
скилла — обновить статус и добавить `upstream.json` в папку скилла.

## Buckets

| Bucket | Purpose |
|--------|---------|
| founder, pm, architect | Business & architecture |
| oss-dev, quality, operator | Engineering practices |
| devops, php | Infrastructure & Laravel |
| roles | Persona-based skills |
| imported | External super-skills (upstream-tracked) |

## Validation

```bash
./scripts/validate.sh    # перед каждым PR; CI запускает то же самое
```

Проверяет: frontmatter всех SKILL.md (для внешних с upstream.json — только
`name` + `description`), схему upstream.json, profiles/*.json, skills.json,
snippet-манифесты, buckets.json (1:1 с каталогами bucket-ов), свежесть
plugin-манифестов (`.claude-plugin/`), уникальность имён скиллов (дубль внутри
bucket-а — ошибка, между bucket-ами — warning).

## Releases & Tagging

- Аннотированные semver-теги: `git tag -a vX.Y.Z -m "..."` (push тегов — вручную).
- **minor** — новая возможность каркаса (установщик, sync, marketplace);
  **patch** — наполнение/правки скиллов.
- При теге перенести раздел `[Unreleased]` CHANGELOG в `[X.Y.Z]`.
- Версии плагинов Claude Code разрешаются в git SHA (поля `version` в
  манифестах намеренно нет) — теги служат человекочитаемыми маркерами релизов,
  на обновление плагинов не влияют.

## Snippet Guidelines

- Anonymize project namespaces: `namespace App\...`
- Add source comment: `// Source: {project}/{file} (anonymized)`
- Quality threshold for scanner: ≥ 60 (see `.skills-scanner.json`)

## Adapters

Provider-specific deltas go in `skills/{bucket}/{name}/adapters/` — never duplicate full SKILL.md.

Global adapter docs: `adapters/{cursor,claude-code,perplexity}/`.

Отдельного sync-скрипта для Obsidian нет. `sync.sh` пушит только в `academici/brain`.

## Scanner

```bash
./scripts/scan-skills.sh              # SCAN + ANALYZE
./scripts/scan-skills.sh --extract    # + EXTRACT to .scanner-output/
./scripts/scan-and-pr.sh              # + COMMIT + PR
```

## Sync to Brain

```bash
BRAIN_PATH=/path/to/brain ./sync.sh --update-registry
```

## Backlog

- [ ] Filament resource generator skill
- [ ] Deeper AzGuard snippet extraction via scanner
- [ ] Per-skill adapter deltas where providers diverge
- [ ] Выборочный импорт кандидатов из references/ (laravel-specialist, laravel-tips, MADR)
