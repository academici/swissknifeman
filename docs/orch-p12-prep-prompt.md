# Промпт 1: доделать и подтвердить доработки после P11

Скопируйте блок целиком в новую сессию (Sonnet 5.5 high или Opus 5.5) в корне репозитория, ветка `ecosystem-split`.
Ветку не публиковать. После него — `docs/orch-p12-observer-prompt.md`.

```text
Ты доводишь до готовности механизм оркестрации перед фазой P12. После прогона фазы P11 механизм переработан:
что и почему — docs/orch-p11-review-opus.md; исходные журналы — docs/orch-p11-run-findings.md и
docs/orch-p11-observer-journal.md; опции и маяки — packages/orch/docs/conductor.md. Изменения лежат в рабочем дереве
незакоммиченными. Правила работы — CLAUDE.md (блок Development mode) и CLAUDE.local.md (движок, пути). Состояние
машины (установка и вход CLI) не менять, push не делать, широкий pkill не использовать.

Часть A. Доделать и закоммитить (логику не менять, только довести):
1. Тесты planner красные (SKM_TEST_JOBS=1 bash packages/planner/scripts/test.sh):
   - граничный тест: packages/planner/dev-skills/planner-development-philosophy/SKILL.md не называет другие модули
     (строка про `standalone.tools` уже поправлена — проверь);
   - compat-тесты старых планов (tests/compat/test_old_plans.py: EXPECTED_WARNINGS_0_28_3 и проверка множества
     {"read_missing", "modify_missing"}): новое предупреждение `validation_id_clash` ожидаемо — добавь его;
   - две ERROR (check и finish на «мусорном» плане) уже исправлены — убедись, что зелёные.
2. Скилл менялся — перегенерируй проекции в песочнице:
   S=$(bash scripts/dev-sandbox.sh new --name reg | tail -1);
   bash scripts/dev-sandbox.sh run "$S" -- bash packages/skiller/bin/skiller registry; bash scripts/dev-sandbox.sh remove "$S";
   python3 scripts/golden.py capture --only skiller-registry --reason "planner skill wording"; python3 scripts/golden.py check.
3. Проверка: SKM_TEST_CLASH=fail python3 scripts/affected-tests.py --run; bash packages/orch/scripts/validate.sh;
   bash packages/planner/scripts/validate.sh; python3 scripts/public-hygiene.py.
4. Три коммита с явными путями (git commit -- <paths>), русские Conventional Commits; перед каждым — git status,
   в индексе ничего лишнего:
   (a) aicore/hub/тесты: par_unittest, параллельные тесты maind/planner/моста, affected-tests, docs-impact,
       analyst как инструмент, CI;
   (b) orch/planner/мост: движок дирижёра, роли, схемы, ворота фазы, документация модулей;
   (c) инструкции и документы: CLAUDE.md, скиллы и проекции, golden, CHANGELOG, docs/orch-p11-review-opus.md,
       docs/orch-p12-*.md.

Часть B. Подтвердить прогонами и починить всплывшее (каждый дефект — тест, падающий без правки; коммит по явным путям):
5. Полный проход ядра на HEAD (долг фазы P11), с замером времени каждой команды и SKM_TEST_CLASH=fail:
   python3 scripts/affected-tests.py --tier all --run --no-cache -j 4; bash scripts/test-integration.sh (и --with-tools);
   python3 scripts/ecosystem-units.py check --strict; python3 scripts/ecosystem-units.py standalone --baseline;
   python3 scripts/golden.py check; bash scripts/lint.sh; bash scripts/test-bridges.sh; scripts/e2e-*.sh и
   aicore schema compat --base origin/ecosystem-split — только внутри scripts/dev-sandbox.sh.
   Красное чини у владельца модуля, затем весь проход ещё раз.
6. Кэш: affected-tests.py --run дважды без изменений — второй раз всё [cached]; правка одного модуля пересчитывает
   только его и его мосты.
7. Изоляция: один короткий запуск роли Claude Code тем argv, что показывает conduct.py run --dry-run --scenario full
   (поля routes и isolation_args), с --safe-mode: allowedTools/disallowedTools действуют, Landlock ro-run работает,
   registrar выполняет ровно `python3 *orch.py source register *`, стартовый контекст ≈ 6 K токенов. Если что-то
   ломается — почини (перенеси нужное в argv) или сузь изоляцию этой роли с объяснением.
8. Ремонт отчёта: подай роли report-fixer (haiku) три битых блока (stage-report с exit "zero", review-findings без id,
   triage-result с отклонённым Major без воспроизведения) через prompts.report_fixer; результат проходит схему и не
   выдумывает фактов. Запиши время и токены.
9. Репетиция одного пункта пробного плана в отдельном клоне дирижёром с умолчаниями по коду: маяки STAGE_IDLE и
   CHECK_SLOW с содержимым, changed_paths из git, путь вне write set — отклонение и строка в промпте ревьюера, блок
   Repository rules в промпте исполнителя, отчёт наблюдателя с маяками и долей проверок, estimate.py до запуска;
   затем resume --retry, run --adopt и settle на искусственных ситуациях там же.
10. План P12 (если детализирован): plan.py check без предупреждений check_cadence и validation_id_clash; тяжёлые
    проверки — в phase.validation; task_files собраны grep-ом по ссылкам. Только привести к правилам скилла
    planner-development-philosophy, суть не менять.

Журнал — секция «Подготовка к P12» в docs/orch-p11-run-findings.md (симптом, причина, правка, замер). В конце —
короткий отчёт: что закоммичено (хэши), что подтверждено, что исправлено, цифры времени до/после, что осталось.
```
