---
name: parametric-config
bucket: blender-modeling
version: 0.1.0
description: "Use when editing parametric configs, derivations, profiles or builders. Covers pure versus bpy layers, mm conversion, profile construction and world-space invariants."
risk: write
persona: oss-dev
tags: [blender, bpy, parametric, dataclass, cad, fdm, sla, geometry, units, python, 3d]
requires: [model-rules]
produces_for: [build-loop]
outputs: []
snippets: [config.py, check.py, profile.py, config-and-profile.md, internals.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Parametric configuration and geometry layers

Read the model contract and existing APIs before adding a layer. Physical config
and dependency conventions belong to `config-conventions`.

| Layer | Responsibility | Blender dependency |
|---|---|---|
| `config.py` / supported `*_config.py` | Physical/design inputs and public facade | None |
| `derived.py` / pure profile modules | Shared formulas, datums and compatibility | None |
| `lib/units.py` | Convert documented mm to Blender metres via `mm(v)` | None |
| `lib/geometry.py` | Data-driven reusable primitives | Lazy bpy/bmesh |
| `parts/*.py` | Build the model's physical parts from those inputs | Blender |
| `test/check.py` | Pure model/config preflight | None |
| `parts/*.test.py` | `test_config()` and applicable `test_mesh(obj)` | Mixed |

Keep imports of bpy/bmesh lazy where modules must load in plain Python. Derive
functions accept the active config; do not bind variant-dependent results once
at module import. `profile.py` is appropriate for a revolved/profile-based shape,
not mandatory for every model or every purchased reference.

## Geometry and units

Convert dimensional values at the Blender boundary through the project's units
helper. Name and document mm, angle units, count and per-side clearance.
For revolve geometry, use ordered profile knots and a closed, nondegenerate XZ
boundary, then the existing revolve helper or SCREW operation. Do not duplicate
a closing profile vertex. Extrusions use the corresponding section/extrude helper.

Keep physical datums and formulas shared between builder and validation. Use
config-owned tolerances and material/printer limits; generic examples such as
0.5 mm matching tolerance or a typical wall range do not set model acceptance.
Printed-thread constraints apply only when the model actually uses printed threads.

## Validation

Run the project's pure preflight before rebuilding. Check positive dimensions,
valid profile ranges, intended mating relationships and nonzero/minimum walls.
`test_mesh(obj)` measures the built/evaluated geometry, not only config metadata.
For rotated or parented objects use world-space coordinates (`matrix_world @ co`)
and radial distance `hypot(x,y)` where the property is rotational; local `x_max`
or an unchecked sibling is not equivalent evidence.

Useful templates are loaded for their actual use:

- [config](snippets/config.py), [check](snippets/check.py), [profile](snippets/profile.py).
- [config-and-profile](snippets/config-and-profile.md),
  [internals](snippets/internals.md): units, profile traversal and test mechanics.

Use `build-loop` for the changed-zone build/check sequence; full acceptance/export
uses `model-verification`. Load `threading` or `version-gotchas` only for a relevant
thread/API question rather than for every config edit.
