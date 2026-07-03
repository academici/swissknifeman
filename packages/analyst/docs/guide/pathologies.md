# Каталог патологий воркфлоу

Прогон Claude Code может «работать», но плохо: гонять по кругу один и тот же файл, накручивать
haiku-агента мышлением вместо текста, тихо раздувать scope, править сгенерированный файл, который
следующий sync затрёт. Это каталог таких паттернов — **workflow pathologies** — с детектором (если
он есть), формулой/порогом, severity и конкретным remediation.

Источник истины кодов/формул/порогов/severity — **[`core/pathology.py`](https://github.com/academici/swissknifeman/blob/main/core/pathology.py)**
(чистая `detect(run_report) -> [finding]`, без I/O и часов, никогда не бросает). Этот документ —
его русскоязычная витрина + маппинг на минимальный список классов «Workflow Pathology Catalog»
(§12 чернового мастер-плана — локальный design-документ, не трекнутый в репо, отсюда без пути/ссылки).
Пороги — **эвристики, НЕ откалиброванные** по полевому false-positive-rate (тот же принцип, что и
[Тюнинг-параметры](./tuning) `analyst`): значения подобраны по форме сигнала, меняются только в
модуле-источнике.

## Слои

```
harness-хук (SessionEnd)        core/pathology.py              потребители маршрутизируют
run-report SCHEMA=2       ──▶   detect(run_report)       ──▶   maind analyze  — attention → reasons
(usage/reads/error_loops/                                                       (вердикт ATTENTION);
 retrieval/protected_writes)                                                    info → секция «Эффективность»
                                                                 analyst digest — рецидив ≥2 из 5
                                                                   последних сессий → кандидат-урок
```

Хук **собирает** сырые срезы прогона (тул-вызовы, чтения, error-серии, retrieval, protected-writes,
usage-токены) в `<project>/.claude/runs/<sid>.json`. `pathology.detect()` **оценивает** этот срез
детекторами ниже и отдаёт плоский список находок — сам ничего никуда не пишет и не решает. Дальше
находки **маршрутизируют** потребители: `maind analyze` — в вердикт текущего прогона (read-only
разбор «всё ли сработало»), `analyst digest` — в кандидат-урок, если патология не разовая (см.
«Правило рецидива» ниже). Один и тот же чистый список находок — на входе у обоих.

Оба подключения реализованы и покрыты тестами (план SKM-MASTER-002, фаза P3, items P3.1–P3.3):

- **`maind analyze`** (`packages/maind/lib/maind/analyze.py`, `pathology_slice()`) раскладывает
  находки по severity: `attention` уходит **строками evidence** (без кода) в `reasons` вердикта
  через `compute_verdict(..., pathology_attention=...)` — попадает туда же, куда pack-drift/грязное
  дерево/токен-аномалии; `info` уходит в `rep["efficiency"]` и печатается в человеко-читаемом выводе
  отдельным блоком `code: evidence` под заголовком **«Эффективность»**. Импорт `core.pathology`
  безусловный — как и остальные `from core import ...` в `maind`/`analyst`/`harness` (ни один не
  обёрнут в `try/except ImportError`; деградация «core/ не на PYTHONPATH» — забота лаунчера/
  `validate.sh`, не каждого импорта по месту). Формально расходится с буквальной формулировкой Code
  Guidance item P3.2 («импорт с ImportError-фолбэком»), но следует фактической репо-конвенции.
- **`analyst digest`** (`packages/analyst/lib/analyst/digest.py`, `extract_pathologies()`) прогоняет
  `detect()` по последним `PATHOLOGY_WINDOW=5` run-report'ам проекта (читает их напрямую с диска
  `<project>/.claude/runs/*.json`, не через тренд-файл) и создаёт кандидат-урок, только если код
  находки **рецидивировал** (см. ниже) — единственный извлекатель digest, которому для этого нужен
  реальный путь проекта, а не только текущий `run_report` (осознанное исключение из «извлекатели —
  чистые функции», см. docstring модуля).

## Detect ≠ Gate

Обнаружение патологии — не то же самое, что блокировка. `severity` в находке — только `info` или
`attention`, никакого `critical`/`fail`: пороги не откалиброваны, а значит не заслуживают доверия
уровня «стоп прогона». Разделение по месту в отчёте `maind analyze`:

