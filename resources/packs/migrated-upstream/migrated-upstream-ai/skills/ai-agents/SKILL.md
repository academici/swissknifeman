---
name: ai-agents
description: "Navigator for the AI-agent building reference (vendored super-skill): agent patterns, MCP servers, RAG, subagent coordination, prompt engineering, deployment. Activate when designing AI agents, building MCP servers/RAG pipelines, orchestrating multi-agent systems, or optimizing prompts."
---

# AI Agent Builder — navigator

Thin wrapper over imported super-skill **get-zeked/ai-agent-super-skill** (vendored,
`strategy: fork`). Complete reference (~2700 lines, 12 sections + applications) — in
[`references/source.md`](references/source.md). **Read the required section as required, not in its entirety** —
this saves context (see skill `context-economy`).

> ⚠️ Model IDs and pricing in the directory - example for 2026-06-11 (upstream date).
> Check the current price list: https://www.anthropic.com/pricing. Current ID models - in skill `claude-api`.

## Routing by [`references/source.md`](references/source.md)

| Task | Section |
|:--|:--|
| Pattern selection, gap-opportunity analysis | §1 Gap Analysis |
| Architecture Patterns (ReAct, Plan-Execute, Reflexion, multi-agent) | §2 Agent Architecture & Design Patterns |
| Build MCP-server | §3 MCP Server Development |
| Collect RAG-pipeline | §4 RAG System Construction |
| Coordination of subagents, worktree-insulation | §5 Subagent Coordination |
| Execution planning and verification | §6 Execution Planning & Verification |
| Prompt engineering and optimization | §7 Prompt Engineering & Optimization |
| ML-integration into agents | §8 ML Integration for Agents |
| Creating new skills/capabilities | §9 Skill & Capability Creation |
| Agent backend infrastructure | §10 Backend Infrastructure for Agents |
| Deployment and monitoring | §11 Agent Deployment & Monitoring |
| Features Perplexity Computer | §12 Unique Perplexity Computer Capabilities |
| Quick pattern selection · ADR · rating MCP · typical failures | Applications A–D |

## Maintenance (for registry maintainers)

This is a fork: upstream is mirrored in `references/source.md`, our edits live in this SKILL.md.
Update - `scripts/update-upstreams.sh` (`--check` → when drifting `--apply` puts
`upstream/source.incoming.md` + puts `review_pending`; move what you need here and `--resolve`).
Details - `docs/guide/upstream-sync.md`.
