# Ремедиация P1: потерянные правила, дедуп расширения, гейт покрытия литералов

**Слой:** 2 (авторский синтез) · **Произведён:** 2026-07-30, заход `plan-design 2026.07.29-HARNESS-AGNOSTIC P1`
(реопен по вердикту RED `phases/P1.md` § `Audit P1 — 2026-07-30`) · **Питает:** ТЗ P1.6 и P1.7,
D75–D79.

**Опирается на слои:** `research/05-instruction-canon-routing.md` (матрица «правило → дом», ВХОД
ремедиации — не её предмет) · `research/04-instruction-mechanism-inventory.md` §4 (механизм) ·
`findings/02-rag-instruction-loading-2026-07-29.md` Ф7/Ф8 (бюджет обоих провайдеров) ·
`phases/P1.md` § `Audit P1 — 2026-07-30` (F1–F10) ·
`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md`
(замороженный контракт, §«Common canon» / §«Provider extensions»).

---

## 1. Метод и собственные прогоны

Аудит назвал класс дефекта («правила с назначенным домом не доехали до рендера, машинной проверки
доставки нет»), но его число — `99/105` — воспроизводится только вместе со способом извлечения.
Поэтому прогон повторён здесь заново, и способ извлечения зафиксирован как БУДУЩИЙ ГЕЙТ, а не как
разовая проверка.

**Прогон 1 — форма §2 матрицы** (`2026-07-30`, дерево `81886a14` + рабочее дерево, матрица не
менялась с `fd5183af`):

```
строк, начинающихся с `|`, во всём §2 — 135
из них строк данных (минус 7 шапок и 7 разделителей) — 121
ячеек «Обязательный литерал» ≠ «—» — 105
```

RAG:— (repo-grounded: собственный прогон извлекателя по
`research/05-instruction-canon-routing.md`, границы §2 — от строки `## 2. ` до `## 3. `).

Отсюда: подпись «135 ячеек колонки «Источник»» в `phases/P1.md:88` (Completion Notes P1.1) названа
неверным предметом — 135 это ВСЕ строки-с-`|` в §2, а строк матрицы 121 (**F8 подтверждён числом**).

**Прогон 2 — покрытие «литерал → его собственная запись каталога»** (строгая форма, см. §6):
литерал обязан присутствовать хотя бы в одном `compatibility_assertions` ТОЙ ЖЕ записи, чей ID
назван в колонке «Дом» той же строки. Результат: **99 из 105 покрыты, 6 — нет**:

| # | Запись каталога («Дом») | Отсутствующий литерал | Класс |
|:--|:--|:--|:--|
| 1 | `root.cli-routing` | `` the umbrella owns the `swissknifeman` launcher alias `` | правило потеряно целиком |
| 2 | `root.shared-core` | `deduplicate rather than maintain parallel implementations` | правило потеряно целиком |
| 3 | `root.decision-verification` | `` prefer `perplexity-web` aggressively over `WebSearch` `` | правило потеряно целиком |
| 4 | `root.codex.launch-and-hook-integrity` | `never native-only` | правило потеряно целиком |
| 5 | `root.codex.bootstrap` | `` canonical skill and command content stays under `packages/skiller/skills/` `` | смысл в рендере есть, литерал — нет (расхождение формулировки) |
| 6 | `harness.agent-pack-lifecycle` | `the review-role registry indexes roles without copying their rules` | смысл в рендере есть, литерал — нет (расхождение формулировки) |

**Расхождение с аудитом раскрыто честно (root.evidence-integrity):** аудит перечислил ЧЕТЫРЕ
отсутствующих литерала (строки 1–4) и отдельно два правила без собственного литерала (см. §3,
правила B и C). Строки 5 и 6 аудит не назвал — они относятся к тому же классу «матричный литерал не
присутствует в `compatibility_assertions`», но их смысл в рендере наличествует, поэтому чтением они
не видны. Число `99/105` при этом совпало: аудит считал по тому же множеству 105 и получил 6
непокрытых, назвав из них 4 «отсутствующих в обоих» и 2 отнеся к правилам-без-литерала. Итог для
ремедиации: **гейт обязан закрыть все шесть строк таблицы выше**, иначе он не станет зелёным.
Матрица при этом НЕ правится (она вход): расхождение формулировки чинится в каноне — прямое
следствие ограничения захода «расхождения матрицы с рендером чинятся в каноне».

