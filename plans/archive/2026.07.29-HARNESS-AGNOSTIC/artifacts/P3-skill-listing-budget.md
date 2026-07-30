# P3.4 — provider-aware бюджет обнаружения скиллов: замер

Вклеенный вывод команд (2026-07-30, дерево на item-коммите этого item'а). Модель —
`packages/skiller/lib/skiller/budget.py` (`measure_listing_budget`,
`profiles_listing_report`; константы `CODEX_LISTING_FALLBACK_CHARS`/
`CODEX_LISTING_BUDGET_FRACTION` рядом с существующей моделью Claude Code).

## Единицы двух моделей — НЕ смешиваются (D52)

- **Claude Code** — 1% контекстного окна в ТОКЕНАХ (30 000 симв @1M, инвариант
  заморожен `test_profile_listing_budget.py`, `2026.07.25-ECO-OPT` P3.4).
- **Codex** — 2% окна В СИМВОЛАХ; реальное окно, которое Codex CLI считает
  «известным», не измерено (round-trip вне скоупа, D3) → расчёт по ХУДШЕМУ
  случаю, фолбэку **8 000 символов** (RAG:✅ `learn.chatgpt.com/docs/build-skills`,
  2026-07-29). `[UNVERIFIED]`: зависимость от реального окна модели.

## `--profile laravel-project --provider codex`

```
$ bash packages/skiller/bin/skiller budget --profile laravel-project --provider codex
[...трёхъярусный отчёт budget_for_set не воспроизводится здесь — не тема замера...]

─── Бюджет обнаружения (листинг), provider: codex ───
Листинг: 18602 симв  vs  бюджет 8000 симв  — ПЕРЕБОР (×2.3)
Режим деградации: скилл может быть выброшен из листинга целиком
```

## `--profile laravel-project --provider claude-code`

```
$ bash packages/skiller/bin/skiller budget --profile laravel-project --provider claude-code

─── Бюджет обнаружения (листинг), provider: claude-code ───
Листинг: 5550 ток  vs  бюджет 10000 ток  — ок
Режим деградации: описание усекается, имя остаётся
```

## `--profiles` — все поставляемые профили × оба провайдера

```
$ bash packages/skiller/bin/skiller budget --profiles

━━━ БЮДЖЕТ ОБНАРУЖЕНИЯ ПО ПРОФИЛЯМ (provider-aware, P3.4) ━━━━━━━━━━━━━━━

| Профиль | Скиллов | Codex (симв) | vs фолбэк 8000 | Claude Code (ток) | vs бюджет 1% @1M |
|:--|--:|--:|:--|--:|:--|
| blender | 30 | 7308 | ок | 2179 | ок |
| dart-flutter | 44 | 10417 | ПЕРЕБОР | 3107 | ок |
| laravel-project | 86 | 18602 | ПЕРЕБОР | 5550 | ок |
| node-frontend | 79 | 18128 | ПЕРЕБОР | 5404 | ок |
| node-package | 46 | 10146 | ПЕРЕБОР | 3030 | ок |
| obsidian-vault | 66 | 13192 | ПЕРЕБОР | 3941 | ок |
| php-package | 76 | 16959 | ПЕРЕБОР | 5058 | ок |
| platform-service | 110 | 24705 | ПЕРЕБОР | 7363 | ок |
| python-backend | 62 | 13069 | ПЕРЕБОР | 3901 | ок |
| standalone | 227 | 52954 | ПЕРЕБОР | 15778 | ПЕРЕБОР |
```

**Вердикт:** 9 из 10 поставляемых профилей превышают фолбэк-бюджет Codex (8 000
симв); на стороне Claude Code переполняет только `standalone` (именованное
исключение, `2026.07.25-ECO-OPT` P3.5). Это **не гигиена реестра** — `2026.07.25-
ECO-OPT` P3.5 уже сузил профили под Claude-бюджет, и Codex-фолбэк это не сняло:
рычаги владельца №2/№3 (`skillOverrides`/`skillListingBudgetFraction`) —
Claude-only, а рычаг №4 (сжатие описаний) арифметически не спасает (на запись
`laravel-project` осталось бы ~105 симв). Структурный перебор фиксируется
записью `roadmap/codex-skill-listing-fallback-overflow.md` + строка индекса
`roadmap/README.md` (D29/OQ-7).

## Тесты (`packages/skiller/scripts/test.sh`)

```
$ bash packages/skiller/scripts/test.sh
tests: OK (Ran 522 tests)
```

Новые тесты обеих моделей — `packages/skiller/tests/test_budget_listing_providers.py`
(13 кейсов: единицы моделей не смешиваются, Codex без per-entry капа vs Claude с
капом 1 536, граница «ровно на фолбэке» не считается перебором, неизвестный
`--provider` завершается ошибкой, `--profiles` покрывает каждый поставляемый
профиль, дефолтный CLI-вывод без `--provider` не меняется). Чужой инвариант не
тронут:

```
$ git diff --stat packages/skiller/tests/test_profile_listing_budget.py
(пусто)

$ PYTHONPATH=packages/skiller/lib:. python3 -m unittest discover \
    -s packages/skiller/tests -p 'test_profile_listing_budget.py' -v
... (3 теста) ... OK
```

## `validate.sh` §17 (WARN-гейт) — изолированный прогон

**Почему изолированно:** дерево несёт ДВА ПРЕДСУЩЕСТВУЮЩИХ гейта, красных РАНЬШЕ
секции 17 в порядке скрипта — §12b (реестр устарел, долг P0.5) и §14 (протухшие
переводы `packages/skiller/skills/repository-bootstrap/package-architecture/
SKILL.md`, тот же долг, не пересекается с `Files` этого item'а). §12b снят как
побочный эффект `skiller registry` (нужен и для собственной регенерации
`skill-authoring`), §14 остаётся — package-architecture НЕ в `Files` P3.4, и его
регенерация требует содержательного перевода чужого 225-строчного RU-источника,
не механической правки; это записано в Pending Work/Known Deviations, не
исправлено молча. Тот же приём («секция извлечена sed'ом из закоммиченного
`validate.sh`») уже применялся в P3.3 для секции 16 по той же причине.

```
$ sed -n '/# --- 17\. WARN/,$p' packages/skiller/scripts/validate.sh > /tmp/section17.sh
$ REPO_ROOT="$(pwd)/packages/skiller" bash /tmp/section17.sh
WARN: 9 профил(ей) листинга превышают фолбэк-бюджет обнаружения Codex (8 000 симв) — структурный перебор, см. roadmap/ (D29/OQ-7, 2026.07.29-HARNESS-AGNOSTIC P3.4):
  dart-flutter: 10417 симв (×1.3)
  laravel-project: 18602 симв (×2.3)
  node-frontend: 18128 симв (×2.3)
  node-package: 10146 симв (×1.3)
  obsidian-vault: 13192 симв (×1.6)
  php-package: 16959 симв (×2.1)
  platform-service: 24705 симв (×3.1)
  python-backend: 13069 симв (×1.6)
  standalone: 52954 симв (×6.6)
exit: 0
```

## `validate.sh` (полный прогон) — красный на ПРЕДСУЩЕСТВУЮЩЕМ §14, не на диффе item'а

```
$ bash packages/skiller/scripts/validate.sh
...
⚠️  EN протух (RU правлен после генерации): skills/repository-bootstrap/package-architecture/SKILL.md (регенерируй из SKILL.ru.md)
ERROR: протухшие переводы SKILL.ru.md→SKILL.md (regen + check-translations.sh --stamp)
$ echo "exit: $?"
exit: 1
```

Секция 17 в полном прогоне НЕ достигается (скрипт останавливается на §14 раньше
по порядку) — доказана изолированно выше. `git diff --stat` на дереве не несёт
`packages/skiller/skills/repository-bootstrap/package-architecture/*` — этот item
её не трогал и не переставлял штамп сверки (см. Known Deviations Pn.m).

## `skiller registry --check`

```
$ bash packages/skiller/bin/skiller registry --check
registry --check: артефакты актуальны (skills.json/_index.md/манифесты/graph.md/budget.md)
```

## `plan-lint`

```
$ python3 packages/task/scripts/plan-lint.py plans/2026.07.29-HARNESS-AGNOSTIC
plan-lint: OK (1 план(ов), 0 ошибок, 5 предупреждений)
```

5 WARN — известные false positives (легенда DoR-маркера + phase-first за
незакрытую P2), задокументированы в `handoff.md` Open risks с P3.1.

## P3.5 — дельта листинга после починки blocker-набора (39 описаний)

Замер `--profiles` ДО (git stash починки, дерево до P3.5) и ПОСЛЕ (item-коммит
P3.5), оба провайдера, все поставляемые профили:

```
ДО:
| Профиль | Codex (симв) | Claude Code (ток) |
|:--|--:|--:|
| blender | 7308 | 2179 |
| dart-flutter | 10417 | 3107 |
| laravel-project | 18602 | 5550 |
| node-frontend | 18128 | 5404 |
| node-package | 10146 | 3030 |
| obsidian-vault | 13192 | 3941 |
| php-package | 16959 | 5058 |
| platform-service | 24705 | 7363 |
| python-backend | 13069 | 3901 |
| standalone | 52954 | 15778 |

ПОСЛЕ:
| Профиль | Codex (симв) | Claude Code (ток) |
|:--|--:|--:|
| blender | 7391 (+83) | 2203 (+24) |
| dart-flutter | 10612 (+195) | 3164 (+57) |
| laravel-project | 18874 (+272) | 5630 (+80) |
| node-frontend | 18368 (+240) | 5474 (+70) |
| node-package | 10236 (+90) | 3056 (+26) |
| obsidian-vault | 13559 (+367) | 4047 (+106) |
| php-package | 17121 (+162) | 5107 (+49) |
| platform-service | 25019 (+314) | 7456 (+93) |
| python-backend | 13297 (+228) | 3967 (+66) |
| standalone | 53589 (+635) | 15964 (+186) |
```

**Вердикт:** починка растит листинг, как и предупреждает Implementation Rules
item'а — цена измерена, не подразумевается. Ни один профиль не пересёк границу
вердикта: девять профилей, УЖЕ переполнявшие Codex-фолбэк ДО правки, остаются
переполненными (структурный перебор из P3.4, `roadmap/codex-skill-listing-
fallback-overflow.md`, D29/OQ-7 — без изменений в счёте вердикта, только в
абсолютных симв/ток); на стороне Claude Code переполняет по-прежнему только
`standalone` (именованное исключение, не новый долг). Рычаг №4 владельца
(сжатие описаний) этим item'ом не нарушен — гейт работает на оси качества
триггера, не сжатия (D52 граница item'а).

## `skiller budget --check-core --strict` — после починки

```
$ bash packages/skiller/bin/skiller budget --check-core --strict
CORE резидент (⊕ tier-0): 663 ток / target 750 — OK (9/9 скиллов)
```

Ни один CORE-скилл (`core-policy.json::skills`) не входит в blocker-набор 39 —
резидентный бюджет не пострадал от починки.

## Негативный прогон нового гейта (description-триггер)

```
$ sed -i 's/description: .*/description: "short"/' packages/skiller/skills/roles/tech-lead/SKILL.md
$ bash packages/skiller/scripts/validate.sh 2>&1 | grep tech-lead
ERROR: skills/roles/tech-lead/SKILL.md: description без триггерной фразы (...) и НЕ в
scripts/desc-trigger-burndown.txt — новый долг запрещён (рэтчет P3.5): ...
$ # восстановлено git-чекаутом сразу после прогона
```

## Blocker-набор до/после (Validation-скрипт item'а)

```
ДО:  BLOCKERS 39 [architect/agent-design, architect/api-design, ... roles/tech-lead]
ПОСЛЕ: BLOCKERS 0 []
```
