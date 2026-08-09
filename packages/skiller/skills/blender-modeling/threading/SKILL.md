---
name: threading
bucket: blender-modeling
version: 0.1.1
description: "Use when designing threads on FDM/SLA parts: material, print physics, radial clearance by fit type."
risk: write
persona: oss-dev
tags: [blender, 3d, fdm, sla, threading, geometry, bpy]
requires: []
produces_for: [parametric-config, build-loop]
outputs: []
snippets: ["snippets-threading.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: threads on FDM/SLA parts

## Material / production
- Threaded parts: FDM/SLA printer, PG plastic (photopolymer or PETG).
- Threads are printed, not cut — accuracy limited by printer resolution (~0.1–0.2 mm).
- Plastic is elastic: threads deform slightly on tightening and self-center.
- Post-print surface not perfectly smooth → extra friction.
- Rule: zero-clearance thread won't engage in reality. Always add radial clearance.

## Clearance for PG plastic (FDM/SLA)

| Use | `thread_clearance` (per side) | Per diameter |
|---|---|---|
| Hand-tightening, no tool | **0.15 mm** | 0.3 mm |
| Tight fit (with force) | 0.05–0.10 mm | 0.1–0.2 mm |
| Free sliding | 0.20–0.25 mm | 0.4–0.5 mm |

- On material/printer change: recompute `thread_clearance` from real measurement after first print.

## Blender 5.x SCREW modifier
Triangular tooth profile (simplified metric thread):

```python
# Single-turn profile (r, z) — isosceles triangle
thread_pts = [
    (r_base,  0.0),
    (r_tip,   pitch / 2),
    (r_base,  pitch),
]
# SCREW modifier:
scr.screw_offset = mm(pitch)   # rise per revolution
scr.iterations   = max(turns - 1, 1)  # profile already spans one pitch
```

- Triangular profile suffices for PG; turns self-center on tightening.
- Per-pair thread params for current model → `models/{name}/ai/rules.md`.
- Trapezoidal profile variant: use if triangle jams after print (add per measurement).

## Geometry guardrails

- Materialize an external thread with `UNION` into its structural sleeve. Cut an internal
  thread with `DIFFERENCE` from a crest-radius bore: unioning a tooth inside an already-solid
  wall is a geometric no-op that leaves a smooth bore.
- When the source triangle already spans one pitch in Z, `N` turns require
  `SCREW.iterations = N - 1`. For multistart threads, distinguish pitch from lead and assert
  the evaluated tool's actual axial span.
- Metadata, bbox, volume and manifold status do not prove that a thread exists. Evaluated tests
  must sample radial modulation on both mating surfaces and a positive assembled radial gap.
- After every later Boolean, re-check modulation, the structural sleeve/base/face and the
  decoration keep-out. A mesh-joined feature can be erased by a downstream Boolean.

## External docs
- [Blender SCREW modifier](https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/screw.html)
- [FDM thread tolerances — Prusa Knowledge Base](https://help.prusa3d.com/article/tolerances_n_of_fdm_3d_printing)

## Related skills
- `blender-modeling/parametric-config` — `*_thread_*` and `*_clearance` params as dataclass fields in `config.py`; invariant `thread_depth > thread_clearance` checked in `check.py`.
- `blender-modeling/model-rules` — "Thread params" table in `models/{name}/ai/rules.md` holds pitch/depth/turns/clearance per part pair.
- `blender-modeling/build-loop` — overall build/check cycle with thread printing embedded.
- `blender/version-gotchas` — SCREW modifier and `temp_override` gotchas in Blender 5.0.