| Severity | Что означает | Куда идёт в `maind analyze` |
|:--|:--|:--|
| `info` | слабый сигнал — посмотреть при плановом разборе, действие не обязательно | секция **«Эффективность»** (не влияет на вердикт) |
| `attention` | вероятная патология — стоит разобрать | список **reasons** → вердикт **ATTENTION** |
| — | **RED невозможен от патологий ни при каком количестве находок** | RED — только упавший тест/линт/воркфлоу (см. `compute_verdict` в `analyze.py`) |

Это прямое следствие принципа мастер-плана §5 «Detect ≠ Gate» и решения D9 плана SKM-MASTER-002:
RED зарезервирован за объективно упавшей проверкой, не за эвристикой. Даже десять
`attention`-находок в одном прогоне не поднимут вердикт выше ATTENTION.

## Правило рецидива ≥2 из 5 (для уроков)

Один прогон с находкой — сигнал для *этого* прогона (`maind analyze`), не повод сразу писать урок:
разовая патология — шум, а `analyst` учит только устойчивому. `analyst digest`
(`extract_pathologies()` в `digest.py`) берёт кандидат-урок из патологии, только если **тот же код**
находки встретился минимум в `PATHOLOGY_MIN_HITS=2` из **последних `PATHOLOGY_WINDOW=5`**
run-report'ов проекта (текущий прогон входит в окно; история — файлы `.claude/runs/*.json`,
свежие по mtime первыми, без нового state-файла). Рецидив считается по `code` находки
(`file-reread`, `protected-write`, …), а не по тексту `evidence` — иначе два прогона с разными
числами никогда не схлопнутся в один паттерн. Тест «разовая патология НЕ создаёт урок»
(`test_single_occurrence_out_of_five_no_lesson` в `test_digest.py`) — часть приёмки item P3.3. Это
тот же анти-шумовой инстинкт, что и человеко-гейт curated: `digest` не угадывает инсайт по одному
наблюдению.

**Второй фильтр, отдельный от рецидива: не любой код рецидива становится уроком.** `digest` ведёт
явный словарь `_PATHOLOGY_REMEDIATIONS` — только код с ГОТОВЫМ конкретным действием попадает в
конвейер урока, даже при устойчивом рецидиве. На 2026-07-02 в словаре **4 кода**:

| Код | Класс §12 | Буквальный `action` кандидат-урока |
|:--|:--|:--|
| `file-reread` | 4. repeated file rereads | «держи карту прочитанного; для повторного обращения используй заметки/план, не re-read» |
| `tool-error-loop` | вне §12 (доп. детектор) | «после 2 одинаковых отказов инструмента меняй подход, не долби» |
| `protected-write` | 8. protected asset mutation attempts | «generated-файлы паков не редактируй — оверрайды в `.claude/rules/*-overrides.md`» |
| `no-verify` | 10. missing acceptance boundaries | «изменил код — прогони тесты до завершения сессии» |

Остальные коды (`no-op-run`, `overthinking`, `cache-miss`, `retrieval-stuffing`, `static-context`,
`fanout`, `no-verify-devloop`) — **сигналы только для `maind analyze`** (reasons/«Эффективность»),
в `analyst digest` не участвуют даже при устойчивом рецидиве: «нет конкретного что делать — учить
агента нечему» (докстринг `digest.py`). Тест на этот фильтр —
`test_code_without_remediation_stays_signal_even_if_recurring` (5 из 5 срабатываний `no-op-run` всё
равно не создают урок).

## Каталог: 10 классов из §12

Порядок и формулировки классов — как в черновике мастер-плана. «Статус детектируемости»:
**детектируется сейчас** (детектор есть и покрывает класс) / **частично** (детектор есть, но ловит
только симптом или подмножество) / **НЕ детектируемо детерминированно** (детектора нет — указано,
какого добора данных не хватает). Колонка «→ digest» — участвует ли код в правиле рецидива (см. выше):
**да** (в `_PATHOLOGY_REMEDIATIONS`) / **нет** (только `maind analyze`) / **—** (детектора нет).

