# P6.2 — Лог sync-волн (router + maind-хуки + packs + skills + гигиена)

Дата: 2026-07-12. Порядок волн: Brain первым (D15), затем остальной флот.

## Волна 0 — Brain (канарейка)

- `maind sync --project brain --only memory-hook,health-hook --mode update` → оба `ok/changed=true`
  (были stale — старые версии хуков).
- `maind sync --project brain --only mcp --mode update` → `ok/changed=false` (уже чисто,
  agentmemory-raw отсутствует).
- Brain не имеет `agent-router.config.json` и `agent-pack.lock.json` локально → router/packs шаг
  пропущен (нечего апгрейдить).
- `maind doctor --context` после волны 0: `brain context=17620 WARN` (без ошибок; бакет-ревизия —
  P6.3, не эта волна).

Успех подтверждён → продолжение по остальному флоту (~16 проектов).

## Волна 1 — maind-хуки (memory-hook + health-hook), весь флот

`maind sync --all --only memory-hook,health-hook --mode update`: 50 записей, **0 ошибок**.
21 проект обновлён (stale→ok), остальные skip (fresh/absent — не управляются этим хуком) +
4 тестовые фикстуры `local-repo` (пропущены — нет MODE/пути, ожидаемо).

## Волна 2 — MCP-sweep, весь флот

`maind sync --all --only mcp --mode update` (dry+apply): **0 изменений** — agentmemory-raw
нигде не найден, весь флот уже чист по MCP. 3 WARN про тестовые фикстуры `local-repo`
(пути в /tmp не существуют — старые unit-test артефакты, не реальные проекты).

## Волна 3 — Router policy v2

- `harness hooks --global` — переустановлен глобальный `~/.claude/hooks/agent-router/`:
  policy v1 (RU, 1445 симв) → v2 (EN-терс, 1186 симв ≈296 ток), подтверждено diff'ом
  (`IDENTICAL now` после копирования). Разово на машину (не per-project).
- `harness router --generate --target <p>` — только 2 проекта имеют локальный
  `.claude/agent-router.config.json` (остальной флот использует глобальный): `azguard`, `vaulter`.
  Оба перегенерены (5 команд, 11 агентов, 2 локальных скилла), без ошибок.

## Волна 4 — agent-packs upgrade

14 проектов имеют `.claude/agent-pack.lock.json`. Апгрейд по паку (`--pack <p> --target <dir>`),
**0 сбоев** (rc=0 везде):

| Проект | Паки (версия→версия) | Конфликты (.pack-new) |
|:--|:--|:--|
| swissknifeman | role-maintainer 0.2.1→0.2.2, role-tech-lead 0.2.1→0.2.2 | — |
| agelto | _common 0.4.0→0.4.1, backend-laravel 0.12.0→0.12.2 | — |
| flexcrm | _common 0.4.0→0.4.1, backend-laravel 0.12.1→0.12.2 | — |
| erp-sdk | role-maintainer 0.2.1→0.2.2 | — |
| azguard | _common 0.4.0→0.4.1, laravel-package 0.2.1→0.2.2, role-maintainer 0.2.1→0.2.2 | docs/05_AI/guidelines/subagents-and-workflows.md |
| botkit | _common 0.4.0→0.4.1, laravel-package 0.2.1→0.2.2, role-maintainer 0.2.1→0.2.2 | — |
| vaulter | _common 0.4.0→0.4.1, laravel-package 0.2.1→0.2.2, role-maintainer 0.2.1→0.2.2 | — |
| corex | _common 0.4.0→0.4.1, laravel-package 0.2.1→0.2.2, role-maintainer 0.2.1→0.2.2 | — |
| memster | _common 0.4.0→0.4.1, backend-laravel 0.12.1→0.12.2 | docs/05_AI/guidelines/subagents-and-workflows.md |
| vintera/cms | _common 0.4.0→0.4.1, laravel-package 0.2.0→0.2.2 | — |
| edufy | _common 0.4.0→0.4.1, backend-laravel 0.12.1→0.12.2 | docs/05_AI/guidelines/subagents-and-workflows.md |
| dterema | _common 0.4.0→0.4.1, backend-laravel 0.12.0→0.12.2, laravel-package 0.2.0→0.2.2, role-cto 0.1.0→0.1.2, role-tech-lead 0.2.0→0.2.2 | docs/05_AI/guidelines/subagents-and-workflows.md; 9 файлов laravel-package (slice-builder/test-writer/reviewer/spec-writer/test-verifier/security-review/dev-loop.js/review-gate.sh/tests.md) — вторая dev-loop-персона (backend-laravel + laravel-package одновременно) |
| sibintek-insiders | _common 0.4.0→0.4.1, laravel-package 0.2.1→0.2.2 | — |
| chatom | _common 0.4.0→0.4.1, laravel-package 0.2.1→0.2.2 | — |

