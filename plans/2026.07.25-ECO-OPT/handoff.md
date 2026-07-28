# HANDOFF — 2026-07-28 — after P1.1

**P1.1 закрыт `⛔ Skipped by decision` — ветка A (рычаг moot).** GATED-вердикт снят НАПРЯМУЮ по
first-party доке (`code.claude.com/docs/en/mcp` §§ «Scale with MCP tool search» / «Configure tool
search» / «Exempt a server from deferral» + `/en/env-vars`, WebFetch 2026-07-28): tool search
включён ПО УМОЛЧАНИЮ, MCP-схемы отложены («Only tool names and server instructions load at session
start»), `ENABLE_TOOL_SEARCH` существует чтобы ФОРСИРОВАТЬ за не-first-party хостом или ВЫКЛЮЧИТЬ.
Ни одно из четырёх условий выключения на флоте не выполняется (21 `.mcp.json` — 0 `alwaysLoad`;
0 настроек с `ANTHROPIC_BASE_URL`/`*_DISABLE_EXPERIMENTAL_BETAS`/`*_USE_BEDROCK`/`*_USE_VERTEX`/
`ENABLE_TOOL_SEARCH`; CLI 2.1.220; модели новее Opus 4.5). Продукт — одна D-запись **D136**
(item-коммит `d68d1d49`); harness и `mcp-advisor` НЕ тронуты (обоснование — в D136).

**Фаза P1 полностью терминальна** (P1.2 🟢, P1.1 ⛔), но статус фазы на доске §4 остаётся
`🟡 In progress`, счётчик — `P1 1/2` (⛔ в числитель 🟢 не входит): закрытие фазы и `closure/P1.json`
— работа `/task:plan-close`, не исполнителя item'а.

**Next:** `/task:plan-close 2026.07.25-ECO-OPT P1` — закрыть терминальную фазу P1.

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — бухгалтерия закрытия фазы, решений нет |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P1 (оба items терминальны): доска §4, `## Phase Handoff`, `closure/P1.json` |

```
/task:plan-close 2026.07.25-ECO-OPT P1
```

Свободные items вне очереди после P1: **P3.1** (implementation/medium, manual — нужен оператор для
`/doctor`/`/context`) · **P2.3** (frontier/high, manual — ждёт P6.3). Непогашенный adversarial-аудит
фазы **P8** по-прежнему открыт (Open risks (17)).

**Done:** **36/52 items терминальны** (24 🟢 · 11 🟠 · 1 ⛔ — счёт на bookkeeping-коммите этого
захода, `python3` по таблицам `## Phase Status` всех `phases/P*.md`). Терминальны фазы **P5** (5/6),
**P8** (7/10), **P9** (3/4), **P10** (1/4), **P11** (6/8); **P1 1/2** — оба items терминальны,
ждёт `plan-close`. Плюс P2.1 · P3.2 вне терминальных фаз.

**Remaining:** 16 items, все `⬜ Not started`: P2.2–P2.3 · P3.1, P3.3–P3.6 · P4 (3) · P6 (3) ·
P7 (3). Порядковые условия: P2.3 — ПОСЛЕ P6.3 (D93); P6.1 — ПОСЛЕ P9.1 (снято); P4.2 — ПОСЛЕ
P3.2 (снято).

