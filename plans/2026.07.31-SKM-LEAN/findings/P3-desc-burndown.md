# P3.5 — приоритизация и числа: `when_to_use`-долг, тиры, обе провайдерные оси

Слой 1 (repo-grounded, живой прогон). Потребители: P3.5 Completion Notes, `roadmap/
skill-description-quality.md` Статус, `roadmap/codex-skill-listing-fallback-overflow.md`
(свежая колонка Codex как вход владельца).

## 1. Приоритизация: usage-сигнал × доля записи в листинге

Источник usage — `skiller bucket-audit --json` (окно 30 дней, `scanned_projects: 24`).
Источник доли — `tier0` (⊕ always) записи из того же прогона, делённый на сумму `tier0`
реестра (`packages/skiller/lib/skiller/budget.py::_listing_entry_tokens`, та же формула,
что гейт `validate.sh`).

`scripts/desc-trigger-burndown.txt` (P3.5, `2026.07.29-HARNESS-AGNOSTIC`) на момент старта
item'а нёс 69 записей `<bucket>/<name>`. Приоритизация — по **бакету** (папке `skills/<bucket>/`,
не по отдельной записи): usage суммируется по всем записям бакета в burn-down, доля — так же.

| Бакет | usage (Σ loaded_count) | доля листинга (Σ tier0/итого) | score = usage×доля | записей в burn-down |
|:--|--:|--:|--:|--:|
| **general** | **374** | 0.0261 | **9.775** | 8 |
| devops | 10 | 0.0216 | 0.216 | 8 |
| quality | 7 | 0.0177 | 0.124 | 5 |
| php | 9 | 0.0110 | 0.099 | 4 |
| axioma | 3 | 0.0218 | 0.065 | 4 |
| system | 1 | 0.0229 | 0.023 | 5 |
| laravel-testing | 2 | 0.0056 | 0.011 | 2 |
| остальные 21 бакет | 0 | — | 0.000 | 34 |

`general` доминирует на два порядка (score 9.78 vs следующий 0.22) — почти целиком за счёт
`general/plan-protocol` (usage 354 — резидентный CORE-скилл этого же плана-протокола,
активируется на каждый `plan-exec`/`plan-run`/`plan-close`/`plan-audit`), плюс `general`
целиком входит в CORE (раздаётся в КАЖДЫЙ проект флота — правка здесь имеет вес × 24+
проекта). Выбор пилотного бакета: **`general`**, закрыт ЦЕЛИКОМ (все 8 записей).

Полная построчная таблица (usage, tier0, score) по всем 69 исходным записям —
воспроизводима командой ниже (не заморожена в файле, чтобы не расходиться с живым прогоном):

```
skiller bucket-audit --json | python3 -c '...' # см. Completion Notes P3.5 для точного скрипта
```

## 2. `general`-бакет — было/стало/дельта (символы записи листинга)

`listing_text = (description + " " + when_to_use).strip()` — та же сумма, что читает
пере-базированный гейт `validate.sh`.

| Скилл | было (симв) | стало (симв) | дельта |
|:--|--:|--:|--:|
| plan-protocol | 158 | 162 | +4 |
| anti-drift | 134 | 162 | +28 |
| complex-task-orchestrator | 123 | 143 | +20 |
| context-economy | 225 | 201 | −24 |
| session-handoff | 121 | 141 | +20 |
| skills-ssot | 107 | 127 | +20 |
| spec-interview | 179 | 158 | −21 |
| task-brief-template | 246 | 190 | −56 |
| **ИТОГО (бакет)** | **1293** | **1284** | **−9** |

Суммарная дельта по бакету — **−9 ≤ 0** (Implementation Rule 3): перенос без сжатия НЕ
считается работой, поэтому три записи, которые не несли готовой трейлинг-компрессии
(`plan-protocol`/`anti-drift`/`complex-task-orchestrator`/`session-handoff`/`skills-ssot`
выросли, добавляя реальный триггер там, где его не было вовсе — не «перенос», а «добавление»),
скомпенсированы сжатием трёх многословных записей (`context-economy`, `spec-interview`,
`task-brief-template`), не потеряв домен-сигнал (проверено вручную, RAG:— по формуле
`roadmap/skill-description-quality.md`).

`desc-trigger-burndown.txt`: **69 → 61 записей** (на закоммиченном дереве этого item'а,
`wc -l` без комментариев/пустых строк) — все 8 удалённых строк из бакета `general`.

## 3. Обе провайдерные оси листинга — `skiller budget --profiles`

