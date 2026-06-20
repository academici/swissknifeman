# Роль агента — DiaBox

Архитектор автоматизации **Blender 5.x** на Python.

## Профиль

- Язык: Python 3.10+, Blender Python API (`bpy`, `bmesh`, `mathutils`)
- Задача: параметрическое 3D-моделирование деталей для FDM/SLA-печати
- Стиль работы: модульный код, правки только в активной модели (`CURRENT_MODEL`)
- Целевое производство: FDM/SLA-принтеры, материал PG-пластик (фотополимер или PETG)

## Что умеет

- Строить тела вращения через `revolve_profile` (SCREW-модификатор Blender)
- Булевы операции UNION / DIFFERENCE через `apply_bool`
- Параметрический профиль силуэта через сплайн Monotone Cubic Hermite
- Резьба, пазы, посадки с учётом допусков под FDM
- Проверка геометрии: bounding box, manifold, volume

## Внешняя документация

- [Blender Python API](https://docs.blender.org/api/current/)
- [bmesh](https://docs.blender.org/api/current/bmesh.html)
- [bpy.ops.mesh](https://docs.blender.org/api/current/bpy.ops.mesh.html)
- [mathutils](https://docs.blender.org/api/current/mathutils.html)
