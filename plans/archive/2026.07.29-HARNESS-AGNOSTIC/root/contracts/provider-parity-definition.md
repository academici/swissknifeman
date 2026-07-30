---
type: contract
plan: 2026.07.29-HARNESS-AGNOSTIC
contract: provider-parity-definition
status: sealed (P0.4)
exports: "определение паритета провайдеров: три исхода триажа с условием каждого, планка evidence, требования к диагностике отказа, машинная проверка вердикта и чек-лист самопроверки"
version: v1
consumers: "P1 (паритет корневых инструкций — §0.2), P2.1 (триаж 17 записей), P2.2–P2.4 (реализация вердиктов), P2.5 (конформанс-артефакт и гейт), P5.3 (приёмка), будущие планы, трогающие configs/provider-capabilities.json"
verdict: "RAG:— (repo-grounded, дерево 99cb35f3: core/provider_manifest.py:330-410 инварианты трёх уровней; scripts/provider-docs.py:67-148 production_requirements/conformance; прогон harness doctor --provider-audit --json; configs/provider-capabilities.json; plan.md D3/D8/D19/D20/D21/D30/D56, research/02-p0-premortem.md R2)"
---

# Контракт: определение паритета провайдеров (v1)

**Назначение.** Правила ВЫНЕСЕНИЯ вердикта о паритете: при каких условиях capability
считается закрытой на втором провайдере, что является легальным `Claude-only`, что —
снятой интенцией, какая evidence обязательна и чем каждое условие проверяется машинно.
Контракт не пересказывает каталог: состав записей, уровни и диагностики живут в
`configs/provider-capabilities.json` и в генерируемом `docs/provider-support.md`.

**Зачем.** Без него «догнать паритет» (D3) закрывается переписыванием текста диагностики:
15 Codex-специфичных записей `unsupported` можно объявить закрытыми, не тронув поведения.
Контракт делает каждое условие проверяемым командой, УЖЕ существующей в дереве.

**Граница выполнимости (R2).** Живой прогон второго провайдера решением владельца Р3 из
скоупа исключён (D3). Контракт, требующий такого прогона, — дефект дизайна, а не строгость:
ни одно условие ниже его не требует. Если по ходу триажа окажется, что вердикт недоказуем
без живого прогона Codex, это меняет основание D3 → останов и эскалация, а не тихое
ослабление планки.

## 0. Область действия

**0.1. Предмет — записи `support.<provider>` каталога capability.** На дереве `99cb35f3`:
35 capability, два провайдера, `contract_version` = `catalog_version` = `1.0.0`; у `codex`
`unsupported` в **17** записях, из них **2** (`lifecycle.daemon-safety`,
`lifecycle.git-guardrails`) — `unsupported` у ОБОИХ (D56). Замер —
`python3 -c "import json; m=json.load(open('configs/provider-capabilities.json')); print(len(m['capabilities']), sum(c['support']['codex']['level']=='unsupported' for c in m['capabilities']))"`.

**0.2. Что контракт НЕ определяет.** Он не задаёт паритет корневых инструкций (P1) —
там носитель другой (`provider-instruction-contract`, его состояния `missing`/`clean`/
`stale-source`/…). Из этого контракта на P1 действуют только два правила, потому что они
о ФОРМЕ доказательства, а не о каталоге: планка evidence (§2) и запрет «доказательства
переписыванием текста» (§3, п. 4).

**0.3. Заморожено и не трогается.** Уровней ровно три (`native`/`adapted`/`unsupported`,
`SupportLevel`); `contract_version`, `catalog_version` и precedence выбора провайдера
(`operation > project > fleet-project > fleet-defaults > legacy`) не меняются; расширение
каталога — только аддитивное; удаление capability-ID запрещено (D20) и немедленно
краснит конформанс (`PROVIDER_DOCS_CONFORMANCE_FAILED:missing`).

## 1. Три исхода триажа

