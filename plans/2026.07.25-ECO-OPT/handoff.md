# HANDOFF — 2026-07-28 — after P9.3

**P9.3 закрыт 🟢 Done** (эталон-корпус ревью + baseline воспроизводимости). 8 реальных диффов
(6 swissknifeman + 1 flexcrm/Laravel), стратифицированных по классу (логика/конфигурация-
провижининг/доки); `answer-key.json` — 50 `must_find` + 3 `is_trap`, размечены и закоммичены
ДО первого прогона (`git log` подтверждает порядок коммитов); `matching-rules.md` +
`score_review_runs.py` (stdlib, детерминированный, `--self-test` зелёный). 24 read-only
ревью-прогона (8 кейсов × 3, `packages/task/commands/review.md` как есть, одна конфигурация —
Opus, без MCP) → `runs-baseline.csv`; 29 неоднозначных матчей разрешены человеческим арбитражем
в `arbitration.json` (обязательный `reason` на каждое решение). Baseline (`findings/P9.3-review-
baseline.md`): `J=0.75`, `U1=0.20`, `R=0.80` (40/50), `R1=0.62`; три корзины (`matched TP=94` /
`judged FP=3` из 72 возможных столкновений с ловушкой / `plausible but unlabeled=290`); разброс
по кейсам назван честно (J кейса C3 = 0.29 < объявленного порога 0.30 — не спрятано); 10 из 50
`must_find` не пойманы ни одним прогоном (перечислены с severity). Правило вердикта P9.4
дословно из ТЗ: `ΔJ ≥ +0.10` И `ΔR ≥ 0` → сигнал улучшения; `ΔR < −0.05` → регресс; иначе —
«сигнала нет». `python3 packages/task/scripts/plan-lint.py plans/2026.07.25-ECO-OPT --baseline
HEAD` — 0 ERROR, 0 новых WARN от диффа item'а.

