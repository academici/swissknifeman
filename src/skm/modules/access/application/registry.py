"""Bus operations of the access module (access §7, §8)."""

from skm.modules.access.application.commands import (
    bootstrap_local_owner,
    create_principal,
    create_token,
    disable_principal,
    grant_membership,
    revoke_membership,
    revoke_token,
    rotate_token,
)
from skm.modules.access.application.queries import (
    get_principal,
    list_memberships,
    list_principals,
    list_tokens,
    whoami,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    create_principal.SPEC,
    disable_principal.SPEC,
    create_token.SPEC,
    revoke_token.SPEC,
    rotate_token.SPEC,
    grant_membership.SPEC,
    revoke_membership.SPEC,
    bootstrap_local_owner.SPEC,
)
QUERIES = (
    whoami.SPEC,
    get_principal.SPEC,
    list_principals.SPEC,
    list_tokens.SPEC,
    list_memberships.SPEC,
)
