# Канон корневых инструкций

Механизм `harness instructions` управляет двенадцатью проекциями корневых/пакетных
инструкций (шесть scope × два провайдера: `CLAUDE.md`/`AGENTS.md` в корне и по одному
на `skiller`/`harness`/`maind`/`analyst`/`task`) из ОДНОГО источника — без ручной
синхронизации между Claude Code и Codex.

## Источник и цели

Источник — фрагменты `packages/harness/configs/common/instructions/**` (правило на
файл) плюс `catalog.json` (76 семантических ID: 56 общих + 20 provider-extension,
D86). Каждая из двенадцати целей рендерится из среза каталога по своему scope и
провайдеру; провайдер-специфичные расширения — аддитивный слой поверх общих правил
(`root.provider-parity`), не замена. Машинный референс с точной картой «scope →
target → счётчики» — [`provider-instructions.md`](./provider-instructions) (генерируется
`operator_reference()`, пинится тестом байт-в-байт — руками не правится).

## Управляемые блоки

В каждой цели правило живёт между парой HTML-маркеров
(`<!-- swissknifeman:instructions:<scope>:<provider>:<common|extension>:begin/end -->`).
**Ручная правка содержимого между маркерами запрещена навсегда**: следующий прогон
`check`/`repair` увидит расхождение хеша и поднимет `managed-drift` на шаге `[9/9]`
`packages/harness/scripts/validate.sh`. Байты вне блоков (заголовок файла, разделы,
не покрытые каталогом) сохраняются вербатим — правятся только фрагменты и
перегенерация.

## Три наблюдения

- **`stale-source`** — исходный фрагмент изменился, а цель ещё несёт старый рендер.
  Чинится обычным `apply --authorize <target>` (создание/обновление).
- **`managed-drift`** — содержимое управляемого блока изменено МИМО механизма (ручная
  правка, чужой коммит). Чинится ТОЛЬКО `repair` с явными `--observed-hash` на каждую
  дрейфующую цель и `--preimage-dir` (см. ниже) — сужение проверки, `|| true` или
  исключение цели из гейта запрещены.
- **`ownership-conflict`** — цель существует, но не несёт маркеров и записи в
  `.swissknifeman/provider-artifacts.lock.json` (типичный случай — вручную написанный
  `CLAUDE.md` до внедрения механизма). `apply`/`repair` такую цель не трогают; путь
  наружу — `adopt` (ниже).

## Пять операций `harness instructions`

```
harness instructions <plan|check|adopt|apply|repair> [--target P]
  [--scope a,b] [--provider a,b] [--authorize a,b]
  [--owner-decision D#] [--mapping FILE] [--preimage-dir DIR]
  [--observed-hash path=hash,...] [--json]
```

- **`plan`** — no-write снимок: что рендерится и как это соотносится с текущим
  деревом. Ничего не пишет.
- **`check`** — то же плюс гейт покрытия обязательных литералов (см. ниже); modular
  entry point для CI/validate.sh — `python3 -m harness.instructions --check`, вердикт
  обязан совпадать с `harness instructions check` байт-в-байт.
- **`adopt`** — owner-gated принятие СУЩЕСТВУЮЩЕГО неуправляемого файла под
  управление: требует ОБЯЗАТЕЛЬНО все три — `--owner-decision D#` (авторитет
  решения), `--mapping FILE` (посекционная карта «источник → семантический ID»,
  покрывающая файл целиком) и `--preimage-dir DIR` (куда пишется байт-в-байт
  pre-image ДО мутации, restore-путь — `rollback_adoption`). Отказывает на любой
  цели, которая не `ownership-conflict`.
- **`apply`** — пишет РОВНО цели, перечисленные `--authorize` (missing/create или
  stale-source/update); список обязан совпадать И по составу, И по ПОРЯДКУ с тем, что
  спланировал `plan` — иначе `INSTRUCTION_WRITE_FORBIDDEN`.
- **`repair`** — чинит `managed-drift`: тот же список-и-порядок в `--authorize`, плюс
  `--observed-hash target=hash` на КАЖДУЮ дрейфующую цель (доказательство, что
  оператор видел актуальное состояние), плюс `--preimage-dir adjacent-backup`
  (буквальная строка — pre-image пишется рядом с целью, не в отдельный каталог).

**Порядок целей в `--authorize` — АЛФАВИТНЫЙ по `target_path`** (авторитетная
формулировка). Любой другой порядок (например, «сначала корневые, потом пакетные»)
даёт `INSTRUCTION_WRITE_FORBIDDEN`, потому что механизм сравнивает кортежи позиционно.

`plan` и `check` — no-write; `apply`/`repair`/`adopt` пишут только после явной
авторизации оператора.

## Adoption-режим: откат

Каждое `adopt` перед мутацией пишет pre-image в `--preimage-dir` и записывает его
хеш/путь в `semantic_metadata.adoption` соответствующей lock-записи. Откат —
`rollback_adoption`: байт-в-байт восстановление из pre-image и снятие lock-записи;
без записанного pre-image откат fail-closed (отказывает, а не аппроксимирует).

## Два машинных гейта

- **Гейт дрейфа `[9/9]`** — последний шаг `packages/harness/scripts/validate.sh`:
  `python3 -m harness.instructions --check`, зелёный только если все двенадцать целей
  `clean`. Единственный CI-носитель на сегодня (`skiller`/`analyst`/`task` в CI не
  покрыты — открытый вопрос вне этого item'а).
- **Гейт равенства провенанса покрытия литералов** — `validate_literal_coverage`
  сверяет два независимых факта: (1) записанный `source_sha256` фикстуры
  `tests/fixtures_data/instruction-literal-coverage-v1.json` равен хешу РОВНО
  извлекаемой §2-секции матрицы `research/05-instruction-canon-routing.md` (иначе
  `INSTRUCTION_PROVENANCE_INVALID`); (2) сам список обязательных литералов
  по-прежнему присутствует в живых проекциях. Провенанс, пиновавший хеш ВСЕГО файла
  матрицы, протухал от любой посторонней правки файла — сужение до §2 и гейт
  равенства (D81) не дают этому повториться молча.

## Отношение к слоям `control-surface`

В терминах трёх слоёв источника зонтичного `control-surface` (canonical → generated →
effective): фрагменты + `catalog.json` — canonical, двенадцать проекций — generated
(дрейф чинится перегенерацией, не правкой файла), то, что реально видит агент в
сессии, — effective.
