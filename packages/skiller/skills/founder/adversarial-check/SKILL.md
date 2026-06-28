---
name: adversarial-check
bucket: founder
version: 0.1.0
description: Structured devil's advocate — 3 strongest counterarguments, failed competitors, negative signals, structural obstacles. Antidote to confirmation bias × AI. Cross-stage.
risk: read
persona: founder
tags: [validation, market]
requires: []
produces_for: [idea-discovery, competitive-analysis, risk-assessment, pmf-diagnostics, new-project, startup-lifecycle]
outputs: ["chat"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Adversarial Check

Apply when: any hypothesis / idea / significant decision is formulated and must be pressure-tested before committing resources. Founder's Playbook: *"Using Claude as structured devil's advocate is a core use case at **every** stage of the AI startup life cycle."* AI follows the direction of the prompt — point it the opposite way.

## Do NOT apply when

- No concrete thesis to attack (formulate hypothesis first — `idea-discovery`).
- Pure execution task, no choice (refactor per plan).
- A `risk-assessment` pre-mortem is already running — that's the broader procedure; adversarial-check is more targeted and faster.

## Principles

1. Attack the **strongest** version of the threat, not the convenient one.
2. **Steelman** the opponent — frame the case against as the smartest skeptic with money would.
3. Facts, not taste — anchor each counterargument to a signal/precedent.
4. **Default to refuted** under uncertainty: no data = weakness of the hypothesis, not neutral.

## 4 attack vectors — run thesis through all four

1. **Strongest counterarguments (≥3)** — 3 strongest arguments **against**. Per each: why dangerous + what must be true to neutralize it.
2. **Failed competitors** — who tried this and **failed**? Why exactly? How does your approach structurally differ — or are you repeating the same mistake re-sauced? (antidote to "competitor neglect": `competitive-analysis`).
3. **Negative market signals** — what in data/trends **contradicts** the thesis? Falling demand, regulatory headwind, behavioral patterns against — what a supportive analysis would quietly deprioritize.
4. **Structural obstacles** — what blocks structurally, independent of execution? Distribution barriers, incumbent switching costs, unit economics, laws, competitor network effects.

**Bonus — "argue why competitor wins":** build the **most convincing** case why the competitor in this space succeeds and you don't. Not the convenient version of the threat.

## Stage-context (adapt focus per stage)

Vectors are static — attack priority shifts by stage. Amplify the matching target:

| Stage | Primary attack target |
|:---|:---|
| **idea** | market: is pain real? "no market need"? Why-now? (vectors 1 and 3) |
| **mvp** | retention: do users return or churn after first use? retention > acquisition |
| **launch / scale** | unit economics: CAC < LTV? channel payback? does it scale with growth? |

If stage not given — ask; default `idea`.

## Output

```
## Adversarial check: [thesis]

### Strongest counterarguments
1. [arg] — dangerous because… neutralized if…
2. …
3. …

### Failed competitors
- [who] failed because… we differ / repeat: …

### Negative signals
- …

### Structural obstacles
- …

### Verdict
SURVIVES (hypothesis holds, named risks monitored) /
REVISE (positioning/segment fix needed) /
KILL (structurally unsound) — with rationale.
```

When findings show the idea needs revision — that's the signal to pivot, not a failure.

## Agent adds

- **Catch own confirmation bias** — if prior analysis was suspiciously confirming, name it and re-attack harder.
- **Asymmetry check** — if "pro" far outweighs "con", ask: is this data or what we want to hear?
- **Web-grounding** — for failed competitors / signals, pull `perplexity-web` / real sources, don't invent.

## Related skills

- `founder/idea-discovery` — supplies the hypothesis; adversarial-check follows right after formulation
- `founder/competitive-analysis` — uses "failed competitors" + "argue why competitor wins" vectors (antidote to competitor neglect)
- `founder/risk-assessment` — broader pre-mortem/RAID; adversarial-check is the fast targeted pressure-test
- `founder/startup-lifecycle` — gate-review mandatorily runs adversarial before a PROCEED verdict
- `pm/requirement-critic` — same spirit (skeptic, not author), for BRD requirements

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 30a2108f0df2990ba87a3e209d7dec43672e83c6964f11c522bfbe7f856f6b4a -->
