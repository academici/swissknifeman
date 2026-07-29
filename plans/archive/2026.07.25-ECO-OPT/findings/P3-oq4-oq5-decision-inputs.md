# P3 слой 1 — входы для owner-решений OQ-4 / OQ-5 плана `2026.07.15-TELEMETRY-OPT` (2026-07-25)

Факт-классы FC-6 · FC-7 · FC-8. Оба вопроса перенесены сюда через архивный `2026.07.15-TOKEN-ECON-P6`
P9 (D2), идентификаторы квалифицированы по канону D3 — это **не** OQ-4 этого плана (D17).
Файл собирает ФАКТЫ для решения владельца; вердикта не выносит.

## 1. FC-6 — вход для OQ-4: `task:research` frontier → implementation?

### Что решалось изначально (repo-grounded)

`plans/archive/2026.07.15-TELEMETRY-OPT/findings/P3-routing-audit.md` §3, вердикт **needs-Owner**:
«Opus-пин = reduce/синтез-мозг. Sonnet 5 near-par на retrieval+синтез, но **fidelity цитат +
кросс-источниковое reasoning** — зона, где Opus чуть впереди. Tradeoff: плохой синтез → плохие входы
`design` (но ловится downstream) → risk **MODERATE**, приоритет низкий.»

**Устарело по составу линейки:** вердикт написан 2026-07-15, когда верхним тиром был **Opus 4.8**.
Сегодня `task:research` пинится на Opus 5, а альтернатива — Sonnet 5. Сравнение «Sonnet 5 vs Opus 4.8»
к этой паре не переносится дословно.

### Цены и позиционирование (бандл-скилл `claude-api`, кэш 2026-06-24)

| Модель | ID | Вход $/1M | Выход $/1M | Контекст |
|:--|:--|--:|--:|--:|
| Opus 5 | `claude-opus-5` | 5.00 | 25.00 | 1M |
| Sonnet 5 | `claude-sonnet-5` | 3.00 (интро 2.00 до 2026-08-31) | 15.00 (интро 10.00) | 1M |
| Haiku 4.5 | `claude-haiku-4-5` | 1.00 | 5.00 | 200K |

Дельта Opus 5 → Sonnet 5: **−40% вход / −40% выход** по списку (−60%/−60% на интро-цене до 2026-08-31).
Позиционирование Sonnet 5 в доке: «The best combination of speed and intelligence in the Sonnet tier;
**near-Opus quality on coding and agentic work**».

### Полевой синтез (RAG ✅ 2026-07-25, perplexity web+social)

Прямого вендорского бенчмарка «citation accuracy Opus 5 vs Sonnet 5» **не найдено** — свидетельство
косвенное, и синтез это честно оговаривает. Что нашлось:

- Anthropic позиционирует Opus 5 как сильную сторону в long-context, устойчивом следовании инструкциям,
  tool calling и reasoning (1M-контекст как дефолт и максимум); Sonnet 5 — как более дешёвую модель,
  близкую на многих агентных задачах.
- **Что типично деградирует** при переводе research/synthesis-агента на Sonnet-класс: сверка документов
  между собой при противоречащих источниках; удержание ограничений на длинных прогонах; надёжность
  сопоставления «почему этот источник подтверждает это утверждение»; устойчивость на «много прочитать →
  написать плотно доказанный синтез».
- **Что держится:** first-pass retrieval; суммаризация отдельного источника; латентность и стоимость;
  достаточное качество на объёмных, не-адверсариальных research-задачах.
- Рекомендация синтеза (не наш вердикт): расщепить роли — Sonnet 5 на retrieval/триаж/черновой синтез,
  Opus 5 на финальный синтез и разрешение конфликтов. «If you want one model only, choose Sonnet 5 for
  scale and Opus 5 for trust.»

**Repo-grounded замечание для владельца:** у нас fan-out в `task:research` уже на implementation-классе
— Opus держит именно reduce-слой. То есть «расщепление ролей» из синтеза — это **текущая** архитектура,
а OQ-4 спрашивает ровно про понижение оставшегося reduce-слоя.

## 2. FC-7 — вход для OQ-5, ось B (auto-approve компаунд read-only)

### First-party механика (WebFetch `/docs/en/permissions`, 2026-07-25)

Дословно:

> «Claude Code is aware of shell operators, so a rule like `Bash(safe-cmd *)` won't give it permission to
> run the command `safe-cmd && other-cmd`. The recognized command separators are `&&`, `||`, `;`, `|`,
> `|&`, `&`, and newlines. **A rule must match each subcommand independently.**»

> «Claude Code recognizes a built-in set of Bash commands as read-only and runs them **without a
> permission prompt in every mode**. These include `ls`, `cat`, `echo`, `pwd`, `head`, `tail`, **`grep`**,
> `find`, `wc`, `which`, `diff`, `stat`, `du`, `cd`, and read-only forms of `git`. The set is not
> configurable…»

> «A `cd` into a path inside your working directory … is also read-only, and **a compound command like
> `cd packages/api && ls` runs without a prompt when each part qualifies on its own.**»

Исключения, при которых read-only-команда **всё равно** спрашивает (дословный перечень):
- «**Unquoted globs for commands with write-capable flags**: commands with write-capable or exec-capable
  flags, such as `find`, `sort`, `sed`, and `git`, prompt when an unquoted glob is present, because the
  glob could expand to a flag like `-delete`.»
