# P6 — фактический вход: statusline, compact-события, overconfidence-измерение (слой 1, 2026-07-25)

Захват по карте `research/12-P6-fact-classes.md` (написана ДО поиска, D20). Движки: first-party
дока Claude Code через WebFetch (я сам, НЕ через тул-бедного субагента — см. §2.4 ниже, почему
это оказалось принципиально) + `perplexity-web` (полевая практика). Цитаты дословные.

---

## 1. Контракт statusline-скрипта (FC-1) — first-party `/docs/en/statusline`, 2026-07-25

### 1.1 Форма настройки

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.sh",
    "padding": 2
  }
}
```

Поля объекта: `type` · `command` · **`padding`** (доп. горизонтальный отступ в символах,
дефолт `0`) · **`refreshInterval`** (пере-запуск команды каждые N секунд «in addition to the
event-driven updates», минимум `1`; «Leave it unset to run only on events») ·
**`hideVimModeIndicator`**.

### 1.2 Когда скрипт вызывается — ДОСЛОВНО

> «Your script runs once when a session starts, including when you resume one. After that,
> it runs again when:
> * A new assistant message arrives
> * `/compact` finishes
> * The permission mode changes
> * Vim mode toggles
> * A `refreshInterval` timer elapses, if you set one»

> «Claude Code **debounces updates at 300ms**, so rapid changes batch together and your script
> runs once after the changes stop. **If a new update triggers while your script is still
> running, Claude Code cancels the in-flight script.** If you edit your script, the changes
> appear the next time an update trigger re-runs it.»

Два следствия, которые прямо задают дизайн: (а) **`/compact finishes` — документированный
триггер statusline**, то есть событие «компакт случился» доступно и без хука; (б) **скрипт
может быть убит на середине** — любая логика с побочным эффектом обязана быть либо мгновенной,
либо отсоединённой от процесса скрипта.

### 1.3 Что скрипт получает (поля контекста)

| Поле | Дословно |
|:--|:--|
| `context_window.total_input_tokens`, `.total_output_tokens` | «Token counts currently in the context window, from the most recent API response. Input includes cache reads and writes» (до v2.1.132 — накопительные суммы сессии) |
| `context_window.context_window_size` | «Maximum context window size in tokens. 200000 by default, or 1000000 for models with extended context» |
| `context_window.used_percentage` | «Pre-calculated percentage of context window used» |
| `context_window.remaining_percentage` | «Pre-calculated percentage of context window remaining» |
| `context_window.current_usage` | разбивка токенов последнего вызова |
| `exceeds_200k_tokens` | «Whether the total token count … exceeds 200k. **This is a fixed threshold regardless of actual context window size**» |
| `session_id`, `cwd`, `workspace.*`, `model.*`, `cost.*`, `effort.level`, `rate_limits.*`, `vim.mode`, `fast_mode`, `thinking.enabled` | прочие поля сессии |

**Null-контракт (важно для порога):**
> «`context_window.current_usage`: `null` before the first API call in a session, **and again
> after `/compact` until the next API call repopulates it**»
> «`context_window.used_percentage`, `context_window.remaining_percentage`: **may be `null`
> early in the session**»

То есть порог обязан переживать `null`, а не считать его нулём или падать.

### 1.4 Вывод, размер, кэш

- Многострочный вывод поддержан (каждый `echo` — отдельная строка), ANSI-цвета и OSC-8 ссылки.
- `tput cols` изнутри НЕ работает («Claude Code captures your script's output instead of
  connecting it directly to the terminal»); ширина приходит переменными окружения
  **`COLUMNS`/`LINES`** (v2.1.153+).
- **Таймаута для statusline-скрипта дока НЕ называет** (в отличие от хуков) — единственный
  документированный предохранитель это отмена in-flight при новом апдейте. Значит бюджет
  времени — наша самодисциплина, а не гарантия рантайма. `[UNVERIFIED]` в части «что будет,
  если скрипт висит минуту» — дока молчит.
- Kill-switch существует на уровне настроек: `disableAllHooks` описан как «Disable all hooks
  **and any custom status line**» (`/docs/en/settings`).

### 1.5 FC-2 — попадает ли statusline в контекст модели: НЕТ, дословно

> «**The status line runs locally and does not consume API tokens.** It temporarily hides during
> certain UI interactions, including autocomplete suggestions, the help menu, and permission
> prompts.»

Плюс `/docs/en/costs` рекомендует statusline именно как способ видеть расход: «Use `/usage` to
check your current token usage, or **configure your status line** to display it continuously».

**Прямое следствие для рамки репо:** statusline — НЕ always-on инжект в контекст. Гейт
`skiller budget --first-turn` меряет пять источников (`skills`/`agents`/`claude_md`/`hooks`/
`mcp`), statusline среди них нет ни фактически, ни по существу — ожидаемая дельта гейта **0
токенов**. Гейт от этого не отменяется: он и есть доказательство, что механизм бесплатен по
контексту (иначе утверждение остаётся словом).

---

## 2. Compact-события (FC-3) — first-party `/docs/en/hooks`, 2026-07-25

### 2.1 `PreCompact` и `PostCompact` СУЩЕСТВУЮТ

Полный перечень hook-событий доки на 2026-07-25 (30 событий): `SessionStart`, `Setup`,
`UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse`, `PermissionRequest`, `PermissionDenied`,
`PostToolUse`, `PostToolUseFailure`, `PostToolBatch`, `Notification`, `MessageDisplay`,
`SubagentStart`, `SubagentStop`, `TaskCreated`, `TaskCompleted`, `Stop`, `StopFailure`,
`TeammateIdle`, `InstructionsLoaded`, `ConfigChange`, `CwdChanged`, `FileChanged`,
`WorktreeCreate`, `WorktreeRemove`, **`PreCompact`**, **`PostCompact`**, `Elicitation`,
`ElicitationResult`, `SessionEnd`.

- `PreCompact` — «Before context compaction», матчеры `manual` | `auto`; exit code 2
  **блокирует** компактизацию.
- `PostCompact` — «After context compaction completes», матчеры `manual` | `auto`; блокировать
  не может (stderr только пользователю).

### 2.2 Но контекст-полей хуки по-прежнему НЕ получают

Общие входные поля хуков: `session_id`, `prompt_id`, `transcript_path`, `cwd`,
`permission_mode`, `effort`, `hook_event_name`, `agent_id`, `agent_type`, `model` (только
SessionStart). **Ни одно событие не получает `context_window` / token-usage /
`used_percentage`.**

### 2.3 Порог авто-компакта

`autoCompactEnabled` — дефолт `true`, «Automatically compact the conversation when context
approaches the limit»; выключается настройкой либо env `DISABLE_AUTO_COMPACT`. **Порог
срабатывания не конфигурируется** — настройки для него в справочнике нет.

### 2.4 Расхождение с нашими же источниками — и его причина

| Источник | Утверждение | Вердикт 2026-07-25 |
|:--|:--|:--|
| `configs/claude-code/settings-keys.json` (verified 2026-07-10, CLI 2.1.206) | `PreCompact` есть в `hook_events`, но файл несёт флаг `"hook_events_unverified": true` | **верно** (и флаг честно предупреждал, что перечень не сверен) |
| `findings/rag-2026-07-25.md` §5 | «hook-событий PreCompact/PostCompact в актуальном перечне НЕТ» | **неверно** |
| `plan.md` §5 **D7** | «hooks context-полей не получают, PreCompact-события в актуальной доке нет» | первая половина **верна**, вторая — **неверна**; вывод D7 (носитель `used_percentage` — только statusline) устоял |

Механизм отказа назван в нашем же каноне: §5 собирался делегированием агенту
`claude-code-guide`, у которого в тулсете `Bash, Read, WebFetch, WebSearch` и **нет**
`perplexity-web`/`context7` — ровно случай из `verify-claims` § «Делегирование: не ронять
ступень» («топикально-подходящий агент часто WebSearch-only → делегируя туда, ты МОЛЧА роняешь
лестницу»). Здесь потерялась не глубина, а **полнота перечня**: сводка агента прошла как
исчерпывающий список событий. Это **второй датированный полевой кейс** того же класса, что D20,
и он идёт входом в P6.3 наравне с первым.

---

## 3. Полевая практика statusline-уведомлений (FC-4) — perplexity-web, 2026-07-25

Источник: claudefa.st/blog/tools/statusline-guide + синтез.

- Рекомендованная развязка: **statusline остаётся дешёвым рендерером**, а уведомление —
  отдельный троттлимый побочный эффект. «Keep the status line itself cheap: parse JSON, decide
  whether the context crossed a threshold, and print a tiny string. Move the actual desktop
  notification to a separate throttled side effect».
- Триггер по практике — **пересечение порога** («context usage crossed 60%/80%») с памятью
  предыдущего состояния, «so you only notify once per threshold crossing», а не «уведомлять на
  каждом запуске».
- Троттлинг: marker-файл + mtime · `flock` (защита от конкурентных отправок в бурстах) · PID-файл
  (подавление стека нотификаторов). На практике комбинируются.
- Что ломается (дословный перечень практики):
  1. **скрипт отменяется на середине** из-за нового апдейта в 300 мс-окне — «If the notification
     is emitted late in the script, you can lose the alert entirely or end up with partially
     written state»;
  2. **зомби/осиротевшие подпроцессы**, если нотификатор запущен в фоне, а родитель отменён;
  3. **деградация UI** при медленном скрипте — он идёт на каждом сообщении ассистента;
  4. **невидимые ошибки**: пользователь видит только отрендеренную строку, «stderr and transient
     shell failures often disappear unless you log them yourself».
- Итоговая рекомендация практики: «treat the status line as a read-only renderer and keep
  alerting separate … status line computes state, writes a small marker atomically, and a gated
  notifier emits one desktop notification per threshold crossing with flock or an mtime window».

---

## 4. Compact/clear-практика и потери компактизации (FC-5, FC-6)

### 4.1 Видит ли модель остаток контекста — first-party

`/docs/en/costs`: `/usage` и `/context` — **пользовательские** команды («Use `/usage` to check
your current token usage», «Run `/context` to see what's consuming space»); statusline назван
способом «display it continuously» для человека. Механизма, которым модель изнутри хода читает
фактический процент, дока не описывает. Премиса P6.2 («эвристика по типу задачи, а не по
проценту») подтверждается: процент модели недоступен, а statusline — поверхность человека.

### 4.2 Первопартийный рычаг, которым мы не пользуемся

`/docs/en/costs` документирует **секцию инструкций компактизации в CLAUDE.md**:

```markdown
# Compact instructions

