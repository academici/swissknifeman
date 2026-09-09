# P4 design baseline: terminal delivery boundary

## Repository evidence

1. `packages/task/lib/task/plan_delivery.py` and `packages/task/scripts/plan-delivery.py` already
   build and verify terminal/handoff receipts over journal state, generated views, handoff and
   digests. They do not own an active run lease and do not inspect the actual assistant response.
   RAG:—.
2. `packages/task/docs/continue-first.md` explicitly leaves heartbeat and actual transcript
   evidence to an adapter/Harness seam. `session_context.py` supplies provider-neutral session
   identity, but there is no terminal admission reducer or active-run registry. RAG:—.
3. P1.3 already owns work estimation and the `continue-root|cold-start|waiting-owner|terminal`
   continuity choice. P4 must consume that typed result; another continuity controller would be a
   duplicate source of truth. RAG:—.
4. `packages/harness/lib/harness/hooks.py` and Codex lifecycle bindings cover `SessionStart`,
   `SessionEnd`, `UserPromptSubmit`, `PreToolUse` and `SubagentStop`, but no shared
   `lifecycle.terminal-admission`/`Stop` surface exists. The root provider manifest consequently has
   no terminal-admission capability row. RAG:—.
5. The preserved P10.6 incident records repeated false terminal responses and asks for a
   pre-final verifier, active dispatch, forty artificial boundaries and a `final_allowed` event.
   Its repository symptom remains valid; its historical assumption that no provider hook exists
   requires current verification. RAG:—.

## External verification

- OpenAI's official [Codex Hooks documentation](https://learn.chatgpt.com/docs/hooks), checked
  2026-09-09, documents a `Stop` event with `turn_id`, `stop_hook_active` and
  `last_assistant_message`. A blocking decision keeps Codex working by injecting the reason as a
  continuation prompt. RAG:✅, confidence high, scope: documented Codex CLI hooks.
- Anthropic's official [Claude Code hooks documentation](https://code.claude.com/docs/en/hooks),
  checked 2026-09-09, documents `Stop`, `stop_hook_active`, `last_assistant_message` and
  `decision: "block"` continuation. It also documents an override after eight consecutive blocks,
  so no design may promise forty unchanged live blocks. RAG:✅, confidence high, scope:
  documented Claude Code hooks.
- No evidence was collected for ChatGPT web, Codex IDE/cloud execution or other provider surfaces;
  they remain outside the support claim. RAG:— as an explicit absence-of-verdict boundary.

## Design consequences

- D5 remains valid: repository admission and provider transport are different fact classes.
- D9 uses current provider Stop hooks where documented, with opt-in/trust/kill-switch conditions.
- The durable proof target is Task's state machine plus thin adapter fixtures. Live provider behavior
  is a separate integration verdict and cannot be inferred from local unit tests.
- Forty boundaries must advance progress/sequence and prove event continuity; the fixture must not
  exercise an unchanged infinite stop loop or contradict Claude Code's cap.
