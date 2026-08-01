# HANDOFF — 2026-08-01 — after P5.6

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model | implementation |
| Thinking | high — гейт очерёдности P2.1 + измерение живой Codex-сессией, effort high+ по §9 (Routing P5.4) |
| Context | continue (/clear) — ручной item |
| Суть | P5.4: обязательство провенанса модели в каноне (3 носителя) + измерение видимости служебных каталогов плана живой Codex-сессией; P2.1 терминальна (🟢) — гейт очерёдности снят |

```
Item P5.4 — Провенанс модели в каноне + видимость служебных каталогов (2026.07.31-SKM-LEAN, phases/P5.md)

Cold-start reads (в этом порядке): plans/2026.07.31-SKM-LEAN/plan.md (Context, Execution Rules, §3
Routing, Status Board) → plans/2026.07.31-SKM-LEAN/handoff.md → plans/2026.07.31-SKM-LEAN/phases/P5.md
(Phase Context + P5.4 целиком) → Required Reads P5.4 по порядку.

Status: ⬜ Not started
Intent: Превратить фактически существующий провенанс авторской модели в объявленное обязательство
канона инструкций (сегодня механика есть, требования нет) и измерить живой Codex-сессией,
действительно ли служебные каталоги плана (plans/<ID>/{root,brief,findings,research}) и корневые
dot-каталоги видимы стороннему провайдеру — закрыв п. 5 audits/skm.md фактом, а не предположением.
Why: Половина (а) уже почти выполнена механикой: провенанс несут ## 0. Meta → Authoring Model,
литерал-колонка Дата | Кто (role/model) | Что в ## 6. Update Log и обязательное поле actor журнала
на каждое исполнение item'а (RAG:— (repo-grounded: findings/P5-hygiene-surfaces-2026-07-31.md §5;
packages/task/lib/task/journal.py:47–50; SKILL.ru.md:1400 i18n-keep)). Чего нет — правила:
root.plan-lifecycle (root/common.md:22–23) о провенансе модели молчит, поэтому обязательство держится
дисциплиной, а не каноном. Половина (б) — разрыв реальный и уже измеренный на практике: в прошлом
переключении на Codex 2 из 4 препятствий сняла починка корневого AGENTS.md, 2 остались известным
риском канона (RAG:— (repo-grounded: audits/skm.md §5)); канон описывает .agents/skills/* как
генерируемые проекции (root/codex.md:1–3) и ограничивает чтение доков «root→cwd, never past the
repository root» (root/codex.md:10–11), но служебные каталоги ПЛАНА не называет ни разу. Проверить
это можно фактом, а не рассуждением: живой codex-cli 0.146.0 установлен (RAG:— (repo-grounded:
findings/P5-hygiene-surfaces-2026-07-31.md §6)).
Scope Included: (а) новая/расширенная секция канона инструкций, объявляющая обязательство
провенанса авторской модели плана (какие три носителя, что каждый означает, что отсутствие —
дефект) + регенерация артефактов штатной операцией + ревизия записи в catalog.json (intent,
obligations, sources[].sha256); (б) измерение холодной Codex-сессией: видит ли codex содержимое
plans/<ID>/brief|findings|research|root, .claude/, .codex/, .agents/ при работе над item'ом плана —
протокол прогона, вывод, поимённый список того, что НЕ видно; (в) если разрыв подтвердится —
минимальная правка канона Codex-ветки, называющая служебные каталоги плана как обязательные к
чтению, + регенерация; (г) отчёт-артефакт findings/P5-codex-visibility.md с командой прогона и
выводом.
Scope Excluded: любой машинный гейт в plan_lint.py (файл правят P5.8 и P5.9 — D58(а), порядок между
ними пинован D43; провенанс-гейт на 26+ живых планах флота — отдельная работа со своим решением);
правка схемы item'а и 16 полей; правка journal.py и его обязательных полей; ретро-заполнение
провенанса в существующих планах; расширение .agents/skills/** (генерируемые проекции —
root.codex.bootstrap); правка секций канона, относящихся к диете P2 (item дописывает, не переписывает
— D10).
Inputs: findings/P5-hygiene-surfaces-2026-07-31.md §5 и §6 · research/05-p5-hygiene-model.md §1 и §6
(риск 4) · audits/skm.md §5 · phases/P2.md §P2.1 Deliverables (что уже сделано с каноном — item
дописывает поверх) · plan.md §5 D10 · гейт: plan.md §4 Status Board — строка P2 (см. Implementation
Rules п. 1)
Files: packages/harness/configs/common/instructions/root/common.md (секция про провенанс плана —
дописывается) · packages/harness/configs/common/instructions/root/codex.md (только при подтверждённом
разрыве видимости) · packages/harness/configs/common/instructions/catalog.json (записи секций +
sources[].sha256) · CLAUDE.md / AGENTS.md + пер-пакетные (перегенерируются, не правятся) ·
.swissknifeman/provider-artifacts.lock.json (перегенерируется той же harness instructions apply —
детерминированный производный артефакт, plan-protocol §6 carve-out (b); назван явно, чтобы дифф не
читался как посторонний — D82) · plans/2026.07.31-SKM-LEAN/findings/P5-codex-visibility.md (новый) ·
packages/harness/docs/reference/instruction-canon.md
Required Reads: 1) plans/2026.07.31-SKM-LEAN/findings/P5-hygiene-surfaces-2026-07-31.md §5, §6;
2) packages/harness/configs/common/instructions/root/common.md целиком (18 секций — куда встаёт новая
и что уже сказано root.plan-lifecycle); 3) packages/harness/configs/common/instructions/root/codex.md
целиком (4 секции); 4) packages/harness/docs/reference/instruction-canon.md целиком (контракт
проекции — расширяется, не обходится); 5) packages/harness/lib/harness/instructions.py:372–470
(операции plan/check/apply) — как делается регенерация; 6)
packages/harness/configs/common/instructions/catalog.json — форма записи секции на примере
root.generated-artifacts (:480–500); 7) plans/2026.07.31-SKM-LEAN/phases/P2.md §P2.1 (что P2 уже
сделала с этим же SSOT).
Implementation Rules: (1) Гейт очерёдности (D10): item выполняется ТОЛЬКО когда P2.1 терминальна
(🟢/🟠 в phases/P2.md §Phase Status) — терминальна (🟢 Done, проверено этим handoff'ом). (2) Секция
ДОПИСЫВАЕТСЯ: ни одна секция, оставленная или сжатая P2.1, не переформулируется — расхождение с её
вердиктом = scope drift. (3) Формулировка обязательства называет ТРИ существующих носителя поимённо
и явно говорит, что механика уже есть, а объявляется правило; изобретать четвёртый носитель запрещено.
(4) Обязательство пишется в терминах catalog.json (modality/subject/action/object/boundary), как
остальные, — свободной прозой мимо схемы каталога нельзя. (5) Артефакты перегенерируются (harness
instructions apply), затем check обязан быть зелёным; ручная правка CLAUDE.md/AGENTS.md = нарушение
root.generated-artifacts. Порядок целей --authorize — алфавитный по target_path (авторитетная
формулировка — D84 плана 2026.07.29-HARNESS-AGNOSTIC; если P5.7 к этому моменту закрыт, ожидаемый
порядок печатает сама диагностика). (6) Измерение (б) — прогон, а не рассуждение: холодная
codex-сессия в этом репозитории получает задание прочитать конкретные файлы плана и назвать их
содержимое; вывод и точный argv идут в findings/P5-codex-visibility.md. Утверждение «видно/не видно»
без вывода прогона — то же, что предпосылка аудита. (7) Правка Codex-ветки канона делается ТОЛЬКО при
подтверждённом разрыве; разрыва нет → это фиксируется как честный отрицательный результат, и (в) не
выполняется.
Code Guidance: Анти-самообман (паттерн 2): «канон дополнен» — половина работы; вторая половина
обязана предъявить вывод живого Codex-прогона. Если прогон не удалось выполнить (бинарь недоступен,
сессия падает) — это НЕ повод написать «видимость обеспечена»: item закрывается 🟠 с точной Pending
Work, а не 🟢 с догадкой. Честность отрицательного результата: «разрыв не подтвердился, правка
Codex-канона не нужна» — полноценный и желательный исход; выдумывать правку, чтобы item выглядел
содержательным, запрещено. Анти-подгонка (паттерн 1): обязательство не формулируется так, чтобы «этот
план и так ему соответствует» — критерий пишется от смысла (можно ли из файлов плана без чата
восстановить, какая модель что спроектировала), и если действующий план ему не полностью
соответствует, это называется в отчёте. Границы чужой фазы: секции, которыми владеет P2.1, не
переформулируются; plan_lint.py не трогается вовсе (его правят P5.8 и P5.9 — D58(а), порядок D43);
git add -A запрещён. If-then эскалация (паттерн 3): если контракт проекции не допускает секции такого
класса (правило о ПЛАНАХ, а не о репозитории) — остановиться: > 🔴 ESCALATION P5.4: обязательство
провенанса не вписывается в контракт instruction-projection | trigger: unclear architecture | нужен:
plan-design, Escalation Needed: yes.
Validation: 1) PYTHONPATH=packages/harness/lib python3 -m harness.instructions --check — зелёный
после регенерации; 2) bash packages/harness/scripts/validate.sh и bash packages/harness/scripts/test.sh
— зелёные; 3) grep -n "Authoring Model\|role/model\|actor" CLAUDE.md AGENTS.md — обязательство
присутствует в обоих провайдерных артефактах (паритет — root.provider-parity); 4) git diff --stat
CLAUDE.md AGENTS.md — изменения ТОЛЬКО как результат регенерации; 5) живой прогон видимости: команда
вида codex exec -C "$PWD" '<задание прочитать plans/2026.07.31-SKM-LEAN/{brief/00-brief.md,findings/,
research/} и .claude/, .codex/, .agents/ и перечислить, что прочитано>' (точный argv фиксируется в
отчёте) — stdout приложен к findings/P5-codex-visibility.md, вместе с codex --version; 6) python3 -c
"import json;d=json.load(open('packages/harness/configs/common/instructions/catalog.json'));
print(sum(1 for s in d['scopes'] for k in s.get('sections',[])))" — счёт секций до/после (число с
якорем; ключи структуры уточнить по факту); 7) python3 packages/task/scripts/plan-lint.py
plans/2026.07.31-SKM-LEAN — счёт с атрибуцией.
Deliverables: секция канона инструкций с объявленным обязательством провенанса авторской модели (три
носителя поимённо) + запись в catalog.json с обязательствами и sha256 источников + перегенерированные
CLAUDE.md/AGENTS.md · findings/P5-codex-visibility.md: точный argv, codex --version, вывод прогона,
поимённый список невидимого (или явная строка «разрыв не подтверждён») · при подтверждённом разрыве —
минимальная правка Codex-ветки канона · обновлённый packages/harness/docs/reference/instruction-canon.md
· два коммита по канону §2 плана.
```

