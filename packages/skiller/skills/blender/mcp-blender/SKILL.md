---
name: mcp-blender
bucket: blender
version: 0.1.0
description: "MCP Blender: инструменты (execute_blender_code, get_object_info, get_viewport_screenshot, get_scene_info), режимы отображения вьюпорта (tech/material/realism/xray), принцип камеры-через-хелпер, паттерн отправки кода и сброса кеша модулей (del sys.modules), скрытие мешающих объектов для скриншота, параллельная работа нескольких агентов. Активировать при работе с Blender через MCP — построение, настройка вьюпорта, скриншоты."
risk: write
persona: oss-dev
tags: [blender, mcp, python, 3d, bpy, viewport, camera, screenshot, orchestration]
requires: [version-gotchas]
produces_for: [build-loop]
outputs: []
snippets: ["role.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# MCP Blender — инструменты, вьюпорт, камера

Универсальный слой работы с Blender через MCP (любой bpy-проект). Дисциплину конкретного цикла
построения параметрической модели см. в скилле `blender-modeling/build-loop`.

## MCP-инструменты

| Инструмент | Назначение | Когда использовать |
|---|---|---|
| `execute_blender_code` | Выполнить Python в Blender | основной инструмент для построения и настройки |
| `get_viewport_screenshot` | Скриншот вьюпорта | только после установки камеры |
| `get_object_info` | Bounding box, вершины, материалы | проверка каждой изменённой детали до скриншота |
| `get_scene_info` | Список всех объектов сцены | см. ниже |

**`get_scene_info` — когда вызывать:**
- **После пересоздания сцены** — убедиться, что старые `MESH_*` объекты удалены и коллекция пересоздана чисто
- **После boolean DIFFERENCE** — проверить, что временный инструмент (имена начинаются с `_`) исчез из сцены (если остался — `apply_bool` не отработал)
- **При неожиданном поведении** — понять, что вообще есть в сцене перед отладкой

Polyhaven / Sketchfab / Hyper3D — не для parametric-моделей.

---

## Отправка кода и сброс кеша модулей

Blender **кеширует Python-модули** между запусками скриптов. Перед импортом своих модулей сбрасывать кеш, иначе правки файлов не подхватятся:

```python
import sys, os
_root = '<абсолютный путь к корню проекта>'   # подставить перед отправкой
_pkg  = '<имя пакета модели>'
for _k in list(sys.modules):
    if _k == _pkg or _k.startswith(_pkg + '.') or _k in ('lib', 'config') or _k.startswith(('lib.', 'config.')):
        del sys.modules[_k]
if _root not in sys.path: sys.path.insert(0, _root)
```

**Причина подстановки путей вручную:** Blender не наследует переменные окружения из shell — `os.environ` в Blender-скрипте, как правило, пуст. Абсолютные пути агент подставляет в код перед отправкой.

**При ошибке в `execute_blender_code` — стоп.** Прочитать traceback, исправить, повторить отправку (типовые ошибки сборки параметрической детали — таблица диагностики в `blender-modeling/build-loop`).

---

## Камера: универсальный принцип

```python
from {model}.common import set_viewport_camera

# z_mm  — центр изменённой зоны в мм (из bounding box)
# distance — высота_зоны_мм × 0.001 × 1.5, минимум 0.05
set_viewport_camera(z_mm=<z_centre>, distance=<distance>)
set_viewport_camera()  # вся модель целиком (distance по умолчанию из model_config)
```

- `z_mm=None` → центр модели (из `model_config`)
- `distance` — чем меньше, тем крупнее план
- Ракурс: `ORTHO`, вид на разрез `X=0`, наклон ~15° (`Euler(75°, 0°, -90°)`)
- **ЗАПРЕЩЕНО** задавать `view_rotation` вручную через Quaternion/Euler — модель перевернётся. Только `set_viewport_camera()`.

Готовые значения `z_mm` / `distance` для конкретной модели — в `models/{name}/ai/rules.md` (см. `blender-modeling/model-rules`).

---

## Проверка размеров

`world_bounding_box` из `get_object_info` → габариты в мм. Паттерн печати высоты/диаметра сразу после построения (до скриншота):

```python
def _bb(obj):
    xs = [v[0] for v in obj.bound_box]; zs = [v[2] for v in obj.bound_box]
    print(f"[BB] {obj.name}: h={(max(zs)-min(zs))*1000:.1f}mm  "
          f"z=[{min(zs)*1000:.1f},{max(zs)*1000:.1f}]mm  x_max={max(xs)*1000:.1f}mm")
```

Если `vertices_count == 0` или bounding box вырожден (все координаты одинаковые) — деталь не построилась.

---

## Режимы отображения вьюпорта

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

## Скрытие мешающих объектов для скриншота

Если нужная зона перекрыта соседними объектами — скрыть их на время скриншота, затем восстановить:

```python
import bpy

hidden = ["MESH_Model_Part", "MESH_Model_Part_SubPart"]   # имена подставить по текущей модели
for name in hidden:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_viewport = True

# ... get_viewport_screenshot() ...

for name in hidden:        # ВСЕГДА восстанавливать после скриншота
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_viewport = False
```

Когда скрывать — спросить пользователя или скрыть самостоятельно, если очевидно (верхняя деталь закрывает кольцо, корпус закрывает внутреннюю трубу).

---

## Параллельная работа нескольких агентов

Несколько агентов (например Cursor и Claude Code) могут выполнять полный флоу через MCP одновременно. Чтобы не затирать правки друг друга:

**Перед правкой кода:**
- Перечитать затрагиваемые `parts/*.py` и `config.py` — другой агент мог изменить файл.
- Если файл изменился с момента последнего чтения — применять правки поверх актуальной версии.

**Перед отправкой в Blender:**
- Перечитать все файлы, которые будут импортированы в Blender-скрипте.
- `del sys.modules` обязателен — Blender кеширует модули между запусками скриптов.

**Правило одного объекта:**
- Два агента не должны одновременно изменять один и тот же `parts/{name}.py`.
- Если задачи на одну деталь — выполнять последовательно, не параллельно.

---

## Связанные скиллы

- `blender/version-gotchas` — ловушки Blender 5.0 API: `temp_override`, нормали после boolean, `surface_render_method`; режим `realism` уже включает пересчёт нормалей.
- `blender-modeling/build-loop` — дисциплина цикла построения параметрической модели поверх этих инструментов.
- `blender-modeling/parametric-config` — архитектура `config.py`/`profile.py`/`parts/*`/`check.py`.
- `blender-modeling/model-rules` — `models/{name}/ai/rules.md`: готовые зоны камеры и специфика модели.
