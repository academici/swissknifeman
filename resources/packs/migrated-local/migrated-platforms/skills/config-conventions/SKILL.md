---
name: config-conventions
description: "Use for physical config fields, units and dependencies between parametric parts. Keeps purchased dimensions, design clearances and derived datums explicit."
---

# Physical configuration and dependencies

One physical entity type or interface has its own `PascalCaseConfig`; repeated
instances may reuse that type. Name instances consistently, such as `lens_config`.
Use the model's existing `config.py` facade and supported `*_config.py` modules;
this convention does not require a new printed part or a new builder per reference.

## Inputs and derived values

- Linear inputs: mm; angles: documented units, normally degrees; RGBA: 0..1.
- Physical purchased dimensions have a source or an explicit unknown/sample gate.
  Keep an engineering reservation distinct from a claimed manufacturer dimension.
- Structural offsets, wall thickness and fit gaps are named design inputs.
- Derived values are formulas or pure functions, not a second independent input.
  Cross-config functions receive the relevant configs explicitly, not globals.
- Document whether a clearance is radial/axial, per side or total. Diametral
  conversion applies twice a radial per-side gap.

```python
@dataclass(frozen=True)
class InsertConfig:
    outer_diameter_mm: float = 40.2  # purchased envelope, source/sample status
    fit_clearance_mm: float = 0.25   # model design, radial per side, mm

def seat_radius_mm(insert: InsertConfig):
    return insert.outer_diameter_mm/2 + insert.fit_clearance_mm
```

Take mating datums from the one interface source. A change to its input must
recompute both sides; do not copy a slot dimension into another part's code.
Physical dimensions in builders come from configuration/derive. Algorithmic
counts and numerical controls follow the project's contract rather than being
mistaken for new physical dimensions.

## Builder names and profiles

Use meaningful local names (`r_outer`, `z0`, `wall`, `clearance`), convert a diameter
once, and distinguish local/world/profile coordinates. For a revolved profile,
comment the meaning and traversal order of each point. Unit conversion and pure
versus Blender layers belong to `parametric-config`.

Detailed naming/dependency examples:
[variable-naming-cross-config](references/variable-naming-cross-config.md).
For a changed physical entity, update its actual config/derive, relevant invariant,
builder and construction documentation. The current task determines whether new
parts or mechanisms are authorized; this naming convention does not expand it.
