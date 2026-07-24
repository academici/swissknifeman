# Research 02 — target operating model

## Один входной контракт

Перед mutation root компилирует `Task Contract v1`:

| Поле | Значение |
|:--|:--|
| Goal | один outcome пользователя |
| Constraints | hard requirements и non-goals |
| Done | observable public/consumer acceptance, не только internal artifact |
| Authority | что можно делать автоматически; exact stop boundaries |
| Next | один executable next step |
| Route | required/actual model+effort |
| Evidence | exact source refs |
| Conflicts | lower-priority stale carriers и resolution |
| Version | content hash + supersedes |

Task Contract не становится новой ручной копией: он является generated
snapshot из canonical carriers и хранит provenance.

Перед mutation и перед final response выполняется contract check. GREEN
запрещён, если item заявляет consumer/cold-start path, а проверены только
package-local bytes/goldens.

## Execution state machine

```text
READY → EXECUTING → VERIFYING → DONE
  │         │           │
  │         ├─ real defect ─→ FIXING ─→ VERIFYING
  │         │                    │
  │         │            same finding >2
  │         │                    ↓
  │         └──────────────→ INCIDENT
  │
  └─ authority missing / external change ─→ OWNER_BOUNDARY
```

`INCIDENT` не означает бесконечный stop: root фиксирует cause/action,
продолжает независимые ready items и запрашивает владельца только если
исправление требует новой authority.

## Source resolution

- canonical semantic body: `packages/skiller/skills` или
  `packages/task/commands`;
- repo `.agents/skills`: только tiny pointer/adapter с provenance;
- generated provider bundle: immutable version→tree hash, complete runtime
  dependency closure;
- installed plugin: один active identity; equivalent local adapter
  suppressed после proof;
- provider-specific claim: capability mapping + behavioral eval или
  fail-closed unpublished.

## Review matrix

| Risk | Review |
|:--|:--|
| low, local, reversible | self-check + focused tests |
| medium, shared but frozen contract | one targeted independent reviewer |
| high/public/security/runtime lifecycle | phase-terminal adversarial audit |

Audits не запускаются на каждый bookkeeping step. Product/evidence states
разделены. Full validation выполняется один раз на terminal phase, targeted
checks — после bounded fix.

## Session/context policy

- main/root сохраняет Task Contract и decisions;
- subagent получает минимальный item slice + contract hash;
- одна linked phase остаётся в одной session, пока context healthy;
- compaction переносит Task Contract, current diff, failed check и exact next;
- новый session не перечитывает весь history без evidence need.

## Why this is minimal

Модель не вводит внешний orchestrator или новый persistence service.
Она переиспользует plan/task/skiller/harness/analyst/maind и устраняет
дублирующие carriers. Новые contracts являются маленькими machine-readable
seams, а не вторым набором narrative docs.
