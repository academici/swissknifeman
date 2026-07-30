---
name: model-rules
bucket: blender-modeling
version: 0.1.0
description: "Use this template before any task on a model: read models/{name}/ai/rules.md, the model-specific rules file."
risk: write
persona: oss-dev
tags: [blender, template, rules, 3d, cad, conventions]
requires: []
produces_for: [build-loop]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Template: `models/{name}/ai/rules.md`

- Every model MUST have `models/{name}/ai/rules.md`. Read by agent before any task; augments `blender-modeling/config-conventions` and `blender-modeling/scene-conventions` with model-specific data.
- Copy template below into `models/{name}/ai/rules.md`; fill every section.

---

```markdown
# {ModelName} — model rules

## Shape and symmetry

<Geometry type: solid of revolution / box / arbitrary. Symmetry axis.>
<Symmetry exceptions: which parts are asymmetric and why.>

## Cut / cross-section (if applicable)

<How model renders in cut mode: cut plane, what's visible inside.>
<Typical cut-mode artifacts for this model (if any).>
<Diameter-in-cut verification rule.>

## Part stack (bottom-up / by layout)

| Position | Part | File |
|---------|--------|------|
| <z or description> | <Name> | `parts/{name}.py` |
| ... | | |

## Connections between parts

- **<Part A> → <Part B>**: <connection type, clearance, fastening method>
- ...

## Cross-config dependencies

| Part | Reads config |
|--------|---------------|
| `{part}.py` | `{XxxConfig}.{field}` |
| ... | |

## Thread parameters

| Part pair | pitch | depth | turns | clearance |
|---|---|---|---|---|
| <male → female> | mm | mm | count | mm |

## Parameters — config.py only

<Reminder: don't hardcode numbers in `parts/`. Any new parameter → into `config.py`.>

## Separate objects in scene (if any)

<Which parts shown offset from main assembly (for separate printing).>
<How to account for offset in bounding-box analysis.>

## Camera: ready zone values

```python
from {name}.common import set_viewport_camera

set_viewport_camera()                         # whole model
set_viewport_camera(z_mm=<z>,  distance=<d>)  # <zone 1>
set_viewport_camera(z_mm=<z>,  distance=<d>)  # <zone 2>
# ...
```
```

---

## When to update

- New part → update stack and connections tables.
- Thread change → update thread parameters table.
- Layout / camera zone change → update ready values.
- New cross-config dependency found → update dependencies table.

## Related skills

- `blender-modeling/build-loop` — reads this file before any task; general model build loop.
- `blender-modeling/parametric-config` — implements cross-config deps and camera zones from this template in `config.py`/`profile.py`/`common.py`.
- `blender-modeling/threading` — source of values for "Thread parameters" table.
- `blender-modeling/config-conventions` — rules for cross-config deps recorded in this file.

<!-- ru-source-sha256: 3e171c3d050da25fbe5e44bebef2ea93a4630b2e96af1b303303e4ba2760f82d -->
