# HANDOFF — 2026-07-20 — after P1.3

**Next:** `/task:plan-exec 2026.07.19-DUAL-PROVIDER P1.4`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | medium — deterministic compatibility fixtures and no-write evidence |
| Context | continue (/clear) — ручной item |
| Суть | P1.4 доказывает matrix legacy/explicit provider compatibility и protected-path delta 0. |

```text
Продолжай только P1.4 плана 2026.07.19-DUAL-PROVIDER.
Прочитай plan.md, handoff.md, phases/P1.md и все P1.4 Required Reads в указанном порядке.
Используй committed P1.3 API from 8f377e1; implement only P1.4 Files and frozen P1.1
compatibility/migration gates. Do not touch live config, FOREMAN, fleet, root config, or
unrelated owner-owned dirt. Close the item through its full validation, two-commit lifecycle,
protected-path snapshots, and baseline-attributed plan lint.
```

**Done:** P1.3 closed `🟢 Done`: item commit `8f377e1` added the pure provider-config resolver,
field provenance, deterministic PCFG diagnostics, and thin skiller/maind adapters. Focused core/
skiller/maind tests, full skiller and maind validation, compile, and diff check passed.

**Remaining:** P1.4 remains, then P1 phase close/audit. P1.4 owns compatibility matrix, legacy
byte-preservation, optional example, protected-path delta evidence, and precise P2 handoff.

**Sources of truth:** `root/contracts/provider-config-contract.md` (D70) ·
`root/contracts/provider-migration-gates.md` · `phases/P1.md` P1.3/P1.4 · item commit `8f377e1` ·
`journal.jsonl`.

**Open risks:** D56 static doctor anomaly remains non-green but non-blocking; D72 runtime banner
is route evidence. P1.4 must retain the before/after protected-path evidence rather than treating
unit-test success as a no-write proof.

**Workarounds/Deferred/Open questions:**

- workarounds: mAInd/live-carrier evidence remains excluded; use synthetic fixtures and committed validators.
- deferred: provider registry, renderer, artifact lifecycle, and package CLI presentation remain in P2+.
- open_questions: —
