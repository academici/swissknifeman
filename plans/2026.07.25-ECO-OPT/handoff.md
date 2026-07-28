# HANDOFF — 2026-07-28 — after P9.2

**P9.2 закрыт 🟢 Done.** Реестр ролей ревью — extension-таблица
`packages/harness/configs/common/agent-packs/review-roles.json` (ключ `(pack_id, role_id)`,
рядом с каноном `roles.json`, D126) + валидатор `harness.reviewroles` (stdlib, восемь
проверок) + шаг `[8/8]` в `packages/harness/scripts/validate.sh`. `role-bindings.json` и
`agentpacks.py` не тронуты вовсе (frozen provider-contract). `bash
packages/harness/scripts/test.sh` → `Ran 442 tests … OK`, `bash
packages/harness/scripts/validate.sh` → `OK`. Детали — `phases/P9.md` P9.2 Completion Notes,
коммиты `ffb52ea1` (item) + bookkeeping ниже.

**Next:** фаза P9 внутренний порядок `P9.3 → P9.2 → P9.4 → P9.1` (D67/D68) — P9.3🟢/P9.2🟢/
P9.1🟠 терминальны, единственный оставшийся item фазы — **P9.4** (повторный замер корпуса +
вердикт дельты). Routing: `implementation/high`, `Exec = manual` (hands-on: 3 прогона на
кейс + арбитраж, `plan-exec` такое не прогонит) — деривация §9, эта команда пинит
sonnet/medium и такой item НЕ исполняет.

| Параметр | Значение |
|:--|:--|
| Model | Sonnet 5 |
| Thinking | high — §3 Routing P9.4: hands-on замер (3 прогона/кейс) + человеческий арбитраж, не выводится агентом на дефолтном тире |
| Context | continue (/clear) — ручной item |
| Суть | Повторный прогон эталон-корпуса `artifacts/p9-review-corpus/` на дереве с терминальной P9.2, расчёт `J`/`U1`/`R`/`R1` тем же скорером, вердикт по правилу из P9.3 |

```
ЗАПУСК ВРУЧНУЮ: sonnet/high — читать plans/2026.07.25-ECO-OPT/phases/P9.md item P9.4
целиком (Intent/Why/Scope Included/Excluded/Inputs/Files/Required Reads/Implementation
Rules/Code Guidance/Validation), затем /task:plan-run 2026.07.25-ECO-OPT P9.4
```

