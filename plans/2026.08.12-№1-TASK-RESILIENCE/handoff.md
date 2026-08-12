# HANDOFF — 2026-08-12 — after P0

**Next:** manual: task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.1

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | continue-root |
| Суть | Повторно сверить roadmap с current runtime и построить полный gap matrix без принятия прежнего candidate на веру. |
| Команда | `$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.1` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | continue-root | Roadmap/runtime gap matrix | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.1'` |

**Done:** active Layout v2 plan P0–P6 полностью детализирован; обязательный Perplexity bridge
исправлен в `perplexity-web-mcp` commit `d77ce0e`, basic/advanced/deep rerun успешен.

**Remaining:** исполнить P0.1–P6.3, создать локальный `v0.13.0`, раскатать зарегистрированные channels.

**Sources of truth:** `plan.md` · `roadmap.md` · `brief/` · `findings/` · `decisions/` · `phases/`.

**Open risks:** active Layout v1 в зарегистрированном fleet ещё не инвентаризированы; это P1.1,
не основание удалять reader заранее.

**Workarounds/Deferred/Open questions:** workarounds — нет; deferred — push/GitHub release;
open_questions — нет.
