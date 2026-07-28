# HANDOFF — 2026-07-28 — after P11

**Фаза P11 закрыта 🟠 Done with deviations.** Все 8 items терминальны (P11.1–P11.5, P11.8 — 🟢
Done; P11.6, P11.7 — 🟠 Done with deviations). Доска `plan.md` §4 — `P11 6/8`, статус фазы
`🟡 In progress → 🟠 Done with deviations`. `closure/P11.json` заведён (Closure Protocol v1).
Продукт фазы: двухшаговый резолвер путей + json-класс цитаты + расширенная поверхность скана
(P11.1–P11.2) · кросс-документный чек `handoff.md`↔доска в `plan_lint.py` (P11.3) ·
dogfood-доказательство на непочиненном дереве (P11.4) · триаж 33 уникальных цитат + baseline-
перечень `verify-citations-known-exceptions.json` (P11.5) · гейт цитат врезан в канон закрытия
item'а (P11.6) · третья точка принуждения — `plan-citations` в `review-gate`, mode `warn` (P11.7) ·
реконсиляция терминальной фазы P9 по всем 12 находкам её аудита без реопена (P11.8). Детали —
`phases/P11.md` `## Phase Handoff` (Known Deviations по item'ам, docs-sync вердикт, что дальше).

Плановое дерево вне P11 не терминально (P1/P2/P3 в работе, P4/P6/P7 не начаты) — `plans/ACTIVE.md`
не трогается, план в целом остаётся `🟡 In progress`.

**Next:** следующий шаг вне протокола — владелец выбирает, какую фазу продолжать (P1/P2/P3 в
работе, P4/P6/P7 не начаты; свободные items вне фазовой очереди — см. ниже).

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — стандартный tiered exec ближайшего готового item'а |
| Context | continue (/clear) — ручной item |
| Суть | Продолжить план: ближайший готовый item среди P1/P2/P3 (владелец выбирает конкретный) |

```
/task:plan-exec 2026.07.25-ECO-OPT P1.1
```

Свободные items вне фазы P11 (не гейтованы): **P1.1** (frontier/high, manual) · **P3.1**
(implementation/medium, manual — нужен оператор для `/doctor`/`/context`) · **P2.3**
(frontier/high, manual — ждёт P6.3). Непогашенный adversarial-аудит фазы **P8** — по-прежнему
открыт (Open risks (17)).

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие находок) · фазы **P5** (5/6 🟠),
**P8** (7/10 🟠), **P9** (3/4 🟠, реконсиляция P11.8 применена — 12 находок аудита закрыты),
**P10** (1/4 🟠), **P11** (6/8 🟠, все 8 items терминальны) терминальны · P2.1 · P3.2 · P1.2 —
**41/52 items закрыто 🟢** (P11.6/P11.7 и другие closed-with-deviations items не входят в
числитель доски), 5 фаз терминальны, 3 в работе, 3 не начаты (P4, P6, P7).

**Remaining:** 11/52 items вне фазы P11 (P11 полностью закрыта). Порядковые условия: P2.3 — ПОСЛЕ
P8 (выполнено) и P6.3 (D93, не выполнено); P6.1 — ПОСЛЕ P9.1 (снято); P4.2 — ПОСЛЕ P3.2 (снято).

**Sources of truth:** `plan.md` (§3 Routing — восемь строк P11; §4 Phase Index — P11 6/8 🟠;
§5 D127–D134; §6 Update Log — запись закрытия P11) · `phases/P11.md` (Phase Context + контракт
фазы + 8 items с ТЗ и Completion Notes + `## Phase Handoff`, все терминальны) ·
`findings/P11-citation-gate-measurements.md` (слой 1) · `findings/P11-gate-dogfood-proof.md`
(слой 3) · `research/27-P11-citation-gate-target-design.md` (слой 2) ·
`plans/verify-citations-known-exceptions.json` (19 записей, P11.5) · `brief/01-refinements.md`
блок 2026-07-28 (слой 0) · `phases/P9.md` блок `## Audit P9 — 2026-07-28` (12 находок, закрыты
P11.8) · `closure/P11.json` (Closure Protocol v1) · машинные гейты `plans/verify-citations.py`,
`plans/cross-plan-files.py`, `packages/task/scripts/plan-lint.py` ·
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §8 (обновлён P11.6) ·
`packages/task/commands/plan-close.md` (обновлён P11.6) ·
`packages/harness/configs/claude-code/hooks/review-gate/` (диспетчер + 4 проверки, P11.7).

