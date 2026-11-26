---
name: operations-cx-super-skill
bucket: operator
version: 1.0.0
description: Broad operations/CX-bucket navigator (composite of external CX skills). For specific work prefer the granular skill — incidents→incident-response, postmortem→postmortem, on-call→oncall-rotation, capacity→capacity-planning, runbooks→runbook. Use only for a cross-cutting overview when no single skill fits.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Operations & CX Super-Skill (navigator)

Thin navigator. The full upstream body (~75KB) lives in [references/full.md](references/full.md).
For a specific task prefer the granular native skill: `operator/incident-response` ·
`operator/postmortem` · `operator/oncall-rotation` · `operator/capacity-planning` ·
`operator/runbook`. Open the reference only for cross-cutting operations/CX questions no granular
skill covers.

**Rule: open references/full.md at the section answering the concrete question — never whole.**

## Section map (anchors in references/full.md)

| Topic | Section |
|---|---|
| Source-skill coverage matrix | [Gap Analysis](references/full.md#gap-analysis-source-skills-vs-this-super-skill) |
| Ticket triage, priorities, SLA | [Section 2](references/full.md#section-2--ticket-triage--classification) |
| Customer response drafting | [Section 3](references/full.md#section-3--customer-response-drafting) |
| Escalation tiers & format | [Section 4](references/full.md#section-4--escalation-management) |
| Customer research, confidence | [Section 5](references/full.md#section-5--customer-research--investigation) |
| Knowledge base management | [Section 6](references/full.md#section-6--knowledge-base-management) |
| Portfolio PM: WSJF/RICE, risk | [Section 7](references/full.md#section-7--project-management--portfolio) |
| Sprint & agile operations | [Section 8](references/full.md#section-8--sprint--agile-operations) |
| File/document organization | [Section 9](references/full.md#section-9--file--document-organization) |
| Invoice/financial processing | [Section 10](references/full.md#section-10--invoice--financial-document-processing) |
| Verification & planning | [Section 11](references/full.md#section-11--operational-quality--verification) |
| Perplexity Computer specifics | [Section 12](references/full.md#section-12--unique-perplexity-computer-capabilities) |
| Cross-domain workflows, cards | [Appendices A–C](references/full.md#appendix-a--cross-domain-workflow-ticket-to-resolution) |
