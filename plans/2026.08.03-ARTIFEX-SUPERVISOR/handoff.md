# HANDOFF — 2026-08-04 — after P3.1

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-code-edit · deterministic-test-execution · plan-self-close |
| Context | continue (/clear) — ручной item |
| Суть | Реализовать и проверить pure Claude Code mapper поверх P3.1 common protocol. |
| Команда | — |

| Model | Thinking | Approval policy | Sandbox | CWD | Context | Суть | Команда |
|:--|:--|:--|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | never | danger-full-access | `/home/vostrikov/projects/packages/swissknifeman` | `continue (/clear) — ручной item` | P3.2 pure Claude Code mapper and adversarial validation | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.2` |

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c model_reasoning_effort="high" -a never -s danger-full-access

$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.2
```

**Done:** Item commit `1a87d960` completed P3.1: the plan-local adapter has a closed shared
protocol, exact version-gated Codex argv mapping, child refusal and JSONL terminal fold. Its
targeted tests, full prototype suite and terminal P0/P1/P2 validators are green.

**Remaining:** Execute P3.2–P6.4 sequentially; P3.2 must add only the Claude mapper and tests,
then P3.3 freezes parity before the P3.4 process boundary.

**Sources of truth:** `phases/P3.md` P3.1/P3.2 ·
`artifacts/supervisor/artifex/providers/{common,codex}.py` ·
`artifacts/P0/{provider-matrix-v1.json,provider-probes/claude-code.json}` · frozen P1 contracts.

**Open risks:** P3.2 must preserve P1 envelope parity, refuse unknown provider records and avoid
real process launch or raw output persistence. The recorded Codex hook `stale-source` warning
remains deferred to P4.4 and is not a green hook verdict.

**Workarounds/Deferred/Open questions:**

- workarounds: none;
- deferred: provider execution remains outside P3.1/P3.2 and starts only at P3.4;
- open_questions: —.
