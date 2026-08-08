---
name: parametric-config
bucket: blender-modeling
version: 0.1.0
description: "Data-config-driven parametric 3D modeling in Blender (bpy): dataclass part params (dims/tolerances/material/units mm), profile + revolve/extrude, invariant validation without launching Blender. Activate when editing models/*/config.py, profile.py, parts/*, check.py; adding a part param; questions about tolerances/units/radius matching for FDM/SLA printing."
risk: write
persona: oss-dev
tags: [blender, bpy, parametric, dataclass, cad, fdm, sla, geometry, units, python, 3d]
requires: [threading, model-rules, version-gotchas]
produces_for: [build-loop]
outputs: []
snippets: [config.py, check.py, profile.py, config-and-profile.md, internals.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: parametric part modeling on a data-config

Part = data, not procedure. All dims/tolerances/material/units in `config.py` as dataclass params; geometry code only reads them and builds mesh.

## When to activate

- Editing `models/<part>/config.py`, `profile.py`, `parts/*.py`, `check.py`.
- Adding a new part param (diameter, wall thickness, clearance, thread pitch).
- Questions: units (mm <-> Blender meters), tolerances, segment-radius matching, min wall thickness for FDM/SLA.
- Revolve or extrude from a 2D profile/spline.

## Core principle

Numbers live ONLY in `config.py`. No magic constants in `parts/*.py` or `profile.py`; every new dimension becomes a dataclass param.

## Related skills

- `blender-modeling/model-rules` — model-specific `ai/rules.md` rules (part stack, joints, camera zones).
- `blender-modeling/threading` — clearances + thread profile for FDM/SLA; `*_thread_*` params here come from there.

## Layer architecture

Boundary: everything computed WITHOUT bpy is separated from everything requiring Blender.

| File / layer | Purpose | bpy? |
|:---|:---|:---|
| `config.py` | dataclass part params: dims, tolerances, material, color; instances at bottom of file | no |
| `lib/units.py` | unit conversion: model stores mm, Blender works in meters (`mm(v) = v*0.001`) | no |
| `profile.py` | build 2D profile/spline from knots + `derive_all()` (recompute dependent dims) | no (revolve separate) |
| `lib/geometry.py` | geom helpers: `revolve_profile`, `make_cylinder`, `revolve_ring`, boolean/join | **yes** (lazy bpy import) |
| `parts/<part>.py` | assemble concrete part: read config -> build mesh via helpers | **yes** |
| `check.py` | validate param invariants; prints `[ OK ]`/`[ FAIL ]`, exit code | **no** (fast run) |
| `parts/<part>.test.py` | two-level tests: `test_config()` without bpy + `test_mesh()` inside Blender | mixed |

**Lazy `import bpy` rule:** in `lib/geometry.py` and `parts/*.py`, import `bpy`/`bmesh` INSIDE functions, not at module top level. Module then imports under plain Python (for `check.py`, level-1 tests, CI); Blender pulled only on real mesh build.

## Algorithm

1. **Units — single source.** All linear dims in config = millimeters. At Blender boundary (meters) pass each value through `units.mm()`. Never multiply by `0.001` by hand in geometry — only via the helper. Document unit in each field comment (`# мм`, `# градусы`, `# шт`).
2. **Param — in dataclass.** Each dim/tolerance/material = `@dataclass` config field with default + unit comment. Group related params into own dataclass (`PartConfig`, `JointConfig`, `MaterialConfig`). Instances created AT BOTTOM OF FILE — user edits those.
3. **Profile — knots, not coords in code.** Revolve silhouette = list of knots `(z, r)` (local z from 0 to segment height). Type alias `ProfileKnot = Tuple[float, float]` makes intent explicit. Intermediate points interpolated (linear or spline) in `profile.py`, not hand-written.
4. **Dependent dims — in `derive_all()`.** Dims derived from others (segment height = `model.height − bottom − top`; last-knot-to-height match; joint PCD) computed once in `derive_all(...)`, called right after config instances created. Do not duplicate a formula in several places — compute in `derive_all`, read the result.
5. **Build geometry from profile.** Revolve: assemble closed `bmesh` profile in XZ plane, apply `SCREW` modifier on Z axis (`steps = segments`, `use_merge_vertices`), apply. Extrude: build 2D section, apply `SOLIDIFY`/`Screw` with zero angle or `bmesh.ops.extrude_*`. Feed each bmesh point through `mm(...)`.
6. **Validate invariants without Blender.** All geometric correctness conditions in `check.py`, run via plain Python (`python models/<part>/check.py`), no bpy, no render. Check: positive heights; adjacent-segment radius matching (`|r_a − r_b| ≤ tol`); nonzero wall thickness (`r_outer > r_inner`); clearance greater than thread profile depth (`thread_depth > thread_clearance`); geometry in valid range (angles 0..360 etc).
7. **Two-level part tests.** `parts/<part>.test.py` has `test_config()` (math only, imported from `check.py`) and `test_mesh(obj)` (manifold, volume, bounding box — inside Blender). Level 1 runs in CI without Blender; level 2 on real rebuild. Mesh assertions compare world-space geometry: use `obj.matrix_world @ vertex.co` when rotation/parenting matters. For rotationally replicated parts, assert radial distance `hypot(x, y)`, never a fixed-world-axis bound such as `x_max`.
8. **Printing (FDM/SLA) — budget tolerances.** Fit + thread clearances = separate params (`*_clearance`), not "tight". Min printable wall thickness = invariant in `check.py` (typically `≥ 0.8–1.5 мм`). Thread params + clearances come from `blender-modeling/threading`.

## Param conventions

- **Unit in name/comment.** Field without explicit unit in comment = review error. Linear = mm, angle = degrees (convert to radians on use), counter = `# шт`.
- **Clearances — per side.** Radial/axial clearance is per single side; diametral formula applies ×2. Document in field comment (`# зазор на сторону, мм`).
- **Match tolerance — named constant.** In `check.py` `tol = 0.5` (mm) for comparing adjacent-segment radii; never compare float radii for exact equality.
- **Color/material — also a param.** `Color = Tuple[float, float, float, float]` (RGBA 0..1) in part config, not hardcoded in material code.
- **Derived functions — next to config.** Pure functions like `joint_outer_radius(joint)` live in `config.py` (no bpy), reused in both `check.py` and `parts/*.py`.

## Which snippet when

| Situation | File |
|:---|:---|
| Add/extend dataclass part params, units, derived functions | `snippets/config.py` |
| Write invariant validation without Blender (`[OK]`/`[FAIL]`, exit code) | `snippets/check.py` |
| Build profile from knots and revolve on Z (via SCREW), `derive_all` | `snippets/profile.py` |

## Quality checklist

- [ ] All linear dims in mm; at Blender boundary — only via `units.mm()`
- [ ] Each config field has unit comment (мм / градусы / шт)
- [ ] Numbers only in `config.py`; no magic constants in `parts/*.py`, `profile.py`
- [ ] Dependent dims computed once in `derive_all()`, not duplicated
- [ ] `import bpy`/`bmesh` lazy (inside functions) — module imports without Blender
- [ ] `check.py` runs under plain Python, no bpy, nonzero exit on FAIL
- [ ] Invariants checked: heights > 0, radius matching (by `tol`), wall > 0, clearance > 0
- [ ] Fit/thread clearances = separate `*_clearance` params, not "tight"
- [ ] Min wall thickness for FDM/SLA = invariant in `check.py`
- [ ] Profile given by knots `(z, r)`, intermediate points interpolated, not hardcoded
- [ ] Part test two-level: `test_config()` (no bpy) + `test_mesh()` (in Blender)
- [ ] Mesh tests keep the `config.py`/`profile_r()` unit contract and use world-space coordinates for rotated or parented objects

## Links

- snippets/config.py — dataclass part params, units, derived functions
- snippets/check.py — invariant validation without Blender
- snippets/profile.py — profile from knots + revolve via SCREW + `derive_all`
- snippets/config-and-profile.md — config naming, `profile_knots`, local/world Z, `derive_all`
- snippets/internals.md — `spl` structure, `pts` point order, non-manifold, units, test files
- Related skills: `blender-modeling/model-rules`, `blender-modeling/threading`, `blender-modeling/build-loop` (shared build+check loop), `blender/mcp-blender` (MCP/viewport tools), `blender/version-gotchas` (5.0-API rules for `bmesh`/SCREW)
- https://docs.blender.org/api/current/bpy.html
- https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/screw.html
- https://help.prusa3d.com/article/tolerances_n_of_fdm_3d_printing

<!-- ru-source-sha256: 1be4b02c6b471b1d6cdb0e4d1c421161e203cd5b495b7ef519a1312d7364162f -->