**Done:** **P5.2, P5.3, P5.6 закрыты этим заходом** — весь батч **B2** (`exec-items: task:plan-exec
2026.07.31-SKM-LEAN P5.2 P5.3 P5.6`) отработан последовательно, полный цикл 1–8 на каждый item.

- **P5.2 🟢 Done** — провенанс `configs/provider-capabilities.json` вне файла (генерируемые носители,
  структурный тест). Item-коммит `b09bab62`.
- **P5.3 🟢 Done** — вердикт-правило трекинга `*.env.ini` по классу; 2 файла untracked вопреки классу
  (`.claude/run-report.env.ini`, `packages/skiller/.claude/auto-approve.env.ini`); новая док-страница
  `hook-intent-files.md` в обеих сборках; тесты лестницы приоритета через реальный `common.sh`. Item-коммит
  `2e53afd9`.
- **P5.6 🟠 Done with deviations** — `--output-dir .playwright-mcp` + пиновка `@playwright/mcp@0.0.78`
  (проверено `npm view`+`--help` на живой версии) на всех трёх носителях обоих провайдеров; тест
  согласованности носителей. Known Deviations: item-коммит задел `packages/harness/docs/reference/
  provider-harness.md` и `plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md`
  вне номинального `Files` — необходимый детерминированный regen (иначе `test_generated_docs_and_p5_
  artifact_are_the_validated_report_consumers` краснеет), не самостоятельное решение. Item-коммит
  `1ba21c39`.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
