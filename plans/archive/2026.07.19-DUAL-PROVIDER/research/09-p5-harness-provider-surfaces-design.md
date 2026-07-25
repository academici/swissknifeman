# P5 design synthesis — provider-native harness surfaces

**Дата:** 2026-07-19

**Основание:** `findings/P5-harness-recon-2026-07-19.md`,
`findings/provider-capabilities-2026-07-19.md`, `brief/00-brief.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/08-p4-task-command-routing-design.md`, draft
`root/contracts/provider-{capability,config}-contract.md` и D2/D3/D5/D9/D24–D27.

## Целевая граница

P5 вводит frozen `provider-harness-contract`: stable profile/surface identity,
security intent, provider-native projections, scope/precedence, managed ownership,
diagnostics и conformance. Common catalog не хранит `.claude`/`.codex` paths, provider
hook events или low-level permission keys. Named Claude/Codex renderers получают explicit
effective provider config, capability manifest, P2 artifact engine и P4 command mapping.

Claude current behavior остаётся compatibility surface. Codex adapter рендерит native
config/trust/approval/sandbox/hooks/MCP/agents artifacts только для trusted/explicit target.
Unsupported provider-native feature остаётся видимым structured diagnostic; ему не
эмулируют ложный parity shell-hook'ом.

## Рассмотренные альтернативы

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Оставить `configs/claude-code` общим каноном и переводить его в Codex | малый стартовый diff | Claude поля становятся скрытым public API; trust/hooks/MCP semantics искажаются | отклонить |
| Поддерживать два независимых config tree вручную | нативные файлы сразу | второй semantic canon, profile drift и двойные fixes | отклонить |
| Один lowest-common-denominator settings JSON | простая schema | теряет provider-native hooks, trust, scopes и agents | отклонить |
| Semantic profile/surface catalog + explicit native adapters/extensions | единый intent, native output, capability diagnostics и lock | требует frozen contract и conformance | принять |
| Один универсальный `yolo` profile | удобное имя | смешивает approval и sandbox; может неявно расширить доступ | отклонить |
| Stable safety intents + явные provider projections | автономность выражена без подмены security semantics | нужен owner-gated mapping | принять |

## Contract outline

P5.1 замораживает:

- stable profile IDs, surface IDs и lifecycle/versioning;
- semantic sections `security`, `hooks`, `context`, `mcp`, `agents`, `agent-packs`;
- support state и capability references вместо silent omission;
- target scope (`project`/`user`/`managed`) и provider-native precedence;
- managed/user-owned boundaries, merge/replace/remove и repair semantics;
- security intent отдельно от provider projection: approval, sandbox, trust prerequisite;
- обязательный explicit full-access operation, который не наследуется default/fleet merge;
- secret references/placeholders; resolved secret values не входят в catalog/lock/report;
- provenance/source/render hashes, diagnostic codes и golden examples;
- compatibility policy для текущей Claude surface и consumer contract для P6/P7.

Exact low-level keys, event names и paths живут только в projection sections. Draft P0/P1/P4
contracts и bootstrap config не являются основанием для freeze: P5.1 имеет hard entry gate
на terminal/frozen predecessor evidence и owner approval.

## Item sequence

1. P5.1 запечатывает harness contract и catalog boundary без package code.
2. P5.2 вводит common profile resolver/render base и security projections; он первым меняет
   package и проходит contribution gate.
3. P5.3 поверх P5.2 добавляет lifecycle hooks/context features с capability/trust gates.
4. P5.4 потребляет P5.3 lifecycle registration для MCP, agents и agent-pack projections.
5. P5.5 строит независимый expected inventory, doctor/conformance и generated docs.

Последовательность намеренная: P5.2–P5.4 меняют один catalog/render/managed-boundary seam и
каждый потребляет deliverable предыдущего. Три независимых deterministic scope отсутствуют,
поэтому workflow criterion не срабатывает.

## Security и compatibility invariants

- `approval=never` и sandbox boundary — независимые axes; отсутствие prompt не означает
  расширение filesystem/network access. RAG:✅ 2026-07-19
  (`findings/provider-capabilities-2026-07-19.md`).
- Full access существует только как explicit trusted opt-in operation; implicit default,
  project/fleet inheritance и fallback на него запрещены.
- Missing trust/capability/mapping/secret reference диагностируется до write; renderer не
  выбирает «ближайший» профиль.
- Existing Claude presets, hooks, agent-pack locks/upgrade categories и command/plugin
  behavior имеют independent pre-change compatibility fixtures.
- Common catalog не содержит provider target paths/events/model names; provider output не
  переводится из output другого provider.
- Secrets не сериализуются в generated artifacts, locks, reports или tests.
- P5 test/render targets — temp only; self-host apply принадлежит P7, fleet — отдельной волне.

## Pre-mortem P5

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| «Автономный» профиль случайно даёт full access | default/fleet merge способен выбрать danger profile | отдельный explicit operation + no-inheritance schema + negative cases | Owner/P5.1–P5.2 |
| Common schema становится копией Claude settings | `.claude`, `PreToolUse`, `permissions.defaultMode` встречаются в semantic catalog | schema rejection + named projection fields | P5.1/P5.5 |
| Codex hook объявлен supported, но project untrusted | render green, runtime silently ignores config | trust prerequisite + activation diagnostic/doctor | P5.3/P5.5 |
| Agent pack «работает» только в source checkout | rendered agents/hooks ссылаются на package-relative templates | cache-contained bundle test + P2 lock | P5.4/P5.5 |
| MCP secrets попадают в lock/report | golden содержит token/env value | secret-reference-only contract + redaction tests | P5.1/P5.4/P5.5 |
| Claude compatibility ломается при общей модели | pre-change settings/hooks/pack fixtures меняются | independent golden; actual не обновляет expected | P5.2–P5.5 |
| P5 design mutates bootstrap/FOREMAN/fleet | protected path diff | before/after snapshot, temp targets, delta=0 | каждый package item |

## Verification

- Repo-grounding: `packages/harness/CLAUDE.md`, relevant modules/config inventory и
  current P4/P5 plan artifacts прочитаны; package code и package scripts не исполнялись.
- External: новых capability claims не получено; использован уже сохранённый first-party
  digest `findings/provider-capabilities-2026-07-19.md` с датой и URLs.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: exact P0/P1/P4 frozen fields и P2 renderer API пока не
  существуют; P5.1–P5.5 держат их hard entry gates, а не предполагают форму.
- `[POSSIBLE-DEFECT]`: current `settings_audit.py` слишком Claude-specific для общего doctor;
  P5.5 должен сохранить его named Claude checker и собрать provider-level conformance над
  ним, не переименовать существующий module в generic без разделения semantics.
