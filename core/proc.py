"""Процессы — общий stdlib-only примитив монорепо.

Проверка «жив ли pid» копировалась в maind (agents/memory) с расхождением: одна
копия НЕ ловила OverflowError и падала на битом/огромном pid. Сведено сюда в
устойчивой редакции. stdlib-only."""
import os


def pid_alive(pid):
    """True/False жив ли процесс; None если pid не задан (неизвестно).

    PermissionError → жив (процесс чужой, но существует). Битый/огромный/нечисловой
    pid (ValueError/OverflowError) трактуем как «жив» (не роняем вызывающего) —
    консервативно: недоказанная смерть не выдаётся за смерть."""
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, ValueError, OverflowError):
        return True
