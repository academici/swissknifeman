---
id: D120
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-SELECTION:P5.2-VERSION-PIN] Shown that the PATH `claude` is `2.1.223 (Claude Code)` while the frozen pin is `2.1.222 (Claude Code)`, the owner literally selected «Гонять 2.1.222 (рекоменд.)» (`brief/33-p5.2-seam-ownership-owner-decision-2026-08-06.md`). The pin is HONORED, not bumped: the pilot resolves the Claude binary through the already-existing `SKM_CLAUDE_BIN` override (`packages/artifex/lib/artifex/providers/claude_code.py:27-32`, which reads it before `shutil.which("claude")`) pointed at `/home/vostrikov/.local/share/claude/versions/2.1.222`, whose `--version` prints the exact frozen literal. No frozen text of `business-dispatch-admission-v1@1.0.0`, no `provider-business-projection-v1.json` row and no `providers/claude_code.BUSINESS_VERSION` constant changes; Codex `codex-cli 0.146.0` already matches its pin. This is therefore not the "provider-version drift" case D109 routes to a P5.5 reopen — there is no drift once the pinned build is the one executed — and it creates no owner grant. Rejected: bumping the pin to `2.1.223` (needs a new grant to edit a frozen contract, reopens P5.5 for a second reason, and would rest every provider claim on a CLI surface never verified first-party at that version). **Consequences:** P5.2's Implementation Rules gain a hard pre-dispatch obligation to re-probe the pinned binary's literal at execution time and refuse before intent if it is absent or prints anything else — the local version manager may prune old builds — and every P5.2–P5.4 pilot invocation must carry the same explicit binary pin rather than inheriting PATH. RAG:✅ 2026-08-06 first-party local probes (`claude --version` → `2.1.223 (Claude Code)`; `~/.local/share/claude/versions/2.1.222 --version` → `2.1.222 (Claude Code)`; `codex --version` → `codex-cli 0.146.0`) captured in `findings/P5.2-seam-ownership-and-version-drift-2026-08-06.md` F3/F4; owner-grounded: `brief/33-p5.2-seam-ownership-owner-decision-2026-08-06.md`.

## Почему

A frozen pin exists to make the measurement reproducible; honoring it with the build that is still on disk costs nothing and keeps the contract, the manifest and the runtime constant mutually consistent, while a bump would trade a solved problem for an unverified provider surface and a second reopen.
