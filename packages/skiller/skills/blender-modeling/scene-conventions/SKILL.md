---
name: scene-conventions
bucket: blender-modeling
version: 0.1.0
description: "Use when naming or parenting model objects, assigning materials, or defining scene ownership. Keeps owned cleanup and printable/reference inventory explicit."
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

# Model scene ownership and appearance

## Names and inventory

Use `MESH_`, `CRV_`, `LGT_`, `MTL_` and stable physical IDs. The collection name
comes from the model contract. Preserve documented legacy names until all users
of the inventory change together.

`setup_scene()` removes only outputs the active model owns, including its stale
temporary tools. Prefix similarity alone does not establish ownership. Other
models, scenes and shared datablocks remain intact. After a standard rebuild,
compare the exact owned universe with its inventory SSOT. Undeclared owned meshes
or leaked tools invalidate that universe; intentionally preserved foreign objects
outside it do not require deletion.

Printed inventory uses explicit `printable`/print-group metadata. Parenting or
visibility cannot turn a bought reference into a printed object. A print group
must form the model's required solid rather than merely overlap two shells.

## Parenting

Parent by physical owner, according to the model's assembly contract. Pins may
belong to their connector ring; a fixed body may own its fitted reference. A
continuous wire spanning detachable modules is not automatically a rigid child
of the moving cap or drawer.

Use the existing `set_parent`/inventory registration API after Boolean operations,
preserving world transforms. Separate helpers are useful for distinct reusable
operations, not mandatory for every trivial child. Do not add an EMPTY if the
physical owner already provides the needed hierarchy. Child visibility requires
the project's assembly-visibility mechanism where ordinary parenting is insufficient.

## Materials

Use the existing shared material helper and the role/config's documented color.
Do not copy a new `apply_material` implementation into each model. Typical API:

```python
from lib.materials import apply_material  # or the model's supported re-export
apply_material(obj, 'MTL_' + obj.name.removeprefix('MESH_'), cfg.color)
```

Use the actual project's API; the example does not authorize a new dependency.
Material slots, parent colors and bought-reference appearance follow the model's
roles, not a universal one-material/same-color rule. Assign appearance explicitly
for material views. For a Blender material API mismatch, consult `version-gotchas`
for the installed version instead of substituting a deprecated property.

Keep model imports relative and builders in the package's established structure.
Scene naming does not require restructuring unrelated files or adding new parts.