**Open risks:** (0) design-заход кода не менял — рабочее дерево несёт только плановые файлы плюс
унаследованную грязь. (1) измеренный регресс воспроизводимости ревью `ΔR=-0.12` между P9.3 и
P9.4 — решение о судьбе реестра P9.2 за владельцем, фаза P11 его НЕ решает и от него не зависит.
(2) из четырёх находок аудита P9, названных брифом как dogfood-корпус, машинно ловится
**только F8**; F1/F2/F9 остаются человеческой правкой (закрыто P11.8) — D130. (3) гейт P11.3
(handoff↔доска) сразу нашёл живое расхождение в предыдущей редакции ЭТОГО файла (строка 44) —
оставлено сознательно непочиненным (Scope Excluded P11.3), гасится следующим bookkeeping-проходом
(владелец решает, каким item'ом/сессией). (3a) факт остаточного корпуса гейта на P11.4 разошёлся
с design-симуляцией (628/52 против предсказанных 587/48) — разбор в P11.5 (33 уникальные цитаты).
(4) второй красный тест `packages/maind/scripts/test.sh` — пред-существующий долг. (5) дельта
Serena `v1.6.1` → `1.6.2.dev0` не вычитана (`[UNVERIFIED]`, D110). (6) P10.4 Pending Work —
рендерер `.mcp.json` (D106). (7) закрыт P11.5 — `verify-citations-known-exceptions.json` заведён.
(8) F13/F14 аудита P5 (заход 2) — за владельцем P5/`maind`. (9) P10.3 Pending Work —
`README.md:122` битая ссылка. (10) carve-out (б) канона `plan-protocol` не переписан (D118).
(11) P8.4 job `hygiene` не подтверждён реальным CI-run'ом. (12) `plans/2026.07.18-FOREMAN` несёт
нелегальную форму ячейки §3 (строка 87) — правит FOREMAN. (13) матрица `docs/status.md` не
сверена с живыми контрактами (D2). (14) `public-hygiene` CI-гейт красный на текущем дереве
(`install.log`, owner). (15) три CORE-скилла без активационной секции (P8.8). (16) ruff-находка
`B904` `packages/skiller/lib/skiller/publication.py:1037` — кандидат `/task:fix`. (17) фаза P8
закрыта 🟠 — adversarial-аудит не выполнен (давний долг). (18) формулировка Validation 1 в ТЗ
P8.10 невыполнима как записана. (19) посторонние untracked каталоги `.swissknife/` и
`packages/task/lib/.claude/` — унаследованный долг. (20) эталон-корпус P9.3/P9.4 (8 кейсов / 50
находок) — sanity-check размер, не статистически надёжная оценка. (21) `review-roles.json`
сознательно НЕ входит в `audited_paths` provider-аудита (D126 Consequences (2)). (22) дрейф пяти
reviewer-паков — `findings/P9.2-review-roles-drift.md`, адресован P7.2. (23) одиночная пустая
строка внутри таблицы `## 3. Routing` тихо режет таблицу (D133 починен точечно на этом плане);
`plan_lint.py` не несёт диагностики целостности §3 — роадмап-кандидат. (24) пять остаточных
R2/R4-исключений перечня несут стале-суффиксы/неоднозначность (P11.5 Pending Work), не блокирует
strict-класс. **(25) P11.6/P11.7:** `verify-citations.py --strict` на живом дереве даёт **16
находок**, все внутри Completion Notes уже закрытого 🟢 P11.5 (`phases/P11.md:628-634,648,676`) —
самореференсный класс «список починенных цитат сам является цитатой»; фикс-предложение —
`phases/P11.md` P11.5/P11.6/P11.7 Pending Work; `config.json:checks[plan-citations].mode`
остаётся `warn` до адресации (25) владельцем.

**Workarounds / Deferred / Open questions:** обходок в коде нет. **Открытые вопросы владельцу
(**OQ-11**, `open-questions.md`):** нужны ли отдельные машинные классы «число прозы против числа
таблицы» (F1) и «ссылка на D-запись» (F9); судьба реестра ролей P9.2 при регрессе `ΔR=-0.12`;
апгрейд `plan-citations` `warn`→`strict` (условие — Open risk (25)). **Отложено ранее:** F8
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py`; сверка полноты
матрицы `docs/status.md` (D2); удаление/gitignore `install.log`; перевод `maind/provider_deploy.py`
на `assert_safe_replace_target`; заполнение `triggers[]` у четырёх скиллов с `evals/`; включение
`Closure Protocol | v1` на `2026.07.18-FOREMAN`/`2026.07.24-AGENT-RELIABILITY`; расширение
реестра ревью на остальные 39 ролей; роадмап-кандидат «гейт воспроизводимость ревью не
деградировала» (D68/D71); перепин на тег Serena (D110). Класс «голое path-упоминание» отклонён
измерением (D128) — кандидат в `docs/rejected-optimizations.md`. Переписать примеры формы цитаты
в Code Guidance P11.1/P11.2 (`phases/P11.md:205,258`) без обратных кавычек — роадмап-кандидат.
16 самореференсных находок в Completion Notes P11.5 (Open risk (25)) — решение объединить обе
правки за владельцем.
