# HANDOFF — 2026-08-01 — after P4.6

**Next:** close: task:plan-close 2026.07.31-SKM-LEAN P4

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | закрыть терминальную фазу P4 (таблицы, Phase Handoff, `closure/P4.json`, lint) — все 6 items 🟢 Done |

```
/task:plan-close 2026.07.31-SKM-LEAN P4
```

**Done:** Этим заходом — **P4.6 закрыт 🟢 Done** (`plan-run`, sonnet/high, ровно
предписанному `implementation/high` — совпадение, не перебор):

- Издан `packages/harness/lib/harness/run/__init__.py` (`cmd_run`) — склеивает
  `plan_reader.queue()` → (`worker.run()`/`gate.pre_launch_verdict()`) → `gate.verdict()` →
  `journal.maybe_write()` последовательно, останов на первом RED, ATTENTION не блокирует
  (D8/D9/Implementation Rule 3). Зарегистрирован в ТРЁХ местах: `cli.COMMANDS["run"]`,
  `bin/harness` whitelist `case` + usage-комментарий (роутер зонтика `bin/swissknifeman`
  не правился — passthrough уже был, проверено `env run --help`).
- `--dry-run` — read-only: не вызывает `worker.run`/`gate.snapshot_before`/`gate.verdict`/
  `journal.maybe_write` (проверено юнит-тестом со смок-заглушками, бросающими
  `AssertionError`), не производит диффа (`git status --porcelain` до/после идентичен —
  и на юнит-фикстуре, и на живой боевой фазе P5).
- `packages/harness/docs/reference/exec-wave.md` создан, зарегистрирован в ОБОИХ
  sidebar'ах VitePress (пер-пакетная + агрегированная сборка, `grep` подтверждает
  вхождение в каждом — F22 не повторён).
