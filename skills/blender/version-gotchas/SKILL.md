---
name: version-gotchas
bucket: blender
version: 0.1.0
description: "Известные breaking changes и ловушки Blender 5.0 API"
risk: write
persona: oss-dev
tags: [blender, api]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Blender version gotchas

Известные breaking changes и ловушки, актуальные для **Blender 5.0** (версия проекта).

---

## API, которое изменилось или убрано

| Старый паттерн | Что делать в 5.0 |
|----------------|-----------------|
| `bpy.ops.*({"active_object": obj})` — dict-контекст | `with bpy.context.temp_override(active_object=obj): bpy.ops.*()` |
| `solver='FAST'` в Boolean | `solver='FLOAT'` (FAST убран) |
| `mat.blend_method = 'OPAQUE'` | `mat.surface_render_method = 'DITHERED'` (непрозрачный) / `'BLENDED'` (с альфа) |
| `mat.shadow_method` | атрибут убран, не существует |
| `me.calc_normals()` | убран; пересчёт через `bmesh.ops.recalc_face_normals(bm, faces=bm.faces)` |
| `import bgl` | убран; использовать `import gpu` |
| EEVEE-свойства рендера на scene | переехали в `view_layer` |

---

## Критические ловушки

### Нормали после boolean

`blender_bool_apply` (DIFFERENCE/UNION) может инвертировать нормали внешней поверхности. Симптом: стенки «прозрачные» в viewport — сквозь них видна внутренняя полость.

**Лечение:** пересчитать нормали после булевых операций:
```python
import bmesh
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
```

Это уже встроено в режим `realism` (`mcp-blender-workflow.md`). При подозрении на инвертированные нормали — включить `realism` и проверить.

### `bpy.ops` без override в 5.0

Начиная с Blender 4.0 передача контекста через dict-аргумент убрана. Без `temp_override` оператор упадёт с `RuntimeError: Calling operator "bpy.ops.object.modifier_apply" ... context is incorrect`.

### `surface_render_method` не меняется через `blend_method`

В Blender 5.0 `mat.blend_method` существует, но присвоение игнорируется. Нужно менять `mat.surface_render_method`:
- `'DITHERED'` — непрозрачный (аналог старого `OPAQUE`)
- `'BLENDED'` — с альфа-блендингом

### Материал без нод = дефолтный серый

Объект без назначенного материала отображается системным серым. В viewport mode `MATERIAL` выглядит как «прозрачный» потому что backface culling отрабатывает на гранях без материала иначе. Решение: всегда назначать материал явно.

---

## Производительность

- `bpy.data` + `bmesh` в 25–300x быстрее `bpy.ops` для построения мешей
- `foreach_set()` для массовой записи координат вершин (через NumPy): массив должен быть `.flatten()` или `.ravel()` перед передачей
