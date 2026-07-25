# HANDOFF — 2026-07-25 — after P4

`P4` в заголовке — совместимый с plan-lint lifecycle carrier для Design Pass
4/4; executable phase P4 и все 21 items остаются ⬜ Not started.

**Next:** manual: frontier/xhigh

`AUDIT-CAP: historical 2/2 exhausted; exceptional 1/1 consumed`.

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `—` |
| Context | `cold-start — plan-step` |
| Native model | `gpt-5.6-sol` |
| Reasoning effort | `xhigh` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Native context | `NEW SESSION` |
| Суть | Terminal Owner decision only after exceptional audit RED; no executable plan step is authorized |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION Owner decision boundary for 2026.07.24-AGENT-RELIABILITY after exceptional independent design audit attempt 3 RED. AUDIT-CAP: historical 2/2 exhausted; exceptional 1/1 consumed. Do not execute P0.1, repair the plan, modify packages/runtime/docs, or start another audit. Read AGENTS.md, CLAUDE.md, plans/2026.07.24-AGENT-RELIABILITY/brief/01-refinements.md, findings/08-design-audit-red-attempt-2.md, findings/09-design-audit-exceptional-attempt-3.md, plan.md, phases/P1.md, phases/P2.md, phases/P3.md, roadmap.md, handoff.md, and journal.jsonl. Present Dmitry Vostrikov only the terminal choice: stop/kill the plan, or explicitly grant a new bounded authority that names the permitted repair scope and any later independent audit. Record no implementation, fleet, consumer, FOREMAN, release, tag, push, or further audit action without that explicit Owner decision.'
```

**Done:** Owner override B's sole fresh exceptional independent audit completed
with literal RED. The historical attempts 1/2 and 2/2 remain RED; this report is
attempt 3 under the one exceptional slot, not a relabelled historical attempt.
No P0.1, package, runtime, docs, release, fleet, consumer, or FOREMAN work ran.

The Pass 4 redesign did repair the original shapes: P0.1 now separates
immutable integrity from an item-owned semantic verifier with closed proof
classes, and P1 names all 13 private bilingual canonical sources, one
`registry.py`→`publication.py` producer, 26 thin roots, exclusion rules, a
combined lock, and P1.4 exactly-once closure. Authority v1.6.1 is also correct.

The exceptional audit nevertheless found three execution-readiness defects:

1. P1.2, P1.3, P2.2, and P2.3 use undefined `ITEM_BASE_SHA` in their
   load-bearing generated-scope validation.
2. P2.3 requires reading absent `review_policy.py` before that same item creates
   it; P3.4 does the same with `canary-cases.json`.
3. P1.1 does not deterministically validate its required exact
   `repository-bootstrap-map.json`.

Full evidence and severity are in
`findings/09-design-audit-exceptional-attempt-3.md`.

**Remaining:** Owner decision only. Current authority permits neither repair,
P0.1, nor another audit. G-EXEC was never reached. G0 and G1 remain untouched.

**Sources of truth:** `plans/2026.07.24-AGENT-RELIABILITY/brief/01-refinements.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/findings/08-design-audit-red-attempt-2.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/findings/09-design-audit-exceptional-attempt-3.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/plan.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P1.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P3.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/roadmap.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/journal.jsonl`.

**Open risks:** any unapproved attempt to infer an item baseline, read a
same-item future artifact, or accept the unvalidated bootstrap map would turn a
frozen plan gate into executor improvisation.

**Workarounds/Deferred/Open questions:**
- workarounds: none authorized;
- deferred: every executable item and every repository/runtime/docs action;
- open_questions: Owner must choose stop/kill, or grant a new explicit bounded
  repair authority and separately state whether a later independent audit is
  permitted.
