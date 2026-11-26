# provider-skills — skills for external agents (paste-in)

SSOT portable **skills-capability for external agents** (Perplexity, etc.), which
are delivered **manual insertion** in UI provider, and not through connect/vendor skill registry.

> Difference from `skills/`: those are loaded by themselves Claude Code (progressive disclosure). `provider-skills/` —
> text that **person copies** in provider (Perplexity → My Skills / Custom Instructions).
> Kanon lives here (versioned, one source); consumers (e.g. Brain
> `40-AI/Workflow/PERPLEXITY/idea-architect.md`) hold **provenance-linked copy** (in the header -
> link to this SSOT, manual resin), is not an independent fork.

## Layout

```
provider-skills/
└── perplexity/
    └── idea-architect.md   # Idea Architect & Startup Auditor (modes Idea/Spec/Architecture)
```

## How to deploy

1. Open the desired file (e.g. `perplexity/idea-architect.md`).
2. Copy body (without service header about deployment) in provider:
   - **Perplexity:** My Skills → Custom Instructions (or file upload if supported).
3. The skill is activated by request type (see «Activation modes» inside).

## Provenance

External methodology (Anthropic Founder's Playbook, CB Insights, Anthropic context-engineering) —
verified via RAG; card in `docs/reference.md`. Edits - here (SSOT), then sync to consumers.
