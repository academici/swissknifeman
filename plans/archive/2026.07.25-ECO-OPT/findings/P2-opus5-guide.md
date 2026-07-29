# Opus 5 prompting guide — полный захват first-party (P2, 2026-07-25)

**Слой:** 1 (сырьё). **Источник:** `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5`
— first-party Anthropic, прочитан WebFetch 2026-07-25 (design pass 2, детализация P2).
**Отношение к `rag-2026-07-25.md` §3:** тот файл — 6-строчная выжимка pass 1; здесь полный
текст рекомендаций с дословными цитатами, чтобы P2.1 (Brain-нота) и P2.2/P2.3 (ревизия
поверхностей) исполнялись по источнику, а не по пересказу. Проектных выводов здесь нет —
классификация и решения живут в `research/01-P2-opus5-revision-map.md` и D14–D18.
RAG:✅ 2026-07-25 (first-party, WebFetch).

## 0. Рамка гайда

Заголовок-подпись: «Behavioral differences and prompting patterns for Claude Opus 5,
covering response verbosity, agentic narration, task scoping, subagent delegation,
self-correction, and output artifacts when thinking is disabled.»

- «It performs well out of the box on existing Claude Opus 4.8 prompts» — миграция НЕ требует
  переписывания промптов; гайд перечисляет ровно те поведения, которые «most often require tuning».
- Смежные first-party доки (линки из гайда): `/docs/en/build-with-claude/effort` ·
  `/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices` (кросс-модельный
  док — целевой линк «общих» рекомендаций для Claude 5 family) ·
  `/docs/en/about-claude/models/migration-guide#migrating-from-claude-opus-4-8-to-claude-opus-5` ·
  `/docs/en/about-claude/models/whats-new-opus-5` · `/docs/en/build-with-claude/context-windows`.

## 1. Capability improvements (что изменилось относительно Opus 4.8)

- **Agentic coding:** сильнейшая сторона — multi-file features, крупные рефакторы, end-to-end.
  «It completes full tasks rather than leaving stubs or placeholders, and it performs best when
  given the complete task specification up front and left to run.»
- **Code review / bug-finding:** высокая точность И полнота; «Accuracy holds at lower effort
  settings, which supports a fast pass at review time and a more thorough pass later».
  Ключевое предупреждение: «If your review prompt says "only report high-severity issues" or
  "be conservative," the model may follow that instruction literally and report less; **ask it to
  report everything and filter in a separate pass instead**.»
- **Efficiency at lower effort:** «`low` and `medium` effort produce strong quality at a fraction
  of the tokens and latency of higher settings. Start with the default (`high`) and adjust based
  on your evals: use `low` and `medium` liberally as your primary control for token cost and
  response time wherever quality holds, and step up to `xhigh` for demanding coding and agentic
  work. **If you carried effort defaults over from a prior model, re-run an effort sweep on your
  own evals.**»
- **Vision:** сильнее на графиках/документах/диаграммах и UI-репликации; «Re-validate any
  prompt-side vision workarounds you tuned for prior models; they may no longer be needed».
- **Long-context:** «1M token context window as both the default and the maximum», качество
  instruction following / tool calling / reasoning держится по всему окну.
- **Office/документы:** многолистовые таблицы с нетривиальными формулами, слайды; стиль/шаблон
  надо задавать промптом.
- **Multi-agent coordination:** «coordinates teams of subagents well, with effective
  writer-verifier patterns and few cases of agents overwriting each other's work. For
  cost-sensitive workloads, cap delegation».

## 2. Response length and verbosity

- Пользовательские ответы длиннее, чем у прежних Opus.
- **Важное разделение рычагов:** «The effort parameter controls how much the model *thinks*
  rather than how much it *says*: lowering effort can reduce thinking volume without reliably
  shortening the visible response. To control response length, prompt for it explicitly.»
- Готовый блок (дословно из гайда):

  ```text
  Keep responses focused, brief, and concise. Keep disclaimers and caveats short, and spend most
  of the response on the main answer. When asked to explain something, give a high-level summary
  unless an in-depth explanation is specifically requested.
  ```

- В длинном system-промпте — продублировать коротким напоминанием ближе к концу:

  ```text
  <tone_preference>
  Keep outputs reasonably concise.
  </tone_preference>
  ```

## 3. User-facing progress updates (нарратив в agentic-работе)

- «Claude Opus 5 narrates readily during agentic work: it tends to announce what it is about to
  do, and its per-message output in agentic sessions is often longer than prior models'.»
