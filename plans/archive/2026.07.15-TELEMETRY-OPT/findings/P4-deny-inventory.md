# P4.1 — Инвентаризация DENY-фрикции (пере-агрегация + бакет-классификация)

Метод: `find /home/vostrikov -path "*/.claude/runs/*.json" -type f` (полное доступное окно,
без `-mtime` — шире baseline/P2.1, зафиксировано фактически) → парс `tool_failures[]` (shape
`{tool, snippet}`, `run-report/_lib.py:445-447`) → фильтр по каноническому паттерну DENY →
нормализация формы команды (top-level сегменты по `;`/`&&`/`||`, голова каждого сегмента) →
группировка по (tool, форма) → счётчик повторов → бакет a/b/c по фактическим
`settings.base.json` (`permissions.allow/ask/deny`) и `hooks/auto-approve/config.json`
(`allow`/`deny_hard`/`deny_block_approve`). Агрегатор — одноразовый скрипт в scratchpad
(`p4-deny-agg.py`), не коммитится (Code Guidance item'а). Tree-anchor чисел ниже — `find`
по `/home/vostrikov` в момент запуска (2026-07-15, полный набор `*/.claude/runs/*.json`,
169 файлов).

## Фактическая цифра и сверка с baseline-118

**Два разных сигнала DENY в данных, с РАЗНОЙ формой snippet** (важное уточнение к D10 —
probe смотрел, судя по всему, только на Bash-форму):

| Сигнал | Форма snippet | Tool | # событий |
|:--|:--|:--|--:|
| Bash-DENY | `Permission to use Bash with command <cmd> has been denied.` | Bash | **75** |
| Read-DENY | `<tool_use_error>File is in a directory that is denied by your permission settings.</tool_use_error>` | Read | **23** |
| **Итого policy-shaped DENY** | | | **98** |

Команда: `find /home/vostrikov -path "*/.claude/runs/*.json" -type f \| wc -l` → 169 файлов;
агрегатор выше даёт **98** policy-shaped DENY-событий на полном окне (2026-07-15, ad-hoc).

**Расхождение с baseline-118 и D10-пробой (124/166, Bash 96) — зафиксировано честно, не
подогнано:**
- Фактическая канонически-отфильтрованная цифра (98) **ниже** обеих прежних оценок.
- Причина расхождения — методологическая, не опровержение самого кластера: (а) канонический
  фильтр `"Permission to use" in snippet` корректно ИСКЛЮЧАЕТ ложные срабатывания на голое
  подстрочное совпадение `"denied"` — в данных встречаются `mysql: ... Access denied` и ОС-шные
  `permission denied` (не Claude Code policy вообще), которые более широкий грепп на `"denied"`
  захватил бы; при подсчёте по одной лишь подстроке `"denied"` цифра поднимается до 101 (Bash+Read
  вместе), что ближе к прежним оценкам, но включает шум; (б) Read-DENY несёт СОВСЕМ ДРУГОЙ текст
  snippet (`File is in a directory that is denied…`), не `"Permission to use … has been denied."` —
  probe/D10, судя по формулировке «Bash 96 из 124», видимо считал Read отдельно похожим образом,
  но точный метод probe не сохранён как воспроизводимая команда (design-time, не задокументирован
  построчно) → сравнить артефакт-в-артефакт не получается, эта цифра (98) — новый source of truth
  взамен. Окно (169 файлов) шире исходного baseline (114), но часть run-report'ов ротируется/
  перезаписывается по session-id между прогонами — абсолютные цифры между разными днями
  структурно НЕ идентичны, только относительная структура (бакеты) сопоставима.
- **rm-гипотеза (D10 if-then) на полном окне НЕ подтвердилась** — `rm`/`rmdir`/`sudo`/`shred`
  форм всего **3 повтора** (`rm -rf .../.claude/skills/plan-protocol`, 3×2 проекта) из 98 —
  явное меньшинство. Эскалация по D10 if-then (§8 плана) **не требуется** — вывод D10
  «rm не доминирует» подтверждён, ослабление D10 не нужно.

## Бакет-классификация (обоснование — Required Reads 3–4: `settings.base.json` allow/ask/deny +
`hooks/auto-approve/config.json` allow/deny_hard/deny_block_approve)

