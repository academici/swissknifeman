# HANDOFF — 2026-08-02 — after P6.1

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — исполнить последний item фазы P6 — **P6.2** (очередь фазы
`P6.3 → P6.1 → P6.2` исчерпана этим шагом, D62)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — `implementation/high` по §3 Routing plan.md, триггер §9 «инварианты»: `CONFIG_KEYS` не должен получить ЧЕТВЁРТЫЙ носитель, а `.swissknife.json` лежит в репозиториях флота (back-compat) |
| Context | continue (/clear) — ручной item |
| Суть | `ProjectConfig` — frozen dataclass stdlib-only для `.swissknife.json` в `packages/skiller/lib/skiller/config.py`, с выводом `CONFIG_KEYS` из полей объекта при НЕИЗМЕННЫХ гейтах `doctor`/`test_schema`; `core/` не трогается ни строкой (D48) |
| Команда | `—` (нет single-command эквивалента — `Exec = manual`) |

```
/model opus
/effort high
/task:plan-run 2026.07.31-SKM-LEAN P6.2
```

**Done:** **P6.1 закрыт 🟠 Done with deviations.** Шесть provider-модулей переехали
`git mv` в `core/provider/` со снятием префикса (`values`/`config`/`manifest`/`artifact`/
`lock`/`registry`), семь тестов — в `core/tests/provider/` с обязательным `__init__.py`
(все 13 файлов видны в `git status` как `R` — `git log --follow` сохранён). Публичный
контракт неизменен: `len(core.__all__)` = **108** (на `d92f3998`), а сортированный перечень
имён, снятый ДО и ПОСЛЕ, сравнён ФАЙЛАМИ — `diff` пуст; блок `__all__` не тронут, изменены
ровно 6 строк импорта фасада. Строгая приёмка (D62): `Ran 251 tests`, `OK` — число тестов не
уменьшилось, провалов ноль. Приёмочный греп `core\.provider_[a-z]` (тот же, которым велась
инвентаризация — D69) даёт **0 строк**, `core\.tests\.test_provider` — **0**; в счёт вошли и
два комментария-упоминания в `harness/instructions.py`. Три якоря `parents[2]` → `parents[3]`.
Единственная связь кластера с плоским остатком поднята на `from ..paths import` в
`core/provider/lock.py`; циклического импорта не возникло. Все четыре пакетных раннера зелены
(skiller 602 · harness 637 · maind 545 · `task validate: OK`), `harness validate.sh` зелен,
`docs-impact --staged` → `OK` без escape-трейлера. §5а (ДЕЛЬТОВАЯ, D70): состав провалов
`scripts/test-provider-docs.py` НЕ изменился — `Ran 5`, тот же единственный средо-зависимый
`test_committed_outputs…`, релевантный `test_independent_exact_set…` зелен. `docs/core/index.md`
впервые описывает кластер (строка `provider/` + подраздел на шесть модулей). Item-коммит
`d92f3998` (29 файлов, +96/−63). **Known Deviations:** (1) дифф вне `Files` — одна строка
`scripts/test-provider-docs.py:19`: загрузчик единственного носителя хешей (заведён P6.3
2026-08-02, уже ПОСЛЕ авторинга ТЗ P6.1) грузит его ПО ПУТИ, приёмочный греп такого сайта не
видит; без правки §5а недостижима по построению; (2) дифф вне `Files` в bookkeeping —
две записи в `plans/verify-citations-known-exceptions.json` (датированные цитаты о замере на
`ebd42655`, переписывать путь в записи о прошлом запрещено); (3) перебор тира — исполнено
`opus/high` при предписанном `implementation/high`.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
P5 6/11 (🟠 Done with deviations, терминальна) · **P6 0/3 (🟡 In progress; P6.3 и P6.1
терминальны 🟠, остался P6.2)** · P7 0/4 (⬜, скелет). Не все фазы плана терминальны —
`plans/ACTIVE.md` и `Status` плана не трогаются.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P6.md` (`## Phase Status`, P6.1
Completion Notes) · `plan.md` §4 Status Board, §6 Update Log · `core/provider/` и
`core/tests/provider/` (новая раскладка) · `docs/core/index.md` (описание кластера) ·
`plans/verify-citations-known-exceptions.json` (две новые записи).

**Open risks:**

- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый
  `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`. `git add -A`
  запрещён — эти файлы вне `Files` items фазы P6.
- **`ruff` несёт 5 пред-существующих ошибок** (те же на `d92f3998^` — `harness/execpolicy.py:11`,
  `harness/tests/test_exec_policy.py:14`, `skiller/publication.py:1037`,
  `skiller/tests/test_budget_listing_providers.py:24`, `skiller/tests/test_status.py:17`):
  новых от диффа P6.1 — ноль, но приёмка «ruff чисто» у следующих items плана красна не по их вине.
- **`verify-citations --strict` несёт 11 пред-существующих находок** (протухшие цитаты фаз
  P2/P3/P5 и `plan.md:242`): гейт цитат красен НЕ по вине P6.1 (новых от диффа — ноль, две
  порождённые переездом закрыты записями исключений).
- **`scripts/test-provider-docs.py` несёт 1 известный FAIL** (`test_committed_outputs…`,
  средо-зависимая хрупкость снимка всего дерева — чужой mAInd-демон) — адресован
  `roadmap/provider-docs-snapshot-daemon-noise.md`; после P6.1 состав провалов не изменился.
- **P6.2 — риск-класс «инварианты»:** `CONFIG_KEYS` обязан ВЫВОДИТЬСЯ из полей `ProjectConfig`
  (второй/четвёртый носитель запрещён), гейты `doctor`/`test_schema` не правятся; `Exec = manual`,
  effort high обязателен — запуск ТОЛЬКО `/task:plan-run` (не `/task:plan-exec`, который пинит
  sonnet/medium и по гейту Routing обязан такой item отклонить).
- Прежние (не изменились): ветка (C) OQ-6 не проверена данными (usage не мерялся) ·
  U1/U2 `[UNVERIFIED]`, остаток риска D106, контракт P4.1 пинован на `06fefc87` ·
  окружной дефект `codex exec -s read-only` (bwrap/AppArmor) · P5.3 Pending Work (унификация
  четырёх парсеров `*.env.ini`) · P5.5 Pending Work (`codex plugin update` без теста) · P5.9
  Pending Work (stray-упоминание `plan-audit-loop.md` в
  `roadmap/plan-design-vs-exec-status-check.md:70`).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений по составу: унификация парсеров `*.env.ini` (P5.3) ·
  `codex plugin update` round-trip (P5.5) · DX-схема `upstream.schema.json` для `audit`/`kind`
  (P5.11) · снимок `test_committed_outputs…` от чужого mAInd-демона (P6.3) — все решением
  владельца/следующей содержательной правкой. Новое P6.1: 5 ошибок `ruff` и 11 находок гейта
  цитат — пред-существующий плановый долг без адреса внутри фазы P6.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец
  протокола). Новых этим заходом не заведено.
