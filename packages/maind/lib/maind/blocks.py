"""Управляемый markdown-блок — вынесен в общий `core.block` (был единственным
писателем таких блоков; примитив generic и переиспользуем). Реэкспорт ради
обратной совместимости импортов `from .blocks import ...` / `from .common import ...`."""
from core.block import content_hash, managed_block, upsert_block  # noqa: F401
