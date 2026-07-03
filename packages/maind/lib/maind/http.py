"""HTTP-клиент (urllib) — вынесен в общий `core.http` (generic stdlib-примитив).
Реэкспорт ради обратной совместимости импортов `from .http import ...` /
`from .common import ...`."""
from core.http import http_get_json, http_post_json, ping  # noqa: F401
