import collections
import json
from pathlib import Path
from p57_audit import ART, PLAN, ROOT, SCRATCH

candidate=(ART/'state.txt').read_text().split('candidate=')[1].splitlines()[0]
records=json.loads((ART/'validation.json').read_text())
anchors=json.loads((ART/'B-anchors.json').read_text())
h=json.loads((ART/'H-results.json').read_text())
commits=json.loads((ART/'H-commit-links.json').read_text())
findings=[
 {'id':'A-1','severity':'Major','confidence':'high','owner':'P11.3',
  'title':'Инвентарь конфигов не покрывает новый мост discovery',
  'where':'scripts/test-config-inventory.py:88; configs/config-inventory.json:263; packages/orch/bridges/task/bridge.json:1',
  'repro':'`python3 scripts/test-config-inventory.py` → exit 1, `configs without an inventory entry: packages/orch/bridges/task/bridge.json`; 5/6 tests pass, `test_scope_covered` fails. Лог `@plan/artifacts/P5.7/B-config-inventory.log`.',
  'expect':'B50, D26 и P11.3 V1: каждый config в scope имеет owner и consumer, acceptance exit 0. Manifest добавлен позже в P5.1, а закрытие P5.5 не проверило корневой hygiene gate.',
  'recommendation':'Добавить manifest с его owner/consumer в инвентарь и выполнить затронутый gate при интеграции последующих конфигов.'},
 {'id':'A-2','severity':'Major','confidence':'high','owner':'P2.2',
  'title':'Guard brief считает декларацию запрета lifecycle-инструкцией',
  'where':'packages/task/bridges/orch/brief.py:207; packages/orch/roles/executor.json:25',
  'repro':'`python3 packages/task/scripts/plan.py bridge orch brief PLAN2 P4.4 --out "$S/p44.json"` → exit 1, `/reads/6/content/forbidden_inputs/1: lifecycle phrase report_api`. `report_api` здесь является значением enum в `forbidden_inputs` role-manifest, а не указанием вызывать API. Логи `D-negative-role-input.log`, `D-negative-role-literal.log`; источник текущего переноса — P7.2.',
  'expect':'R1/I1, P2.2 T2: полный worker input по обязательным reads без исполняемых lifecycle-инструкций; запрет не должен делать недоступным чтение собственного нейтрального manifest. В D получено 18 BRIEF_INCOMPLETE (включая и намеренно запрещённый lifecycle в guidance), но этот reproducer изолирует машинную отрицательную декларацию.',
  'recommendation':'Согласовать обработку деклараций forbidden_inputs с запретом исполняемых инструкций и покрыть живой brief с role-manifest тестом в мосту.'},
 {'id':'A-3','severity':'Minor','confidence':'high','owner':'P5.5',
  'title':'Свежие записи CHANGELOG описывают заменённую архитектуру',
  'where':'CHANGELOG.md:7; CHANGELOG.md:8; CHANGELOG.md:139',
  'repro':'`packages/skiller/bin/skiller resolve --role reviewer --json` → exit 2, `unrecognized arguments: --role` (`B-stale-changelog-cli.log`). Каталог находится в `packages/orch/configs/launch-catalog.json:1`, а Task review method остаётся собственным (`packages/task/skills/plan-protocol/references/review-mode.md:1`; E boundary exit 0).',
  'expect':'D12/D15/D16/D25: Skiller resolve принимает skill IDs, роли раскрывает мост потребителя; каталог принадлежит orch; review-методика Task не генерируется из Skiller. В более поздних записях этого же Unreleased уже описано правильное поведение.',
  'recommendation':'Удалить или переписать три противоречащие D12/D25 строки Unreleased по фактическим владельцам и CLI.'},
 {'id':'A-4','severity':'Minor','confidence':'high','owner':'P11.4',
  'title':'Удалённый profile-catalog ошибочно назван never released',
  'where':'CHANGELOG.md:187; core/config_paths.py:11',
  'repro':'`git cat-file -e v0.28.6:configs/profile-catalog.json` → exit 0 (`G-profile-released.log`). `git show v0.28.6:core/config_paths.py` → exit 0: root config был primary. Scratch-проба в `B-extra-contract-probes.log` (exit 0) показывает root-only layout: release path exists=True, current owner path exists=False.',
  'expect':'R21 и блок G: release provenance должна соответствовать tag. Перенос к владельцу прямо принят D26 и уже описан в Changed; аудит не предлагает отменять его. Утверждение never released фактически неверно.',
  'recommendation':'Указать реальную историю выпуска, новый путь владельца и смысл изменения при обновлении существующих root configs.'},
 {'id':'A-5','severity':'Minor','confidence':'high','owner':'P5.5',
  'title':'Architecture docs ссылаются на отсутствующий orch.discovery',
  'where':'packages/orch/docs/architecture.md:12; packages/orch/docs/architecture.md:35',
  'repro':'`rg -n orch.discovery packages/orch/docs/architecture.md` → exit 0 (строка 12); файла `packages/orch/lib/orch/discovery.py` нет. Реальный discovery — `packages/orch/bridges/task/discovery.py:28`, каталог вызывает нейтральный bridge resolver (`packages/orch/lib/orch/catalog.py:1`).',
  'expect':'R12/R19, D13 и P5.5: docs описывают текущую границу пакета, всё знание о партнёре находится в bridge.',
  'recommendation':'Описать bridge discovery вместо несуществующего модуля ядра и обновить layout docs.'},
 {'id':'A-6','severity':'Minor','confidence':'high','owner':'P6.6',
  'title':'Документация не покрывает глагол supersede из актуального CLI-каталога',
  'where':'packages/task/lib/task/plan/cli.py:799; packages/task/docs/json-plan-design.md:1',
  'repro':'`plan.py schema --verbs` → exit 0, 41 verbs; независимый поиск всех имён в `packages/task/docs/*.md` не находит только supersede (`J-results.json`, `J-schema-verbs.log`). `plan.py supersede --help` → exit 0 (`G-current-help-supersede.log`).',
  'expect':'Блок J и P6.6: документация/каталог дают полный способ работы с решениями, в том числе superseded и supersedes.',
  'recommendation':'Добавить supersede и его синтаксис в существующий справочник Task по JSON API.'},
 {'id':'A-7','severity':'Minor','confidence':'high','owner':'P5.5',
  'title':'Новые конкретные ссылки на PLAN2 остаются в общих docs и коде',
  'where':'packages/orch/README.md:4; packages/orch/README.md:33; packages/orch/docs/engine-port.md:5; packages/orch/lib/orch/schema.py:3',
  'repro':'`python3 scripts/public-hygiene.py` → exit 1 (`K-hygiene-head.log`); на базе плана с отдельным candidate-bound git index → exit 1 (`K-hygiene-base-indexed.log`). Delta на изменённых файлах содержит 44 строки (`K-hygiene-delta.json`), включая README/engine-port с PLAN2.D2/D4/P5.3. Остальная большая часть delta — синтетические fixtures/tests; их идентификаторы не доказывают утечку реальных данных.',
  'expect':'Блок K: новые реальные ссылки на план в общих продуктовых файлах должны быть отделены от приватных материалов плана и синтетических тестовых идентификаторов.',
  'recommendation':'Заменить ссылки на конкретные items/decisions в общих docs нейтральным описанием контрактов и отдельно согласовать область hygiene guard для synthetic fixtures.'},
]
for finding in findings:
    ART.joinpath('findings.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2)+'\n')

comment={
 'R1':('WRONG','Нейтральные роли существуют; декларация запрета в required role-manifest блокирует живой worker input (A-2, D-negative-role-input exit 1).'),
 'R2':('CONFIRMED','Контракт model_wait/quota/EOF и reducer подтверждены; live stream остаётся Plan 2.'),
 'R3':('CONFIRMED','Task владеет данными и регистрацией; legacy scout остаётся по D25, перенос исполнения в Plan 2.'),
 'R4':('CONFIRMED','5 ролей × 3 provider в каталоге; argv builders ничего не запускают.'),
 'R5':('CONFIRMED','Все три dry-run prepare и launch-plan validate exit 0 (D); запуск ещё NOT_IMPLEMENTED.'),
 'R6':('CONFIRMED','stage kinds, профили и 5 role manifests присутствуют; fixtures входят в orch 164 tests.'),
 'R7':('CONFIRMED','stage.provider, optional review/refusals и independent_provider проверяются существующими тестами.'),
 'R8':('CONFIRMED','run-event/raw_ref/EOF reducer есть; видимость живого исполнения явно отложена.'),
 'R9':('CONFIRMED','role-skills и resolver мост существуют; локально привязанные 11 bridge tests exit 0, исходный PATH устарел.'),
 'R10':('CONFIRMED','Закрыто решением §1/§7 DECISIONS; live engine не исследовался повторно.'),
 'R11':('CONFIRMED','EnginePort и три bindings реализуют prep; runtime engine явно отложен.'),
 'R12':('STALE','Документы существуют, но discovery/layout устарели (A-5).'),
 'R13':('CONFIRMED','Adhoc/review-only constructors, render и portability tests присутствуют и выполняются в orch suite.'),
 'R14':('CONFIRMED','Оговорка F-C1/F-C2 подтверждена; 8/70 реальных inputs и 4/4 demo валидны; portable demo проходит 3 bindings.'),
 'R15':('CONFIRMED','Принятое решение native + optional CAO есть в DECISIONS §0–§1.'),
 'R16':('CONFIRMED','3 bindings, 7 declared seeds, CAO projection и portability tests; известные оговорки входа сохраняются.'),
 'R17':('CONFIRMED','Task-owned handoff и review instructions, neutral orch roles; boundary/managed checks exit 0.'),
 'R18':('CONFIRMED','9 видов схем + defs, positive/negative fixtures и schema/semantic tests существуют и пройдены.'),
 'R19':('CONFIRMED','Связи в bridges, Skiller standalone и Task discovery в harness; D13/D16 соответствуют коду.'),
 'R20':('CONFIRMED','Runtime operations отказаны как NOT_IMPLEMENTED; Plan 2 здесь не проектировался.'),
 'R21':('WRONG','Фраза never released неверна: config есть в v0.28.6 (A-4); изменение resolver принято D26 и записано в Changed.'),
 'R22':('STALE','Q11/Q12/Q13b/Q14–Q19 .json/.md tracked; F-C3 устранён c51e9197.'),
 'R23':('CONFIRMED','Исходных items 72 (70 выполнены, 2 skipped); P5.7 добавлен позже, всего сейчас 73 (H).'),
 'R24':('STALE','Маршруты имеются; фактически 19 Sol, 38 Sonnet, 13 Opus до P5.7, а не 14; provider aliases/unknown route — прежний риск.'),
 'R25':('CONFIRMED','Coverage содержит все R1–R28/I1–I15/B44–B52; текущая независимая таблица содержит 52 строки.'),
 'R26':('UNVERIFIABLE','Требование новой design-сессии зафиксировано; независимая runtime identity исторического design не входит в доступные материалы.'),
 'R27':('STALE','Все 70 notes/acceptance IDs и W1–W12 сохранены; F-C3 закрыт, commit statistics изменились; два RED checks объяснены (H).'),
 'R28':('CONFIRMED','Conclusion существует и отмечен note P5; содержание перепроверено этим аудитом.'),
 'I1':('STALE','verify/no-truncation tests существуют; F-C3 закрыт; текущий P5.6 pack 372 KB, а не 345 KB (B-conclusion-context-budget exit 0).'),
 'I2':('CONFIRMED','Один workflow owner задокументирован; каждый prepare работает со своей binding.'),
 'I3':('CONFIRMED','INPUT_AUTHORITY + read_only/write_authority, plan_mutation forbidden; register только через Task subprocess.'),
 'I4':('CONFIRMED','Evidence fields/subject/exit/mandatory mode подтверждены suite; сверка candidate с actual tree намеренно Plan 2.'),
 'I5':('CONFIRMED','Actor attribution и известные route undershoot checks есть; для неизвестных исторических aliases class check ограничен (прежний риск).'),
 'I6':('CONFIRMED','Matching attempt replay no-op, conflict/concurrent tests существуют и прошли; commit receipts исполнит Plan 2.'),
 'I7':('CONFIRMED','Required unavailable → CAPABILITY_UNSUPPORTED; native×grok refusal явно проверяется portability test.'),
 'I8':('CONFIRMED','Catalog и Task bridge выбирают class_selectors[class][0]; новых модельных списков нет.'),
 'I9':('CONFIRMED','Task-owned review/handoff; внутри package managed sources; sync-managed-blocks --check exit 0.'),
 'I10':('CONFIRMED','POLICY_REVIEW_LIMIT и opt-in правила сохранены; executor/reviewer не запускают recursive correction.'),
 'I11':('CONFIRMED','AST stdlib-only boundary test orch и independent bridge imports scan exit 0.'),
 'I12':('CONFIRMED','--bare запрещён launch validator; в config/Task bridges совпадений нет (rg exit 1 ожидаем).'),
 'I13':('CONFIRMED','Env → neighbour → monorepo fallback в harness/task_paths и orch bridge discovery; public argument сохранился.'),
 'I14':('CONFIRMED','Unknown usage без numeric counts, quota/auth отдельные статусы; no fallback provider/model.'),
 'I15':('CONFIRMED','Artifex без candidate commits (B-artifex-history exit 0, пусто); harness/run diff только discovery callers.'),
 'B44':('CONFIRMED','Task boundary 5 tests exit 0; методика review собственная, Skiller упоминаний нет.'),
 'B45':('CONFIRMED','Task/orch/Skiller boundary tests 5/3/13 exit 0; независимый scan не нашёл foreign imports; прочие seams roadmap.'),
 'B46':('CONFIRMED','Generic bridge scanner и partner-x fixture есть; второго живого orchestration bridge, как и ранее, нет.'),
 'B47':('CONFIRMED','Standalone Skiller 803 tests, registry и validate exit 0; core/provider data разрешены D20.'),
 'B48':('STALE','Commit helper/roles/bridge есть; теперь 39 trailer commits для 34 items, прежние 38/33 — до conclusion commit.'),
 'B49':('CONFIRMED','Каталог orch и builders для claude-code/codex/grok + Task launch bridge присутствуют.'),
 'B50':('WRONG','Inventory guard exit 1: новый bridges/task/bridge.json не покрыт (A-1).'),
 'B51':('CONFIRMED','Parallel readiness/conflict data и isolation schema существуют; real process/worktree manager оставлен Plan 2.'),
 'B52':('CONFIRMED','Scope filters, budget/dedupe markers, check/design-done gates и protocol instructions реализованы; F-C1 — дефект отдельной проекции.'),
}
assert len(comment)==52
coverage=['| ID | Итог | Комментарий и независимое доказательство |','| --- | --- | --- |']
for group,count in [('R',28),('I',15),('B',9)]:
    ids=range(44,53) if group=='B' else range(1,count+1)
    for n in ids:
        iid=group+str(n);status,note=comment[iid]
        refs='; '.join(anchors.get(iid,[])[:2])
        coverage.append('| '+iid+' | '+status+' | '+note+' '+refs+' |')
cov_counts=collections.Counter(v[0] for v in comment.values())

methods={
 'A':'check/stats/get plan/list items/next exit 0; 12 phases closed, 70 done, 2 skipped, P5.7 active. Next archive — ожидаемая известная phase closure особенность, без обхода.',
 'B':'Исходники/тесты 52 строк, managed-blocks exit 0; inventory exit 1 (A-1); stale --role exit 2 (A-3); P5.6 context budget exit 0. Полная выборка B-source-final.log + anchors.',
 'C':'F-C1 brief 0 → validate 1; F-C2 set в scratch 0 → brief 0 → validate 1; F-C3 refuted на кандидате, 15 файлов c51e9197 tracked (H).',
 'D':'70 завершённых items: 8 pass, 40 schema failures только included, 18 lexical refusals, 4 historical READ_MISSING; 4 demo items pass. Demo → prepare и launch validation всех 3 bindings exit 0. A-2.',
 'E':'5 Task + 3 orch + 13 Skiller boundary tests exit 0. Независимый tracked scan и AST bridges: foreign imports отсутствуют. Три текстовых совпадения — описания внешнего harness и from task в обычной английской фразе, разрешено D16.',
 'F':'По одному широкому запуску: Task 0, Skiller validate+test 0, Harness validate+test 0, render 0, registry 0, standalone 0. Orch 1 из-за PATH Skiller v0.28.6; docs-sync 1 из-за ignored mirror. Узкий orch/skiller bridge с явным checkout root 0 (11 tests), docs-check на git archive HEAD 0; исходный environment GREEN не заявлен.',
 'G':'Tag v0.28.6, plan commit ancestor check 1 ожидаем. 24 удалённых/перенесённых paths, 18 есть в tag; публичные переносы отражены в Unreleased, но A-4 неверно отрицает release. plan.py/plan/cli.py в tag отсутствуют (git show 128), потому перечень старых verbs пуст; все 41 нынешние --help 0. Skiller --help/connect/vendor/sync 0; harness fallback сохранён.',
 'H':'212 tracked JSON carriers сканированы; notes/acceptance IDs полны, 2 red checks честно объяснены, start/finish и review notes есть. Concrete own-plan refs полны; regex candidates относятся к примерам, scratch plan и шаблонам. 39 trailer commits; 10 subject-unlinked items привязаны отдельной path history.',
 'I':'29 decisions: accepted имеют consumers, supersedes targets существуют. Код D12–D17/D19/D20/D25 сопоставлен ниже. Старый review-p6 F1 исправлен: set несуществующей зависимости в scratch → PLAN_INVALID exit 1.',
 'J':'Все упомянутые orch CLI verbs/subverbs --help 0; schema 41 verbs 0, отсутствует supersede в docs (A-6); orch.discovery docs stale (A-5).',
 'K':'diff --check exit 2: EOF blank test_delivery.py и пробелы в старых raw review artifacts. Bare scan exit 1 означает отсутствие флага. Secret literal scan — 0 совпадений. Public-hygiene HEAD 1, indexed base 1, 44 delta rows; A-7 для реальных docs, synthetic samples отдельно.',
}
method=['Один read-only проход, без субагентов, сети, моделей, CAO и tmux. Все изменения-пробы — в scratch. Наблюдаемый route codex/gpt-6.1-sol/xhigh (выше требуемого high), session 01a11749-1a0a-72f1-9737-6b8aee330f2c, approval never, sandbox danger-full-access; кандидат из state.txt. Полный context pack прочитан без изменения. Разрешённые методикой дорогие проверки шли в фоне; широкие suites не повторялись.','',
        '| Блок | Команды, exit и итог |','| --- | --- |']
for block in 'ABCDEFGHIJK':
    entries=[r for r in records if r['block']==block]
    method.append('| '+block+' | '+methods[block]+f' ({len(entries)} записей; точные команды/exit: commands.log, {block}-*.log.) |')
method.extend(['','D12–D17, D19, D20, D25: реализация подтверждена отдельно от прежних notes:',
 '| Decision | Реализация |','| --- | --- |',
 '| D12 | packages/task/skills/plan-protocol/references/review-mode.md:5; E-task-boundary exit 0 |',
 '| D13 | packages/task/tests/test_boundary.py:64; packages/orch/tests/test_boundaries.py:30; E scan AST без foreign imports |',
 '| D14 | packages/task/lib/task/plan/bridges.py:31; packages/task/bridges/orch/bridge.json:1 |',
 '| D15 | packages/task/bridges/orch/brief.py:218; ядро без verb brief, test_brief.py:506 |',
 '| D16 | packages/skiller/lib/skiller/host.py:1; configs/skiller-host.json:1; standalone exit 0 |',
 '| D17 | packages/task/lib/task/plan/gitops.py:175; parallel.py:25; packages/orch/lib/orch/launch.py:56; configs/config-inventory.json:1 (A-1) |',
 '| D19 | packages/task/lib/task/plan/lifecycle.py:684; packages/task/schemas/plan/v1/check-evidence.schema.json:1; evidence tests входят в Task validate exit 0 |',
 '| D20 | scripts/skiller-standalone-check.sh:35; shared core copied, no sibling packages, 803 tests exit 0 |',
 '| D25 | packages/orch/configs/launch-catalog.json:1; packages/task/lib/task/plan/scout.py:70; Task bridge launch.py:48 |',
 '', 'Audit driver/probes сохранены в artifacts/P5.7/p57_*.py; исторические команды с /tmp/p57_* ссылаются на эти сохранённые исходники. Первые инструментальные неудачи (escaping symlinks в scratch, парсинг Unicode git output и archive без Git index) сохранены в логах; последующие адресные пробы используют tracked копию git ls-files -z и изолированный индекс базы.'])
finding_text=[]
for f in findings:
    finding_text.extend([f"### {f['id']} — {f['severity']}, confidence {f['confidence']}: {f['title']}",
       'Место: '+f['where']+'.','Воспроизведение: '+f['repro'],'Ожидание: '+f['expect'],
       'Owning item: '+f['owner']+'.','Рекомендация: '+f['recommendation'],''])
finding_text.extend([
 '### Находки исходного conclusion: самостоятельное подтверждение',
 'F-C1 — **confirmed**, Major, owning P12.1 (carrier P7.2). C-fc1-brief exit 0, C-fc1-validate exit 1, /reads/N/included; D: 40 execution-input failures на том же поле. Не новая находка.',
 'F-C2 — **confirmed**, Major, owning P2.1 (regression P2.2; carrier P7.2). В копии route.settings добавлено через API; C-fc2-brief-with-tracked-reads exit 0, C-fc2-validate-with-tracked-reads exit 1, /route/minimum/settings. Не новая находка.',
 'F-C3 — **refuted на текущем кандидате / historically confirmed**. c51e9197 содержит все 15 недостающих D26–D29/knowledge/research carriers; H повторно проверил реальные refs. Пункт P5.6 правильно фиксировал прошлый HEAD, но его оговорка устарела.',
 '',
 '### Негейтящие наблюдения и вопросы',
 'Info: raw F-orch-validate exit 1 связан с PATH /home/vostrikov/.local/share/swissknifeman/releases/v0.28.6/packages/skiller/bin/skiller, который не имеет resolve; текущий checkout bridge проходит 11/11. F-docs-sync exit 1 связан с ignored docs/skiller; archived HEAD check exit 0. Это ограничения среды, не скрытые GREEN и не утверждение о дефекте кандидата.',
 'Info: K-diff-check exit 2 включает raw артефакты P7.5/P9.1, чьи пробелы являются частью сохранённого diff/transcript; отдельный product scan нашёл только packages/skiller/tests/test_delivery.py:375 (новый пустой EOF). Низкий приоритет, изменение истории артефактов не предлагается.',
 'Question (R21/D26): исторический root-only layout для shared_config_path(profile-catalog) работает в v0.28.6 и перестаёт работать сейчас. D26 прямо принимает owner-only resolver; достаточно ли записи Changed для существующих пользовательских root overrides? Этот аудит не отменяет принятого решения.',
 'Known recording debt: неизвестные aliases оставляют model class unchecked (lifecycle.py:270), хотя effort всё ещё проверяется; refine заключения: неизвестный class не равен отключению всех route checks. 10 items без subject/trailer link уже подпадают под описанную conclusion проблему, отдельные commits подтверждены path history.'])

recording=[
 'H-records-complete exit 0: 70 выполненных items, notes/acceptance IDs полны; ни одного done_with_deviations без deviations, skipped без причины или item без start/finish. Review-p1/review-p2/review-p6/conclusion имеют note events (6/2/3/3 соответственно; часть mentions — в notes других items). W1–W12 — test_record_parity, 6 tests внутри Task bridge suite 97 tests, exit 0.',
 '', '| Item | Красный check | Статус и точное объяснение |','| --- | --- | --- |',
 '| P2.4 | V5=1 | done_with_deviations: новые human_view rules обнаруживали 24 старых refs в архивном плане; baseline тоже RED, deviation сохранён |',
 '| P11.1 | V3=1 | done_with_deviations: отсутствующий старый путь maind-overview, baseline тоже RED; последующий перенос/документы P11.5 учтены |',
 '', 'Git completeness: 212 tracked JSON carriers просканированы (`git ls-files -z`); 15 F-C3 carriers подтверждены c51e9197. Все concrete own-plan источники tracked. Regex-кандидаты ниже проверены как шаблоны/описания/scratch evidence и не объявлены отсутствующим состоянием:',
 '| Кандидат | Квалификация |','| --- | --- |',
 '| knowledge/brief, knowledge/decision(s), knowledge/sections, knowledge/artifacts | названия категорий контента в prose, не refs отдельных документов |',
 '| knowledge/audit-plan2-, knowledge/audit-plan2-*.json, knowledge/review-p | будущий deliverable/template или диапазон review-pN; существующие review-p1/2/6 проверены |',
 '| knowledge/brief-, knowledge/x, knowledge/x.json | примеры output/formats в context-scope-p12/read-api, не реальные локальные targets |',
 '| @plan/artifacts/wrong-subject.json, @plan/artifacts/valid.json | команды и output scratch PLAN1 в embedded independent review-p2 evidence; не ссылки на production PLAN2 |',
 '', '212 carriers включают один намеренно пустой stdout failed reviewer: artifacts/P8.6/review-sandbox-failed-review-native.json (0 bytes). Это не plan/v1 документ; scanner проверил raw text, parse не выдавался за успешный.',
 '', '39 trailer commits для 34 distinct item refs (H-commits exit 0); остальных ищем только в base..candidate, чтобы не подменить PLAN2 commit одноимённым Pn.m старого плана. Из 70 items 10 без item ID в subject/trailer, но каждый имеет commit продукта/своего item JSON:',
 '| Item | Подтверждённый commit по истории пути |','| --- | --- |']
for r in commits['unlinked']:
    line=r['path_history'].splitlines()[0];sha,subject=line.split('\t',1)
    if r['item']=='P2.1':sha='38b6b18d02c1966c27c7e9d6cdb15971e9b73e81';subject='feat(task): добавить plan.py brief'
    recording.append('| '+r['item']+' | '+sha[:12]+' '+subject+' |')
recording.extend(['', 'Actor identities (H-results.json): 19 codex/gpt-6.1-sol; Sonnet 38 под provider anthropic/claude и model aliases; Opus 13. Сессия этого аудита фиксируется отдельно при finish, без присвоения старых identities.',
 'Запись объёма выводов не уменьшена; raw evidence и все exits текущего аудита сохранены.'])

compat=[
 'База: '+Path(SCRATCH,'base-sha').read_text()+' (58025e3a4^); кандидат '+candidate+'; tag v0.28.6 — первый в git tag --sort=-creatordate (G-tags exit 0). git merge-base --is-ancestor 58025e3a4 v0.28.6 exit 1: Plan №2 не входил в release.',
 'G-results.json: 24 DR paths, 18 существуют в v0.28.6. 14 root-bootstrap canonical skills переехали к владельцам с сохранением identities/projections (Unreleased Repository bootstrap); их бывшие lock/config carriers внутренние. test_task_plugin_cache_revision.py перенесён к host, это тест, не CLI. Остальные удаления migration/README/helpers и промежуточные Task surfaces отсутствовали в tag.',
 'configs/profile-catalog.json реально был выпущен (git cat-file exit 0). Удаление отражено в Removed и новый resolver в Changed, но never released неверно (A-4); влияние на root-only overrides — отдельный вопрос по принятому D26.',
 'v0.28.6 не содержит ни packages/task/scripts/plan.py, ни packages/task/lib/task/plan/cli.py (git show exit 128); поэтому извлекать старые plan.py verbs из указанного методикой файла нельзя. Это проверенная неприменимость, а не 0 успешно протестированных release verbs. Все 41 текущие verbs --help exit 0; новые глаголы не выданы за старые.',
 'skiller --help и connect/vendor/sync --help exit 0, standalone 803 tests. Поведение live установки/доставки и внешних consumers не проверялось. Harness monorepo fallback остаётся последним обычным шагом в task_paths.py:37; caller-supplied monorepo_root продолжает выигрывать (строка 29).',
 'Public method/CLI/schema corrections F-C1/F-C2 и A-2 требуют affected conformance checks и task:review после owning correction; текущий аудит не меняет публичные контракты.']

not_checked=[
 'Live модели/CAO/tmux/сеть и действия publishing: не входят в scope, ни разу не запускались.',
 'Исходный широкий orch validate не подтверждён GREEN в установленной среде: exit 1, PATH разрешает Skiller v0.28.6 без resolve. 164 core tests, прочие bridge tests и адресные 11 local Skiller bridge tests подтверждены; второй широкий запуск запрещён методикой и не делался.',
 'Исходный docs-sync --check не подтверждён GREEN для ignored materialized docs/skiller: exit 1. HEAD archive check exit 0 доказывает tracked candidate, ignored owner mirror не менялся.',
 'Историческая runtime identity design-сессии R26: требование/решение есть, независимой telemetry этой сессии нет.',
 'Глаголы plan.py release v0.28.6: исходный файл отсутствует (G-released-cli exit 128); нынешние 41 --help проверены отдельно.',
 'Четыре исторических item brief прекращаются READ_MISSING на перенесённых required source paths: P2.2, P7.2, P7.3, P8.6 (D-brief-*.log). Их прежние acceptance не переписывались, полный 70-item conformance не объявлен успешным.',
 'Начальные ошибки audit tooling (symlinks escaping scratch root, mapping envelope ref/id, JSON quoted git paths) не являются продуктовым findings; корректированные узкие проверки сохранены вместе с первыми exits.']
recommendations=[
 '1. Owning correction P11.3 для A-1; учесть, что новый manifest пришёл из P5.1. Root inventory hygiene gate должен быть GREEN перед передачей двигателю.',
 '2. Owning corrections P12.1/P2.1–P2.2 для F-C1/F-C2/A-2, текущий carrier P7.2: добавить scoped reads/route.settings/role-manifest live contract cases, сохранить запрет исполняемого lifecycle, затем task:review изменённого exec/v1 seam.',
 '3. P5.5 исправляет устаревшие CHANGELOG/architecture docs и concrete plan citations (A-3/A-5/A-7); P11.4 — release provenance каталога (A-4); P6.6 — docs supersede (A-6).',
 '4. Подтвердить совместимость принятых D26 изменений с поддерживаемыми consumer layouts; при необходимости владелец выбирает migration notice, без самовольной отмены решения аудитором.',
 '5. До следующего обычного broad validation явно выбрать checkout Skiller либо обновить установку, а ignored docs mirrors освежить штатным docs-sync вне read-only аудита. Это ограничение проверки среды, не повторный audit.',
 'Reopen и реализация принадлежат владельцу; этот item фиксирует read-only результат, не выполняет исправления. Никаких дополнительных фаз или новых обязательных review циклов не создано.',
 'Docs maintenance: docs not needed для самого аудита — процессы, возможности и схемы не изменены; найденные docs-проблемы записаны на owning items. CHANGELOG/registry/package version не изменяются в read-only scope.']
verdict='ATTENTION. Кандидат '+candidate+'. Новые находки: 0 Blocker, 2 Major, 5 Minor; дополнительно самостоятельно подтверждены известные F-C1/F-C2 (2 Major), F-C3 закрыт.\n'
verdict+='Config inventory gate реально RED; живой Task → exec/v1 по всем завершённым items не GREEN (8/70 pass), demo проходит 4/4 и все 3 bindings.\n'
verdict+='Широкие Task/Skiller/Harness/standalone checks GREEN; исходные orch/docs-sync checks RED из-за локальной среды, ограничение явно записано и квалифицировано адресными checks.\n'
verdict+='Coverage recheck: '+', '.join(k+'='+str(v) for k,v in sorted(cov_counts.items()))+'. Plan notes/checks/ссылки в git сохранены; 10 legacy commits требуют ручной path-history attribution. Продукт и принятые D1–D29 не менялись.'
doc={'$schema':'urn:swissknifeman:task:plan:document:v1','id':'audit-plan2-2026-10-07',
 'title':'Независимый общий аудит Plan №2 (P5.7): ATTENTION, кандидат '+candidate[:12],
 'sections':[{'id':i,'title':t,'text':'\n'.join(value) if isinstance(value,list) else value} for i,t,value in [
 ('verdict','Вердикт',verdict),('method','Методика и блоки A–K',method),('findings','Находки, известные дефекты и вопросы',finding_text),
 ('coverage-recheck','Перепроверка 52 строк R/I/B',coverage),('recording-recheck','Запись, ссылки и коммиты',recording),
 ('compat','Совместимость с v0.28.6',compat),('not-checked','Непроверенное и ограничения',not_checked),
 ('recommendations','Рекомендации по owning items',recommendations)]],'applies_to':['P5.7']}
Path(SCRATCH,'audit.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
print(verdict)
print('report',str(Path(SCRATCH,'audit.json')),'bytes',len(json.dumps(doc,ensure_ascii=False).encode()))
