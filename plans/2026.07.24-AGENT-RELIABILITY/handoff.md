# HANDOFF — 2026-07-26 — after P1.5

**Committed item tree: `0a87a4e5`** (item-коммит, форма `git commit --only -- <пути>` — чужой
дифф в индексе/дереве остался ровно там же и в том же виде). Этот файл коммитится следом
бухгалтерией (`plans/2026.07.24-AGENT-RELIABILITY` + `plans/ACTIVE.md`); собственный хеш в него
не вписывается.

**P1.5 закрыт `🟠 Done with deviations`.** Четыре root-дубля `architect`
(`architecture`, `codebase-design`, `domain-modeling`, `package-contribution-protocol`)
удалены из `.agents/skills/` после доказательства ownership (frontmatter `name:` канона ==
frontmatter root-адаптера + членство identity в published `architect` bucket unit —
совпадение по display-префиксу/байтам НЕ использовано). `workflow-craft` получил class-B
(D43) запись: `configs/repository-bootstrap-skills.json` несёт новый ключ `class_b`,
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.5/root-bootstrap-extension-map.json` —
новый frozen-артефакт (schema v1, 1 запись). Root-bootstrap renderer (`publication.py`)
расширен вторым классом источника: тонкая Codex-only проекция `workflow-craft`
(provenance/hash, без тела), precondition проверяется против ЯВНО переданного
`donor_enabled` (никогда live-профиль/кэш). `repository-bootstrap` `0.1.0→0.2.0`, `skiller`
package API `0.4.1→0.4.2`; combined lock — 27 records. **Найден и исправлен риск регрессии
до коммита:** первая версия рендера стамповала умбрелла-версию во ВСЕ 26 class-A проекций
(нарушая явный byte-identical guard контракта) — исправлено новым D38-замороженным
`class_a_content_version` (`0.1.0`, никогда не двигается), умбрелла-версия используется
только в lock/class-B. Генератор и `registry --check` теперь проверяют «root-набор
провайдера == declared target set» (undeclared каталог — ошибка). `doctor.py` получил
read-only детектор D42 (`detect_core_donor_collisions`); `skiller doctor
--provider-distribution` воспроизводит ровно девять именованных core↔donor пар. Детали,
числа и команды — `phases/P1.md` P1.5 Completion Notes/Known Deviations,
`findings/P1.5-collision-closure.md`.

**Material Known Deviation, важно для P1.4 (см. Open risks/Next ниже).**
`build_effective_inventory.py --check-collision-owners` (Validation P1.5) остаётся красным
(16 failures) — структурно, не по вине этого item'а: скрипт требует ТОЧНОГО совпадения
измеренного СЕЙЧАС carrier-набора против ЗАМОРОЖЕННОГО P1.1-снапшота, собранного ДО
P1.2/P1.3/P1.5; ни P1.2, ни P1.3 не перезахватывали `remediation-map.json` после своих
(корректных, утверждённых) root-удалений. Все 16 failures объяснены исчерпывающе в
Known Deviations (3) `phases/P1.md` — ни одна коллизия НЕ осталась без владельца в смысле
контракта `semantic-identity-ownership-v1.md`, но БУКВАЛЬНЫЙ вывод скрипта не сходится.
Это НЕ мой выбор статуса ради «отчитаться» — это material-отклонение по status-rule
(Validation осталась красной, не чинится в рамках Scope P1.5 — скрипт и map заморожены
P1.1, вне Files P1.5).

**Коммит-гигиена, живое предупреждение (класс не изменился).** Рабочее дерево по-прежнему
несёт чужой дифф параллельного процесса — `assert_generated_scope.py generated-scope
--owner P1.5` насчитывает **28 uncommitted foreign paths** вне owner-набора P1.5 (owned=19,
foreign_commit=0). Item-коммит `0a87a4e5` сделан формой `git commit --only -- <пути>`.
`packages/skiller/skills/general/workflow-craft/{SKILL.md,SKILL.ru.md}` (канон class-B) БЫЛ
ГРЯЗЕН на старте этого item'а тем же чужим процессом — прочитан заново непосредственно перед
использованием как канон; текущие байты (sha256
`a0d26c8d3fd174ab72de0333377b25e6040d1eecbac5ed9d04a3a4ccd9756586`) совпали БАЙТ-В-БАЙТ с уже
запиненным `remediation-map.json::class_b.canonical_sha256` — совпадение подтверждено, файл
не тронут (вне Files P1.5), git status на закрытии по-прежнему грязный (чужой владелец).

**Next:** `/task:plan-design 2026.07.24-AGENT-RELIABILITY P1.4`

P1.4 заблокирован собственной precondition — требуется `plan-design`, не `plan-exec`.
P1.4 Implementation Rules буквально требуют committed **green** P1.5 («их отсутствие или
non-green статус P1.5 — fail closed без запуска фикстур», D41) — P1.5 закрыт `🟠`, не `🟢`.
`/task:plan-exec P1.4` немедленно упадёт fail-closed на этой precondition, а не на
содержательной работе. Это конфликт правил (P1.4 ТЗ написано под допущение «P1.5 всегда
🟢», реальность плана — фазовая ремедиация может закрываться 🟠 с material, но полностью
объяснённым остатком) — решает Owner/`plan-design`, не исполнитель: либо (а) новый D#
явно принимает P1.5 `🟠` как достаточное входное условие P1.4 (все 16
`check-collision-owners` failures объяснены, ownership-контракт цел), переписывая
Inputs/Implementation Rules P1.4 с «green» на «terminal (🟢 или 🟠 с объяснённым Known
Deviations)», либо (б) заводится узкий follow-up fix-item, чинящий `check_collision_owners`
(allowlist `--tolerate-resolved <owner-item>` ИЛИ `resolved_by` поле в `remediation-map.json`
по closure каждого owner-item'а — оба варианта трогают ЗАМОРОЖЕННЫЙ P1.1-контракт и требуют
своего owner'а/ADR), который выполняется ПЕРЕД P1.4 и переводит P1.5 в 🟢 задним числом
(через новый D# + bookkeeping-правку, не тихую правку Completion Notes).

| Параметр | Значение |
|:--|:--|
| Model | opus (`plan-design` пин) |
| Thinking | high — конфликт правил precondition P1.4 vs фактический статус P1.5, решение владельца/дизайна |
| Context | NEW SESSION — шаг-не-item |
| Суть | Разрешить конфликт: P1.4 Inputs/Implementation Rules требуют green P1.5, P1.5 закрыт 🟠 с полностью объяснённым material Known Deviation — новый D# принимает 🟠 как достаточное ИЛИ заводит узкий fix-item на `check_collision_owners`/`remediation-map.json` ПЕРЕД запуском P1.4 |

```
/task:plan-design 2026.07.24-AGENT-RELIABILITY P1.4
```

**Done:**
- Четыре `.agents/skills/{architecture,codebase-design,domain-modeling,
  package-contribution-protocol}/` каталога удалены (8 файлов) после per-identity
  ownership-доказательства.
- `packages/skiller/configs/repository-bootstrap-skills.json` — новый ключ `class_b`
  (1 запись) + новое D38-замороженное поле `class_a_content_version: "0.1.0"`.
- `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.5/root-bootstrap-extension-map.json` —
  новый frozen-артефакт (schema v1, 1 запись, все поля ТЗ).
- `packages/skiller/lib/skiller/publication.py` — class-B рендер (thin Codex projection,
  явный `donor_enabled` precondition-параметр), `assert_root_bootstrap_set_completeness`.
- `packages/skiller/lib/skiller/registry.py` — `build_catalog` (shared helper), wiring
  completeness-check в `check_drift`/`write_plugin_manifests`.
- `packages/skiller/lib/skiller/doctor.py` — `detect_core_donor_collisions` (D42) +
  `_provider_distribution_doctor` печатает диагностику.
- `packages/skiller/package.json` `0.4.1→0.4.2`; `configs/publication-versions.json`
  `units.repository-bootstrap` `0.1.0→0.2.0`.
- `packages/skiller/adapters/repository-bootstrap/publication-lock.json` — 27 records.
- `.agents/skills/workflow-craft/SKILL.md` — регенерирована как тонкая class-B проекция.
- 6 тестовых файлов сверены/расширены (84 focused-теста зелёные); один pre-existing latent
  bug исправлен (`test_provider_publication_parity.py` — сверка `core` version против
  `publication-versions.json`, не `package.json`).
- `findings/P1.5-collision-closure.md` — catalog-wide closure report.
- `CHANGELOG.md` — запись `[Unreleased]`.

**Remaining:** 15/22 items `⬜`+🟠 (плюс P0.4 🟠, P1.2 🟠, теперь P1.5 🟠). Порядок фаз: P0 →
P1 (P1.2 ✅ → P1.3 ✅ → P1.5 ✅🟠 → **P1.4 — заблокирован конфликтом precondition, см. Next**)
→ P2 → P3 → P4.

**Sources of truth:** `plan.md` v1.12.9 (§0 Last Updated, §6 Update Log) · `phases/P1.md`
(Phase Status таблица, P1.5 Completion Notes/Known Deviations) · `findings/
P1.5-collision-closure.md` · `packages/skiller/configs/repository-bootstrap-skills.json` ·
`packages/skiller/adapters/repository-bootstrap/publication-lock.json` ·
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.5/root-bootstrap-extension-map.json` ·
`journal.jsonl`.

