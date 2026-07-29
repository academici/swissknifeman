# Claude 5 family: Sonnet 5 guide · кросс-модельный док · полевая практика миграции (P2, 2026-07-25)

**Слой:** 1 (сырьё). **Повод:** замечание владельца 2026-07-25 — при детализации P2 RAG свёлся к
двум first-party докам по Opus 5, perplexity-ступень не вызывалась, соседние модели семейства не
читались. Разбор причины (слой 2) — `research/02-P2-rag-coverage-postmortem.md`.
**Дополняет** `findings/P2-opus5-guide.md`, не заменяет.

## 1. Prompting Claude Sonnet 5 — first-party (WebFetch 2026-07-25)

Источник: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5`.
RAG:✅ 2026-07-25 (first-party). **Почему это несущий источник для нас:** implementation-тир
экосистемы — Sonnet, на нём пинятся `dev.md`, `fix.md`, `make-workflow.md`, `plan-exec.md`,
`plan-close.md` (5 из 10 запиненных команд) и большинство агентов agent-packs.

**Ключевое, ломающее рамку «анти-верификация = специфика Opus 5»** (раздел «Tool use triggering»):
«Claude Sonnet 5 is more agentic than Claude Sonnet 4.6 by default and **will reach for tools and
run self-verification loops more readily**.» ⇒ класс A правила D15 применим и к Sonnet-пиненным
поверхностям, а не только к Opus-пиненным.

**«User-facing progress updates»:** «Claude Sonnet 5 provides regular, higher-quality updates to the
user throughout long agentic traces. **If you've added scaffolding to force interim status messages
("After every 3 tool calls, summarize progress"), try removing it.**» ⇒ второй подкласс класса A:
леса принудительных статус-апдейтов, не только верификации.

**«More literal instruction following»:** «Claude Sonnet 5 interprets prompts literally and
explicitly, particularly at lower effort levels. **It does not silently generalize an instruction
from one item to another**, and it does not infer requests you didn't make. … If you need Claude to
apply an instruction broadly, state the scope explicitly (for example, "Apply this formatting to
every section, not just the first one").» ⇒ прямое следствие для наших ТЗ item'ов и команд:
правило, написанное про один объект, НЕ переносится исполнителем на остальные — область действия
надо называть явно. Это касается и `plan-exec`-item'ов, которые пишет `plan-design`.

**«Calibrating effort and thinking depth»** (несущее для D16):

- effort по умолчанию `high` (как и на Sonnet 4.6); `xhigh` — «for the hardest coding and agentic tasks».
- Кросс-модельный мэппинг при миграции: «Claude Sonnet 5 at **medium** is comparable in intelligence
  to Claude Sonnet 4.6 at **high**, and Claude Sonnet 5 at **high** is comparable to Claude Sonnet 4.6
  at **max**. When benchmarking, match by observed thinking length rather than effort name.»
- «Claude Sonnet 5 respects effort levels strictly, especially at the low end. At `low` and `medium`,
  the model scopes its work to what was asked rather than going above and beyond. … on moderately
  complex tasks running at `low` effort there is some risk of under-thinking.»
- «If you observe shallow reasoning on complex problems, **raise effort rather than prompting around it**.»
- adaptive thinking включён по умолчанию; ручной extended thinking (`budget_tokens`) снят — 400.

**«Code review harnesses»** — прямое попадание в наши `review.md`/`plan-audit.md`: «If your
code-review harness was tuned for an earlier model, you may initially see **lower recall** on Claude
Sonnet 5. This is likely a harness effect, not a capability regression. When a review prompt says
things like "only report high-severity issues," "be conservative," or "don't nitpick," Claude Sonnet
5 may follow that instruction more faithfully … Precision typically rises, but measured recall can
fall». Готовая формулировка (дословно):

```text
Report every issue you find, including ones you are uncertain about or consider low-severity. Do not
filter for importance or confidence at this stage - a separate verification step will do that. Your
goal here is coverage: it is better to surface a finding that later gets filtered out than to
silently drop a real bug. For each finding, include your confidence level and an estimated severity
so a downstream filter can rank them.
```

Наш канон уже несёт «Детект ≠ гейтинг. Репортишь ВСЕ находки» — но НЕ несёт второй половины:
«include your **confidence level**» на каждую находку. Это кандидат на «добавить» (класс «добавить»
правила D15), а не на «убрать».

**Новый токенайзер (внутри Note раздела effort):** «Claude Sonnet 5 uses a new tokenizer that
produces **approximately 30% more tokens for the same text**, `max_tokens` limits tuned for Claude
Sonnet 4.6 may truncate equivalent output.» ⇒ прямое следствие для `skiller budget --first-turn`:
пороги (target 3–7K, warn 10K) калиброваны на прежнем токенайзере; та же always-on поверхность
теперь считается иначе. Это факт про инструмент замера, а не про промпт.

**Прочее (в наш скоуп не входит, зафиксировано для полноты):** `temperature`/`top_p`/`top_k` → 400;
дефолтный «house style» на фронтенд-брифах; `computer_20251124`.

## 2. Кросс-модельный док `claude-prompting-best-practices` (WebFetch 2026-07-25)

Источник: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices`.
RAG:✅ 2026-07-25 (first-party). Структура страницы (её собственная формулировка): «**Model-specific
guidance** first … **Techniques for all current models** after that: general principles, output and
formatting, tool use, thinking, and agentic systems. **Migration considerations** last». Явно
перечисляет как актуальные модели: Fable 5, Mythos 5, Opus 5, Opus 4.8, Opus 4.7, Opus 4.6,
Sonnet 5, Sonnet 4.6, Haiku 4.5.

