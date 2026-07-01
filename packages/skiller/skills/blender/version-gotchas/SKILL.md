---
name: version-gotchas
bucket: blender
version: 0.1.0
description: "Known breaking changes and pitfalls of the Blender 5.0 API"
risk: write
persona: oss-dev
tags: [blender, api, bpy, 3d, python, gotchas, advisory, version]
requires: []
produces_for: [mcp-blender, parametric-config]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Blender version gotchas

Target: **Blender 5.0**.

## Changed/removed API

| Old | Use in 5.0 |
|---|---|
| `bpy.ops.*({"active_object": obj})` (dict context) | `with bpy.context.temp_override(active_object=obj): bpy.ops.*()` |
| `solver='FAST'` (Boolean) | `solver='FLOAT'` (FAST removed) |
| `mat.blend_method = 'OPAQUE'` | `mat.surface_render_method = 'DITHERED'` (opaque) / `'BLENDED'` (alpha) |
| `mat.shadow_method` | removed, does not exist |
| `me.calc_normals()` | removed; recalc via `bmesh.ops.recalc_face_normals(bm, faces=bm.faces)` |
| `import bgl` | removed; use `import gpu` |
| EEVEE render props on scene | moved to `view_layer` |

## Critical pitfalls

### Normals after boolean
- `blender_bool_apply` (DIFFERENCE/UNION) may invert outer-surface normals. Symptom: walls look "transparent" in viewport (inner cavity visible through them).
- Fix — recalc normals after boolean:
```python
import bmesh
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
```
- Already built into `realism` mode (`mcp-blender`). On suspected inverted normals — enable `realism` and check.

### `bpy.ops` without override (5.0)
- Since Blender 4.0 passing context via dict-arg is removed. Without `temp_override` the operator fails: `RuntimeError: Calling operator "bpy.ops.object.modifier_apply" ... context is incorrect`.

### `surface_render_method` not set via `blend_method`
- In 5.0 `mat.blend_method` exists but assignment is ignored. Set `mat.surface_render_method`:
  - `'DITHERED'` — opaque (old `OPAQUE`)
  - `'BLENDED'` — alpha blending

### Material with no nodes = default gray
- Object with no assigned material renders system gray. In viewport mode `MATERIAL` looks "transparent" (backface culling differs on faces without material). Always assign a material explicitly.

## Performance
- `bpy.data` + `bmesh` is 25–300x faster than `bpy.ops` for building meshes.
- `foreach_set()` for bulk vertex-coord writes (via NumPy): array must be `.flatten()`/`.ravel()` before passing.

## Related skills
- `blender/mcp-blender` — error-diagnosis table references these pitfalls (`temp_override`, normals after boolean, `surface_render_method`); `realism` mode already includes normal recalc.
- `blender-modeling/parametric-config` — mesh build via `bmesh`/SCREW where these 5.0-API rules apply.
- `blender-modeling/threading` — SCREW thread modifier, sensitive to API changes.

<!-- ru-source-sha256: 21f87e4580de4e17251bd8a179f4239b6ba0f8f42b6c848ab0f952f057e5cfa4 -->
