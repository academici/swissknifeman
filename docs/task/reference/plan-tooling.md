# Plan tooling: сверочные гейты `plans/`

## Lean lifecycle selection

`task.plan_lifecycle.select(LifecycleInput(...))` — рекомендация по оценённому воздействию,
не workflow engine и не gate. Неизвестное имя риска отклоняется с диагностикой.
Разрешённый порядок работы выбирает исполнитель; правила Scope/Acceptance/authority действуют.

Read-only подготовка snapshot через существующий launcher:

```bash
python3 packages/task/scripts/plan-session.py prepare --plan-dir plans/<ID> --item P1.1 --risk none
```

`none` означает проведённую оценку без hard risk, а не отсутствие входов. Можно повторить
`--risk security-auth --risk public-api-schema`. Snapshot объединяет контекст, evidence graph,
producer readiness и Validation prerequisites; он не заменяет route/admission перед записью.

```bash
bash packages/task/scripts/validate.sh --plan plans/<ID>
bash packages/task/scripts/validate.sh --fleet
python3 packages/task/scripts/plan-session.py installed --source packages/task --installed <selected-task-cache>
```

Без `--plan`/`--fleet` validator квалифицирует пакет. Повторяй `--plan` для затронутой dependency
closure; `--fleet` оставлен CI/release. Чужой red видим; пересечение со scope остаётся gating.
`installed` сравнивает version/path/digest выбранной копии с исходниками, возвращая ненулевой
exit при drift. Проверяй отдельно Task и core; затем обновляй через provider plugin manager
и проверяй новым запуском. Checkout `--check` не доказывает свежесть установленного пакета.

## Codex launch-block для handoff

Launch-block выбирает native-синтаксис по активному provider adapter: Claude Code получает
slash-команду, Codex — полный `codex ...` запуск. Эти native-формы не смешиваются. Таблица хранит
только Batch/Model/Thinking/Context/Суть; команда всегда идёт после неё отдельным fenced-блоком,
чтобы Markdown-переносы ячейки не ломали копирование. Предпочтительна одна физическая строка;
если shell-команда разбита намеренно, каждая продолжаемая строка заканчивается `\`.

При фактическом final общий renderer сохраняет рекомендацию Next независимо от optional lease.
Native-блок обязателен при fresh-session boundary, в том числе по явной просьбе владельца.
Завершение заказанного scope может оставить `continue-root`: итог содержит successor как
рекомендацию для текущего чата и не требует нового процесса. Подробности — в
[continue-first](../continue-first.md#continue-root-без-лишней-сессии).

`plan-run` поддерживает два равноправных входа. В уже открытой CLI-сессии оператор может выполнить
`/clear`, выбрать требуемые Routing модель/effort и вставить provider-neutral `$ task:…` command.
Либо можно открыть новый процесс нативной командой с явными cwd, моделью, effort, approval и
sandbox. Поэтому handoff сохраняет обе формы; для `plan-run` маршрут всегда берётся из Routing
следующего item'а:

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:plan-run <PLAN-ID> <Pn.m>'
```

Provider-neutral форма удобна для `/clear`, native-блок делает отдельный запуск воспроизводимым.

Перед любой plan-командой (`plan-design`, `plan-exec`, `plan-run`, `plan-audit`,
`plan-close`) Codex-проекция получает current-route provenance автоматически до первой
product-journal мутации. Команда ниже показана для `plan-run`; проекция подставляет exact
текущую Task-команду и её аргументы:

```bash
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH=packages/task/lib \
  python3 -m task.route_evidence_codex capture \
  --expected-invocation '$ task:plan-run <PLAN-ID> <Pn.m>' \
  --expected-cwd "$PWD")"
```

Adapter сначала связывает `CODEX_THREAD_ID` с единственным active rollout и читает последний
provider-written `turn_context`: model, effort, cwd, approval, sandbox и exact Task prompt.
Evidence получает `source=provider-thread-state`; поэтому смена `/model`/`/reasoning` и новый chat
после `/clear` проверяются по текущему состоянию, а не по argv старого процесса. Если thread state
действительно отсутствует, остаётся compatibility fallback: exact native argv с `-m`,
`model_reasoning_effort`, `-C`, `-a never`, `-s danger-full-access` и Task prompt. Malformed или
mismatched state отказывает fail-closed и не подменяется `codex doctor`, config-файлом, actor prose
или памятью агента.

