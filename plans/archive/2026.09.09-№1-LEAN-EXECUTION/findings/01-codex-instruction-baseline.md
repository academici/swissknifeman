# Codex instruction and skill baseline — 2026-09-09

## Repository measurements

RAG:— (local CLI/source inspection supplied by the authoring root and independently mapped to the
canonical owners named below).

- `packages/skiller/bin/skiller budget --target . --provider codex --json`: initial listing raw
  8,578 characters, above the 8,000-character fallback budget; 37 skills; tier-1 bodies 60,136
  characters but loaded progressively; description-trigger debt 61.
- Root `AGENTS.md`: 8,586 bytes / 92 lines; estimated effective root instruction weight 2,522
  tokens and root+package paths 3,062–3,451 tokens.
- `.agents/skills/`: 15 generated thin bootstrap projections, 4,038 listing characters; Task has
  11 skills / 1,874 characters and core has 9 / 2,264 characters in the known inventory.
- Canonical AGENTS inputs are
  `packages/harness/configs/common/instructions/catalog.json`, root/provider fragments under
  `packages/harness/configs/common/instructions/`, and package fragments; renderer is
  `packages/harness/lib/harness/instructions.py`.
- Bootstrap skill list owner is `packages/skiller/configs/repository-bootstrap-skills.json`;
  publication owners are `packages/skiller/lib/skiller/{registry,publication}.py` and
  `packages/skiller/adapters/repository-bootstrap/publication-lock.json`.
- Duplicate/noise candidates include overlapping root/package validation and invariant prose,
  always-on Task launch/session procedure, and unmanaged `.bak` files below `.agents/skills/`.
  Current completeness checks validate directories rather than exact managed file membership.

## Environment defect affecting trust

RAG:—. `skiller` reports core/task enabled, while live `codex plugin list` marks installed
`core@0.13.1` and `task@0.13.3` disabled; this session nevertheless exposes their skills. Therefore
no listing/body deletion is admissible before a Codex-native cold-start probe records command argv,
model, effort, cwd, plugin state and the actual instruction/skill sources seen by the new process.

## External evidence

RAG:✅ 2026-09-09, Perplexity Web advanced restricted by query to official OpenAI sources, then
direct URL cross-check required in P6.1:

- <https://developers.openai.com/codex/agent-configuration/agents-md>
- <https://developers.openai.com/codex/build-skills>
- <https://developers.openai.com/blog/eval-skills>
- <https://developers.openai.com/api/docs/guides/latest-model>
- <https://developers.openai.com/codex/learn/best-practices>

The official material supports root-to-cwd AGENTS layering, a default 32 KiB combined project-doc
cap, progressive skill disclosure, an initial skill catalogue capped at 2% or 8,000 characters
when context is unknown, description shortening/possible omission, explicit invocation remaining
available when implicit invocation is disabled, and small 10–20 prompt evaluations with positive
and negative controls. It recommends auditing unclear/conflicting instructions and keeping
AGENTS concise. No controlled official evidence was found that blanket skill deletion improves
quality; deletion is a hypothesis to test, not the default conclusion.

## Проверка

- RAG: `perplexity-web search_advanced` query covering all five official fact classes; official
  URLs above, accessed 2026-09-09.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact live plugin/source discrepancy; P6.1 must reproduce it in
  a new Codex root before any mutation.
- Обходки/[POSSIBLE-DEFECT]: current-session skill exposure despite disabled plugin listing is
  recorded as a baseline defect, not treated as green.
