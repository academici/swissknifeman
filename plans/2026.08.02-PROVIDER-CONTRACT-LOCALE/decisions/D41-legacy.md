---
id: D41
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Locale canonicalization is pinned to one faithfully vendored carrier, `core/locale/data/language-subtag-registry.txt`, with adjacent `upstream.json`: official IANA URL, `File-Date: 2026-06-14`, SHA-256 `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`. P2.1 freezes bytes/provenance, P4.1 implements the stdlib reader and sole explicit update producer, and P7.3 verifies the same identity in docs/release evidence. RAG:✅ 2026-08-03 official IANA registry and RFC 5646 verification in `findings/12-design-audit-remediation-2026-08-03.md`.

## Почему

A host-time registry lookup or duplicated hardcoded subset would let contract checker, runtime and release use different registration/`Preferred-Value` truth; one pinned data carrier preserves reproducibility and shared-core ownership.