Конфликты — ожидаемое поведение апгрейдера (локальная правка `subagents-and-workflows.md` /
двойной пак у dterema): safe-apply-часть накатилась, конфликтная — оставлена нетронутой +
записан `.pack-new` рядом (владелец мержит вручную). Не форсилось — по Implementation Rules.
dterema warn (removed commands в 0.12.2: code-review/security-check/test-gen.md) — не удалялись
авто, тоже по правилу.

## Волна 5 — `.bak`-гигиена

Разовая чистка: `find <proj>/.claude -name '*.bak' -delete` по всем 21 проекту фонда
(список показан до удаления) — **331 файл** (в основном свежие backup-копии от самого этого
sync/upgrade-прогона + накопленные с прошлых ручных правок). Не найдено уже — потерь нет
(бэкапы регенерируются при следующей записи merge-writer'ов).

## Волна 6 — vendor-sync (skiller)

10 vendor-канальных проектов (`~/.swissknifeman/projects.json`, channel=vendor):
**8 успешно, 2 сбоя** (≤3 — порог массового сбоя не пройден, продолжение волны корректно):

| Проект | Результат |
|:--|:--|
| agelto | `+127 ~0 -0 =0` (.claude/skills) |
| diabox | `+0 ~4 -0 =13` (.cursor/skills) |
| dterema/app | `+0 ~4 -0 =23` (.agents/skills) |
| dterema/dterema | `+97 ~0 -0 =0` (.claude/skills) |
| flexcrm | **ERROR**: `.swissknifeman/config.json` не найден (пред-существующий дрейф — репо есть, конфига нет; не создан этим прогоном, не в Scope P6.2 чинить — Pending Work) |
| azguard | `+97 ~0 -0 =0` (.claude/skills) |
| botkit | `+97 ~0 -0 =0` (.claude/skills) |
| vintera/cms | `+24 ~0 -0 =0` (.claude/skills) |
| vintera/vintera | `+0 ~5 -0 =25` (.agents/skills), 17 WARN «бакет переехал» (frontend/* → frontend-vue/frontend-linting/frontend-vite/frontend-nuxt/frontend-animations/frontend-figma — legacy-имена бакетов в конфиге устарели, не блокирует sync, но конфиг стоит обновить — Pending Work) |
| sova | **ERROR**: `.swissknifeman/config.json` не найден (тот же дрейф, вне scope `axioma` fleet — sova не в `config.json` maind, отдельная регистрация в skiller) |

`+127` у agelto ожидаемо и НЕ регресс: локальный `.claude/skills` был рассинхронизирован
(11 физических каталогов при 20 заявленных бакетах) — sync восстановил консистентность с
текущим `.swissknifeman/config.json`; сокращение количества/размера бакетов — предмет P6.3
(следующий item), не этой волны.

## Итоговая проверка

- `maind doctor --context` после всех волн: 21 реальный проект — числовой `context=`, **0 n/a**
  (3 `n/a` — тестовые фикстуры `/tmp/tmp.*/local-repo` из прошлых unit-test прогонов, не реальные
  проекты флота).
- `maind sync --all --only memory-hook,health-hook --mode update --dry-run`: **0 stale** —
  все managed-хуки консистентны.
- Выборочная проверка 3 проектов (agelto/azguard/brain): `maind-memory.sh` несёт новый
  комментарий-версию (шапка "managed by maind — SessionStart: инжект ДАЙДЖЕСТА…"); azguard/brain
  `maind-health.sh` содержит `--strict` (agelto health-hook не установлен локально — `skip/absent`,
  ожидаемо, не управляется этим проектом).

## Остаток / исключения (Pending Work)

- `flexcrm`, `sova` — нет `.swissknifeman/config.json` при vendor-регистрации в
  `~/.swissknifeman/projects.json` (дрейф до P6.2, не создан этим прогоном); физический
  vendor-sync для них не выполнен. Требует отдельного решения (создать конфиг или снять
  vendor-регистрацию) — не Scope P6.2.
- `vintera/vintera` — 17 legacy-имён бакетов (`frontend/*`) в `.swissknifeman/config.json`,
  требуют переименования на новые (frontend-vue/frontend-linting/frontend-vite/frontend-nuxt/
  frontend-animations/frontend-figma) — sync отработал (маппинг есть), но конфиг стоит обновить.
- `dterema` — два одновременных Laravel-пака (backend-laravel + laravel-package) дают частичное
  пересечение файлов агентов — 9 файлов конфликтуют (`.pack-new`), ручной мерж владельцем.
- 4 проекта (azguard/memster/edufy/dterema) несут конфликт по
  `docs/05_AI/guidelines/subagents-and-workflows.md` (локальная правка) — `.pack-new` рядом,
  не форсилось.
