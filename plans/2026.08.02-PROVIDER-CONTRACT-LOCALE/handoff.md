# HANDOFF — 2026-08-14 — after P2.1

**Next:** run-items: task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.2-P2.3

| Параметр | Значение |
|:--|:--|
| Batch | p2-contracts |
| Model | frontier |
| Thinking | high |
| Context | continue-root |
| Суть | Заморозить English authoring overlay, review policy and evidence contract, consuming frozen P2.1 locale semantics. |

**Provider-neutral plan-protocol command:**

```text
task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.2-P2.3
```

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P2.2-P2.3'
```

**Done:**

- P2.1 frozen by D74: independent `response`/`plan`/`diagnostics` precedence and the separate syntax, canonicalization, catalog and provenance boundaries are normative in locale-resolution v1.0.0.
- The exact `File-Date: 2026-06-14` IANA snapshot is vendored with byte identity and honest canonical/retrieval provenance.
- Positive and negative vectors plus the stdlib-only checker cover the full P2.1 acceptance inventory; item commit is `428d3871`.

**Remaining:** P2.2–P7; execute the adjacent P2.2–P2.3 suffix in the existing `p2-contracts` root, with P2.2 producing P2.3 inputs before its turn.

**Sources of truth:** `plan.md` §2–§3 and Contracts; `phases/P2/P2.md`; `phases/P2/P2.1.state.md`; `root/contracts/locale-resolution-v1.md`; `decisions/D74-locale-resolution-v1.md`; `core/locale/data/upstream.json`; P2 locale fixtures/checker.

**Open risks:** the Task decision-queue helper emitted derived transition rows without run/session binding; the explicit start and terminal P2.1 rows remain bound to the verified original route receipt. Historical registry retrieval used an immutable third-party mirror after the live IANA endpoint advanced, with exact digest/size validation and distinct provenance fields.

**Workarounds/Deferred/Open questions:** Workarounds: immutable mirror only for recovery of the plan-pinned bytes; runtime remains offline and pinned. Deferred: P2.3 execution waits inside the batch until P2.2 materializes its declared inputs; registry update producer is P4.1; CHANGELOG/release assembly is P7.3. Open questions: —.
