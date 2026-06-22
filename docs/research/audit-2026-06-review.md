# Ревью внешнего аудита SwissKnifeMan (2026-06)

> Честный разбор внешнего аудита (источник — `Audit.md`, удалён из корня после
> переноса выводов сюда). Аудит давал рекомендации по трём осям: дедупликация
> скиллов, рефакторинг Python-ядра/CLI, новые скиллы. Сверка — с **живым**
> реестром (`skills/`, `skills.json`, `lib/`), а не по именам. Помеченное
> ✅DONE/🟡EXTEND реализовано в этот заход; ❌ — отклонено с причиной.

## Метод и доверие к источнику

Аудит, в отличие от предыдущего (loops), **читал реальное дерево**: почти все
названия скиллов точны (php/frontend/devops/founder/pm существуют как заявлено;
галлюцинации — только в секции «новые скиллы»). Но оценка велась **по
именам/поверхности**, без чтения `SKILL.md` и пайплайна генерации. Отсюда
систематическая ошибка: аудит переоткрывает уже реализованное под другими
именами (`depends_on`≈`requires`, `skill.yaml`≈`SKILL.md` frontmatter) и
рекомендует зависимости, нарушающие инвариант проекта (stdlib-only).

Главная ценность аудита — **не его фиксы, а повод проверить остроту триггеров и
связность зависимостей** в реестре на ~180 скиллов.

## Сводный вердикт

| # | Рекомендация | Вердикт | Причина |
|:--|:--|:--|:--|
| 1a | Слить `laravel`/`laravel-best-practices`/`laravel-structure`/`php-patterns` в `laravel-core` | ❌ | Разные слои; слияние убивает skill-granular вендоринг и upstream-tracking |
| 1b | Мета-скилл `laravel-auth-patterns` | ❌→A | Подходы разные, но новый мета-скилл = новая сущность. Решено остротой триггеров |
| 1c | `laravel-testing` ↔ `test-isolation-guard` дубль | ❌ | Намеренная иерархия: guard — страж поверх паттернов |
| 1d | Слить vue-кластер | 🟡→A+B | Реальный overlap, но 2/3 upstream (слияние ломает sync). Решено: trim локального `vue-composition-api` + триггеры |
| 1e | Слить vitest-кластер | 🟡→A | `vitest` (рецепт Laravel/Inertia) и `vitest-vue` (generic, upstream) комплементарны — не дубль. Добавлен указатель |
| 1f | nuxt модули/seo → сниппеты | ❌ | Skill-granular вендоринг: проект тянет только nuxt-seo при нужде |
| 1g | «Наследуемые скиллы» (docker-php → docker) | ✅ уже есть | `requires` + транзитивный `resolve_requires` (vendor.py); напр. `docker-services`→`[docker-php,docker-postgres]` |
| 1h | founder/pm/roles пересечения | ❌ | Разнесены по persona-бакетам осознанно (разная аудитория раздачи) |
| 2А | `skill.yaml` → CLI генерит plugin.json/skills.json | ✅ уже есть | `SKILL.md` frontmatter = SSOT; `skiller registry` генерит всё. plugin.json — **per-bucket**, не per-skill (аудит ошибся в гранулярности) |
| 2Б | Typer/Click/Rich вместо argparse | ❌ инвариант | CLAUDE.md: `lib/` — **stdlib-only**. Осознанный дизайн (zero-install) |
| 2Б | Pydantic для валидации JSON | ❌ инвариант | Тот же stdlib-only; забота уже закрыта `scripts/validate.sh` |
| 2Б | bash → Python ради Windows | ❌ non-goal | Windows нигде не цель; скрипты проверяются `bash -n` |
| 2В | `depends_on` + сборка бандла | ✅ уже есть | `requires`/`produces_for` + `docs/guide/graph.md`; бандл = `resolve_requires`; lazy-load нативный |
| 2Г | `skm minify` / локальная NN сжатия .md | ❌ | Скиллы уже lazy-loaded (в контексте только name+description). Налог CLAUDE.md/rules закрыт `context-economy` |
| 3a | `python/rag-architecture` | ❌ дубль | `imported/ai-agents` (§RAG) + `architect/eval-design` |
| 3b | `python/ai-agents-langchain` | ❌ дубль | `architect/agent-design` + `imported/ai-agents` |
| 3c | `general/prompt-engineering` | ❌ дубль | `imported/ai-agents` §prompt-engineering |
| 3d | `security/owasp-top-10` | 🟡 расширить | Уже: `architect/security-design` + `php/laravel-security-audit` + `imported/security` |
| 3e | `devops/github-actions-security` | ✅→C | Реальный пробел: security-гейты в CI. Расширен `devops/ci-cd`, без нового скилла |
| 3f | `devops/terraform-basics` | ❌ вне scope | IaC не в сценариях проекта |
| 3g | `devops/kubernetes-manifests` | ❌ вне scope | k8s нет в экосистеме; место — локальные скиллы потребителя |
| 3h | `python/data-pipelines` | ❌ вне scope | Data-engineering не в сценариях |
| 3i | `operator/telemetry-grafana` | ❌ дубль | `architect/observability-design` покрывает Prometheus/OTel/Grafana + LLM-метрики |

## Что сделано в этот заход

- **A. Trigger-дизамбигуация.** `laravel-permissions` (0.3.1) — описание-триггер
  (убран путающий тег «AzGuard patterns», добавлено «когда azguard →…, когда
  атрибуты →…»; `azguard`/`attribute-authorization` уже имели острые тела).
  `vitest` (0.1.1) — указатель на `vitest-vue` (generic API vs рецепт Laravel/Inertia).
- **B. Дедуп.** `frontend/vue-composition-api` (0.2.0) обрезан до дельты (ref-first +
  паттерн composables); базовый синтаксис/props/emits отданы upstream `vue`/
  `vue-best-practices`. **Не удалён** (≈13 кросс-ссылок из frontend-кластера —
  скилл служит якорем «паттерн composable»); вместо удаления — острый триггер.
- **C. CI security-гейты.** `devops/ci-cd` (0.3.0) — секция «Security gates»
  (SAST/PHPStan-taint, `composer/npm audit`+Dependabot, Trivy скан образа) +
  сниппет `github-actions-security.yml`. Без нового скилла/бакета.

## Что осознанно НЕ сделано

Слияния кластеров в «core+advanced»; `skill.yaml`; Pydantic/Typer/Click/Rich
(stdlib-only); bash→Python (Windows — non-goal); `depends_on` (уже `requires`);
`skm minify`; новые скиллы rag/langchain/prompt-engineering/terraform/k8s/
data-pipelines/telemetry-grafana/owasp.
