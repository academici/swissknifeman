# Decision record — `decisions/<D-id>.md`

```markdown
# <D-id> — <short decision>

**Date:** <YYYY-MM-DD>
**Status:** accepted | superseded
**Actor:** <role/model-class/effort>
**Evidence:** RAG:✅ <date + query/source> | RAG:— <repo evidence> | [UNVERIFIED]
**Supersedes:** — | <D-id>
**Superseded By:** — | <D-id>

## Decision

<one precise decision>

## Why

<alternatives and reason>

**Consequences:** <affected specs, carriers, consumers, migrations>
```

Accepted records are append-only in meaning. Correct with a new superseding record and regenerate
the decision views; do not rewrite history.
