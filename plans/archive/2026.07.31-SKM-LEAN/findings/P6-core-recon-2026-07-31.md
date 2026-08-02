# P6 — разведка `core/` и поверхности конфига (слой 1)

**Дата:** 2026-07-31 · **Способ:** живой замер репозитория на `HEAD = ebd42655`
(`git log --oneline -1`), команды приведены при каждом числе. Класс фактов —
**repo-grounded** (внешних фактов один: поведение `unittest discover` на подкаталогах —
он снят ЭКСПЕРИМЕНТОМ на живом Python 3.12.3, см. §6, а не взят из документации).

Назначение: вход для детализации фазы P6. Все числа `findings/repo-recon-2026-07-31.md` §3
здесь перепроверены — **два из них разошлись с деревом** (§1).

---

## 1. Инвентарь `core/` и расхождение с прежним recon

`ls -l core/*.py`:

| Файл | Байт | Кластер |
|:--|--:|:--|
| `provider_lock.py` | 68 070 | provider |
| `provider_manifest.py` | 27 170 | provider |
| `provider_artifact.py` | 17 994 | provider |
| `provider_config.py` | 11 445 | provider |
| `provider_registry.py` | 11 441 | provider |
| `provider.py` | 8 686 | provider |
| `pathology.py` | 16 729 | — |
| `usage.py` | 10 496 | — |
| `io.py` | 9 410 | — |
| `__init__.py` | 7 066 | фасад |
| `project.py` | 6 669 | — |
| `runs.py` | 6 215 | — |
| `text.py` | 5 605 | — |
| `cli.py` | 4 795 | — |
| `repo.py` | 4 212 | — |
| `http.py` | 3 337 | — |
| `paths.py` | 2 371 | — |
| `block.py` | 2 288 | — |
| `term.py` | 1 982 | — |
| `env.py` | 1 799 | — |
| `proc.py` | 1 123 | — |

Итого **21 файл** (20 модулей + `__init__.py`).

**Расхождение с `findings/repo-recon-2026-07-31.md` §3 (исправляется здесь):**

| Утверждение recon §3 | Факт на `ebd42655` | Команда |
|:--|:--|:--|
| «кластер `provider_*` — **7 файлов**» | **6 файлов** | `ls core/provider*.py \| wc -l` → `6` |
| «**152 КБ**» | **144 806 байт = 141,4 KiB** | `ls -l core/provider*.py \| awk '{s+=$5} END {print s}'` |
| «зеркало `core/tests/` — 12 из 20» | **13 тест-файлов** в `core/tests/` | `ls core/tests/*.py \| wc -l` → `13` |
| «38/38 `@dataclass(frozen=True)`» | подтверждено | `grep -c "@dataclass" core/*.py` / `grep -c "frozen=True"` |

Расхождение не меняет ни одного вердикта фазы, но числа в ТЗ берутся ОТСЮДА: ТЗ, стоящее
на «7 файлов, 152 КБ», отправило бы исполнителя искать седьмой файл.

`core/tests/` — 13 файлов: `test_core.py`, `test_io.py`, `test_pathology.py`, `test_runs.py`,
`test_text.py`, `test_usage.py` (6 не-provider) + `test_provider.py`,
`test_provider_artifact.py`, `test_provider_artifact_e2e.py`, `test_provider_config.py`,
`test_provider_lock.py`, `test_provider_manifest.py`, `test_provider_registry.py`
(**7 provider**). `__init__.py` в `core/tests/` **нет** (namespace-пакет).

## 2. Фасад `core/__init__.py` — публичный контракт

- 16 строк `from .<mod> import …` (`:16–62`), `__all__` — **108 имён** (`:64–102`,
  `PYTHONPATH=. python3 -c "import core; print(len(core.__all__))"` → `108`; дублей нет —
  `len(set(core.__all__))` = `108`).
  > **Исправлено 2026-07-31 (D68, находка аудита F1).** В первой редакции этого файла было
  > напечатано `110` вместе с той же командой — прогон на `ebd42655` даёт `108`. Число ушло
  > из слоя 1 в слой 2 и в ТЗ P6.1, где стало недостижимым приёмочным критерием.
