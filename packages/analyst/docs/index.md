---
layout: home

hero:
  name: analyst
  text: Continuous learning of the ecosystem
  tagline: Deterministic capture «hard-won lessons» from runs Claude Code — with a person at the gate, without auto-recording
  actions:
    - theme: brand
      text: What is analyst
      link: ./guide/
    - theme: alt
      text: CLI and commands
      link: ./guide/cli
    - theme: alt
      text: Architecture
      link: ./architecture

features:
  - title: 🎯 Deterministic capture
    details: digest candidate learns from run-report by high-precision signals (resolved-failure, workaround). Not «guesses insights» — stdlib, on-demand, without a daemon.
  - title: 🧑‍⚖️ Man at the gate
    details: Lesson transition to curated and promotion to the skill - only with the explicit consent of the person. Auto-recording to skills is PROHIBITED - package invariant.
  - title: 🔒 Privacy by design
    details: Raw materials (raw-transcript) — LOCAL-only. Out (to memory mAInd, in cross-project index) goes only abstracted trigger→action. Secrets - follow the link.
  - title: 🌐 Cross-project patterns
    details: scan bypasses the project registry, clusters lessons by Jaccard and detects patterns in ≥N projects - namespace-isolated (pattern from ns:axioma does not flow into someone else's).
  - title: 📈 Confidence-life cycle
    details: recompute recalculates confidence (Beta-average × volume × decay) from append-only events.ndjson → numeric state-machine and shooting ranges. Determinism - we will restore it from the logs.
  - title: 🧩 Bridge to skills (P4)
    details: suggest turns cross-project pattern in DRAFT SKILL.ru.md in staging — person finalizes and promotes. Doesn't write to skills/, does not generate EN, does not register.
---


## Skills

The module plugin ships `session-observer`. The sources live in `packages/analyst/skills/` and are released with the module.
A project receives them through the host-provided `system` bucket of `skiller`: `skiller connect` enables the plugin
`analyst`, and `skiller sync` copies the skills into the project. The `skiller` guide
"Configuration, host buckets and metadata" describes the bucket.
