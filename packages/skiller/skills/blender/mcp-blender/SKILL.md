---
name: mcp-blender
bucket: blender
version: 0.1.0
description: "Use when working through Blender MCP: execution, object inspection, viewport setup and screenshots. Includes module reload, world-space units and exact visibility restoration."
risk: write
persona: oss-dev
tags: [blender, mcp, python, 3d, bpy, viewport, camera, screenshot, orchestration]
requires: []
produces_for: [build-loop]
outputs: []
snippets: ["role.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Blender MCP tools

Use this card when the task actually uses MCP. Headless builds use the project's
entrypoint and launcher. The current task and model contract determine which
objects and properties need inspection; this card does not add a full audit.

## Execution and module provenance

Read the project's environment loader and entrypoint. Insert its resolved root
before alternate checkouts and reset changed model/shared packages in a persistent
Blender process before importing them:

```python
import sys
_root = '<root resolved by the project loader>'
_pkg = '<actual model package>'
for name in tuple(sys.modules):
    if name == _pkg or name.startswith(_pkg + '.') or name in ('lib', 'config') or name.startswith(('lib.', 'config.')):
        del sys.modules[name]
if _root not in sys.path:
    sys.path.insert(0, _root)
```

Use `importlib.import_module` for package names containing hyphens. Read changed
dependencies when another agent owns related files; record loaded paths for a
verification run. Do not infer paths from an assumption that `os.environ` is empty.
A fresh background process already has a fresh module cache.

`execute_blender_code` runs the script. If execution fails, read the traceback,
fix and retry before geometry checks; this does not end the authorized task.
One operator owns a shared live Blender scene. Other agents may prepare source
changes or isolated headless runs, but must not rebuild that scene concurrently.

## Object and scene inspection

- `get_object_info`: inspect the changed object/context before a screenshot:
  non-empty mesh, world bbox, transform and material. Use the returned field names;
  tool versions may report mesh counts under `mesh` rather than `vertices_count`.
- `get_scene_info`: check the owned universe after a rebuild, or investigate an
  unexpected object/tool. Check leftover Boolean tools when the operation batch
  closes or fails; a separate whole-scene call after every Difference is unnecessary.
- `get_viewport_screenshot`: capture only after framing the relevant zone.

Do not assume MCP bbox coordinates are millimetres. Confirm the tool/project unit
contract. For a project storing mm and building Blender metres, multiply returned
world coordinates by 1000 once. Prefer the project's evaluated world-bbox helper.
Fallback for that same unit contract:

```python
import bpy
from mathutils import Vector
obj_eval = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
world_mm = [tuple(1000*c for c in obj_eval.matrix_world @ Vector(corner))
            for corner in obj_eval.bound_box]
lo = tuple(min(p[k] for p in world_mm) for k in range(3))
hi = tuple(max(p[k] for p in world_mm) for k in range(3))
```

Raw `obj.bound_box` is local space. Object information is a framing/provenance
check, not proof of manifold topology, wall thickness or a real mating clearance.
Batch already-required metadata where supported; do not duplicate it with one
round-trip for every unchanged or repeated bought reference.

## Camera, display and reversible isolation

Read the actual `common.set_viewport_camera` signature. A Z-centre helper alone
cannot centre an off-axis target; use the model's documented XYZ wrapper if it has
one. Choose distance from the world extent, inspect the result, and use the
project's helper instead of scattered viewport quaternion assignments.

Viewport modes and settings: [viewport-display-modes](references/viewport-display-modes.md).
Hide only the obstructing context needed for the view and restore its exact state,
including objects that were hidden before capture:

```python
import bpy
objects = [bpy.data.objects[name] for name in target_names if name in bpy.data.objects]
saved = [(obj, obj.hide_get(), obj.hide_viewport, obj.hide_render) for obj in objects]
try:
    for obj in objects:
        obj.hide_set(True)
    # Set the documented camera, then capture/inspect the screenshot.
finally:
    for obj, hidden, viewport, render in saved:
        obj.hide_viewport, obj.hide_render = viewport, render
        obj.hide_set(hidden)
```

Prefer the project's capture transaction when it also restores selection, camera,
shading and collection state. Purchased asset generators are not parametric CAD
builders. See `build-loop` for scoped rebuilds, `model-verification` for acceptance
or export, and `version-gotchas` only for an applicable Blender API issue.
