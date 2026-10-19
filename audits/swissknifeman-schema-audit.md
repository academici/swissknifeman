# Глубокий аудит схем планов и конфигурации Swiss Knife Man

**Репозиторий:** `academici/swissknifeman`  
**Зафиксированная ревизия:** `81a4507e6abeec7c92b042043a460ba11316863a`  
**Дата:** 19 октября 2026 года  
**Область:** схемы Planner и Orch, review на уровне пунктов и батчей, порядок исполнения, материалы/RAG, бюджеты, Markdown-представления, конфигурационные файлы и подготовка к реляционному хранилищу.

## Резюме

В текущей архитектуре review в основном является свойством **run policy**, а не обязательным, явно сериализованным свойством каждого пункта плана. Полная политика `full` задаёт общие `max_rounds`, `max_corrections`, требование независимого provider и triage, но этого недостаточно для выбора разных reviewers, группового review после нескольких пунктов или materialized отображения решения в roadmap.[cite:57][cite:62]

Целевая модель должна разделять пять понятий:

1. **Review intent** — что потребовал автор плана на пункте.
2. **Review strategy** — как planner сгруппировал проверки.
3. **Review assignment** — какие reviewer routes были разрешены или выбраны.
4. **Review execution** — конкретные попытки и раунды.
5. **Review evidence** — findings, verdict, покрытие и подтверждённые checks.

Рекомендуется сделать поле `review` обязательным для каждого executable item, но использовать не `false | object`, а закрытый tagged union с явным `mode`. Значение по умолчанию должно быть **не скрытым JSON Schema default**, а материализованным объектом `{"mode":"inherit"}` либо `{"mode":"none","reason":"..."}`. Для строгого плана предпочтительно `inherit`: итоговый effective review вычисляется и фиксируется до публикации или запуска.

Второе ключевое изменение — хранить план как нормализованный граф сущностей: plan → phases → items → dependency edges → review groups → material bindings → budgets → execution attempts. `sort_order` полезен только как стабильная подсказка отображения; реальный порядок исполнения должен выводиться из зависимостей, readiness gates и scheduler policy.

## Проверенные основы

`orch` уже отделяет execution contracts от planner lifecycle: пакет владеет `exec/v1`, role manifests, policy packs и Engine Port, но не владеет данными плана.[cite:61] Поэтому item-level review следует определять прежде всего в контракте Planner и компилировать в `execution-input`/`run-policy overlay`, а не встраивать planner semantics непосредственно в `orch`.

Полная политика `full` содержит optional review, `independent_provider: true`, `max_rounds: 2`, `max_corrections: 1` и triage на implementation class; её бюджеты задаются на уровне всего запуска.[cite:57] Набор policy packs также включает `solo`, `scout-solo`, `frontend-bounded`, `review-only` и `full`, то есть сегодняшняя единица выбора — сценарий запуска, а не review contract конкретного plan item.[cite:55][cite:62]

Role manifest уже является закрытым engine-neutral контрактом, задающим instructions, skills, tools, write authority, result shape, minimum model class и forbidden inputs.[cite:63] Это хороший шаблон для review schema: семантику reviewer следует отделить от конкретного имени модели, сохранив route selector и разрешённые fallback-варианты.

## Целевая модель review

### Почему `false | object` недостаточно

Булево значение удобно сначала, но плохо эволюционирует. Оно не различает:

- review явно запрещён;
- review унаследован;
- planner должен выбрать оптимальную стратегию;
- review будет выполнен сразу после item;
- review будет выполнен в конце группы;
- review является внешним/manual gate;
- review обязателен, но reviewer пока не назначен.

Рекомендуемый обязательный объект:

```json
"review": {
  "mode": "inherit"
}
```

Допустимые modes:

| Mode | Значение |
|---|---|
| `none` | Review явно отключён; обязательны `reason` и `approved_by` для risk-sensitive item |
| `inherit` | Использовать phase/plan/config defaults |
| `auto` | Planner выбирает оптимальную item/group/phase стратегию |
| `item` | Review непосредственно после этого item |
| `group` | Item входит в именованную review group |
| `phase` | Review после completion barrier фазы |
| `plan` | Общий review перед завершением плана |
| `manual` | Human/external approval gate |

`review` должно присутствовать в каждом executable item. Отсутствие поля должно быть schema error. Это исключает различие между «автор сознательно выбрал inherit» и «старый producer забыл поле».

