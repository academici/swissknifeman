# HANDOFF — 2026-07-22 — after P6.8

**Next:** /task:plan-design 2026.07.19-DUAL-PROVIDER P6

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high — bounded transfer refusal design |
| Context | NEW SESSION — шаг-не-item |
| Суть | Design only the owning P2/P5/P6 repair route for the still-refused D104 live no-write candidate. |

```text
$ task:plan-design 2026.07.19-DUAL-PROVIDER P6

РЕЖИМ: bounded repair design only.
ВХОД: P6.8 finding and D103/D104 transfer records.
СКОУП: explain the non-green D104 live dry-run admission and specify only the owning P2/P5/P6 repair route.
НЕ ТРОГАТЬ: live apply/repair, P7.2 rerun, P7.3+, FOREMAN, fleet, tag and push; do not begin P6 close/audit.
```

**Done:** P6.8 independently passed its disposable-root D104 matrix at `f29653a7` (21
provider-deploy tests and 19 deploy tests). The exact live preimage and absence inventory match
D104, but both permitted readers remain non-green: `maind sync --dry-run --json` reports
`MAIND_PROVIDER_DEPLOY_REFUSED`, and the direct harness lifecycle observer dry-run refuses the
unmanaged hooks target. Both snapshots showed no live `.codex` or P2-lock delta.

**Remaining:** Design a bounded P2/P5/P6 fix-forward route, execute it only after design, then
repeat P6.8 evidence. A fresh P6 audit is not started by this handoff. P7.2 remains closed;
P7.3+, FOREMAN, fleet, tag and push remain excluded.

**Sources of truth:** `phases/P6.md` P6.8 Completion Notes;
`artifacts/P6-bootstrap-transfer-independent-conformance.md`;
`findings/P6-bootstrap-transfer-live-preflight-2026-07-22.md`; D104 in
`research/23-p7.2-live-preflight-remediation-design.md`; item commit `f18fbd4b`.

**Open risks:** The matching D104 preimage, missing companion and missing lock are insufficient
to make the live provider row green. Do not infer that an Owner decision or a dry-run refusal
permits adoption/repair; the mAInd caller's refusal must be understood at the owning seam.

**Workarounds/Deferred/Open questions:**

- Workarounds: —
- Deferred: all live transfer/apply/repair and the P7.2 full rerun.
- Open questions: why the exact D104 candidate is not selected as a green P6 dry-run admission.
