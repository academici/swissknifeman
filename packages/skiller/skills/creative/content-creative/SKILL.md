---
name: content-creative-super-skill
bucket: creative
version: 1.0.0
description: Comprehensive creative studio skill merging Perplexity Computer's video production, speech synthesis, image generation, and website building with Claude Code's canvas design, algorithmic art, brand guidelines, frontend design, artifacts builder, content frameworks, content calendar, and prompt engineering. Use when creating visual content, designing interfaces, building brands, generating videos/images/audio, writing content, planning content calendars, or doing any creative production work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Content & Creative Super-Skill — Navigator

Thin navigator over the vendored **get-zeked/content-creative-super-skill**. The full
production manual (~90KB: 10 sections, decision trees, appendix) lives in
[`references/full.md`](references/full.md). **Open it point-by-point for the concrete
question at hand — never load the whole file** (context economy).

## Section map ([`references/full.md`](references/full.md))

| Task | Section |
|:--|:--|
| Ecosystem capability comparison, what tool for what | [§1 Gap Analysis Table](references/full.md#section-1-gap-analysis-table) |
| Canvas design, AI image generation, visual briefs | [§2 Visual Design & Canvas](references/full.md#section-2-visual-design--canvas) |
| Brand archetypes, voice framework, identity briefs | [§3 Brand Identity & Guidelines](references/full.md#section-3-brand-identity--guidelines) |
| Web artifacts (React+shadcn), Tailwind patterns, landing pages | [§4 Frontend Design & Web Artifacts](references/full.md#section-4-frontend-design--web-artifacts) |
| p5.js algorithmic art, GIFs, AI video, storyboards | [§5 Generative Art & Animation](references/full.md#section-5-generative-art--animation) |
| TTS, transcription, podcast/voiceover production | [§6 Audio & Speech](references/full.md#section-6-audio--speech) |
| Copywriting workflow, hooks, blog/social/email/SEO/PR templates | [§7 Content Creation & Copywriting](references/full.md#section-7-content-creation--copywriting) |
| Content pillars, monthly calendars, repurposing matrix | [§8 Content Calendar & Planning](references/full.md#section-8-content-calendar--planning) |
| Creative prompt templates and optimization | [§9 Prompt Engineering for Creative Work](references/full.md#section-9-prompt-engineering-for-creative-work) |
| Perplexity Computer native tools | [§10 Unique Perplexity Computer Capabilities](references/full.md#section-10-unique-perplexity-computer-capabilities) |
| Fast method selection · dependency notes | [Decision Trees](references/full.md#quick-reference-decision-trees) · [Appendix](references/full.md#appendix-dependencies-reference) |

## Maintenance (registry maintainers)

Upstream `strategy: notify`; the tracked body is `references/full.md`
(`body_path` in `upstream.json`). This SKILL.md is hand-authored —
`scripts/update-upstreams.sh` never overwrites it.
