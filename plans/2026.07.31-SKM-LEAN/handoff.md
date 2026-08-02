# HANDOFF — 2026-08-02 — after P6.2

**Next:** закрыть фазу **P6** — все три её item'а терминальны (P6.3 🟠 · P6.1 🟠 · P6.2 🟠),
очередь фазы (D62) исчерпана; `Phase Handoff` пуст, `closure/P6.json` не написан

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — закрытие фазы по git-фактам, новых решений нет |
| Context | NEW SESSION — шаг-не-item |
| Суть | `plan-close` сводит фазу P6: `Phase Handoff`, `closure/P6.json` (Closure Protocol v1), статус фазы в §4 Status Board с 🟡 на 🟠 |
| Команда | `/task:plan-close 2026.07.31-SKM-LEAN P6` |

**Done:** **P6.2 закрыт 🟠 Done with deviations.** `.swissknife.json` читается frozen
dataclass'ом `ProjectConfig` (`packages/skiller/lib/skiller/config.py`, stdlib-only,
`collections.abc.Mapping` как read-only back-compat-проекция на `raw`), а **`CONFIG_KEYS`
выведён из полей объекта** через `field(metadata={"json_type": …})` и реэкспортируется из
`common.py` лениво (module `__getattr__`, PEP 562 — прямой импорт замкнул бы цикл
`common → config → common`; обе стороны цикла проверены прогоном). Носителей перечня ключей
снова три, а не четыре. Оба гейта синхрона со схемой не тронуты ни строкой: `skiller doctor`
на `~/projects/packages/botkit` печатает `[ok ]` и на «⇄ ключи», и на «⇄ типы», а полный
вывод `doctor` до/после различается ровно двумя строками окружения копии дерева (сверка
против `git archive d9bf22d9`). Замер потребителей (правило «список в `Files` — ожидание,
замер — истина»): **46** строк `config.get(`/`cfg.get(` в `packages/skiller/lib` (на
`d9bf22d9`), из них на конфиге ПРОЕКТА — **24** в шести модулях; после правки — **4**, и все
четыре внутри `validate_config`, который по построению работает с сырым JSON до сборки
объекта; **22** чтения переведены на атрибуты (на `c01270af`). Мутации конфига после
загрузки в пакете нет ни одной (греп — 0 строк), поэтому if-then-эскалация ТЗ не сработала.
Приёмка: `skiller test.sh` → `Ran 622 tests` (было 602: +20 новых в
`tests/test_config_object.py`), `validate.sh` → exit 0, `docs-impact --staged` → OK, смежные
раннеры зелены (harness 637 · maind 545 · `task validate: OK`). Регресс back-compat снят на
СИНТЕТИЧЕСКОЙ фикстуре (в корне репо `.swissknife.json` нет): временный проект с файлом на
все 13 ключей, обе формы `memory_brain` — `skiller status` и `skiller budget --first-turn`
дают вывод, **побайтово совпадающий** с прогоном до правки (4/4 `cmp -s`). Item-коммит
`c01270af` (9 файлов, +400/−58). **Known Deviations:** (1) Validation (7) `ruff` красна —
3 находки, набор ИДЕНТИЧЕН пред-существующему (сверка на `d9bf22d9` и `c01270af`), новых от
диффа — 0, в рамках Scope не чинятся; (2) Scope Included выполнен не полностью — четыре
потребителя `load_config` ВНЕ `Files` оставлены на Mapping-поверхности, чтобы item-коммит не
нёс дифф вне `Files`; (3) ТЗ говорит «14 ключей `CONFIG_KEYS`», факт — **13** (замер на
`d9bf22d9`); (4) перебор тира — исполнено `opus/high` при предписанном `implementation/high`.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
P5 6/11 (🟠 Done with deviations, терминальна) · **P6 0/3 (🟡 In progress в §4 Status Board;
ВСЕ три items терминальны 🟠 — статус фазы поднимает `plan-close`)** · P7 0/4 (⬜, скелет).
Не все фазы плана терминальны — `plans/ACTIVE.md` и `Status` плана не трогаются.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P6.md` (`## Phase Status`, P6.2
Completion Notes) · `plan.md` §4 Status Board, §6 Update Log, `## 0. Meta` Last Updated ·
`packages/skiller/lib/skiller/config.py` (`ProjectConfig`, производный `CONFIG_KEYS`) ·
`packages/skiller/lib/skiller/common.py` (ленивый реэкспорт имени) ·
`packages/skiller/tests/test_config_object.py` · `packages/skiller/docs/guide/installation.md`
(раздел «Носитель конфига внутри skiller»).

**Open risks:**

- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый
  `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`. `git add -A`
  запрещён — эти файлы вне `Files` items фазы P6.
- **`ruff` несёт пред-существующие ошибки** (5 по репозиторию, из них 3 на путях skiller:
  `packages/skiller/lib/skiller/publication.py:1037` B904,
  `packages/skiller/tests/test_budget_listing_providers.py:24` F401,
  `packages/skiller/tests/test_status.py:17` F401): новых от диффа P6.2 — ноль, но приёмка
  «ruff чисто» у следующих items плана красна не по их вине.
- **`verify-citations --strict` несёт пред-существующие находки** (протухшие цитаты фаз
  P2/P3/P5 и `plan.md`): гейт цитат красен НЕ по вине P6.2 (диффа цитат этот item не даёт).
- **`scripts/test-provider-docs.py` несёт 1 известный FAIL** (`test_committed_outputs…`,
  средо-зависимая хрупкость снимка всего дерева — чужой mAInd-демон) — адресован
  `roadmap/provider-docs-snapshot-daemon-noise.md`.
- **`skiller doctor` держит пред-существующий `[FAIL] хабы проектов свежие`** (18 проектов
  флота отстали от реестра) — воспроизведён и на `d9bf22d9`, к P6.2 отношения не имеет.
- **Типизация не сплошная:** `integrate.py`, `hub.py`, `quality/analyze.py`,
  `quality/audit.py` читают конфиг через Mapping-проекцию (поведение идентично) — их перевод
  на атрибуты в Pending Work P6.2; пока проекция жива, соблазн «оставить dict-доступ навсегда»
  реален.
- Прежние (не изменились): ветка (C) OQ-6 не проверена данными (usage не мерялся) ·
  U1/U2 `[UNVERIFIED]`, остаток риска D106, контракт P4.1 пинован на `06fefc87` ·
  окружной дефект `codex exec -s read-only` (bwrap/AppArmor) · P5.3 Pending Work (унификация
  четырёх парсеров `*.env.ini`) · P5.5 Pending Work (`codex plugin update` без теста) ·
  P5.9 Pending Work (stray-упоминание `plan-audit-loop.md` в
  `roadmap/plan-design-vs-exec-status-check.md:70`).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений по составу: унификация парсеров `*.env.ini` (P5.3) ·
  `codex plugin update` round-trip (P5.5) · DX-схема `upstream.schema.json` для `audit`/`kind`
  (P5.11) · снимок `test_committed_outputs…` от чужого mAInd-демона (P6.3) · 5 ошибок `ruff`
  и находки гейта цитат (P6.1) — все решением владельца/следующей содержательной правкой.
  Новое P6.2: типизация `.swissknifeman/config.json` (`SKILLSET_KEYS`) — соседний носитель,
  объявлен Scope Excluded item'а.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец
  протокола). Новых этим заходом не заведено.
