# Dual-provider domain language

> **OWNER-APPROVED — D53.** Весь glossary утверждён вместе с scenario set
> `research/04-provider-domain-scenarios.md`. Evidence boundary: terminal P0.5 finding
> на tree `d8ac22c04fc4d4219dc95244ee9d181e92553a74`; его counts — current observations,
> а не frozen contract constants.

Общий язык экосистемы swissknifeman для provider-neutral semantics и provider-native
представлений. Этот glossary определяет только смысл терминов; форматы файлов, схемы,
precedence и алгоритмы принадлежат последующим contracts.

**Approval Owner:** Dmitry Vostrikov  
**Approval:** D53, 2026-07-20

## Bounded contexts

| Context | Stewardship | Relationship |
|:--|:--|:--|
| `core/providers` | provider identity, capability support и security distinctions | Поставляет общий язык всем остальным contexts; не знает provider renderers. |
| `core/artifacts` | canonical/rendered/managed lifecycle, override, drift и repair | Поставляет provider-neutral artifact semantics публикации, harness и deployment. |
| `skiller/publication` | skills и их provider publication | Потребляет provider/artifact vocabulary; владеет semantic skill catalog. |
| `task/command-contract` | semantic task commands и provider projections | Потребляет provider/artifact vocabulary; владеет значением Task Command. |
| `harness/rendering` | provider-native environment surfaces | Проецирует общий intent, не переопределяя trust/approval/sandbox. |
| `maind/deployment` | effective providers проекта и lifecycle deployment | Оркестрирует adapters, не становится renderer или владельцем capability semantics. |
| `analyst/events` | neutral run/session/event meaning | Нормализует provider observations, сохраняя provenance provider'а. |
| `ecosystem/command-inventory` | umbrella inventory top-level package command surfaces | Агрегирует package-owned definitions, но не переименовывает их все в Task Commands. |

## Language

### Provider

Поддерживаемая agent-development среда, для которой swissknifeman публикует и обслуживает
нативные представления общего semantic source.

**Steward:** `core/providers`  
**Crosses:** `skiller`, `task`, `harness`, `maind`, `analyst`  
**allowed synonym:** provider environment — только когда environment scope явен.  
**deprecated synonym:** agent, client, platform — слишком широкие или неоднозначные слова.

### Provider ID

Стабильная внутренняя идентичность Provider, независимая от UI-имени, брендинга и версии.
Первая поддерживаемая пара: `claude-code` и `codex`.

**Steward:** `core/providers`  
**Crosses:** все provider-aware contexts  
**allowed synonym:** stable provider identifier.  
**deprecated synonym:** provider name, model name, CLI name.

### Capability

Стабильный semantic intent, который Provider способен предоставить нативно, через Adapter
или не способен предоставить в поддерживаемой форме.

**Steward:** `core/providers`  
**Crosses:** `skiller`, `task`, `harness`, `maind`, `analyst`  
**allowed synonym:** provider capability — если нужна явная привязка к Provider.  
**deprecated synonym:** feature flag, provider option, config key.

### Support Level

Утверждение о том, как конкретный Provider реализует Capability: `native` — напрямую своей
семантикой; `adapted` — детерминированной проекцией с сохранением intent; `unsupported` —
поддерживаемого эквивалента нет. `unsupported` нельзя молча выдавать за parity.

**Steward:** `core/providers`  
**Crosses:** capability catalog, adapters, diagnostics, generated documentation  
**allowed synonym:** capability support level.  
**deprecated synonym:** parity boolean, supported flag, best effort.

### Canonical Source

Единственный author-owned semantic источник, из которого производятся provider-specific
представления; provider output не может становиться его обратным источником.

**Steward:** `core/artifacts`  
**Crosses:** `skiller`, `task`, `harness`, `maind`  
**allowed synonym:** semantic source.  
**deprecated synonym:** master copy, Claude source, primary output.

### Adapter

Provider-specific преобразователь Canonical Source в нативное представление с явно
заявленными Capability requirements и Support Level.

**Steward:** `core/artifacts`  
**Crosses:** publication, command projection, harness rendering, deployment  
**allowed synonym:** provider adapter.  
**deprecated synonym:** copier, compatibility shim, provider fork.

### Rendered Artifact

Provider-native представление, полученное Adapter'ом из Canonical Source и отличимое от
самого semantic source.

**Steward:** `core/artifacts`  
**Crosses:** `skiller`, `task`, `harness`, `maind`  
**allowed synonym:** provider output — только при указанном Adapter/provenance.  
**deprecated synonym:** canonical file, source copy, manual mirror.

### Native Extension

Provider-specific возможность сверх общего capability set, которая сохраняется явно и не
объявляется общей parity-возможностью без semantic эквивалента у другого Provider.

**Steward:** `core/providers`  
**Crosses:** capability catalog, provider adapters, generated documentation  
**allowed synonym:** provider-native extension.  
**deprecated synonym:** common capability, hidden special case, parity exception.

