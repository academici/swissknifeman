# Model-local verification instruction template

Use this template to author or audit one model's verification instruction. Keep generic
capture, hashing, cleanup, transaction, and report mechanics in the shared skill. Replace
every placeholder with model-owned truth; do not copy values from another model.

## Contents

1. Authority and ownership
2. Sources and run controls
3. Ordered lifecycle
4. Step catalogue
5. Report and promotion contract
6. Conformance checklist

## Authority and ownership

```markdown
# <Model> verification instruction — verification-v1

## Authority and non-claims

This instruction owns model-specific inventory, interfaces, views, expected observations,
thresholds, printer facts, and blockers. The shared model-verification skill owns mechanics.

State which geometry, assembly, print, optical, electrical, and physical claims remain
unverified or owner-gated. State that section/cut modes are display-only when applicable.
```

## Sources and run controls

Name executable providers or authoritative documents for all of these:

| Required source | Model-local value |
|:--|:--|
| active model/mode loader | `<module:function or command>` |
| final-object inventory | `<provider>` |
| print-unit inventory | `<provider>` |
| interface/datum catalogue | `<provider or contract>` |
| config/derivation gate | `<plain-Python command>` |
| production build entry point | `<module:function>` |
| evaluated mesh checks | `<module:function>` |
| capture runner | `<module:function or script>` |
| visual analysis/closure | `<supported command or operator procedure>` |
| routine workspace | `models/<model>/test/artifacts/verification/current/` |
| explicit promotion command | `<command>` |

Declare release and diagnostic behaviour, the required full/default build mode, provenance
inputs to hash, printer/profile identity when relevant, and model-specific early blockers.

## Ordered lifecycle

Map the shared stages without reordering. Give each model stage a stable id and name its
model-local action, inputs, output, and stop/continue rule:

1. provenance/preflight;
2. plain-Python/config gates;
3. default production build and exact inventory;
4. evaluated final-mesh and real-interface metrics;
5. isolated final-object views;
6. assembly/interface/section contexts;
7. explicit expected-vs-observed image analysis;
8. aggregate report and verified transactional restore.

## Step catalogue

Represent every required object, print unit, interface, datum, and prescribed context as a
Markdown table or executable data structure. Every step must expose these fields:

| Field | Requirement |
|:--|:--|
| `id` | Stable unique identifier. |
| `target` | Exact model-owned object, print unit, interface, or datum. |
| `visible_context` | Exact real counterpart set; use `target-only` for isolation. |
| `build_mode` | Production proof mode; use full/default for geometry. |
| `view_preset` | Technical/material/xray/section preset and named view roles. |
| `framing_rule` | Config-derived datum or evaluated-world-bounds rule. |
| `automated_prerequisites` | Earlier gates and fresh metrics required by this step. |
| `expected_observations` | Non-empty, falsifiable, metric/view-linked observations. |
| `red_conditions` | Non-empty explicit failure or blocker conditions. |
| `evidence_stem` | Deterministic filename stem unique within the run. |
| `claim_boundary` | Digital/interface scope, physical non-claim, or owner gate. |

Require at least primary and oblique isolated evidence for every final printable object.
Add detail, underside, interface, xray, or section views whenever the first two do not expose
all required features. Require a measurable check plus a prescribed context for every real
interface, or retain an explicit owner gate with a diagnostic context.

Reject subjective expected observations such as "looks correct". Name silhouette, surface,
appendage, boolean-scar, thin-contact, interface, handedness, orientation, or model-specific
features that the evidence must decide.

## Report and promotion contract

Require `manifest.json`, `metrics.json`, `report.json`, `report.md`, and deterministic view
files in the routine workspace. Each report row contains step id, target, verdict, expected
and observed facts, exact evidence paths, freshness identity, claim boundary, blocker/RED
reason, and next safe action.

Summarize exact inventory, isolated-view, interface-context, and visual-analysis coverage;
per-verdict totals; candidate identity; restore status; and all physical non-claims. Define
which model-specific gates must be GREEN before an explicit non-overwriting baseline promotion.

## Conformance checklist

- [ ] Inventory and interface sources are authoritative and executable or documented.
- [ ] Every shared lifecycle stage is mapped in order.
- [ ] Every final printable object has fresh metrics and required isolated views.
- [ ] Every real interface has a measured check and prescribed context or explicit blocker.
- [ ] Every step has all catalogue fields and falsifiable observations.
- [ ] Release stops on early RED; diagnostic continuation stays diagnostic-red.
- [ ] Routine cleanup proves the exact model-owned current path and rejects symlinks/escape.
- [ ] Source/tool/profile changes stale dependent evidence.
- [ ] Capture restores scene and viewport state in `finally` and verifies restoration.
- [ ] Images require explicit analysis and cannot auto-pass.
- [ ] Promotion is explicit, non-overwriting, fresh, complete, restored, and GREEN-only.
- [ ] Digital evidence does not silently upgrade physical claims.
