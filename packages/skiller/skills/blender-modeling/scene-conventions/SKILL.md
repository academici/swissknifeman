---
name: scene-conventions
bucket: blender-modeling
version: 0.1.0
description: "Соглашения сцены параметрической модели: префиксы объектов (MESH_/CRV_/LGT_/MTL_), иерархия parenting по физической принадлежности, коллекции, назначение материала из поля color конфига. Активировать при создании объектов/материалов в сцене, настройке parenting подчастей составной детали, вопросах про имена объектов и серый материал."
risk: write
persona: oss-dev
tags: [blender, cad, parametric, naming, scene, materials, parenting, bpy]
requires: []
produces_for: [build-loop]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Именование объектов и сцена

## Префиксы объектов

| Префикс | Тип |
|---------|-----|
| `MESH_` | Меши |
| `CRV_` | Кривые |
| `LGT_` | Свет |
| `MTL_` | Материалы |

Коллекция: константа `COLLECTION_NAME` в `config.py` (например `"Model"`).

## Иерархия объектов (parenting)

Составная деталь строится по схеме **Вариант A**: основная оболочка — родитель, подчасти — дочерние.

```
MESH_Model_Body                    ← родитель
└── MESH_Model_Body_ConnRing       ← дочерний

MESH_Model_Nose                    ← родитель
└── MESH_Model_Nose_ConnRing       ← дочерний
    ├── MESH_Model_Nose_Pin_1      ← дочерний к кольцу (не к носу!)
    ├── MESH_Model_Nose_Pin_3
    └── MESH_Model_Nose_Pin_5
```

Принцип: **объект привязывается к тому родителю, без которого он не может существовать физически.** Штыри — часть соединительного кольца, поэтому дочерние к кольцу, а не к носу.

Установка через `set_parent(child, parent)` из `{model}.common`:

```python
from {model}.common import set_parent
set_parent(ring, body)
set_parent(pin, ring)   # не set_parent(pin, nose)!
```

**Правила:**
- `set_parent` вызывается **после всех boolean-операций** над дочерним объектом
- Каждая подчасть, становящаяся дочерним объектом, строится в **отдельной `_build_*` функции** — не inline в оркестраторе
- Оркестратор `build_*` только вызывает `_build_*` / `_cut_*` и выставляет parenting перед `return`

**Зачем:** глазик в Outliner скрывает всю деталь вместе с подчастями; иерархия отражает физическую принадлежность деталей.

## Материалы: назначение через конфиг

Каждая деталь получает материал из поля `color: Color` своего `*Config`. Паттерн создания и назначения — через `common.py` (функция `apply_material` должна быть реализована в `common.py` модели):

```python
from {model}.common import apply_material

# В build_*() после revolve_profile:
obj = revolve_profile("MESH_Model_Part", pts, col, seg)
apply_material(obj, "MTL_Model_Part", cfg.color)
```

Если `apply_material` ещё не реализована — добавить в `common.py`:
```python
def apply_material(obj, name: str, color):
    import bpy
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = False
    mat.diffuse_color = color
    mat.surface_render_method = 'DITHERED'   # Blender 5.0
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
```

**Правила:**
- Имя материала: `MTL_` + имя объекта без префикса `MESH_` (например `MTL_Model_Body`)
- Цвет — `(R, G, B, A)` 0..1, хранится в `*Config.color`
- Один материал на один объект; подчасти (`ConnRing`, `Pin`) получают тот же материал что родитель
- Объект без материала в режиме `MATERIAL` выглядит серым — всегда назначать явно
- В Blender 5.0: `mat.surface_render_method = 'DITHERED'` (не `blend_method`) → скилл `blender/version-gotchas`

## Код Python

- Пакет: `models/{name}/`, точка входа `{name}.py`, функция `main()`
- Деталь: один файл в `parts/`, экспорт `build_*`
- Импорты внутри пакета относительные: `from .config import ...`

## Связанные скиллы

- `blender-modeling/config-conventions` — именование переменных и конфигов, из чьего поля `color` берётся материал.
- `blender-modeling/parametric-config` — построение меша (`revolve_profile`), к выходу которого применяются эти имена и материалы.
- `blender/version-gotchas` — `surface_render_method` вместо `blend_method` в Blender 5.0.
