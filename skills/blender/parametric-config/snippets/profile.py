# Source: anonymized production project
"""
Построение профиля из узлов и тело вращения (revolve) по оси Z.

В config.py каждый сегмент хранит profile_knots — ЛОКАЛЬНЫЙ z от 0 до высоты сегмента.
derive_all() пересчитывает зависимые размеры и синхронизирует последний узел с height.

revolve_profile() требует Blender — bpy/bmesh импортируются ЛЕНИВО (внутри функции),
чтобы этот модуль импортировался обычным Python (check.py, тесты уровня 1, CI).
"""

from __future__ import annotations

from typing import List, Tuple

# Конвертация единиц: модель в мм, Blender — в метрах.
def mm(v: float) -> float:
    """Миллиметры → метры (единицы Blender)."""
    return v * 0.001


ProfileKnot = Tuple[float, float]  # (z, r) — оба в мм


# ── Пересчёт зависимых размеров (без bpy) ────────────────────────────────────


def derive_all(model, shell, joint) -> None:
    """Считает производные размеры из конструкции один раз после создания экземпляров.

    1. base_radius — наружный r на z=0 из посадки и стенки.
    2. Последний узел profile_knots синхронизируется с актуальной height
       (z последнего узла обязан совпадать с высотой сегмента).
    """
    model.base_radius = joint.seat_inner_diameter * 0.5 + joint.wall + model.wall

    if shell.height >= model.height:
        raise ValueError(f"shell.height={shell.height} >= model.height={model.height}")

    if shell.profile_knots:
        last_r = shell.profile_knots[-1][1]
        shell.profile_knots[-1] = (shell.height, last_r)

    _validate_local_profile(shell)


def _validate_local_profile(shell) -> None:
    """Первый узел z должен быть 0, последний — равен высоте сегмента."""
    tol = 1e-3
    knots = shell.profile_knots
    if not knots:
        raise ValueError("profile_knots пуст")
    if abs(knots[0][0]) > tol:
        raise ValueError(f"первый узел z должен быть 0, сейчас {knots[0][0]}")
    if abs(knots[-1][0] - shell.height) > tol:
        raise ValueError(
            f"последний узел z должен быть {shell.height} (высота сегмента), сейчас {knots[-1][0]}"
        )


def interpolate_profile(knots: List[ProfileKnot], n_points: int) -> List[ProfileKnot]:
    """Линейная интерполяция силуэта в n_points равномерных точек по z (мм).

    Узлы в config.py — опорные; промежуточные точки считаются здесь, а не хардкодятся.
    Для гладкого силуэта здесь можно подставить сплайн (Catmull-Rom) — интерфейс тот же.
    """
    z0, z1 = knots[0][0], knots[-1][0]
    out: List[ProfileKnot] = []
    for i in range(n_points + 1):
        z = z0 + (z1 - z0) * i / n_points
        out.append((z, _r_at_z(knots, z)))
    return out


def _r_at_z(knots: List[ProfileKnot], z: float) -> float:
    """Радиус (мм) на высоте z линейной интерполяцией между опорными узлами."""
    if z <= knots[0][0]:
        return knots[0][1]
    if z >= knots[-1][0]:
        return knots[-1][1]
    for (z_a, r_a), (z_b, r_b) in zip(knots, knots[1:]):
        if z_a <= z <= z_b:
            t = (z - z_a) / (z_b - z_a) if z_b > z_a else 0.0
            return r_a + (r_b - r_a) * t
    return knots[-1][1]


# ── Тело вращения (требует Blender; bpy/bmesh — ленивый импорт) ───────────────


def revolve_profile(name: str, knots_zr: List[ProfileKnot], col, segments: int):
    """Тело вращения из 2D-профиля (список (z, r) в мм) вокруг оси Z.

    1. Убирает соседние дубликаты узлов.
    2. Строит замкнутый bmesh-профиль в плоскости XZ (каждая точка через mm()).
    3. Навешивает SCREW-модификатор по Z и применяет.

    Возвращает готовый bpy.Object.
    """
    import bpy
    import bmesh

    # 1. Убрать соседние дубликаты.
    clean: List[ProfileKnot] = [knots_zr[0]]
    for z, r in knots_zr[1:]:
        if abs(z - clean[-1][0]) > 1e-6 or abs(r - clean[-1][1]) > 1e-6:
            clean.append((z, r))

    # 2. Замкнутый профиль в XZ (x = r, z = z), всё в метрах через mm().
    bm = bmesh.new()
    verts = [bm.verts.new((mm(r), 0.0, mm(z))) for z, r in clean]
    for i in range(len(verts) - 1):
        bm.edges.new((verts[i], verts[i + 1]))
    bm.edges.new((verts[-1], verts[0]))  # замыкаем контур

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)

    # 3. SCREW по оси Z — полный оборот за segments шагов.
    scr = obj.modifiers.new("Screw", "SCREW")
    scr.axis = "Z"
    scr.steps = scr.render_steps = segments
    scr.use_merge_vertices = True
    scr.merge_threshold = mm(0.05)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="Screw")
    return obj
