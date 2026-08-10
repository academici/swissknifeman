# RAG — session continuity and adaptive review

Verification date: 2026-08-08.

Question: must a blocked/escalated plan item always leave the executor session for a fresh audit or
research session, and must execution then start yet another session?

## R23 — a manager can retain control while a specialist runs in an isolated context

- OpenAI's practical guide distinguishes a manager pattern, where one central agent retains control
  and calls specialists, from handoffs, where the specialist becomes the active agent:
  <https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/>.
- The OpenAI Agents SDK documents the same distinction as `agents as tools` versus `handoffs`.
  A nested agent can receive a bounded structured input and return its result while the parent
  continues; it does not automatically inherit the full parent conversation:
  <https://openai.github.io/openai-agents-python/multi_agent/>,
  <https://openai.github.io/openai-agents-python/tools/>,
  <https://openai.github.io/openai-agents-python/handoffs/>.
- The SDK's human-in-the-loop documentation also models an interrupted run as resumable state rather
  than a requirement to rebuild the whole run from scratch:
  <https://openai.github.io/openai-agents-python/human_in_the_loop/>.

Verdict: a fresh reviewer context and continuity of the root executor are compatible. The reviewer
can be an isolated specialist call that returns a bounded verdict to the root run. `RAG:✅`.

## R24 — separate contexts pay only when the task justifies their overhead

- Anthropic's multi-agent research report says subagents use separate context windows and return
  condensed results. It also reports substantial overhead in its research system and explicitly
  warns that multi-agent designs fit breadth-heavy parallel research better than tightly dependent
  coding work. Its orchestrator scales effort and avoids spawning agents for simple work:
  <https://www.anthropic.com/engineering/multi-agent-research-system>.
- Anthropic's context-engineering guidance treats compaction, persistent notes, and subagents as
  different tools: subagents are for complex analysis; persistent artifacts preserve long-horizon
  state; context should be curated rather than copied wholesale:
  <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>.
- Its agent-design guidance recommends adding evaluator/optimizer and parallel patterns selectively,
  when their additional complexity produces value:
  <https://www.anthropic.com/engineering/building-effective-agents>.

Verdict: an automatic audit on every first local failure is not supported. A deterministic local
repair should stay in the executor session; isolation is justified by risk, ambiguity, independence,
or repeated failure. `RAG:✅`.

## R25 — boundary of the evidence

The sources support the architectural distinction, not a universal numeric retry limit. The exact
ladder in this plan therefore reuses its repo-grounded durable fingerprint and existing
`same_return_max = 2`: first occurrence permits one local repair, second occurrence of the same
fingerprint requires isolated review, and the third reaches the existing owner gate. The reported
multi-agent cost multiplier in Anthropic's research system is not generalized to this repository.

## Design consequence

Keep three axes independent:

1. root execution-session continuity;
2. freshness/independence of reviewer context;
3. reviewer model class and effort.

The default is `continue-root`. A scoped isolated reviewer is a child/tool call and returns control
to the same root run. A new root session is reserved for a measured context boundary, unavailable
nested/resume capability, an unresolved owner pause, or a whole-plan independent audit.
