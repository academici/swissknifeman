---
name: pitch-deck
bucket: founder
version: 0.1.0
description: 10-slide investor deck per YC/Sequoia canon from existing project artifacts
risk: draft
persona: founder
tags: [gtm, market, monetization]
requires: [competitive-analysis, unit-economics, go-to-market]
produces_for: []
outputs: ["docs/01_Business/08_Pitch_Deck.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Pitch Deck

Apply when: user asks for "deck"/"pitch"/"investor presentation" or is going for a round (pre-seed / seed / A).

Output = **markdown describing each slide**, NOT PPTX. Export to .pptx/.pdf is separate via `document-generator` MCP (only if asked).

## Do NOT apply when
- No existing `competitive-analysis` and `unit-economics` — refuse, send user to run those skills first.
- Internal team deck requested — plain markdown, no 10-slide canon.
- Pre-discovery stage (deck before JTBD).

## 10-slide canon (Sequoia / YC hybrid)

| # | Slide | Show | Vault source |
|:---|:---|:---|:---|
| 1 | **Title** | Name, one-liner, contacts, date | `ProjectName.md` |
| 2 | **Problem** | Who hurts, how much, cost of not solving | `00_Idea_Discovery.md` |
| 3 | **Solution** | One MVP screen + how it closes the pain | `01_Concept_and_Monetization.md` + `BRD.md` |
| 4 | **Why now** | Trend / tech / regulation, window of opportunity | `02_Competitive_Analysis.md` + research |
| 5 | **Market size** | TAM / SAM / SOM with sources | research (Perplexity `search_deep`) |
| 6 | **Competition** | Market map + our attack vector | `02_Competitive_Analysis.md` |
| 7 | **Product** | 2–3 key MVP features + screenshot/wireframe | `BRD.md` + `07_Product_Roadmap.md` |
| 8 | **Business model** | How we earn + unit economics LTV/CAC | `03_Monetization_Model.md` + `04_Unit_Economics.md` |
| 9 | **Traction / GTM** | What exists (pilots, waitlist, MAU) + launch plan | `06_Go_To_Market.md` + current metrics |
| 10 | **Team + Ask** | Team, how much, what for, runway | user |

**Optional 11–12:**
- Roadmap (phases from `07_Product_Roadmap.md`)
- Appendix: financial model, tech deep-dive

## Slide rules
1. One thesis per slide.
2. Eye reads in 5s. Title = main thesis, not "Problem" but "3 of 4 SMBs lose 8 hours/week on X".
3. Numbers > epithets. "Fast" = nothing; "3.2× faster than peers" = thesis.
4. Sources: every number on slides 4, 5, 6, 8, 9 — with link / appendix.
5. Visual hierarchy: one main object, rest is support.

## Survey questions BEFORE writing
- Round stage (pre-seed / seed / A) — sets traction-slide depth.
- Ask amount + runway (months) + what for (R&D / GTM / hire).
- Team: names, roles, key past experience.
- Traction available: MAU/MRR/LOI/pilots/waitlist — concrete numbers.
- Deck audience: VC / angel / accelerator (slight tweak per each).

## Agent adds itself
- **Hook on Problem slide.** If pain is weak, rewrite as "X people lose Y because Z".
- **Why-now candidates.** From competitive-analysis + research find 1–2 fresh trends (AI wave, regulatory change, competitor plateau).
- **Competitive vector.** Not just matrix — **one sentence** on our angle (cheaper / faster / niche / new tech / new model).
- **Risk-acknowledgement slide (optional).** If project has obvious risk (DMCA, regulation) — address it yourself in appendix.

## Output file structure

`docs/01_Business/08_Pitch_Deck.md`:

```markdown
---
project: [ProjectName]
stage: pitch-deck
round: [pre-seed | seed | series-a]
ask_usd: [сумма]
runway_months: [число]
created: YYYY-MM-DD
---

# Pitch Deck — [ProjectName]

## Slide 1 — Title
- Заголовок: [ProjectName]
- One-liner: [одна строка]
- Контакт: ...

## Slide 2 — Problem
**Тезис:** [главный hook]
- Кому больно: ...
- Цена нерешения: ...
- Источник: [[00_Idea_Discovery]]

## Slide 3 — Solution
**Тезис:** ...
- Что делаем: ...
- Скриншот / wireframe: [ссылка]
- Почему закрывает боль: ...

## Slide 4 — Why now
**Тезис:** ...
- Тренд / технология: ...
- Окно возможностей: ...

## Slide 5 — Market size
- TAM: $X (источник)
- SAM: $Y (источник)
- SOM: $Z (наш taking)

## Slide 6 — Competition
- Карта: [таблица из 02_Competitive_Analysis]
- Наш вектор атаки: [одно предложение]

## Slide 7 — Product
- Фича 1: ...
- Фича 2: ...
- Фича 3: ...

## Slide 8 — Business model
- Модель: [из 03_Monetization_Model]
- LTV: $X, CAC: $Y, payback: Z мес (из 04_Unit_Economics)

## Slide 9 — Traction / GTM
- Текущее: [цифры]
- План GTM: [из 06_Go_To_Market]

## Slide 10 — Team + Ask
- Команда: [имена, роли]
- Ask: $[сумма] на [runway] мес
- На что: [breakdown]

## (Appendix) — Risk acknowledgement
[если применимо]
```

## Hard prohibitions

FORBIDDEN:
- Numbers without source.
- "Revolutionary", "unique", "no analogs" — without proof.
- "Vision" slide without traction (defer to series A+).
- Financial projections beyond 24 months at pre-seed.
- Hiding a key risk — VCs will find it anyway.

## Export

If user asks .pptx or .pdf:
- Use `document-generator-mcp` (see `docs/ai/mcp-servers.md`).
- Markdown stays source of truth — `.pptx` rebuilt from it each time, not edited separately.

## Related skills

Deck consumes ready artifacts, recomputes nothing. Slide sources:
- `founder/competitive-analysis` — Competition + Why-now slides (market map, attack vector).
- `pm/unit-economics` — Business model slide (LTV/CAC/payback).
- `pm/go-to-market` — Traction / GTM slide (launch plan).
- `founder/idea-discovery` — Problem slide (pain, cost of not solving).
- `pm/monetization-design` — Business model slide (chosen business model).
- `pm/product-roadmap` — Product slide + optional Roadmap.
- `founder/risk-assessment` — optional Risk-acknowledgement slide in appendix.

<!-- ru-source-sha256: f7292354956c8efc9870985459cf8cd1c4af6ed4c7e7175a81915eb2aee832cc -->
