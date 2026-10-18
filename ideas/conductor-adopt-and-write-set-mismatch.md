# Идея: `orch conduct run --adopt` отказывает на законных побочных правках; write-set пункта не совпадает с реальным

Статус: идея, не реализовано. Источник: сессия оркестрации PLAN3 (vaulter), переход P5.3 с ручного цикла на кондуктор,
2026-10-17. Связано: `orchestrator-session-bypasses-conductor.md`.

## Что произошло

Ручной субагент P5.3 был остановлен на середине (~15 мин работы, 192 файла), пункт передан кондуктору:
`orch conduct run --plan P --items P5.3 P5.4 --batch --adopt`. Ответ:

```
WORKTREE_DIRTY — run --adopt takes only changes inside the write set of P5.3; outside it:
docs/guides/errors.md, docs/reference/errors.md, docs/ru/reference/errors.md, packages/documents/resources/lang/en/p…
```

Кондуктор считает «своими» только пути из write-set пункта (`task_files` + `scope.include`) и папки плана/артефактов.
Всё остальное — чужая грязь; `--adopt` не берёт её, а остановка не оставляет выбора: закоммитить чужое, отложить или
стереть. Я отложил в `git stash` (весь набор сохранён в `stash@{0}`, дерево возвращено к HEAD) и стартовал пункт с нуля.
Потеряно ~15 минут уже сделанной работы.

## Почему write-set не совпал

Это не ошибка агента: пункт объективно требует правок вне заявленных `task_files`. На P4/P5 так было у каждого пункта:

- сгенерированные страницы (`docs/{,ru/}reference/errors.md|config.md|commands.md`) при любом новом problem code/ключе;
- снимки и ожидаемые схемы (`tests/Fixtures/Schema/expected/**`, `__snapshots__`), `openapi/*.yaml`;
- ledger и реестры (`tests/Repo/Arch/Fixtures/**`, `tests/baseline/**`, `tests/suites.json`, `tests/zones.json`,
  `packages/*/tests/groups.php`), `tests/baseline/*.list`;
- lock-файлы и манифесты (`package-lock.json`, `composer.json`, `release/packages.json`);
- lang-файлы и config нового пакета.

Автор плана перечисляет «смысловые» файлы, а производные от них (генераторы, снимки, реестры) нигде не объявлены. Политика
`scope.outside: deviation` позволяет их править в рабочем прогоне, но на `--adopt` та же политика не применяется:
правило жёстче, чем в обычном ходе исполнителя.

## Как исправить в SKM

1. **`--adopt` применяет `scope.outside`.** Пути вне write-set при политике `deviation` попадают в список «внешних правок
   попытки» (в промпт исполнителю: «они сделаны прошлой попыткой, проверь и либо оставь с записью отклонения, либо
   откати»), а не вызывают `WORKTREE_DIRTY`. Остановка — только при `scope.outside: block` либо при правках, не
   относящихся к попытке (например, изменённые до claim файлы).
2. **Манифест производных путей в плане.** Поле пункта/фазы `derived_paths` (или `write_set_extra`) с глобами
   генераторов, снимков, реестров и lock-файлов; кондуктор включает их в write-set; `plan.py check` предупреждает, если
   пункт добавляет типы/ключи/problem codes, а производные не объявлены. Заполняется `plan-design` по шаблону проекта
   (stub), а не вручную в каждом пункте.
3. **Явное «отложить попытку».** `orch conduct run --adopt` при `WORKTREE_DIRTY` предлагает команду:
   `orch conduct shelve --items P5.3` (сохраняет в служебную ветку/stash с сообщением и привязывает к пункту), и
   `orch conduct run … --restore-shelf` возвращает набор исполнителю как «прошлую попытку». Тогда отказ не превращается
   в ручной `git stash` с обходными путями.
4. **Диагностика.** Сообщение называет все внешние пути (сейчас обрезано), их число и предлагает три действия: расширить
   write-set (`--allow-path` / `derived_paths`), `shelve`, `settle`.
5. **Ручной `git stash` с pathspec** (`git stash push -u -- . ':!plans'`) сохранил набор, но не вернул дерево к HEAD
   (`stash@{0}` создан, рабочие файлы остались): команда `shelve` должна делать это атомарно и безопасно, не требуя `rm`
   (хук `deny_hard` блокирует `rm` в безопасных папках).

## Критерии приёмки

- `--adopt` на дереве с производными правками (генерируемые страницы, снимки, ledger) не останавливается при
  `scope.outside: deviation`; в отчёте пункта эти пути перечислены как отклонение.
- Пункт с новым problem code/ключом без объявленных производных путей получает предупреждение `plan.py check`.
- `orch conduct shelve/--restore-shelf` переносит попытку между ручным и кондукторным исполнением без потери работы.

## Что сделано в текущей сессии

- Попытка отложена: `git stash list` → `stash@{0}: P5.3 partial work of killed manual agent` (174 tracked + 5 untracked).
  Восстановить: `git stash show -p stash@{0}`, `git checkout stash@{0} -- <path>`, untracked — из `stash@{0}^3`.
- P5.3/P5.4 запущены кондуктором с нуля (`--batch --debug`, frontier-исполнитель через `--options`).

## Дополнение (2026-10-17): `run --input followup.json --commit` — COMMIT_REFUSED
Правки по групповому ревью (adhoc-пункт) прошли executor и checks (green), но коммит упал: кондуктор делает `git add` пути
`.swissknifeman` (игнорируется .gitignore). Работа осталась в индексе, закоммитил вручную. Исправить: исключать
игнорируемые пути из списка коммита; не считать их изменением пункта.

## Дополнение (2026-10-18): `--dry-run` не проверяет digest ручного followup
Ручной `execution-input` (правка текста goal) прошёл `--dry-run`, а реальный запуск упал `INPUT_INVALID: DIGEST_MISMATCH`.
Нужно: dry-run валидирует вход по контракту; команда `orch conduct input seal FILE` пересчитывает digest и input_id.