- Рычаг — описать КАДЕНЦИЮ и форму, а не запрещать:

  ```text
  Before your first tool call, say in one sentence what you're about to do. While working, give a
  brief update only when you find something important or change direction. When you finish, lead
  with the outcome: your first sentence should answer "what happened" or "what did you find,"
  with supporting detail after it for readers who want it.
  ```

- «Positive examples of the communication style you want tend to be more effective than
  instructions about what not to do.»

## 4. Written deliverable length (файлы на диск)

Отдельно от разговорной многословности: «files that Claude Opus 5 writes to disk (reports,
Markdown documents, summaries) are often longer than on prior models». Готовый блок:

```text
Match the length of written documents to what the task needs: cover the substance, but do not pad
with filler sections, redundant summaries, or boilerplate.
```

## 5. Task scope and over-verification — ЦЕНТРАЛЬНЫЙ анти-паттерн

Дословно: «Claude Opus 5 verifies its own work without being told to. If your prompt contains
explicit verification instructions ("include a final verification step for any non-trivial task,"
"use a subagent to verify"), **remove them**: instructions like these cause over-verification on
Claude Opus 5, and removing them reduces wasted tokens with no loss in quality. **The same applies
to legacy harness scaffolding that adds separate verification steps.**»

Про расширение скоупа: «Claude Opus 5 can also expand the scope of a task, adding steps that
weren't requested or applying its own judgment about what the task should be. For narrow tasks,
constrain scope explicitly:»

```text
Deliver what was asked, at the scope intended. Make routine judgment calls yourself, and check in
only when different readings of the request would lead to materially different work. If the
request seems mistaken or a better approach exists, say so in a sentence and continue with the
task as asked rather than quietly narrowing, widening, or transforming it. Finish the whole task,
and stop short of actions that are clearly beyond what was asked.
```

## 6. Controlling subagent spawning

«Claude Opus 5 delegates to subagents more readily than prior models. Delegation pays off on
genuinely independent, sizeable tracks of work, but it multiplies cost and time when applied to
small tasks. If your harness supports subagents, give explicit guidance on which scenarios warrant
delegation, or set deterministic caps on how many agents can be launched.» Готовый блок:

```text
Delegate to a subagent only for large tasks that are genuinely independent and parallelizable,
such as a wide multi-file investigation. Do not delegate work you can finish yourself in a handful
of tool calls, and do not use subagents to verify or double-check your own work. If one subagent
can complete the task, use one rather than several, and keep spawn counts low.
```

## 7. Self-correction

- «Claude Opus 5 catches and fixes its own mistakes well without prompting. Avoid instructing
  re-checks it already performs ("double-check your answer," "re-verify before responding"); like
  verification instructions, these compound with the model's own behavior and add cost without
  improving results.»
- Модель чаще прежних нарративит собственные исправления; ограничивать так:

  ```text
  Only correct an earlier statement when the error would change the user's code, conclusions, or
  decisions. State corrections plainly and briefly, then continue the task. For slips that change
  nothing for the user, make the fix and move on without noting it.
  ```

## 8. Running with thinking disabled

- Thinking включён по умолчанию; отключить можно только при effort `high` и ниже (migration guide).
- Два артефакта при выключенном thinking: (а) **tool calls as text** — модель пишет вызов тула в
  видимый текст вместо `tool_use`-блока, вызов не исполняется, а утёкший текст остаётся в истории и
  влияет на последующие ходы (чаще всего на tool-heavy нагрузках вроде поиска); (б) **внутренние
  XML-теги** (`<thinking>` и пр.) в видимом ответе.
- «The primary mitigation for both is to keep thinking enabled and control token cost with lower
  effort levels instead of disabling thinking: **for most tasks, thinking enabled at `low` effort
  performs better than thinking disabled at similar cost**.»
- «If your system prompt contains a rule instructing the model not to think or not to reason,
  remove it; that kind of instruction increases tag leakage.»
- Комбинированная смягчающая инструкция (если thinking обязан быть выключен):

  ```text
  When you use a tool, you may say a brief sentence first. If no tool can express what the user
  asked for, say so instead of guessing. Do not include internal or system XML tags in your
  response.
  ```

- «Instructions that call out thinking tags by name are less effective than the general form, so
  avoid naming them specifically.»

## 9. Чего в гайде НЕТ (границы источника — важно для честности ревизии)