**Прогон 3 — цепочка доказательства.** Механизм уже проверяет, что каждое утверждение
`compatibility_assertions` присутствует в РЕНДЕРЕ дословно
(`packages/harness/lib/harness/instructions.py:745-755`, `INSTRUCTION_COMPATIBILITY_MISMATCH`).
Значит цепочка замыкается транзитивно: `матричный литерал ⊆ compatibility_assertions` (новый гейт)
`⊆ рендер` (существующий гейт) `⊆ живой файл` (гейт дрейфа `[9/9]`). Именно поэтому гейт покрытия
достаточно ставить на каталог, а не на двенадцать файлов: третье звено уже оплачено P1.5.
RAG:— (repo-grounded: `instructions.py:745-755` — подстрочная проверка утверждений против
`projection.result.managed_bytes`).

---

## 2. Почему потеря именно молчаливая (природа дефекта, не вина исполнителя)

Гейты фазы проверяли ФОРМУ, а не ПОКРЫТИЕ:

- `validate_catalog` — конверт, инвентарь, плотность `order`, хеши фрагментов, фикстура
  (`instructions.py:275-349`);
- `_validate_projection_semantics` — набор ID в рендере, паритет common, присутствие утверждений
  (`:715-768`);
- `[9/9]` в `validate.sh` — двенадцать целей `clean`.

Ни один из них не знает о существовании матрицы. Инвариант **И5** (`plans/README.md`) требует, чтобы
носители, невидимые машинному гейту, проверялись ЧТЕНИЕМ, — ни одна `Validation` фазы такой проверки
не несла. Отсюда вывод, который и делает ремедиацию не «доклейкой шести строк»: **у трансляции
«инвентарь → канон → живой файл» обязана быть машинная проверка ПОКРЫТИЯ, а не только формы**;
без неё матрица деградирует в документ-намерение.

---

## 3. Шесть потерянных правил: дом, целевой текст, форма защиты

Целевой язык — английский, изложение сжатое (решение владельца Р5); формат фрагмента не меняется
(маркер `<!-- instruction:<id> -->`, заголовок, тело). **Регистр литерала значим** — проверка
подстрочная и регистрозависимая, поэтому литерал вставляется в предложение так, чтобы он
присутствовал ДОСЛОВНО (в частности с маленькой буквы в середине фразы).

| Правило | Дом (запись) | Фрагмент | Матричный литерал | Как защищается |
|:--|:--|:--|:--|:--|
| A. Владение алиасом `swissknifeman`: зонтичный `install.sh` делегирует пакетным, алиасом владеет зонтик | `root.cli-routing` | `root/common.md` | есть (`the umbrella owns the …`) | гейт покрытия §6 |
| B. Плагины `harness`/`maind` — только команды, без MCP-сервера | `root.marketplace` | `root/common.md` | НЕТ (строка матрицы отдала литерал курируемому `core`) | НОВОЕ утверждение в каталоге (D78) |
| C. Граница «репо vs vault» + указатель `axioma/ecosystem-map` | `root.plan-lifecycle` | `root/common.md` | НЕТ (литерал строки — про `plans/<ID>/`) | НОВОЕ утверждение в каталоге (D78) |
| D. Агрессивность лестницы: retrieval/синтез внешних фактов выгружать на flat-rate `perplexity-web` по максимуму | `root.decision-verification` | `root/common.md` | есть (`prefer \`perplexity-web\` aggressively …`) | гейт покрытия §6 |
| E. Единый источник истины: дедуп вместо параллельных реализаций | `root.shared-core` | `root/common.md` | есть (`deduplicate rather than …`) | гейт покрытия §6 |
| F. Обязательность провайдер-нейтральной формы launch-block'а | `root.codex.launch-and-hook-integrity` | `root/codex.md` | есть (`never native-only`) | гейт покрытия §6 |

**Предлагаемые формулировки** (авторские, сжатые; исполнитель вправе улучшить стиль, но обязан
сохранить литерал дословно и не потерять смысл):

- **A** → в тело `root.cli-routing`: `Installation delegates to package installers, and the umbrella
  owns the \`swissknifeman\` launcher alias.`
- **B** → в тело `root.marketplace`: `The \`harness\` and \`maind\` plugins ship commands only, without
  an MCP server.`
- **C** → в тело `root.plan-lifecycle`: `The vault keeps only the programme-level cross-project plan
  and a link to the control tower; the situational map of where things live is the
  \`axioma/ecosystem-map\` skill, not this canon.`