Codex runtime передаёт этот JSON-объект непосредственно в оба `task_contract` gate
(`pre-mutation` и `pre-final`). Поэтому один и тот же provider-written record, а не повторно
введённые модель/effort placeholders, определяет разрешение. Старый рецепт
`provider-doctor`/`self-attested` не допускается в Codex projection; regression test проверяет это
для всех пяти plan-команд.

Два stdlib-скрипта в `plans/` (не в `packages/task/lib/`, не встроены в `plan_lint.py` —
у каждого свой предмет): `cross-plan-files.py` (межплановые пересечения `Files`) и
`verify-citations.py` (ссылки-доказательства резолвятся до факта). Оба — CLI одной формы:
человекочитаемый отчёт всегда, `--strict` переключает только exit-код. Третий гейт живёт
В `plan_lint.py` самом (`packages/task/lib/task/plan_lint.py` + лаунчер
`packages/task/scripts/plan-lint.py`) — режим `--conflicts`, задокументирован ниже.

## Калибровка верхней оценки токенов v2

`packages/task/scripts/calibrate-token-estimate.py` вручную замораживает активный
`configs/token-estimate-calibration.json` только после bounded Codex-прогона. Команда требует
явно назвать provider и model; сеть и provider CLI используются только здесь, никогда не в
offline `task.token_estimate` или CI:

```bash
python3 packages/task/scripts/calibrate-token-estimate.py \
  --provider codex --model gpt-5.6-terra --smoke-probe
python3 packages/task/scripts/calibrate-token-estimate.py \
  --provider codex --model gpt-5.6-terra
```

Адаптер запускает `codex exec --json` в пустом временном cwd и нормализует только
`turn.completed.usage.input_tokens`; cache-поля остаются диагностикой и не прибавляются к
total. Полный прогон принимает ровно 8 разных real-source samples (≤16 KiB каждый, ≤128 KiB
всего) через bracket-controls (не более 3 payload между controls, ≤12 provider calls). Артефакт
несёт provider/model/protocol/classifier provenance и fail-closed отвергает v1 или несовпадение
classifier. Исторические Claude v1 artifact и probe-log остаются plan-owned snapshots; будущий
Claude adapter — отдельная additive provider projection.

## Hard-gate бюджета чтения для layout v2

Обычный `plan-lint.py plans/<ID>` применяет frozen `read-budget` v1 только к плану с
`Layout | v2`. Для каждого `ready` item он отказывает при превышении D2(a), нечитаемом или
нерезолвленном обязательном входе и файле, превышающем любой из двух лимитов чтения. Отсутствие
калибровки, `read-limit` или plan-owned threshold contract также является ERROR; retired layout не
получает ни opt-in, ни warning-ветви. Детали диагностик и владельцы вычислений —
[`plan-read-budget-gate.md`](plan-read-budget-gate.md).

## Downstream gate producer→consumer

`plan-downstream.py` механически выводит потребителей из объявленных путей, прогоняет применимое
подмножество их `Validation` и сохраняет трёхзначный результат с ключом версии ТЗ и item-коммита
продюсера. Проверка наличия записи выключена до P6. CLI, exit-коды и форма finding описаны в
[`plan-downstream-gate.md`](plan-downstream-gate.md).

## `packages/task/scripts/verify-plan-citations.py`

Проверяет ссылки-доказательства вида `` `path:line` ``/`` `path::symbol` `` во ВСЕЙ прозе живого
плана: `plan.md`, `handoff.md`, `roadmap.md`, `phases/*.md`, `findings/**/*.md`,
`research/**/*.md`, `brief/**/*.md` (рекурсивно; `artifacts/`, `closure/`, `root/` сознательно
вне поверхности — сырьё измерений/генерируемые отчёты/переезжает в `docs/` проекта). Файл
существует, номер строки внутри файла, символ после `::` встречается в файле (поиск по имени,
БЕЗ AST-разбора).