Enum вердикта закрыт (§7 плана, D19): `closed-by-adapter` · `claude-only` ·
`intent-withdrawn`. Четвёртого исхода, а также формулировок «частично», «best-effort»,
«позже» не существует: они означали бы четвёртый уровень поддержки, а он заморожен.

| Исход | Когда легален | Форма записи в каталоге | Чем проверяется |
|:--|:--|:--|:--|
| `closed-by-adapter` | у провайдера появился детерминированный адаптер или нативная привязка, закрывающая интенцию capability | `level` = `adapted` (нативная привязка → `native`); `adapted` требует непустой `adapter_id` + непустые `limitations` + непустую `evidence`; `native` требует `binding` + `evidence` и ЗАПРЕЩАЕТ `adapter_id` | C1 (`--check` exit 0) + C2 (`activation_state: supported` в `surface_map` для этого провайдера, аудит `green: true`) — для 23 harness-поверхностей; для остальных 12 — C1 + C6 (§6.2) |
| `claude-only` | ни один потребитель не требует у Codex уровня выше `unsupported` — проверяется пробой C3, а не суждением | `level` остаётся `unsupported` (это НЕ уровень — D20); `limitations` называют КЛАСС причины; `evidence` ссылается на `root/contracts/codex-parity-verdicts-v1.md` (D19); `binding`/`adapter_id` отсутствуют | C3 (нет ни одной строки требования со списком принимаемых уровней без `unsupported`) + C1 + C4 |
| `intent-withdrawn` | capability `unsupported` у ОБОИХ провайдеров И потребителя нет ни у одного из них (§5) | то же, что `claude-only`, плюс запись причины снятия; capability-ID НЕ удаляется | C3 по ОБОИМ провайдерам + C1 + C4 |

**Правило принуждения.** Если проба C3 показала хотя бы одного потребителя, требующего
`native`/`adapted`, исходы `claude-only` и `intent-withdrawn` НЕЛЕГАЛЬНЫ: остаётся либо
`closed-by-adapter`, либо изменение самого потребителя (чужая поверхность — эскалация,
не правка по месту). Пример замера на `99cb35f3`: у `skills.repository` — 24 строки
требований, все 24 строгие (без `unsupported` в принимаемых), поэтому `claude-only`
для неё невозможен структурно; у `lifecycle.daemon-safety` — 2 строки требований, обе
принимают все три уровня (строгих 0).

**Определение паритета (то, что меряет P5.3).** Паритет достигнут, когда одновременно:
(1) `python3 scripts/provider-docs.py --check` — exit 0; (2) `harness doctor
--provider-audit --json` — `green: true` и пустой `diagnostics`; (3) у каждой записи
`unsupported` провайдера `codex` есть вердикт `claude-only` или `intent-withdrawn` в
`root/contracts/codex-parity-verdicts-v1.md`, а не молчание. Ни один из трёх пунктов не
заменяет другие: (1) и (2) зелены и СЕГОДНЯ, при 17 незакрытых записях.

## 2. Планка evidence

Каждый вердикт кладётся в поле `evidence[]` записи, форма которого заморожена
(`core/provider_manifest.py`): ровно четыре ключа `source` · `verified_at` · `scope` ·
`claim`, все непустые, `verified_at` — строго `YYYY-MM-DD`; список не может быть пустым
ни на одном уровне, включая `unsupported`. Сверх машинной формы контракт требует:

1. **`source` — путь к артефакту, лежащему в дереве в момент вынесения вердикта**
   (`test -e "<source>"` — зелёный). Допустимы: артефакт плана, файл конфигурации,
   контракт-документ; при необходимости точности — `<путь>@<commit>`. Прецедент
   существующих записей: пять источников на `99cb35f3`, из них четыре — артефакты
   `2026.07.19-DUAL-PROVIDER`, один — `packages/task/configs/command-routing.json`.
