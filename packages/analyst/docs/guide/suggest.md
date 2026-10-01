# suggest — cross-project паттерн → черновик скилла

`analyst suggest` закрывает разрыв между «нашли межпроектный паттерн» ([scan](./lifecycle#cross-project-scan-p2))
и «есть переиспользуемый [скилл](/skiller/guide/)». Это детерминированный мост: паттерн →
**staged-ЧЕРНОВИК** `SKILL.ru.md`, который человек дорабатывает и промоутит. Дальнейшие направления — [roadmap](/roadmap).

```
analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
```

## Что делает

Читает **только** абстрагированный индекс `~/.swissknifeman/analyst/index/by_pattern/<id>.json` и
генерит staged-каталог:

```
~/.swissknifeman/analyst/drafts/<pattern_id>/
  SKILL.ru.md      # RU-источник-ЗАГОТОВКА (frontmatter-скелет + провенанс-штамп + тело) — правит человек
  draft.meta.json  # паспорт черновика: провенанс + seed_sha256 (детект ручных правок)
```

Каталог **зеркалит форму скилла** (`skills/<bucket>/<name>/`) — человек кладёт рядом `snippets/` и
переносит одной командой.

## Инвариант — чего suggest НЕ делает

| Не делает | Как удержано |
|:--|:--|
| Не пишет в `skills/` | Только `~/.swissknifeman/analyst/drafts/`; промоут — руки человека |
| Не генерит EN `SKILL.md` | Только RU-заготовку; EN — человек промтом skiller после доработки |
| Не авто-регистрирует | Не зовёт `skiller registry`/`integrate`; не трогает `skills.json` |
| Не раскрывает raw/секреты | Читает **только** индекс `by_pattern/` (уже абстрагирован) — приватность структурна |
| Не затирает правки человека | `seed_sha256`-детект: правленое тело не трогается без `--force` |
| Не удаляет черновики авто | Осиротевшие — предупреждение, не delete |

## Идемпотентность (edit-safety)

Ре-suggest не затирает ручную работу. Механизм — `seed_sha256` в `draft.meta.json`:

- каталога нет → создать (`created`);
- тело совпадает с генерённым → `unchanged`;
- тело == прошлого seed (не правили) либо `--force` → перегенерить (`updated`/`forced`);
- тело != прошлого seed (правили руками) → тело **не трогаем**, освежаем лишь провенанс meta
  (`skipped-edited`).

**Осиротевшие черновики** (паттерн исчез из индекса) при `--all` — **предупреждение, не удаление**
(в отличие от [scan-prune](./lifecycle#cross-project-scan-p2): черновик человеко-редактируем,
авто-delete = потеря труда).

## Числовые гейты

По умолчанию — по всем паттернам, что дал `scan` (уже прошли `min_projects≥3`). `--min-weight N`
поднимает планку по числу проектов. `--min-tier` **отложен**: индекс паттерна не несёт confidence
(она per-lesson, P3) — потребовал бы обратного чтения уроков, что нарушило бы «читаем только индекс».

## Промоут черновика в скилл (делает человек)

`suggest` печатает точную последовательность (repo-grounded, **не** `skiller integrate` — тот вшивает
скиллы *в проект*, а не регистрирует новый):

1. `mkdir -p skills/<bucket>/<name>/` и перенести туда `SKILL.ru.md` (`name` == имя каталога).
2. Сгенерировать EN-канон: промт `packages/skiller/prompts/generate/claude-canon-from-ru.md` → `SKILL.md`.
3. `bash packages/skiller/scripts/check-translations.sh --stamp`.
4. `bash packages/skiller/scripts/validate.sh`.
5. `skiller registry`.

`bucket` угадать нельзя (namespace — изоляция, bucket — тема): по умолчанию `TODO`-плейсхолдер +
подсказка со списком бакетов; выбирает человек (`--bucket B`). Двуязычная модель скиллов —
см. [skiller](/skiller/guide/creating-skills).
