# Viewport display modes

Skill reference `mcp-blender`.


Named presets. Apply at the user’s command or independently select the optimal one for the task.

### `tech` — technical view (default for checking geometry)

**When:** checking the shape, dimensions, joints, grooves, threads. Maximum readability of ribs and cavities.

```python
import bpy
bpy.ops.object.select_all(action='DESELECT')
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'SOLID'
                sh.light = 'FLAT'
                sh.show_backface_culling = True
                sh.background_type = 'VIEWPORT'
                sh.background_color = (0.28, 0.28, 0.28)
                sh.color_type = 'SINGLE'
                sh.single_color = (0.92, 0.92, 0.92)
                sh.show_cavity = True
                sh.cavity_type = 'BOTH'
                sh.curvature_ridge_factor = 0.25
                sh.curvature_valley_factor = 2.0
                sh.show_xray = False
                ov.show_wireframes = True
                ov.wireframe_opacity = 1.0
                ov.show_floor = False
                ov.show_axis_x = ov.show_axis_y = ov.show_axis_z = False
                ov.show_overlays = True
        break
```

### `material` — color identification of parts

**When:** checking part ownership, color differentiation after assembly, close-ups of joints.

```python
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'MATERIAL'
                sh.use_scene_lights = False
                sh.use_scene_world = False
                sh.show_backface_culling = True
                sh.show_xray = False
                if hasattr(sh, 'studiolight_intensity'):
                    sh.studiolight_intensity = 1.15
                sh.show_cavity = True
                sh.cavity_type = 'BOTH'
                sh.curvature_ridge_factor = 0.35
                sh.curvature_valley_factor = 1.4
                ov.show_wireframes = True
                ov.wireframe_opacity = 0.42
                ov.show_floor = False
                ov.show_axis_x = ov.show_axis_y = ov.show_axis_z = False
                ov.show_overlays = True
        break
```

### `realism` — maximum realism (presentation)

**When:** final screenshot for evaluation of appearance, demonstration to the user. Before use, recalculate the normals (see `blender/version-gotchas`).

```python
import bpy, bmesh

# Recalculation of normals (if they were inverted after boolean)
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data); bm.free(); obj.data.update()

for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'MATERIAL'
                sh.use_scene_lights = False
                sh.use_scene_world = False
                sh.show_backface_culling = True
                sh.show_xray = False
                if hasattr(sh, 'studiolight_intensity'):
                    sh.studiolight_intensity = 1.2
                ov.show_wireframes = False
                ov.show_overlays = False
        break
```

### `xray` — view internal geometry

**When:** debugging cavities, checking fills, viewing hidden parts (pipe inside the housing, magnet sockets).

```python
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'SOLID'
                sh.show_xray = True
                sh.xray_alpha = 0.25          # transparency: 0.1 (almost invisible) … 0.5 (translucent)
                sh.color_type = 'MATERIAL'
                sh.show_backface_culling = False
                sh.background_type = 'VIEWPORT'
                sh.background_color = (0.22, 0.22, 0.22)
                ov.show_wireframes = True
                ov.wireframe_opacity = 0.3
                ov.show_floor = False
                ov.show_axis_x = ov.show_axis_y = ov.show_axis_z = False
                ov.show_overlays = True
        break
```

| Mode | User command | Best for |
|-------|---------------------|------------|
| `tech` | «turn on tech» | geometry, dimensions, joints, threads |
| `material` | «turn on material» | detail colors, close-ups |
| `realism` | «turn on realism» | presentation, final view |
| `xray` | «turn on xray» | cavities, filling, hidden parts |

**Automatic mode selection by agent:**
- Constructing and checking geometry → `tech`
- Color differentiation of parts → `material`
- Final demo / presentation to the user → `realism`
- Debugging cavities, normals, internal parts → `xray`

---