- Provider-кластер даёт 6 из 16 строк импорта: `.provider`, `.provider_config`,
  `.provider_manifest`, `.provider_artifact`, `.provider_lock`, `.provider_registry`.
- Внутренние импорты кластера (`grep -n "^from \." core/provider*.py`): `provider_registry`
  → provider/provider_artifact/provider_config; `provider_manifest` → provider/provider_config;
  `provider_config` → provider; `provider_lock` → provider_artifact/provider/**paths**;
  `provider_artifact` → provider. Единственная связь кластера с плоским остатком —
  `provider_lock` → `core/paths.py` (`is_within`, `is_within_lexical`).

## 3. Blast radius переезда provider-кластера (14 живых файлов)

Инвентаризация ведётся ТЕМ ЖЕ грепом, что и приёмка item'а P6.1 (D69 — расхождение двух
паттернов и было дефектом первой редакции):

`grep -rn "core\.provider_[a-z]" --include=*.py . | grep -v "plans/archive"` (+ отдельно
импортёры тест-фикстур `from core.tests.test_provider_config import …`):

| Файл | Что импортирует |
|:--|:--|
| `packages/harness/lib/harness/instructions.py` | `core.provider` · `core.provider_artifact` · `core.provider_lock` |
| `packages/task/lib/task/command_render.py` | `core.provider` · `core.provider_artifact` · `core.provider_lock` · `core.provider_manifest` |
| `packages/maind/lib/maind/provider_deploy.py` | `core.provider_lock` (`artifact_doctor`, `rollback_chained_bootstrap_transfer`) |
| `packages/skiller/lib/skiller/publication.py` | `core.provider_lock` (`LOCK_RELATIVE_PATH`) |
| `packages/harness/tests/test_instruction_adoption.py` | `core.provider_artifact` · `core.provider_lock` |
| `packages/harness/tests/test_provider_instructions.py` | `core.provider_artifact` · `core.provider_lock` |
| `packages/harness/tests/test_provider_profiles.py` | `core.provider_lock` |
| `packages/task/tests/test_codex_command_adapter.py` | `core.provider_lock` |
| `packages/maind/tests/test_provider_deploy.py` | `core.provider_lock` — строковая цель `patch("core.provider_lock._bootstrap_write_state", …)` на `:510`, не оператор `import` (добавлен 2026-07-31, D69) |
| `core/tests/test_provider_registry.py` | 6 deep-импортов кластера |
| `core/tests/test_provider_lock.py` | `import core.provider_lock as provider_lock` |
| `core/tests/test_provider_artifact_e2e.py` | `core.provider_lock` (×2) |
| `packages/maind/tests/test_config.py` | `from core.tests.test_provider_config import catalog, config` |
| `packages/skiller/tests/test_provider_config.py` | `from core.tests.test_provider_config import catalog, config, layer` |

**Всего живых файлов: 14** (9 вне `core/` + 3 в `core/tests/` + 2 импортёра тест-фикстур) —
счёт пере-снят 2026-07-31 приёмочным грепом (D69); прежнее «13 (8 + 3 + 2)» получено более
узким паттерном `^\s*\(from\|import\) core\.provider` и пропускало строковые цели `patch()`.
Ни одного deep-импорта кластера в `bin/**`, `scripts/**`: `scripts/provider-docs.py:16–18`
берёт provider-символы через **фасад** (`from core import ProviderId, …`) и отдельно
`from core.repo import resolve_plan_dir` — плоский модуль, переезда не касается.

Для сравнения: всего файлов вне `core/`, импортирующих `core` любым способом — **88**;
deep-импортов (`core.<mod>`) — 55 строк в 38 файлах, из них provider-кластер — 24 строки
ИМПОРТ-ОПЕРАТОРОВ в 11 файлах; сверх них приёмочный греп находит строковые цели (`patch("core.provider_lock…")`)
и отдельно существуют 2 импортёра тест-фикстур — итого 14 живых файлов таблицы выше (D69). Остальные 31 строка — `core.repo`/`core.http`/`core.runs`/`core.term`/`core.io`/
`core.usage`/`core.pathology`/`core.cli`/`core.block`, т.е. плоский остаток, которого переезд
кластера НЕ касается.

**Исторические носители, где `core.provider_*` упоминается и которые переписывать НЕЛЬЗЯ:**
`CHANGELOG.md`, `docs/rejected-optimizations.md`, `plans/archive/**` (≈200 вхождений в 40+
файлах архива). Это записи о прошлом, а не ссылки на текущее дерево.

## 4. Гейты, которые срабатывают на переезд

1. **`scripts/docs-impact.py`** (`:37` `SURFACE_CORE = ^core/.*\.py$`): статус `A`/`D`/`R` на
   surface-пути **всегда** триггерит гейт — change-set обязан содержать правку доков той же
   поверхности. Дом доков core — `docs/core/**` (`:61`, `:84–85`), физически это
   `docs/core/index.md` (46 строк, таблица «Что внутри» перечисляет 13 модулей и **не
   содержит ни одного provider-модуля** — кластер в доках core сегодня не описан).
2. **`packages/harness/configs/claude-code/hooks/review-gate/checks/plan-citations.sh`**:
   если change-set задел `plans/<ID>/`, по КАЖДОМУ задетому плану гоняется
   `plans/verify-citations.py plans/<ID> --strict`; нарушением считаются находки сверх
   `plans/verify-citations-known-exceptions.json`. Значит bookkeeping-коммит P6.1 обязан
   оставить в файлах ЭТОГО плана только существующие после переезда пути.
3. **CI `.github/workflows/test.yml:36`**: `PYTHONPATH=. python3 -m unittest discover -s core/tests -v`.
   `:47` ruff: `core/ core/tests …` (рекурсивно, подкаталоги покрыты автоматически).
4. **`packages/harness/scripts/validate.sh:18–22`**: `cmp` вендоренной копии
   `core/usage.py` ↔ `packages/harness/lib/harness/_usage.py` (писатель —
   `packages/harness/scripts/sync-usage.sh`). Переезд `usage.py` потребовал бы синхронной
   правки обоих; provider-кластера это НЕ касается.
5. **Лаунчеры** (`packages/*/bin/*:~60`): на `PYTHONPATH` кладётся корень монорепо ради
   пакета `core` — путь импорта пакета не меняется при внутренней перекладке модулей.

## 5. Baseline тестов `core/` — КРАСНЫЙ на `HEAD`

```
PYTHONPATH=. python3 -m unittest discover -s core/tests
Ran 251 tests in 3.366s
FAILED (failures=1)
```

Единственный провал (воспроизводится на чистом `HEAD`, рабочее дерево не содержит правок
`configs/`/`core/`):

```
FAIL: test_approved_carrier_round_trips_with_distinct_canonical_and_carrier_hashes
core/tests/test_provider_manifest.py:34
AssertionError: '9d8b9570…20b4' != '603c7949…d4e1'
```

Тест читает ЖИВОЙ `configs/provider-capabilities.json` (`test_provider_manifest.py:14–17`:
`ROOT = parents[2]`, `APPROVED_CANONICAL_SHA256` — константа в тесте) — т.е. канонический
хеш манифеста разошёлся с утверждённым. Предмет — поверхность манифеста провайдеров
(соседняя с P5.2), не структура каталога. **Для P6 это baseline:** «зелёный прогон» как
критерий приёмки здесь недостижим, критерий обязан быть дельтовым.

## 6. Замер: `unittest discover` и подкаталоги (Python 3.12.3, живой эксперимент)

Вопрос: обнаружит ли `discover -s core/tests` тесты, переехавшие в `core/tests/provider/`.

```bash
mkdir -p X/tests/sub
# tests/test_top.py и tests/sub/test_nested.py — по одному тривиальному TestCase
python3 -m unittest discover -s tests        # без __init__.py в sub/
→ Ran 1 test                                  # ТЕСТ ИЗ ПОДКАТАЛОГА ПОТЕРЯН МОЛЧА
touch tests/sub/__init__.py
python3 -m unittest discover -s tests
→ Ran 2 tests
```

`python3 --version` → **3.12.3**.

Вывод: подкаталог без `__init__.py` не обнаруживается и **не даёт ни ошибки, ни
предупреждения** — прогон остаётся «зелёным» на уменьшившемся наборе. Это ровно класс
«гейт зеленеет на пустоте». Отсюда два обязательных требования к зеркалу тестов:
`core/tests/provider/__init__.py` должен существовать, а приёмка — сверять ЧИСЛО
обнаруженных тестов с baseline (251).

## 7. Якоря путей, зависящие от глубины файла

`grep -rn "parents\[" core/*.py core/tests/*.py`:

| Файл | Строка | Якорь |
|:--|:--|:--|
| `core/tests/test_provider_config.py` | `:61` | `Path(__file__).resolve().parents[2]` |
| `core/tests/test_provider_manifest.py` | `:14` | `parents[2]` (→ `configs/provider-capabilities.json`) |
| `core/tests/test_provider_registry.py` | `:51` | `parents[2]` |
| `core/tests/test_usage.py` | `:18` | `parent.parent / "usage.py"` (не provider — не двигается) |

Все три `parents[2]` — в provider-тестах; при переезде на уровень ниже они обязаны стать
`parents[3]`, иначе ROOT укажет на `core/`. В самих модулях `core/*.py` якорей `parents[…]`
нет вовсе — код кластера от глубины не зависит.

## 8. Поверхность конфига (вход P6.2)

**Носитель `.swissknife.json` (конфиг проекта):**

- Загрузка — `packages/skiller/lib/skiller/config.py:156–166` `load_config(env, target)`:
  `json.loads` → `validate_config` → **возвращает голый `dict`** (или `{}`).
- Валидация — `config.py:117–154`: перебор ключей против `CONFIG_KEYS`
  (`packages/skiller/lib/skiller/common.py:43–61`, **14 ключей**), плюс проверки, требующие
  ЛОКАЛЬНОГО знания skiller: имя профиля сверяется со списком `env.root/profiles/*.json`
  (`:137`), `agent` — с `AGENT_DEFAULTS` (`:140`), четыре ключа помечены `_RESERVED` и дают
  WARN (`:145–154`).
- Потребители — 45 вызовов `config.get(…)`/`cfg.get(…)` в `packages/skiller/lib`
  (`grep -c`), топ-ключи: `skills_path` (8), `project_type` (6), `exclude` (5), `buckets` (5),
  `agent` (4), `presets` (2), `memory_brain`, `providers`.
- **Третий носитель тех же ключей** — `packages/skiller/schema/swissknife.schema.json`
  (JSON-schema, DX/IntelliSense). Синхрон сторожат ДВА гейта: `skiller doctor`
  (`packages/skiller/lib/skiller/doctor.py:1010–1045` — сверяет и имена, и ТИПЫ свойств) и
  `packages/skiller/tests/test_schema.py`.
- Второй читатель того же файла вне skiller — `packages/maind/lib/maind/provider_deploy.py:175`
  (`root / ".swissknife.json"`), но он читает только подветку `/providers` через
  `core.provider_config` — типизация ветки уже сделана в core.

**Носитель `config.json` (конфиг узла maind):** обёртка УЖЕ существует —
`packages/maind/lib/maind/config.py:378` `class Config(dict)` с `load/save`, `source`/`path`
и аксессорами секций (`projects`, `namespaces`, `integrations`). То есть «голых dict» на этом
носителе нет; предмет P6.2 — не он.

**Образец типизации в `core/`:** `core/env.py:13–30` `@dataclass(frozen=True) class BaseEnv`
с `__post_init__`-нормализацией. 38 `@dataclass` в `core/*.py`, все `frozen=True`.

**Критерий приёма примитива в `core/`** (документирован): «когда примитив дублируется между
≥2 пакетами со стабильной границей … доменные надстройки остаются в `common.py` пакетов»
(`docs/core/index.md`, раздел «Когда трогать»).

## 9. Запрет навигации графом (перепроверено)

`audits/skm.md` §«Пробел В»: пилот `tirth8205/code-review-graph` против Serena дал
precision blast-radius **0.039** при заявленном пороге **≥0.40** на co-change замере →
вердикт «канон навигации — Serena (LSP); повторное подключение графового MCP без НОВОГО
собственного замера противоречит принятому вердикту». Формулировка аудита прямо предупреждает,
что мысль подключить граф возникнет именно на рефакторинге `core/` (п. 4) — то есть на этой
фазе.
