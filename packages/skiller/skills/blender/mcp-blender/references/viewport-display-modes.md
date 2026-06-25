# Режимы отображения вьюпорта

Справочник к скиллу `mcp-blender`.


Именованные пресеты. Применять по команде пользователя или самостоятельно выбирать оптимальный для задачи.

### `tech` — технический вид (дефолтный для проверки геометрии)

**Когда:** проверка формы, размеров, стыков, пазов, резьбы. Максимальная читаемость рёбер и полостей.

```python
import bpy
bpy.ops.object.select_all(action='DESELECT')
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'SOLID'
                sh.light = 'FLAT'
                sh.show_backface_culling = True
                sh.background_type = 'VIEWPORT'
                sh.background_color = (0.28, 0.28, 0.28)
                sh.color_type = 'SINGLE'
                sh.single_color = (0.92, 0.92, 0.92)
                sh.show_cavity = True
                sh.cavity_type = 'BOTH'
                sh.curvature_ridge_factor = 0.25
                sh.curvature_valley_factor = 2.0
                sh.show_xray = False
                ov.show_wireframes = True
                ov.wireframe_opacity = 1.0
                ov.show_floor = False
                ov.show_axis_x = ov.show_axis_y = ov.show_axis_z = False
                ov.show_overlays = True
        break
```

### `material` — цветовая идентификация деталей

**Когда:** проверка принадлежности детали, цветовая дифференциация после сборки, крупные планы стыков.

```python
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'MATERIAL'
                sh.use_scene_lights = False
                sh.use_scene_world = False
                sh.show_backface_culling = True
                sh.show_xray = False
                if hasattr(sh, 'studiolight_intensity'):
                    sh.studiolight_intensity = 1.15
                sh.show_cavity = True
                sh.cavity_type = 'BOTH'
                sh.curvature_ridge_factor = 0.35
                sh.curvature_valley_factor = 1.4
                ov.show_wireframes = True
                ov.wireframe_opacity = 0.42
                ov.show_floor = False
                ov.show_axis_x = ov.show_axis_y = ov.show_axis_z = False
                ov.show_overlays = True
        break
```

### `realism` — максимальный реализм (презентация)

**Когда:** итоговый скриншот для оценки внешнего вида, демонстрация пользователю. Перед применением — пересчитать нормали (см. `blender/version-gotchas`).

```python
import bpy, bmesh

# Пересчёт нормалей (если были инвертированы после boolean)
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data); bm.free(); obj.data.update()

for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'MATERIAL'
                sh.use_scene_lights = False
                sh.use_scene_world = False
                sh.show_backface_culling = True
                sh.show_xray = False
                if hasattr(sh, 'studiolight_intensity'):
                    sh.studiolight_intensity = 1.2
                ov.show_wireframes = False
                ov.show_overlays = False
        break
```

### `xray` — просмотр внутренней геометрии

**Когда:** отладка полостей, проверка заливки, просмотр скрытых деталей (труба внутри корпуса, гнёзда магнитов).

```python
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                sh = space.shading; ov = space.overlay
                sh.type = 'SOLID'
                sh.show_xray = True
                sh.xray_alpha = 0.25          # прозрачность: 0.1 (почти невидимо) … 0.5 (полупрозрачно)
                sh.color_type = 'MATERIAL'
                sh.show_backface_culling = False
                sh.background_type = 'VIEWPORT'
                sh.background_color = (0.22, 0.22, 0.22)
                ov.show_wireframes = True
                ov.wireframe_opacity = 0.3
                ov.show_floor = False
                ov.show_axis_x = ov.show_axis_y = ov.show_axis_z = False
                ov.show_overlays = True
        break
```

| Режим | Команда пользователя | Лучший для |
|-------|---------------------|------------|
| `tech` | «включи tech» | геометрия, размеры, стыки, резьба |
| `material` | «включи material» | цвета деталей, крупные планы |
| `realism` | «включи realism» | презентация, итоговый вид |
| `xray` | «включи xray» | полости, заливка, скрытые детали |

**Автовыбор режима агентом:**
- Построение и проверка геометрии → `tech`
- Цветовая дифференциация деталей → `material`
- Итоговая демонстрация / презентация пользователю → `realism`
- Отладка полостей, нормалей, внутренних деталей → `xray`

---
