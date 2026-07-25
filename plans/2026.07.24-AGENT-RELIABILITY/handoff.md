# HANDOFF — 2026-07-25 — after P4

`P4` в заголовке — совместимый с plan-lint lifecycle carrier для Design Pass
4/4; executable phase P4 и все её items остаются ⬜ Not started.

**Next:** audit-design: task:plan-audit 2026.07.24-AGENT-RELIABILITY design

`AUDIT-CAP: design — historical 2/2 exhausted; Owner override B exceptional
slot 0/1 before launch. This launch consumes the only slot.`

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `—` |
| Context | `cold-start — plan-step` |
| Суть | Fresh independent audit of redesigned executable contract v1.6.0; no P0.1 or remediation in the audit session |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION exceptional independent design audit for 2026.07.24-AGENT-RELIABILITY after Owner override B. AUDIT-CAP: historical design audits 2/2 remain RED; this is the only exceptional slot 0/1 and consumes it. Read AGENTS.md, CLAUDE.md, task:task-plan-audit and canonical plan-protocol completely; run the full cold-start preflight and scoped plan-lint. Read brief/00-brief.md, brief/01-refinements.md Owner override B, findings/08-design-audit-red-attempt-2.md, plan.md v1.6.0, all phases, roadmap.md, handoff.md and journal.jsonl. Audit independently; do not execute P0.1, repair files, weaken validation or relabel historical RED. Specifically prove F1 is executable with immutable source-evidence bytes plus a P0.1-owned semantic contract/verifier/tests/proof classes, and prove F2 has 13 exact private bilingual canonical sources, normal-publication and consumer vendor/connect exclusion, one registry.py→publication.py generator, 26 thin root targets, version/tree lock and P1.4 exactly-once closure. Then perform the full brief/DoR/routing/Files/Required-Reads/generated-scope sweep. Literal GREEN unlocks P0.1. Any RED or ATTENTION exhausts exceptional 1/1 and returns only an Owner decision boundary; it grants no automatic redesign or further audit.'
```

**Done:** Owner option B is recorded in `brief/01-refinements.md` and D29.
The historical design audit attempts 1/2 and 2/2 remain RED. The one
authorized redesign pass 4/4 changed only plan artifacts, kept all 21 items
not started and did not execute P0.1.

F1 is structurally repaired in the executable specification:

1. immutable `artifacts/source-evidence/verify_source_bundle.py` keeps only
   its actual integrity/pinned checks and is not edited;
2. P0.1 owns Source Evidence Verification v1, a machine contract, stdlib
   semantic verifier, mutation tests and deterministic report;
3. manifest/session/corpus/journal/baseline cross-checks are executable, while
   excluded raw-session dedup and classifier-derived numbers are explicitly
   `pinned-not-recomputable`/`unknown`, never semantically verified.

F2 is structurally repaired in P1:

1. P1.1 freezes exact migration seeds and 13
   `packages/skiller/skills/repository-bootstrap/<name>/{SKILL.ru.md,SKILL.md}`
   targets;
2. the bucket is private/source-only: indexed for ownership but excluded from
   normal Claude/Codex bucket, core, marketplace and consumer vendor/connect
   publication;
3. the sole `registry.py`→`publication.py` path emits 13 thin Claude plus 13
   thin Codex root adapters and one `repository-bootstrap@0.1.0` source/tree
   lock; `skillset.py` enforces consumer exclusion but is explicitly not this
   producer;
4. P1.4 validates canonical hash/provenance/private exclusion and per-provider
   exactly-once resolution together with the 12 core/task collision removals.

**Remaining:** Run the single exceptional independent audit only. P0.1 and
all implementation/package/docs/changelog/runtime changes remain blocked
until literal GREEN. G0 still blocks behavior after P0.3; G1 still owns all
fleet/consumer/FOREMAN/tag/push/release authority.

**Sources of truth:** `plans/2026.07.24-AGENT-RELIABILITY/brief/01-refinements.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/findings/08-design-audit-red-attempt-2.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/plan.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P0.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P1.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/roadmap.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/journal.jsonl`.

**Open risks:** P0.1 may legitimately leave causal/raw-session quantities
non-recomputable; downstream acceptance must not promote them. P1.2 is a large
but closed generator transaction and must preserve the private-bucket exclusion
and unaffected publication units byte-identically. Audit outcome is not
prejudged by this redesign.

**Workarounds/Deferred/Open questions:**
- workarounds: none; no hash-green-as-semantic-proof, manual root copy, private
  bucket marketplace publication or conditional collision suppression is
  accepted;
- deferred: all implementation until exceptional audit GREEN;
- open_questions: none before audit. A non-GREEN verdict creates a new Owner
  decision boundary because exceptional audit authority is exhausted.
