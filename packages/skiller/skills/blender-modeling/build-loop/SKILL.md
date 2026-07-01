---
name: build-loop
bucket: blender-modeling
version: 0.1.0
description: "Parametric-modeling build loop via MCP Blender: analyze task → check flexibility/cross-config recompute → incremental part build → verify geometry via get_object_info BEFORE screenshot → camera on changed zone → screenshot in right mode → propose rule fixes. Includes part docstring template and error-diagnosis table. Activate on any part build/edit task in Blender. Tool/preset mechanics from skill blender/mcp-blender."
risk: write
persona: oss-dev
tags: [blender, cad, parametric, workflow, bpy, mcp, 3d, fdm, sla]
requires: [mcp-blender, parametric-config, config-conventions, scene-conventions, model-rules, threading]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Parametric model build loop

Procedure for any "build/edit part" task. Tool/viewport-preset/camera mechanics live in `blender/mcp-blender` — do not duplicate here.

## Step 1. Analyze task

Before any code:
- Which parts are affected? (`parts/*.py`, `config.py`)
- Role of each affected part (purpose, material, fits).
- Target geometry (shape, sizes, joints with neighbors).
- Inter-part dependencies (mating radii, slots, threads).
- Which **foreign configs** to read in this part (fit → mating part's config; cup → inserted part's config).

**Flexibility check before code (mandatory):** for each number you'd write in `parts/*.py` ask "what if user changes an adjacent config param?":
- Size depends on another part → **take from its config**, don't duplicate.
- Structural offset/thickness/clearance → **add config field**, don't hardcode.
- Computed value (e.g. joint z-position) → **formula from configs**, not a number.

Goal: changing any single `config.py` param must not break other parts' geometry. Full cross-config/recompute methodology — `blender-modeling/config-conventions`.

**Mental recompute check (mandatory before code):** for each param the task depends on, run: "if this value changes → what shifts in neighbors → do they adjust correctly?" If chain breaks → there's a hardcode; find and replace with formula before sending to Blender.

**For composite parts and new profiles — describe the algorithm in words before code.** For each subpart (`_build_*`, `_attach_*`, `_cut_*`) record:
1. **Shape**: what it is geometrically (tube, disk, cylinder, slotted ring...).
2. **Profile `pts`**: key points in traversal order and meaning of each.
3. **Joints**: where/how the subpart meets neighbors (at which radius, at which height).
4. **Operation**: `revolve_profile` → standalone object, or UNION/DIFFERENCE against what.

## Step 2. Edit code

- Numbers only in `config.py`, never hardcode in `parts/` (see `blender-modeling/config-conventions`).
- New part → separate file in `parts/`, relative imports (`from .config import ...`).
- On construction/param change → update docstring and adjacent comments.

**File docstring standard (mandatory):** each `parts/{name}.py` starts with a module docstring:

```python
"""
<Part name> (<comma-separated Blender object names>).

Purpose:
  What it physically is, why it exists, its role in the assembly.

Construction (bottom-up / inside-out):
  1. <subpart>: <shape, material, geometric principle>
  2. <subpart>: ...

Links to other parts:
  - <part A>: <link type — joint, fit, thread, L-slot, contains inside...>
    Config: <where params come from — XxxConfig.field>

Contains / holds:
  - <external element>: <what it is, how inserted, config — XxxConfig>

Technical notes:
  - <print specifics, material, clearances, boolean-op order, what must not change>

Section (if model viewed in cross-section):
  <what's visible in section, any artifacts, what to watch>

Screenshot:
  <which neighboring objects occlude the part and must be hidden for inspection>
  <recommended display mode: tech / material / xray>
"""
```

**Update rules:** on any part change update affected docstring sections; if a new link A↔B is found — add a "Links" entry in **both** parts.

## Step 3. Check invariants without Blender

Before sending to Blender, validate params in plain Python (no bpy): heights > 0, adjacent-segment radii match, nonzero wall thickness, clearance greater than thread profile depth. `check.py` architecture and two-level tests — `blender-modeling/parametric-config`.

