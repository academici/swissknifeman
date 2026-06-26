---
name: mcp-blender
bucket: blender
version: 0.1.0
description: "MCP Blender: tools (execute_blender_code, get_object_info, get_viewport_screenshot, get_scene_info), viewport display modes (tech/material/realism/xray), camera-via-helper principle, code-send & module-cache reset (del sys.modules), hiding obstructing objects for screenshot, parallel multi-agent work. Activate when working with Blender via MCP — building, viewport setup, screenshots."
risk: write
persona: oss-dev
tags: [blender, mcp, python, 3d, bpy, viewport, camera, screenshot, orchestration]
requires: [version-gotchas]
produces_for: [build-loop]
outputs: []
snippets: ["role.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# MCP Blender — tools, viewport, camera

Universal layer for Blender via MCP (any bpy project). Parametric-model build-loop discipline → skill `blender-modeling/build-loop`.

## MCP tools

| Tool | Purpose | When |
|---|---|---|
| `execute_blender_code` | Run Python in Blender | main tool for building & setup |
| `get_viewport_screenshot` | Viewport screenshot | only after camera set |
| `get_object_info` | Bounding box, vertices, materials | check every changed part before screenshot |
| `get_scene_info` | List all scene objects | see below |

`get_scene_info` — call:
- After scene recreation — confirm old `MESH_*` objects removed and collection recreated clean.
- After boolean DIFFERENCE — confirm temp tool (names start with `_`) gone from scene (if present → `apply_bool` failed).
- On unexpected behavior — see what exists in scene before debugging.

Polyhaven / Sketchfab / Hyper3D — not for parametric models.

## Code send & module-cache reset

Blender caches Python modules between script runs. Reset cache before importing your modules, else file edits won't apply:

```python
import sys, os
_root = '<absolute path to project root>'   # substitute before sending
_pkg  = '<model package name>'
for _k in list(sys.modules):
    if _k == _pkg or _k.startswith(_pkg + '.') or _k in ('lib', 'config') or _k.startswith(('lib.', 'config.')):
        del sys.modules[_k]
if _root not in sys.path: sys.path.insert(0, _root)
```

- Paths substituted manually: Blender doesn't inherit shell env vars — `os.environ` is usually empty in Blender scripts. Agent substitutes absolute paths into code before sending.
- On error in `execute_blender_code` — STOP. Read traceback, fix, resend (typical parametric-part build errors → diagnostics table in `blender-modeling/build-loop`).

## Camera: universal principle

```python
from {model}.common import set_viewport_camera

# z_mm  — center of changed zone in mm (from bounding box)
# distance — zone_height_mm × 0.001 × 1.5, min 0.05
set_viewport_camera(z_mm=<z_centre>, distance=<distance>)
set_viewport_camera()  # whole model (default distance from model_config)
```

- `z_mm=None` → model center (from `model_config`).
- `distance` — smaller = closer view.
- Angle: `ORTHO`, view on cut `X=0`, tilt ~15° (`Euler(75°, 0°, -90°)`).
- FORBIDDEN: setting `view_rotation` manually via Quaternion/Euler — model flips. Only `set_viewport_camera()`.

Ready `z_mm` / `distance` values per model → `models/{name}/ai/rules.md` (see `blender-modeling/model-rules`).

## Size check

`world_bounding_box` from `get_object_info` → dimensions in mm. Print height/diameter right after build (before screenshot):

```python
def _bb(obj):
    xs = [v[0] for v in obj.bound_box]; zs = [v[2] for v in obj.bound_box]
    print(f"[BB] {obj.name}: h={(max(zs)-min(zs))*1000:.1f}mm  "
          f"z=[{min(zs)*1000:.1f},{max(zs)*1000:.1f}]mm  x_max={max(xs)*1000:.1f}mm")
```

If `vertices_count == 0` or bounding box degenerate (all coords equal) — part didn't build.

## Viewport display modes

Full table of viewport display modes (shading/overlay, wireframe/solid/material/rendered) and screenshot usage → [references/viewport-display-modes.md](references/viewport-display-modes.md).

## Hiding obstructing objects for screenshot

If target zone is occluded by neighbors — hide them for screenshot, then restore:

```python
import bpy

hidden = ["MESH_Model_Part", "MESH_Model_Part_SubPart"]   # substitute names for current model
for name in hidden:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_viewport = True

# ... get_viewport_screenshot() ...

for name in hidden:        # ALWAYS restore after screenshot
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_viewport = False
```

When to hide — ask user, or hide yourself if obvious (top part covers ring, body covers inner tube).

## Parallel multi-agent work

Multiple agents (e.g. Cursor + Claude Code) may run the full flow via MCP simultaneously. To avoid overwriting each other:

Before editing code:
- Re-read affected `parts/*.py` and `config.py` — another agent may have changed the file.
- If file changed since last read — apply edits on top of current version.

Before sending to Blender:
- Re-read all files that will be imported in the Blender script.
- `del sys.modules` mandatory — Blender caches modules between script runs.

One-object rule:
- Two agents must not edit the same `parts/{name}.py` simultaneously.
- If tasks target one part — run sequentially, not in parallel.

## Related skills

- `blender/version-gotchas` — Blender 5.0 API traps: `temp_override`, normals after boolean, `surface_render_method`; `realism` mode already includes normal recompute.
- `blender-modeling/build-loop` — parametric-model build-loop discipline over these tools.
- `blender-modeling/parametric-config` — architecture of `config.py`/`profile.py`/`parts/*`/`check.py`.
- `blender-modeling/model-rules` — `models/{name}/ai/rules.md`: ready camera zones and model specifics.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 2e7a187e44c4277d80e3eddc3a64ad95a07706cf5e9c3040b09758db706b963e -->
