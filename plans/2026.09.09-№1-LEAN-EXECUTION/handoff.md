# HANDOFF — 2026-09-10 — after P4.1

**Next:** run-items: task:plan-run 2026.09.09-№1-LEAN-EXECUTION P4.2

| Параметр | Значение |
|:--|:--|
| Batch | B-P4-TERMINAL |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | Implement the provider adapters over the closed P4.1 policy; preserve its explicit provider-boundary limits. |
| Capabilities | skills.repository · command.filesystem-read · command.git-read · command.filesystem-write |
| Context | continue-root |
| Суть | P4.2 is the sole remaining member of the terminal-admission batch and consumes the generated P4.1 contract. |

**Provider-neutral command:**

```text
$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P4.2
```

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P4.2'
```

**Done:** P4.1 owns a versioned, lease-bound repository terminal-admission reducer. It binds typed P1.3 continuity, stable provider-session/Task-run identity, current terminal receipt, and the exact machine-authored final fragment; events remain hash-only.
**Remaining:** Implement P4.2's opt-in provider Stop adapters and bounded forty-progress-plus-final proof, using the P4.1 CLI rather than duplicating policy.
**Sources of truth:** `plans/2026.09.09-№1-LEAN-EXECUTION/phases/P4/P4.1.state.md` · `plans/2026.09.09-№1-LEAN-EXECUTION/phases/P4/P4.2.md` · `packages/task/lib/task/terminal_admission.py` · `packages/task/scripts/plan-terminal-admission.py`.
**Open risks:** Provider bindings must disclose unsupported transports and provider retry ceilings; they must neither store raw messages nor claim repository code intercepts all final output.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: provider-specific transport payloads and Stop-hook responses are P4.2-owned.
- open_questions: —
