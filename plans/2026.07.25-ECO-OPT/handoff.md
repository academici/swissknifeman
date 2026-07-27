# HANDOFF — 2026-07-27 — after P8

**Фаза P8 закрыта 🟠 Done with deviations** — все 10 items терминальны (7🟢 + 3🟠: P8.1/P8.3/
P8.10). Status Board `P8 | 7/10 | 🟠 Done with deviations`. `## Phase Handoff` в `phases/P8.md`
заполнен (10 items сдачи + агрегат Known Deviations трёх items + вердикт docs-sync). Отчёт
закрытия `closure/P8.json` (Closure Protocol v1) собран механически из полей items: 10
`items[]`, 5 `gates[]` (task/skiller/harness PASS, maind FAIL — оба провала пред-существующие,
core.tests PASS), `metrics[]`, честные `limitations[]` (P8.4/P8.6 Pending Work, охват evidence).
Три поверхности фазы: честность закрытия plan-протокола (P8.1–P8.3), гейты дерева и CI
(P8.4–P8.7), гейты инструкционного слоя (P8.8–P8.9); собственная оснастка протокола — P8.10
(D125). `bash packages/task/scripts/validate.sh` — `validate: OK`, `plan-lint: OK (14
план(ов), 0 ошибок, 219 предупреждений)`. `python3 packages/task/scripts/plan-lint.py
plans/2026.07.25-ECO-OPT --baseline HEAD` — `0 ошибок` (25 предупреждений, 0 новых от рабочего
дерева).

**Next:** фаза 🟠 (Known Deviations есть, эскалаций нет) ⇒ по правилу «была 🟠 → сперва аудит»
следующий шаг — adversarial-аудит закрытой фазы P8, НЕ `plan-exec`.

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Adversarial-аудит закрытой фазы P8: сверка 🟢/🟠 с git-фактами, no-op, scope drift, closure/P8.json vs Completion Notes |

```
/task:plan-audit 2026.07.25-ECO-OPT P8
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · фаза P10
закрыта (P10.1🟢 `0b33116c`+`243254aa` · P10.2🟠 `47d6972d` · P10.3🟠 `ae54d790` · P10.4🟠
`77bf9d8c`) · фаза P5 закрыта (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` ·
P5.4🟢 `253ae4a6` · P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) · **фаза P8 закрыта** (P8.1🟠
`5f5dfa73` · P8.2🟢 `2a6cbb3d`/`9950eaa0` · P8.3🟠 `c36bbee5` · P8.4🟢 `5b7cc15e` · P8.5🟢
`d12ccaf7` · P8.6🟢 `12ff61e1` · P8.7🟢 `fa1ee8bf` · P8.8🟢 `4ee3ba6d` · P8.9🟢 `980ce398` ·
P8.10🟠 `a020f434`) · **P9.1** · **P2.1** · **P3.2** · **P1.2** — **30/44 items закрыто**, 3
фазы терминальны (P5, P8, P10), 4 фазы в работе (P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2), 2
фазы не начаты (P4, P6, P7 — три не начаты).

**Remaining:** 14/44 items. Свободные к запуску (без порядковых условий друг относительно
друга, помимо аудита P8 выше): **P9.3** (frontier/high, manual) · **P1.1** (frontier/high,
manual) · **P3.1** (implementation/medium, manual — нужен оператор для `/doctor`/`/context`) ·
**P2.3** (frontier/high, manual — её гейт «после P8.1/P8.2/P8.3 и P6.3» частично снят: P8 вся
терминальна, но P6.3 ещё не исполнена). Порядковые условия: P2.3 — ПОСЛЕ P8 (выполнено) и P6.3
(D93, не выполнено); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2 (условие снято).
P8.10 предшественником других items не является.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing; §4 Phase Index — P8 `7/10 🟠
Done with deviations`; §5 D124/D125; §6 Update Log — строка закрытия фазы P8) · `phases/P8.md`
(`## Phase Status` — все 10 items терминальны; `## Phase Handoff` — заполнен) ·
`closure/P8.json` (Closure Protocol v1, схема v1) · `research/25-P8.5-routing-cell-form-
2026-07-27.md` (диагноз §3 Routing, целевой дизайн P8.10) · `packages/skiller/skills/general/
plan-protocol/SKILL.ru.md` §8/§9 (канон отчёта закрытия и формы ячейки — SSOT) · машинные
гейты `plans/cross-plan-files.py`, `plans/verify-citations.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а, назван в `closure/P8.json` `gates[]`; (2) дельта
Serena `v1.6.1` → `1.6.2.dev0` не вычитана (`[UNVERIFIED]`, D110); (3) P10.4 Pending Work —
рендерер `.mcp.json` (D106); (4) P10.3 Pending Work — `README.md:122` битая ссылка (кандидат
`/task:fix`); (5) F13/F14 аудита P5 (заход 2) — за владельцем P5/`maind`; (6) P10.2 Pending
Work (b) — `verify-citations-known-exceptions.json` не решён владельцем; (7) carve-out (б)
канона `plan-protocol` не переписан (D118); (8) P8.4 job `hygiene` не подтверждён реальным
CI-run'ом (Pending Work, назван в `closure/P8.json` `limitations[]`); (9) `plans/2026.07.18-
FOREMAN` несёт нелегальную форму ячейки §3 (`P4.1–P4.2, P4.4`, строка 87) — 3 его items не
строят Task Contract; правит FOREMAN, не этот план (И4–И6); отказ прямо называет ячейку, строку
и обе легальные формы (P8.10); (10) матрица `docs/status.md` не сверена с живыми контрактами
(D2, отложено); (11) `public-hygiene` CI-гейт (P8.6) красный на текущем дереве — `install.log`
в `artifacts/p5-pilot/stage0/` (P8.6 Pending Work, owner, назван в `closure/P8.json`
`limitations[]`); (12) три CORE-скилла без активационной секции — унаследованный долг в
`skill-sections-burndown.txt` (P8.8, правка тел вне scope); (13) пред-существующая ruff-находка
`B904` в `packages/skiller/lib/skiller/publication.py:1037` — вне `Files` P8.9, не регрессия
(кандидат `/task:fix`); (14) формулировка Validation 1 в ТЗ P8.10 невыполнима как записана
(тест-модуль импортирует соседний `fixtures` ⇒ каталог тестов обязан быть на `PYTHONPATH`);
(15) **посторонние untracked каталоги в рабочем дереве** — `.swissknife/` и
`packages/task/lib/.claude/` — не относятся к items фазы P8, git status грязный этими двумя
путями на момент закрытия; кандидат для владельца — решить, оставлять/чистить (не блокирует
закрытие фазы).

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py` (Scope Excluded
P8.10 — кандидат `roadmap.md`, если форма всплывёт снова); сверка полноты матрицы
`docs/status.md` (D2); удаление/gitignore `install.log` (P8.6 Pending Work, owner); перевод
`maind/provider_deploy.py` на `assert_safe_replace_target` (P8.7, roadmap-кандидат); заполнение
`triggers[]` у четырёх скиллов с `evals/` (P8.8, WARNING); включение `Closure Protocol | v1` на
`2026.07.18-FOREMAN`/`2026.07.24-AGENT-RELIABILITY` (P8.1 Pending Work, owner). Долг
«перепиннуться на тег Serena» держит `roadmap.md` § «Отложенное» (D110).
