# Framework Audit — periodic framework audit (Perplexity)

> Role in work flow: **framework auditor**. Unlike [perplexity](./perplexity)
> (research from scratch for a new task), this industrial audits an ALREADY existing
> agent-framework and looking for DELTS: regressions, inconsistencies, new official/OSS-solutions.

You launch it manually periodically. As input you give two files from
[agent-framework](../agent-framework/index.md): `framework-overview` (which already exists) and
`decisions-ledger` (which is accepted/rejected) — then the audit does not re-offer what is ready.

## Pre-flight (required, verifiable)

Run running on rotten input produces false findings: audit 2026-07-29
received `framework-overview` with seven `🔜` with ready implementation and in good faith
proposed to build an already standing ([triage](../audits/2026-07-29-harness-agnostic.md),
meta find). Manual reminder «update review» this failure class has not been caught once -
so the freshness of the input is checked by the machine:

1. Drive away `bash packages/skiller/scripts/validate.sh`. **Red gate of canon freshness**
   (section «framework canon: table „pack → version“ vs `pack.json`») — run does NOT run:
   first the table is repaired in `framework-overview.md`, the gate message carries a fix string.
2. Take the stamp `## Tested against tree: <DATE>` from `framework-overview.md` and substitute
   him in `{{DATE}}` promt. A stamp in the industrial document is required: the auditor is obliged to see what
   number stated input, and call the discrepancy a find.
3. `{{DATE_PAST_AUDIT}}` — last line date `docs/audits/index.md`.

Gate deterministic (version reconciliation, without network and calendar thresholds): he catches exactly that
drift - the docks lagged behind the packs - which broke the 2026-07-29 run. The freshness of PROSE he does not
argues, so step 5 of the cycle below remains the responsibility of the individual.

## Settings Perplexity

- **Length**: `Detailed` (Long).
- **Mode**: Pro Search (fresh sources). `Academic` — for questions about internals Claude Code.

## Loop (what to do with the result)

1. Ran the promt → saved output verbatim in `packages/skiller/docs/audits/<YYYY-MM-DD>-<topic>.raw.md`.
2. Triage: create `<YYYY-MM-DD>-<topic>.md` next - table absorb-now/later/reject + where it landed.
3. Update `decisions-ledger.md` (so that the next audit does not ask again) and
   `packages/skiller/references/framework-audits.md` (ledger-string).
4. Implement absorb-now → CHANGELOG pack + bump versions.
5. Update `framework-overview.md` (including table «pack → version» and stamp
   `## Tested against tree: <DATE>`) → is the input of the NEXT audit, and its freshness
   holds the gate `validate.sh` from pre-flight. The loop has closed.

## Promt (insert into Perplexity)

```
You are auditing MATURE, opined agent-framework for Claude Code — he's ALREADY
exists. Your task is to find DELTAs, and not to design from scratch and not
reoffer ready-made.

## CURRENT FRAMEWORK STATUS (v{{VERSION}}, on {{DATE}})
{{INSERT: framework-overview.md — which already exists (hub/skills-index, field skills:
preload, agent roles, profiles as DATA, review-gate hook, dev-loop work flow with
lessons, package breakdown skiller/harness/maind, status Agent Teams)}}

## ALREADY DECIDED - DO NOT re-offer (you can challenge, but only with NEW evidence):
{{INSERT: decisions-ledger.md — accept/reject/defer + justification. Among reject:
Mustache-agent generation engine, file numbering for priority, file-lock
protocol, format tasks.json, complexity scoring, `extends:`/`@include` from agents.}}

## TASKS
1. REGRESSIONS AND INCONSISTENTS (highest priority). Where the frame can silently break:
   agents/skills «are not visible» (names in skills: give no-op, hub is deprecated, boost
   overwritten CLAUDE.md), drift agent↔skill, conflicting rules between
   CLAUDE.md / hub / agents / .claude/rules/.
2. CHECK conditional clauses ONLY according to OFFICIAL documents (code.claude.com/docs,
   anthropic.com/engineering). For each: CONFIRMED / UNCONFIRMED / REFUTED + accurate URL.
   Current open conventions: {{INSERT list if any}}.
3. NEW solutions with {{DATE_PAST_AUDIT}}: official features Claude Code and noticeable
   OSS (subagents, skills, hooks, orchestration). Only what is NOT in the CURRENT
   CONDITION and ALREADY RESOLVED.
4. For each find - DELTA line (format below). No general best-practice essay.
   Without retelling what is already in the CURRENT STATE.

## OUTPUT FORMAT (strictly)
### A. Regressions / inconsistencies (priority)
| id | symptom | where it hits | fix direction | confidence | source |
### B. Checking conventions
| item | verdict (CONFIRMED/UNCONFIRMED/REFUTED) | official. URL | consequence |
### C. New deltas (features / OSS)
| id | what | where does it go (hub/skill/agent/harness/maind/data) | absorb-now/later/reject (your rec.) | source URL |
### D. Sources
| name | URL | why is it important |

Rules: each statement has a link; official docs take precedence over blogs/video;
mark LOW confidence everything that is only from the video/blog; be specific to the DATA+SKILL
models of this frame (NOT a generator engine); don't offer Python-generator, Mustache,
priority by file numbering or file-lock — they are clearly rejected.
```

## Wording rules

- **Always serve `framework-overview` + `decisions-ledger`** — without them audit
  slides into a re-offer of a ready-made (this happened with the first two audits).
- **Require a check of the conditions according to the OFITIC. docks** — lesson `.claude/rules/` (video/blog
  was incorrectly filed as «not native»/«native»; the official gave the truth. dock).
- **Fixed delta format** — so that the triage is mechanical.
- **LOW confidence on video/blog** — do not build on them without official permission. confirmation.

## What we get

Delta tables → triage in `audits/` → update ledger/overview → implementation. See
[agent-framework](../agent-framework/index.md).
