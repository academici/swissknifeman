# HANDOFF — 2026-07-22 — after P7.1

**Next:** run-items: task:plan-run 2026.07.19-DUAL-PROVIDER P7.1

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | same-session — item |
| Суть | Materialize and approve the frozen capability manifest, wire production gates, then generate/check provider docs. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman --no-alt-screen -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'Выполни $ task:plan-run 2026.07.19-DUAL-PROVIDER P7.1 в новой сессии. Начни с plans/2026.07.19-DUAL-PROVIDER/research/22-p7-capability-manifest-remediation.md и plans/2026.07.19-DUAL-PROVIDER/findings/P7.1-capability-manifest-gap-2026-07-22.md. Собери exact manifest candidate + shared-core contribution review; до production switch выдай один exact Owner D# и approval-строку, затем продолжи тот же item после ответа. Только P7.1; frozen semantics, closed predecessor deliverables, P7.2+, live provider outputs, FOREMAN, fleet, dirty root и push не трогать. После GREEN не запускай successor: закончи exact P7.2 launch-block из roadmap.md.'
```

**Done:** D98 зафиксировал root cause второго P7.1 escalation: отсутствовали не только docs renderer/check, но и normative manifest carrier + production consumption. P7.1 переписан как один bounded manifest→gates→docs hotspot; hook dry-run D97 остаётся non-blocking.

**Remaining:** P7.1 execution + in-item manifest approval → P7.2 → P7.3 → P7.4 → P7 close/audit. FOREMAN и fleet остаются вне scope.

**Sources of truth:** `phases/P7.md` P7.1; `research/22-p7-capability-manifest-remediation.md`; `findings/P7.1-capability-manifest-gap-2026-07-22.md`; frozen `root/contracts/provider-capability-contract.md`; accepted `root/adr/0001-provider-adapter-architecture.md`; P3–P6 conformance artifacts.

**Open risks:** exact catalog content/support evidence and additive core/public API require explicit in-item Owner D#; any frozen-schema insufficiency must stop and escalate rather than create a package-local fallback. P7.2–P7.4 gates remain closed.

**Workarounds/Deferred/Open questions:**

- workarounds: none accepted; no hand-authored or output-derived support matrix.
- deferred: live self-host, cleanup, release verdict, FOREMAN/fleet, tag and push remain later authority.
- open_questions: none at design level; exact catalog candidate is the explicit P7.1 owner gate.
