from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.modules.planning.domain.allows_import_cycles import Origin


class Partner:
    origin: "Origin | None" = None
