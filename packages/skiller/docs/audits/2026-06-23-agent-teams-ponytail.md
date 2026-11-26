# Триаж: Agent Teams + Ponytail (2026-06-23)

- **Источник:** Perplexity-аудит, оригинал `memster/claude_agent_teams_and_ponytail.md` →
  архив [raw](./2026-06-23-agent-teams-ponytail.raw).
- **Тема:** (1) экспериментальные Agent Teams (Mesh), (2) ponytail (YAGNI-лесенка),
  (3) гибкое наследование агентов через `_base.md` + `extends:`/`@include`.

## Проверка по официальным докам (важно)

| Утверждение | Вердикт | Источник |
|---|---|---|
| Agent Teams (Mesh, teammates, mailbox, shared task list) | ✅ CONFIRMED, экспериментально | code.claude.com/docs/en/agent-teams |
| Доступность на CC 2.1.158 | ❌ нет (нужно ≥2.1.178) | там же (auto-setup с 2.1.178) |
| Хуки `TeammateIdle`/`TaskCompleted` | ✅ официальные | code.claude.com/docs/en/hooks |
| Наследование агентов `extends:` + `@include` в теле агента | ❌ REFUTED (не существует) | code.claude.com/docs/en/sub-agents |
| Frontmatter `triggers/role/version/project_type` | ❌ REFUTED (выдумано) | там же |
| `.claude/rules/` с `paths:` | ✅ CONFIRMED нативно | code.claude.com/docs/en/memory |
| `${CLAUDE_PROJECT_DIR}`/`${CLAUDE_PLUGIN_ROOT}` | ✅ CONFIRMED | code.claude.com/docs/en/hooks |

## Триаж

| Идея | Вердикт | Куда / почему |
|---|---|---|
| Agent Teams (Mesh) | ✅ accept v1 | Фаза 6; предпосылка CC ≥2.1.178; роли = teammates; config форвард-совместим |
| Хуки TeammateIdle/TaskCompleted (quality-gate/validator) | ✅ absorb | переиспользуют логику review-gate; append-if-absent (без конфликта) |
| ponytail (YAGNI-лесенка + over-engineering ревью) | ✅ absorb (дисциплину) | без внешнего плагина; в reviewer-роль + опц. `quality/lean-code` |
| Внешний плагин ponytail (его SessionStart/UserPromptSubmit хуки, AGENTS.md-в-корень) | ❌ reject | конфликт-поверхность с boost-генерённым AGENTS.md |
| `_base.md` + `extends:`/`@include` наследование агентов | ❌ reject | не нативно (REFUTED); наследование = build-time пака |
| skill-enforcement хук (TeammateIdle, exit 2, греп транскрипта) | ❌ reject (как хук) | хрупко; «гейт на скиллы» закрывает детерминированная сверка имён `skills:` в hub |
| module-boundaries (зоны путей под роли) | ✅ absorb | Фаза 6; координация через task list, БЕЗ file-lock |
| `.claude/rules/` нативно | ✅ confirmed | подтверждает Фазу 3 |

## Куда легло

Фаза 6 (Agent Teams), Фаза 3 (ponytail-дисциплина, rules). Зафиксировано в
[decisions-ledger](../agent-framework/decisions-ledger). Положительный побочный эффект:
аудит дал авторитетную проверку, снявшую условность `.claude/rules/` и подтвердившую
отказ от рантайм-наследования агентов.
