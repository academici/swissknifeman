---
name: build-loop
bucket: blender-modeling
version: 0.1.0
description: "Use for an incremental parametric part build or geometry fix: config preflight, scoped rebuild, evaluated geometry and affected interfaces, then framed visual evidence."
risk: write
persona: oss-dev
tags: [blender, cad, parametric, workflow, bpy, mcp, 3d, fdm, sla]
requires: [parametric-config, config-conventions, scene-conventions, model-rules]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Scoped parametric build loop

The current task and local model contract define the parts, properties and
acceptance scope. A routine geometry/config edit does not activate a full release
audit. Use `model-verification` for final acceptance/export of a declared assembly.

## Prepare and rebuild

1. Read the affected configs, builder, shared datums and model rules. Use their
   sources for mating dimensions and design gaps (`config-conventions`).
2. Edit the authorized construction. Keep its purpose, actual dependencies and
   non-obvious geometric operations documented; a long repeated docstring template
   is not a prerequisite for a small correction.
3. Run the project's plain-Python preflight before Blender. Geometry and pure
   derivation stay in their existing layers (`parametric-config`).
4. Rebuild the changed output and required mating context through the supported
   entrypoint. Incremental replacement is appropriate only when the builder
   preserves neighbors and parenting; a `setup_scene()` that clears the entire
   model is not an incremental part builder.

Use the project launcher/loader for headless builds. In a persistent MCP process,
reload changed model/shared modules and use the actual paths (`mcp-blender`). One
operator controls a shared live scene; parallel source work does not authorize
concurrent scene rebuilds.

## Fix execution errors before measurement

Read the traceback and relevant source, fix, retry. Do not continue geometry
checks on a failed build, and do not end the authorized task just because its
first execution failed.

| Symptom | Technical checks |
|---|---|
| Import/module error | Actual module name, loaded path, entrypoint and persistent cache |
| Missing config field | Current config/derive API and every affected caller |
| Invalid profile/invariant | Named constraint, knot order, closed boundary, dimensional source |
| Operator context error | Appropriate context and `temp_override` for the installed API |
| Empty/degenerate mesh | Builder output and intermediate profile/Boolean geometry |
| Dark patch or invalid boundary | Real face winding/intersection; do not globally flip closed cavity normals |

A symptom is not proof of one cause. Preserve legitimate small faces; do not
remove nonzero geometry or remesh an exact interface merely to obtain PASS.

## Measure, then view

- Apply relevant `test_mesh()`/evaluated mesh checks to changed physical outputs.
  Check real affected interfaces with config-owned limits; bbox proximity does not
  prove fit. A changed shared generator can affect several differently shaped
  instances, which need their applicable checks.
- Before images, inspect non-empty geometry, world bbox and transforms for the
  changed zone. For MCP use `get_object_info`; for headless checks use the declared
  evaluated geometry API. Reuse recorded metadata rather than duplicate calls.
- Frame the actual zone with the documented camera helper, including off-axis
  coordinates where its model wrapper supports them. Use technical/material/xray
  views according to the property, inspect the images, and restore exact state.

Record changed inputs, what was measured and any unresolved or physical property.
Update local rules only when a real model constraint changed; general mechanics
remain in shared skills. No full matrix or exhaustive reference-wire collision
certificate is added unless the task/local acceptance actually requires it.