- «`docker` pointed at another daemon» · «`file` with path-opening flags» · «Network paths on Windows».
- «**Commands the analysis can't parse**: when Claude Code can't fully parse a command, it asks for
  approval instead of treating the command as read-only. **Commands longer than 10,000 characters always
  prompt**.»
- `cd` + `git` (смена каталога → чужие хуки) и `cd` + редирект, чей таргет не резолвится.

Смежное, важное для нашей конфигурации:
> «A rule like `Bash(command:rm *)` would be bypassable by a compound command, so Claude Code **ignores it
> and emits a startup warning**. Use `Bash(rm *)` … instead.»
> «Bash permission patterns that try to constrain command arguments are **fragile**» (пример с `curl`),
> рекомендованные альтернативы — deny-правила + `WebFetch(domain:…)`, **PreToolUse-хуки**, CLAUDE.md-гайд.

Обёртки: strip'аются `timeout`/`time`/`nice`/`nohup`/`stdbuf`/`command`/`builtin`/`noglob` и **голый**
`xargs`; НЕ strip'аются `direnv exec`/`devbox run`/`mise exec`/`npx`/`docker exec`; `watch`/`setsid`/
`ionice`/`flock` и `find -exec|-delete` **всегда** спрашивают.

### Repo-grounded: у нас это уже реализовано с обеих сторон

`packages/harness/configs/claude-code/hooks/auto-approve/lib/analyze.sh:64-101` — функция `_segments`
режет команду по `$(`, backtick, `&&`, `||`, `|`, `;`, `(){}<>&`, затем `_segment_ok` проверяет **голову
каждого сегмента** против allow-множества (`config.json:allow` — `ls/cat/head/tail/wc/stat/file/find/
grep/egrep/fgrep/rg/ag/tree/which/…`), со снятием ведущих присваиваний и обёрток. То есть **«ось B»
(компаунд-парсинг read-only) в нашем хуке уже есть**, и одновременно тот же разбор делает сам движок.

### Следствие для формулировки OQ-5 (синтез, не вердикт)

Вопрос владельцу меняет форму: не «строить ли компаунд-парсинг auto-approve» (построено дважды), а
**«почему при двух работающих разборах на полном окне осталось 16 компаунд-read-only DENY (бакет a) и
36 атомарных needs-Owner (бакет c, крупнейшая форма — `grep -rn "…"`, 16×, 5 проектов)»**. Из
first-party выше следуют три конкретных проверяемых объяснения, которых у P4.1 не было:
(1) unquoted-glob при write-capable флагах (`find`/`sed`/`git`) — часть форм бакета c именно такие;
(2) «analysis can't parse» → prompt (в т.ч. команды >10 000 символов);
(3) `cd` + `git` / `cd` + редирект.
Плюс гипотеза P4.1 `[POSSIBLE-DEFECT]` «хук не активен в части проектов» — остаётся, но теперь она
**не единственная** и проверяется дешевле (форма против перечня исключений).

## 3. FC-8 — вход для OQ-5, ось C (dedicated permission-friction сигнал)

Ось C формулировалась как «завести в run-report отдельный сигнал `permission_friction` сверх сырья
`tool_failures`». **Отрицательный результат для «изобретать своё»:** first-party телеметрия Claude Code
уже несёт ровно этот сигнал (WebFetch `/docs/en/monitoring-usage`, 2026-07-25) —

- событие **`claude_code.tool_decision`** с атрибутами `decision` (`accept`|`reject`), `source`
  (`config` | `hook` | `user_permanent` | `user_temporary` | `user_abort` | `user_reject`), `tool_name`,
  `tool_use_id`, `tool_source` (`builtin`|`mcp`|…);
- событие `claude_code.tool_result` (`success`, `duration_ms`, `error_type`, `decision_source`).

Цена: требуется OpenTelemetry-контур (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_LOGS_EXPORTER=otlp`,
`OTEL_EXPORTER_OTLP_ENDPOINT=…`), то есть **резидентный коллектор** — против нашего файлового run-report
(SessionEnd-хук harness) это другой класс инфраструктуры.

**Следствие (синтез):** ось C сводится к выбору владельца «adopt first-party OTel-контур vs остаться на
`tool_failures` в run-report», а не «проектировать новый сигнал». Ключевое преимущество first-party:
`source` различает `config`/`hook`/`user_reject` — именно та разбивка, которой не хватило P4.1, чтобы
отделить «политика запретила» от «хук не сработал».

## Проверка

- Проверено (first-party, WebFetch 2026-07-25): компаунд-семантика permission-правил, built-in read-only
  набор и его исключения, обёртки, предупреждение про `Bash(command:…)`; OTel-события `tool_decision`/
  `tool_result` и их атрибуты.
- Проверено (repo-grounded): `analyze.sh:64-101` + `config.json:allow` — компаунд-разбор в нашем хуке
  существует; `P3-routing-audit.md` §3 и `P4-deny-inventory.md` — исходные формулировки OQ-4/OQ-5.
- Проверено (RAG ✅ 2026-07-25, perplexity web+social + бандл-скилл `claude-api`): цены Opus 5/Sonnet 5,
  позиционирование, типовые деградации при downgrade research-агента.
- **Непроверенное → помечено:** вендорского замера «citation fidelity Opus 5 vs Sonnet 5» не найдено —
  свидетельство косвенное; собственного A/B у нас нет (это и есть предмет OQ-4). Причина 16 компаунд-DENY
  и 36 атомарных needs-Owner **не установлена** — first-party дал перечень кандидатов-объяснений, но
  сверка конкретных форм с исключениями не проводилась (работа P3.3, а до неё — вход владельцу).
</content>