Вывод для P2.1: это правильный целевой линк «общего best-practices дока» (D5) — он же хаб на
per-model гайды. Пересказывать его в ноте не нужно, дать ссылкой.

## 3. Перплексити-синтез: полевая практика миграции (perplexity-web, web+social, 2026-07-25)

Запрос: практика ревизии готовых промптов/команд/харнесов при смене поколения модели — что реально
ломается, какие приёмы удаляют, какие чек-листы применяют. **Статус каждой строки помечен явно** —
синтез смешивает факты по разным моделям семейства (Fable 5 / Mythos / Opus 5 / Sonnet 5), поэтому
дословно принимать нельзя.

**Подтверждает first-party (корроборация, не новое):** удалять explicit verification/self-check;
удалять устаревшие status-update шаблоны; пересмотреть severity-фильтры в code-review промптах;
добавить brevity-инструкции и scope-constraints; в мульти-агентных — явный кап на субагентов или
критерии делегирования; пересчитать токен-бюджеты (+30% токенайзер).

**Новое, чего в прочитанных нами гайдах НЕТ** (и что first-party подтверждением НЕ покрыто):

| Утверждение | Статус | Почему важно нам |
|:--|:--|:--|
| «Anthropic для Claude Code сократил системный промпт **на 80%** при переходе на Fable 5; модели 5-го поколения деградируют от чрезмерно prescriptive инструкций» | **[UNVERIFIED]** — полевой репорт, first-party подтверждения не найдено | Если верно — это про НАШИ команды: `plan-design.md` ~270 строк, `plan-exec.md` ~200. Кандидат в отдельную тему (сжатие инструкционного слоя), пересекается с OQ-4 и P3.1 |
| «Статус-апдейты без привязки к tool results → фабрикованные отчёты о прогрессе» + промпт-противоядие «Before reporting progress, audit each claim against a tool result from this session» | **[UNVERIFIED]** для Opus 5/Sonnet 5 (в синтезе отнесено к Fable 5) | Прямо соседствует с нашим правилом «якорь дерева для чисел» (plan-protocol §8) — если подтвердится, это тот же инвариант, сформулированный со стороны модели |
| Минимум prompt caching снижен 1024 → 512 токенов | **[UNVERIFIED]** | Влияет на экономику, не на скоуп P2 |
| Убрать явный счётчик остатка токенов из контекста модели — «триггерит early stopping» | **[UNVERIFIED]** | Пересекается с P6.1 (statusline context-notify): важно, что уведомление идёт ВЛАДЕЛЬЦУ, а не в контекст модели — наш дизайн уже такой (D7) |
| Слэш-инструмент `/claude-api migrate this project to claude-opus-5` автоматизирует API-часть миграции | частично repo-grounded: скилл `claude-api` в этой сессии доступен | Нашей поверхности (Claude Code команды, не API-вызовы) касается мало |

**Что из синтеза заведомо ВНЕ нашей поверхности:** всё API-уровневое (`thinking:{disabled}`,
`budget_tokens`, `temperature`, assistant prefill, `fallbacks:"default"`, обработка
`stop_reason:"refusal"`). Мы не вызываем Messages API — мы пишем команды и агентов для Claude Code;
из API-слоя нас касается только `effort`, который Claude Code выставляет сам.

## 4. Итог: что этот заход изменил в скоупе P2

1. Класс A правила D15 распространяется на **Sonnet-пиненные** поверхности (`dev`, `fix`,
   `make-workflow`, `plan-exec`, `plan-close`) — Sonnet 5 тоже гоняет self-verification loops.
2. Появился **второй подкласс A**: леса принудительных статус-апдейтов («каждые N шагов —
   сводка»).
3. Появился новый кандидат в класс «добавить»: **confidence level на находку** в
   `review.md`/`plan-audit.md` (у нас есть severity, нет confidence).
4. Появилось следствие для **гейта бюджета**: токенайзер Sonnet 5 даёт ~+30% на том же тексте —
   пороги `skiller budget --first-turn` (3–7K/10K) откалиброваны на прежней шкале.
5. Появился кандидат-тема вне P2: **сжатие инструкционного слоя** (промпты 5-го поколения хотят
   короче) — пересекается с OQ-4 и P3.1, но подтверждения first-party нет ⇒ не действие, а вопрос.
