# P3 слой 1 — как Claude Code грузит описания скиллов и режет tool-result MCP (2026-07-25)

Источники — first-party дока Claude Code (`code.claude.com/docs/en/{skills,mcp,settings}`, WebFetch
2026-07-25) + бандл-скилл `claude-api` (кэш 2026-06-24, модели/цены/токенайзер). Каждое утверждение
несёт цитату; вывод для скоупа отделён от цитаты явно.

Покрывает факт-классы FC-1 · FC-2 · FC-3 · FC-4 карты `research/03-P3-fact-classes.md`.

## 1. FC-1 — что резидентно из скилла и чем ограничено (first-party)

Дословно (`/docs/en/skills`, раздел «Skill descriptions are cut short»):

> «Claude Code loads a listing of skill names and descriptions into context so Claude knows what's
> available. The listing **always contains every skill name**, but if you have many skills, Claude Code
> **shortens descriptions to fit the listing's character budget**, which can strip the keywords Claude
> needs to match your request. **The budget scales at 1% of the model's context window.** When the
> listing overflows, Claude Code **drops descriptions starting with the skills you invoke least**, so
> the skills you use most keep their full text.»

> «Run `/doctor` for an estimate of the listing's context cost and its biggest contributors. When the
> listing exceeds its budget, Claude Code also writes a warning to the debug log, visible with `--debug`.»

> «**The Skills row in `/context` reports the size of the listing after the budget is applied**, so it
> matches what the model receives. **Before v2.1.196, the row counted the full text of every description
> and could show a value several times larger than the configured budget.**»

> «To raise the budget, set the `skillListingBudgetFraction` setting (e.g. `0.02` = 2%) or the
> `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable to a fixed character count. To free budget for
> other skills, set low-priority entries to `"name-only"` in `skillOverrides` so they list without a
> description. You can also trim the `description` and `when_to_use` text at the source: put the key use
> case first, since **each entry's combined text is capped at 1,536 characters regardless of budget**.
> The cap is configurable with `skillListingMaxDescChars`.»

Из таблицы frontmatter там же:

> `description` — «What the skill does and when to use it. … the combined `description` and
> `when_to_use` text is **truncated at 1,536 characters in the skill listing** to reduce context usage.»
> `when_to_use` — «Appended to `description` in the skill listing and **counts toward the 1,536-character cap**.»

Модель загрузки (таблица «When loaded into context»): «Description always in context, full skill loads
when invoked»; отдельная нота — «In a regular session, skill descriptions are loaded into context so
Claude knows what's available, but full skill content only loads when invoked.»

**Не найдено:** строк `skillListingBudgetFraction` / `skillListingMaxDescChars` в таблице
`/docs/en/settings#available-settings` (фетч вернул только `disableBundledSkills` и
`disableSkillShellExecution` по маске «skill»), и их нет в `json.schemastore.org/claude-code-settings.json`
(схема отстаёт). Имена и семантика — только из прозы страницы skills; **числовые дефолты**
(`0.01` фракция, `1536` символов) взяты из той же прозы, отдельной строки-дефолта нет. Статус:
first-party, но не из таблицы настроек — при реализации сверять `/doctor` фактическим прогоном.

### Следствие для P3.1 (это синтез, не цитата)

Премиса экс-P7 («сжали топ-7 описаний на ~30% → сэкономили ≈260 ток × N резидента») **условна**:
резидент — не сумма всех описаний, а **листинг после применения бюджета**. Если на проекте листинг
переполняет бюджет, Claude Code уже урезает/снимает описания сам, и ручное сжатие даёт экономию
не резидента, а **места в бюджете для описаний менее вызываемых скиллов** (то есть выигрыш в точности
триггеров, не в токенах). `budget.py` считает сумму всех описаний — тот же класс переучёта, что был в
`/context` до v2.1.196.

## 2. FC-2 — токенайзер Claude 5 и как считать токены честно

Из бандл-скилла `claude-api` (`shared/model-migration.md`, `shared/models.md`, `shared/token-counting.md`;
кэш моделей 2026-06-24):

- **Sonnet 5:** «New tokenizer (**~30% more tokens for the same text** vs Sonnet 4.6)». Это подтверждает
  цитату D19 — но привязывает её к **линии Sonnet**, а не к «Claude 5 family» целиком.
- **Opus 5 / Fable 5:** «same tokenizer as Opus 4.8 (introduced with **Opus 4.7**)». Для Opus-линии
  токенайзер сменился ещё на 4.7: «the Opus 4.7 tokenizer uses **~1×–1.35×** as many tokens» относительно
  Opus 4.6/Sonnet/Haiku и старше. Прямого утверждения «Opus 5 даёт +30%» в источниках **нет** —
  оценка D19 в этой части шире, чем доказано.
- **Как мерить правильно:** `POST /v1/messages/count_tokens` — «Token counts are **model-specific** — pass
  the same model ID you'll use for inference». И прямой запрет суррогатов: «**Do not use `tiktoken`.**
  It's OpenAI's tokenizer. It undercounts Claude tokens by ~15–20% on typical text, and by much more on
  code or non-English input.» CLI-форма: `ant messages count-tokens --model <id> --message '{role: user,
  content: "@./FILE"}' --transform input_tokens -r`.
- **Цены (для owner-решения OQ-4, см. второй финдинг):** Opus 5 — $5/$25 за 1M вход/выход;
  Sonnet 5 — $3/$15 (интро $2/$10 до 2026-08-31); Haiku 4.5 — $1/$5. Контекст: Opus 5 и Sonnet 5 — 1M.