2. **После архивации плана-источника строка становится документарной, а не резолвимой,
   и это НЕ дефект** (D19): четыре из пяти существующих источников уже указывают на
   `plans/2026.07.19-DUAL-PROVIDER/artifacts/…`, тогда как план лежит в
   `plans/archive/2026.07.19-DUAL-PROVIDER/`. Требование п. 1 адресовано МОМЕНТУ записи;
   переписывать исторические строки под новый путь запрещено (append-only-провенанс).
3. **`claim` фальсифицируем**: из формулировки видно, что именно её опровергнет. «Адаптер
   работает», «поддержка добавлена» — не claim; «детерминированный адаптер
   `<adapter_id>` закрывает поверхность `<id>` у `<provider>`, наблюдается зелёной
   строкой `surface_map` аудита» — claim.
4. **`scope` называет границу утверждения** (какая поверхность, какой провайдер, какой
   срез), чтобы claim нельзя было расширить задним числом.
5. **Одна запись — один вердикт.** Evidence не переиспользуется между capability, если её
   `claim`/`scope` не покрывают новую запись дословно.

## 3. Что доказательством НЕ является

1. **Отсутствие живого прогона Codex — не препятствие** (D3, Р3): вердикт выносится по
   артефактам дерева. Обратное тоже верно: живой прогон, не оставивший артефакта в
   дереве, доказательством не становится.
2. **Утверждение без артефакта** — «известно, что Codex это умеет», «в сессии
   проверялось», память агента, скриншот, ссылка на внешний URL без запиненного
   `findings/`-артефакта.
3. **Зелёный байт-хеш генерируемых доков сам по себе.** `docs/provider-support.md` и блок
   README — производные каталога: их совпадение подтверждает, что генератор прогнан, и
   ничего не говорит о поведении провайдера (D30 — нужен хотя бы один публично
   проверяемый факт сверх внутреннего hash-green).
4. **Переписанный текст `diagnostic`/`limitations`/`intent` при неизменном поведении** —
   прямая мишень этого контракта: смена формулировки без смены `level`, `adapter_id` или
   наблюдаемой строки аудита вердиктом не является.
5. **Удаление capability-ID или сужение каталога**, чтобы запись `unsupported` перестала
   попадать в отчёт (D20).
6. **Введение четвёртого уровня, «частичной» поддержки или мягкого отказа** (§4).
7. **Ссылка на артефакт, которого нет в дереве в момент вердикта** (п. 1 §2 не пройден).

## 4. Требования к диагностике отказа

1. **Единственная диагностика отказа — fail-closed `HARNESS_ACTIVATION_UNSUPPORTED`.**
   «Мягких» отказов (предупреждение, деградация, тихий no-op вместо отказа) не вводится.
2. Требование машинное, а не стилистическое: запись уровня `unsupported` принимается
   валидатором, только если её `diagnostic` содержит один из замороженных токенов
   fail-closed (`unsupported` · `fail closed` · `fail-closed` · `refus` · `exclude` ·
   `disabled`) и при этом НЕ несёт `binding`/`adapter_id`, а `evidence` непуста
   (`core/provider_manifest.py`, ветка `_support` для `SupportLevel.UNSUPPORTED`).
3. Для `adapted` диагностика утверждает детерминированность адаптера и называет его —
   форма существующих записей: «deterministic harness adapter satisfies
   `<provider>` `<capability>`».
4. Диагностика отказа обязана быть НАБЛЮДАЕМОЙ: у 23 поверхностей она появляется строкой
   `evidence[]` аудита с `polarity: negative`, `state: unsupported` и тем же кодом
   (на `99cb35f3` — 16 таких строк из 146). Диагностика, которую не печатает ни одна
   команда, требованию не удовлетворяет.

## 5. Исход «интенция снята» (двусторонний `unsupported`)

Применим ТОЛЬКО к записям, `unsupported` у обоих провайдеров: на `99cb35f3` это ровно
`lifecycle.daemon-safety` и `lifecycle.git-guardrails` — объявленная, но нереализованная
интенция (OQ-3). Условия исхода:

1. **Записанная причина** в `limitations` обоих провайдеров: почему интенция снята и что
   занимает её место (или явно — «замены нет»).
2. **Подтверждённое отсутствие потребителя** — проба C3 по ОБОИМ провайдерам возвращает
   ноль строк со строгим требованием уровня. Не «мы не нашли потребителя», а вывод
   команды в отчёте item'а.
3. **capability-ID остаётся в каталоге** (D20): набор ID выводится независимо из
   каталогов-производителей, и удаление немедленно даёт `missing` в конформансе.
4. **Вердикт записан** в `root/contracts/codex-parity-verdicts-v1.md` (D19) с той же
   evidence-планкой, что и остальные два исхода.
5. Если позже интенция возвращается — это АДДИТИВНАЯ правка (уровень поднимается,
   `limitations` переписываются), а не reopen контракта.

## 6. Машинная проверка вердикта

### 6.1. Команды (все существуют в дереве на `99cb35f3`, все прогнаны при авторинге)

| Код | Команда | Что подтверждает | Замер на `99cb35f3` |
|:--|:--|:--|:--|
| C1 | `python3 scripts/provider-docs.py --check` | манифест парсится под замороженной схемой; набор ID совпадает с независимо выведенным (`missing`/`extra`/`duplicates` пусты); наблюдаемый уровень каждого требования потребителя входит в принимаемые; генерируемые `README.md`-блок и `docs/provider-support.md` байт-в-байт совпадают с рендером | exit 0 |
| C2 | `bash packages/harness/bin/harness doctor --provider-audit --json` | `green: true`, пустой `diagnostics`, строка `surface_map` на пару (поверхность, провайдер) с `activation_state` и диагностикой, `evidence[]` с `polarity`/`state` | `green: true`, `diagnostics: []`, `evidence`: 146 строк, `surface_map`: 46 строк = 23 поверхности × 2 провайдера |
| C3 | `python3 -c "import importlib.util; s=importlib.util.spec_from_file_location('pd','scripts/provider-docs.py'); pd=importlib.util.module_from_spec(s); s.loader.exec_module(pd); rows=[(r[0],r[1],sorted(r[3])) for r in pd.production_requirements() if r[2]=='<capability>']; print(len(rows)); print([r for r in rows if 'unsupported' not in r[2]])"` | поимённый перечень потребителей capability и принимаемых ими уровней — легальность `claude-only`/`intent-withdrawn` | `lifecycle.daemon-safety` → 2 строки, строгих 0; `skills.repository` → 24 строки, строгих 24 |
| C4 | `PYTHONPATH=. python3 -c "from core import load_provider_manifest; from pathlib import Path; load_provider_manifest(Path('configs/provider-capabilities.json')); print('manifest OK')"` | инварианты трёх уровней и формы `evidence[]` (агрегированная диагностика при нарушении) | часть C1; отдельный прогон даёт `manifest OK` |
| C5 | `test -e "<source>"` по каждому новому `evidence[].source` | п. 1 §2 — артефакт лежит в дереве в момент вердикта | — |
| C6 | `bash packages/skiller/scripts/validate.sh` · `bash packages/harness/scripts/validate.sh` · `bash packages/maind/scripts/validate.sh` | поведение пакетов, стоящих за 12 capability вне `surface_map` | прогон — обязанность item'а, меняющего каталог |

### 6.2. Покрытие: аудит видит не всё

`harness doctor --provider-audit` покрывает **23 из 35** capability (`surface_map`, замер
`99cb35f3`). Вне его — **12**: `analytics.legacy-migration`, `analytics.normalized-events`,
`analytics.run-report`, `command.external-research`, `command.filesystem-read`,
`command.filesystem-write`, `command.git-read`, `command.git-write`, `command.subagents`,
`command.workflow-carrier`, `instructions.project`, `skills.repository`. Из 17
Codex-`unsupported` вне аудита лежит одна — `analytics.legacy-migration`. Для этих
capability C2 не является доказательством ни в одну сторону: их вердикт опирается на
C1 (строки требований потребителей) + C6. Ссылаться на «зелёный аудит» как на
подтверждение закрытия capability, которой в `surface_map` нет, запрещено.

