# Internal agreements: spl, pts, bounding box

## Spline `spl` — what's inside

`build_spline(knots)` returns three `(zs, rs, ms)`:

| Field | Type | Meaning |
|---|---|---|
| `zs` | `list[float]` | z-node coordinates (mm, world) |
| `rs` | `list[float]` | r-node coordinates (mm) |
| `ms` | `list[float]` | tangents Monotone Cubic Hermite in each node |

The variable is called `spl` everywhere in the code. When debugging, you can unpack: `zs, rs, ms = spl`.

`profile_r(spl, z)` → profile radius in millimeters at height z.
Search for the desired segment - O(log n) via `bisect`.

---

## Profile `pts` — point order and closure

Profile - contour in plane XZ (r, z), all values in **mm**. Rules:

- The dots are coming **clockwise** viewed from axis +Y (standard Blender SCREW)
- Start: usually **outer bottom** `(r_outer, z_bottom)`
- Stroke: outer contour up → top end inward → inner contour down
- `build_revolved_solid` closes the last point with the first automatically through `bm.edges.new((vs[-1], vs[0]))`

**Closure rule:** DO NOT add a period, **coinciding with the first one in coordinates** — this creates a duplicate edge. After `bisect use_fill=True` the duplicate edge produces an artifact: a translucent partition on the cut plane.

**Normals:** when walking clockwise (look from +Y) Screw automatically creates normals directed **out**. Additional operation «recalculation of normals» is not needed - if the profile is correct, the normals are correct. Dark spots in tech form (frame A) after `revolve_profile` — sign of incorrect bypass `pts`; fix: reverse list of points (`pts[::-1]`, then adjust the starting point to the rule «outer bottom»).

Bottom end **add explicitly** only if it carries independent geometry (G-groove, step, chamfer). If the bottom end is just a horizontal edge from the last point to the first - Screw will create it itself, no need to add it.

**Two typical cases:**

```
# Simple tube - bottom end Screw creates itself:
(r_outer, 0)  →  (r_outer, h)  →  (r_inner, h)  →  (r_inner, 0)
                                              ↑ last dot ≠ first - everything is correct

# Body with an L-slot at the bottom - the bottom end is added explicitly:
(r_tube_outer, 0)  →  ... outer contour up...  →  ... inner contour down...
  →  (r_groove_out, mount_h)  →  (r_groove_out, z_bg_bot)  →  (r_tube_outer, z_bg_bot)
  →  (r_tube_outer, 0)   ← explicit last point: other coordinates by R, than the groove itself
```

---

## Non-manifold: signs of a bad profile and diagnosis

`revolve_profile` + boolean can give non-manifold geometry. Most problems arise **to** boolean — in the profile itself `pts`.

### Prohibited profile states

| Situation | Consequence | How to avoid |
|----------|-------------|--------------|
| `r < 0` | vertices go beyond the axis, mesh is turned inside out | always `r = max(r, 0)` |
| `r = 0` not on point | degenerate edge on the axis Z (all points converge into a line) | `r = 0` only at the last point of the nose |
| two adjacent `(r, z)` identical | rib collapse, loose vertex | are removed automatically in `revolve_profile`, but they say there is a logic error |
| dot `pts[-1]` matches `pts[0]` | duplicate edge → artifact after bisect | do not add the last point if the profile is already geometrically closed |
| profile self-intersects (inner contour extends beyond the outer one) | flipped faces inside the mesh | check `r_inner < r_outer` throughout the entire range Z |

### Self-diagnosis before sending code to Blender

Before `revolve_profile` — mentally (or in the comment) check:

```
1. All r >= 0?
2. r = 0 only on the tip (if it exists)?
3. There are no two identical points in a row?
4. Does the inner contour extend beyond the outer? (r_inner < r_outer everywhere)
5. The profile moves clockwise when viewed from +Y?
```

### After `revolve_profile` — technical view (frame A)

- **Dark spots on the surface** — inverted normals → bypass `pts` incorrect, reverse the order of points
- **Black hole at the end** — end is not closed: the lower or upper contour is not closed → check first/last profile point
- **Thin partition on a plane X=0** — duplicate edge (dot `pts[-1]` == `pts[0]`) → remove the last dot

### After boolean — auto cleanup

`apply_bool` automatically removes degenerate faces (`area < 1e-9`), loose edges and loose vertices. If after this you still see artifacts in the technical view, the problem is in the original profile, not in boolean.

