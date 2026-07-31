# Разбор красного baseline `test_provider_manifest` (гейт OQ-7)

**Дата:** 2026-07-31 · **Дерево:** `HEAD = ebd42655` · **Класс:** repo-grounded (внешних
фактов нет — всё воспроизводится командами ниже на этом дереве).

Слой 1. Файл производит вход для гейта владельца **OQ-7** и для item'а **P6.3**.
Синтез и вердикт — `research/08-premortem-and-oq7-verdict.md` §1 и D61 `plan.md`.

## 1. Что именно красное

```
$ PYTHONPATH=. python3 -m unittest discover -s core/tests 2>&1 | tail -12
FAIL: test_approved_carrier_round_trips_with_distinct_canonical_and_carrier_hashes
  File ".../core/tests/test_provider_manifest.py", line 34
AssertionError: '9d8b95709c5977dcec4699e515feebadcbb4c77b00d3c4a25ca869b61e8920b4'
          !=   '603c7949d7b236bbce0f5ec1a682f79b8dfde4bb75a42436600594797d64d4e1'
Ran 251 tests in 3.877s
FAILED (failures=1)
```

Утверждение падает ПЕРВЫМ из четырёх в том же тесте (`:34`), поэтому остальные три
(carrier-хеш, побайтовый round-trip, кортеж `(2, 35, 0)`) на `HEAD` не выполнялись вовсе —
их состояние до этого разбора было неизвестно.

## 2. Кто разошёлся: тест или манифест

Канонический хеш живого манифеста, посчитанный тем же кодом, что и в тесте, на трёх
коммитах:

| Коммит | canonical sha256 | carrier sha256 | тест |
|:--|:--|:--|:--|
| `ebb63efa` (= `af8d0f37^`) | `603c7949…d4e1` | `153d13bf…de1a` | 🟢 |
| `af8d0f37` | `9d8b9570…20b4` | `2b3bd60c…f387d` | 🔴 |
| `ebd42655` (HEAD) | `9d8b9570…20b4` | `2b3bd60c…f387d` | 🔴 |

Константы теста (`core/tests/test_provider_manifest.py:16–17`) равны значениям строки
`ebb63efa`. Значит **разошёлся тест**: он несёт хеши до-регенерационного состояния.

Команда воспроизведения (для любого `<ref>`):

```
git show <ref>:configs/provider-capabilities.json > /tmp/m.json
PYTHONPATH=. python3 -c "
import hashlib
from core import parse_provider_manifest, provider_manifest_sha256
raw = open('/tmp/m.json','rb').read()
print(provider_manifest_sha256(parse_provider_manifest(raw)), hashlib.sha256(raw).hexdigest())"
```

## 3. Чем именно отличается манифест (полный семантический дифф)

`af8d0f37` — коммит `docs(plan): миграция root/ 2026.07.29-HARNESS-AGNOSTIC → docs`;
в его сообщении прямо сказано, что `configs/provider-capabilities.json` +
`docs/provider-support.md` + `README.md` **перегенерированы через
`scripts/provider-docs.py --write`**.

Дифф манифеста (JSON — одна строка, поэтому сравнение сделано по разобранному значению):

```
python3 -c "
import json, difflib
a = json.load(open('old.json')); b = json.load(open('new.json'))
fmt = lambda v: json.dumps(v, indent=1, ensure_ascii=False, sort_keys=True).splitlines()
print('\n'.join(difflib.unified_diff(fmt(a), fmt(b), lineterm='', n=0)))"
```

Результат: **29 изменённых строк, все одного вида** —

```
-  "source": "plans/2026.07.29-HARNESS-AGNOSTIC/root/contracts/codex-parity-verdicts-v1.md",
+  "source": "plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/contracts/codex-parity-verdicts-v1.md",
```

Изменены ТОЛЬКО поля `evidence[].source`. Ноль изменений в `providers`, `capabilities`,
`support`, `native_extensions`, `contract_version`, `catalog_version`. Кортеж
`(len(providers), len(capabilities), len(native_extensions))` остаётся `(2, 35, 0)` —
то есть третье и четвёртое утверждения теста прошли бы.

