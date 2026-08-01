# P4-6 — приёмка драйвера exec-волны (`harness run`)

Два прогона (D33, `research/04-p4-driver-model.md` §6): (a) `--dry-run` на РЕАЛЬНОЙ фазе
живого плана — read-only, доказывает, что чтение работает на боевом входе; (b) сквозная
волна на изолированном фикстурном плане с настоящими `claude -p`-воркерами — доказывает,
что цикл замыкается end-to-end. Клиент: `claude 2.1.220`.

## Определение «вмешательства» (записано ДО прогона (b), Implementation Rule 5)

**Вмешательство владельца** = строка, которую **драйвер** дописывает в `journal.jsonl`
(`harness.run.journal.maybe_write`, `wrote_driver_line=True` в записи волны), а НЕ строка,
которую пишет сама сессия воркера через собственный close-протокол `/task:plan-exec`. Это
определение НЕ вводится этим отчётом — оно зафиксировано КОДОМ `P4.5` (закрыт 2026-08-01,
ДО старта P4.6): `harness.run.journal.WHO_WRITES`/`classify()` относят к «driver» РОВНО
исходы `routing-blocked` / `timeout` / `transport` / `quota` / `error` / `no-op` — то есть
случаи, когда сессия воркера НЕ дошла до close-протокола сама. Успешный самозакрывшийся
item (`outcome=ok` И терминальный статус после прогона) — `who=WORKER`, строку не пишет
никто ВТОРОЙ раз (D32); драйвер такой item НЕ засчитывает как вмешательство.

**Доля вмешательств волны** = `interventions / queued` (поля сводки
`journal.summarize_wave()`, печатаются `harness run --json`).

**Класс числа, названный ЗАРАНЕЕ (не постфактум):** результат прогона (b) — СИНТЕТИЧЕСКАЯ
величина на 2-item фикстуре с механическими item'ами, специально не несущими design-
решений. Она НЕ боевая статистика и не может использоваться как самостоятельная оценка
частоты вмешательств на реальных exec-волнах (`research/04-p4-driver-model.md` §6, OQ-3).
Первое боевое число копится штатно — журналом `journal.jsonl` при обычных exec-волнах
P5/P7 этого плана, которые читает **P7.1**.

## Прогон (a) — `--dry-run` на живой фазе

Команда (реальный прогон, репозиторий `swissknifeman`, коммит-якорь — Completion Notes
P4.6 ниже):

```
packages/harness/bin/harness run 2026.07.31-SKM-LEAN P5 --dry-run
```

Результат: очередь фазы P5 (9 item'ов) прочитана целиком — 3 `[ВОЖДЕНИЕ]` (P5.2/P5.3/P5.6,
`Exec=plan-exec`, точный `argv` каждого распечатан) + 6 `[ОТКАЗ]` (`EXEC-NOT-PLAN-EXEC`,
`Exec=manual`), 0 терминальных исключено, `next_form` резолвлен (`run-items`). Ни одной
записи не произведено — `git status --porcelain plans/2026.07.31-SKM-LEAN` ДО и ПОСЛЕ
прогона идентичен (проверено буквально: пустой diff между снимками). Полный вывод — ниже
(Completion Notes P4.6, Validation).

## Прогон (b) — сквозная волна на фикстуре

Фикстура — `plans/2026.07.31-SKM-LEAN/artifacts/p4-6-fixture-plan.sh` (изолированный
временный git-репозиторий, план `P4-6-FIXTURE`, фаза P1, два item'а `Exec=plan-exec`:
P1.1 создаёт `src/greet.py`+`tests/test_greet.py`, P1.2 добавляет `farewell()`).

Команда (из cwd фикстуры — обязательное условие: `worker.run()` не переопределяет cwd
спавна, наследует его от процесса `harness`, D29):

```
cd <fixture> && packages/harness/bin/harness run P4-6-FIXTURE P1 \
  --plans-root <fixture>/plans --timeout 900 --json
```

### Заход 1 — фикстура вскрыла реальный дефект СВОЕЙ спеки, не драйвера

