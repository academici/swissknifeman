# Source: anonymized production project
"""
Параметры детали (generic Part) — по сущностям, без единого глобального PARAMS.

Все линейные размеры — в МИЛЛИМЕТРАХ (мм), если не указано иное.
Экземпляры *Config создаются ВНИЗУ файла — их и правит пользователь.
Зависимые размеры считает derive_all() из profile.py (вызов в конце файла).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# Узел силуэта: z — локальный от 0 до высоты ДАННОГО сегмента (мм); r — наружный радиус (мм).
ProfileKnot = Tuple[float, float]

# Цвет материала Blender: (R, G, B, A), каждое значение 0..1
Color = Tuple[float, float, float, float]


# ── Модель в целом (общий силуэт и разрешение) ───────────────────────────────


@dataclass
class ModelConfig:
    height: float = 120.0           # полная высота детали, мм
    wall: float = 2.4               # номинальная толщина стенки, мм
    profile_points: int = 200       # число точек интерполяции профиля (гладкость)
    segments: int = 128             # число сегментов тела вращения (грани по окружности)

    base_radius: float = field(default=0.0, init=False)  # наружный r на z=0; считает derive_all()


# ── Сегмент оболочки (тело вращения по узлам профиля) ────────────────────────


@dataclass
class ShellConfig:
    """Один сегмент наружной оболочки: силуэт задаётся узлами profile_knots."""

    color: Color = (0.85, 0.85, 0.85, 1.0)
    height: float = 60.0            # высота сегмента по Z, мм
    radius_bottom: float = 30.0     # наружный r на нижнем торце, мм (стык с предыдущим сегментом)
    radius_top: float = 24.0        # наружный r на верхнем торце, мм (стык со следующим)
    # Силуэт: локальный z ∈ [0, height]. ВНИМАНИЕ: последний z всегда == height.
    # derive_all() синхронизирует последний узел с актуальной height.
    profile_knots: List[ProfileKnot] = field(
        default_factory=lambda: [
            (0.0,  30.0),           # нижний торец
            (20.0, 30.0),           # ровная зона
            (45.0, 28.0),           # начало сужения
            (60.0, 24.0),           # верхний торец
        ]
    )


# ── Посадка/гнездо (joint) — соединение двух деталей ─────────────────────────


@dataclass
class JointConfig:
    """Цилиндрическая посадка «папа в маму»."""

    seat_inner_diameter: float = 24.0  # внутренний диаметр гнезда, мм
    depth: float = 10.0                # глубина посадки (высота цилиндра), мм
    wall: float = 2.0                  # толщина стенки посадочного цилиндра, мм
    clearance: float = 0.15            # зазор на сторону между папой и мамой, мм


# ── Резьба (параметры — см. навык blender/threading) ─────────────────────────


@dataclass
class ThreadConfig:
    """Печатаемая резьба (FDM/SLA). Зазор обязателен — точная резьба не вкрутится."""

    pitch: float = 1.0                 # шаг резьбы, мм
    depth: float = 0.4                 # глубина профиля зубца по R, мм
    turns: int = 3                     # число витков, шт
    clearance: float = 0.15            # радиальный зазор между резьбами на сторону, мм


# ── Производные функции (чистые, без bpy — переиспользуются в check.py) ───────


def joint_outer_radius(joint: "JointConfig") -> float:
    """Наружный радиус посадочного цилиндра (папа), мм: r_seat + стенка."""
    return joint.seat_inner_diameter * 0.5 + joint.wall


# ── Экземпляры (редактировать здесь) ─────────────────────────────────────────


model_config = ModelConfig()
shell_config = ShellConfig()
joint_config = JointConfig()
thread_config = ThreadConfig()

from .profile import derive_all  # noqa: E402 — после экземпляров, избежать цикла импорта

derive_all(model_config, shell_config, joint_config)

COLLECTION_NAME = "Part"