---

## `r_inner_floor` — inner radius limitation

When constructing the internal contour of a body of revolution with **variable profile** always limit:

```python
r_inner = max(profile_r(spl, z) - wall, r_inner_floor)
```

Without this when narrowing the outer profile `r_inner` will go beyond the axis, the profile will intersect itself and the body of rotation will be inverted. `r_inner_floor` is taken from `model_config.base_radius`.

---

## Geometric integrity: no voids at joints

When a composite part is built from several `revolve_profile` + UNION, **joints between them must be without gaps and overlap artifacts**.

Rules:

1. **Ring The/flange is connected to the main body without clearance.** The outer radius of the ring is taken exactly along the profile of the body at the same height (`profile_r(spl, z_ring_top)`), and not an arbitrary number.

2. **The ring extends to the axis of its inner radius** — all material from `ring_inner_r` is filled to the outer body wall. None «air pockets» between the ring and the main body.

3. **UNION welds bodies correctly** only if they intersect (overlap each other by at least 1 polygon). If the bodies only touch their faces (zero-thickness contact) — boolean can give an artifact. Always give a slight overlap (0.1–0.5 mm Z or R).

4. **Check after UNION** (visual): in mode cut there should be no dark gaps or translucent edges at the junction of the ring and the body. If there is, then the geometry does not converge.

Example for connecting ring body.py:
```python
ring_pts = [
    (ring_inner_r,               z_ring_bottom),   # inner bottom
    (ring_inner_r,               z_ring_top),       # inner top
    (profile_r(spl, z_ring_top), z_ring_top),       # outer top = body profile (no gap)
    (profile_r(spl, z_ring_top), z_ring_bottom),    # outer bottom = body profile (no gap)
]
```

---

## Composite Part Pattern: Functions and Order of Operations

### Code structure

Each logical subpart of a composite part is built in **of a separate private function** `_build_*`. Function `build_*` — orchestrator only: calls `_build_*` and merges the result.

```python
def build_part(spl, col):
    """Orchestrator. Calls only _build_* and _cut_*. Returns all public objects."""
    shell = _build_shell(spl, col)        # 1. main shell → MESH_Model_Part
    _cut_joint(shell, spl, col)           # 2. DIFFERENCE: boring/groove
    ring  = _build_conn_ring(spl, col)    # 3. separate object → MESH_Model_Part_ConnRing
    _cut_holes(ring, spl, col)            # 4. DIFFERENCE: sockets/holes in the ring
    set_parent(ring, shell)               # 5. parenting — after all boolean
    return shell, ring                    # both objects are in Outliner, one material

def _build_shell(spl, col):
    """Main shell → revolve_profile → MESH_Model_Part."""
    ...
    return revolve_profile("MESH_Model_Part", pts, col, seg)

def _build_conn_ring(spl, col):
    """Separate ring object → MESH_Model_Part_ConnRing. Without UNION with shell."""
    ...
    return revolve_profile("MESH_Model_Part_ConnRing", pts, col, seg)

def _cut_joint(shell, spl, col):
    """Cuts a boring / groove from the shell."""
    tool = revolve_profile("_part_joint_tool", pts, col, seg)
    blender_bool_apply(shell, tool, 'DIFFERENCE', solver='FLOAT')

def _cut_holes(ring, spl, col):
    """Cuts out nests / holes from the ring (not from shell)."""
    ...
    blender_bool_apply(ring, tool, 'DIFFERENCE', solver='FLOAT')
```

Function naming rules:
- `_build_*` — builds geometry, returns self `MESH_*`-object
- `_cut_*` — cuts through DIFFERENCE, modifies the passed object, returns nothing

Note: `_attach_*` (UNION to the main object) is used when the subpart **not** is needed as a separate object in Outliner. If the subpart is logically independent - `_build_*` + separate object (like `ConnRing`).

### Resulting objects in Blender

Each **logically independent subpart** gets its own `MESH_*`-object and remains visible in Outliner. Intermediate boolean-tools (borings, sockets) are named with `_` and are deleted automatically after application.

| Type | Name | Seen in Outliner |
|-----|-----|-----------------|
| Main shell | `MESH_Model_Part` | yes |
| Composite subpart (ring, flange) | `MESH_Model_Part_ConnRing` | yes |
| Boolean-tool (boring, socket) | `_part_joint_tool`, `_part_hole_0` | no (is removed) |

