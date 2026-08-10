---
id: D80
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3.4 owns the forward-only admission→provider native-tool projection in the existing adapter modules and their tests; D74/D77 and terminal P1/P2/P3 histories remain unchanged. Claude `tools=[]` must render literal `--tools ""` with no `--allowedTools`; Codex has no proven global no-tool carrier and must return `CAPABILITY_UNSUPPORTED` before process. Installed provider-version drift likewise returns `MAPPING_UNKNOWN` without repinning P0/P3 parity. A minimized non-green readiness row is valid evidence but never provider success/maturity. RAG:✅ 2026-08-04 installed CLI + first-party verification in `findings/P3.4-native-no-tool-verification-2026-08-04.md`; RAG:— (repo-grounded: D34/D36/D74/D77, frozen admission bytes and `research/24-p3.4-native-tool-projection-design.md`).

## Почему

Exact authority stays stricter than implementation convenience: the runner cannot widen tools or fake parity, while P3.4 can still finish its deterministic runner/evidence deliverables and hand honest provider readiness to P4.