- **D** → в тело `root.decision-verification`: `Delegate retrieval and synthesis of external facts to
  flat-rate tooling: prefer \`perplexity-web\` aggressively over \`WebSearch\`.`
- **E** → в тело `root.shared-core`: `One source of truth beats copies: deduplicate rather than
  maintain parallel implementations.`
- **F** → в тело `root.codex.launch-and-hook-integrity`: `Every finished task and terminal handoff
  ends with a launch block, and for plan work the provider-neutral \`plan-protocol\` form is mandatory
  alongside the native table — never native-only.`

**Почему B и C получают утверждения, которых в матрице нет (обоснование D78).** Гейт покрытия
односторонний: `матричные литералы ⊆ compatibility_assertions`. Обратного включения он не требует и
требовать не должен — иначе канон нельзя было бы усилить ничем, кроме перезаписи матрицы (а матрица
заморожена как вход). Поэтому лишнее утверждение законно, а для B и C оно ЕДИНСТВЕННЫЙ способ
сделать правило машинно защищённым: их собственные строки матрицы литерала не выделили, значит
гейт покрытия к ним слеп по построению, и защиту даёт только звено «утверждение ⊆ рендер»
(`instructions.py:745-755`). Это надо назвать в Completion Notes прямо, а не выдавать B и C за
покрытые гейтом.

---

## 4. F2 — дедуп внутри provider-extension (исполнение долга D73)

**Что нарушено.** `root.codex.bootstrap` (`AGENTS.md:82`, фрагмент `root/codex.md`) несёт два
обязательства, дословно живущие в common той же проекции:

| Фрагмент текста расширения | Дублируемый common-ID | Где виден дубль |
|:--|:--|:--|
| `use worktree-local package CLIs for writes` | `root.worktree-safety` | `AGENTS.md:58` |
| `and preserve Claude Code compatibility` | `root.provider-parity` | `AGENTS.md:55` |