Первая сборка фикстуры (`Inputs: —` у P1.1 без единого committed execution input в
`Required Reads`) закономерно упёрлась в `task.task_contract.pre_mutation ==
'block:PORTABILITY_INPUT_MISSING'` (tier `committed-bundle` — план несёт `handoff.md` —
требует непустой `execution_inputs`, D75/plan-portability-v1.md). Воркер (`claude 2.1.220`,
`session_id c871d22b-…`, 23 хода, `duration_ms=138248`, `cost_usd=0.7175`) корректно
эскалировал по протоколу `plan-exec.md` п. 5 (не импровизировал): `Status: 🔴 Blocked`,
блоккавот эскалации, коммит бухгалтерии, `ESCALATION-REQUIRED: P1.1 — …`. `gate.verdict`
классифицировал это `RED` (`escalation-in-report` + `closure-signature-incomplete` +
`lint-new-error` + `item-fields-unavailable`) и волна ОСТАНОВИЛАСЬ на первом item'е, P1.2 не
запускался (Implementation Rule 3) — цикл `plan_reader → worker → gate → journal` отработал
ровно так, как предписано: fail-safe сработал НА РЕАЛЬНОМ, не синтетическом отказе. `journal`
строку не писал (`interventions=0`) — воркер уже закрыл журнал сам записью `escalated` (D32).

Правка (по существу — дефект фикстуры, не драйвера, не item'а живого плана): `Required
Reads` P1.1 получил committed execution input (`plans/P4-6-FIXTURE/plan.md` в backtick'ах) —
`packages/task/lib/task/task_contract.build/evaluate` подтверждён напрямую ДО повторного
дорогого прогона (`pre_mutation: 'allow'`, `pre_final: 'allow'` для ОБОИХ item'ов).

### Заход 2 — сквозная волна, оба item'а GREEN

Команда (реальная, из cwd фикстуры):

```
cd /tmp/tmp.WMuNRzo3bx && \
  packages/harness/bin/harness run P4-6-FIXTURE P1 \
  --plans-root /tmp/tmp.WMuNRzo3bx/plans --timeout 900 --json
```

`run_id=wave-P4-6-FIXTURE-P1-1691e860a4ed`, клиент `claude 2.1.220 (Claude Code)`.

| Item | Вердикт | outcome | cost_usd | num_turns | duration_ms | signals_matched |
|:--|:--|:--|--:|--:|--:|:--|
| P1.1 | 🟢 GREEN | ok | 0.9779 | 40 | 168638 | `all-clear` |
| P1.2 | 🟢 GREEN | ok | 0.9191 | 37 | 141259 | `all-clear` |

**Сводка волны:** ведено 2 из 2 · GREEN 2 / ATTENTION 0 / RED 0 · **вмешательств
драйвера: 0** (доля 0/2 — определение и класс числа см. выше) · `cost_usd_total = 1.8969`
· `duration_ms_total = 309897` (≈5 мин 10 с) · `journal.jsonl` фикстуры несёт 4 строки, ВСЕ
от воркера (`in-progress`/`closed-green` ×2 item'а) — драйвер не дописал ни одной (оба item'а
самозакрылись, D32 подтверждён живьём).

**Реальность правки (не заглушка):** `git log --oneline` фикстуры после волны —
```
322ed1a план(P4-6-FIXTURE): закрыт P1.2 — bookkeeping
62baea5 фикстура: farewell() — модуль + тест (P1.2)
bcf79ec план(P4-6-FIXTURE): закрыт P1.1 — bookkeeping
46468b7 фикстура: greet() — модуль + тест (P1.1)
45e34ee фикстура: P4-6-FIXTURE создан (P4.6, p4-6-fixture-plan.sh)
```
Ровно ДВА коммита на item (item-коммит + bookkeeping), топология канона соблюдена. Итоговый
`src/greet.py` несёт обе функции (`greet`/`farewell`), `tests/test_greet.py` — оба кейса;
`python3 packages/task/scripts/plan-lint.py <fixture>/plans/P4-6-FIXTURE` после волны —
**0 ошибок, 3 предупреждения** (те же структурные WARN'ы, что и на свежесозданной фикстуре
— отсутствие `brief/`/`roadmap.md`/`index.md`, ожидаемо для синтетического плана, не
регрессия волны). Окружение фикстуры не несёт системного `pytest` — воркер обеих сессий
честно зафиксировал это в Workarounds и прогнал тесты через ephemeral venv вне репозитория
(не входит в Scope, не коммитится) — зафиксировано САМИМ воркером, не подогнано отчётом
задним числом.

## Итог

Двупронговая приёмка (D33) пройдена: (a) `--dry-run` доказал read-only чтение боевой
очереди без единой записи; (b) сквозная волна доказала полный цикл до GREEN на РЕАЛЬНОЙ
работе (код + тест + два коммита на item), включая корректный fail-safe на первом заходе
(отказ на реальном, не синтетическом, портабельность-дефекте фикстуры). Первое число для
критерия «N волн» (OQ-3, вход **P7.1**): **доля вмешательств фикстурной волны = 0/2 (0%),
класс — синтетическая, не боевая статистика.**