До (`HEAD` перед item'ом) / после (после `general`-правки), `Codex` — сырые символы без
капа, `Claude Code` — токены с капом 1 536 симв/запись:

| Профиль | Codex до | Codex после | Δ | Claude до | Claude после | Δ |
|:--|--:|--:|--:|--:|--:|--:|
| blender | 7391 | 7419 | +28 | 2203 | 2211 | +8 |
| dart-flutter | 10612 | 10584 | −28 | 3164 | 3155 | −9 |
| laravel-project | 18874 | 18846 | −28 | 5630 | 5621 | −9 |
| node-frontend | 18368 | 18340 | −28 | 5474 | 5465 | −9 |
| node-package | 10236 | 10264 | +28 | 2850 | 2858 | +8 |
| obsidian-vault | 13559 | 13531 | −28 | 4047 | 4038 | −9 |
| php-package | 17121 | 17149 | +28 | 4901 | 4909 | +8 |
| platform-service | 25019 | 25010 | −9 | 7063 | 7060 | −3 |
| python-backend | 13297 | 13269 | −28 | 3967 | 3958 | −9 |
| standalone | 53589 | 53580 | −9 | 15571 | 15568 | −3 |

Знак дельты по профилю зависит от того, включает ли профиль `general`-скиллы, у которых
конкретная строка сдвинулась в плюс (`plan-protocol`/`anti-drift`/… — profили, тянущие
CORE) или в минус (`context-economy`/`spec-interview`/`task-brief-template` — не все
профили их тянут напрямую, но CORE резидентен в каждом). Ни один профиль не сменил
вердикт (`ок`/`ПЕРЕБОР`) — рычаг №4 «сжатие описаний» (D74 владельца) для Codex-оси
арифметически недостаточен и на 8 скиллах, см. `roadmap/codex-skill-listing-fallback-overflow.md`
(не тронут этим item'ом — только свежие числа).

Реестр целиком (`docs/guide/budget.md`, `⊕ always`): **16146 → 16008 ток (−138)**.

## 4. Ось A первого хода — `skiller budget --first-turn` (репозиторий swissknifeman сам как проект)

До: **7179 ток** (совпадает со значением, записанным в `handoff.md` на закрытии P3.4 —
резидентный слой этим item'ом не пересекался до P3.5). После: **7176 ток** (−3, малая
дельта — этот проект тянет из `general` только часть 33-скилловой листинговой выборки).
Оба — `OK` относительно порога `target ≤16000 · warn >23000` (P1.3).

## 5. Тиры `model:`/`effort:` — вывод и гейт применимости

Полное обоснование — `docs/guide/skill-taxonomy.md` §«Тиры `model:`/`effort:`». Кратко:
override оправдан ТОЛЬКО для дискретной ограниченной задачи, не для advisory/meta-дисциплины,
применяемой параллельно основной работе сессии — форсированный override на таком скилле ломает
тир ОСНОВНОЙ задачи ради стороннего чеклита. Из 8 правленых скиллов `general`-бакета override
назначен ДВУМ:

| Скилл | Класс | `model` | `effort` |
|:--|:--|:--|:--|
| `spec-interview` | дискретная задача с суждением (интервью) | `sonnet` | `medium` |
| `task-brief-template` | дискретная механическая задача (шаблон) | `sonnet` | `low` |

Остальным ШЕСТИ (`plan-protocol`, `anti-drift`, `complex-task-orchestrator`, `context-economy`,
`session-handoff`, `skills-ssot`) override НЕ назначен — сознательное решение (гейт применимости
не пройден: `plan-protocol` несёт собственную таблицу маршрутизации §3 Routing per-item,
остальные пять — advisory/meta, активны параллельно основной задаче). Раскатка на остаток
реестра (221 скилл) продолжается по той же usage-приоритизации из §1 — Pending Work item'а.

## 6. Триггер-точность — `skiller eval <скилл> --triggers`

`general/anti-drift` — единственный из восьми с готовым `evals/` ДО item'а: прогон
`--triggers` возвращает офлайн-границу («online-оптимизация требует `claude` CLI в
окружении — недоступен, `docs/guide/evals.md`»), схема `triggers.json` валидна (без ошибок
`validate_triggers`). Для остальных семи `evals/triggers.json` заведён через
`skiller eval <скилл> --scaffold` (реальные `should_trigger`/`should_not` кейсы под новый
`when_to_use`, не заглушки-плейсхолдеры) — `--scaffold` создаёт ТРИ файла атомарно
(`evals.json`/`pressure.json`/`triggers.json`, `lib/skiller/quality/eval.py::scaffold_evals`),
удалить лишние `evals.json`/`pressure.json`-заглушки штатным `rm` не удалось (харнесс блокирует
`rm` вне `safe-dirs`) — оставлены как честный TODO-скаффолд (не скрыты, не выдаются за
заполненные поведенческие тесты; `evals coverage` метрика `validate.sh` выросла 4/173 → 11/173,
это отражает реальное состояние, не самообман). `--triggers` прогнан на всех восьми — все
восемь дают одну и ту же офлайн-границу (нет `claude` CLI в этом окружении).