**Sources of truth:** `plan.md` (§4 Phase Index — `P1 1/2`; §5 **D136** — литеральный вердикт с
дословными цитатами доки; §6 Update Log — запись закрытия P1.1) · `phases/P1.md` (P1.1 Completion
Notes — команды проверки флота и их числа; Pending Work — дельта для тела `mcp-advisor`) ·
`plans/archive/2026.07.15-TOKEN-ECON-P6/findings/P6-tool-search-precheck.md` (дизайн-RAG 2026-07-15,
чей вывод подтверждён дословно) · `plans/2026.07.25-ECO-OPT/findings/P5-codegraph-vs-serena-facts.md`
§6 (тот же first-party раздел, снятый P5) · `packages/skiller/skills/general/mcp-advisor/SKILL.ru.md`
§ «Прополка резидентного MCP» п. 3 (действующий caveat про default-on) · машинные гейты
`plans/verify-citations.py`, `plans/cross-plan-files.py`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (0) заход кода не менял — дифф только плановые файлы плюс унаследованная грязь.
(1) измеренный регресс воспроизводимости ревью `ΔR=-0.12` между P9.3 и P9.4 — решение о судьбе
реестра P9.2 за владельцем. (2) из четырёх находок аудита P9, названных брифом как dogfood-корпус,
машинно ловится **только F8**; F1/F2/F9 — человеческая правка (закрыто P11.8) — D130.
(3a) факт остаточного корпуса гейта на P11.4 разошёлся с design-симуляцией (628/52 против
предсказанных 587/48) — разбор в P11.5. (4) второй красный тест `packages/maind/scripts/test.sh` —
пред-существующий долг. (5) дельта Serena `v1.6.1` → `1.6.2.dev0` не вычитана (`[UNVERIFIED]`,
D110). (6) P10.4 Pending Work — рендерер `.mcp.json` (D106). (8) F13/F14 аудита P5 (заход 2) — за
владельцем P5/`maind`. (9) P10.3 Pending Work — `README.md:122` битая ссылка. (10) carve-out (б)
канона `plan-protocol` не переписан (D118). (11) P8.4 job `hygiene` не подтверждён реальным
CI-run'ом. (12) `plans/2026.07.18-FOREMAN` несёт нелегальную форму ячейки §3 (строка 87) — правит
FOREMAN. (13) матрица `docs/status.md` не сверена с живыми контрактами (D2). (14) `public-hygiene`
CI-гейт красный на текущем дереве (`install.log`, owner). (15) три CORE-скилла без активационной
секции (P8.8). (16) ruff-находка `B904` `packages/skiller/lib/skiller/publication.py:1037` —
кандидат `/task:fix`. (17) фаза P8 закрыта 🟠 — adversarial-аудит не выполнен (давний долг).
(18) формулировка Validation 1 в ТЗ P8.10 невыполнима как записана. (19) посторонние untracked
каталоги `.swissknife/` и `packages/task/lib/.claude/` — унаследованный долг, этим заходом не
тронуты. (20) эталон-корпус P9.3/P9.4 (8 кейсов / 50 находок) — sanity-check размер, не
статистически надёжная оценка. (21) `review-roles.json` сознательно НЕ входит в `audited_paths`
provider-аудита (D126 Consequences (2)). (22) дрейф пяти reviewer-паков —
`findings/P9.2-review-roles-drift.md`, адресован P7.2. (23) одиночная пустая строка внутри таблицы
`## 3. Routing` тихо режет таблицу (D133 починен точечно); `plan_lint.py` не несёт диагностики
целостности §3 — роадмап-кандидат. (24) пять остаточных R2/R4-исключений перечня несут
стале-суффиксы/неоднозначность (P11.5 Pending Work). (25) `verify-citations.py --strict` даёт
находки внутри Completion Notes уже закрытого 🟢 P11.5 — самореференсный класс;
`config.json:checks[plan-citations].mode` остаётся `warn` до адресации владельцем. (26) **новый:**
дельта для тела `general/mcp-advisor` (три пункта, P1.1 Pending Work) не внесена — правка
запечатанного `SKILL.md` тянет публикационную цепочку вне `Files` P1.1, владелец тела (P5.2, D98)
терминален; нужен либо новый item, либо строка `roadmap.md`.

**Workarounds / Deferred / Open questions:** обходок в коде нет; вердикт P1.1 не нёс ни одного
`[POSSIBLE-DEFECT]` — оба несущих факта сняты дословной цитатой first-party доки.
**Открытые вопросы владельцу (OQ-11, `open-questions.md`):** нужны ли отдельные машинные классы
«число прозы против числа таблицы» (F1) и «ссылка на D-запись» (F9); судьба реестра ролей P9.2 при
регрессе `ΔR=-0.12`; апгрейд `plan-citations` `warn`→`strict` (условие — Open risk (25)); куда
адресовать дельту `mcp-advisor` (Open risk (26)). **Отложено ранее:** F8 (хеши item-коммитов в §6
Update Log); машинный lint формы §3 в `plan_lint.py`; сверка полноты матрицы `docs/status.md` (D2);
удаление/gitignore `install.log`; перевод `maind/provider_deploy.py` на `assert_safe_replace_target`;
заполнение `triggers[]` у четырёх скиллов с `evals/`; включение `Closure Protocol | v1` на
`2026.07.18-FOREMAN`/`2026.07.24-AGENT-RELIABILITY`; расширение реестра ревью на остальные 39 ролей;
роадмап-кандидат «гейт воспроизводимость ревью не деградировала» (D68/D71); перепин на тег Serena
(D110). Класс «голое path-упоминание» отклонён измерением (D128) — кандидат в
`docs/rejected-optimizations.md`. Переписать примеры формы цитаты в Code Guidance P11.1/P11.2
(`phases/P11.md:205,258`) без обратных кавычек — роадмап-кандидат.