### Предлагаемая схема

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:swissknifeman:planner:review-policy:v2",
  "type": "object",
  "required": ["mode"],
  "properties": {
    "mode": {
      "enum": ["none", "inherit", "auto", "item", "group", "phase", "plan", "manual"]
    },
    "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
    "group_id": {"$ref": "urn:swissknifeman:planner:defs:v2#/$defs/entityId"},
    "strategy": {
      "enum": ["balanced", "fast", "strict", "security", "compliance", "custom"]
    },
    "reviewers": {
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {"$ref": "#/$defs/reviewerSelector"}
    },
    "selection": {
      "type": "object",
      "required": ["cardinality", "failure_mode"],
      "properties": {
        "cardinality": {"enum": ["one", "all", "quorum"]},
        "quorum": {"type": "integer", "minimum": 1},
        "failure_mode": {"enum": ["block", "degrade", "defer", "owner"]},
        "allow_fallback": {"type": "boolean"}
      },
      "additionalProperties": false
    },
    "rounds": {
      "type": "object",
      "required": ["max"],
      "properties": {
        "min": {"type": "integer", "minimum": 0, "default": 1},
        "max": {"type": "integer", "minimum": 1, "maximum": 10},
        "max_corrections": {"type": "integer", "minimum": 0, "maximum": 10},
        "stop_when": {
          "enum": ["accepted", "no_new_findings", "budget_exhausted", "quorum"]
        }
      },
      "additionalProperties": false
    },
    "independence": {
      "type": "object",
      "properties": {
        "provider": {"enum": ["required", "preferred", "not_required"]},
        "model_family": {"enum": ["required", "preferred", "not_required"]},
        "context": {"enum": ["fresh", "execution_bundle", "full_history"]}
      },
      "additionalProperties": false
    },
    "scope": {
      "type": "object",
      "properties": {
        "include": {
          "type": "array",
          "items": {"enum": ["diff", "tests", "artifacts", "acceptance", "dependencies", "security", "docs"]},
          "uniqueItems": true
        },
        "paths": {"type": "array", "items": {"type": "string"}},
        "baseline": {"enum": ["item_start", "group_start", "phase_start", "git_merge_base"]}
      },
      "additionalProperties": false
    },
    "budget_ref": {"$ref": "urn:swissknifeman:planner:defs:v2#/$defs/entityId"},
    "required_checks": {
      "type": "array",
      "items": {"$ref": "urn:swissknifeman:planner:defs:v2#/$defs/entityId"},
      "uniqueItems": true
    },
    "waiver": {"$ref": "#/$defs/reviewWaiver"}
  },
  "allOf": [
    {
      "if": {"properties": {"mode": {"const": "group"}}, "required": ["mode"]},
      "then": {"required": ["group_id"]}
    },
    {
      "if": {"properties": {"mode": {"const": "none"}}, "required": ["mode"]},
      "then": {"required": ["reason"]}
    }
  ],
  "unevaluatedProperties": false,
  "$defs": {
    "reviewerSelector": {
      "type": "object",
      "required": ["provider", "model"],
      "properties": {
        "provider": {"enum": ["claude-code", "codex", "grok"]},
        "model": {"type": "string", "minLength": 1},
        "model_class": {"enum": ["economy", "implementation", "frontier"]},
        "effort": {"enum": ["low", "medium", "high", "max"]},
        "priority": {"type": "integer", "minimum": 0},
        "required_capabilities": {
          "type": "array",
          "items": {"type": "string"},
          "uniqueItems": true
        }
      },
      "additionalProperties": false
    },
    "reviewWaiver": {
      "type": "object",
      "required": ["reason", "approved_by", "expires_at"],
      "properties": {
        "reason": {"type": "string", "minLength": 1},
        "approved_by": {"type": "string", "minLength": 1},
        "expires_at": {"type": "string", "format": "date-time"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": false
    }
  }
}
```

JSON Schema Draft 2020-12 позволяет выразить такие зависимости через `if`/`then`/`else`, `dependentRequired` и `dependentSchemas`; закрывать свойства при композиции удобнее через `unevaluatedProperties: false`.[web:109][web:110][web:113][web:116] При этом нужно подтвердить, что закрытый validator `aicore` поддерживает все выбранные keywords: текущая архитектура использует собственный closed-profile validator, а не произвольную полную реализацию Draft 2020-12.[cite:61]

### Reviewer routes

Поле `reviewers` не должно означать только список provider. Оно должно быть ordered set селекторов:

```json
"reviewers": [
  {
    "provider": "grok",
    "model": "grok-4.7",
    "priority": 10,
    "required_capabilities": ["code-review", "structured-findings"]
  },
  {
    "provider": "codex",
    "model": "gpt-6.1-sol",
    "priority": 20,
    "required_capabilities": ["code-review", "structured-findings"]
  }
],
"selection": {
  "cardinality": "one",
  "allow_fallback": true,
  "failure_mode": "block"
}
```

Это отвечает трём различным случаям:

- **one** — выбрать первого доступного либо оптимального reviewer;
- **all** — каждый reviewer должен вернуть verdict;
- **quorum** — принять решение при заданном количестве согласованных verdicts.

В frozen execution manifest должны попасть не только selectors, но и фактически разрешённые provider/model/version, capability snapshot и причина выбора. Иначе один и тот же план спустя месяц может исполняться иначе после изменения каталога моделей.

### Effective review

Следует хранить оба представления:

```json
"review": {"mode": "inherit"},
"effective_review": {
  "resolved_from": [
    "config:planner.defaults.review",
    "plan:PLAN-42.review_defaults",
    "phase:PH-3.review_defaults"
  ],
  "mode": "group",
  "group_id": "RG-PH3-02",
  "reviewers": [{"provider": "grok", "model": "grok-4.7"}],
  "rounds": {"min": 1, "max": 2, "max_corrections": 1},
  "digest": "sha256:..."
}
```

`review` — authoring intent. `effective_review` — immutable compiled decision. Второе поле не редактируется вручную и пересчитывается при изменении плана. Для базы данных оно может быть materialized projection, а не каноническим источником.

## Review батчей

### Отдельная сущность review group

Review после каждых двух пунктов нельзя надёжно представить только локальным полем item. Нужна самостоятельная сущность:

```json
{
  "id": "RG-PH3-02",
  "phase_id": "PH-3",
  "strategy": "count",
  "members": ["ITEM-3.3", "ITEM-3.4"],
  "trigger": {
    "kind": "all_members_terminal"
  },
  "review": {
    "mode": "group",
    "reviewers": [
      {"provider": "grok", "model": "grok-4.7", "priority": 10}
    ],
    "rounds": {"min": 1, "max": 2, "max_corrections": 1}
  },
  "correction_target": "finding_owner_item",
  "baseline": "group_start"
}
```

Поддерживаемые стратегии группировки:

| Strategy | Применение |
|---|---|
| `explicit` | Автор перечисляет members |
| `count` | Review после каждых N завершённых пунктов |
| `cost` | При достижении token/money/time threshold |
| `risk` | После накопления risk score |
| `component` | По package/module/service |
| `dependency_cut` | После завершения логического слоя DAG |
| `phase_end` | Один review на всю фазу |
| `plan_end` | Один финальный review |

`after_every: 2` удобно как authoring sugar, но перед публикацией должно компилироваться в explicit review groups. Иначе изменение порядка items незаметно изменит смысл review.

### Оптимальная стратегия

`auto` должен быть детерминированной planner policy, а не свободным решением LLM. Пример:

```yaml
review_strategy:
  id: balanced-v2
  rules:
    - when: risk.security == true
      choose: item
      reviewer_class: frontier
      independent_provider: required
    - when: item.side_effects contains migration
      choose: item
    - when: logical_chain.length <= 4 and total_estimated_tokens <= 120000
      choose: group
    - when: component_changes > 3
      choose: dependency_cut
    - otherwise:
      choose: phase
```

LLM может рекомендовать risk tags и grouping, но schema validator и deterministic compiler должны:

- проверять ссылки;
- запрещать циклы;
- материализовать groups;
- проверять coverage;
- гарантировать review до downstream irreversible item;
- фиксировать decision trace.

### Review coverage invariant

Перед публикацией план должен проходить semantic checks:

```text
Каждый executable item покрыт ровно одним effective review disposition:
- reviewed individually;
- входит в review group;
- покрыт phase/plan review;
- имеет валидный waiver.
```

Дополнительные invariants:

- group members принадлежат одному plan;
- item не входит в две blocking groups одного уровня;
- review group не запускается раньше terminal state всех required members;
- item с migration/security/public API не может иметь `none` без waiver;
- reviewer provider отличается от executor provider, если independence required;
- `quorum <= reviewers.length`;
- `min <= max`;
- correction round не может превышать review round;
- downstream gate ждёт verdict, а не только завершение reviewer process.

## Markdown и roadmap

Markdown не должен быть вторым источником истины. Он должен генерироваться из canonical JSON и содержать читаемое review-представление.

### Строка item

```markdown
- [ ] **ITEM-3.4 — Добавить durable result acknowledgement**
  - Depends on: ITEM-3.2, ITEM-3.3
  - Order hint: 340
  - Review: Group `RG-PH3-02`
  - Reviewer candidates: `grok/grok-4.7` → `codex/gpt-6.1-sol`
  - Rounds: 1–2; corrections: 1
  - Scope: diff, tests, acceptance
  - Materials: MAT-12 (required), MAT-18 (reference)
  - Budget: BUD-ITEM-L
```

### Review group

```markdown
#### Review group RG-PH3-02

| Field | Value |
|---|---|
| Trigger | After ITEM-3.3 and ITEM-3.4 |
| Strategy | Dependency cut |
| Reviewer | Grok 4.7, fallback GPT-6.1 Sol |
| Rounds | Maximum 2 |
| Correction | Maximum 1 |
| Baseline | Group start |
| Gate | ITEM-3.5 cannot start before acceptance |
```

### Состояние review

Шаблон должен различать plan-time и run-time:

```markdown
- Review policy: `group / strict`
- Review assignment: `grok/grok-4.7`
- Review state: `pending`
- Last verdict: `not-run`
```

Нельзя заменять policy текущим status. Policy сохраняется при завершении run; status меняется в projection.

### Round-trip защита

Если Markdown редактируется вручную, нужны два режима:

- **Generated-only:** файл полностью перегенерируется, ручные изменения запрещены.
- **Managed blocks:** generator изменяет только подписанные блоки, а пользовательские notes сохраняются отдельно.

Markdown parser не должен реконструировать canonical plan из prose. Импорт допустим только из строго размеченных machine blocks с digest и schema version.

## План как граф и база данных

### `sort_order`

Поле полезно, но не должно задавать семантический порядок выполнения.

```json
"display": {
  "sort_key": "000340",
  "lane": "backend",
  "group": "durability"
}
```

Почему не `sort_order: 7`:

- вставка между 7 и 8 требует массовой перенумерации;
- параллельные ветви не имеют единственного правильного порядка;
- порядок исполнения зависит от dependency readiness;
- пользовательская сортировка и scheduler order — разные понятия.

Лучше хранить:

- `depends_on[]` — жёсткие causal dependencies;
- `blocks[]` — вычисляемая обратная связь, не canonical duplication;
- `display.sort_key` — стабильное отображение;
- `scheduler.priority` — относительный приоритет ready-items;
- `scheduler.not_before` — временное ограничение;
- `gates[]` — acceptance/review/manual prerequisites.

PostgreSQL поддерживает рекурсивные запросы и вычисление depth-first/breadth-first search order, а также cycle detection для recursive CTE; это ещё один аргумент хранить зависимости как рёбра, а не как единственный порядковый номер.[web:135][web:137]

### Нормализованная модель

| Entity | Primary key | Главные связи |
|---|---|---|
| `plans` | `plan_id` | owner, schema version, defaults |
| `phases` | `phase_id` | FK → plan |
| `items` | `item_id` | FK → phase/plan |
| `item_dependencies` | `(from_item,to_item,type)` | FK → items |
| `review_groups` | `review_group_id` | FK → plan/phase |
| `review_group_members` | `(group_id,item_id)` | FK → groups/items |
| `review_policies` | `review_policy_id` | referenced by plan/phase/item/group |
| `material_sources` | `material_id` | immutable source metadata |
| `material_bindings` | `(item_id,material_id,purpose)` | FK → items/materials |
| `budgets` | `budget_id` | reusable budget policy |
| `checks` | `check_id` | acceptance or validation definition |
| `item_checks` | `(item_id,check_id)` | requirement relation |
| `runs` | `run_id` | FK → plan revision |
| `attempts` | `attempt_id` | FK → run/item/stage |
| `review_runs` | `review_run_id` | FK → group/item/attempt |
| `artifacts` | `artifact_id` | content-addressed blob metadata |
| `artifact_links` | `(artifact_id,entity_type,entity_id,role)` | typed association |

Для SQLite необходимо явно включать `PRAGMA foreign_keys = ON`, поскольку enforcement выключен по умолчанию для каждого соединения; referenced non-primary parent keys должны иметь UNIQUE constraint.[web:124][web:125] Рекомендуется также проверять эти настройки в startup doctor и integration tests.

### Идентификаторы

Каждая persistable сущность должна иметь:

```json
{
  "id": "01K7...",
  "schema_version": "planner/v2",
  "revision": 7,
  "created_at": "2026-10-19T06:00:00Z",
  "updated_at": "2026-10-19T06:20:00Z",
  "content_digest": "sha256:..."
}
```

`format: uuid` и `format: date-time` являются стандартизованными annotations JSON Schema, но `format` по умолчанию может не выполнять assertion; validator должен явно включать строгую проверку либо проверять эти значения отдельным semantic layer.[web:128][web:130]

### Revision semantics

Не следует изменять опубликованный план in place:

```text
plan_id: стабильная логическая сущность
revision_id: immutable snapshot
parent_revision_id: предыдущая ревизия
content_digest: digest canonical JSON
status: draft | published | superseded | archived
```

Run всегда ссылается на `revision_id`, а не просто `plan_id`.

## Материалы, артефакты и RAG

### Разделить понятия

Термин `artifact` обычно смешивает несколько разных сущностей:

| Тип | Смысл |
|---|---|
| `source_material` | Исходный документ, предоставленный задаче |
| `context_extract` | Выжимка, созданная scout/context architect |
| `execution_artifact` | Файл или отчёт, созданный executor |
| `evidence` | Результат проверки, лог, test report |
| `deliverable` | Пользовательский конечный результат |
| `reference` | Доступный, но не включённый в prompt материал |

Schema должна различать их, иначе retention, trust и permissions становятся неоднозначными.

### Material descriptor

```json
{
  "id": "MAT-12",
  "kind": "source_material",
  "media_type": "application/pdf",
  "title": "Protocol specification",
  "uri": "artifact://sha256/...",
  "sha256": "...",
  "size_bytes": 18300421,
  "revision": "2026-10-01",
  "trust": "user-provided",
  "sensitivity": "internal",
  "license": "proprietary-internal",
  "retention": "project",
  "access": {
    "roles": ["context-scout", "executor", "reviewer"],
    "network_required": false
  }
}
```

Большой документ не следует помещать непосредственно в plan JSON. План хранит immutable descriptor и content-addressed reference.

### Binding к item

```json
"materials": [
  {
    "material_id": "MAT-12",
    "purpose": "requirements",
    "requirement": "required",
    "delivery": "rag",
    "sections": ["4", "7.2"],
    "must_cite": true,
    "freshness": {"max_age_days": 30},
    "fallback": "block"
  },
  {
    "material_id": "MAT-18",
    "purpose": "background",
    "requirement": "optional",
    "delivery": "reference",
    "must_cite": false,
    "fallback": "continue"
  }
]
```

### Не поле `rag: true`

Булево `rag` слишком неоднозначно. Нужен retrieval policy:

```json
"knowledge": {
  "mode": "required",
  "sources": ["MAT-12", "MAT-18"],
  "retrieval": {
    "strategy": "hybrid",
    "top_k": 12,
    "max_context_tokens": 18000,
    "rerank": true,
    "filters": {
      "revision": "current",
      "sensitivity_max": "internal"
    }
  },
  "grounding": {
    "citations_required": true,
    "minimum_sources": 1,
    "unsupported_claims": "reject"
  },
  "on_unavailable": "block"
}
```

Modes:

- `none` — retrieval запрещён;
- `optional` — можно использовать;
- `required` — execution не начинается без material readiness;
- `evidence_required` — result должен ссылаться на извлечённые fragments;
- `fresh_required` — source freshness проверяется перед запуском.

### Context extract

Scout должен возвращать не только summary, но и provenance:

```json
{
  "extract_id": "CTX-77",
  "item_id": "ITEM-3.4",
  "source_materials": [
    {"material_id": "MAT-12", "digest": "sha256:..."}
  ],
  "claims": [
    {
      "text": "Result acknowledgement must be idempotent.",
      "source": {
        "material_id": "MAT-12",
        "locator": "page:18#paragraph:3",
        "fragment_digest": "sha256:..."
      },
      "confidence": "high"
    }
  ],
  "open_questions": ["Whether acknowledgement TTL is configurable"],
  "reference_access": ["MAT-12", "MAT-18"],
  "created_by": {
    "provider": "claude-code",
    "model": "haiku"
  }
}
```

Executor получает выжимку, но сохраняет read access к исходным materials по `reference_access`. Любое дополнительное чтение записывается в context manifest. Review должен иметь возможность проверить claims против тех же immutable source revisions.

### Material readiness

До запуска item проверяются:

- объект существует;
- digest совпадает;
- media type поддерживается;
- extractor доступен;
- документ не превышает ingestion policy;
- sensitivity совместима с provider;
- лицензия допускает передачу provider;
- required index построен;
- freshness не истекла;
- malware/content scan завершён.

## Бюджеты

### Разделить оценки и ограничения

У item нужны два разных объекта:

```json
"estimate": {
  "complexity": "L",
  "input_tokens": 80000,
  "output_tokens": 12000,
  "wall_time_seconds": 3600,
  "artifact_bytes": 50000000
},
"budget": {
  "policy_id": "BUD-ITEM-L",
  "tokens": {"soft": 120000, "hard": 300000},
  "money": {"soft": 8, "hard": 30, "currency": "USD"},
  "time": {"soft_seconds": 3600, "hard_seconds": 10800},
  "artifacts": {
    "input_bytes": 100000000,
    "output_bytes": 50000000,
    "count": 100
  },
  "retrieval": {
    "documents": 20,
    "chunks": 100,
    "context_tokens": 30000
  },
  "review": {
    "rounds": 2,
    "corrections": 1,
    "tokens": 100000
  },
  "on_soft_limit": "condense",
  "on_hard_limit": "replan"
}
```

Текущая `full` policy имеет общие byte/token/retry limits, причём `stage_tokens_max: 0` означает отсутствие лимита.[cite:57][cite:62] Для больших задач это предотвращает преждевременный отказ, но item schema должна различать unlimited, inherited и explicitly zero; числовой sentinel `0` менее ясен, чем tagged representation.

Рекомендуется:

```json
"stage_tokens": {"mode": "unlimited"}
```

или

```json
"stage_tokens": {"mode": "limit", "soft": 120000, "hard": 300000}
```

### Budget inheritance

```text
organization cap
→ machine cap
→ workspace cap
→ plan cap
→ phase allocation
→ item allocation
→ stage allocation
```

Нижний слой может только уменьшить hard cap, если не приложен signed waiver. Неиспользованный item budget не должен автоматически расширять другой item без deterministic allocator decision.

## Полная item schema

Рекомендуемый item object:

```json
{
  "id": "ITEM-3.4",
  "type": "implementation",
  "phase_id": "PH-3",
  "title": "Добавить durable result acknowledgement",
  "objective": "Исключить потерю результата при разрыве transport",
  "status": "planned",
  "revision": 1,
  "depends_on": [
    {"item_id": "ITEM-3.2", "type": "finish_to_start"},
    {"item_id": "ITEM-3.3", "type": "evidence"}
  ],
  "display": {"sort_key": "000340", "lane": "orchestration"},
  "scheduler": {"priority": 70, "concurrency_key": "orch-state"},
  "scope": {
    "read": ["packages/orch/**", "packages/aicore/**"],
    "write": ["packages/orch/**"],
    "forbidden": ["releases/**"]
  },
  "acceptance": {
    "checks": ["CHK-ACK-IDEMPOTENT", "CHK-REPLAY"],
    "definition_of_done": [
      "Duplicate acknowledgement has no additional effect",
      "Replay reconstructs the same state"
    ]
  },
  "materials": [
    {"material_id": "MAT-12", "purpose": "requirements", "requirement": "required", "delivery": "rag"}
  ],
  "knowledge": {
    "mode": "evidence_required",
    "sources": ["MAT-12"],
    "grounding": {"citations_required": true}
  },
  "execution": {
    "role": "executor",
    "required_capabilities": ["implementation", "structured-result"],
    "provider_preferences": ["codex", "claude-code", "grok"]
  },
  "review": {
    "mode": "group",
    "group_id": "RG-PH3-02"
  },
  "budget_ref": "BUD-ITEM-L",
  "risk": {
    "level": "high",
    "dimensions": ["durability", "data-integrity"]
  },
  "side_effects": ["database-write"],
  "rollback": {
    "required": true,
    "strategy": "feature-flag",
    "evidence_check": "CHK-ROLLBACK"
  },
  "outputs": [
    {"kind": "code-change", "required": true},
    {"kind": "test-evidence", "required": true}
  ],
  "tags": ["orch", "durability"],
  "extensions": {}
}
```

### Дополнительные обязательные поля по типу задачи

Использовать discriminated union по `type`:

| Type | Дополнительные требования |
|---|---|
| `implementation` | scope.write, acceptance, outputs |
| `research` | questions, sources policy, evidence contract |
| `migration` | rollback, backup, compatibility window, irreversible flag |
| `release` | version, changelog, signing, rollout, rollback |
| `security` | threat model, independent review, disclosure policy |
| `documentation` | audience, source-of-truth links, examples |
| `operation` | target environment, maintenance window, approval gate |
| `decision` | options, criteria, decision record output |
| `manual` | owner, instructions, evidence, due policy |

## Семантические валидаторы

JSON Schema недостаточно для междокументных и графовых правил. Нужны отдельные deterministic passes:

1. **Structural validator:** типы, enums, required, closed objects.
2. **Reference validator:** все IDs существуют и имеют правильный kind.
3. **Graph validator:** DAG, отсутствие self-edge, reachable items.
4. **Review coverage validator:** каждый item имеет disposition.
5. **Policy validator:** inheritance не ослабляет security/budget caps.
6. **Material validator:** digest, ACL, sensitivity, freshness.
7. **Scheduling validator:** concurrency keys, barriers, impossible gates.
8. **Database projection validator:** canonical JSON без потерь раскладывается в tables и собирается обратно.
9. **Markdown conformance:** generated roadmap соответствует canonical revision.
10. **Evolution validator:** migration from previous contract version is deterministic.

Ошибки должны иметь стабильные codes:

```text
PLAN_REF_UNKNOWN
PLAN_DEPENDENCY_CYCLE
PLAN_REVIEW_UNCOVERED
PLAN_REVIEW_GROUP_OVERLAP
PLAN_REVIEW_QUORUM_INVALID
PLAN_MATERIAL_DIGEST_MISMATCH
PLAN_KNOWLEDGE_REQUIRED_UNAVAILABLE
PLAN_BUDGET_ESCALATION
PLAN_SORT_KEY_DUPLICATE
PLAN_EXTENSION_UNREGISTERED
PLAN_MARKDOWN_STALE
```

## Конфигурационная целостность

### Не все конфиги должны следовать одной механике

Идея `config.example.toml` → локальный gitignored `config.toml` правильна для **операторских runtime overrides**, но её нельзя механически применять ко всем конфигурационным артефактам.

Нужно разделить:

| Класс | Git | Механика |
|---|---|---|
| Product defaults | tracked | schema + generated example |
| Runtime operator overrides | ignored | copy/merge from example |
| Project policy | tracked | reviewed, deterministic |
| Secrets | never tracked | env/keyring/secret store |
| Toolchain config | tracked | нативный формат инструмента |
| Generated cache/state | ignored | regenerated automatically |
| Model catalog/capabilities | tracked or signed remote | immutable revision |

Например, `mypy.ini` сам по себе не является устаревшим: mypy официально поддерживает `mypy.ini`, `.mypy.ini`, `pyproject.toml` и `setup.cfg`, а INI остаётся нативным форматом конфигурации инструмента.[web:140][web:143] Миграция в `pyproject.toml` может улучшить консолидацию, но не должна проводиться только из-за расширения `.ini`.

TOML действительно лучше подходит для вложенных typed runtime settings: его цель — однозначно отображаться в структуру данных, тогда как INI не стандартизован и неудобен глубже одного-двух уровней.[web:78] Однако формат следует выбирать по owner и контракту, а не вводить обязательный TOML для внешних инструментов.

### Целевая схема runtime config

Для каждого собственного пакета:

```text
configs/config.schema.json       tracked source of truth
config.example.toml              tracked, generated
config.toml                      ignored operator override
config.lock.json                 ignored or runtime state; effective digest
```

Но базовые defaults не следует генерировать в gitignored config как полный снимок. Иначе при обновлении example новая настройка не попадёт в существующий локальный файл.

Лучше:

```text
effective = schema defaults
          + shipped defaults
          + local sparse overrides
          + environment
          + CLI flags
```

`config.toml` должен содержать только overrides. Команда upgrade показывает diff:

```bash
swissknifeman config doctor
swissknifeman config effective --json
swissknifeman config diff-example
swissknifeman config migrate --from 1 --to 2
```

### Versioned config

```toml
schema_version = 2

[orch.review.defaults]
mode = "auto"
strategy = "balanced"

[orch.review.routing]
reviewers = [
  "grok/grok-4.7",
  "codex/gpt-6.1-sol"
]

[orch.models.classes.economy]
claude-code = "haiku"
codex = "gpt-6-luna"
grok = "grok-4.6"
```

Требования:

- неизвестный ключ — ошибка, не warning;
- deprecated key — warning с migration path;
- schema_version обязателен;
- migration сохраняет комментарии либо создаёт patch, а не перезаписывает файл молча;
- `config.example.toml` генерируется из той же schema/default registry;
- example и schema проходят drift test;
- секреты запрещены schema-level annotations;
- effective config имеет digest и provenance.

### Конфиги, требующие отдельной проверки

На зафиксированной ревизии корень содержит `.swissknife.json`, `ruff.toml` и `pyrightconfig.json`; пакеты также используют собственные schema-backed configs и generated examples.[cite:53][cite:61] Для полного config inventory нужен автоматический CI scanner, а не ручной список:

```text
find tracked files by patterns:
*.toml, *.ini, *.cfg, *config*.json, *.yaml, .env*, settings*, policy*

classify owner:
product | toolchain | secret-template | runtime | generated | test-fixture

assert:
registered owner
schema or native-tool validation
tracked/ignored policy
version strategy
upgrade strategy
```

CI должен падать на `CONFIG_UNREGISTERED`, если появляется новый config-like файл без записи в `configs/registry.json`.

Пример registry:

```json
{
  "path": "packages/orch/config.example.toml",
  "owner": "orch",
  "kind": "runtime-example",
  "format": "toml",
  "schema": "packages/orch/configs/config.schema.json",
  "generated": true,
  "live_path": "$SKM_HOME/orch/config.toml",
  "live_tracked": false,
  "migration": "orch-config-v1-v2"
}
```

## Версионирование контрактов

Item-level review нельзя добавлять как незаметное изменение существующей версии, если поле становится required. Нужен новый contract version и deterministic migration:

```text
planner/v1 item without review
→ planner/v2 item.review = {"mode":"inherit"}
```

Этапы rollout:

1. Добавить v2 schemas и dual-read.
2. Добавить migration command.
3. Генерировать v2 для новых планов.
4. Renderers читают v1/v2, пишут только v2.
5. Orch bridge компилирует v2 review в execution overlay.
6. После telemetry включить v2-only publish.
7. Позже удалить v1 write path.

Каждая схема должна иметь:

- стабильный `$id`;
- `contract_version` в экземпляре;
- changelog;
- migration fixtures;
- valid/invalid fixtures;
- consumer conformance tests;
- direction/ownership metadata;
- compatibility policy.

## Что добавить в Planner

### Plan

- `plan_id`, immutable `revision_id`, `parent_revision_id`.
- `schema_version`, `content_digest`.
- `review_defaults` и `review_strategy_ref`.
- `budget_pool` и allocation policy.
- `material_catalog` references.
- `risk_policy_ref`.
- `publish_state`.
- `owners`, `approvers`.
- `labels/tags`.
- `extensions` с namespaced keys.

### Phase

- stable `phase_id`.
- entry/exit gates.
- phase-level review defaults.
- concurrency limit.
- budget allocation.
- rollback boundary.
- material defaults.
- completion policy: all/required/quorum.

### Item

- type discriminator.
- dependency edges.
- display order отдельно от scheduler priority.
- explicit scope.
- acceptance checks.
- materials и retrieval policy.
- estimate и budget отдельно.
- risk dimensions.
- side effects.
- rollback/compensation.
- review intent.
- output contract.
- owner/assignee role.
- concurrency key.
- retry policy.
- idempotency class.
- observability requirements.
- retention/sensitivity.

## Что добавить в Orch

Planner не должен передавать произвольный run policy напрямую. Bridge должен компилировать item semantics в закрытый `execution-input`:

```text
planner item
+ effective review
+ effective budgets
+ material readiness
+ provider catalog snapshot
→ compiled execution request
```

В `execution-input` рекомендуются:

- `plan_revision_id`;
- `item_revision`;
- `effective_review`;
- `context_bundle_ref`;
- `material_refs`;
- `budget_envelope`;
- `route_constraints`;
- `idempotency_key`;
- `policy_digest`;
- `capability_snapshot_digest`.

Run policy остаётся сценарием orchestration, а item review является input-specific overlay. Overlay может сужать возможности policy, но не должен обходить глобальные security constraints.

## Приоритеты реализации

### P0

- Добавить обязательный `review` tagged union в planner/v2.
- Добавить review groups как отдельные entities.
- Ввести effective review compilation и coverage validator.
- Разделить dependency order, display order и scheduler priority.
- Разделить source materials, context extracts, execution artifacts и evidence.
- Ввести immutable plan revisions.
- Добавить reference и graph semantic validation.

### P1

- Добавить material/RAG policy с provenance и citations.
- Разделить estimate и budget.
- Добавить review-specific budget.
- Materialize review в шаблоны roadmap.
- Добавить config registry и `CONFIG_UNREGISTERED` CI check.
- Сделать local runtime config sparse overlay, а не копию defaults.
- Добавить config migration/versioning.

### P2

- Нормализованная SQL projection и round-trip tests.
- Auto review strategy compiler.
- Risk-based grouping.
- Quorum reviewers.
- GUI plan graph, review coverage и material lineage.
- Policy simulation до публикации плана.

## Acceptance criteria

Работа считается завершённой, когда:

- каждый executable item явно содержит `review`;
- ни один опубликованный item не остаётся без effective review disposition;
- review после каждых N items компилируется в explicit immutable groups;
- roadmap показывает policy, assignment и runtime status раздельно;
- reviewer routes позволяют one/all/quorum и fallback;
- provider/model resolution замораживается в run manifest;
- dependency DAG не смешивается с sort/display order;
- plan revision immutable и адресуется digest;
- большие материалы передаются ссылками, а extracts содержат provenance;
- executor может дочитать разрешённый original material;
- required RAG отсутствие блокирует запуск;
- budget учитывает retrieval, artifacts и review rounds;
- config inventory полон и проверяется CI;
- schema/example/effective config не расходятся;
- v1 → v2 migration детерминирована и покрыта fixtures;
- JSON → DB → JSON round trip не теряет семантику;
- структурная, ссылочная и графовая валидация имеют стабильные error codes.

## Итог

Главное изменение — перенести review из общего флага run policy в полноценную доменную модель Planner, сохранив `orch` как исполнитель с закрытыми контрактами. Для каждого пункта должен существовать явный review intent; для каждой опубликованной ревизии — вычисленный effective review; для каждого запуска — замороженный reviewer assignment; для каждого результата — отдельное review evidence.

Гибкий batching следует моделировать review groups, а не неявным «после каждых двух» во время исполнения. Порядок следует задавать dependency graph, gates и scheduler priority, оставляя `sort_key` только представлению. Материалы и RAG должны стать typed, content-addressed и provenance-aware, а конфигурация — schema-backed, versioned, sparse-overlay и полностью зарегистрированной в одном inventory.
