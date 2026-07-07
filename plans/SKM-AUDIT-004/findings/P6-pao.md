# P6.1 — Laravel PAO: первопричинный разбор (read-only)

Дата: 2026-07-07. Severity-enum: `blocker | major | minor | nit` (как в P1).

## Внешняя верификация (RAG, не по памяти)

- Источник: [laravel.com/blog — Introducing Laravel PAO](https://laravel.com/blog/introducing-laravel-pao-cleaner-output-for-ai-agents)
  (Nuno Maduro, 2026-05-14, WebFetch 2026-07-07) + локальный скилл
  `packages/skiller/skills/php/pao/SKILL.md`.
- `laravel/pao` — dev-only composer-пакет («PHP agent-optimized output»). Детектит запуск
  PHPUnit/Pest/Paratest/PHPStan/Rector/Artisan внутри AI-агента (env `CLAUDE_CODE`,
  `CURSOR_AGENT`, …) → компактный JSON (~20 токенов вместо тысяч); терминал человека не меняется.
  Требования: PHP ≥ 8.3, Laravel 12+ (или standalone PHP через Composer-автолоадер).
  Установка: `composer require laravel/pao --dev`.
- **Не связан с Laravel Boost** (MCP-сервер инспекции приложения) — два независимых пакета,
  не смешивать (см. D9 в `plan.md`).

## Repro: Agelto (2026-07-07)

- `php -v` → `PHP 8.5.8` (требование ≥8.3 **выполнено**; в composer.json `"php": "^8.4"`).
- Скилл доставлен: `.claude/skills/pao` присутствует.
- `grep -i "laravel/pao" composer.lock` → 0 совпадений.
- `vendor/laravel/pao` → `No such file or directory`.
- ⇒ **PAO не установлен**, хотя знание про него (скилл) доставлено и все хард-требования
  выполнены.
- Побочно (НЕ про PAO): `.mcp.json` Agelto содержит запись `laravel-boost` (`boost:mcp`)
  без установленного composer-пакета Boost — orphaned MCP-запись, гигиена, отдельная от PAO
  (см. Code Guidance ниже, действие — P6.4).

## Первопричина (repo-grounded, подтверждено чтением кода)

### F-pao-1 · major · `packages/maind/lib/maind/provision/sync.py:274` · онбординг доставляет PAO только как скилл, установку не исполняет

`grep -rn "composer require\|composer install" packages/*/lib` → 0 попаданий (единственное
упоминание слова `pao` в коде — `sync.py:274`, комментарий-пример «новый скилл в уже выбранном
бакете (напр. `pao` в `php`) доезжает до уже онбордженных проектов» — про раздачу каталога
скиллов, не про установку зависимости). Весь контракт тулинга с PAO = «раздать SKILL.md, который
советует агенту поставить пакет» — пассивная доставка знания, не действие и не инвариант
онбординга. Сценарий отказа: PHP-проект онбордится (`maind onboard`/`skiller integrate`), скилл
`pao` копируется/подключается вместе с бакетом `php`, но `composer require laravel/pao --dev`
никто не запускает и не предлагает — установка зависит от того, заметит ли агент скилл
проактивно (на Agelto не заметил).

### F-pao-2 · major · `packages/{skiller,harness,analyst,maind}/lib/*/doctor.py` · нет doctor-гейта на отсутствие PAO

`grep -rln "pao\|composer require\|composer install" packages/*/lib/*/doctor.py` → 0 попаданий
во всех 4 doctor.py (`skiller/lib/skiller/doctor.py`, `harness/lib/harness/doctor.py`,
`analyst/lib/analyst/doctor.py`, `maind/lib/maind/doctor.py`). Ни один doctor не утверждает
«PHP-проект (≥8.3) ⇒ `laravel/pao` установлен» → онбординг Agelto прошёл **GREEN** при
фактическом отсутствии PAO — тот же класс тихого ложно-зелёного, что и находки P1 (аудит
трёхдневного диффа). Сценарий отказа: `doctor` (любой из четырёх) репортит здоровый проект,
владелец проекта не имеет сигнала о недостающей токен-экономии, узнаёт об этом только по
внешнему наблюдению (field-feedback), как здесь.

### F-pao-3 · nit · `packages/skiller/skills/php/pao/SKILL.md:19,56-58` · провенанс-нестыковка ссылок в скилле

Тело скилла (`## Steps`, шаг 2, строка 27) верно использует composer-имя `laravel/pao`
(подтверждённое блогом Laravel как официальное), но описание (строка 19) и раздел `## Links`
(строки 56-58) линкуют на `github.com/nunomaduro/pao` — репозиторий автора/до вхождения в
организацию `laravel`, а не текущий официальный `laravel/pao` из блога. Несостыковка
косметическая (composer-команда верна, PAO будет установлен правильно), но ссылки в скилле не
совпадают с официальным источником, на который сам скилл же и опирается. Действие — починка в
P6.2 (Scope P6.2 явно включает «провенанс-ссылки в скилле, если подтвердится» — подтверждено
здесь).

## Вывод

Дыра контракта онбординга: **«доставить скилл» ≠ «установить и верифицировать зависимость»**.
Для PHP-проекта, где токен-экономия вывода инструментов — прямая измеримая выгода (ядро
философии `context-economy` корневого CLAUDE.md), PAO должен быть **инвариантом онбординга**
(F-pao-1 → P6.2) с видимым doctor-гейтом при нарушении (F-pao-2 → P6.3), а не надеждой на
проактивность агента, прочитавшего скилл.

## Несвязанная гигиена (НЕ про PAO — не смешивать, см. D9)

Orphaned MCP-запись `laravel-boost` в `.mcp.json` Agelto без установленного composer-пакета
Boost — зафиксировано выше в разделе Repro. Это про **Laravel Boost** (MCP-сервер инспекции),
независимый от PAO пакет; действие (доустановить Boost ИЛИ убрать запись) — предмет P6.4, не
P6.2/P6.3.

## Validation

- Находки — с `file:line` и repro (см. выше).
- Внешняя верификация процитирована (блог + локальный скилл, дата WebFetch указана).
- Код не тронут — `git status` показывает только новый файл findings (см. Completion Notes P6.1
  в `phases/P6.md`).
