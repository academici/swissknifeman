---
name: config-conventions
bucket: blender-modeling
version: 0.1.0
description: "Parametric CAD config conventions: one entity = one dataclass; variable naming (r_outer/z0/wall/clearance); units mm; everything-from-formulas (no magic numbers in parts/); cross-config dependencies and end-to-end recompute; part-adding pattern. Activate on config.py edits, adding a param/part, cross-config questions, hardcoded sizes, reading another part's config."
risk: write
persona: oss-dev
tags: [blender, cad, parametric, dataclass, config, cross-config, conventions, bpy, fdm, sla]
requires: []
produces_for: [parametric-config, build-loop]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Config & variable-naming conventions

Apply to all models in `models/*/`.

## 1. One entity = one dataclass

Each physical entity (part, material, insert/purchased element) gets its own `@dataclass` in the model's `config.py`.

```python
@dataclass
class ShellConfig:
    height: float = 60.0          # высота, мм
    wall: float = 2.8             # толщина стенки, мм
    outer_diameter: float = 40.0  # наружный диаметр, мм

@dataclass
class InsertConfig:                # внешний/покупной элемент, вставляемый в деталь
    outer_diameter: float = 40.2  # посадочный ⌀, мм
    thickness: float = 3.5        # толщина, мм
```

Rules:
- Class name: `PascalCase` + `Config` suffix → `ShellConfig`, `MountConfig`, `InsertConfig`.
- Instance name: `snake_case` + `_config` suffix → `shell_config`, `mount_config`.
- Declare instances at the **bottom** of `config.py`, after all classes.
- All linear sizes in **mm**; color `(R, G, B, A)` 0..1.
- If a param is computed from others → `@property`/method, do not store in a field.
- Methods depending on other configs take them as **arguments** (never read globals).

```python
# Правильно: аргументы явные
def full_stack_height(self, insert: InsertConfig, plate: PlateConfig) -> float:
    return 2 * self.wall + 2 * insert.thickness + plate.thickness

# Неправильно: скрытая зависимость от глобала
@property
def full_stack_height(self):
    return 2 * self.wall + 2 * insert_config.thickness  # хрупко
```

## 2. Variable naming in part code (`parts/*.py`)

Full name tables (radii `r_*`, heights/`z*`, thicknesses/clearances) + local config aliases → [references/variable-naming-cross-config.md](references/variable-naming-cross-config.md). Brief:
- Name says meaning (`r_outer`/`z0`/`wall`), not `r1/r2`.
- Diameter in config → radius in code (`r = d * 0.5`).
- At builder start, short config aliases (`m`=model, `sh`=shell).

## 3. Profile `pts`: how to build

Point order, closing rule, non-manifold diagnostics → skill `blender-modeling/parametric-config` (snippet `internals.md`, section «Профиль `pts`»).

Point-naming rule: each point gets an inline comment with its meaning:

```python
pts = [
    (r_outer, 0.0),          # наружный низ
    (r_outer, h_cap),        # наружный верх
    (r_rim,   h_cap),        # бортик: шаг внутрь
    (r_rim,   h_cap - gw),   # вертикаль бортика вниз
    (r_inner, h_cap - gw),   # горизонт (дно паза)
    (r_inner, 0.0),          # внутренняя стенка вниз
]
```

## 4. Pattern: adding a new entity

Step 1 — config in `config.py`:
```python
@dataclass
class InsertConfig:
    outer_diameter: float = 40.2   # посадочный ⌀, мм
    thickness: float = 3.5         # толщина, мм

insert_config = InsertConfig()
```

Step 2 — part in `parts/insert.py`:
```python
from ..config import insert_config, model_config
from ..common import build_revolved_solid

def build_insert(col):
    ic = insert_config
    r_outer = ic.outer_diameter * 0.5
    ...
```

Step 3 — checks in `test/check.py` (cross-part) or `parts/{name}.test.py` (local):
```python
# В test/check.py — если новая деталь взаимодействует с существующей:
check(ic.outer_diameter <= mt.seat_inner_diameter + 0.4, ...)

# В parts/insert.test.py → test_config() — локальные инварианты самой детали:
assert ic.outer_diameter > 0
assert ic.thickness >= 1.0
```

