---
name: marketing-super-skill
bucket: marketing
version: 1.0.0
description: Comprehensive end-to-end marketing skill merging Perplexity Computer's 6 built-in marketing skills with Claude Code's best community marketing skills. Covers campaign planning, brand voice, competitive analysis, SEO, content creation, performance analytics, copywriting frameworks, and marketing ops. Use when planning campaigns, analyzing competitors, creating content, building brand guidelines, tracking marketing metrics, or optimizing conversion funnels.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Marketing Super-Skill (navigator)

Thin navigator over the full upstream playbook stored in
[references/full.md](references/full.md) (~57KB): frameworks, fill-in templates,
and workflows merging Claude Code community marketing skills with Perplexity
Computer's built-in marketing skills.

**Rule: open `references/full.md` selectively — jump to the one section that
answers the current question. Never load the whole file into context.**

## Section map (anchors in references/full.md)

| Need | Open section |
|:--|:--|
| What Claude Code vs Computer each cover, feature matrix | [Gap Analysis](references/full.md#gap-analysis) |
| Blog posts, video scripts, repurposing, captions, headline formulas, SEO briefs, content calendar | [Content Creation & SEO](references/full.md#merged-skill-content-creation--seo) |
| Campaign briefs, demand-gen playbook, launch checklist, experiment log, budget allocation | [Campaign Planning & Demand Gen](references/full.md#merged-skill-campaign-planning--demand-gen) |
| KPI dashboards, attribution, UTM taxonomy, cohorts, MMM, incrementality testing | [Analytics & Performance](references/full.md#merged-skill-analytics--performance) |
| Competitor battlecards, win/loss analysis, share of voice, positioning maps | [Competitive Intelligence & PMM](references/full.md#merged-skill-competitive-intelligence--pmm) |
| App-store keyword research, listing optimization, CVR, ASO metrics | [App Store Optimization (ASO)](references/full.md#merged-skill-app-store-optimization-aso) |
| Prompting principles + ready marketing prompt library | [Prompt Engineering for Marketing](references/full.md#merged-skill-prompt-engineering-for-marketing) |
| Persona simulation, real-time competitive intel, PR & communications templates | [Unique Computer Capabilities](references/full.md#unique-computer-capabilities-not-in-claude-code) |

## When to use

- Planning a campaign or launch → Campaign Planning section (brief + checklist).
- Writing content/copy/SEO briefs → Content Creation & SEO.
- Measuring or attributing performance → Analytics & Performance.
- Studying competitors or positioning → Competitive Intelligence & PMM.
- Mobile app growth → ASO. Crafting LLM prompts for marketing tasks → Prompt Engineering.
