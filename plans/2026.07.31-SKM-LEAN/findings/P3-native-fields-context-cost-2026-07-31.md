# P3 — что нативные поля скиллов делают с КОНТЕКСТОМ (проверка 2026-07-31)

**Слой 1 (внешнее сырьё + repo-grounded якоря).** Собрано в ходе `plan-design <ID> P3`
2026-07-31. Дополняет `findings/rag-2026-07-31-native-skill-fields.md` (тот отвечал на вопрос
«какие поля СУЩЕСТВУЮТ»), здесь — вопрос «какое поле и на какую ОСЬ цены действует».
Потребители: **P3.1–P3.5**, косвенно — P2.5 (форма хаб-блока) и P1.3 (порог).

## 0. Почему заведён этот файл

Постановка брифа §P3 стоит на допущении «нативный `paths:` даёт скоуп скиллов» (и на нём же
стоит вердикт владельца D5(а) «дефолт `connect` не меняем — скоуп даёт `paths:`»). Допущение
проверено дословно по first-party доку — и **не подтвердилось на резидентной оси**. Факт
несущий: без него первый item фазы измерял бы поле, которое по конструкции не может дать
ожидаемого числа.

## 1. Таблица «поле → на что действует» (first-party, дословно)

Источник: <https://code.claude.com/docs/en/skills>, полный текст страницы прочитан
2026-07-31 (WebFetch). Вердикт: **first-party, актуально**.

| Поле | Резидентный первый ход (листинг) | Тело в сессии | Дословная опора |
|:--|:--|:--|:--|
| `paths` | **НЕ снимает** запись листинга | ограничивает АВТО-загрузку тела | «Glob patterns that limit when this skill is **activated**. When set, Claude loads the skill automatically only when working with files matching the patterns» |
| `disable-model-invocation: true` | **снимает запись целиком** | тело грузится только по `/name` | таблица §«Control who invokes a skill», колонка «When loaded into context»: `disable-model-invocation: true` → **«Description not in context, full skill loads when you invoke»** |
| `user-invocable: false` | не снимает | как у дефолта | та же таблица: «Description always in context» |
| (дефолт) | запись в листинге | тело по вызову | та же таблица: «Description always in context, full skill loads when invoked» |
| `when_to_use` | **увеличивает** запись листинга | — | «Appended to `description` in the skill listing and **counts toward the 1,536-character cap**» |
| `context: fork` | не меняет листинг | тело уходит в форкнутый контекст, в основную сессию не садится | §«Run skills in a subagent» + §2 файла `rag-2026-07-31-native-skill-fields.md` |
| `model` / `effort` | не меняет | не меняет | «The override applies **for the rest of the current turn** and is not saved to settings»; `effort` — «Overrides the session effort level» на время активности |
| `background` | — | `false` → ждать результат в том же ходе; **требует ≥ 2.1.218** | таблица frontmatter (min-version 2.1.218) |

**Второй источник (подтверждение, не первоисточник):** perplexity-web 2026-07-31, запрос
«does a path-scoped skill still appear in the startup skill listing»: «a skill with `paths:`
is **still part of the startup skill listing** if it's model-invocable; the paths glob only
narrows **when it auto-activates**, not whether its name/description exists in the session's
skill inventory»; про `disable-model-invocation` — «removes the skill's description from the
preloaded listing/context entirely».

## 2. Вердикт: у фазы ДВЕ РАЗНЫЕ оси, и их приборы разные

| Ось | Что это | Кто на неё действует | Чем меряется |
|:--|:--|:--|:--|
| **A — резидентный первый ход** | сумма записей листинга (`name` + `description` + `when_to_use`, кап 1 536 симв) по активному набору | сжатие описаний · `disable-model-invocation` · состав активного набора (вне скоупа, D5) | `skiller budget --first-turn` (МОДЕЛЬ) + стенд `claude -p --output-format json` (НАБЛЮДЕНИЕ) |
| **B — цена внутри сессии** | тела скиллов, осевшие в контексте после (в т. ч. ложной) активации | `paths:` (меньше ложных авто-активаций) · `context: fork` (тело не садится в основную сессию) | нашим измерителем **не меряется вовсе**; наблюдение — `/context` владельца, `claude -p` прогон с наблюдаемым составом |