```bash
python3 packages/task/scripts/verify-plan-citations.py                        # все живые планы
python3 packages/task/scripts/verify-plan-citations.py plans/<PLAN-ID>         # один план (путь ИЛИ голый ID)
python3 packages/task/scripts/verify-plan-citations.py plans/<PLAN-ID> --strict   # exit 1 при любой находке
python3 packages/task/scripts/verify-plan-citations.py --include-archive          # + архивные планы
python3 packages/task/scripts/verify-plan-citations.py --selftest                 # embedded unittest
```

**Читать exit-код:** без `--strict` скрипт всегда возвращает `0` (отчёт — для чтения глазами
или CI-лога, не гейт); с `--strict` — `1`, если хотя бы одна ссылка не резолвилась, иначе `0`.

**Проверяемые формы** (ссылка — ОДИН токен внутри одинарных бэктиков):
- `` `path/to/file.ext:123` `` — строка внутри файла;
- `` `path/to/file.ext:123-145` `` — диапазон строк;
- `` `path/to/file.ext:123,145` `` — пара несмежных строк;
- `` `path/to/file.ext::symbol` `` — имя символа есть в файле. `a::B::c` — гейт грепает
  ТОЛЬКО лист `c` (без разбора вложенности класс/метод) — граница инструмента, а не баг:
  «валидация символа» здесь означает «имя встречается в файле», не «сигнатура совпадает».
- `` `path/to/file.json::a.b.c` `` — путь ключей ВНУТРИ JSON-файла (P11.2). Резолвится
  `json.load` + **greedy-обход**: на каждом уровне берётся ДЛИННЕЙШИЙ дотированный префикс
  остатка, являющийся ключом текущего объекта (для списка — целочисленный индекс). Greedy
  не украшение: ключи плановых артефактов сами содержат точки (`owners.P2.2` = ключ
  `"P2.2"` внутри `owners`) — наивный `split(".")` даёт ложную находку. Файл, не
  распарсившийся как JSON, — находка «JSON не парсится» (не тихий пропуск, не фолбэк на
  грep). Граница та же, что у `::symbol`: **«ключ существует» ≠ «значение совпадает»** —
  значение по ключу гейт не сверяет.

**Путь обязан содержать `/`.** Голое path-упоминание без суффикса не проверяется вовсе (класс
отклонён измерением 16% шума, D128). Резолв — ДВУХШАГОВЫЙ и порядок баз ЗАФИКСИРОВАН: (1)
корень репозитория, (2) каталог плана-источника (`plans/<PLAN-ID>/`) — первая база, под которой
файл существует, определяет резолв, суффикс проверяется относительно НЕЁ. Короткая
внутриплановая форма (например, `` `phases/P1.md:80` `` как продолжение перечисления после
полного пути чуть раньше в прозе) резолвится ВТОРОЙ базой — это не «восстановление
подразумеваемого контекста прозы», а вторая детерминированная база, известная скрипту по
построению (сам обходит `plans/<PLAN-ID>/`). Файл, не найденный ни от одной из двух баз, —
находка, называющая ОБЕ пробованные базы. Общая граница «машина не угадывает» остаётся: третьей
базы (корень пакета) нет, а голый путь без суффикса по-прежнему не проверяется.

**Известные исключения** — ссылки на пути ВНЕ репозитория (например, файл npm-зависимости,
прочитанный напрямую при RAG-верификации) или на деливерабл БУДУЩЕГО item'а, которого на
этом дереве ещё нет по построению. Данные, не код: `packages/task/configs/verify-citations-known-exceptions.json`
(если файла нет — исключений нет, что и означает пустой отчёт по умолчанию); перечень
глобален (по строке цитаты, не по плану), заводится и пополняется триажем гейта, не правкой
кода:

```json
{
  "exceptions": [
    {"citation": "path/to/file.ext:123", "reason": "почему это не дефект"}
  ]
}
```