| # | Класс (§12) | Код(ы) | Severity | → digest | Статус |
|:-:|:--|:--|:--|:-:|:--|
| 1 | repeated re-planning | нет | — | — | НЕ детектируемо — счётчик повторов TodoWrite (фаза 2) |
| 2 | no-op execution | `no-op-run` | info | нет | детектируется сейчас |
| 3 | overthinking on cheap agents | `overthinking` | info | нет | детектируется сейчас |
| 4 | repeated file rereads | `file-reread` | attention | да | детектируется сейчас |
| 5 | hidden scope expansion | нет | — | — | НЕ детектируемо — declared-scope из plans/-протокола |
| 6 | stack-pack ↔ project type mismatch | нет | — | — | НЕ детектируемо здесь — `harness agent-packs doctor` |
| 7 | invalid handoff after context reset | нет | — | — | НЕ детектируемо — кросс-ран корреляция |
| 8 | protected asset mutation attempts | `protected-write` | attention | да | детектируется сейчас |
| 9 | prompt bloat from overlapping rules | `static-context` | info | нет | частично (симптом, не причина) |
| 10 | missing acceptance boundaries | `no-verify` / `no-verify-devloop` | attention / info | да / нет | частично (прокси отсутствия verify) |

### 1. repeated re-planning

**Детектор:** нет. **Формула/порог:** нет. **Severity:** —.

**Remediation:** сузить task item по plan-protocol (`task:plan-*`/`general/spec-interview`) до одной
атомарной цели ДО старта исполнения. Повторное перепланирование — повод для явной эскалации по
`plan-protocol §8` («план разошёлся с кодом — не импровизировать»), а не для тихой подмены плана.
Причину ре-планирования фиксировать в Decision Log плана, а не терять её между заходами.

**Статус: НЕ детектируемо детерминированно.** Добор данных: счётчик повторов `TodoWrite` с одним и
тем же shape/целью между вызовами инструмента (фаза 2 — нужен отдельный лог TodoWrite-вызовов в
хуке, которого сейчас нет в run-report SCHEMA=2; `pathology.py` видит только агрегаты прогона, а не
последовательность правок плана внутри него).

### 2. no-op execution

**Детектор:** `no-op-run`. **Формула:** `tools.total ≥ NOOP_MIN_TOOLS(20)` и `files_changed=[]` и
`bash.tests=[]` и `retrieval.calls==0`. **Severity:** `info`.

**Remediation:** если это была намеренная read-only разведка — сигнал не требует действия (потому и
`info`, не `attention`). Если задача подразумевала правку — проверить, не потерялся ли план/scope
между тул-вызовами (см. `session-handoff`), не зациклилась ли модель на чтении без записи.

**Статус: детектируется сейчас** (→ `maind analyze`, секция «Эффективность»). **→ digest: нет** —
нет записи в `_PATHOLOGY_REMEDIATIONS`, урок не создаётся даже при устойчивом рецидиве (нет
конкретного действия, которому можно научить).

### 3. overthinking on cheap agents

**Детектор:** `overthinking`. **Формула:** субагент с `model` содержащим `haiku`;
`thinking_chars / (thinking_chars + text_chars) > OVERTHINKING_RATIO(0.6)`. **Severity:** `info`.

**Remediation:** пересмотреть model routing для этого шага — задача, похоже, не под haiku-тир
(поднять до sonnet) либо промпт для дешёвой модели не сужен до чек-листа. Проверить, не течёт ли в
дешёвого субагента открытый reasoning вместо конкретной инструкции (см. `Reasoning policy` мастер-плана §4).

**Статус: детектируется сейчас** (→ `maind analyze`, секция «Эффективность»). **→ digest: нет** —
как и `no-op-run`, кода нет в `_PATHOLOGY_REMEDIATIONS`.

### 4. repeated file rereads

**Детектор:** `file-reread`. **Формула:** `total ≥ REREAD_MIN_TOTAL(10)`;
`(total − unique) / total > REREAD_RATIO_MAX(0.4)`. **Severity:** `attention`.

**Remediation:** повторные чтения одного файла — контекст не удерживается между шагами. Свести к
одному `Read` и работе in-memory; для символьного/структурного поиска использовать код-граф
(Serena) вместо повторного `grep`/`Read`; если рвётся при context-reset — проверить полноту
handoff-артефакта (класс 7).

**Статус: детектируется сейчас** (→ `maind analyze`, вердикт ATTENTION). **→ digest: да** — при
рецидиве ≥2/5 `analyst digest` создаёт урок буквально с action «держи карту прочитанного; для
повторного обращения используй заметки/план, не re-read» (см. «Правило рецидива» выше).

### 5. hidden scope expansion

**Детектор:** нет. **Формула/порог:** нет. **Severity:** —.

**Remediation:** заявлять scope явно в плане/task item (`Scope Included`/`Scope Excluded`) ДО старта
исполнения. Расширение diff'а за пределы заявленного — повод для явной эскалации, не для молчаливого
«заодно поправил и это».

