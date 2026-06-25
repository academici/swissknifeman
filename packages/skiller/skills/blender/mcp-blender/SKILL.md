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

Полная таблица режимов отображения вьюпорта (shading/overlay, wireframe/solid/material/rendered) и их применение для скриншотов — [references/viewport-display-modes.md](references/viewport-display-modes.md).

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