Заведён P11.5 (`research/27-P11-citation-gate-target-design.md` §3) по четырём МЕХАНИЧЕСКИМ
правилам триажа находки (не суждение на глаз): **R1** — короткая форма в `findings/`/
`research/`/`plan.md`/`handoff.md`/`roadmap.md` своего плана, полный путь восстанавливается
ОДНОЗНАЧНО (ровно один файл в `git ls-files` с таким суффиксом) → цитата ЧИНИТСЯ на полный
путь; **R2** — кандидатов ноль (внешний файл вне репозитория) или больше одного (путь
неоднозначен) → запись в перечень с адресной причиной; **R3** — цитата в ЧУЖОМ плане →
только запись в перечень (чужая проза не правится, `plans/README.md` И4–И6); **R4** — цитата
внутри полей ЗАКРЫТОГО item'а (ТЗ) своего плана (включая цитаты внутри дословных
транскриптов findings-документов, ссылающиеся на позиции того item'а) → запись в перечень +
Pending Work (правка ТЗ закрытых items вне скоупа триажа).

**Тесты** — `python3 packages/task/scripts/verify-plan-citations.py --selftest` (embedded `unittest`, отдельного
файла в `packages/task/tests/` нет: скрипт stdlib-only и самодостаточен, той же формы, что
`packages/task/scripts/cross-plan-files.py`).

## `packages/task/scripts/cross-plan-files.py`

См. докстринг файла — сверка `Files` между живыми планами, `--strict` baseline-режим против
`cross-plan-known-intersections.json`.

## `plan-lint.py --conflicts`

Третья нога конфликт-скана `plan-audit-loop.md` §A.1 (2026.07.31-SKM-LEAN P5.9) — детерминированная
сверка «EN-only канон (`SKILL.md`) ↔ реализация (реестры-константы `plan_lint.py`)», **без аргумента-плана**
(артефакт-проверка, не линт конкретного `plans/<ID>`; `path`, если передан, игнорируется):

```bash
python3 packages/task/scripts/plan-lint.py --conflicts
```

Точные литералы объявляются директивами `i18n-keep` в том же EN-каноне. Семь сверяемых
классов, каждая находка — обе стороны с `файл:строка`
(«канон говорит X → реализация говорит Y»):

1. шесть канонических статусов (`STATUSES`) ↔ SKILL.md §4;
2. 16 полей item'а и их порядок (`REQUIRED_ITEM_FIELDS`) ↔ SKILL.md §3;
3. закрытый enum форм `Next` (альтернация `SEMANTIC_NEXT_RE`) ↔ SKILL.md §6;
4. три значения layout-v2 `Context` (`CONTEXT_VALUES`) ↔ SKILL.md §6;
5. литералы `i18n-keep` (`CANON_LITERALS`) ↔ директивы `<!-- i18n-keep: … -->` в SKILL.md (тот
   же предикат, что T2 `packages/task/tests/test_canon_literals.py`, доступный из CLI без unittest);
6. форма launch-block'а: `LAUNCH_TABLE_ROW_RE` ↔ metadata-таблица без команды,
   provider-native fenced command block обязателен, а `LAUNCH_COMMAND_ROW_RE` остаётся только
   reader-side совместимостью старых планов;
7. обязательные carrier literals блока `Layout v2 carrier contract`.

Если монорепо должно нести canon, но `SKILL.md` исчез, сверка fail-closed. Только настоящий
standalone package layout может пропустить literal unittest, не превращая repo-проверку в
vacuous pass. Зарегистрирован ступенью `packages/task/scripts/validate.sh` и первой,
самой дешёвой командой конфликт-скана `packages/task/commands/plan-audit.md` (§1).

Отдельно, в РЕЖИМЕ ПЛАНА (без `--conflicts`, обычный `plan-lint.py plans/<ID>`) — диагностика
**повтора поля** внутри тела item'а (D90): строка `**Поле:** значение`, случайно совпавшая по
форме внутри свободной прозы другого поля (например, `**Validation:** …`, дописанная как
инлайн-заметка в Completion Notes), молча подменяла собой РАННЕЕ легитимное значение поля — и у
`plan_lint`, и у `task_contract`, оба берут ПОСЛЕДНЕЕ вхождение. ERROR называет item, поле и обе
строки (`файл:строка` каждой).