**Open risks:**
- **P1.4 precondition-конфликт (см. Next) — блокирует терминальный гейт фазы P1** пока Owner/
  `plan-design` не примет решение (новый D#).
- **28 незакоммиченных чужих путей остаются в дереве** (см. «Коммит-гигиена» выше) —
  `generated-scope` Validation P1.5 красная ИМЕННО из-за них (owned=19/foreign_commit=0/
  undeclared_drift=28, ни один owned-путь не задет). Владелец — чужой параллельный процесс;
  следующий item, читающий/трогающий owner-пути этого же класса, обязан повторить проверку
  `git status --porcelain` ПЕРЕД `baseline --capture-or-verify`.
- **`check_collision_owners` структурно несовместим с фазовой ремедиацией** (Known Deviation
  (3) `phases/P1.md` P1.5) — если Owner выберет путь (б) из Next, это отдельный fix-item,
  трогающий заморроженные P1.1-артефакты (`build_effective_inventory.py`,
  `remediation-map.json`), собственный ADR/D#.
- 21 недекларированный файл в root-поверхности (P1.1) — все, кроме `workflow-craft`
  (регенерирован этим item'ом, больше не «недекларирован»), закрыты P1.2/P1.3/P1.5.
- `command.interactive-user-input` отсутствует в каталоге capability (P1.1 находка) — новый
  public capability id требует D23 proposal/ADR/SemVer review, вне Scope закрытых items;
  остаётся named debt без переназначенного владельца.
- Claude enabled-set остаётся `unknown` (P1.1 долг, read-only команда не объявлена).
- Прежний долг без изменений: три находки A2; A1 F11; расхождение провенанса harness-CLI ↔
  maind-адаптера (из P0.4).
- `plans/README.md` § «Очередь планов» показывает устаревший счётчик item'ов этого плана —
  вне Files/carve-out этого item'а, не трогалось.

**Workarounds/Deferred/Open questions:**
- workarounds: class-A embedded version развязан от умбрелла-версии новым
  `class_a_content_version` полем (`configs/repository-bootstrap-skills.json`) — паттерн
  переиспользуется, если умбрелла-версия `repository-bootstrap` будет бампиться дальше
  (P2.2 держит её `0.2.0` byte-identical по ledger);
- deferred: `command.interactive-user-input` capability id (D23-гейт); расхождение
  провенанса harness-CLI ↔ maind-адаптера (P0.4, владельца нет); фикс
  `check_collision_owners`/`remediation-map.json` под фазовую ремедиацию (см. Open risks);
- open_questions: принимает ли Owner P1.5 `🟠` как достаточный вход P1.4 (новый D#) или
  требует отдельный fix-item ПЕРЕД P1.4 — см. Next.
