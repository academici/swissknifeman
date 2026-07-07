# P1.2 — Adversarial code review диффа `ea8e4d3..HEAD`

Ревьюер: opus/xhigh (субагент), read-only. Диапазон подтверждён: 17 коммитов (см. `git log
--oneline ea8e4d3..HEAD`). Дубли с `findings/P1-gates.md` (F1, F2) не повторяются здесь.

## Таблица: коммит → вердикт

| Commit | Пакет | Вердикт |
|:--|:--|:--|
| 1d45be9 merge: gitignore-ephemeral-artifacts | harness/skiller | 1 находка (N1) |
| b6a8225 feat(harness,skiller): agent-pack+registry | harness/skiller | 1 находка (N1); известный F1 |
| b310f03 build: ignore ephemeral analyst artifacts | .claude/ | 1 находка (N1 — не расстрекивает уже закоммиченное) |
| a7377dd Merge PR #139 | — | ok |
| 7402046 fix(maind): `_ensure_project` матчинг по пути | maind | 1 находка (N4 — symlink-дедуп-пробел) |
| 01717c8 Merge PR #138 | — | ok |
| 410f216 docs: чек-лист drift-gate | docs | ok |
| 1ee0977 docs(maind): Serena/sync | docs | ok |
| 9a3c19d feat(maind): doctor `--skill-drift` | maind | ok (покрыт тестами); nit N5 |
| 78acc25 feat(skiller): doctor `--vendor-drift` | skiller | ok (покрыт тестами) |
| 916f970 feat(task): plan-lint принимает plan-design | task | ok (покрыт тестами) |
| 295951c feat(maind): analyze напоминает о pending_lessons | maind | ok (покрыт тестами) |
| 903ff60 feat(harness): run-report хук → analyst digest | harness | 1 находка (N3 — нет теста, hardcode-путь) |
| 0195366 fix(analyst): сигнал A | analyst | 2 находки (N2a major, N2b minor) |
| 00b2a22 fix(skiller): topology init монорепо-корень | skiller | ok (standalone-fallback проверен) |
| c48a515 feat(task): готовая команда + Model Hint | task | ok |
| a7800e2 Merge PR #137 | — | ok |

Все 17 коммитов покрыты (14 без блокирующих находок, из них 5 «ok» — merge/docs без своей логики).

## Находки

### N2a · major · `packages/analyst/lib/analyst/digest.py:45-72` · сигнал A глушит реальные Laravel-прогоны — CONFIRMED
`_is_real_check` относит к «разведке» команды, реально запускающие тест-раннер, не входящий в
`_RUNNER_EXEC`: `php artisan test` → `False`, `php artisan test --filter Foo` → `False`,
`sail test` → `False` (проверено исполнением). Экосистема несёт `backend-laravel` agent-pack, где
дефолтный раннер — `php artisan test`; хук кладёт его в `bash.tests` (по `TEST_PAT`), но
`extract_resolved_failures` его отфильтровывает → пара «упал→прошёл» на `php artisan test`
никогда не порождает урок. Петля обучения слепа для Laravel-стека. Ни один тест не покрывает
удержание `php artisan test` как реального прогона (тесты — только pytest/pest/npm).

### N2b · minor · `packages/analyst/lib/analyst/digest.py:64-66` · прогон с `||` отбрасывается — CONFIRMED
`pytest tests/ || exit 1` → `False`. Ветка «`||` ⇒ проверка присутствия, не прогон» рубит легитимные
guard-паттерны (`pytest || exit 1`, `... | xargs pytest`). Такие вызовы реально исполняют раннер и
сохраняют exit-код — настоящий resolved-failure молча теряется. Тестом не покрыто.

### N1 · minor · `packages/harness/.claude/analyst/{audit,events}.ndjson` · ephemeral-логи закоммичены в VCS — CONFIRMED
`git ls-files` показывает оба трекнутыми; `git check-ignore` → exit 1 (не игнорируются). Содержат
session-UUID, timestamp, id, производный от абсолютного домашнего пути одного разработчика.
Новый авто-digest хук (903ff60) дописывает строку на каждом session-end → постоянный diff-churn,
риск merge-конфликтов, утечка личного home-пути в репозиторий. `b310f03` добавил `.gitignore`
вперёд, но уже закоммиченные файлы это не расстрекивает (нужен `git rm --cached`).

