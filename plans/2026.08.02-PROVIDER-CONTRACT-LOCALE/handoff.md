# HANDOFF — 2026-08-15 — after P4.3

**Next:** `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4`

| Параметр | Значение |
|:--|:--|
| Batch | solo/per-cwd-ledger |
| Model | implementation |
| Thinking | high — package-cwd catalog migration |
| Context | continue-root |
| Суть | Migrate only admitted command, plugin and diagnostic carrier rows with bounded package-cwd checkpoints. |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4'
```

**Provider-neutral plan-protocol command:**

```text
task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4
```

**Done:** P4.3 repaired its false terminal classification append-only, admitted the scoped local
root-bootstrap skill batch with distinct EN/RU evidence and rollback, and closed with the exact
P4.6 derived-target set deferred to its generator owner.

**Remaining:** P4.4–P4.6, then P5–P7.

**Sources of truth:** `phases/P4/P4.3.md`; `phases/P4/P4.3.state.md`;
`configs/locale-corpus-v1.json`; `artifacts/execution/P4.3/`; `journal.jsonl`;
`phases/P4/P4.4.md`; `roadmap.md`.

**Open risks:** `packages/skiller/scripts/validate.sh` is nonzero only for the checkpoint-enumerated
P4.6 generated targets. P4.4 must preserve that exact deferred set and may not regenerate it.

**Workarounds/Deferred/Open questions:**
- workarounds: the historical P4.3 terminal-block and fingerprint mismatch remain append-only journal evidence.
- deferred: P4.6 owns regeneration of the exact Skiller registry/bootstrap/budget targets.
- open_questions: —