| Бакет | Определение | Bash | Read | Итого | Доля |
|:--|:--|--:|--:|--:|--:|
| **a** — компаунд/пайп read-only | ≥2 top-level сегмента (`;`/`&&`/`\|\|`), ВСЕ головы сегментов — в read-only allow-множестве (`ls/cat/head/grep/echo/find/sed -n/…`, `hooks/auto-approve/config.json:allow`), не деструктив | 16 | — | **16** | 16% |
| **b** — корректный protection-deny (by-design) | `rm/rmdir/sudo/shred` НЕ в safe-dirs, ИЛИ путь/имя точно матчит `settings.base.json:permissions.deny` (`.env`/`.env.local`/`.env.production`/`**/*.pem`/`**/*.key`/`~/.ssh/**`/`~/.aws/**`/`**/CHANGELOG.md`/`**/skills.json`/`**/package-lock.json`/`**/composer.lock`/`**/*.lock`) — включая ВСЕ Read-DENY (директория/файл сама попала в deny) | 23 | 23 | **46** | 47% |
| **c** — needs-Owner (форма денайнута вне явного deny-паттерна, причина неоднозначна) | атомарная (не компаунд) команда, не деструктив, не content-deny-match — почему денайнута НЕ следует напрямую из читаемых allow/deny-правил | 36 | — | **36** | 37% |