### N3 · minor · `packages/harness/.../run-report/run-report.py:147-188` · авто-digest без теста, hardcode-fallback — CONFIRMED (design), нетестируемо
Резолв `_analyst_bin` (ANALYST_BIN → PATH → topology → hardcode) и `_run_digest` не покрыты ни
одним тестом (harness validate.sh только py_compile'ит хук). Fallback-путь
`~/projects/packages/swissknifeman/packages/analyst/bin/analyst` (строка ~169) машинно-специфичен —
на чужой машине без analyst в PATH и без узла swissknifeman в topology.json петля обучения молча
не срабатывает (best-effort, не крэш). `subprocess.run(..., timeout=30)` ограничивает задержку
SessionEnd 30 секундами, сбой/таймаут глотается — сессия не ломается. По хотспоту (a) из Code
Guidance: безопасно, но непокрыто тестом и с хрупким hardcode-дефолтом.

### N4 · minor · `packages/maind/lib/maind/provision/onboard.py:55-62` · дедуп по пути не резолвит симлинки — CONFIRMED
`norm_path` делает только `expanduser+normpath`, без резолва симлинков. Основной инцидент
(тройная запись loqum при повторном `onboard` на тот же путь) починен и покрыт тестом;
trailing-slash и `.`-сегменты нормализуются корректно. Остаточный edge: повторный `maind onboard`
через симлинк/иной эквивалентный путь на тот же каталог всё ещё штампует дубль-запись.
Не основной кейс инцидента, но не закрыт.

### N5 · nit · `packages/maind/lib/maind/doctor.py` (`_skill_drift`) · «absent» всегда = дрейф — PLAUSIBLE
Для enabled-проекта, где ecosystem-mcp/setup скилл никогда не раскатывали, состояние `"absent"`
попадает в drifted навсегда → вечный warn в `maind doctor`. По дизайну ожидаемо (enabled ⇒ должен
иметь скилл), но потенциальный шумный false-positive для проектов, сознательно без
ecosystem-скиллов. Косметика, не блокирует.

## Исходы (P2.1)

- **N2a · major → fixed.** `_RUNNER_EXEC` (`packages/analyst/lib/analyst/digest.py`)
  получил ветку `(?:php\s+artisan|sail)\s+test\b` (документированный Sail-shortcut на
  `artisan test`, проверено WebSearch). Регресс-тест
  `test_is_real_check_laravel_runners` (`tests/test_digest.py`).
- **N2b · minor → fixed.** Убран бланкетный `if "||" in cmd: return False` в
  `_is_real_check` — диагностику (`grep`/`ls`/`find`/… как проба присутствия) и так ловит
  соседняя проверка (раннер должен резолвиться в первом сегменте до `|`/`;`/`&`).
  Заодно `_RUNNER_EXEC` научился видеть раннер после `xargs` (`\bxargs\s+`) —
  `... | xargs pytest` без диагностического префикса в другом сегменте теперь
  резолвится как реальный прогон; комбинация `find ... | xargs pytest` (раннер и
  diagnostic-слово `find` в РАЗНЫХ сегментах одного пайплайна) остаётся непокрытой —
  корректное различение требует посегментного разбора команды (какой сегмент реально
  породил runner-match), это уже не «дешёвый minor», см. Pending Work. Регресс-тест
  `test_is_real_check_guarded_pipe_is_still_a_real_run`.
- **N1 · minor → fixed.** `git rm --cached` для `packages/harness/.claude/analyst/
  {audit,events}.ndjson` (session-UUID/timestamp/home-путь одного разработчика,
  бесконечный diff-churn от авто-digest хука). `.claude/.gitignore` пакета harness
  переведён с явного "коммитируются" на игнор обоих файлов; файлы остались на диске
  (только untrack).
- **N4 · minor → fixed.** `norm_path` (`packages/maind/lib/maind/provision/
  workspace.py`) — `os.path.normpath` → `os.path.realpath` (резолвит симлинки).
  Затрагивает все вызовы `norm_path` (`_ensure_project`, `trusted_dirs`,
  `probe.py`) — единообразно корректнее для дедупа/доверия. Регресс-тест
  `test_repeat_onboard_via_symlink_does_not_duplicate_entry`
  (`packages/maind/tests/test_onboard.py`).
- **N3 · minor → не фиксили (осознанно).** Требует тестовой инфраструктуры для
  SessionEnd-хука (`harness validate.sh` сейчас только py_compile'ит хуки) — не
  «дешёвый minor по пути» из Intent P2.1; ТЗ в самой находке не содержит конкретного
  предложения фикса (в отличие от F1/F2/N1/N2a/N2b/N4). Оставлено на отдельный item/итерацию.
- **N5 · nit → не фиксили.** Вне Scope P2.1 («nit-косметика россыпью» исключена явно).

## Проверено чисто (без находок)

- **b6a8225 / 1d45be9** (агрегатные merge-коммиты): содержат agent-pack md-шаблоны, snippets,
  roadmap-заметки, `test_common.py` (F1 — известен) и ndjson-файлы (N1). Собственной
  код-логики сверх перечисленного не несут — landing без индивидуального PR-ревью подтверждён,
  но содержимое сведено к уже обнаруженным находкам.
- **00b2a22** topology init: `find_monorepo_root(env.root) or env.root` — для standalone-раскладки
  (нет родителя с `packages/`/`core/`) корректно фолбэчит на `env.root`. Не сломано.
- **78acc25 / 9a3c19d** doctor fleet-сканы: удалённый/переименованный проект
  (`not pdir.is_dir()` → `continue`), битый `config.json` (`except SystemExit/JSONDecodeError` →
  `continue`), `plan_sync` в `try/except` — ни один путь не крэшит, все корректно скипают.
  `res["state"]` в `_skill_drift` безопасен: `_result` всегда кладёт ключ `state`.
- Все JSON-записи в диапазоне идут через существующий `atomic_write_*`; новый код (digest-фильтр,
  doctor-сканы, pending_lessons) только читает/считает — наивных записей состояния не добавляет.

## Coverage-проверка

Все 17 коммитов из `git log --oneline ea8e4d3..HEAD` присутствуют в таблице выше с явным
вердиктом; ни один не пропущен.
