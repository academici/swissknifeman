# References — directory of external sources

Analysis of external repositories and skill marketplaces: what is it, what is it **worth taking
selectively**, what is not needed, and the current status. This is the selection documentation - files from here
do not fall into `skills.json` and are not installed in projects.

> Not to be confused with `skills/oss-dev/references/` — these are language reference-files inside
> bucket-a oss-dev (part of the skill content).

## Selection principle

From sources we take **not everything, but only what really fits** for my scripts:
documentation, Obsidian vault, TK, PHP-packages (Laravel), large Laravel-projects.
Solution for each skill/snippet - separate. Import is processed through
`upstream.json` in the skill folder (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

## Statuses

| Status | Meaning |
|---|---|
| `planned` | The source has been studied, candidates have been selected, import has not yet been done |
| `imported` | Something has already been taken (there are skills with `upstream.json` to this source) |
| `rejected` | Reviewed and rejected (reason in the file) |
| `trusted` | We do not import - we trust locally in projects; the registry complements, does not duplicate |

## Index

| Source | Value | Status |
|---|---|---|
| [laravel/boost](laravel-boost.md) | Version-specific Laravel-skills + MCP + generator CLAUDE.md | trusted |
| [laravel/docs](laravel-docs.md) | Official documentation Laravel (chapters → distillates) | imported |
| [spatie/guidelines.spatie.be](spatie-guidelines.md) | Guidelines Spatie: code-style PHP/JS | imported |
| [sickn33/antigravity-awesome-skills](sickn33-antigravity-awesome-skills.md) | Source docker-expert | imported |
| [get-zeked/perplexity-super-skills](get-zeked-perplexity-super-skills.md) | 12 super-skills, gap-analysis format | imported |
| [anthropics/claude-code](anthropics-claude-code.md) | Official Specification SKILL.md | imported |
| [anthropics/skills](anthropics-skills.md) | Official collection of skills Anthropic (Apache-2.0) | imported |
| [VoltAgent/awesome-agent-skills](voltagent-awesome-agent-skills.md) | Curated index of official skills | planned |
| [jpcaparas/superpowers-laravel](jpcaparas-superpowers-laravel.md) | Laravel workflow-skills (TDD, debug, plan) | planned |
| [skills.laravel.cloud](skills-laravel-cloud.md) | Laravel-marketplace, 175 skills | planned |
| [mwguerra/claude-code-plugins](mwguerra-claude-code-plugins.md) | Obsidian-vault integration | planned |
| [muratcankoylan/Agent-Skills-for-Context-Engineering](muratcankoylan-context-engineering.md) | Context engineering principles | planned |
| [PatrickJS/awesome-cursorrules](patrickjs-awesome-cursorrules.md) | 500+ rules → snippet source | planned |
| [anthropics/knowledge-work-plugins](anthropics-knowledge-work-plugins.md) | Official plugin-architecture | planned |
| [alexeymezenin/laravel-best-practices](alexeymezenin-laravel-best-practices.md) | 40+ Laravel best practices (bad/good) | planned |
| [LaravelDaily/laravel-tips](laraveldaily-laravel-tips.md) | 1000+ Laravel tips | planned |
| [WendellAdriel/laravel-expressive](wendelladriel-laravel-expressive.md) | 8 development skills Laravel-packages → `php/` | imported |
| [adr/madr](adr-madr.md) | MADR templates ADR | planned |
| [nicholasjconn/docker-best-practices](nicholasjconn-docker-best-practices.md) | Docker patterns | planned |
| [DenisSergeevitch/agents-best-practices](denissergeevitch-agents-best-practices.md) | Agent workflow-patterns | planned |
| [mattpocock/skills](mattpocock-skills.md) | Engineering methodology (debug/TDD/deep-modules/grilling/triage) | imported |