When you are using compact, please focus on test output and code changes
```

плюс адресную форму `/compact Focus on code samples and API usage`. То есть «что сохранить при
компакте» — управляемо декларативно, а не только вручную в момент `/compact`.

### 4.3 Что теряется при компактизации — полевая практика (perplexity-web, 2026-07-25)

- Компакт «keeps the current task, recent files, recent errors, and broad architecture, but it
  can drop **earlier instructions, intermediate decisions, exact snippets**, and subtle style or
  process constraints that were never written to disk».
- Ключевой класс потери: **«почему НЕ выбрали альтернативу»**. «A summary can retain conclusions,
  but it often collapses conditionals, nuance, and the chain of evidence»; «the model may remember
  "what we were doing" while losing "why we chose this"» → агент «rediscovers the same bad
  approach because the guardrail is gone».
- Эвристики границы сессии — по ФОРМЕ задачи, не по проценту: завершённая единица работы ·
  смена фазы research → implementation → verification · следующая задача унаследовала бы
  нерелевантный уклон · «repeated compaction is a sign the task wants to be split».
  Дословно: «compact at a logical breakpoint, not because the percentage crossed some magical
  number».
- Разделение трёх механизмов: «compaction is for continuation, handoff files are for transfer,
  and `/clear` is for reset».
- Оборотная сторона секции в CLAUDE.md: файл «is a scarce, always-on context budget… If you stuff
  it with compaction-specific prose, it becomes noisy, competes with genuinely permanent project
  rules».

---

## 5. Измерение overconfidence и pressure-тестирование (FC-7) — perplexity-web (web+academic), 2026-07-25

Источники синтеза: agentmarketcap.ai (2026-04, tool-use calibration), futureagi.com (2026, eval
metrics guide).

### 5.1 Метрики

Принятый стек: **ECE** (expected calibration error) · **Brier score** · **AUROC** (разделяет ли
уверенность верное от неверного) · **selective/abstention accuracy** · **overconfidence на
неверных ответах** (в цитируемой работе — MCIP, «mean confidence on incorrect predictions»).
Отдельно от них — процессные метрики, ближе всего к нашему случаю: **unsupported-claim rate**
(«claimed without citing a source») и **verification tool-use rate**.

Важное для нас наблюдение работы: «evidence tools can **increase** overconfidence while
verification tools can ground reasoning» — калибровку надо мерить ПО РЕЖИМУ инструмента, а не
одним агрегатом.

### 5.2 Как строят pressure-наборы

Классы кейсов: ambiguity traps (недоспецифицированные задачи) · false-evidence traps
(правдоподобное, но вводящее в заблуждение сырьё) · **tool temptation** («tasks where a quick
answer feels easy, but verification is needed») · conflict cases (два источника противоречат) ·
time-pressure формулировки («socially or linguistically encourage skipping checks»). Для
кодовых агентов сильнейшая форма — «solve it now» + скрытые отказы в репо.

### 5.3 Размеры выборки

«30–50 examples: enough to iterate a rubric or prompt · 50–200: meaningful for a stable per-rubric
calibration estimate · 500+: broad coverage». Ниже 50 «variance is usually too high to trust».
Оговорка: «stratifying matters more than raw size».

### 5.4 Провалы grading'а по ключевым словам — прямо про наш харнес

> «Keyword or regex assertions are fragile because they test **surface form, not actual epistemic
> behavior**. A model can say "I'm not sure", include a citation-looking token, or mention a tool
> call, while still skipping verification internally or fabricating a claim.»

Названные режимы отказа: **form over substance** · **keyword laundering** («includes "source",
"citation", "verified" without real evidence») · **tool-call theater** («invokes a tool
superficially, then ignores the result») · **prompt overfitting** (агент учится триггер-словам
набора). Рекомендация: «use regex only as a **cheap smoke test**; use human or LLM-judge rubrics
for the actual decision».

**Прямое следствие для P6.3:** `skiller eval` грейдит ровно семью текстовыми ассершенами
(`contains`/`not_contains`/`regex`/`not_regex`/`file_exists`/`file_absent`/`min_words`,
`quality/eval.py:42`) — то есть наши pressure-кейсы по построению являются smoke-тестом формы, а
не измерением поведения. Это обязано быть НАЗВАНО в результате item'а, а не подразумеваться;
заявлять по нему «overconfidence устранён» нельзя. Апгрейд до trace/judge-грейдинга — отдельная
тема (кандидат roadmap), не этот item.

---

## 6. Граница «класс A vs класс B» (FC-8) — сверка с уже захваченным

Пробела нет, ответ уже в слое 1 фазы P2 (`findings/P2-opus5-guide.md` §5, §9): гайд про
**самопроверку собственного вывода** («include a final verification step», «use a subagent to
verify», «double-check your answer») — и там же зафиксировано «нет ни слова против верификации
ВНЕШНИХ фактов (RAG)». Правило D15 относит RAG-верификацию внешних фактов к **классу B**
(сохранять). Значит усиление `verify-claims` не противоречит линии P2 — **при условии**, что
добавляемый текст остаётся про ПОКРЫТИЕ ВНЕШНИХ фактов и не превращается в предписание
перепроверять собственный вывод. Граница узкая, поэтому вписана в Implementation Rules P6.3, а
не оставлена на усмотрение.

## 7. `i-have-adhd` (FC-9) — уже захвачено

`findings/rag-2026-07-25.md` §2 (GitHub API + README, 2026-07-25): «10 правил вывода (action
first, нумерация шагов, no preamble/closers, конкретные file:line)». Наш `compact-responses` уже
несёт «No trailing summaries», «No "I'll now…" preambles» и банлист фраз — то есть
`no preamble/closers` покрыт, а `action first` и «конкретные file:line» — нет. Дословные
формулировки берутся из источника В МОМЕНТ правки (README мог измениться), сводка выше —
основание для скоупа, а не текст для копирования.

---

## Проверка (verification status)

- RAG: WebFetch first-party ×3 (`/docs/en/statusline`, `/docs/en/hooks`, `/docs/en/costs`) +
  ×1 (`/docs/en/settings`) — OK; `perplexity-web` ×3 (statusline-практика web+social,
  overconfidence-измерение web+academic, compact-практика web) — OK. Ступень выполнена в
  основном контексте, субагентам не делегирована (осознанно — §2.4).
- Непроверено → ПОВТОРНЫЙ ПРОХОД: поведение рантайма при «скрипт statusline висит долго»
  (таймаута дока не называет) — помечено `[UNVERIFIED]` в §1.4, снимается замером в P6.1, а не
  поиском.
- Обходки/`[POSSIBLE-DEFECT]`: нет.
- Расхождение источников разрешено явно (§2.4): first-party дока побеждает нашу сводку
  2026-07-25 и наш же файл `settings-keys.json` от 2026-07-10; слой 1 задним числом не
  переписывается — `findings/rag-2026-07-25.md` §5 остаётся как есть, поправка живёт здесь и в
  D-логе.
