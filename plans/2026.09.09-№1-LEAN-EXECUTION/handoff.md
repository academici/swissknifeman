# HANDOFF — 2026-09-10 — after P4.2

**Next:** audit-phase: task:plan-audit 2026.09.09-№1-LEAN-EXECUTION P4

| Параметр | Значение |
|:--|:--|
| Batch | B-P4-TERMINAL |
| Model class | frontier |
| Model | gpt-5.6-sol |
| Effort | xhigh |
| Thinking | Independently audit the Task/Harness Stop seam, provider response parity, generated artifacts and declared transport limitations. |
| Capabilities | skills.repository · command.filesystem-read · command.git-read |
| Context | cold-start-root: whole-plan-independent-audit |
| Суть | P4 is terminal at item level; its declared internal-integration assurance requires a read-only phase audit before phase close. |

**Provider-neutral command:**

```text
$ task:plan-audit 2026.09.09-№1-LEAN-EXECUTION P4
```

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access '$ task:plan-audit 2026.09.09-№1-LEAN-EXECUTION P4'
```

**Done:** P4.2 adds the opt-in shared `lifecycle.terminal-admission` surface, Codex and Claude Code Stop adapters, capability evidence and generated provider artifacts. Its deterministic proof drives forty advancing boundaries through the P4.1 reducer, then admits only the exact final response; persisted evidence remains hash-only.
**Remaining:** Read-only P4 audit and phase close. No product implementation remains in B-P4-TERMINAL.
**Sources of truth:** `plans/2026.09.09-№1-LEAN-EXECUTION/phases/P4/P4.1.state.md` · `plans/2026.09.09-№1-LEAN-EXECUTION/phases/P4/P4.2.md` · `packages/task/lib/task/terminal_admission.py` · `packages/harness/lib/harness/hooks.py` · `configs/provider-capabilities.json`.
**Open risks:** Provider enforcement remains limited to explicitly configured, trusted documented CLI hooks; Claude Code's documented consecutive-block ceiling is not claimed as an unbounded live guarantee. The first P5.1 bundle currently reports `unresolvable_entry: current ratchet, budget and bucket-audit output`; that is a P5 planning defect requiring `task:plan-design`, not a P4 product regression.
**Workarounds/Deferred/Open questions:**
- workarounds: no applicable lease is a successful hook no-op; an applicable malformed/missing Task verifier state fails closed with a named diagnostic.
- deferred: unsupported, unconfigured and non-CLI transports remain explicit capability gaps.
- open_questions: —
