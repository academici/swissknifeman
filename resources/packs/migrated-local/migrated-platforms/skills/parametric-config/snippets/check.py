# Source: anonymized production project
"""
Validation of part parameter invariants WITHOUT running Blender.

Launch:
    python models/part/check.py        # normal Python, without bpy

Each check prints [ OK ] or [ FAIL ]. When adding a new parameter
in config.py — add the appropriate invariant here. Non-zero exit when FAIL.
"""

import os
import sys

# Project root in the path so that the import works without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.part.config import (  # noqa: E402
    model_config as m,
    shell_config as sh,
    joint_config as jt,
    thread_config as th,
    joint_outer_radius,
)

_failures: list[str] = []

# Minimum printable wall thickness under FDM/SLA, mm.
MIN_WALL = 0.8
# Tolerance for joining radii of adjacent segments, mm (float not comparable exactly).
TOL = 0.5


def ok(msg: str) -> None:
    print(f"  [ OK ] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    _failures.append(msg)


def check(condition: bool, msg_ok: str, msg_fail: str) -> None:
    ok(msg_ok) if condition else fail(msg_fail)


# ── Heights and units ─────────────────────────────────────────────────────────
print("\n── Heights ───────────────────────────────────────────────────────────────")

check(
    sh.height > 0,
    f"Segment height is positive: {sh.height:.1f} mm",
    f"Segment height ≤ 0: {sh.height:.1f} mm",
)
check(
    sh.height < m.height,
    f"Segment below the model: {sh.height:.1f} < {m.height:.1f} mm",
    f"Segment not lower than model: {sh.height:.1f} ≥ {m.height:.1f} mm",
)
check(
    abs(sh.profile_knots[-1][0] - sh.height) < TOL,
    f"Last profile node z ≈ height ({sh.height:.1f} mm)",
    f"Last node z={sh.profile_knots[-1][0]} ≠ height={sh.height}",
)

# ── Joining radii (float — according to tolerance, not exactly) ─────────────────────────
print("\n── Joining radii ────────────────────────────────────────────────────")

r_knot_bottom = sh.profile_knots[0][1]
r_knot_top = sh.profile_knots[-1][1]
check(
    abs(r_knot_bottom - sh.radius_bottom) <= TOL,
    f"Bottom node r={r_knot_bottom} matches radius_bottom={sh.radius_bottom} (±{TOL})",
    f"Bottom node r={r_knot_bottom} ≠ radius_bottom={sh.radius_bottom} (tolerance {TOL} mm)",
)
check(
    abs(r_knot_top - sh.radius_top) <= TOL,
    f"Top node r={r_knot_top} matches radius_top={sh.radius_top} (±{TOL})",
    f"Top node r={r_knot_top} ≠ radius_top={sh.radius_top} (tolerance {TOL} mm)",
)

# ── Wall thickness (print FDM/SLA) ──────────────────────────────────────────
print("\n── Wall thickness ───────────────────────────────────────────────────────")

check(
    m.wall >= MIN_WALL,
    f"Wall wall={m.wall} ≥ MIN_WALL={MIN_WALL} mm: printable",
    f"Wall wall={m.wall} < MIN_WALL={MIN_WALL} mm: too thin to print",
)
check(
    jt.wall >= MIN_WALL,
    f"Landing wall joint.wall={jt.wall} ≥ {MIN_WALL} mm",
    f"Landing wall joint.wall={jt.wall} < {MIN_WALL} mm: too thin",
)

# ── Landing (joint) ──────────────────────────────────────────────────────────
print("\n── Landing ──────────────────────────────────────────────────────────────")

r_seat = jt.seat_inner_diameter * 0.5
r_joint_outer = joint_outer_radius(jt)
check(
    r_joint_outer > r_seat,
    f"Dad r_outer={r_joint_outer:.2f} > r_seat={r_seat:.2f}: there is a landing wall",
    f"Dad r_outer={r_joint_outer:.2f} ≤ r_seat={r_seat:.2f}: zero wall",
)
check(
    jt.clearance > 0,
    f"clearance={jt.clearance} mm > 0: landing is assembled with a gap",
    f"clearance={jt.clearance} mm ≤ 0: dad won't enter mom",
)
check(
    jt.depth <= sh.height,
    f"Planting depth depth={jt.depth} ≤ segment height {sh.height} mm",
    f"depth={jt.depth} > height={sh.height}: fit extends beyond the part",
)

# ── Thread (gap vs profile; parameters - skill blender-modeling/threading) ───────────
print("\n── Thread ───────────────────────────────────────────────────────────────")

check(
    th.depth > th.clearance,
    f"thread depth={th.depth} > clearance={th.clearance}: tooth protrudes above gap",
    f"thread depth={th.depth} ≤ clearance={th.clearance}: tooth completely in gap",
)
check(
    th.pitch > 0 and th.turns >= 1,
    f"The thread is correct: pitch={th.pitch} mm, turns={th.turns}",
    f"Incorrect thread: pitch={th.pitch}, turns={th.turns}",
)

# ── Summary ─────────────────────────────────────────────────────────────────────
print("\n── Summary ─────────────────────────────────────────────────────────────────")
if _failures:
    print(f"\n  {len(_failures)} errors:\n")
    for f_ in _failures:
        print(f"    • {f_}")
    sys.exit(1)
print("\n  All checks passed.\n")
