# Variable naming and cross-config (details)

Skill reference `config-conventions`: variable part name tables and details
examples of inter-configuration dependencies.


## 2. Naming variables in part code (`parts/*.py`)

### Radii

| Variable | Meaning |
|---|---|
| `r_outer` | outer radius of the part / cylinder |
| `r_inner` | inner radius (cavity, channel) |
| `r_insert` | radius of the inserted / purchased item |
| `r_bore` | through hole radius (port, landing) |
| `r_rim` | side radius (ledge, overlapping element) |
| `r_view` | viewing hole radius / light channel |
| `r_slot` | radius of the cylindrical step of the groove |
| `r_groove_in` | internal radius of the L-slot |
| `r_base` | base radius of thread profile |
| `r_tip` | thread tip radius |
| `r_inner_floor` | minimum permissible inner radius (= `base_radius`) |

Diameter in config → radius in code: `r_insert = ic.outer_diameter * 0.5`

### Heights and z-coordinates

| Variable | Meaning |
|---|---|
| `z0` | bottom boundary of the part in world coordinates |
| `z1` | upper limit (= `z0 + height`) |
| `z_floor` | bottom of inner pocket / cavities |
| `z_groove_top` | upper edge of the groove Z |
| `z_groove_bot` | lower edge of the groove along Z |
| `mount_h` | bevel height / transition zone |
| `h_cap` | cover height |
| `h_half` | half-part height |

### Thicknesses and clearances

| Variable | Meaning |
|---|---|
| `wall` | wall thickness (from `model_config.wall`) |
| `gw` | groove_width — groove width according to Z |
| `gd` | groove_depth — groove depth according to R |
| `slide_gap` | gap under sheet/sliding part |
| `clearance` | radial thread clearance |
| `tdepth` | thread profile depth |

### Local config aliases

At the beginning of each builder function there are short aliases (1–2 letters each from the part name):

```python
def build_shell(spl, col):
    m  = model_config       # general model config
    sh = shell_config       # current part
    ins = insert_config     # inserted element
```

Rule: alias read (`sh` — shell, `ins` — insert, `mt` — mount), is the same throughout the file; general model config - always `m`.

---


## 7. Inter-configuration dependencies (cross-config)

Details **can and should** read each other's configs if there is a physical connection between them.

**Rule:** source of truth - one config. All other parts that are adjacent to it read its parameters directly - they do not duplicate numbers.

```python
# Part part_a.py reads the config part_b, to accurately land:
from ..config import part_b_config, part_a_config

def build_part_a(spl, col):
    pb = part_b_config
    pa = part_a_config
    # Landing cylinder («mom») — geometry from the config part_b:
    r_joint_in = spl.r(pb.height) - pb.joint_wall   # landing radius
    z_joint_bot = pb.height - pb.joint_depth          # bottom edge of the groove
```

**Typical types of connections between parts:**

| Situation | Detail reads config |
|----------|----------------------|
| Part A accepts the part into the groove B | A reads the config B: dimensions, clearances |
| Part A fits the part B | A reads the config B: `joint_depth`, `joint_wall`, `joint_clearance` |
| Part A forms a bowl under the element C | A reads the config C: outer diameter, height, clearance |
| Connecting element between A and B | reads the configs of both parts |

Specific connections for the current model - in `models/{name}/ai/rules.md` (see skill `blender-modeling/model-rules`).

**The principle of end-to-end recalculation is mandatory when constructing:**

For any change in the config, the entire associated chain of parts must be recalculated without manual editing. Check mentally:

- Changed `wall` housings → inner radius has moved → the groove of the mating part must not «swim»
- Changed `height` lower part → the top has risen → the connection ring must remain in place relative to the joint
- Insert size changed → the bowl was counted for her → the part does not protrude beyond the body

If a mental check shows that the part «will float» — means there is a hard code in its code that needs to be replaced with the formula from the config.

**Explicit import of the config of someone else's part is normal:**

```python
# holder.py — reads the config of the inserted part to build a bowl exactly for it
from ..config import insert_config, holder_config

def build_holder(spl, col):
    ic = insert_config   # insert part (board, optics, cartridge...)
    hc = holder_config
    r_cup_outer = ic.outer_diameter * 0.5 + ic.wall + hc.cup_clearance
    # ^ if insert will change - the bowl will rearrange itself automatically
```

---

