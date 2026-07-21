# Provider capability contract

**Version:** v1.0.0

**Status:** frozen

**Approval Owner:** Dmitry Vostrikov

**Approval:** D55, 2026-07-20

**Vocabulary:** `../CONTEXT.md`, approved D53

## Purpose

Этот контракт задаёт один versioned capability manifest для поддерживаемых Provider'ов.
Manifest является единственным источником Support Level, provider-native binding,
Native Extension, adapter gates, diagnostics и generated capability matrix. README,
doctor и provider adapters не ведут собственные списки поддержки.

Контракт не описывает provider config carriers, output paths или реализацию parser'а.
Текущие inventory counts P0.1/P0.5 остаются tree-anchored observations и не входят в
нормативную модель.

Нормативные слова `MUST`, `MUST NOT`, `SHOULD` и `MAY` трактуются буквально. D55 заморозил
этот contract как обязательный вход последующей implementation.

## Vocabulary

Контракт использует без переопределения термины D53:

- **Provider** и стабильный **Provider ID**;
- **Capability** и **Support Level** `native` / `adapted` / `unsupported`;
- **Adapter** и **Native Extension**;
- отдельные **Project Trust**, **Approval Policy** и **Sandbox Boundary**.

Первый поддерживаемый provider set состоит из `claude-code` и `codex`. Display name,
CLI name, model family и UI alias не являются Provider ID.

Project Trust управляет activation project-scoped surfaces; Approval Policy — моментом
human confirmation; Sandbox Boundary — максимальной границей доступа. Manifest MUST NOT
схлопывать их в `permission_mode`, `autonomy` или единый boolean.

## Normative model

### Manifest envelope

Машиночитаемый manifest MUST иметь следующую семантическую форму. Конкретный carrier и
parser принадлежат P1; имена ниже являются frozen contract keys:

| Key | Cardinality | Contract |
|:--|:--|:--|
| `contract_version` | exactly one | SemVer этого schema contract; для данного freeze — `1.0.0`. |
| `catalog_version` | exactly one | SemVer содержимого provider/capability catalog. |
| `providers` | one or more | Уникальные Provider records, включая `claude-code` и `codex`. |
| `capabilities` | one or more | Уникальные Capability records; каждый содержит полную provider matrix. |
| `native_extensions` | zero or more | Явные provider-owned records без parity claim. |

Provider record MUST содержать стабильный `id` и MAY содержать display metadata.
Display metadata не участвует в identity. Provider ID после публикации нельзя переиспользовать
для другой среды.

Capability record MUST содержать:

| Key | Contract |
|:--|:--|
| `id` | Стабильный semantic ID, не зависящий от provider path/key/event. |
| `intent` | Observable promise Capability без provider-native syntax. |
| `support` | Ровно один Support record на каждый Provider из `providers`. |

Capability ID MUST начинаться с ASCII lowercase letter и состоять из lowercase segments,
разделённых `.`; внутри segment разрешены lowercase letters, digits и `-`. Удалённый ID
не переиспользуется с новым смыслом.

Support record MUST содержать:

| Key | Contract |
|:--|:--|
| `level` | Ровно одно из `native`, `adapted`, `unsupported`. |
| `binding` | Provider-native binding metadata; обязательно для `native`, допустимо для `adapted`, запрещено для `unsupported`. |
| `adapter_id` | Стабильная identity Adapter; обязательно только для `adapted`. |
| `limitations` | Явные ограничения observable promise; пустой список допустим. |
| `evidence` | Непустой список source/scope/verification records, подтверждающих claim. |
| `diagnostic` | Объяснение level и допустимого следующего действия для operator'а. |

Evidence record MUST содержать `source`, `verified_at`, `scope` и `claim`. External provider
claim требует current first-party source. Repo-grounded adapted claim MAY ссылаться на
committed test/evidence artifact. URL, path или date сами по себе без `claim` не являются
evidence.

### Support Level invariants

- `native`: Provider исполняет Capability своей нативной семантикой; `binding` и evidence
  обязательны, `adapter_id` отсутствует.
- `adapted`: deterministic Adapter сохраняет заявленный observable intent; `adapter_id`,
  ограничения и evidence обязательны. Projection нельзя выдавать за native.
- `unsupported`: поддерживаемого semantic equivalent нет; `binding` и `adapter_id`
  отсутствуют, diagnostic называет fail-closed outcome или явное исключение Capability.
- Отсутствующий Support record не равен `unsupported`; это invalid manifest.
- Unknown level, unknown Provider ID и unknown contract major fail closed.

### Native Extensions

