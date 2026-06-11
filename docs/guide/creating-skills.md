# Создание скиллов

Два пути пополнения реестра: написать свой скилл или выборочно импортировать
внешний с отслеживанием обновлений.

## Свой скилл

1. Скопируйте `SKILL_TEMPLATE.md` → `skills/{bucket}/{name}/SKILL.md`
2. Заполните frontmatter и разделы (см. [Анатомию скилла](/guide/skill-anatomy))
3. Добавьте `snippets/` с манифестом `index.json`
4. Проверьте: `./scripts/validate.sh`
5. Пересоберите реестр: `./sync.sh --update-registry`
6. Откройте PR — CI прогонит ту же валидацию

::: tip generate-skill
В репозитории есть мета-скилл `generate-skill/` — агент может создавать новые
скиллы по шаблону сам. Он ставится только с профилем `standalone`
(`include_meta: true`).
:::

## Внешний скилл

Внешние скиллы берутся **выборочно** — только то, что реально подходит под
рабочие сценарии, а не репозитории целиком. Кандидаты и анализ источников —
в каталоге `references/`.

1. Создайте папку: `mkdir -p skills/{bucket}/{name}`
2. Создайте `upstream.json` (sha256 и fetched_at оставьте пустыми):

```json
{
  "schema_version": 1,
  "source": "github",
  "repo": "owner/repo",
  "strategy": "replace",
  "files": [
    {
      "path": "SKILL.md",
      "url": "https://raw.githubusercontent.com/owner/repo/main/SKILL.md",
      "sha256": "",
      "fetched_at": ""
    }
  ]
}
```

3. Скачайте файл и зафиксируйте sha:

```bash
./scripts/update-upstreams.sh --apply --skill {bucket}/{name}
```

4. Выберите стратегию:
   - `replace` — файл зеркалируется как есть; у апстрима должен быть пригодный
     frontmatter (`name` + `description`), иначе валидатор не пропустит;
   - `notify` — вы адаптируете локальную копию (свой frontmatter, правки);
     об обновлениях апстрима только сообщается.

5. `./sync.sh --update-registry` → PR
6. Обновите статус источника в `references/{source}.md` на `imported`

## Жизненный цикл references/

`references/` — каталог внешних источников: один md-файл на источник с URL,
описанием, решением «брать выборочно / не брать», целевыми bucket-ами и
статусом:

```
planned → imported | rejected
```

При фактическом импорте скилла статус обновляется, а в папке скилла появляется
`upstream.json`.

## Валидация

Перед каждым PR:

```bash
./scripts/validate.sh
```

Проверяет frontmatter всех скиллов, корректность `upstream.json`, профили,
реестр и snippet-манифесты. CI ([validate.yml](/guide/ci)) запускает то же самое.
