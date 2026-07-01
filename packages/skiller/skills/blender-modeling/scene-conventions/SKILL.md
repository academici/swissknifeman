---
name: scene-conventions
bucket: blender-modeling
version: 0.1.0
description: "Parametric-model scene conventions: object prefixes (MESH_/CRV_/LGT_/MTL_), parenting hierarchy by physical belonging, collections, material assignment from config color field. Activate when creating scene objects/materials, setting parenting of subparts, questions about object names and grey material."
risk: write
persona: oss-dev
tags: [blender, cad, parametric, naming, scene, materials, parenting, bpy]
requires: []
produces_for: [build-loop]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Object naming & scene

## Object prefixes

| Prefix | Type |
|--------|------|
| `MESH_` | Meshes |
| `CRV_` | Curves |
| `LGT_` | Lights |
| `MTL_` | Materials |

- Collection: constant `COLLECTION_NAME` in `config.py` (e.g. `"Model"`).

## Parenting hierarchy

Composite part → **Variant A**: main shell = parent, subparts = children.

```
MESH_Model_Body                    ← parent
└── MESH_Model_Body_ConnRing       ← child

MESH_Model_Nose                    ← parent
└── MESH_Model_Nose_ConnRing       ← child
    ├── MESH_Model_Nose_Pin_1      ← child of ring (not nose!)
    ├── MESH_Model_Nose_Pin_3
    └── MESH_Model_Nose_Pin_5
```

- Object parents to the one it cannot exist without physically. Pins belong to the connector ring → children of ring, not nose.

Set via `set_parent(child, parent)` from `{model}.common`:

```python
from {model}.common import set_parent
set_parent(ring, body)
set_parent(pin, ring)   # not set_parent(pin, nose)!
```

- Call `set_parent` **after all boolean ops** on the child object.
- Each subpart that becomes a child built in a **separate `_build_*` function** — not inline in orchestrator.
- Orchestrator `build_*` only calls `_build_*` / `_cut_*` and sets parenting before `return`.

## Materials from config

Each part gets material from `color: Color` field of its `*Config`. Create/assign via `common.py` (`apply_material` must be implemented in model's `common.py`):

```python
from {model}.common import apply_material

# In build_*() after revolve_profile:
obj = revolve_profile("MESH_Model_Part", pts, col, seg)
apply_material(obj, "MTL_Model_Part", cfg.color)
```

If `apply_material` not yet implemented — add to `common.py`:
```python
def apply_material(obj, name: str, color):
    import bpy
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = False
    mat.diffuse_color = color
    mat.surface_render_method = 'DITHERED'   # Blender 5.0
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
```

- Material name: `MTL_` + object name without `MESH_` prefix (e.g. `MTL_Model_Body`).
- Color: `(R, G, B, A)` 0..1, stored in `*Config.color`.
- One material per object; subparts (`ConnRing`, `Pin`) get same material as parent.
- Object with no material renders grey in `MATERIAL` mode — always assign explicitly.
- Blender 5.0: `mat.surface_render_method = 'DITHERED'` (not `blend_method`) → skill `blender/version-gotchas`.

## Python code

- Package: `models/{name}/`, entry `{name}.py`, function `main()`.
- Part: one file in `parts/`, export `build_*`.
- Intra-package imports relative: `from .config import ...`.

## Related skills

- `blender-modeling/config-conventions` — variable/config naming, which `color` field feeds the material.
- `blender-modeling/parametric-config` — mesh build (`revolve_profile`), output these names/materials apply to.
- `blender/version-gotchas` — `surface_render_method` instead of `blend_method` in Blender 5.0.

<!-- ru-source-sha256: b6952f75b2d573ead06bbd2b5e23173fe8f556355dbd46f059d2a50cff4e6b06 -->