- Нет ни слова о том, что доменные acceptance-чеклисты, детерминированные Validation-команды или
  ОТДЕЛЬНЫЕ ревью/аудит-сессии вредны: анти-паттерн сформулирован ровно про инструкции
  само-верификации внутри одной задачи («verify your own work», «double-check your answer»,
  «use a subagent to verify») и про legacy harness-леса вокруг них.
- Нет ни слова против верификации ВНЕШНИХ фактов (RAG): гайд про самопроверку собственного вывода,
  не про эпистемику источников.
- Нет числовых порогов для капов субагентов — «keep spawn counts low» без конкретного N; наш кап
  выбирается нами.
- Нет готовых effort-рекомендаций «под задачу X» — только правило «re-run an effort sweep on your
  own evals»; конкретные уровни — в отдельном доке `/docs/en/build-with-claude/effort`,
  захвачен ниже (§10).

## 10. Effort — отдельный first-party док (`/docs/en/build-with-claude/effort`, WebFetch 2026-07-25)

RAG:✅ 2026-07-25 (first-party). Захвачено ради ревизии effort-пинов (P2.2/P2.3).

**Пять уровней и их назначение (таблица «Effort levels», дословно колонка Typical use case):**

| Уровень | Typical use case |
|:--|:--|
| `max` | «Tasks requiring the deepest possible reasoning and most thorough analysis» |
| `xhigh` | «Long-running agentic and coding tasks (over 30 minutes) with token budgets in the millions» |
| `high` | «Complex reasoning, difficult coding problems, agentic tasks» (= поведение при отсутствии параметра) |
| `medium` | «Agentic tasks that require a balance of speed, cost, and performance» |
| `low` | «Simpler tasks that need the best speed and lowest costs, **such as subagents**» |

- «By default, Claude uses high effort» · «Setting `effort` to `"high"` produces exactly the same
  behavior as omitting the `effort` parameter entirely.»
- «The effort parameter affects **all tokens** in the response, including: text responses …, tool
  calls and function arguments, thinking (when active)» → «lower effort would mean Claude makes
  fewer tool calls». Раздел «Effort with tool use»: низкий effort склеивает операции в меньшее
  число вызовов и идёт к действию без преамбулы; высокий — больше вызовов, план перед действием,
  подробные сводки изменений и более развёрнутые комментарии в коде.
- «Effort is a behavioral signal, not a strict token budget.»

**Recommended effort levels for Claude Opus 5 (раздел целиком, дословно):** «Claude Opus 5 supports
all five effort levels. **Start with `high`, the default**, and adjust based on your evals: step up
to `xhigh` for demanding coding and agentic work, or to `max` when a task justifies unconstrained
token spending, and use `low` and `medium` liberally as your primary control for token cost and
response time wherever your evals show quality holds. If you carried effort settings over from an
earlier model, run a fresh effort sweep on your evals rather than reusing them.» Плюс: «Effort
controls thinking volume, not visible response length» · «On Claude Opus 5, thinking cannot be
disabled at `xhigh` or `max` effort: requests that set `thinking: {"type": "disabled"}` at those
levels return a 400 error» · при `xhigh`/`max` ставить большой `max_tokens` (старт 64k).

**Recommended effort levels for Claude Sonnet 5:** «Claude Sonnet 5 defaults to `high` effort on
the Claude API **and Claude Code**.» · xhigh — «for the hardest coding and agentic tasks» ·
medium — «Cost-saving step-down from the default. Comparable to Claude Sonnet 4.6 at high effort» ·
low — «For high-volume or latency-sensitive workloads. Suitable for chat and non-coding use cases».

**Best practices (раздел):** «Set effort explicitly» · «Test your use case: The impact of effort
levels varies by task type. Evaluate performance on your specific use cases before deploying» ·
«**Hold effort constant within cached conversations:** Changing the effort value between requests
invalidates prompt caching, so vary effort across workloads rather than within a conversation that
relies on cache hits.»

Отдельно (раздел «Changing effort mid-conversation»): «Because effort shapes the rendered prompt,
changing it between requests does not preserve cached prefixes from earlier turns; if you rely on
prompt caching across a long session, pick an effort level at the start and keep it constant.»
Наблюдение для нашей маршрутизации (не решение): наши команды пинят разный effort, поэтому смена
команды внутри одной сессии — это смена effort → инвалидация префикс-кэша; батчинг item'ов
одинакового effort (`Batch` §3 Routing) при прочих равных дешевле разнородного.