**Статус: НЕ детектируемо детерминированно.** Добор данных: declared-scope из plans/-протокола —
нужен список заявленных путей/файлов task item как эталон, чтобы сравнить с фактическим
`files_changed` run-report'а. `core/pathology.py` видит только ЧТО реально изменено за прогон, без
эталона «что было заявлено» — сравнивать не с чем.

### 6. mismatch between stack-pack and project type

**Детектор:** нет (не в run-телеметрии). **Формула/порог:** нет. **Severity:** —.

**Remediation:** `harness agent-packs doctor` (или `harness doctor`) — сверка пака с типом проекта
на этапе provisioning/sync. Для Laravel-пакетов (не app) — целевое решение отдельного пака
`laravel-package` (мастер-план §14, план SKM-MASTER-002 фаза P6/F).

**Статус: НЕ детектируемо здесь.** Это статическая диагностика конфигурации проекта на этапе
установки/синка стек-пака, не сигнал одного прогона — живёт в `harness agent-packs doctor`, не в
`core/pathology.py`: пороги/детекторы этого файла оперируют только run-report'ом сессии.

### 7. invalid handoff after context reset

**Детектор:** нет. **Формула/порог:** нет. **Severity:** —.

**Remediation:** валидировать handoff-артефакт (мастер-план §8/P4 «Context Reset Handoff Standard»)
на минимальную достаточность ДО старта следующей сессии; зафиксировать явный acceptance-шаг «handoff
читаем и соответствует текущему состоянию плана».

**Статус: НЕ детектируемо детерминированно.** Добор данных: кросс-ран корреляция — нужно
сопоставить handoff-артефакт ПРЕДЫДУЩЕГО прогона с фактическим стартовым состоянием СЛЕДУЮЩЕГО.
`core/pathology.py detect()` видит один run-report за раз (без памяти о соседней сессии) — это в
принципе другая форма входа, не одна патология внутри отчёта.

### 8. protected asset mutation attempts

**Детектор:** `protected-write`. **Формула:** `len(protected_writes) > 0` (порог 0 — любая непустая
запись). **Severity:** `attention` (всегда, независимо от объёма).

**Remediation:** правку в managed-пути (vendor-скиллы/generated-файлы agent-pack) переносить в
override/extension-зону (base+overlay, мастер-план §13/P9, решение D11) и восстановить
сгенерированный файл (`harness agent-packs render`). Сгенерированные файлы руками не редактируются
никогда — их перезатрёт следующий `sync`.

**Статус: детектируется сейчас** (→ `maind analyze`, вердикт ATTENTION). **→ digest: да** — при
рецидиве ≥2/5 action урока буквально «generated-файлы паков не редактируй — оверрайды в
`.claude/rules/*-overrides.md`».

### 9. prompt bloat from overlapping rules

**Детектор:** `static-context` (частично). **Формула:** для агента `label=="main"` (fallback —
первый агент usage-среза), при `msgs ≥ STATIC_MIN_MSGS(3)`: `avg_in = (in + cache_read) / msgs`;
`share = avg_in / CONTEXT_WINDOW_TOKENS(200_000) > STATIC_WINDOW_SHARE(0.7)` **и**
`tools.total < STATIC_MAX_TOOLS(15)`. **Severity:** `info`.

**Remediation:** ревизия резидентных бакетов/MCP-выдачи (`skiller budget`); убрать пересечения
правил между bucket'ами/stack-pack'ами/project overrides (мастер-план §11/P7 bucket-audit); перевести
редко нужные правила из always-on в on-demand retrieval.

**Статус: частично** (симптом, не причина; → `maind analyze`, секция «Эффективность»). `static-context`
детектирует СИМПТОМ — раздутый резидентный вход при малом объёме тул-работы (жирные бакеты/MCP-выдача
давят на каждый вызов), но не ПРИЧИНУ. Атрибуция «какие именно правила/бакеты пересекаются» требует
статического P7 bucket-audit (инвентаризация overlap bucket↔stack-pack↔override, §11), а не
run-телеметрии одного прогона. **→ digest: нет** — кода нет в `_PATHOLOGY_REMEDIATIONS`.

### 10. missing acceptance boundaries

