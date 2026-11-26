# Thread and helical geometry

> Material, physics FDM, gaps according to the type of fit - in the body of the skill `blender-modeling/threading` (`SKILL.md`).

## How clearance is used in code

**Standard pattern** — clearance applied **to external thread only** («dad»):
- The base of the external thread is shifted inward by `clearance`: `r_base = r_nominal - thread_depth - clearance`
- Male thread tooth tip: `r_tip = r_base + thread_depth - clearance`
- Internal thread («mom») under construction **without correction** — she «host»

This gives an even gap across the entire coil profile.

**General principle for other pairs of parts:**

The gap can be distributed in two ways:
- **Only on dad** (external) — standard for FDM, where the outer contour is more precise than the inner one. This is exactly the case for external threads.
- **Equally between mom and dad** — if both parts are made of the same material and technology, and clearance without displacement of the center of the thread is important.

Selection rule: give the gap to the part that **is easier to deform when printing** (usually external). With the same technology - equally. When changing material or printer, recalculate `thread_clearance` for real measurements.

---

Specific thread parameters for pairs of parts of the current model - in `models/{name}/ai/rules.md`.