### Следствие для перекалибровки (синтез)

`packages/skiller/lib/skiller/budget.py:40-66` считает токены **эвристикой chars/tok** (кириллица ≈2.9,
латиница ≈3.4), пороги — `FIRST_TURN_TARGET_MAX = 7_000`, `FIRST_TURN_WARN = 10_000`
(`budget.py:193-194`), цена MCP-тула — `TOKENS_PER_MCP_TOOL = 150` (`budget.py:206`). Перекалибровка
теперь имеет **детерминированный якорь**: посчитать тот же корпус через `count_tokens` на
`claude-opus-5` и вывести константы из замера, а не из статей. Это сетевой one-off (ключ/`ant auth`),
не рантайм — stdlib-only ограничение пакета не нарушается, если константы **зашиваются числом**, а
измерительный скрипт живёт в scratchpad/артефактах.

## 3. FC-3 — клиентские лимиты MCP tool-result (БЛОКИРУЮЩИЙ факт для P3.2)

Дословно (`/docs/en/mcp`, раздел «MCP output limits and warnings»):

> «**Output warning threshold**: Claude Code displays a warning when any MCP tool output exceeds
> **10,000 tokens**»
> «**Configurable limit**: you can adjust the maximum allowed MCP output tokens using the
> `MAX_MCP_OUTPUT_TOKENS` environment variable»
> «**Default limit**: the default maximum is **25,000 tokens**»
> «**Scope**: the environment variable applies to tools that don't declare their own limit. Tools that set
> `anthropic/maxResultSizeChars` use that value instead for text content, regardless of what
> `MAX_MCP_OUTPUT_TOKENS` is set to.»

И — ключевое для дизайна:

> «If you're building an MCP server, you can allow individual tools to return results larger than the
> default persist-to-disk threshold by setting `_meta["anthropic/maxResultSizeChars"]` in the tool's
> `tools/list` response entry. Claude Code raises that tool's threshold to the annotated value, **up to a
> hard ceiling of 500,000 characters**. … **Without the annotation, results that exceed the default
> threshold are persisted to disk and replaced with a file reference in the conversation.**»

> «You can also ask the server author to add the `anthropic/maxResultSizeChars` annotation **or to
> paginate their responses**.»

Отдельно (там же): «Claude Code **truncates tool descriptions and server instructions at 2KB each**.
Keep them concise to avoid truncation, and put critical details near the start.»

### Следствие для P3.2 (синтез)

Премиса экс-P8 («без серверного потолка модель галлюцинирует поверх обрыва») **частично снята**: клиент
не рубит молча — он **выгружает превышение на диск и подставляет file-reference**. Значит цель серверного
тримминга смещается: (а) не допустить деградации «ответ → ссылка на файл» (это меняет режим работы:
модели нужен отдельный шаг чтения); (б) держаться **ниже 10 000 токенов**, где начинается warning, а не
ниже 25 000; (в) `truncated`/PARTIAL-receipt нужен именно для случая, когда **сервер сам** решил урезать.
Плюс появился новый, дешёвый рычаг, которого в экс-P8 не было: `_meta["anthropic/maxResultSizeChars"]`
на конкретных тулах maind (напр. `maind_projects_status`, который заведомо крупный) — и ревизия
`description` 11 тулов против лимита 2KB.

## 4. FC-4 — как сигнализировать частичный результат

- **Claude-Code-специфичный канал** — `_meta["anthropic/maxResultSizeChars"]` в записи `tools/list`
  (цитата выше). Это не про «частичность», а про подъём порога.
- **Протокольный канон пагинации** — в спеке MCP пагинация есть на уровне `tools/list` (`nextCursor`);
  канонического общепротокольного флага «этот tool-result усечён» в найденных источниках **нет**.
  Практика (см. `findings/P3-mcp-result-field-practice.md`) — договорные поля в payload'е
  (`truncated`/`has_more`/`next_cursor`/`returned_count`/`total_count`) плюс человекочитаемая строка в
  текстовом слое.
- **`isError`** в нашем сервере уже используется как флаг ошибки инструмента
  (`packages/maind/lib/maind/mcp.py:97-102`) — под частичность его переиспользовать нельзя: это иной класс.

## Проверка

- Проверено (first-party, WebFetch 2026-07-25): лимиты и поведение листинга скиллов
  (`/docs/en/skills`), лимиты MCP-вывода и аннотация `_meta` (`/docs/en/mcp`).
- Проверено (бандл-скилл `claude-api`, кэш 2026-06-24): токенайзеры Opus/Sonnet 5, `count_tokens` как
  канон подсчёта, цены и контексты моделей.
- **Непроверенное → помечено:** дефолты `skillListingBudgetFraction`/`skillListingMaxDescChars`
  отсутствуют в таблице настроек и в schemastore — взяты из прозы страницы skills, при реализации
  подтверждаются прогоном `/doctor`/`--debug`. Утверждение D19 «+30% у всей Claude 5 family» —
  подтверждено только для **Sonnet 5**; по Opus 5 источники говорят «тот же токенайзер, что у Opus 4.8».
- Обходок-`[POSSIBLE-DEFECT]`: `budget.py` суммирует все описания скиллов, тогда как клиент применяет
  бюджет листинга — вероятный переучёт компоненты `skills ⊕` (тот же дефект, что был в `/context`
  до v2.1.196). Гипотеза, требует замера в P3.1, а не правки вслепую.
</content>
