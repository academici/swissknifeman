"""academici_core — общий stdlib-only фундамент пакетов монорепо.

Здесь живут ТОЛЬКО дословные дубли, которые исторически копировались между
swissknifeman/maind/brain байт-в-байт: вывод (die/warn/now_iso/confirm), slug
(sanitize) и базовый Env (общее ядро root/cmd/home). Доменные надстройки —
path-property, parse_args/parse_flags, atomic JSON, HTTP, frontmatter — остаются
в common.py каждого пакета (они расходятся по контракту и не дословны).

Без сторонних зависимостей. Подключается через PYTHONPATH (см. bin-лаунчеры)."""
from .env import HOME, BaseEnv
from .term import confirm, die, now_iso, warn
from .text import sanitize

__all__ = ["HOME", "BaseEnv", "die", "warn", "now_iso", "confirm", "sanitize"]