Норма — потребляемый замороженный контракт: «A common rule is never copied into an extension
record»; «Duplicate meaning is rejected even when wording differs: an extension cannot hide a second
maintenance copy behind a new ID»
(`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md:122,152-153`).
Полномочие на изъятие выдано **D73** ещё в P1.1; адресатами были P1.2 (отложил) и P1.3 (счёл чужим
follow-up'ом), после закрытия обоих дом долга исчез.

**Целевое тело `root.codex.bootstrap`** (сужение + внесение матричного литерала строки 5 таблицы §1):

```
Treat `.agents/skills/*` as thin generated Codex bootstrap projections that are never the source of
truth: canonical skill and command content stays under `packages/skiller/skills/` and
`packages/task/commands/`.
```

Оба дубля уходят, Codex-специфичная часть (раскладка `.agents/**`, «адаптер не источник истины»)
остаётся, матричный литерал приезжает дословно.

**`root.codex.launch-and-hook-integrity`: изъятия НЕТ.** Прочитано целиком (`root/codex.md`,
`AGENTS.md:84-85`): дублей `root.provider-parity`/`root.worktree-safety`/`root.evidence-integrity`
текст не несёт — обязательство раскрытия дефектов окружения уехало в common ещё в P1.3
(`root.evidence-integrity`), а в расширении осталась только нативная механика запуска и хуков.
Работа по этой записи — исключительно ДОБАВЛЕНИЕ правила F (§3). Придумывать изъятие ради
симметрии со скоупом захода запрещено: это была бы подгонка под формулировку задания.

**Удаление утверждений законно** ровно для тех строк, что перечислены здесь: старое
полнофразовое утверждение `root.codex.bootstrap` («Treat `.agents/skills/*` as thin Codex adapters,
keep canonical skill and command content under … , use worktree-local package CLIs for writes, and
preserve Claude Code compatibility.») содержит удаляемый текст и обязано быть заменено на
утверждения нового тела. Основание — D73 + норма контракта, а не компактность.

**Слепая зона гейта остаётся (раскрыто, не чинится здесь).** `_validate_conflicts`
(`instructions.py:1005-1022`) сверяет `obligations`, чей `object` — самореферентный плейсхолдер
(`root.codex.bootstrap.requirements` против `root.worktree-safety.requirements`), поэтому
`INSTRUCTION_EXTENSION_CONFLICT` не может сработать ни при каком дубле СМЫСЛА. Механизм унаследован
от донора; правка схемы `obligations` — отдельный предмет с домом в `roadmap/` (граница захода).
Следствие, которое обязано быть названо в Completion Notes: зелёный `validate_catalog()`
доказательством отсутствия дублей не является — доказательство здесь только чтением по таблице выше.

---

## 5. F3 — `instructions` в `harness.command-surface`

`harness.command-surface` (фрагмент `packages/harness/configs/common/instructions/packages/harness/common.md`,
рендер `packages/harness/CLAUDE.md:21` и `packages/harness/AGENTS.md:21`) перечисляет семь команд:
`permissions`, `mcp`, `hooks`, `router`, `agent-packs`, `safe-dirs`, `doctor`. Команда `instructions`
сдана P1.4 в `COMMANDS` (`cli.py`) и в `bin/harness`, но в канон не попала — always-on документ,
поставленный сторожем дрейфа, сам стал источником дрейфа.

Обязательство адресовано трижды: §6 матрицы стр. 311, §7 находка 2 стр. 356, Pending Work (2) P1.2.

**Целевое тело:**

```
Keep the CLI surface `permissions`, `mcp`, `hooks`, `router`, `agent-packs`, `safe-dirs`,
`instructions`, and `doctor`, with explicit `--target` and dry-run behavior where defined.
```

**Гейт покрытия это позволяет:** матричный литерал строки (`research/05:152`) — короткий
`Keep the CLI surface`, а не полный перечень, поэтому расширение списка его не ломает. Старое
полнофразовое утверждение каталога заменяется новым, плюс добавляется токен `` `instructions` ``.

**Шестая непокрытая строка того же фрагмента** (`harness.agent-pack-lifecycle`, литерал
`the review-role registry indexes roles without copying their rules` против живой формулировки
«…indexes roles as an extension table alongside the canonical `roles.json` without duplicating its
rules») чинится там же переформулировкой хвоста, например:

```
… and the review-role registry indexes roles without copying their rules, as an extension table
alongside the canonical `roles.json`.
```

Смысл сохраняется полностью (extension-таблица рядом с каноном), литерал приезжает дословно.

---

## 6. Гейт покрытия: форма, альтернативы, почему выбрана эта

**Требования к форме гейта** (выведены из дефекта, а не из вкуса):

1. проверяет ПОКРЫТИЕ (каждый обязательный литерал имеет дом в утверждениях своей записи), а не
   форму;
2. строгая привязка «литерал → его запись»: совпадение с утверждением ЧУЖОЙ записи не считается
   покрытием (иначе гейт зелёный при правиле, уехавшем в неверную секцию);
3. живёт там, где его нельзя обойти при обычной разработке (`validate.sh` → `[9/9]`);
4. не делает пакет `harness` зависимым от каталога `plans/**`: пакет собирается и валидируется
   standalone (конвенция `root.docs-build`, `harness/scripts/test.sh` с fallback без `core`), а план
   когда-нибудь уедет в `plans/archive/`;
5. не вводит семнадцатого диагностического кода: набор из 16 кодов принадлежит ЗАМОРОЖЕННОМУ
   контракту донора;
6. не блокирует запись (`apply`/`repair`) — иначе красное покрытие невозможно починить: чтобы
   привести рендер в соответствие с исправленным каноном, нужен именно `apply`.

**Выбранная форма (D76):**

- **носитель обязательных литералов** — фикстура ВНУТРИ пакета
  `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` (прецедент:
  `instruction-compatibility-v1.json` из того же каталога читается ПРОДАКШН-кодом
  `instructions.py:257-258,1051-1054`, то есть «фикстура как замороженный вход валидатора» — уже
  принятая в механизме топология);
- **провенанс фикстуры** — путь матрицы, её `sha256`
  (`b2df0bceb39dc45c98febb005ff4e921d99f41d0cabbfc0861d5ccc9bfd5f219` на 2026-07-30), номер §,
  генератор, `owner_decision`, число строк (121) и число литералов (105);
- **генератор** — `plans/archive/2026.07.29-HARNESS-AGNOSTIC/artifacts/P1.6-extract-literals.py` (прецедент
  P1.5: генератор mapping'а `artifacts/P1.5-build-mapping.py` жил в carve-out плана). Так фикстура
  остаётся ГЕНЕРИРУЕМЫМ артефактом (`root.generated-artifacts`), а зависимость от `plans/**` живёт
  в плане, а не в пакете;
- **валидатор** — `validate_literal_coverage(...)` в `instructions.py`, диагностика — существующий
  `INSTRUCTION_COMPATIBILITY_MISMATCH` (`observation="semantic-invalid"`, `semantic_id`,
  `expected=<литерал>`, `observed="matrix literal not asserted"`);
- **точка включения** — `check_instructions` (`instructions.py:368-374`), то есть ОБА пути
  (`harness instructions check` и `python3 -m harness.instructions --check`) получают один вердикт
  автоматически, и существующий шаг `[9/9]` краснеет без перенумерации;
- **тесты** — `packages/harness/tests/test_instruction_literal_coverage.py`: зелёный прогон реальной
  фикстуры (105/105), сверка числа с провенансом, негативы (литерал-отсутствующий, неизвестный
  `semantic_id`, битый конверт), и один тест проводки (`check_instructions` не зелёный при красном
  покрытии).

**Отклонённые альтернативы:**

| Вариант | Почему отклонён |
|:--|:--|
| Новый шаг `[10/10]` в `validate.sh` | занимает номер, зарезервированный D48 за гейтом политики P4.3, и требует сплошной перенумерации ещё раз; при этом ничего не даёт сверх включения в существующий `[9/9]` |
| Читать матрицу `plans/**` прямо из кода пакета в рантайме | ломает standalone-валидацию пакета и портируемость: после архивации плана путь меняется, гейт станет либо красным, либо «пропущенным» (а пропуск, выданный за зелёное, запрещён `root.evidence-integrity`) |
| Новый диагностический код (17-й) | трогает набор диагностик ЗАМОРОЖЕННОГО контракта; аддендум канона `instruction-canon-addendum-v1.md` запечатан как аддитивная дельта СЕКЦИЙ, не кодов |
| Включить покрытие в `validate_catalog` | `validate_catalog` вызывается из `load_catalog`, то есть из `plan/apply/repair/adopt` — красное покрытие заблокировало бы `apply`, которым покрытие и чинится (дедлок) |
| Включить покрытие в `plan_instructions` | тот же дедлок: `apply`/`repair`/`adopt` строятся поверх `plan_instructions` |
| Оставить проверку разовым прогоном в Completion Notes | это ровно тот дефект, который аудит назвал F1: доказательство существует один раз и не переживает следующей правки |

**Извлекатель — три требования к реализации** (иначе число не воспроизведётся):

1. границы §2 — от строки `## 2. ` до следующей `## 3. ` (семь подтаблиц внутри);
2. строки данных = начинающиеся с `|` минус шапки и разделители (`|:--`); **экранированный `\|`
   внутри ячейки не является разделителем колонок** — наивный `split('|')` даёт фантомный 106-й
   литерал на строке `root.cli-routing` (проверено: именно так расходятся 105 и 106);
3. нормализация ячейки: срезать обрамляющие серии backtick'ов и пробелы; `—` — не литерал;
   колонка «Дом» разбирается по префиксу `ID `/`NEW `/`EXT `, дома `скилл …`/`снимается: …`
   литерала не несут.

---

## 7. Бухгалтерия ремонта (F4–F10): проверенные факты

**F4 — карта «коммит → item»** (`git log`, ветка `next/harness-agnostic`):

| Item | item-коммит | сопутствующие |
|:--|:--|:--|
| P1.1 | `fd5183af` | `340d0846` (bookkeeping) |
| P1.2 | `e574fdda` | `d1e393af` |
| P1.3 | `b02e48be` | `4ae56350` (bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) |
| P1.4 | `1e0262a4` | `d5482b37` |
| P1.5 | `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` |

Ни одна из пяти строк `## 6. Update Log` хеша не несёт; `handoff.md:17` называет пять хешей, из
которых `4ae56350` — bookkeeping, поданный как item-коммит, а `fd5183af`, `b02e48be` и `1e0262a4`
отсутствуют.

**F5** — `plan.md:13` несёт `Last Updated | 2026-07-29`, последняя строка `## 6. Update Log` —
`2026-07-30` (закрытие фазы). Правило: `Last Updated` = дата ПОСЛЕДНЕЙ строки Update Log.

**F6** — атрибуция WARN. Прогон
`python3 packages/task/scripts/plan-lint.py plans/2026.07.29-HARNESS-AGNOSTIC --baseline 4bdc4a5e`
даёт `0 ошибок, 2 предупреждений; новых от рабочего дерева: 1`: WARN `phases/P1.md:51` рождён
переводом фазы в терминальный статус (P1.1 это признал, агрегат фазы — переклеил на
«предсуществующий»). ERROR-гейт `K = 0` верен.

**F7** — порядок коммитов пре-имиджей: `git show --stat c3b3a8a3` — тринадцать файлов, каталога
`artifacts/` среди них нет; семь `pre_image_path`, записанных в lock ЭТИМ коммитом, появляются в
дереве только следующим (`d052698f`). Откат по контракту с дерева `c3b3a8a3` невозможен — это и есть
содержание записи, которой не хватает в Known Deviations (2) P1.5.

**F8** — 135 против 121, см. §1 (число заякорено командой, подписано неверным предметом).

**F9** — «десять остальных (три … и семь codex-фрагментов пакетов)» (`phases/P1.md:116-118`): из этих
семи **четыре** — `codex.md` (`harness`, `maind`, `analyst`, `task`), **три** — `claude-code.md`
(`maind`, `analyst`, `task`). Сам набор верен (18 фрагментов = 6 scope × 3; изменено 8, не тронуто
10 = три названных отдельно + эти семь). Проверено раскладкой каталога фрагментов и `git show
--stat e574fdda`.

**F10** — снятие 2 (`research/05:262`) обещает нормативную роль пакета в «шести `<pkg>.identity`».
Замер каталога: записей ровно формы `<pkg>.identity` — **четыре** (`skiller.identity`,
`harness.identity`, `maind.identity`, `task.identity`); у `analyst` роль пакета несёт
`analyst.identity-human-gate` (плюс `analyst.layout`, `analyst.module-boundaries`). Точная
формулировка правки — «четыре записи формы `<pkg>.identity`, у `analyst` — `analyst.identity-human-gate`»
(аудит в скобках назвал только `analyst.layout`/`analyst.module-boundaries`, что беднее факта).

---

## 8. Разнесение находок по items

| Находка | Item | Носитель правки |
|:--|:--|:--|
| F1 (шесть правил) | **P1.6** | `root/common.md`, `root/codex.md`, `catalog.json`, фикстура совместимости, рендер |
| F1 (гейт покрытия) | **P1.6** | фикстура покрытия, `instructions.py`, тесты, генератор в `artifacts/` |
| F1 (строки 5–6 §1: расхождения формулировок) | **P1.6** | `root/codex.md`, `packages/harness/common.md` |
| F2 (D73) | **P1.6** | `root/codex.md`, `catalog.json` |
| F3 | **P1.6** | `packages/harness/common.md`, `catalog.json` |
| F4, F5, F6 | **P1.7** | `plan.md` §0/§6, `handoff.md` |
| F7 | **P1.7** | `phases/P1.md` Known Deviations P1.5 |
| F8, F9 | **P1.7** | `phases/P1.md` Completion Notes P1.1/P1.2 (подписи чисел) |
| F10 | **P1.7** | `research/05` §5 (узкое исключение, D79) |

**Почему F1–F3 в одном item'е.** Три находки правят ОДНИ И ТЕ ЖЕ носители (`root/codex.md` — и
литерал F, и сужение F2; `packages/harness/common.md` — и F3, и строка 6 §1; `catalog.json` и
фикстура совместимости — все три), а любая правка каталога делает `source_hash` ВСЕХ двенадцати
проекций устаревшим (каталог — источник каждой проекции, `instructions.py:789-794`), то есть требует
полного `apply` и повторного замера бюджета. Два item'а означали бы двойной прогон живой транзакции
и промежуточное дерево с полу-сведённым каноном. Гейт покрытия остаётся В ТОМ ЖЕ item'е — иначе
содержательная правка закрылась бы `🟢` без машинного доказательства доставки, то есть дефект F1
воспроизвёлся бы в собственной ремедиации.

**Почему бухгалтерия — отдельный item.** У неё нет ни одного общего файла с P1.6 (кроме `plan.md`
§6, куда каждый item пишет свою строку сам), она обязана идти ПОСЛЕДНЕЙ (её предмет — в том числе
`Last Updated` = дата последней строки Update Log, а строку P1.6 пишет P1.6) и её риск-класс
принципиально иной: правки прозы закрытых items без права трогать их ТЗ.
