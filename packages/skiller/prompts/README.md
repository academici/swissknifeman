# prompts — industrial library swissknifeman

Ready-made processes for routine work on the skill register: audit, review, generation. This
**not skills** (they are not seen by the agent in projects) — these are the templates that you hand
paste into Claude Code or Perplexity, when you are accompanying yourself
registry.

```
prompts/
├── audit/      # quality and relevance checks
│   ├── claude-skill-audit.md       # audit of one SKILL.md (Claude)
│   ├── claude-repo-audit.md        # audit of the entire registry (Claude)
│   ├── perplexity-repo-audit.md    # external repository audit (Perplexity)
│   └── perplexity-tech-radar.md    # relevance of technology/versions (Perplexity)
├── review/     # code review and comparison
│   ├── claude-pr-review.md         # review PR to registry
│   └── claude-skill-compare.md     # comparison of two similar skills (take?)
└── generate/   # creation and transformation
    ├── claude-new-skill.md         # new skill according to the scheme
    ├── claude-compact-skill.md     # compaction SKILL.md
    └── claude-translate-skill.md   # one-time translation of external material for analysis
```

## Models

Where the product mentions the model identifier - use the current ones:
`claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5`. Don't copy outdated ones
id from external audits.

## Communication with tooling

Structural checks (frontmatter, `name==dir`, semver, resolve `requires`, loops)
are already automated in [`scripts/validate.sh`](../scripts/validate.sh) — promty
audit for what the machine does not catch: intersections in meaning, water content, outdated
facts, duplicates. Token budget - `skiller budget` and
[budget map](../docs/guide/budget.md).