**Важное уточнение к Phase Context/D10:** на полном окне бакет **(a) — МЕНЬШИНСТВО (16%)**, не
доминанта. Доминируют **(b) protection-deny by-design (47%, зеркалит baseline-гипотезу «rm/deny-
файлы», просто шире — не только rm)** и **(c) needs-Owner ambiguous (37%)**. Это НЕ откат к
исходной baseline-гипотезе (rm сам по себе — меньшинство внутри (b), основной вклад в (b) —
Read-директория-deny и Bash-чтение deny-листнутых файлов типа CHANGELOG.md/*.lock), но
**переоценивает вес (a) вниз** относительно формулировки D10/Phase Context («подавляюще
компаунд»). Расхождение — честно зафиксировано; Phase Context уже содержит if-then только на
случай rm-доминирования (не сработал), явного if-then на «a — не большинство» ТЗ не содержит →
не эскалирую формально, но рекомендация P4.2 ниже учитывает пере-взвешенную картину (дисциплина
не заточена ТОЛЬКО на компаунд-форму, а общая для всех терминальных DENY).

## Топ-10 повторных форм (по числу повторов, все Bash — Read-форма одна, не варьируется)

| # | Форма (усечено) | Повторов | Проектов | Бакет |
|:--|:--|--:|--:|:--|
| 1 | `grep -rn "guarded\|fillable\|custom_properties\|casts" .../Media.php` (варианты аргументов) | 16 | 5 | c |
| 2 | `cd .../vendor/filament && grep -rn "function datalist" forms/src` | 4 | 3 | a |
| 3 | `head -20 grep -rn "virtualAs\|storedAs" --include=*.php ...` (одна голова, не компаунд) | 4 | 3 | c |
| 4 | `ls vendor/laravel/framework/.../Schema/` | 4 | 3 | c |
| 5 | `grep -n "^DB_" .env.example ; grep -n "DB_HOST..." .env` | 4 | 2 | b (.env-сегмент) |
| 6 | `find . -path ./vendor -prune -o -name '<Test>.php' -print` | 3 | 2 | c |
| 7 | `grep -n "DB_CONNECTION" .env ; grep -n "'default'" config/database.php` | 3 | 2 | b |
| 8 | `sed -n '1,200p' .env.example` | 3 | 3 | c |
| 9 | `rm -rf .../.claude/skills/plan-protocol` | 3 | 2 | b |
| 10 | `cat -n .../CHANGELOG.md` | 2 | 2 | b |

**Форма #1 (16×, 5 проектов) — крупнейшая, требует отдельного комментария.** Атомарный
(не компаунд) `grep -rn "…"` в разных проектах на похожий medialibrary-контекст (Filament/Laravel
vendor-код, вероятно один и тот же класс агента-пака или интент-паттерн переиспользуется между
сессиями/проектами). `settings.base.json:permissions.allow` **НЕ несёт** `Bash(grep *)` (только
`Bash(rg *)`) — на уровне Claude Code core-движка bare `grep` не авто-approve'ится статическим
allow-листом; `hooks/auto-approve/config.json:allow` **несёт** `grep` — если хук активен и решает
запрос, `grep`-атомарник должен пройти. Что 16× подряд денайнуто именно так — не выводится
однозначно ни из allow, ни из deny (нет паттерна в `deny_hard`/`deny_block_approve`, нет
content-match). **Гипотеза [POSSIBLE-DEFECT], НЕ факт** (не верифицирована глубже — вне Scope
item'а, углубление в `lib/analyze.sh`/`lib/common.sh` матчинга не входит в Инвентаризацию):
проект(ы)-источник этих run-report'ов могли не иметь установленного/активного auto-approve хука
(established Laravel-стек, harness-конфиг per-project не гарантирован везде) → запрос ушёл в
обычный interactive-ask и был явно отклонён человеком/сессией — тогда это НЕ «policy(config)»-
deny вовсе, а интерактивный отказ, и бакет (c) корректен именно как «needs-Owner», а не
«баг allow-листа». Кандидат на P4.2/OQ-5: проверить per-project наличие auto-approve хука там,
где форма #1 встречается (не эта фаза).

## Рекомендация для P4.2

1. **Дисциплина-first (Ось A, применяется P4.2), формулировка ОБЩАЯ, не завязанная на бакет:**
   «DENY(policy) терминален для ТОЧНОЙ формы команды в рамках сессии — не пере-издавать verbatim
   (следующая попытка обязана быть либо атомарной/allow-matchable альтернативой, либо штатным
   тулом: `skiller`/`maind` вместо ручного `rm` managed-ассета, либо явным запросом контекста у
   пользователя, если форма неоднозначно денайнута)». Применимо равномерно к бакетам (a)/(b)/(c) —
   инвентаризация не даёт оснований сужать правило только до компаунд-Bash (a — меньшинство).
2. **Бакет (b) — НЕ трогать protection-surface.** Он уже by-design (rm/deny-файлы/директории) —
   зеркалит D6/D10: нативный гейт корректен, чинит дисциплина «не долбиться повторно», не
   ослабление правил.
3. **Бакет (c) — Owner-gated, в `open-questions.md` (OQ-5), НЕ угадывать.** Явный кандидат для
   Owner-расследования: гипотеза «нет auto-approve хука в части проектов» (форма #1) — если
   подтвердится отдельным расследованием, рычаг сместится с «политики» на «покрытие
   онбординга/harness», это вне текущей фазы.
4. **Бакет (a) — компаунд read-only.** Реальный, но МЕНЬШИНСТВО (16%). Дисциплина из п.1 его
   покрывает («издать атомарную форму вместо компаунда» — конкретный пример остаётся в скилле);
   тюнинг auto-approve под компаунд-парсинг (Ось B Обсуждения №3) остаётся Owner-gated /
   protection-surface, НЕ в скоупе plan-exec (не изменилось относительно Phase Context).

## Проверка

Внешних фактов нет — всё repo-grounded: (1) `*/.claude/runs/*.json` (169 файлов, полное окно,
`find` выше) — данные из этого репозитория/машины пользователя, не внешний источник; (2)
`packages/harness/configs/claude-code/settings.base.json` (`permissions.allow/ask/deny`, прочитан
целиком выше); (3) `packages/harness/configs/claude-code/hooks/auto-approve/config.json`
(`allow`/`deny_hard`/`deny_block_approve`, прочитан целиком); (4)
`packages/harness/configs/claude-code/hooks/run-report/_lib.py:415-455` (shape `tool_failures`).
Непроверенное → гипотеза формы #1 (P4.1 «Рекомендация», п.3) явно помечена `[POSSIBLE-DEFECT]` и
НЕ утверждается как факт — требует отдельного расследования per-project, не входит в Scope P4.1.
Обходок нет.
