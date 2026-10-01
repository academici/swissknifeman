# Source: anonymized production project
"""
Part parameters (generic Part) — by entities, without a single global PARAMS.

All linear dimensions are in MILLIMETERS (mm), unless otherwise noted.
Instances *Config are created at the BOTTOM of the file - they are edited by the user.
Dependent dimensions counts derive_all() from profile.py (call at the end of the file).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# Silhouette node: z — local from 0 to the height of THIS segment (mm); r — outer radius (mm).
ProfileKnot = Tuple[float, float]

# Material color Blender: (R, G, B, A), each value 0..1
Color = Tuple[float, float, float, float]


# ── Model as a whole (general silhouette and resolution) ───────────────────────────────


@dataclass
class ModelConfig:
    height: float = 120.0           # full height of the part, mm
    wall: float = 2.4               # nominal wall thickness, mm
    profile_points: int = 200       # number of profile interpolation points (smoothness)
    segments: int = 128             # number of segments of a body of rotation (edges around the circle)

    base_radius: float = field(default=0.0, init=False)  # external r on z=0; believes derive_all()


# ── Shell segment (body of revolution by profile nodes) ────────────────────────


@dataclass
class ShellConfig:
    """One outer shell segment: silhouette defined by nodes profile_knots."""

    color: Color = (0.85, 0.85, 0.85, 1.0)
    height: float = 60.0            # segment height by Z, mm
    radius_bottom: float = 30.0     # external r at the bottom end, mm (junction with the previous segment)
    radius_top: float = 24.0        # external r at the upper end, mm (junction with the following)
    # Silhouette: local z ∈ [0, height]. WARNING: last z always == height.
    # derive_all() synchronizes the last node with the current one height.
    profile_knots: List[ProfileKnot] = field(
        default_factory=lambda: [
            (0.0,  30.0),           # bottom end
            (20.0, 30.0),           # flat area
            (45.0, 28.0),           # beginning of narrowing
            (60.0, 24.0),           # top end
        ]
    )


# ── Landing/socket (joint) — connection of two parts ─────────────────────────


@dataclass
class JointConfig:
    """Cylindrical fit «mom and dad»."""

    seat_inner_diameter: float = 24.0  # internal diameter of the socket, mm
    depth: float = 10.0                # planting depth (cylinder height), mm
    wall: float = 2.0                  # wall thickness of the landing cylinder, mm
    clearance: float = 0.15            # side gap between male and female, mm


# ── Thread (parameters - see skill blender-modeling/threading) ─────────────────────────


@dataclass
class ThreadConfig:
    """Printable thread (FDM/SLA). A gap is required - the exact thread will not screw in."""

    pitch: float = 1.0                 # thread pitch, mm
    depth: float = 0.4                 # tooth profile depth according to R, mm
    turns: int = 3                     # number of turns, pcs
    clearance: float = 0.15            # radial clearance between threads per side, mm


# ── Derived functions (clean, without bpy — are reused in check.py) ───────


def joint_outer_radius(joint: "JointConfig") -> float:
    """Outer radius of landing cylinder (dad), mm: r_seat + wall."""
    return joint.seat_inner_diameter * 0.5 + joint.wall


# ── Instances (edit here) ─────────────────────────────────────────


model_config = ModelConfig()
shell_config = ShellConfig()
joint_config = JointConfig()
thread_config = ThreadConfig()

from .profile import derive_all  # noqa: E402 — after instances, avoid import loop

derive_all(model_config, shell_config, joint_config)

COLLECTION_NAME = "Part"