The subpart is built in `_build_*`-function is added to the same collection, **not** merges through UNION with the main body - remains a separate object. Parenting (object hierarchy) — skill `blender-modeling/scene-conventions`. When finalized, both objects receive the same material and are processed as one part.

This allows you to:
- select the ring separately in Outliner and check its dimensions via `get_object_info`
- assign different material if debugging is needed
- easy to remove/recreate only the ring without touching the shell

### Order of operations is critical

First things first UNION, then that's it DIFFERENCE. If you do DIFFERENCE before UNION — subsequent UNION will close the cut cavity:

```python
# Correct
bool_apply(body, ring,   'UNION')       # build up first
bool_apply(body, pocket, 'DIFFERENCE')  # then cut

# Incorrect
bool_apply(body, pocket, 'DIFFERENCE')  # cut out the pocket...
bool_apply(body, ring,   'UNION')       # ...UNION closed it back
```

Separate `revolve_profile` for flange/rings are the only way to avoid self-intersection when `ring_inner_r < r_inner_top` (the ring goes deeper than the inner surface of the main body).

---

## Bounding box from `get_object_info`

MCP-tool `get_object_info` returns `world_bounding_box` in **meters**:

```json
"world_bounding_box": [
  [x_min, y_min, z_min],
  [x_max, y_max, z_max]
]
```

Conversion to mm and dimensions:

```python
bb = obj["world_bounding_box"]
height_mm   = (bb[1][2] - bb[0][2]) * 1000
diameter_mm = (bb[1][0] - bb[0][0]) * 1000
# For bodies of revolution diameter_mm = 2 * r_outer
```

Objects with offset `location`: bounding box is already in world coordinates, the offset is taken into account.

### Mandatory print dimensions after construction (antihallucination)

**Rule:** immediately after `revolve_profile` and after each `blender_bool_apply` — add `print` with real values from `obj.bound_box`. This is done directly in execute-code, before the screenshot, and before any sizing statements in the response body.

```python
def _print_bb(obj, mode_cut=False):
    bb = obj.bound_box  # local coordinates, but location is already applied if z_offset=0
    xs = [v[0] for v in bb]; zs = [v[2] for v in bb]
    h_mm  = (max(zs) - min(zs)) * 1000
    if mode_cut:
        d_mm = max(xs) * 2 * 1000   # x_min ≈ 0 in cut-mode
    else:
        d_mm = (max(xs) - min(xs)) * 1000
    print(f"[BB] {obj.name}: h={h_mm:.2f}mm  ⌀={d_mm:.2f}mm  "
          f"z=[{min(zs)*1000:.2f}, {max(zs)*1000:.2f}]mm")
```

Call immediately after object creation:
```python
obj = revolve_profile("MESH_Model_Part", pts, col, seg)
_print_bb(obj)

blender_bool_apply(obj, tool, 'DIFFERENCE', solver='FLOAT')
_print_bb(obj)  # make sure that the object is not degenerate after boolean
```

**Why this is important:** `get_object_info` is called separately MCP-request after construction - by that time the AI could already formulate a statement about the sizes based on expectations, not fact. Print in execute-code outputs the same response as the build, and makes the real values ​​explicit before any output.

---

## Test files and testing structure

### Architecture (three layers)

```
test/check.py                    ← ENTRY POINT - always run before Blender
├── cross-detail checks     ← joints, stacks Z, fit compatibility, PCD connections
└── autodiscovery parts/*.test.py → calls test_config() every detail

parts/{name}.test.py             ← local invariants of one part
├── test_config()                ← level 1: config only, without Blender
└── test_mesh(obj)               ← level 2: real mesh, only inside Blender

test/geom_test.py                ← mesh utilities for level 2
└── re-exports lib/geom_test + new features (assert_wall_solid etc.)
```

**Launch:**
```bash
python models/{model}/test/check.py          # all at once - before each Blender
python models/{model}/parts/{name}.test.py   # only one part
```

**Autodiscovery:** `test/check.py` finds everything `parts/*.test.py` via `glob` — new parts are picked up automatically, without editing `check.py`.

### Level 1 - config (`test_config()`, without Blender)

What to check in `parts/{name}.test.py`:
- All sizes > 0 (height, radii, thickness)
- Wall thicknesses ≥ minimum printable (usually 1.5–2 mm)
- Grooves and fits do not extend beyond the part
- Thread clearances: `depth > clearance`
- Dependent parameters from the configs of adjacent parts are the same