### Managed Artifact

Rendered Artifact с явно переданной swissknifeman зоной владения, provenance и правом на
контролируемое обновление или Repair только внутри этой зоны.

**Steward:** `core/artifacts`  
**Crosses:** publication, harness rendering, deployment, doctor  
**allowed synonym:** managed provider artifact.  
**deprecated synonym:** generated file, owned project file, safe-to-overwrite file.

### Override

Явный user- или project-owned semantic input, который изменяет effective intent без ручной
правки Managed Artifact и сохраняет отдельное владение.

**Steward:** `core/artifacts`  
**Crosses:** provider config, publication, harness, deployment  
**allowed synonym:** project override, local override — только с явным owner layer.  
**deprecated synonym:** local patch, edited generated output, exception file.

### Drift

Проверяемое расхождение между ожидаемым Rendered Artifact и наблюдаемым состоянием с учётом
Canonical Source, Adapter, provenance, managed boundary и разрешённого Override.

**Steward:** `core/artifacts`  
**Crosses:** publication, harness, deployment, doctor  
**allowed synonym:** managed drift.  
**deprecated synonym:** any diff, local customization, corruption.

### Repair

Контролируемое восстановление ожидаемого состояния Managed Artifact после классифицированного
Drift без изменения Canonical Source, Override или user-owned области.

**Steward:** `core/artifacts`  
**Crosses:** publication, harness, deployment, doctor  
**allowed synonym:** managed repair.  
**deprecated synonym:** overwrite, reset, regenerate everything.

### Project Trust

Provider-native решение о том, можно ли активировать project-scoped instructions и
configuration. Trust не предоставляет доступ за Sandbox Boundary и не заменяет Approval Policy.

**Steward:** `core/providers`  
**Crosses:** harness, deployment, provider activation  
**allowed synonym:** workspace trust — только как provider-native binding этого понятия.  
**deprecated synonym:** permission mode, sandbox mode, approval mode.

### Approval Policy

Политика того, когда Provider запрашивает человеческое подтверждение операции. Отсутствие
запросов не расширяет Sandbox Boundary и не означает Project Trust.

**Steward:** `core/providers`  
**Crosses:** harness security profiles, deployment, operator documentation  
**allowed synonym:** approval prompting policy.  
**deprecated synonym:** access level, autonomy level, sandbox permission.

### Sandbox Boundary

Максимальная граница ресурсов и действий, доступных Provider независимо от частоты approval
prompts. Расширение границы является отдельным явным выбором.

**Steward:** `core/providers`  
**Crosses:** harness security profiles, deployment, operator documentation  
**allowed synonym:** sandbox access boundary.  
**deprecated synonym:** approval policy, trust level, auto-approve.

### Command Surface

Umbrella union direct Markdown command definitions в пяти явно перечисленных
first-party package roots: task, skiller, harness, maind и analyst. Это inventory
class, а не общий semantic contract всех команд. На terminal P0.5 anchor union
содержит 32 entries (`11 + 5 + 6 + 8 + 2`), но число остаётся tree-anchored
observation, не frozen invariant.

**Steward:** `ecosystem/command-inventory`  
**Crosses:** `task`, `skiller`, `harness`, `maind`, `analyst`, provider publication  
**allowed synonym:** top-level package command surface.  
**deprecated synonym:** task commands — когда этим именем называют union всех package surfaces.

### Task Command

Provider-neutral intent workflow из canonical `task` source, публикуемый через нативные
provider projections. Current source set — 11 direct файлов `packages/task/commands/*.md`;
он является подмножеством Command Surface. Это semantic command, а не любой command file
или только slash syntax; anchored count не является вечным contract invariant.

**Steward:** `task/command-contract`  
**Crosses:** `task`, `skiller`, provider marketplaces  
**allowed synonym:** semantic task workflow — только когда command identity сохраняется.  
**deprecated synonym:** slash command, command file, all package commands.

## Collision register

| Collision | Canonical distinction | Steward |
|:--|:--|:--|
| provider / model / agent | Provider — среда; model — execution resource; agent — actor/configuration внутри среды. | `core/providers` |
| capability / provider option | Capability — semantic intent; option — provider-native binding detail. | `core/providers` |
| canonical / rendered / managed | Canonical Source задаёт смысл; Rendered Artifact представляет его; Managed Artifact добавляет ownership lifecycle. | `core/artifacts` |
| override / drift | Override разрешён и отделён от managed output; Drift — проверяемое нежелательное расхождение. | `core/artifacts` |
| trust / approval / sandbox | Activation, prompt policy и access boundary — три независимых решения. | `core/providers` |
| command surface / task command; count 32 / 11 | Command Surface — umbrella union пяти top-level roots (`32` current); Task Command — semantic `packages/task/commands` subset (`11` current). | `ecosystem/command-inventory` + `task/command-contract` |
