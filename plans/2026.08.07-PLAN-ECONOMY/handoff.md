# HANDOFF — 2026-08-08 — after P2.7

**Next:** `/task:plan-run 2026.08.07-PLAN-ECONOMY P2.8`

**Native Codex launch-block**

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | continue (/clear) — ручной item |
| Суть | Выполнить самохостящую миграцию P2.8 и замер пути v2 |
| Команда | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.8'` |

**Provider-neutral plan-protocol launch-block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | Мигрировать этот план v1→v2 конвертером и доказать инвентарь/вес |
| Команда | `/task:plan-run 2026.08.07-PLAN-ECONOMY P2.8` |

```text
$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.8
```

**Done:** P2.7 поставил status-aware phase resolver и generated `phase-closure`; закрытые фазы
исключены из живых путей, аудитор сохраняет адресацию. D130 синхронизировал четыре
registry/spec copies на `.closed.md`. Item-коммит: `f03d0eb9`.

**Remaining:** P2.8–P6. Follow-up P2.6: литеральный full unittest без корневого `PYTHONPATH`
не воспроизводит штатный package launcher.

**Sources of truth:** `phases/P2.md` P2.7 Completion Notes · D34/D130 ·
`packages/task/lib/task/plan_closure.py` · `packages/task/lib/task/plan_layout.py`.

**Open risks:** P2.7 закрыт 🟠 только из-за literal unittest environment mismatch; package
validation и P2.7 functional checks зелёные. P2.8 остаётся необратимой миграцией живого плана.

**Workarounds/Deferred/Open questions:**

- Workarounds: полная регрессия запускается через `bash packages/task/scripts/validate.sh`.
- Deferred: P2.6 validation-path repair.
- Open questions: —.
