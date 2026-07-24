# HANDOFF — 2026-07-24 — after P4

**Next:** waiting: Owner decision по AUDIT-CAP design 2/2 → manual: frontier/xhigh

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `—` |
| Context | `cold-start — plan-step` |
| Суть | Зафиксировать решение владельца по двум blocker'ам финального design audit; P0.1 и remediation не запускать без новой authority |

```bash
# НЕ раньше: Dmitry Vostrikov выбирает явное решение по AUDIT-CAP design 2/2
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION Owner decision boundary for 2026.07.24-AGENT-RELIABILITY after final design audit attempt 2/2 RED. Do not execute P0.1, do not repair the plan, and do not start a third design audit. Read AGENTS.md, CLAUDE.md, plans/2026.07.24-AGENT-RELIABILITY/findings/08-design-audit-red-attempt-2.md, plan.md, phases/P0.md, phases/P1.md and handoff.md. Present Dmitry Vostrikov only the exact capped choice: (A) stop/kill this plan, or (B) explicitly override the two-audit cap and grant new authority for a redesigned executable contract plus a later independent audit. Record no package, docs, plan-item, FOREMAN, fleet or consumer changes until the owner chooses.'
```

**Done:** Fresh frontier/xhigh adversarial design audit attempt 2/2 completed
without executing P0 or changing package/docs/runtime sources. Live preflight was
green (`codex doctor`, effective hook executability plus synthetic SessionStart
probe, `maind health`, installed plugin inventory). All four committed-bundle
commands and scoped `plan-lint` ran green. The audit nevertheless returned
literal RED because two executable-contract blockers remain:

1. P0.1 promises semantic provenance/redaction/selection and corrected
   denominator/dedup verification by the immutable committed
   `verify_source_bundle.py`, but that verifier only checks hashes, required
   fields/case IDs and a few stored constants; P0.1 cannot edit it.
2. P1.2 promises 13 generated thin root adapters, but none of the 13 identities
   has a canonical source under `packages/skiller/skills/`; the named registry
   writer does not own root `.agents/skills`, `skillset.py` is outside Files,
   and the required canonical `skill-authoring` path does not exist.

The canonical report is
`findings/08-design-audit-red-attempt-2.md`. This is the capped second verdict:
no repair or third audit has been assigned.

**Remaining:** Owner decision only. P0.1, all implementation/remediation,
package/docs/changelog changes, P4 structural work and any
fleet/consumer/FOREMAN/tag/push/release action remain unauthorized.

**Sources of truth:** `plans/2026.07.24-AGENT-RELIABILITY/findings/08-design-audit-red-attempt-2.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/plan.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/roadmap.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P0.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/phases/P1.md` ·
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/verify_source_bundle.py` ·
`AGENTS.md` · `packages/skiller/CLAUDE.md`.

**Open risks:** The two blockers above make the declared execution contract
unachievable as written. Existing planned risks also remain: causal weights are
unknown until valid P0 evidence verification; the hook before-state is
intentionally red until an approved P0.4; current root discovery still has 12
core/task collisions. A green live environment does not waive a red plan
contract.

**Workarounds/Deferred/Open questions:**
- workarounds: none; accepting hash-green output as semantic verification or
  hand-authoring the 13 adapters would contradict the plan's own fail-closed and
  generator-ownership rules;
- deferred: all plan execution and remediation pending the owner boundary;
- open_questions: Dmitry Vostrikov must choose exactly (A) stop/kill this plan,
  or (B) explicitly override the two-audit cap and grant new authority for a
  redesigned executable contract plus a later independent audit.
