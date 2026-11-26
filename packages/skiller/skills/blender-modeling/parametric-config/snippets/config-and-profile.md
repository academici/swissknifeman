# Configs and silhouette

## Naming configs

- Dataclass: `*Config` (`LensMountConfig`, `BottomShellConfig`, …).
- Instances in `config.py` at the bottom of the file: `snake_case` + suffix `_config`, for example `bottom_shell_config`, `model_config`.
- Profile point type: `ProfileKnot = Tuple[float, float]` — in meaning `(z_local, r_external)` in **mm**.

## `profile_knots`: local Z

U **each** parts nodes are specified in **local** z:

- first node: **`z = 0`** (bottom of the part in its system);
- last node: **`z = segment height`**.

The height of some sections may not be stored as a separate field, but rather calculated as the difference in heights from the configs of adjacent parts. After changing any of these values **update latest z** in the corresponding `profile_knots` (otherwise validation will fail `derive_all`).

Fields **`radius_bottom` / `radius_top`** — end tip; shape source for spline - **nodes**. Keep signatures consistent with the first/last `r` in `profile_knots`.

## Worldwide translation Z

- `model_part_z(part)` — lower limit of the part in world mm.
- `profile_knots_world(local_knots, part)` → `[(z + z0, r), …]`.
- `world_profile_knots(part)` — convenient in `main()` before `build_spline`.

Splines for `profile_r` in `parts/*` is still in **world** z (how each part is built).

## `derive_all` — what it does and how to expand

`derive_all(model, ...)` is called at the end `config.py` **after** declarations of all config instances. Accepts all configs as arguments (doesn't read globals).

**What it does:**
- Calculates fields that depend on several configs simultaneously (for example `model.base_radius` — from lens fit and wall thickness).
- Launches `_validate_local_profiles`: checks that `z[0]==0`, `z[-1]==height` in each segment, nodes are not empty.
- Recalculates derivatives Z-positions (for example `nameplate.z_bottom`).

**How to expand when adding a new model:**
```python
# profile.py new model
def derive_all(model, part_a, part_b, external_element, ...):
    # 1. calculate derived fields
    model.base_radius = external_element.outer_diameter * 0.5 + part_a.inner_wall
    # 2. recalculate Z-positions
    part_b.z_bottom = part_a.height + part_b.z_local_offset
    # 3. validate profiles
    _validate_local_profiles(part_a, part_b, ...)
```

Rule: `derive_all` — is the only place where one config sets the field of another. Outside `derive_all` configs only read each other, but do not write.

## Relevance of comments in the code

When you change the design, you need to update not only the formulas, but also the text next to them:

- comments for fields in `config.py`;
- docstring file and `build_*()` / auxiliary functions in `parts/*.py`;
- inline-comments for key profile blocks, grooves, fits, threads, chamber.

The rule is simple: if after editing the comment describes **old** form, old parameter meaning or old sequence of points, it needs to be corrected in the same task.

## Import: module order

Loop **`config` ↔ `profile`**: for manual tests first `import {model}.config`, do not import `{model}.profile` until fully loaded `config`. Entry point `{model}.py` pulls `common` → `config` — order is safe.

## Spline `spl` and profile `pts` — details

Detailed description of the internal structure `spl`, bypass rules `pts`, diagnostics non-manifold → snippet `internals.md` of this skill.

## Global spline vs in parts

One general spline is convenient when you need strict consistency of the entire curve with one expression. Individual splines by part + local z is more convenient when **segment heights change** and the silhouette rule in parts: world z is popped from the stack rather than rewritten across all nodes.
