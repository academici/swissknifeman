---
id: D10
date: 2026-09-09
status: accepted
item: P5.1
items: [P5.1, P5.2]
supersedes: []
superseded_by: null
---
# D10 — Evidence-first field promotion without fleet mutation

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:— `findings/06-p5-design-baseline.md`; `research/06-p5-field-gaps.md`; current Skiller, Analyst and Task sources

## Решение

P5 produces two evidence contracts instead of mass edits. P5.1 joins the existing description
ratchet to existing budget/direct-usage metrics and treats zero or resident-only visibility as
insufficient for a routing-failure verdict. P5.2 scans only declared registered plan roots,
statically parses workflow files without executing them, deduplicates exact mirrors by digest and
counts Rule of Three across distinct plan identities. Analyst may refine an existing Task template
only when three plans prove an uncovered slot/guard; a new template family or mandatory-stage
matrix change remains a report-only proposal requiring a later decision. Registered projects and
vaults are read-only throughout.

## Почему

The current trigger debt is real but its live usage sample is incomplete, so bulk rewriting would
optimize an alphabetical list rather than an observed failure. The workflow corpus is large enough
for synthesis but contains local/vault mirrors and legacy files, so path counts and code execution
would produce unsafe evidence. One versioned report per gap makes uncertainty explicit and lets
future authors reuse the result without reopening the whole fleet.

## Consequences

P5 can close green with a deterministic queue and a `covered`/`hold` workflow verdict even when no
skill or Task template content changes. Any actual existing-template refinement must cite three
distinct-plan evidence records and pass focused fixtures. Description content continues to burn
down only through separately justified skill edits; automatic cross-project writes, skill
promotion, fifth-template creation and workflow matrix redesign remain forbidden in P5.