**Детекторы:** `no-verify` (правки без проверки) и `no-verify-devloop` (dev-loop без итога).
**Формулы:** `no-verify`: `files_changed` непусто и `bash.tests == []` → `attention` (порог 0).
`no-verify-devloop`: `devloop` присутствует (непустой dict), но без ключей `verify`/`results` →
`info` (порог 0). **Severity:** `attention` / `info` соответственно.

**Remediation:** зафиксировать acceptance-критерии/Definition of Done в плане ДО исполнения
(`general/task-brief-template`, `plan-protocol §7 Reporting Schema`); прогнать `validate.sh`/тесты
перед завершением среза; dev-loop обязан писать `verify`/`results`, а не оставлять итог среза
незафиксированным.

**Статус: частично** (прокси отсутствия verify; → `maind analyze` для обоих кодов). Детекторы ловят
ОТСУТСТВИЕ verify-следа как прокси отсутствия границ приёмки (правки без прогона проверки, или срез
без записанного итога), но не проверяют, были ли acceptance-критерии вообще СФОРМУЛИРОВАНЫ в плане
до старта — тот же добор, что у класса 5: нужен эталон «что должно было быть проверено» из
plans/-протокола, а не только факт отсутствия прогона. **→ digest:** только `no-verify` (`attention`)
— да, action буквально «изменил код — прогони тесты до завершения сессии» при рецидиве ≥2/5;
`no-verify-devloop` (`info`) в `_PATHOLOGY_REMEDIATIONS` не входит — нет.

## Детекторы вне минимального списка §12

`core/pathology.py` реализует больше детекторов, чем минимальный список §12 (индустриальные
эвристики LLM-agent observability — см. [docs/reference.md](/reference)). Для полноты SSOT — они
здесь же, без привязки к конкретному классу черновика:

| Код | Что ловит | Формула/порог | Severity | → digest |
|:--|:--|:--|:--|:-:|
| `tool-error-loop` | серия однотипных ошибок одного инструмента подряд — retry без смены подхода | `len(loop) ≥ ERROR_LOOP_INFO_LEN(3)` → info; `≥ ERROR_LOOP_ATTENTION_LEN(5)` → attention | info/attention | **да** — рецидив ≥2/5 → action «после 2 одинаковых отказов инструмента меняй подход, не долби» |
| `cache-miss` | низкая доля кэш-чтений при большом входе — нестабильный системный промпт рвёт prompt-cache | `cache_hit < CACHE_HIT_LOW(0.4)` и объём входа `> CACHE_MISS_MIN_TOKENS(200_000)` ток | info | нет |
| `retrieval-stuffing` | retrieval-выдача занимает заметную долю входа — сырьё льют в контекст вместо синтеза | `retrieval_tokens/in > RETRIEVAL_IN_SHARE(0.25)`; `attention` при `repeated_queries ≥ RETRIEVAL_REPEATED_MIN(2)` | info/attention | нет |
| `fanout` | широкий fan-out субагентов при скромном выхлопе по файлам | `agents > FANOUT_MIN_AGENTS(8)` и `files_changed < FANOUT_MAX_FILES(5)` | info | нет |

`tool-error-loop` — единственный из «внесписочных» детекторов с готовой ремедиацией в
`_PATHOLOGY_REMEDIATIONS`: хотя он не входит в минимальный список §12 (ближе всего по духу к классу 1
«repeated re-planning» — оба про застревание без смены подхода, но `tool-error-loop` — про инструмент
внутри ОДНОГО прогона, а не про план между прогонами), при рецидиве он тоже становится кандидат-уроком.

## См. также

- [`core/pathology.py`](https://github.com/academici/swissknifeman/blob/main/core/pathology.py) —
  код детекторов (SSOT формул/порогов/severity).
- [`packages/maind/lib/maind/analyze.py`](https://github.com/academici/swissknifeman/blob/main/packages/maind/lib/maind/analyze.py)
  (`pathology_slice`) · [`packages/analyst/lib/analyst/digest.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/digest.py)
  (`extract_pathologies`, `_PATHOLOGY_REMEDIATIONS`) — маршрутизация находок в вердикт/уроки.
- [Тюнинг-параметры](./tuning) — тот же принцип «менять порог только в модуле-источнике», для
  confidence-арифметики `analyst`.
- [CLI и команды](./cli) · [Жизненный цикл урока](./lifecycle) — куда приземляется кандидат-урок из
  рецидивирующей патологии после `digest`.
- `plans/SKM-MASTER-002/phases/P3.md` — фаза, вводящая каталог патологий (items P3.1–P3.4).
