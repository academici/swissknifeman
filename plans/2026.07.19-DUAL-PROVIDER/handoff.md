# HANDOFF — 2026-07-21 — after P5.3

**Next:** run-items: task:plan-run 2026.07.19-DUAL-PROVIDER P5.4

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | continue (reset the session context) — ручной item |
| Суть | Project MCP, agent and agent-pack projections through the committed P5.3 lifecycle seam. |

```text
$ task:plan-run 2026.07.19-DUAL-PROVIDER P5.4
```

**Done:** P5.3 maps every common lifecycle/context intent through named Claude and Codex
projections. Codex emits one hook-native project `hooks.json` observer registration plus its
generated handler in temporary roots; auto-approval remains P5.2 config-native and every other
unimplemented lifecycle/context row is explicit unsupported. Existing Claude registrations and
kill-switches are guarded by an independent fixture; no raw Claude command is reused in Codex output.

**Remaining:** P5.4–P5.7 remain sequential. Full package validation, phase close and independent
audit remain deferred to the terminal P5 gate under D80 and the Owner execution instruction.

**Sources of truth:** `plan.md` D85/Contracts/Routing; `phases/P5.md` P5.3–P5.4;
`root/contracts/provider-harness-contract.md`; `artifacts/P5-hook-context-matrix.md`;
`packages/harness/lib/harness/{hooks,profiles,provider_render}.py`; native Hooks evidence at
`/tmp/openai-docs-cache/codex-manual.md`.

**Open risks:** Codex project hooks require user trust review and can be disabled with
`[features].hooks = false`; no live installation was authorized. `context.output-style` and
`context.plans-directory` remain visible unsupported Codex rows for later provider-qualified work.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: single-commit item/bookkeeping bundling is an Owner-required process deviation;
  exact commit hash is reported after commit instead of embedded self-referentially.
- open_questions: none.
