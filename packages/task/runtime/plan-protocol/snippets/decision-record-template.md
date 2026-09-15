# Decision record — `decisions/<D-id>.md`

```markdown
---
id: <D-id>
date: <YYYY-MM-DD>
status: accepted
item: <Pn.m>
items: [<Pn.m>]
supersedes: []
superseded_by: null
---
# <D-id> — <short decision>

**Actor:** <role/model-class/effort>
**Evidence:** RAG:✅ <date + query/source> | RAG:— <repo evidence> | [UNVERIFIED]

## Решение

<one precise decision>

## Почему

<alternatives and reason>

## Consequences

<affected specs, carriers, consumers, migrations>
```

Use a filename such as `D1-short-decision.md`; `id` contains only `D1`. Keep the YAML keys
and the literal headings `Решение` and `Почему`: they are parser anchors, independent of
the prose language. List every affected item in `items`, including the primary `item`.
For a replacement, set `supersedes: [D1]` on the new record and retain `## Consequences`;
mark the old record `status: superseded` and `superseded_by: D2` reciprocally.

Accepted records are append-only in meaning. Correct with a new superseding record and regenerate
the decision views; do not rewrite history.