## Step 4. Send model to Blender (incremental)

If task touches one part — rebuild **only it**, not the whole model (faster, leaves neighbors). Full build — when verifying joints of several parts. Send pattern, module-cache reset (`del sys.modules`), and `execute_blender_code` — `blender/mcp-blender`.

**On `execute_blender_code` error — stop.** Do not proceed to geometry check. Read traceback, find error line, fix, retry.

**Diagnosis by error type:**

| Error | Cause | Action |
|--------|---------|----------|
| `ImportError: No module named '...'` | Modules not reset or wrong path | Check `del sys.modules` block; check `sys.path` |
| `ModuleNotFoundError` after editing file | Stale `.pyc` in cache | Add `del sys.modules` for the package |
| `AttributeError: '...Config' has no attribute '...'` | Field renamed or removed | Open `config.py`, find current name |
| Geometric invariant violated | Formula error in config | Read validation message, fix formula |
| `z[0] != 0` or `z[-1] != height` in profile | Last profile node not brought to segment height | Bring last `profile_knots` node to `height` |
| Object created but `vertices_count = 0` | Profile `pts` degenerate (all r=0 or self-intersection) | `print(pts)` before `revolve_profile`, check r |
| Dark spots / flipped normals | Wrong `pts` traversal | Reverse list: `pts[::-1]` and fix start point |
| `RuntimeError: Calling operator ... context is incorrect` | `bpy.ops.*` without `temp_override` in Blender 5.0 | Wrap in `temp_override` (see `blender/version-gotchas`) |
| Semi-transparent partition on section plane | `pts[-1] == pts[0]` — duplicate edge | Drop last profile point |

## Step 5. Verify geometry via `get_object_info` (before screenshot)

**Before screenshot** call `get_object_info` for each changed part:
1. **Sizes**: `world_bounding_box` → height and diameter in mm.
2. **Defect signs**: `vertices_count == 0` or degenerate bounding box → part didn't build, return to Step 2.
3. **Compute part z-center** for camera: `z_mm = (z_min + z_max) / 2 * 1000`.

Tool semantics and bounding-box formulas — `blender/mcp-blender`.

## Step 6. Camera on changed zone (mandatory before screenshot)

**Never screenshot without first setting the camera.** Aim camera at the changed part/zone using `z_mm` from Step 5. Camera-via-helper principle and `distance` formula — `blender/mcp-blender`. Ready zone values for a specific model — in `models/{name}/ai/rules.md` (see `blender-modeling/model-rules`).

## Step 7. Screenshot in suitable mode

Pick **one mode** by task (geometry → `tech`; part colors → `material`; presentation → `realism`; cavities/hidden → `xray`). Preset code and rule for hiding occluding objects — `blender/mcp-blender`.

## Step 8. Propose rule fixes (if needed)

If mismatches, gaps, or inaccuracies found in model rules/skills — formulate a proposal, apply the fix, **tell the user** (what changed, where, rationale). Don't stay silent about noticed mismatches.

## Related skills

- `blender/mcp-blender` — MCP tools, viewport modes, camera, send/reload pattern (all mechanics).
- `blender/version-gotchas` — Blender 5.0 API traps from Step 4 diagnosis table.
- `blender-modeling/parametric-config` — `config.py`/`profile.py`/`check.py` layer the loop rests on.
- `blender-modeling/config-conventions` — cross-config and recompute (Step 1).
- `blender-modeling/scene-conventions` — object names and materials of created parts.
- `blender-modeling/model-rules` — `models/{name}/ai/rules.md`: part stack, camera zones, thread params.
- `blender-modeling/threading` — thread printing and radial clearances (Steps 2–7).

<!-- ru-source-sha256: a347ddcbac6cc2f53fd0b80c42663c7406bb6a18f2e2f27d1b9885f45f766daa -->