Native Extension record MUST содержать provider-namespaced `id`, `provider_id`, `intent`,
provider-native `binding`, evidence и diagnostic. Его ID начинается с `<provider-id>.`.
Extension не добавляется в common Capability matrix, пока для неё не утверждён общий
semantic intent и Support record каждого Provider.

### Derived consumers

README matrix, operator docs, doctor output и adapter capability gates MUST быть derived
из одного manifest. Consumer MAY фильтровать presentation, но MUST NOT менять level,
скрывать `unsupported`, превращать Native Extension в common parity или подменять evidence.

Adapter MUST объявить требуемые Capability IDs и допустимые Support Levels до render.
Unknown/missing/unsupported requirement блокирует render до записи output. `adapted`
разрешён только если Adapter явно допускает adapted promise.

Отсутствующий project provider config (S7) не является отсутствующим Support record и не
может автоматически означать `unsupported` или explicit disable. Effective Provider/default
и provenance такого решения принадлежат frozen P1 config contract.

## Compatibility

`contract_version` и `catalog_version` используют SemVer независимо:

- contract **major**: удаление/переименование frozen key, изменение смысла Support Level,
  identity или fail-closed rule;
- contract **minor**: additive optional key или новая обратно совместимая validation rule;
- contract **patch**: editorial clarification без semantic change;
- catalog **major**: удаление/переименование Provider/Capability ID, сужение observable
  intent, downgrade `native|adapted → unsupported` или несовместимое изменение limitations;
- catalog **minor**: новый Provider/Capability/Native Extension, либо support improvement
  `unsupported → adapted|native` / `adapted → native` при сохранённом intent;
- catalog **patch**: evidence refresh, display/binding metadata или diagnostic без изменения
  intent, level и limitations.

Consumer MUST pin supported contract major и сохранять observed catalog version в
provenance. Неизвестный major или semantic downgrade не получает compatibility fallback.

После freeze/изменения владелец contract обновляет `plan.md` Contracts/Decision Log и
уведомляет same-root consumer plans по plan-protocol Contracts. Cross-repo consumer
получает explicit mAInd/open-risk notification; молчаливое «уведомим позже» запрещено.

## Validation

Manifest validator MUST отвергать как минимум:

1. duplicate/invalid Provider ID или Capability ID;
2. provider matrix, где отсутствует или продублирован Support record;
3. unknown Support Level;
4. `native` без binding/evidence или с `adapter_id`;
5. `adapted` без `adapter_id`, limitations или evidence;
6. `unsupported` с binding/adapter либо без fail-closed diagnostic;
7. Native Extension без provider namespace/evidence;
8. смешение Project Trust, Approval Policy и Sandbox Boundary в одном capability value;
9. generated matrix/diagnostic, не совпадающие с manifest;
10. unknown contract major.

Validation и check/doctor operations MUST быть no-write. Writer не начинает render, пока
все Capability requirements Adapter'а не прошли validation.

## Examples

### Golden manifest fragment

```json
{
  "contract_version": "1.0.0",
  "catalog_version": "1.0.0",
  "providers": [
    {"id": "claude-code", "display_name": "Claude Code"},
    {"id": "codex", "display_name": "Codex"}
  ],
  "capabilities": [
    {
      "id": "instructions.project",
      "intent": "activate repository-scoped operator instructions after provider trust checks",
      "support": {
        "claude-code": {
          "level": "native",
          "binding": {"surface": "CLAUDE.md"},
          "adapter_id": null,
          "limitations": [],
          "evidence": [{
            "source": "findings/provider-capabilities-2026-07-19.md",
            "verified_at": "2026-07-19",
            "scope": "Claude Code project instructions",
            "claim": "provider has a native project instruction surface"
          }],
          "diagnostic": "native project instructions; activation remains trust-gated"
        },
        "codex": {
          "level": "native",
          "binding": {"surface": "AGENTS.md"},
          "adapter_id": null,
          "limitations": [],
          "evidence": [{
            "source": "findings/provider-capabilities-2026-07-19.md",
            "verified_at": "2026-07-19",
            "scope": "Codex project instructions",
            "claim": "provider has a native repository instruction chain"
          }],
          "diagnostic": "native repository instructions; activation remains trust-gated"
        }
      }
    }
  ],
  "native_extensions": []
}
```

Этот пример проверяет S1. Для S2 `level=adapted` добавляет `adapter_id` и limitations;
для S3 `level=unsupported` удаляет binding/adapter и добавляет fail-closed diagnostic;
для S8 provider-namespaced record помещается только в `native_extensions`.

### Independent security axes

Manifest MAY иметь отдельные Capability IDs для project activation, approval prompting
и sandbox access. Из `approval_policy=never` нельзя вывести trusted project или расширенную
Sandbox Boundary: такое derived правило невалидно по S4/S9.
