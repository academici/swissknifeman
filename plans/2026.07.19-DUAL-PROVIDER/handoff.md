# HANDOFF — 2026-07-20 — after P2.5

**Next:** «ЗАПУСК ВРУЧНУЮ: gpt-5.6-sol/high»

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high — independent adversarial P2 audit |
| Context | NEW SESSION — шаг-не-item |
| Суть | Провести fresh independent audit terminal P2; P3.1 не начинать. |

```text
Проведи только fresh independent audit P2 плана 2026.07.19-DUAL-PROVIDER на gpt-5.6-sol/high.

Сначала прочитай AGENTS.md, CLAUDE.md, plans/2026.07.19-DUAL-PROVIDER/plan.md,
handoff.md и phases/P2.md, включая Audit P2 от 2026-07-20 и P2.5. Затем читай ровно
материалы, необходимые для независимой проверки P2.1–P2.5 и D76.

Проверь на свежем контексте commit 5db342e: malformed provenance/override fail closed,
all-noop apply invokes no writer, caller-supplied managed-block codec preserves outside bytes
and refuses duplicate/nested/missing/reordered boundaries, and project Override gives stale-source/update.
Не изменяй core, frozen contracts/ADR/K1–K6, packages, live paths, FOREMAN, fleet, P3+ или owner dirt.
Выдай только audit verdict и evidence; при RED применяй fix-forward protocol, не начинай P3.1.
```

**Done:** P2.5 closed green. Item commit `5db342e` validates complete/canonical provenance
and override layers before clean classification, makes all-`noop` apply return with zero target,
backup, or lock writes, and carries one explicit caller-owned managed-block codec pair through
plan/apply. Synthetic evidence has 11 named contract cases, including outside-byte preservation,
boundary refusal and project-Override stale-source/update.

**Remaining:** Fresh independent P2 audit. P3.1 remains out of scope until literal GREEN.

**Sources of truth:** `phases/P2.md` P2.1–P2.5 and Audit P2 · D16–D18/D75/D76 in `plan.md` ·
frozen `root/contracts/provider-{capability,artifact,config,migration-gates}.md` ·
`artifacts/P2-provider-artifact-conformance.md` · `research/17-p2-red-audit-remediation.md` ·
commit `5db342e` · `journal.jsonl`.

**Open risks:** Static `codex doctor --json` route/effort ambiguity remains D56 non-green but
non-blocking under D72. Unrelated owner dirt remains intentionally unstaged. The P2.5 codec seam
must remain caller-supplied and must not grow into marker grammar, discovery, or registry.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: package/provider delivery begins only after fresh P2 audit GREEN.
- open_questions: —
