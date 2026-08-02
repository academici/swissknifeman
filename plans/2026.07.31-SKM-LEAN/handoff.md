# HANDOFF — 2026-08-02 — after P6.3

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — исполнить второй item фазы P6 — **P6.1** (очередь фазы
`P6.3 → P6.1 → P6.2`, D62; P6.3 зелёный baseline `core/tests` (251/0) — вход §5а)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — `implementation/high` по §3 Routing plan.md, триггер §10 «multi-package refactoring» (переезд 6 модулей ядра, 14 живых импорт-сайтов в четырёх пакетах, публичный фасад `__all__` — 108 имён, D68) |
| Context | continue (/clear) — ручной item |
| Суть | Переезд `core/` в доменный подпакет `core/provider/` (6 модулей без префикса) с зеркалом `core/tests/provider/`, неизменным по составу фасадом `core/__init__.py`; §5а — ДЕЛЬТОВАЯ приёмка `scripts/test-provider-docs.py` (D70): состав провалов не изменился относительно P6.3 |
| Команда | `—` (нет single-command эквивалента — `Exec = manual`) |

```
/model opus
/effort high
/task:plan-run 2026.07.31-SKM-LEAN P6.1
```

**Done:** **P6.3 закрыт 🟠 Done with deviations.** Дифф манифеста `af8d0f37^`↔`HEAD`
воспроизведён собственным прогоном (`difflib.unified_diff` на разобранном JSON): **19 пар**
изменённых строк, все вида `evidence[].source: "plans/…" → "plans/archive/…"`
(providers/capabilities/native_extensions/версии не тронуты, `(2, 35, 0)` сохранён) — число
19 расходится с оценкой findings («29»), собственный прогон авторитетен по IR §2. Утверждённые
хеши актуализированы СВОИМ прогоном (`provider_manifest_sha256`/`hashlib.sha256`): canonical
`9d8b9570…8920b4`, carrier `2b3bd60c…8f387d`. Литералы сведены в единственный носитель
`core/tests/test_provider_manifest.py` (namespace-пакет без `__init__.py` → импорт по имени
хрупок), `scripts/test-provider-docs.py` потребляет их через `importlib.util.spec_from_file_location`
(тот же приём, каким сам файл грузит `provider-docs.py`). Диагностическое сообщение
`REGENERATION_DIAGNOSTIC` (что произошло / команда семантического диффа / команда пересъёма
снимка) добавлено во все четыре сравнивающих `assertEqual`, подтверждено негативным прогоном
(1 бит испорчен в манифесте, оба раннера, манифест восстановлен `git checkout --`). `core/tests`
251/0 зелены (было `FAILED (failures=1)`); `scripts/test-provider-docs.py` — релевантный провал
`test_independent_exact_set…` исчез, средо-зависимый `test_committed_outputs…` **воспроизведён**
в трёх изолированных прогонах — root cause изолирован: `snapshot(ROOT)` цепляет
`packages/maind/data/state_store.db/mem%3Ahealth.bin`, переписываемый живым mAInd-демоном во
время прогона; заведён `roadmap/provider-docs-snapshot-daemon-noise.md` (класс
`deferred-with-criterion`) — этот вердикт есть **вход дельтовой приёмки P6.1 §5а** (D70).
`provider-docs.py --check` зелен (`0`), `git diff --stat -- configs/provider-capabilities.json`
пуст. Единственность носителя проверена структурно (оба новых хеша — 1 попадание, тот же файл;
оба старых литерала — 0 попаданий). `ruff` чисто. Item-коммит `90afaff1`. **Known Deviations:**
item-коммит несёт дифф вне `Files` — `roadmap/README.md` + новый `roadmap/provider-docs-snapshot-daemon-noise.md`
(top-level `roadmap/` не carve-out D75, но запись предписана `Implementation Rules` §6 самого
item'а) — детали `phases/P6.md` P6.3 Known Deviations.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
P5 6/11 (🟠 Done with deviations, терминальна) · **P6 0/3 (🟡 In progress, P6.3 терминален
🟠, очередь → P6.1 → P6.2)** · P7 0/4 (⬜, скелет). Не все фазы плана терминальны — `plans/ACTIVE.md`
и `Status` плана не трогаются.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P6.md` (`## Phase Status`, P6.3
Completion Notes) · `plan.md` §4 Status Board, §6 Update Log · `roadmap/provider-docs-snapshot-daemon-noise.md`
(новая запись) · `roadmap/README.md` (строка добавлена) · `plans/2026.07.31-SKM-LEAN/roadmap.md`
(карта батчей, очередь P6).

**Open risks:**

- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый
  `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`. `git add -A`
  запрещён — эти файлы вне `Files` всех items фазы P6.
- **`scripts/test-provider-docs.py` несёт 1 известный FAIL** (`test_committed_outputs…`,
  средо-зависимая хрупкость снимка всего дерева — чужой mAInd-демон) — измерено и адресовано
  `roadmap/provider-docs-snapshot-daemon-noise.md`; вход дельтовой приёмки P6.1 §5а (D70).
- **P6.1 — риск-класс «multi-package refactoring»** (14 импорт-сайтов в четырёх пакетах,
  публичный фасад `__all__` инвариант — 108 имён): `Exec = manual`, effort high обязателен;
  запуск ТОЛЬКО `/task:plan-run` (не `/task:plan-exec`, который пинит sonnet/medium и по гейту
  Routing обязан такой item отклонить).
- Прежние (не изменились): ветка (C) OQ-6 не проверена данными (usage не мерялся) ·
  U1/U2 `[UNVERIFIED]`, остаток риска D106, контракт P4.1 пинован на `06fefc87` ·
  окружной дефект `codex exec -s read-only` (bwrap/AppArmor) · P5.3 Pending Work (унификация
  четырёх парсеров `*.env.ini`) · P5.5 Pending Work (`codex plugin update` без теста) · P5.9
  Pending Work (stray-упоминание `plan-audit-loop.md` в
  `roadmap/plan-design-vs-exec-status-check.md:70`).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений: унификация парсеров `*.env.ini` (P5.3) · `codex plugin update`
  round-trip (P5.5) · DX-схема `upstream.schema.json` для `audit`/`kind` (P5.11) · снимок
  `test_committed_outputs…` от чужого mAInd-демона (P6.3, новое — `roadmap/provider-docs-snapshot-daemon-noise.md`)
  — все решением владельца/следующей содержательной правкой.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец
  протокола). Новых этим заходом не заведено.
