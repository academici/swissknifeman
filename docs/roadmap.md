# Roadmap

An opt-in [Codex request observer](harness/codex-request-lifecycle.md) captures native
app-server request identity and lifecycle without storing prompt or answer content; it needs
integration at the owning client. A 2026-10-05 field silence of a Codex executor remains
unexplained without those client/server events.

Directions only; order within a block is rough priority. Work starts on measured need, not in anticipation of it.

## JSON v3 reconciliation with main (2026-10-05)

The feature branch incorporates compatible main changes at `b0f63fd4` while keeping the JSON v3
state API and lifecycle. Optional `--reviewer` selection is independent of storage; risk does not
admit review. Executor/reviewer roles, bounded correction and systemic invariant checks are retained.
The v2 check runner, review packet/ACP jobs, candidate receipts and whole-plan close facade were
removed with v2 and are not v3 capabilities. Prior v2 field qualification is historical evidence,
not qualification of the replacement engine. The existing roadmap records remain useful failure
examples; adapt their behavior only when measured or explicitly prioritized.

Future work: smart orchestration, machine-run checks with stored proof, native reviewer job recovery
and candidate-bound provenance. Design these against JSON objects and the simple `plan.py` API;
do not resurrect Markdown state reducers. No implementation of that future orchestrator is included.

## Near term

- **Session efficiency.** Accumulated tool results, not the resident skill set, dominate Codex session growth; duplicate skill names exist in the umbrella and in Vaulter. Next: safe pilots that trim tool-result carry-over and remove the duplicates.
- **Provider parity.** Plugin/skill reconcile plus Cursor/Grok field residue after the provider-aware `budget`/`doctor` work. Grok is a managed provider (Codex-shaped hooks/MCP TOML, Cursor-shaped skill discovery); fleet health still requires only Claude/Codex/Cursor.
- **Own skills migration.** Analyze local projects listed in `.skills-scanner.json`, move the universal part into the registry (via the [scanner](/skiller/guide/scanner) or by hand), connect it back with `skiller connect` / `skiller vendor`, delete local copies.
- **Vendor skills in packages.** Apply the [publication mechanism](/skiller/guide/vendor-skills) in own open-source packages: `resources/skills/` + ServiceProvider publication + a full-cycle test (`composer install → vendor:publish → agent sees the skill`).
- **`configs/` content.** Preconfigured subagents (`.claude/agents/`), hooks (auto-format, pre-commit validation), other IDE configs — see the [configs overview](/harness/configs/). Verified `.mcp.json` presets already ship (`context7` + a curated subset), see [Integrations](/harness/integrations/).

## Strategic

- **Cross-project optimizer** — the read-only overview ships as `system/cross-project-coordinator` plus the `code-coordinator` agent. Next: turn findings into action (auto-extraction to a shared package, PRs to target projects) and write cross-project facts to shared memory.
- **Skills Marketplace UI** — web UI over the registry: tag search, snippet preview, "Install to project". Minimum: VitePress + GitHub API.
- **Skill Composition** — `extends: laravel` in frontmatter: the agent loads the parent context first.
- **Versioned Snapshots** — SemVer tags on the repository and a version pin in `skiller vendor` (`swissknifeman@1.2.0`); sha256 in the registry already exists.
- **Skill Chains** — the `requires` / `produces_for` graph already exists in frontmatter; visualize it as a DAG and run a chain in one call.

## Technical

- **Snippet auto-scoring** — GitHub Action runs phpcs/phpstan/hadolint on new snippets and writes a score to `index.json`; candidates below threshold are blocked.
- **Obsidian plugin** — `skills.json` in the sidebar, open SKILL.md, insert a snippet with `/skill`.
- **MCP server for skills** — `get_skill(name)`, `list_skills(bucket)`, `search_snippets(query)` instead of file reads.
- **Quality badges** — generated per-skill badges: `snippets: 5`, `used_in: 3 projects`, `last_tested: <date>`.

## Experimental