**Next:** внутрифазный порядок P9 — `P9.1(готово) → P9.3(готово) → P9.2 → P9.4`. Следующий
свободный шаг фазы — **P9.2** (`Exec = plan-exec`, реестр ролей ревью как данные + валидатор).

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — Routing §3 (`implementation/medium`, `plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | P9.2: реестр ролей ревью (`agent-packs/role-bindings.json` `binding_version` 1.0.0→1.1.0) + валидатор `lib/harness/reviewroles.py` + гейт в `validate.sh` |

```
/task:plan-exec 2026.07.25-ECO-OPT P9.2
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · фаза P10
закрыта (P10.1🟢 `0b33116c`+`243254aa` · P10.2🟠 `47d6972d` · P10.3🟠 `ae54d790` · P10.4🟠
`77bf9d8c`) · фаза P5 закрыта (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` ·
P5.4🟢 `253ae4a6` · P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) · фаза P8 закрыта (P8.1🟠 `5f5dfa73` ·
P8.2🟢 `2a6cbb3d`/`9950eaa0` · P8.3🟠 `c36bbee5` · P8.4🟢 `5b7cc15e` · P8.5🟢 `d12ccaf7` · P8.6🟢
`12ff61e1` · P8.7🟢 `fa1ee8bf` · P8.8🟢 `4ee3ba6d` · P8.9🟢 `980ce398` · P8.10🟠 `a020f434`) ·
P9.1🟠 `05c5d87e` · **P9.3🟢 `a2ac24b1`/`be6c8822`** · P2.1 · P3.2 · P1.2 — **31/44 items
закрыто**, 3 фазы терминальны (P5, P8, P10), 4 фазы в работе (P9 — 2/4, P2 — 1/3, P3 — 1/6,
P1 — 1/2), 2 фазы не начаты (P4, P6, P7).

**Remaining:** 13/44 items. Свободные к запуску (без порядковых условий друг относительно
друга, помимо аудита P8 ниже): **P9.2** (implementation/medium, `plan-exec`) · **P1.1**
(frontier/high, manual) · **P3.1** (implementation/medium, manual — нужен оператор для
`/doctor`/`/context`) · **P2.3** (frontier/high, manual — её гейт «после P8.1/P8.2/P8.3 и P6.3»
частично снят: P8 вся терминальна, но P6.3 ещё не исполнена). Порядковые условия: P2.3 — ПОСЛЕ
P8 (выполнено) и P6.3 (D93, не выполнено); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2
(условие снято); P9.4 — ПОСЛЕ терминальной P9.2 (не выполнено, без входа). Фаза P8 закрыта
🟠 (Known Deviations есть, эскалаций нет) ⇒ по правилу «была 🟠 → сперва аудит» adversarial-
аудит `phases/P8.md` остаётся открытым шагом (не выполнен этим заходом — P9.3 не пересекается
с P8 файлами, аудит и P9.3 независимы, оба свободны к запуску).

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing — P9.3 строка; §4 Phase Index —
P9 `1/4 🟡 In progress`; §6 Update Log — строка закрытия P9.3) · `phases/P9.md` (`## Phase
Status` — P9.1🟠/P9.3🟢/P9.2⬜/P9.4⬜; P9.3 Completion Notes) · `plans/2026.07.25-ECO-OPT/
artifacts/p9-review-corpus/` (cases.json/answer-key.json/matching-rules.md/score_review_runs.py/
runs-baseline.csv/arbitration.json) · `findings/P9.3-review-baseline.md` · машинные гейты
`plans/cross-plan-files.py`, `plans/verify-citations.py`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` не вычитана
(`[UNVERIFIED]`, D110); (3) P10.4 Pending Work — рендерер `.mcp.json` (D106); (4) P10.3 Pending
Work — `README.md:122` битая ссылка (кандидат `/task:fix`); (5) F13/F14 аудита P5 (заход 2) — за
владельцем P5/`maind`; (6) P10.2 Pending Work (b) — `verify-citations-known-exceptions.json` не
решён владельцем; (7) carve-out (б) канона `plan-protocol` не переписан (D118); (8) P8.4 job
`hygiene` не подтверждён реальным CI-run'ом; (9) `plans/2026.07.18-FOREMAN` несёт нелегальную
форму ячейки §3 (`P4.1–P4.2, P4.4`, строка 87) — правит FOREMAN, не этот план; (10) матрица
`docs/status.md` не сверена с живыми контрактами (D2, отложено); (11) `public-hygiene` CI-гейт
(P8.6) красный на текущем дереве — `install.log` в `artifacts/p5-pilot/stage0/` (owner); (12)
три CORE-скилла без активационной секции — унаследованный долг (P8.8); (13) пред-существующая
ruff-находка `B904` в `packages/skiller/lib/skiller/publication.py:1037` — вне `Files` P8.9
(кандидат `/task:fix`); (14) формулировка Validation 1 в ТЗ P8.10 невыполнима как записана; (15)
посторонние untracked каталоги в рабочем дереве — `.swissknife/` и `packages/task/lib/.claude/`
— унаследованный долг с закрытия P8, не блокирует; (16) фаза P8 закрыта 🟠 — adversarial-аудит
(`/task:plan-audit 2026.07.25-ECO-OPT P8`) остаётся не выполненным шагом; (17) эталон-корпус
P9.3 — 8 кейсов/50 находок — sanity-check размер (research/18 §4), НЕ статистически надёжная
оценка стабильности процедуры ревью; корпус C5 (public-hygiene/verify-tag) не поймал `F030`
(Major — отсутствие правила на SSH-ключи без суффикса) ни одним из 3 прогонов — названо в
`findings/P9.3-review-baseline.md` §4, не чинится этим item'ом (измеряет, не правит).

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py`; сверка полноты
матрицы `docs/status.md` (D2); удаление/gitignore `install.log` (P8.6 Pending Work, owner);
перевод `maind/provider_deploy.py` на `assert_safe_replace_target` (P8.7, roadmap-кандидат);
заполнение `triggers[]` у четырёх скиллов с `evals/` (P8.8, WARNING); включение `Closure
Protocol | v1` на `2026.07.18-FOREMAN`/`2026.07.24-AGENT-RELIABILITY` (P8.1 Pending Work,
owner). Долг «перепиннуться на тег Serena» держит `roadmap.md` § «Отложенное» (D110). Agent-tool
этой сессии не экспонирует independent `effort`-параметр для суб-агентов — известное ограничение
конфигурации P9.3 (`findings/P9.3-review-baseline.md` §0), не блокирует baseline.
