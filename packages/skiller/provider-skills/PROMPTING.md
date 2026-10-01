# Provider-prompting — universal principles (SSOT)

Provider-agnostic core methodology for working with AI-providers in the dev chain. **The universal lives
here** (package canon); personal orchestration (specific models/tools/flow) — at the consumer
(e.g. Brain `40-AI/Workflow/`), which references this file.

> Difference from `provider-skills/<provider>/`: those are ready **skills-roles** to insert into the provider;
> this file - **principles of promting** (how to formulate queries), common to everyone.

## Roles of providers in the chain (separation of responsibilities)

| Stage | Provider type | Task |
|:--|:--|:--|
| Research | research-engine (web+sources) | current data, references, best practices, primary technical specifications with sources |
| Design | reasoning-engine | detailed technical specifications, architecture, patterns (at the input - research-entire output) |
| Implementation | cheap model (IDE) | code according to technical specifications |
| Review | reasoning + research | quality + checking relevance |

Key: **different tasks - different providers**; not to be confused «performer» and «thinker».

## Universal rules

1. **Block «Resources/Sources» required** y research-provider - source next to each fact; this is
   knowledge base for the next step.
2. **Indicate the year + ecosystem** in the request - otherwise the result may be out of date.
3. **Transfer entire artifacts** between stages (Technical specifications, links) — don't summarize, don't lose context.
4. **Periodic currency-review** for long projects - recheck once every sprint best practices
   (what has changed in 6–12 months).
5. **Role vs one-time promt:** permanent role (My Skills / Custom Instructions / Claude skill) —
   for sustainable behavior; one-time industrial work - for a specific task. Do not mix.
6. **Long/Detailed response** y research-removes the provider «water» is better than short (no need to compress
   needed).
7. **External facts - through RAG, out of memory** (versions/market/«still relevant») — canon `general/verify-claims`.

## Provenance

Distilled from Personal Methodology Brain (`40-AI/Workflow/00-overview.md`,
`40-AI/Workflow/PERPLEXITY/prompting.md`). Personal chain (specific models/tools) remains
there; here is the reused kernel. Pasteable provider-skills - in `provider-skills/<provider>/`.
