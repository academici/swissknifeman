# Retrieval captures — PLAN1 design (2026-10-05)

Tool: `perplexity-web` (MCP `search`, pool `swissknifeman`, called through a stdio client from the design
session). Captures are verbatim provenance, not normative decisions; the synthesis is
`research/01-rag.md`.

| File | Topic | Used by |
|:--|:--|:--|
| `pplx-01.md` | JSON task-plan tools: Task Master, beads, Backlog.md, Spec Kit, OpenSpec, Kiro | D1 |
| `pplx-02.md` | Cheap scout model gathers context before a strong coder (answer truncated by the tool) | D3 |
| `pplx-03.md` | Codex/AGENTS.md instruction overload — official OpenAI guidance | D1, D3, P3.1 |
| `pplx-04.md` | Agent friction/decision log: minimal event schema | D1 (log), P2.1 |
| `pplx-05.md` | stdlib JSON Schema validation and Markdown templating with partials | D1, P1.1, P1.3 |

Not retrieved: the owner's YouTube short (`https://www.youtube.com/shorts/ZweCNMdza8o`) — video content
is not readable by the available tools; D3 relies on `pplx-02.md` and the owner's description instead
`[UNVERIFIED]`.