Step 4 — call in `main()` in `{model}.py`.

Step 5 — part description in `models/{name}/docs/tech.md`: row in parts table + construction section.

## 5. Units

Full picture (table, `mm()` function, rule, examples) → skill `blender-modeling/parametric-config` (snippet `internals.md`, section «Единицы измерения»).

Config specifics:
- All fields in `config.py` — **mm**: `height = 60.0`, `wall = 2.8`.
- Angles in configs — **degrees** (Blender API — radians via `math.radians(...)`).
- Color — `(R, G, B, A)` in `0.0..1.0`; type `Color = Tuple[float, float, float, float]` in `config.py`.

## 6. Everything-from-formulas (mandatory)

All part geometry params must be **derived from config by formulas**, not literal numbers in code.

External/purchased parts also go in config: any part that is not printed but constrains geometry (insert, glass, board, battery, fastener) must have its own `*Config` with physical sizes. Those sizes feed formulas; changing a part's size = one config line, rest recomputes automatically.

```python
# Правильно: паз под плату берётся из конфига платы
board_r = board_config.width * 0.5 + board_config.clearance

# Неправильно: размер платы зашит в детали
board_r = 17.5   # откуда это число? не очевидно, не обновляется
```

Rules:
- Task says "offset 2 mm from wall" → add config field (e.g. `inner_margin: float = 2.0`); code: `r = r_wall - conn.inner_margin`.
- Part must **match another part's slot** → read slot params from that part's config, don't duplicate numbers:

```python
# Правильно: размер папы берётся из конфига мамы
jd = float(mt.joint_depth)     # глубина посадки
jw = float(mt.joint_wall)      # толщина стенки папы
jclr = float(mt.joint_clearance)
r_papa_out = r_wall_top         # наружный r папы = внутренний r мамы
r_papa_in  = r_papa_out - jw

# Неправильно: числа прописаны вручную
r_papa_out = 32.35
r_papa_in  = 29.85
```

- If task doesn't say **how to compute** a param → derive from neighboring configs by physical meaning (wall + clearance + element size + clearance), write the formula in a comment.
- Every config field — with a comment: what it is, where it comes from, in mm.

Example: connection ring element
```
ring_inner_r = inner_r_mating_part
             - conn.inner_margin        # отступ от внутренней стенки
             - conn.element_diameter/2  # радиус встраиваемого элемента (магнит, штырь)
             - conn.inner_margin        # ещё отступ до края кольца
```
This is a formula, not a number. Change `element_diameter` in config → ring recomputes automatically.

## 7. Cross-config dependencies

Parts **may and must** read each other's configs on physical link; single source of truth = one config, others read its params without duplicating numbers. Detailed examples (importing another config, link kinds, end-to-end recompute) → [references/variable-naming-cross-config.md](references/variable-naming-cross-config.md). End-to-end recompute is mandatory: changing a config recomputes the whole linked chain with no manual edits — if a part "drifts", code has a hardcode to replace with a formula.

## 8. Don't

- No magic numbers in `parts/*.py` — only via config.
- No `r1`, `r2`, `r3` — name must say meaning.
- Don't duplicate diameter/radius computation — compute once at function start.
- Don't read global configs inside dataclass methods — take as arguments.
- Don't add a field to an existing config for a new entity — create a separate class.
- Don't write sizes in part code that already exist in another part's config — read from there.

## Related skills

- `blender-modeling/parametric-config` — `config.py`/`profile.py`/`check.py` layer, units, `spl`/`pts` internals (snippets `config-and-profile.md`, `internals.md`).
- `blender-modeling/model-rules` — `models/{name}/ai/rules.md` template fixing model-specific cross-config links.
- `blender-modeling/scene-conventions` — scene object & material naming.
- `blender-modeling/threading` — thread params (`*_clearance`, `*_thread_*`) set up per these conventions.
