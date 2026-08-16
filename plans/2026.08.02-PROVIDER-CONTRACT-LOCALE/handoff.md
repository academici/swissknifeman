# HANDOFF — 2026-08-16 — after P6

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P6

**Provider-neutral plan-protocol command:**

```text
task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P6
```

| Параметр | Значение |
|:--|:--|
| Batch | P6 optional-membership redesign |
| Model | frontier |
| Thinking | high |
| Context | `cold-start-root: audit-root-terminal` |
| Суть | Зафиксировать generic required/optional project membership и убрать release-gating связь optional Brain без special-case имени. |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P6'
```

**Done:** repository owner approved `DR-P6-BRAIN-OPTIONALITY-1` option
`define_optional_project_membership`. The append-only response is provenance-qualified by the
exact Codex owner-continuation turn and resumes the original P6 design target. No package runtime,
provider adapter, frozen contract, or fleet evidence was changed in this response step.

**Remaining:** redesign the provider-neutral membership contract so required projects remain
release-gating while optional integrations do not gate package runtime or fleet release merely by
being absent/non-participating. Brain may be one optional integration, but neither schema nor code
may special-case its name. Rebound P6.3 evidence and terminal candidate only after the design is
committed and validated.

**Sources of truth:** plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/decisions/queue.jsonl ·
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P6/P6.md ·
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-health-v1.md ·
plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/findings/P6.3-brain-optionality-authority-boundary.md

**Open risks:** the committed `provider-health-v1` exact-set aggregate remains unchanged until the
design root defines membership, compatibility/versioning, and evidence semantics. The measured P5
and shared-plane blockers remain real and must not be hidden by optionality.

**Workarounds/Deferred/Open questions:**

- workarounds: none; no Brain-name exception or runtime coupling is authorized.
- deferred: contract edits, D-record, brief/research traceability, evidence rebound, and terminal
  closure belong to the fresh routed `plan-design P6` root.
- open_questions: choose the smallest generic carrier and compatibility treatment that preserves
  required-project exactness while representing optional participation explicitly.

**ROUTE-UNVERIFIABLE:** the current owner-response turn is not the exact Task invocation required
by the Codex write-site contract. The native launch above is mandatory; this response root does not
perform the redesign itself.
