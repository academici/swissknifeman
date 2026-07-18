---
type: research-artifact
plan: 2026.07.18-FOREMAN
date: 2026-07-18
purpose: Промпт для Perplexity Deep Research — аудит готовых OSS-скиллов/хуков под компоненты Artifex. Запускает владелец; результат разбирается в P0.4/P0.5-заходе и кладётся в findings/
---

# Промпт для Perplexity Deep Research (копипаст целиком)

```
ROLE. You are a senior engineer auditing the open-source Claude Code ecosystem
(skills, subagents, hooks, plugins, orchestrators) for reusable building blocks.

CONTEXT. We are building "Artifex" — a supervisor package for UNATTENDED execution
of multi-phase master plans with local Claude Code CLI on Linux. Architecture:
a CLI driver runs each plan item as a FRESH headless session
(`claude -p "/task:plan-exec Pn.m" --output-format json`), parses a per-plan
handoff/status contract plus an append-only execution journal, then decides
next / retry / escalate. Human owner approves plans; execution runs autonomously
with messenger escalation on conflicts.

COMPONENTS WE NEED (audit target):
  C1. Supervisor/orchestrator loop over headless `claude -p` (spawn, JSON parse,
      exit-code interpretation, retry budgets, escalation state machine).
  C2. Progress & loop/thrash detection: N iterations of the same command —
      distinguishing real convergence from "fix one thing, break another".
  C3. Permission auto-approve policy engines: PreToolUse / PermissionRequest hooks
      emitting allow/deny/ask decisions from a declarative per-project policy file.
  C4. Escalation bots: Telegram AND VK MAX (max.ru) messenger adapters; blocking
      Q&A pattern — session defers, owner answers in messenger, session resumes
      (Claude Code `defer` + Agent SDK resume); multi-channel with dedup.
  C5. Per-plan run journaling / session-to-plan attribution (Claude Code sessions
      are not bound to plans — we need the binding layer).
  C6. Skill/hook packaging and VERSIONED rollout across many projects
      (marketplace/plugin formats, lock files, upgrade paths).

SEED LIST (collections we already track — start here, then go BEYOND):
  github.com/obra/superpowers · eyaltoledano/claude-task-master · github/spec-kit ·
  VoltAgent/awesome-agent-skills · VoltAgent/awesome-claude-code-subagents ·
  wshobson/agents · 0xfurai/claude-code-subagents · rahulvrane/awesome-claude-agents ·
  DietrichGebert/ponytail · musistudio/claude-code-router · steveyegge/beads ·
  othmanadi/planning-with-files · oraios/serena

SEARCH DIRECTIONS beyond the seed list: "ralph loop" / overnight autonomous runners;
Claude Code hook collections (notification bridges, permission gates); session log
analyzers / cost trackers; plan-file-driven executors; Agent SDK supervisor examples;
anything published 2025–2026.

FOR EACH CANDIDATE report:
  - repo/skill name + URL
  - component(s) C1–C6 covered
  - actual mechanism (what the code does — not the README marketing)
  - maturity: last commit date, stars, open issues trend
  - license (prefer MIT/Apache; flag anything else)
  - integration form: SKILL.md / hook script / MCP server / CLI / plugin
  - verdict: ADOPT as-is | ADAPT (state exactly what to change) |
    INSPIRE only (pattern worth copying) | SKIP (state why)

HARD CONSTRAINTS:
  - Must work with LOCAL Claude Code CLI (project skills/hooks/CLAUDE.md must load);
    cloud-only orchestrators = SKIP.
  - No frameworks that replace Claude Code as the agent runtime (LangChain-style) —
    we orchestrate Claude Code itself.
  - Verify claims against the repo (README + code structure), not blog posts.

OUTPUT FORMAT (in Russian):
  1. Таблица кандидатов ПО КАЖДОМУ компоненту C1–C6 (столбцы: репо/URL, механизм,
     зрелость, лицензия, форма интеграции, вердикт+обоснование).
  2. Отдельный список: компоненты БЕЗ адекватного покрытия (build-from-scratch зоны).
  3. Топ-5 рекомендаций «встроить в Artifex» с порядком внедрения.
  4. Полный список источников-URL.
```

## Как использовать

1. Запустить в Perplexity (режим Deep Research / Research) целиком.
2. Результат сохранить в `findings/owner-deep-audit-skills-<дата>.md` этого плана.
3. Разбор — в заходе P0.4/P0.5: сверка с pre-audit
   (`findings/perplexity-skills-ecosystem-preaudit-2026-07-18.md`), ADOPT/ADAPT-вердикты
   в D-лог, интеграционные кандидаты — items соответствующих фаз.
