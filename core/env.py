"""Базовый Env — общее ядро контекста запуска (root/cmd/home).

Исторически дублировалось байт-в-байт в swissknifeman/maind: frozen dataclass с
полями root/cmd/home и __post_init__, нормализующим root/home в Path. Доменные
path-property (state_dir, db_file, data_dir, …) у каждого пакета свои — они
объявляются в подклассе. frozen=True сохраняется и в подклассах."""
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home()


@dataclass(frozen=True)
class BaseEnv:
    """Контекст запуска: корень репозитория, текущая команда, домашний каталог.

    Значения передаются явно (не модульные глобали) — функции тестируемы: можно
    подсунуть временный root и home, не трогая argv процесса. frozen=True: контекст
    запуска неизменен; __post_init__ нормализует root/home в Path (принимаем str/Path)."""

    root: Path
    cmd: str = ""
    # Зовём Path.home() при создании экземпляра (а не модульный снимок HOME) —
    # подменённый в тестах $HOME подхватывается. Модульный HOME оставлен как
    # публичная константа (re-export в core.__init__, STATE_DIR в пакетах).
    home: Path = field(default_factory=lambda: Path.home())

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(self, "home", Path(self.home))