What it checks `test/check.py` additional (cross-detail):
- Joint radii between sections coincide
- Height stack is not negative
- PCD magnets/pins match for both mating parts
- Dimensions of inserted elements (insert, pipe) do not extend beyond the receiving part

### Level 2 - mesh (`test_mesh()`, inside Blender)

Called after `build_*()` in incremental mode (Step 4A).
The files are called `{name}.test.py` — direct `import` does not work, only through `importlib`:
```python
import importlib.util, os
_f = os.path.join(_root, 'models', _model, 'parts', '{name}.test.py')
_spec = importlib.util.spec_from_file_location('{name}_test', _f)
_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
obj, subpart = build_{name}(spl, col)
_mod.test_mesh(obj, subpart)
```

Functions from `lib/geom_test` (basic, always available):
- `assert_not_empty(obj)` — vertices are
- `assert_manifold(obj)` — mesh is sealed
- `assert_volume_gt(obj, min_mm3)` — volume is not zero
- `assert_height(obj, expected_mm)` — height matches
- `assert_z_position(obj, z_min, z_max)` — part in the correct position
- `print_bb(obj)` — anti-hallucination of dimensions (always call)

Functions from `{model}/test/geom_test` (extended):
- `assert_normals_outward(obj)` — normals are not inverted after boolean
- `assert_rotational_symmetry(obj)` — diameters X/Y match (body of rotation)
- `assert_wall_solid(obj, r_inner, r_outer, z_samples)` — wall is full (ray cast)
- `assert_objects_no_overlap(obj_a, obj_b)` — parts do not collide (integration)
- `assert_pin_alignment(pin_objs, ring_obj)` — pins fit into sockets according to XY

```python
# Importing advanced functions internally Blender:
from {model}.test.geom_test import (
    assert_normals_outward, assert_rotational_symmetry, assert_wall_solid,
)
```

### Rule when creating a new part

When adding `parts/{name}.py` — must be created `parts/{name}.test.py`.
Minimum: `test_config()` with basic assert-ami + `test_mesh()` with `assert_manifold` and `assert_volume_gt`.

### Rule when design changes

For any change in the geometry, config or logic of the part - **check and update if necessary** corresponding `parts/{name}.test.py`:

- Expected dimensions have changed → update `assert_height`, `assert_z_position`, `assert_diameter`
- New intentionally open ends have appeared (plantings, nests) → loosen `assert_manifold` with an explanation why
- Added a new config parameter → add assert in `test_config()`
- Parameter removed or renamed → remove or update old assert
- The logic of joining with an adjacent part has changed → update dependent parameter checking

**Open ends are not always a bug.** Intentionally open ends (landing joint, sockets for magnets) needs to be documented explicitly in the test:
```python
# Body: the bottom end is open intentionally - it sits there bottom (dad enters mom)
# ConnRing: the ends of the sockets are open - magnets are inserted from below during assembly
```
And check that non-manifold edges only in valid places, and not over the entire surface.

---

## `bpy.data` vs `bpy.ops` — what to use in scripts

**Rule:** prefer `bpy.data` and `bmesh`. `bpy.ops` — only when there is no alternative.

| Approach | When to use |
|--------|--------------------|
| `bpy.data.*` + `bmesh` | creating meshes, objects, materials is always preferable |
| `bpy.ops.*` | operators without data-API analog (for example `modifier_apply`, `convert`, `transform_apply`) |

**Why avoid `bpy.ops`:**
- Depends on `bpy.context` (active object, correct mode) — in scripts the context is unpredictable
- Significantly slower data-API
- Starting from Blender 4.0 operators require `context.temp_override()` or will fall from `RuntimeError`

**When `bpy.ops` inevitable** — transmit override explicitly:
```python
with bpy.context.temp_override(active_object=obj, selected_objects=[obj]):
    bpy.ops.object.modifier_apply(modifier="Bevel")
```

---

## Units of measurement

| In code (Python/config) | B Blender (bpy) |
|---|---|
| mm (`float`) | meters (`mm(x) = x * 0.001`) |
| `profile_r` returns mm | `bm.verts.new((mm(r), 0, mm(z)))` |
| `get_object_info` → meters | × 1000 → mm |

Function `mm()` lives in `common.py` and is imported into all `parts/`.
