from typing import TYPE_CHECKING

from skm.modules.planning.domain.allows_import_cycles_partner import Partner

if TYPE_CHECKING:
    from skm.modules.planning.domain.allows_domain_purity import decide


class Origin:
    partner: Partner