Альтернатива в этой же сессии: `/model opus` (или сохранить sonnet, если оператор считает
effort high достаточным без смены модели) + `/effort high` + `/task:plan-run
2026.07.25-ECO-OPT P9.4` (D18).

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · фаза P10
закрыта (P10.1🟢 `0b33116c`+`243254aa` · P10.2🟠 `47d6972d` · P10.3🟠 `ae54d790` · P10.4🟠
`77bf9d8c`) · фаза P5 закрыта (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` ·
P5.4🟢 `253ae4a6` · P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) · фаза P8 закрыта (P8.1🟠 `5f5dfa73` ·
P8.2🟢 `2a6cbb3d`/`9950eaa0` · P8.3🟠 `c36bbee5` · P8.4🟢 `5b7cc15e` · P8.5🟢 `d12ccaf7` · P8.6🟢
`12ff61e1` · P8.7🟢 `fa1ee8bf` · P8.8🟢 `4ee3ba6d` · P8.9🟢 `980ce398` · P8.10🟠 `a020f434`) ·
P9.1🟠 `05c5d87e` · P9.3🟢 `a2ac24b1`/`be6c8822` · **P9.2🟢 `ffb52ea1`** · P2.1 · P3.2 · P1.2 —
**32/44 items закрыто**, 3 фазы терминальны (P5, P8, P10), 4 фазы в работе (P9 — 3/4 закрыто,
P2 — 1/3, P3 — 1/6, P1 — 1/2), 2 фазы не начаты (P4, P6, P7).

**Remaining:** 12/44 items. **P9.4** свободен к запуску (единственный оставшийся item фазы
P9, вход — терминальная P9.2). Прочие свободные: **P1.1** (frontier/high, manual) ·
**P3.1** (implementation/medium, manual — нужен оператор для `/doctor`/`/context`) ·
**P2.3** (frontier/high, manual — её гейт «после P8 и P6.3» снят частично: P8 вся
терминальна, P6.3 ещё не исполнена). Порядковые условия: P2.3 — ПОСЛЕ P8 (выполнено) и P6.3
(D93, не выполнено); P6.1 — ПОСЛЕ P9.1 (снято); P4.2 — ПОСЛЕ P3.2 (снято). Фаза P8 закрыта
🟠 ⇒ по правилу «была 🟠 → сперва аудит» adversarial-аудит `phases/P8.md` остаётся открытым
шагом (Open risks (16)).

**Sources of truth:** `plan.md` (§3 Routing — строка P9.4; §5 D126; §6 Update Log; §4 Phase
Index P9 3/4) · `phases/P9.md` (`## Phase Status` — P9.1🟠/P9.2🟢/P9.3🟢/P9.4⬜; P9.2
Completion Notes — реализация и команды) · `packages/harness/configs/common/agent-packs/
review-roles.json` + `lib/harness/reviewroles.py` (новый носитель и валидатор, D126) ·
`findings/P9.2-review-roles-drift.md` (карта дрейфа пяти паков, финальная версия) ·
`findings/P9.3-review-baseline.md` (baseline-числа, пин конфигурации, правило вердикта для
P9.4) · машинные гейты `plans/cross-plan-files.py`, `plans/verify-citations.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (0) П9.2 не даёт новых рисков — рабочее дерево чисто после item-коммита
`ffb52ea1` (проверено `git diff --stat` по role-bindings.json/agent-packs телам/roles.json —
пусто). (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` не
вычитана (`[UNVERIFIED]`, D110); (3) P10.4 Pending Work — рендерер `.mcp.json` (D106); (4)
P10.3 Pending Work — `README.md:122` битая ссылка (кандидат `/task:fix`); (5) F13/F14 аудита
P5 (заход 2) — за владельцем P5/`maind`; (6) P10.2 Pending Work (b) —
`verify-citations-known-exceptions.json` не решён владельцем; (7) carve-out (б) канона
`plan-protocol` не переписан (D118); (8) P8.4 job `hygiene` не подтверждён реальным
CI-run'ом; (9) `plans/2026.07.18-FOREMAN` несёт нелегальную форму ячейки §3
(`P4.1–P4.2, P4.4`, строка 87) — правит FOREMAN; (10) матрица `docs/status.md` не сверена с
живыми контрактами (D2, отложено); (11) `public-hygiene` CI-гейт (P8.6) красный на текущем
дереве — `install.log` в `artifacts/p5-pilot/stage0/` (owner); (12) три CORE-скилла без
активационной секции — унаследованный долг (P8.8); (13) пред-существующая ruff-находка
`B904` в `packages/skiller/lib/skiller/publication.py:1037` — вне `Files` P8.9 (кандидат
`/task:fix`); (14) формулировка Validation 1 в ТЗ P8.10 невыполнима как записана; (15)
посторонние untracked каталоги — `.swissknife/` и `packages/task/lib/.claude/` —
унаследованный долг с закрытия P8; (16) фаза P8 закрыта 🟠 — adversarial-аудит
(`/task:plan-audit 2026.07.25-ECO-OPT P8`) не выполнен; (17) эталон-корпус P9.3 — 8
кейсов/50 находок — sanity-check размер, НЕ статистически надёжная оценка; корпус C5 не
поймал `F030` ни одним из 3 прогонов; (18) `review-roles.json` сознательно НЕ входит в
`audited_paths` provider-аудита ⇒ его целостность держит ТОЛЬКО шаг `[8/8]` `validate.sh`
(D126 Consequences (2)); (19, НОВОЕ) дрейф пяти reviewer-паков (три написания заголовка
«Гейты вердикта», разброс `skills:` 6/6/4/2/1, пустые `reviewer-overrides.md`) зафиксирован
`findings/P9.2-review-roles-drift.md`, адресован треку 1 OQ-4 / P7.2 — не чинится этим
планом.

**Workarounds / Deferred / Open questions:** обходок в коде нет. Open question P9.2
закрыт D126 и реализован. Отложено владельцем: **F8** (хеши item-коммитов в §6 Update Log);
машинный lint формы §3 в `plan_lint.py`; сверка полноты матрицы `docs/status.md` (D2);
удаление/gitignore `install.log` (P8.6 Pending Work, owner); перевод
`maind/provider_deploy.py` на `assert_safe_replace_target` (P8.7, roadmap-кандидат);
заполнение `triggers[]` у четырёх скиллов с `evals/` (P8.8, WARNING); включение
`Closure Protocol | v1` на `2026.07.18-FOREMAN`/`2026.07.24-AGENT-RELIABILITY` (P8.1 Pending
Work, owner); расширение реестра ревью на остальные 39 ролей (Scope Excluded P9.2 —
кандидат в roadmap). Долг «перепиннуться на тег Serena» держит `roadmap.md` §
«Отложенное» (D110). Agent-tool не экспонирует independent `effort` для суб-агентов —
известное ограничение конфигурации P9.3, не блокирует.