**Вывод:** правка манифеста правомерна и обязательна — план `2026.07.29-HARNESS-AGNOSTIC`
уехал в `plans/archive/`, и ссылки-доказательства обязаны указывать на его новое место.
Незамеченным осталось не изменение манифеста, а НЕобновление констант.

## 4. Носителей устаревшей константы ДВА, а не один

Тот же литерал живёт во втором файле — и второй раннер тоже красный:

| Файл | Строки | Что несёт |
|:--|:--|:--|
| `core/tests/test_provider_manifest.py` | `:16` `APPROVED_CANONICAL_SHA256`, `:17` `APPROVED_CARRIER_SHA256` | утверждённый снимок манифеста |
| `scripts/test-provider-docs.py` | `:33`, `:35` — те же два литерала инлайном | конформанс генератора доков |

```
$ PYTHONPATH=. python3 scripts/test-provider-docs.py 2>&1 | tail -3
Ran 4 tests in 23.665s
FAILED (failures=2)
```

Из двух провалов второго раннера **релевантен один** —
`test_independent_exact_set_matrix_and_production_requirements_are_green` (`:32`, тот же
устаревший канонический хеш). Второй провал —
`test_committed_outputs_are_exact_and_check_is_no_write` (`:46`) — падает на сверке
снимка ВСЕГО дерева до/после прогона (`snapshot(ROOT)` обходит `root.rglob("*")`), то есть
ловит любой файл, изменённый посторонним процессом за время прогона; утверждение
«закоммиченные выходы точны» (`:44`) при этом ПРОШЛО. Класс второго провала — средо-зависимая
хрупкость теста, а не дрейф манифеста; он назван здесь, чтобы исполнитель P6.3 не принял его
за часть своей работы.

## 5. Область поражения — CI, а не только локальный прогон

```
.github/workflows/hygiene.yml:45   python3 scripts/test-provider-docs.py -v
.github/workflows/hygiene.yml:46   python3 scripts/provider-docs.py --check
.github/workflows/test.yml:36      PYTHONPATH=. python3 -m unittest discover -s core/tests -v
```

Два из трёх шагов красны с `af8d0f37` (30 июля 2026). Третий —
`provider-docs.py --check` — **зелёный** (`exit=0`): закоммиченные `docs/provider-support.md`
и `README.md` перегенерированы правильно и несут ВЕРНЫЙ хеш `9d8b9570…20b4`. То есть
сгенерированные доки уже содержат истинное значение, а два теста — устаревшее.

## 6. Почему дрейф прожил незамеченным

Ни один гейт не связывает регенерацию манифеста с константами: `provider-docs.py --write`
перезаписывает манифест и доки, но про два тест-файла не знает; тесты сравнивают хеш с
литералом и при расхождении печатают только `'<hex>' != '<hex>'` — без указания, что
делать. Оператор, увидевший такой дифф, не может отличить «манифест перегенерирован
правомерно» от «манифест испорчен». Это и есть предмет гейта, который P6.3 обязан завести
(вердикт владельца 2026-07-31, D61).

## 7. Что НЕ проверялось

- `[UNVERIFIED]` Прогон `scripts/test-provider-docs.py` в чистом CI-окружении (без фоновых
  процессов, пишущих в дерево) — второй провал §4 там может не воспроизвестись. Проверка —
  предмет P6.3, а не этого разбора.
Отдельно ПРОВЕРЕНО (третьего устаревшего носителя нет). Свип по всем четырём литералам
(`grep -rn "603c7949d7b236bb\|153d13bf98df0de1\|9d8b95709c5977\|2b3bd60cade123" .`, без
`.git/` и без плановых каталогов) даёт ровно четыре носителя:

| Файл | Значение | Состояние |
|:--|:--|:--|
| `core/tests/test_provider_manifest.py:16,17` | `603c7949…` / `153d13bf…` | **устарело** |
| `scripts/test-provider-docs.py:33,35` | `603c7949…` / `153d13bf…` | **устарело** |
| `README.md:21` | `9d8b9570…` | верно (генерируется) |
| `docs/provider-support.md:9,10` | `9d8b9570…` / `2b3bd60c…` | верно (генерируется) |

Итог: чинить нужно ровно два файла, и оба — тестовые.
