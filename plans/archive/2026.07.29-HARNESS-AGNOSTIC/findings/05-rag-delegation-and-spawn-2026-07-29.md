# RAG-разведка: делегирование субагенту и критерий спавна — 2026-07-29

Слой 1 (сырьё). Заход дизайна фазы **P4**. Проверяются несущие внешние факты, на которых
стоят items P4.2 (политика спавна) и P4.4 (delegation contract). Лестница: прямой WebFetch
first-party → Perplexity как перекрёстная проверка. Автор — Opus 5/high.

Контекст: `findings/00` §7 (аудит владельца) назвал оба тезиса, но опирался на **пересказ**
(`simonwillison.net`), а не на первоисточник; `phases/P4.md` (скелет) честно нёс
`[UNVERIFIED]` в части точной формулировки. Этот заход закрывает ровно это.

---

## Ф19. Форма задания субагенту — first-party Anthropic, дословно

**Вердикт:** ✅ подтверждён прямым WebFetch
`https://www.anthropic.com/engineering/multi-agent-research-system` (2026-07-29).

Дословная цитата (перечень элементов задания):

> «Each subagent needs an objective, an output format, guidance on the tools and sources to
> use, and clear task boundaries.»

То есть **пять** адресуемых элементов: `objective` · `output format` · `tool guidance` ·
`source guidance` · `task boundaries` (первоисточник склеивает tools и sources одной фразой,
но перечисляет их как две разные «guidance», и наш аудит §7 читал их так же).

Названный режим отказа при неполном задании — дословно:

> «Without detailed task descriptions, agents duplicate work, leave gaps, or fail to find
> necessary information.»

Иллюстрация из статьи: субагенты исследовали разные периоды дефицита чипов без координации →
избыточное дублирование пересекающихся тем.

**Следствие для плана.** `[UNVERIFIED]` из скелета P4.3 снят: тезис аудита воспроизводит
первоисточник дословно, а не в пересказе. Пять элементов становятся закрытым перечнем
обязательных полей delegation contract (P4.2 запечатывает, P4.4 приземляет).

## Ф20. Спавн как КОМПРЕССИЯ контекста, а не как параллелизм — first-party Anthropic

**Вердикт:** ✅ тот же источник, дословно:

> «Subagents facilitate compression by operating in parallel with their own context windows,
> exploring different aspects of the question simultaneously before condensing the most
> important tokens for the lead research agent.»

**Следствие.** Критерий «спавнить по бюджету контекста, а не по размеру задачи»
(`findings/00` §11-правило 4) опирается на first-party формулировку: ценность субагента —
сжатие (много сырья внутри → мало токенов наружу), параллелизм назван СПОСОБОМ, а не целью.

## Ф21. Масштабирование числа субагентов по классу задачи — first-party Anthropic

**Вердикт:** ✅ тот же источник, дословно:

> «Simple fact-finding requires just 1 agent with 3-10 tool calls, direct comparisons might
> need 2-4 subagents with 10-15 calls each, and complex research might use more than 10
> subagents with clearly divided responsibilities.»

**Следствие.** У политики спавна появляется first-party шкала `1 / 2–4 / >10` по классу
задачи — вместо изобретённого порога. Наш собственный «кап делегирования» в командах
(`packages/task/commands/{design,research,review,plan-design}.md`) формулирует ТУ ЖЕ
дисциплину прозой («число спавнов держи низким»), но без числа и без класса задачи.

## Ф22. Изоляция контекста субагента — first-party Claude Code, дословно

**Вердикт:** ✅ подтверждён прямым WebFetch `https://code.claude.com/docs/en/sub-agents`
(2026-07-29; та же страница, что читалась в `findings/04` Ф15/Ф17 — здесь другие абзацы).

Дословно:

> «Use one when a side task would flood your main conversation with search results, logs, or
> file contents you won't reference again: the subagent does that work in its own context and
> returns only the summary.»

> «Each subagent runs in its own context window with a custom system prompt, specific tool
> access, and independent permissions.»

Перечень выгод (дословно, пять пунктов):

> «**Preserve context** by keeping exploration and implementation out of your main
> conversation · **Enforce constraints** by limiting which tools a subagent can use ·
> **Reuse configurations** across projects with user-level subagents · **Specialize
> behavior** with focused system prompts for specific domains · **Control costs** by routing
> tasks to faster, cheaper models like Haiku»

Границы механизмов названы там же: субагенты живут ВНУТРИ одной сессии; независимые
параллельные сессии — `background agents`; общающиеся между собой — `agent teams`.

**Следствие.** Условие спавна у обоих первоисточников формулируется через один и тот же
предикат: «сырьё, к которому родитель БОЛЬШЕ не вернётся». Это делает критерий
проверяемым в форме политики: спавн оправдан, когда (а) ожидаемый объём разведочного сырья
велик, (б) родителю нужна только сводка, (в) сырьё не потребуется на следующих шагах.
Отрицание (в) — прямое противопоказание к спавну, и именно оно сегодня нигде не записано.

## Перекрёстная проверка (Perplexity, тот же день)

Запрос о семантике изоляции контекста Claude Code дал ответ, цитирующий ту же first-party
страницу и совпадающий по существу («main session sees the outcome, not the full chain of
exploration»; «use a subagent for gather/analyze/summarize, keep the main session for
decide/integrate/continue»). Расхождений с прямым чтением не обнаружено — противоречия
разбирать не потребовалось.

## Не проверено (риск принят явно)

- `[UNVERIFIED]` Числа шкалы Ф21 (`1 / 2–4 / >10`) получены на домене deep-research
  Anthropic, а не на нашем домене (кодовая работа в монорепо). Политика берёт их как
  СТАРТОВЫЕ значения с записанным происхождением, а не как измеренную для нас константу;
  калибровка — по факту накопления прогонов (`analyst`), вне скоупа плана.
- `[UNVERIFIED]` Живого замера «сколько токенов сырья реально остаётся в родителе без
  спавна» на наших прогонах не делалось; порог `spawn_threshold` формулируется как
  КЛАСС ситуации (перечислимый предикат), а не как число токенов — число без замера было бы
  выдумкой.
- `[UNVERIFIED]` Поведение Codex CLI при превышении `agents.max_concurrent_threads_per_session`
  (`findings/03` Ф11) вживую не проверялось — round-trip прогон второго провайдера вне
  скоупа плана (D3).