**P5 2/11 (🟡 In progress)** · P6 0/3 (⬜) · P7 0/4 (⬜). Открыты P5.4/P5.5/P5.7–P5.11. Следующий по
порядку — **P5.4** (`solo`, `manual`, implementation/high, гейт очерёдности D10 снят — P2.1 🟢).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P5.md` (ТЗ P5.4 и далее) · `plan.md` §3
Routing · `roadmap.md` (карта батчей — B2 закрыт).

**Open risks:**

- Прежние (не изменились этим заходом): supply-chain находка §3.1 живая до закрытия P5.10 · гейт
  триажа красен по конструкции (D109) · пинованный внешний источник может исчезнуть · ветка (C) OQ-6 не
  проверена данными · преэкзистентный HTTP 404 `oss-dev/to-issues` · U1/U2 `[UNVERIFIED]`, остаток риска
  D106, контракт P4.1 пинован на `06fefc87`.
- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый `RESEARCH/AUDIT-loqum-findings.md`;
  untracked `.swissknife/` и `audits/`.
- `scripts/test-provider-docs.py` несёт 2 известных FAIL (устаревшие утверждённые хеши манифеста) —
  адрес P6.3, не трогать здесь.
- P5.3 Pending Work: унификация четырёх самописных парсеров `*.env.ini` — вне Scope, уходит в
  `roadmap/` при подтверждении владельцем.
- P5.4 (следующий item): гейт разрыва Codex-видимости — если прогон не подтвердит разрыв, это честный
  отрицательный результат (см. Code Guidance item'а выше), не повод изобретать правку.

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений (см. предыдущий handoff); + унификация парсеров `*.env.ini` (P5.3
  Pending Work) — потенциальная новая запись `roadmap/`, решение за владельцем.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец протокола).