- **LLM gap analysis** — a monthly agent reads PRs/issues of working projects, finds patterns no skill covers, drafts new SKILL.md files.
- **Snippet leaderboard** — track which snippets are copied into projects and how stable they stay.
- **Skill health monitor** — scheduled Action checks that snippets compile/lint on current PHP, Node and Docker versions.

## Deferred audit proposals (2026-10-19)

prompt-profile/v1 и трансформации порядка блоков принадлежат PLAN4 P13.3; источники — PLAN8 knowledge/research#prompt-placement. Здесь эти изменения не планируются повторно.

### Источник

[audits/skm.md](../audits/skm.md), [audits/swissknifeman-schema-audit.md](../audits/swissknifeman-schema-audit.md), PLAN8 knowledge/audit-verdicts#deferred, #orch и #schema. Условия ниже определяют момент возврата к предложению, а не разрешение на его реализацию.

### Предложения и триггеры

- O6-O7 Capability scoring и shadow/advisory/canary routing — триггер: отчёт analyst за 2 недели показывает ≥ 30 завершённых модельных попыток на пару role×provider×model с исходом и стоимостью; владелец: orch; источник: audits/skm.md раздел «Routing моделей» и audits/skm.md раздел «Shadow routing».
- O10-package Пакетный слой инструкций — триггер: замер хотя бы одного run показывает, что обязательные секции CLAUDE.md пакета не вошли в repository_rules из-за лимита 4000 символов context-стадии stages/context.py; владелец: orch; источник: audits/skm.md раздел «Конфигурация инструкций».
- O11 context-bundle/v2, artifact refs и semantic retrieval — триггер: доля модельных стадий со Stop PROVIDER_CONTEXT или TOKEN_BUDGET превышает 10% за 2 недели; владелец: orch; источник: audits/skm.md раздел «Context Bundle v2».
- O13 Денежные бюджеты — триггер: в model-catalog появляются цены или подключается хотя бы один провайдер с оплатой за токен; владелец: orch; источник: audits/skm.md раздел «Бюджеты и большие задачи».
- O18 Circuit breaker и общий provider health — триггер: ≥ 3 run за 2 недели остановлены серией transport/provider_internal ошибок одного провайдера; владелец: orch; источник: audits/skm.md раздел «Этап 4: adaptive budgets».
- O20 Multi-repo подписанные GUI catalogs и Level-2 UI — триггер: первый модуль с destination own-repo публикует gui.json из своего репозитория; владелец: gui; источник: audits/skm.md раздел «Multi-repository mode» и audits/skm.md раздел «GUI limitations».
- O21 Полная conformance-матрица provider × auth/quota/rate-limit/invalid JSON — триггер: хотя бы одно обновление CLI провайдера ломает разбор ответа в run; владелец: orch; источник: audits/skm.md раздел «Provider conformance».
- S4 Quorum/all reviewers — триггер: владелец запрашивает второго reviewer на одном пункте; владелец: orch; источник: audits/swissknifeman-schema-audit.md раздел «Reviewer routes».
- S6 Immutable plan revisions, SQL projection и round-trip — триггер: хотя бы один run должен ссылаться на ревизию плана, изменённую после claim, или появляется БД-хранилище планов; владелец: planner; источник: audits/swissknifeman-schema-audit.md раздел «План как граф и база данных».
- S7 Material descriptors, RAG policy и citations — триггер: хотя бы один материал пункта превышает 1 МБ или пункт получает бинарный вход; владелец: planner; источник: audits/swissknifeman-schema-audit.md раздел «Материалы, артефакты и RAG».
- S14 Discriminated item type с rollback/backup/compatibility window — триггер: появляется план хотя бы с одним пунктом миграции данных или релиза; владелец: planner; источник: audits/swissknifeman-schema-audit.md раздел «Дополнительные обязательные поля по типу задачи».
- R-REVIEW Проекция review.reviewer/rounds_max мостом planner-orch и честная проверка covers (отказ или предупреждение до исполнения) — триггер: следующий план использует covers или review.reviewer хотя бы в одном пункте; владелец: planner-orch + planner check; источник: PLAN8 knowledge/audit-verdicts#schema S2.
