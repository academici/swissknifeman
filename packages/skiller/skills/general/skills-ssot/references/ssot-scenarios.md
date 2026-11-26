# Route by the actual task

These are discovery pointers, not a required skill chain or automatic workflow. Use the
project's selected delivery and concrete stack; `.ai/skills` is only one possible source.

| Task | Relevant owner |
|---|---|
| Code diff review | `quality/code-review`; domain rules only for changed behavior |
| Tests or failed checks | Project test commands and stack testing/isolation skill |
| Auth, secrets, exposure | Relevant security design or stack audit |
| Several affected layers | Trace the affected contract; breadth alone does not start orchestration |
| Skill/guideline drift | `general/skills-ssot`, then the verified owning generator |
| Commits/hooks | Project conventions and actual tooling preflight |

Read only the required references, preserve safety controls, and continue the authorized task
through verification. An optional broader workflow or redesign remains a separate recommendation.