**Следствие 1.** Ожидание «пилот `paths:` даст падение первого хода» — **ложно по
конструкции**. Пилот, снятый `skiller budget --first-turn`, покажет дельту **0** независимо
от того, работает поле или нет; ноль будет истолкован как «поле не работает» — ошибка в обе
стороны.

**Следствие 2.** Единственное нативное поле с ДОКАЗАННЫМ нулевым резидентным входом —
`disable-model-invocation: true`, и платится за него потерей авто-роутинга (скилл виден
только человеку по `/name`). Это не техническая деталь, а вердикт уровня раздачи на флот.

**Следствие 3.** Перенос триггер-фразы из `description` в `when_to_use` **сам по себе
экономии не даёт**: оба поля входят в одну запись листинга и в один кап 1 536. Экономию даёт
только СЖАТИЕ суммарной записи.

## 3. Что об этом «думает» наш измеритель (repo-grounded)

- `packages/skiller/lib/skiller/budget.py:243–258` `_listing_entry_tokens` — считает
  `name` + (`description` + ` ` + `when_to_use`), обрезая до
  `SKILL_LISTING_MAX_ENTRY_CHARS = 1_536` (`:220`). **`when_to_use` уже учтён** — новая
  строка во frontmatter немедленно подорожает замер.
- `budget.py:260–271` `_listing_entry_chars` — Codex-ось, та же пара полей, **без капа**
  (первоисточник числа для Codex не называет).
- `budget.py:274–296` `measure_listing_budget` — суммирует ПО ВСЕМУ активному набору:
  **ни `disable-model-invocation`, ни `paths` не учитываются**. То есть на 2026-07-31 прибор
  завышает резидентный листинг ровно на 10 скиллов, уже несущих
  `disable-model-invocation` (`findings/repo-recon-2026-07-31.md` §4).
- `budget.py:123–152` `resolve_active_set` — тот же путь выборки, что у раздачи `vendor`.

## 4. Гейты репозитория, которые задевает правка описаний (repo-grounded)

- `packages/skiller/scripts/validate.sh:91,92` — `DESC_WARN_MAX = 300`,
  `DESC_ERROR_MAX = 450`; счёт ведётся по `len(description)` **без** `when_to_use`
  (`:232–247`).
- `:96–98` `DESC_TRIGGER_RE` — триггер-фраза ищется **только в `description`**
  (`:252` `has_trigger = bool(DESC_TRIGGER_RE.search(desc))`), upstream-скиллы пропускаются.
- `:117` `TRIG_BURNDOWN` — рэтчет `scripts/desc-trigger-burndown.txt` (91 строка файла,
  69 записей долга); отсутствие скилла в списке при отсутствии триггера = **ERROR**.
- `:324–344` — протухшие записи обоих burn-down списков дают WARN.
- `:1231–1236` §12b — drift-гейт реестра: после правки frontmatter обязателен
  `bin/skiller registry --check` (`skills.json`/`_index.md`/манифесты — производные).
- `:1274` §14 — двуязычная свежесть: маркер `<!-- ru-source-sha256: … -->` в `SKILL.md`
  = sha256 файла `SKILL.ru.md` (`packages/skiller/scripts/check-translations.sh:48,58`).
- `:1385` §17 — WARN-гейт листинга профилей против фолбэк-бюджета Codex.

**Следствие для P3.5.** Перенос триггер-фразы в `when_to_use` при НЕИЗМЕНЁННЫХ гейтах:
(а) делает 69-строчный долг триггеров формально «ухудшившимся» (фраза ушла из
`description` → ERROR у скиллов, которых нет в burn-down), (б) прячет рост реальной цены
записи под порогом, который смотрит только на `description`. Гейты обязаны быть
пере-базированы на СОВОКУПНУЮ запись листинга в том же item'е, что вводит `when_to_use`.

