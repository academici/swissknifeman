# Source: anonymized production project
"""
Constructing a profile from nodes and a body of rotation (revolve) axis Z.

B config.py each segment stores profile_knots — LOCAL z from 0 to segment height.
derive_all() recalculates dependent dimensions and synchronizes the last node with height.

revolve_profile() requires Blender — bpy/bmesh are imported LAZY (inside a function),
so that this module is imported normally Python (check.py, level 1 tests, CI).
"""

from __future__ import annotations

from typing import List, Tuple

# Unit conversion: model in mm, Blender — in meters.
def mm(v: float) -> float:
    """Millimeters → meters (units Blender)."""
    return v * 0.001


ProfileKnot = Tuple[float, float]  # (z, r) — both in mm


# ── Recalculation of dependent dimensions (without bpy) ────────────────────────────────────


def derive_all(model, shell, joint) -> None:
    """Counts derived dimensions from a design once after instantiation.

    1. base_radius — external r on z=0 from the landing and the wall.
    2. Last node profile_knots is synchronized with the current height
       (z of the last node must match the height of the segment).
    """
    model.base_radius = joint.seat_inner_diameter * 0.5 + joint.wall + model.wall

    if shell.height >= model.height:
        raise ValueError(f"shell.height={shell.height} >= model.height={model.height}")

    if shell.profile_knots:
        last_r = shell.profile_knots[-1][1]
        shell.profile_knots[-1] = (shell.height, last_r)

    _validate_local_profile(shell)


def _validate_local_profile(shell) -> None:
    """First node z must be 0, the last one equal to the height of the segment."""
    tol = 1e-3
    knots = shell.profile_knots
    if not knots:
        raise ValueError("profile_knots empty")
    if abs(knots[0][0]) > tol:
        raise ValueError(f"first node z should be 0 for now {knots[0][0]}")
    if abs(knots[-1][0] - shell.height) > tol:
        raise ValueError(
            f"last node z should be {shell.height} (segment height), now {knots[-1][0]}"
        )


def interpolate_profile(knots: List[ProfileKnot], n_points: int) -> List[ProfileKnot]:
    """Linear silhouette interpolation in n_points uniform points along z (mm).

    Nodes in config.py — support; intermediate points are counted here and not hardcoded.
    For a smooth silhouette, you can insert a spline here (Catmull-Rom) — interface is the same.
    """
    z0, z1 = knots[0][0], knots[-1][0]
    out: List[ProfileKnot] = []
    for i in range(n_points + 1):
        z = z0 + (z1 - z0) * i / n_points
        out.append((z, _r_at_z(knots, z)))
    return out


def _r_at_z(knots: List[ProfileKnot], z: float) -> float:
    """Radius (mm) on top z linear interpolation between reference nodes."""
    if z <= knots[0][0]:
        return knots[0][1]
    if z >= knots[-1][0]:
        return knots[-1][1]
    for (z_a, r_a), (z_b, r_b) in zip(knots, knots[1:]):
        if z_a <= z <= z_b:
            t = (z - z_a) / (z_b - z_a) if z_b > z_a else 0.0
            return r_a + (r_b - r_a) * t
    return knots[-1][1]


# ── Body of revolution (requires Blender; bpy/bmesh — lazy import) ───────────────


def revolve_profile(name: str, knots_zr: List[ProfileKnot], col, segments: int):
    """Body of revolution from 2D-profile (list (z, r) in mm) around axis Z.

    1. Removes adjacent duplicate nodes.
    2. Builds a closed bmesh-profile in plane XZ (each point through mm()).
    3. Hangs SCREW-modifier by Z and applies.

    Returns the finished bpy.Object.
    """
    import bpy
    import bmesh

    # 1. Remove adjacent duplicates.
    clean: List[ProfileKnot] = [knots_zr[0]]
    for z, r in knots_zr[1:]:
        if abs(z - clean[-1][0]) > 1e-6 or abs(r - clean[-1][1]) > 1e-6:
            clean.append((z, r))

    # 2. Closed profile in XZ (x = r, z = z), all in meters across mm().
    bm = bmesh.new()
    verts = [bm.verts.new((mm(r), 0.0, mm(z))) for z, r in clean]
    for i in range(len(verts) - 1):
        bm.edges.new((verts[i], verts[i + 1]))
    bm.edges.new((verts[-1], verts[0]))  # close the circuit

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)

    # 3. SCREW axis Z — full revolution per segments steps.
    scr = obj.modifiers.new("Screw", "SCREW")
    scr.axis = "Z"
    scr.steps = scr.render_steps = segments
    scr.use_merge_vertices = True
    scr.merge_threshold = mm(0.05)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="Screw")
    return obj