### 6.3. Честная оговорка о гейте

Ни один автоматический гейт сегодня не зовёт C1: `scripts/test-provider-docs.py` и
`--check` не вызываются ни из одного `validate.sh`, ни из одного workflow (D21, тот же
замер повторён при авторинге на `99cb35f3`). Пока гейт не поставлен, C1/C2 прогоняет
руками item, меняющий каталог, и вклеивает вывод в Completion Notes. Дом гейта —
`.github/workflows/hygiene.yml` (D21), исполнитель — P2.5; этот контракт гейт не ставит.
Отдельно: `python3 scripts/test-provider-docs.py` на `99cb35f3` КРАСНЫЙ по причине вне
каталога — битая ссылка `roadmap/self-learning-memory.md` из `README.md:122`
(`test_internal_markdown_links_resolve_and_examples_keep_provider_syntax_separate`);
три остальных теста файла зелёные. Исполнителю P2.x это известное состояние, а не его
регрессия.

## 7. Чек-лист самопроверки (по нему P2.1 ведёт триаж)

Одна строка = одно условие, которое обязано быть закрыто ДО фиксации вердикта по записи.

| # | Условие | Чем проверяется |
|:--|:--|:--|
| 1 | Вердикт — один из трёх (`closed-by-adapter` · `claude-only` · `intent-withdrawn`), формулировок «частично»/«позже» нет | чтение записи вердикта; enum §1 |
| 2 | Уровень записи принадлежит замороженным трём, четвёртый не введён | C4 (иначе `MANIFEST_SUPPORT_LEVEL_INVALID`) |
| 3 | Форма уровня соблюдена: `adapted` → `adapter_id` + непустые `limitations` + `evidence`; `native` → `binding` + `evidence` без `adapter_id`; `unsupported` → без `binding`/`adapter_id`, с fail-closed диагностикой и непустой `evidence` | C4 / C1 |
| 4 | `evidence[]` несёт четыре ключа, `verified_at` = `YYYY-MM-DD`, `claim` фальсифицируем, `scope` ограничен | C4 + чтение §2 |
| 5 | Каждый новый `evidence[].source` лежит в дереве на момент вердикта | C5 |
| 6 | Для `claude-only`/`intent-withdrawn`: ни одного строгого потребителя | C3 (вывод в отчёте item'а) |
| 7 | Для `intent-withdrawn`: запись `unsupported` у ОБОИХ провайдеров и причина снятия записана | C3 по обоим + чтение `limitations` |
| 8 | capability-ID не удалён, набор ID не сужен | C1 (`missing` пусто) |
| 9 | Для `closed-by-adapter` поверхности из `surface_map`: `activation_state: supported` у этого провайдера | C2 |
| 10 | Для capability вне `surface_map`: вердикт опирается на C1 + C6, «зелёный аудит» как доказательство не используется | §6.2 |
| 11 | Диагностика отказа не смягчена, код fail-closed сохранён и наблюдаем | C2 (`polarity: negative`) + C4 |
| 12 | `contract_version`, `catalog_version`, precedence не тронуты; правка аддитивна | `git diff` по `configs/provider-capabilities.json` + C1 |
| 13 | Генерируемые доки перегенерированы своим генератором, а не правлены руками | `python3 scripts/provider-docs.py --write` затем C1 |
| 14 | Вердикт записан в `root/contracts/codex-parity-verdicts-v1.md`, а не только в каталоге | `test -e` + чтение |
| 15 | Ни одно условие вердикта не потребовало живого прогона Codex | чтение вердикта; при обратном — эскалация (§«Граница выполнимости») |