- Двупронговая приёмка (D33, `findings/P4-wave-acceptance.md`): (a) `--dry-run` на живой
  фазе P5 — 3 `[ВОЖДЕНИЕ]` + 6 `[ОТКАЗ]` (`EXEC-NOT-PLAN-EXEC`), точный `argv`, ноль
  записей; (b) сквозная волна на изолированной фикстуре (`p4-6-fixture-plan.sh`, план
  `P4-6-FIXTURE`, temp git-репо, символическая ссылка `packages/task` + directory-
  marketplace на РЕАЛЬНЫЙ монорепо для доступности плагина `task`) с настоящими `claude
  2.1.220`-воркерами. **Заход 1 упёрся в РЕАЛЬНЫЙ `PORTABILITY_INPUT_MISSING`** (дефект
  спеки самой фикстуры — `Inputs: —` без committed execution input у tier
  `committed-bundle`; НЕ дефект драйвера) — воркер корректно эскалировал, `gate` дал `RED`,
  волна остановилась на первом item'е: fail-safe подтверждён на РЕАЛЬНОМ отказе, не
  синтетике. Фикстура пофикшена (`Required Reads` получил committed input), **заход 2 —
  оба item'а `GREEN`**, `cost_usd_total=1.8969`, `duration_ms_total≈310с`, вмешательств
  драйвера **0** (оба item'а самозакрылись, D32 подтверждён живьём — `journal.jsonl`
  фикстуры несёт только строки воркера). Реальность правки подтверждена git-логом
  фикстуры (2 item-коммита с кодом+тестом, 2 bookkeeping-коммита) и `plan-lint` (0 ошибок).
  Первое (синтетическое, класс назван явно) число для критерия OQ-3/**P7.1**: доля
  вмешательств `0/2`.
- `bash packages/harness/scripts/test.sh` — **630 тестов** (было 618 на P4.5, +12 в новом
  `test_run_cli.py`), зелено; `validate.sh` — зелено (10/10); `plan-lint` плана — 0 ошибок,
  4 WARN (все преэкзистентны, без изменений этим заходом).
- Известных material-отклонений нет (Known Deviations P4.6 — пусто); первый заход
  приёмки (b), упёршийся в дефект фикстуры, — это отладка ДО закрытия (нормальная часть
  Implementation), не process-отклонение исполнителя: причина в спеке синтетической
  фикстуры, не в Routing/Scope этого item'а.

**Фаза P4 терминальна (6/6 items 🟢 Done)** — счётчик Board обновлён (`Items 🟢/всего` =
6/6), Status-ячейка Board флипнута на `🟢 Done` (`plan_lint.py` требует ЭТО дословно:
«все items 🟢 Done → статус фазы обязан быть 🟢 Done», иначе ERROR на самом счётчике).
**Остаточный ERROR ПОСЛЕ этого флипа (плановый, не дефект P4.6):** тот же `plan_lint.py`
ТУТ ЖЕ требует `plans/2026.07.31-SKM-LEAN/closure/P4.json` (Closure Protocol v1 — «фаза
терминальна 🟢, но отчёта закрытия нет») — артефакт, которым владеет ИСКЛЮЧИТЕЛЬНО
`plan-close` (прецедент — P1/P2/P3 несут `closure/Pn.json`, все от `plan-close`,
ОТДЕЛЬНОЙ записью Update Log ПОСЛЕ последнего item'а фазы). `plan-exec.md`, который этот
item исполнял дословно, о `closure/*.json` не упоминает вовсе — это НЕ его протокол.
Названо честно (Known Deviations/Pending Work P4.6, `phases/P4.md`): `plan-lint`
--baseline на bookkeeping-коммите этого item'а даёт K=1, а не K=0. Next ниже (`plan-close
P4`) — прямая и единственная ремедиация.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠, терминальна) · **P4 6/6
(items терминальны, фаза ждёт `plan-close`)** · P5 0/9 (⬜) · P6 0/3 (⬜) · P7 0/4 (⬜).
Всего 38 items. После `plan-close P4` — следующая фаза по порядку (`plan.md` Execution
Mode phase-first) — **P5** (Гигиена и безопасность, ещё детализирована полностью, DoR
пройден design-проходом — первый item **P5.1**, `frontier/high`, `manual`).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/plan.md` §3 Routing (P4.6) ·
`phases/P4.md` P4.6 Completion Notes · `findings/P4-wave-acceptance.md` (числа обоих
прогонов приёмки) · `plans/2026.07.31-SKM-LEAN/artifacts/p4-6-fixture-plan.sh`
(воспроизводимый строитель фикстуры) · `packages/harness/lib/harness/run/__init__.py`
(`cmd_run`) · `packages/harness/docs/reference/exec-wave.md` (пользовательская
документация команды).

**Open risks:** без изменений по содержанию от предыдущего handoff, кроме закрытого P4.6
(гейт вердикта проверен живьём — риск «строже гейта» из предыдущего захода СНЯТ
наблюдением, не остаётся open risk), плюс:

- **Артефакт закрытого P4.1 правлен после закрытия** (контракт §5/§7 + frontmatter
  `amended`) — зафиксировано в D103 Consequences, задним числом Completion Notes P4.1 не
  переписывались. Аудит фазы должен видеть это как решение, а не как дрейф.
- **Осознанный остаток риска D106:** незакоммиченный код в путях `Files` ВНЕ каталога
  плана вердиктом не ловится — разбор поля `Files` на пути был бы третьей собственной
  точкой разбора против §3 контракта.
- **U1/U2 контракта остаются `[UNVERIFIED]` с адресом «первое боевое наблюдение»** — без
  изменений (P4.3 закрыл только U3; P4.6 приёмка была на ФИКСТУРЕ, не боевым наблюдением
  U1/U2 — квота/долгий прогон там не воспроизводились).
- **Контракт пинован на `06fefc87`, канон живёт своей жизнью** — без изменений этим
  заходом (P4.6 контракт не правил).
- **Два WARN линтера по фазе P4** — без изменений (латентные ложные срабатывания, адрес —
  `plan-close 2026.07.31-SKM-LEAN P4` либо отдельный fix-item; один из двух — строка 67
  `[NEEDS CLARIFICATION]`-ложняк на тексте самого DoR-чеклиста, второй — «оркестрация без
  workflow-скрипта», тоже ложняк — DoR фазы явно снял критерий §7).
- **`fixtures_data/run/**` не несёт статический пример журнала со строками воркера** —
  P4.5 Pending Work, адрес не назначен; P4.6 приёмка использовала ЖИВУЮ фикстуру вместо
  статического примера — та же находка, адрес не сдвинулся.
- **`worker.py` — единственный источник знания о `command-routing.json` в драйвере** — без
  изменений.
- (в силе) остаток `desc-trigger-burndown.txt` 61 запись · 221/229 скиллов без тиров
  `model:`/`effort:` · `paths:` не раскатан (D98) · `disable-model-invocation` только на 4
  пилотных · 14 файлов evals-заглушек · **OQ-9** (`ACCEPTANCE_NOT_PUBLIC` против D77,
  владелец вне плана) · долг **D90** · 3 дефекта в `snippets/` `devops/db-test-preflight`
  · кандидаты под `context: fork` отложены · конфликт правил в ТЗ P3.6 · токен
  `contradictory evidence` вне enum §10 · дефект генератора `.mcp.json.example` ·
  path-scoped rules только на пилоте `dterema/app` · `resolve_active_set` слеп к плагинам
  · Boost/`.ai`-CLAUDE.md флот не покрыт P2.2 · пять секций-кандидатов P2.1 резидентны
  (D89) · гейт размера файла целиком · токенная оценка продублирована в двух пакетах ·
  `closure/P1.json` hash устарел (D87) · остаточная находка `verify-citations` в
  `phases/P2.md` (P2.3).
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый
  `RESEARCH/AUDIT-loqum-findings.md`, неотслеживаемые `.swissknife/`, `audits/`) — этим
  заходом не тронут и не коммитился.

**Workarounds/Deferred/Open questions:** обходных приёмов в СКОУПЕ item'а не применялось
(фикстура приёмки использовала ephemeral venv для `pytest` внутри СЕБЯ — задокументировано
воркером в её собственных Workarounds, не влияет на Scope этого item'а). Отложено явно:
U1/U2 (боевое наблюдение), экономика волны за пределами фикстуры (P4.6 дал только
синтетическое число), Codex-водитель (U4 → вне плана, D9), остаток риска D106
(незакоммиченный код вне каталога плана), статический пример `journal.jsonl` в
`fixtures_data/run/**` (P4.5 Pending Work, адрес не назначен). Новых open questions не
заведено; открытых остаётся **три** — OQ-3 · OQ-6 · OQ-8 — плюс OQ-9 (владелец протокола,
вне этого плана). OQ-3 получила первое (синтетическое) число — вход **P7.1**.
