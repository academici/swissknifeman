# HANDOFF — 2026-08-02 — after P6

**Next:** детализировать фазу **P7** («Закрытие roadmap в ноль») — сегодня скелет (0/4,
`⬜ Not started`); P6 закрыта 🟠 Done with deviations, следующая фаза по номеру — последняя в
плане.

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — детализация фазы: контракт-блок, четыре ТЗ items, DoR-свип |
| Context | NEW SESSION — шаг-не-item |
| Суть | `plan-design 2026.07.31-SKM-LEAN P7` разворачивает скелет P7 в полные ТЗ items |
| Команда | `/task:plan-design 2026.07.31-SKM-LEAN P7` |

**Done:** **Фаза P6 закрыта 🟠 Done with deviations.** Все три item'а терминальны в очереди
D62 (P6.3 → P6.1 → P6.2). `core/` получил доменный подпакет `core/provider/` (6 модулей без
префикса) с зеркалом `core/tests/provider/`; фасад `core/__init__.py` не изменил `__all__`
(108 имён, D68, машинное сравнение); утверждённые хеши манифеста сведены к единственному
носителю (`core/tests/provider/test_manifest.py`) с диагностическим сообщением при
регенерации; `core/tests` — 251/251 зелёных (baseline снят P6.3 первым в очереди).
`.swissknife.json` читается типизированным frozen dataclass `ProjectConfig`
(`packages/skiller/lib/skiller/config.py`), `CONFIG_KEYS` выведен из его полей (13 ключей, не
14 — факт разошёлся с числом ТЗ); оба гейта синхрона со схемой не тронуты. `docs/core/index.md`
и `packages/skiller/docs/guide/installation.md` обновлены (docs-sync: обновлено). Известные
отклонения по items — в `## Phase Handoff` `phases/P6.md` (агрегат механический, дословно из
Known Deviations трёх items). `closure/P6.json` написан (Closure Protocol v1).

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
P5 6/11 (🟠 Done with deviations, терминальна) · **P6 0/3 (🟠 Done with deviations, терминальна)**
· P7 0/4 (⬜, скелет — последняя нетерминальная фаза плана). `plans/ACTIVE.md` и `Status` плана
не трогаются — не все фазы плана терминальны.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P6.md` (`## Phase Status`,
`## Phase Handoff`, Completion Notes трёх items) · `plan.md` §4 Status Board, §6 Update Log,
`## 0. Meta` Last Updated · `plans/2026.07.31-SKM-LEAN/closure/P6.json` ·
`core/provider/` · `core/tests/provider/test_manifest.py` ·
`packages/skiller/lib/skiller/config.py` (`ProjectConfig`, производный `CONFIG_KEYS`) ·
`docs/core/index.md` · `packages/skiller/docs/guide/installation.md`.

**Open risks:**

- **Чужой дифф в рабочем дереве** (этим заходом не тронут, тот же класс что на закрытии P5):
  удалённый `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`.
  `git add -A` запрещён — эти файлы вне `Files` items фазы P6.
- **`ruff` несёт пред-существующие ошибки** (3 на путях skiller: `publication.py:1037` B904,
  `test_budget_listing_providers.py:24` F401, `test_status.py:17` F401): новых от диффа P6 —
  ноль.
- **`scripts/test-provider-docs.py` несёт 1 известный FAIL** (`test_committed_outputs…`,
  средо-зависимая хрупкость снимка дерева — чужой mAInd-демон) — адресован
  `roadmap/provider-docs-snapshot-daemon-noise.md` (P5.2 владелец адреса).
- **Остаточный `plan-lint` WARN** систематического класса (D29, оркестрация фазы P6 без
  workflow-скрипта) — тот же класс, что несут `phases/P1.md`/`P3.md`/`P4.md`/`P5.md`; фикс —
  завести `plans/2026.07.31-SKM-LEAN/workflows/` для P6 либо решением владельца снять
  формулировку оркестрации из Phase Context P6.
- **Типизация не сплошная:** `integrate.py`, `hub.py`, `quality/analyze.py`,
  `quality/audit.py` читают конфиг через Mapping-проекцию (поведение идентично) — перевод на
  атрибуты не сделан (Pending Work P6.2).
- Прежние (не изменились): ветка (C) OQ-6 не проверена данными (usage не мерялся) ·
  U1/U2 `[UNVERIFIED]`, остаток риска D106, контракт P4.1 пинован на `06fefc87` ·
  окружной дефект `codex exec -s read-only` (bwrap/AppArmor) · P5.3 Pending Work (унификация
  четырёх парсеров `*.env.ini`) · P5.5 Pending Work (`codex plugin update` без теста) ·
  P5.9 Pending Work (stray-упоминание `plan-audit-loop.md` в
  `roadmap/plan-design-vs-exec-status-check.md:70`).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений по составу плюс новое от P6: унификация парсеров `*.env.ini`
  (P5.3) · `codex plugin update` round-trip (P5.5) · DX-схема `upstream.schema.json` для
  `audit`/`kind` (P5.11) · снимок `test_committed_outputs…` от чужого mAInd-демона (P6.3) ·
  типизация `.swissknifeman/config.json` (`SKILLSET_KEYS`, P6.2, соседний носитель, Scope
  Excluded) · перевод 4 потребителей `load_config` на атрибуты (P6.2 Pending Work) ·
  `plan-lint` WARN D29 для фазы P6 (workflow-скрипт либо снятие формулировки).
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец
  протокола). Новых этим заходом не заведено.