## 5. Наблюдательный стенд: чем поле проверяется агентом (repo-grounded)

`packages/skiller/lib/skiller/quality/eval.py` уже несёт процессный раннер:

- `:19` — «РАННЕР (`run_case` через `claude -p`) — online, opt-in; нет `claude` в PATH → …»;
- `:387` `build_run_cmd` — сборка argv для `claude -p`;
- `:397` `_parse_claude_json` — разбор `(text, tokens)` из JSON-вывода `claude -p`;
- `:412–441` `run_case` — один прогон в каталоге workspace, `DEFAULT_TIMEOUT = 180` (`:49`).

> **Исправление 2026-08-01 (заход `plan-design <ID> P3.1`, фактура —
> `findings/P3.1-bench-harness-probe-2026-08-01.md` §5).** Прежняя редакция этих трёх строк
> называла символ `_build_argv` (в дереве его НЕТ: `grep -rn "_build_argv" packages/` → 0) и
> утверждала, что «скилл инъектируется в workspace». Фактически `build_run_cmd` подмешивает
> ТЕЛО скилла в системный промпт (`--append-system-prompt`), а в workspace пишутся только
> `case.files[]`. Для P3.1 этот способ непригоден по ПРЕДМЕТУ: поля frontmatter действуют на
> механизм скиллов клиента, а инъекция тела в системный промпт его обходит — пробник кладётся
> на диск настоящим скиллом (D94). Формула токенов раннера (`input_tokens + output_tokens`)
> для оси A тоже непригодна: резидентный префикс приезжает в кэш-поля (`input_tokens` = 2 на
> живом прогоне), см. §3 того же файла.

То есть A/B-замер «одинаковый промпт в фикстурном workspace, поле включено/выключено →
дельта входных токенов из `--output-format json`» — **исполним агентом**, без участия
человека. `/context` и `/doctor` остаются пользовательскими командами (агенту не видны,
`findings/P2-resident-layer-probe-2026-07-31.md` §9) — они годятся как КАЛИБРОВКА владельцем,
но не как приёмка item'а.

Отдельный готовый режим — `skiller eval <скилл> --triggers` (`quality/eval.py:1017,1052–1060`):
оптимизация ТРИГГЕР-точности описания по `evals/triggers.json` (`should_trigger` /
`should_not`), стабы создаются `--scaffold`. Это прямой прибор приёмки для правки описаний.

Покрытие поведенческими тестами скиллов сегодня — **4 `evals.json` на 229 скиллов**
(`general/verify-claims`, `general/anti-drift`, `general/compact-responses`,
`quality/code-review`): проверить «не сломался ли авто-роутинг после правки описания» онлайн
можно ровно на этой четвёрке, для остальных прибора нет — граница называется явно.

## 6. Источник приоритизации по факту (repo-grounded)

`packages/skiller/lib/skiller/quality/audit.py:12,145–313` — команда `skiller bucket-audit`
(`packages/skiller/lib/skiller/cli.py:32`) даёт usage-сигнал
фан-аутом по `~/.swissknifeman/projects.json` (загрузки скилла из JSONL-транскриптов за окно),
вердикты и `usage_note`; при `scanned_projects == 0` данные объявляются неинформативными, а не
«всё мертво». Это тот самый «источник приоритизации по ФАКТУ», которого требовал
`roadmap/skill-description-quality.md` §«Почему отложено дальше этого».

## 7. Известные дефекты апстрима — статус на 2026-07-31 (перенос из соседнего файла)

- **#49835** (`paths:` полностью выбивает скилл из обнаружения) — **open**, подтверждён на
  2.1.92; живая версия среды 2.1.220. Проверяется P3.1.
- **#17283** (`context: fork` игнорируется при вызове через Skill tool) — closed, фикс-версия
  не названа. Проверяется P3.1 на обоих путях активации.
